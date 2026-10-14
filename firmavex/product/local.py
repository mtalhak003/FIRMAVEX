"""Bounded local job facade over the existing supervised worker.

No sockets, authentication server, alternate evaluator, retries or result schema.
The caller is the same trusted OS user as the owned worker. Session job IDs are
not remote bearer credentials; persisted backend receipts remain authoritative.
"""

from copy import deepcopy
import math
import threading
import time
from uuid import uuid4

from .capabilities import LOCAL_COMMANDS, describe
from .errors import ProductError
from .protocol import encode_command, decode_command
from .supervisor import Supervisor


def _error(category, message):
    raise ProductError(category, message)


class LocalSession:
    def __init__(self, *, supervisor=None):
        # Injection is an administrator/test configuration, never wire input.
        self.supervisor = supervisor or Supervisor()
        self._lock = threading.RLock()
        self._jobs = {}
        self._closed = False

    def capabilities(self):
        return describe()

    def submit(self, command, payload, *, timeout_seconds=3600):
        if type(command) is not str or command not in LOCAL_COMMANDS:
            _error(
                "unsupported_command",
                "This local interface does not expose that command.",
            )
        # Round-trip gives a strict ordinary-JSON snapshot, not caller-owned data.
        copied = decode_command(encode_command("validation", command, payload))[
            "payload"
        ]
        from .worker import validate_payload

        validate_payload(command, copied)
        if command in {"backend_execute", "backend_reproduce"} and (
            type(copied.get("trust")) is not str
            or copied["trust"] not in {"trusted_example", "trusted_project"}
        ):
            _error(
                "untrusted_workload",
                "Unknown workloads are rejected; explicit project/runtime trust is required.",
            )
        if command == "backend_execute":
            from firmavex.backends.api import request_from_dict

            try:
                request_from_dict(copied["request"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ProductError("invalid_request", str(exc)) from exc
        if "profile" in copied:
            from firmavex.backends.api import profiles

            if type(copied["profile"]) is not str or copied["profile"] not in profiles:
                _error("invalid_request", "Choose a documented target profile.")
        for key in ("run_dir", "output_dir"):
            if key in copied and (
                type(copied[key]) is not str
                or not copied[key]
                or len(copied[key]) > 4096
                or any(ord(c) < 32 for c in copied[key])
            ):
                _error(
                    "invalid_request",
                    "Choose a valid local path with no control characters.",
                )
        if (
            type(timeout_seconds) not in {int, float}
            or not math.isfinite(timeout_seconds)
            or not 0.1 <= timeout_seconds <= 86400
        ):
            _error("invalid_request", "Worker deadline must be 0.1–86400 seconds.")
        with self._lock:
            if self._closed:
                _error("session_closed", "The local session is closed.")
            if any(
                job["state"] in {"running", "cancellation_requested"}
                for job in self._jobs.values()
            ):
                _error("worker_busy", "One active job is permitted per session.")
            if len(self._jobs) >= 32:
                _error(
                    "capacity_exceeded",
                    "Forget a terminal session job before submitting another. Saved files are not deleted.",
                )
            identifier = uuid4().hex
            job = {
                "job_id": identifier,
                "command": command,
                "state": "running",
                "result": None,
                "error": None,
                "events": [],
                "cancel": threading.Event(),
                "thread": None,
                "started_monotonic": time.monotonic(),
                "elapsed_seconds": None,
            }
            self._jobs[identifier] = job
            thread = threading.Thread(
                target=self._execute,
                args=(identifier, copied, timeout_seconds),
                daemon=True,
            )
            job["thread"] = thread
            try:
                thread.start()
            except BaseException:
                del self._jobs[identifier]
                raise
            return identifier

    def _execute(self, identifier, payload, timeout):
        with self._lock:
            job = self._jobs[identifier]

        def progress(event):
            # Progress metadata is bounded. Full evidence/diagnostics stay in
            # terminal worker responses and archives, not a second event journal.
            data = event.get("payload", {})
            summary = {
                "sequence": event["sequence"],
                "kind": event["kind"],
                "stage": str(data.get("stage", data.get("type", "")))[:128],
            }
            with self._lock:
                job["events"].append(summary)
                del job["events"][:-64]

        try:
            result = self.supervisor.execute(
                job["command"],
                payload,
                cancel_event=job["cancel"],
                event_callback=progress,
                timeout=timeout,
            )
            with self._lock:
                job["result"], job["state"] = result, "finished"
        except BaseException as exc:
            error = (
                exc.to_dict()
                if isinstance(exc, ProductError)
                else ProductError(
                    (
                        "worker_interrupted"
                        if not isinstance(exc, Exception)
                        else "worker_failure"
                    ),
                    "The local job failed; inspect saved receipts before any explicit restart.",
                    {
                        "exception_type": type(exc).__name__,
                        "diagnostic": str(exc)[:4096],
                        "accounting": "unknown_unless_established_by_saved_receipts",
                    },
                ).to_dict()
            )
            with self._lock:
                job["error"], job["state"] = error, "failed"
        finally:
            with self._lock:
                job["elapsed_seconds"] = time.monotonic() - job["started_monotonic"]

    def _get(self, identifier):
        if type(identifier) is not str or identifier not in self._jobs:
            _error(
                "unknown_job",
                "Job does not belong to this session; open persisted results separately.",
            )
        return self._jobs[identifier]

    def status(self, identifier):
        with self._lock:
            job = self._get(identifier)
            return deepcopy(
                {
                    key: job[key]
                    for key in (
                        "job_id",
                        "command",
                        "state",
                        "events",
                        "elapsed_seconds",
                    )
                }
            )

    def cancel(self, identifier):
        with self._lock:
            job = self._get(identifier)
            if job["state"] in {"running", "cancellation_requested"}:
                job["cancel"].set()
                job["state"] = "cancellation_requested"
            return self.status(identifier)

    def result(self, identifier):
        with self._lock:
            job = self._get(identifier)
            if job["state"] in {"running", "cancellation_requested"}:
                _error(
                    "job_not_finished",
                    "Cancellation is a request; wait for terminal worker cleanup.",
                )
            return deepcopy(
                {
                    "job_id": identifier,
                    "state": job["state"],
                    "result": job["result"],
                    "error": job["error"],
                }
            )

    def forget(self, identifier):
        with self._lock:
            job = self._get(identifier)
            if job["state"] in {"running", "cancellation_requested"}:
                _error("worker_busy", "Cannot forget an active job.")
            del self._jobs[identifier]
            return {"forgotten": identifier, "saved_files_deleted": False}

    def close(self):
        with self._lock:
            self._closed = True
            threads = []
            for job in self._jobs.values():
                job["cancel"].set()
                threads.append(job["thread"])
        for thread in threads:
            thread.join(timeout=2 * self.supervisor.cancellation_grace + 10)
            if thread.is_alive():
                _error(
                    "cleanup_failure",
                    "Job supervision has not terminated; saved execution accounting may be unknown.",
                )

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        try:
            self.close()
        except BaseException as cleanup:
            if error is None:
                raise
            error.add_note("Local session cleanup failed: " + str(cleanup))
