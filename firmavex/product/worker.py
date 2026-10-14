"""Supervised JSON-line worker: one job, responsive cooperative cancellation."""

from __future__ import annotations

import sys
import os
import threading
import hashlib
from typing import Any, BinaryIO

from .errors import ProductError
from .protocol import MAX_LINE_BYTES, decode_command, encode_event

_FIELDS = {
    "capabilities": (set(), set()), "doctor": (set(), set()), "validate": ({"config"}, set()),
    "run": ({"config", "output_dir"}, set()),
    "reproduce": ({"run_dir", "output_dir"}, {"attempts"}),
    "inspect": ({"run_dir"}, set()), "export": ({"run_dir", "output_dir"}, set()),
    "recover": ({"run_dir"}, set()), "restart": ({"run_dir", "output_dir"}, set()),
    "demo": ({"output_dir"}, set()),
    "build_example": ({"output_dir"}, set()),
    "prepare_example": ({"output_dir"}, set()), "setup_runtime": (set(), set()),
    "runtime_history": (set(), set()), "rollback_runtime": ({"generation"}, set()),
    "demo_builtin": ({"output_dir"}, set()),
    "backend_check": ({"profile"}, set()),
    "backend_prepare": ({"profile", "output_dir"}, set()),
    "backend_execute": ({"request", "output_dir", "trust"}, set()),
    "backend_inspect": ({"run_dir"}, set()),
    "backend_reproduce": ({"run_dir", "output_dir", "trust"}, set()),
    "backend_export": ({"run_dir", "output_dir"}, set()),
    "cancel": (set(), {"job_request_id"}), "shutdown": (set(), set()),
}

def validate_payload(command, payload):
    """Shared command-field validation; service-specific values stay in services."""
    if command not in _FIELDS or type(payload) is not dict:
        raise ProductError("protocol_error", "Invalid command payload fields.")
    required, optional = _FIELDS[command]
    if not required <= payload.keys() or not payload.keys() <= required | optional:
        raise ProductError("protocol_error", "Invalid command payload fields.")

DIAGNOSTIC_PREVIEW_BYTES = 4096


def _transport_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Copy diagnostic previews only; archive records and scientific fields stay intact."""
    truncations: list[dict[str, Any]] = []

    def copy(value: Any, path: str = "", key: str = "") -> Any:
        if type(value) is str and (
            key in {"stdout", "stderr", "diagnostic"}
            or key.endswith("_stdout") or key.endswith("_stderr")
        ):
            data = value.encode("utf-8")
            if len(data) > DIAGNOSTIC_PREVIEW_BYTES:
                preview = data[:DIAGNOSTIC_PREVIEW_BYTES].decode("utf-8", errors="ignore")
                truncations.append({
                    "field": path, "original_utf8_bytes": len(data),
                    "retained_utf8_bytes": len(preview.encode("utf-8")),
                    "original_sha256": hashlib.sha256(data).hexdigest(),
                })
                return preview
        if type(value) is dict:
            return {name: copy(item, path + "/" + str(name).replace("~", "~0").replace("/", "~1"), str(name))
                    for name, item in value.items()}
        if type(value) is list:
            return [copy(item, path + "/" + str(index)) for index, item in enumerate(value)]
        return value

    result = copy(payload)
    if truncations:
        if "transport_preview" in result:
            raise ProductError("protocol_error", "Transport preview metadata conflicts with a supplied field.")
        result["transport_preview"] = {
            "diagnostics_truncated": True, "maximum_field_bytes": DIAGNOSTIC_PREVIEW_BYTES,
            "truncated_fields": truncations, "archive_records_modified": False,
        }
    return result


class Worker:
    """Public transport shell; all execution/accounting belongs to services."""

    def __init__(self, output: BinaryIO, services: Any = None):
        if services is None:
            from . import services as service_module
            services = service_module
        self.services = services
        self.output = output
        self._lock = threading.RLock()
        self._sequence = 0
        self._thread: threading.Thread | None = None
        self._job_request_id: str | None = None
        self._cancel: threading.Event | None = None
        self._requests: set[str] = set()
        self._active_output_dir: str | None = None
        self.stopping = False
        self.failed = False

    def emit(self, request_id: str, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            next_sequence = self._sequence + 1
            try:
                data = encode_event(request_id, next_sequence, kind, _transport_payload(payload))
            except ProductError:
                if kind != "error":
                    raise
                # An error can itself contain an oversized partial result. Send
                # a truthful transport failure instead of dying or skipping a
                # sequence. Full persisted data remain in their run archive.
                details: dict[str, Any] = {"full_record_transport": "unavailable"}
                if type(self._active_output_dir) is str and len(self._active_output_dir.encode("utf-8")) <= 4096:
                    details["run_directory"] = self._active_output_dir
                data = encode_event(request_id, next_sequence, "error", ProductError(
                    "protocol_error", "Record cannot be represented by the bounded transport; inspect the saved archive directly.", details,
                ).to_dict())
            # Encoding can fail. Charge an event sequence only once a complete
            # valid frame exists, so the following error never creates a gap.
            self._sequence = next_sequence
            self.output.write(data)
            self.output.flush()

    def handle(self, message: dict[str, Any]) -> None:
        request_id, command, payload = message["request_id"], message["command"], message["payload"]
        with self._lock:
            if request_id in self._requests:
                self.emit(request_id, "error", ProductError("protocol_error", "Request identifier has already been used.").to_dict())
                return
            self._requests.add(request_id)
            try:
                validate_payload(command, payload)
            except ProductError as exc:
                self.emit(request_id, "error", exc.to_dict())
                return
            if self.stopping:
                self.emit(request_id, "error", ProductError("worker_stopping", "Worker is shutting down.").to_dict())
                return
            if command in {"cancel", "shutdown"}:
                target = payload.get("job_request_id")
                if target is not None and (type(target) is not str or target != self._job_request_id):
                    self.emit(request_id, "error", ProductError("invalid_request", "Cancellation target is not the active job.").to_dict())
                    return
                if self._cancel is not None:
                    self._cancel.set()
                if command == "shutdown":
                    self.stopping = True
                self.emit(request_id, "cancelling" if command == "cancel" else "shutdown", {"active_job": self._job_request_id})
                return
            if self._thread is not None and self._thread.is_alive():
                self.emit(request_id, "error", ProductError("worker_busy", "Only one job can execute at a time.").to_dict())
                return
            self._job_request_id = request_id
            self._active_output_dir = payload.get("output_dir")
            self._cancel = threading.Event()
            self.emit(request_id, "accepted", {"command": command})
            self._thread = threading.Thread(target=self._execute, args=(message, self._cancel), name="firmavex-job")
            self._thread.start()

    def _execute(self, message: dict[str, Any], cancel: threading.Event) -> None:
        request_id, command, payload = message["request_id"], message["command"], message["payload"]
        try:
            callback = lambda data: self.emit(request_id, "progress", data)
            if command == "capabilities":
                from .capabilities import describe
                result = describe()
            elif command.startswith("backend_"):
                from . import backend_services as backend
                if command == "backend_check":
                    result = backend.check(payload["profile"])
                elif command == "backend_prepare":
                    result = backend.prepare(payload["profile"], payload["output_dir"], cancel_event=cancel)
                elif command == "backend_execute":
                    result = backend.execute(payload["request"],payload["output_dir"],trust=payload["trust"],cancel_event=cancel,event_callback=callback)
                elif command == "backend_inspect":
                    result = backend.inspect(payload["run_dir"])
                elif command == "backend_reproduce":
                    result = backend.reproduce(payload["run_dir"],payload["output_dir"],trust=payload["trust"],cancel_event=cancel,event_callback=callback)
                elif command == "backend_export":
                    result = backend.export(payload["run_dir"],payload["output_dir"])
                else:
                    raise ProductError("protocol_error", "Unsupported backend command")
            elif command == "doctor":
                result = self.services.doctor()
            elif command == "validate":
                result = self.services.validate_project(payload["config"])
            elif command == "run":
                result = self.services.run_project(payload["config"], payload["output_dir"], cancel_event=cancel, event_callback=callback)
            elif command == "reproduce":
                attempts = payload.get("attempts", 3)
                if type(attempts) is not int or not 1 <= attempts <= 100:
                    raise ProductError("configuration_error", "Reproduction attempts must be an integer from 1 to 100.")
                result = self.services.reproduce_run(payload["run_dir"], payload["output_dir"], attempts, cancel_event=cancel, event_callback=callback)
            elif command == "inspect":
                result = self.services.inspect_run(payload["run_dir"])
            elif command == "export":
                result = self.services.export_run(payload["run_dir"], payload["output_dir"])
            elif command == "recover":
                result = self.services.recover_run(payload["run_dir"])
            elif command == "restart":
                result = self.services.restart_run(payload["run_dir"], payload["output_dir"], cancel_event=cancel, event_callback=callback)
            elif command == "demo":
                result = self.services.run_demo(payload["output_dir"], cancel_event=cancel, event_callback=callback)
            elif command == "prepare_example":
                result = self.services.prepare_example_project(payload["output_dir"], cancel_event=cancel, event_callback=callback)
            elif command == "setup_runtime":
                result = self.services.setup_runtime(cancel_event=cancel, event_callback=callback)
            elif command == "runtime_history":
                result = self.services.runtime_history()
            elif command == "rollback_runtime":
                result = self.services.rollback_runtime(payload["generation"], cancel_event=cancel)
            elif command == "demo_builtin":
                result = self.services.run_demo(payload["output_dir"], cancel_event=cancel, event_callback=callback, _builtin=True)
            elif command == "build_example":
                result = self.services.build_example_project(payload["output_dir"], cancel_event=cancel, event_callback=callback)
            else:
                raise ProductError("protocol_error", "Unsupported job command.")
            self.emit(request_id, "result", result)
            if os.environ.get("FIRMAVEX_WORKER_DIAGNOSTICS") == "1":
                print("FIRMAVEX_WORKER_TERMINAL_EMITTED", file=sys.stderr, flush=True)
        except ProductError as exc:
            if exc.category == "protocol_error" and type(payload.get("output_dir")) is str:
                exc.details["run_directory"] = payload["output_dir"]
                exc.details["full_record_transport"] = "unavailable"
            self.emit(request_id, "error", exc.to_dict())
        except (KeyboardInterrupt, SystemExit) as exc:
            # Services persist authoritative partial accounting before raising.
            # Cancellation is terminal and must never masquerade as completion.
            self.failed = True
            details: dict[str, Any] = {"exception_type": type(exc).__name__}
            output_dir = payload.get("output_dir")
            if output_dir is not None:
                try:
                    if command.startswith("backend_"):
                        from .backend_services import inspect as inspect_backend
                        details["partial_result"] = inspect_backend(output_dir)
                    else:
                        details["partial_result"] = self.services.inspect_run(output_dir)
                except Exception as inspection_error:
                    details["inspection_error"] = str(inspection_error)
            self.emit(request_id, "error", ProductError("cancelled", "Execution was interrupted; inspect the partial run before restart.", details).to_dict())
        except Exception as exc:
            self.failed = True
            self.emit(request_id, "error", ProductError("worker_failure", "Execution service raised an unexpected exception.", {"exception_type": type(exc).__name__, "diagnostic": str(exc)}).to_dict())
        finally:
            with self._lock:
                self._job_request_id = None
                self._cancel = None
                self._active_output_dir = None

    def close(self) -> None:
        with self._lock:
            self.stopping = True
            if self._cancel is not None:
                self._cancel.set()
            thread = self._thread
        if thread is not None:
            thread.join()


def serve(input_stream: BinaryIO, output_stream: BinaryIO, services: Any = None) -> int:
    worker = Worker(output_stream, services)
    try:
        while not worker.stopping:
            line = input_stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            try:
                worker.handle(decode_command(line))
            except ProductError as exc:
                worker.failed = True
                worker.emit("protocol", "error", exc.to_dict())
                # After a framing failure there is no trustworthy message boundary.
                break
    finally:
        if os.environ.get("FIRMAVEX_WORKER_DIAGNOSTICS") == "1":
            print("FIRMAVEX_WORKER_CLOSING", file=sys.stderr, flush=True)
        worker.close()
        if os.environ.get("FIRMAVEX_WORKER_DIAGNOSTICS") == "1":
            print("FIRMAVEX_WORKER_JOINED", file=sys.stderr, flush=True)
    return 1 if worker.failed else 0


def main() -> int:
    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
