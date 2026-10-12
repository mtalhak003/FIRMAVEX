"""Owned worker subprocess, strict event sequencing, and bounded cancellation."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Any

from .errors import ProductError
from .protocol import MAX_LINE_BYTES, decode_event, encode_command
from .windows_job import WindowsJob


class Supervisor:
    """Run one job per owned worker; never restart a job automatically."""

    def __init__(self, worker_argv: Sequence[str] | None = None, *, cancellation_grace: float = 15.0):
        if cancellation_grace <= 0:
            raise ValueError("Cancellation grace must be positive.")
        self.worker_argv = list(worker_argv or [sys.executable, "-m", "firmavex.product.worker"])
        self.cancellation_grace = cancellation_grace

    def execute(self, command: str, payload: dict[str, Any], *,
                cancel_event: threading.Event | None = None,
                event_callback: Callable[[dict[str, Any]], None] | None = None,
                timeout: float | None = None) -> dict[str, Any]:
        if timeout is not None and timeout <= 0:
            raise ValueError("Worker timeout must be positive.")
        request_id = uuid.uuid4().hex
        command_data = encode_command(request_id, command, payload)
        kwargs: dict[str, Any] = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
                                  "stderr": subprocess.PIPE, "bufsize": 0}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            process = subprocess.Popen(self.worker_argv, **kwargs)
        except OSError as exc:
            raise ProductError("worker_failure", "Cannot start the execution worker.", {"diagnostic": str(exc)}) from exc
        # The trusted worker waits for its first command before dispatching any
        # firmware. Establish Windows descendant ownership before that command
        # or before starting any communication threads.
        windows_job: WindowsJob | None = None
        try:
            windows_job = self._create_windows_job(process)
        except BaseException as original:
            try:
                self._terminate(process)
            except BaseException as cleanup:
                WindowsJob._attach_cleanup(original, cleanup)
            finally:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except BaseException as cleanup:
                            WindowsJob._attach_cleanup(original, cleanup)
            raise
        messages: queue.Queue[bytes | Exception | None] = queue.Queue()
        diagnostics = bytearray()
        diagnostic_lock = threading.Lock()

        def read_output() -> None:
            try:
                assert process.stdout is not None
                while True:
                    line = process.stdout.readline(MAX_LINE_BYTES + 1)
                    if not line:
                        break
                    messages.put(line)
                    if len(line) > MAX_LINE_BYTES:
                        break
            except Exception as exc:
                messages.put(exc)
            finally:
                messages.put(None)

        def read_diagnostics() -> None:
            assert process.stderr is not None
            try:
                while True:
                    chunk = process.stderr.read(8192)
                    if not chunk:
                        return
                    with diagnostic_lock:
                        diagnostics.extend(chunk)
                        if len(diagnostics) > 65536:
                            del diagnostics[:-65536]
            except (OSError, ValueError):
                # Teardown may close this owned pipe; job/worker cleanup is
                # independently checked before a successful return.
                return

        readers = [threading.Thread(target=read_output, daemon=True), threading.Thread(target=read_diagnostics, daemon=True)]
        started_readers: list[threading.Thread] = []
        started = time.monotonic()
        sequence = 0
        cancellation_id: str | None = None
        cancellation_started: float | None = None
        timed_out = False
        interrupted = False
        terminal_result: dict[str, Any] | None = None

        def send(name: str, values: dict[str, Any], identifier: str) -> None:
            try:
                assert process.stdin is not None
                process.stdin.write(encode_command(identifier, name, values))
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise ProductError("worker_interrupted", "Worker command channel closed before completion.") from exc

        try:
            for reader in readers:
                reader.start()
                started_readers.append(reader)
            send(command, payload, request_id)
            while True:
                now = time.monotonic()
                timed_out = timed_out or (timeout is not None and now - started >= timeout)
                if (interrupted or timed_out or (cancel_event is not None and cancel_event.is_set())) and cancellation_started is None:
                    cancellation_id = "cancel:" + uuid.uuid4().hex
                    send("cancel", {"job_request_id": request_id}, cancellation_id)
                    cancellation_started = now
                if cancellation_started is not None and now - cancellation_started >= self.cancellation_grace:
                    raise ProductError("worker_timeout" if timed_out else "worker_interrupted",
                                       "Worker did not finish after cancellation; partial accounting may be unknown.")
                try:
                    line = messages.get(timeout=0.05)
                except queue.Empty:
                    if process.poll() is not None:
                        # Descendants can keep inherited pipes open after the
                        # worker dies. Do not wait for pipe EOF to detect death.
                        raise ProductError("worker_interrupted", "Worker exited without a terminal job record.",
                                           {"returncode": process.returncode, "accounting": "inspect_persisted_run"})
                    continue
                except KeyboardInterrupt:
                    interrupted = True
                    continue
                if line is None:
                    with diagnostic_lock:
                        detail = bytes(diagnostics).decode("utf-8", errors="replace")
                    raise ProductError("worker_interrupted", "Worker exited without a terminal job record.",
                                       {"returncode": process.poll(), "stderr": detail, "accounting": "inspect_persisted_run"})
                if isinstance(line, Exception):
                    raise ProductError("worker_interrupted", "Cannot read worker events.", {"diagnostic": str(line)})
                event = decode_event(line)
                if event["sequence"] != sequence + 1:
                    raise ProductError("protocol_error", "Worker event sequence is missing, repeated, or out of order.")
                sequence = event["sequence"]
                if event["request_id"] == cancellation_id:
                    if event["kind"] not in {"cancelling", "error"}:
                        raise ProductError("protocol_error", "Unexpected cancellation response.")
                    continue
                if event["request_id"] != request_id:
                    raise ProductError("protocol_error", "Worker event belongs to an unexpected request.")
                if event_callback is not None:
                    event_callback(event)
                if event["kind"] == "error":
                    error = event["payload"]
                    if type(error.get("category")) is not str or type(error.get("message")) is not str or type(error.get("details")) is not dict:
                        raise ProductError("protocol_error", "Malformed worker error payload.")
                    raise ProductError(error["category"], error["message"], error["details"])
                if event["kind"] == "result":
                    if timed_out:
                        raise ProductError("worker_timeout", "The supervisor time limit expired.", {"partial_result": event["payload"]})
                    if interrupted:
                        raise KeyboardInterrupt
                    terminal_result = event["payload"]
                    return terminal_result
                if event["kind"] not in {"accepted", "progress"}:
                    raise ProductError("protocol_error", "Unexpected job event kind.")
        finally:
            active_error = sys.exc_info()[1]
            cleanup_error: str | None = None
            cleanup_interruption: BaseException | None = None
            # EOF tells the worker to cancel and join its active service.
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except BaseException as exc:
                    cleanup_error = f"Cannot close the worker command channel: {exc}"
                    if not isinstance(exc, Exception):
                        cleanup_interruption = exc
            try:
                process.wait(timeout=self.cancellation_grace)
            except subprocess.TimeoutExpired:
                cleanup_error = "Worker required forced termination after its command channel closed."
                try:
                    self._terminate(process, windows_job)
                except BaseException as exc:
                    cleanup_error += f" {exc}"
                    if not isinstance(exc, Exception):
                        cleanup_interruption = exc
            except BaseException as exc:
                cleanup_error = f"Cannot reap the owned worker: {exc}"
                if not isinstance(exc, Exception):
                    cleanup_interruption = exc
                try:
                    self._terminate(process, windows_job)
                except BaseException as secondary:
                    cleanup_error += f" {secondary}"
            # Job close is required even after a normal worker exit: owned
            # descendants may otherwise outlive their original parent.
            if windows_job is not None:
                try:
                    windows_job.close()
                except BaseException as exc:
                    cleanup_error = f"Cannot close the owned Windows process job: {exc}"
                    if not isinstance(exc, Exception) and cleanup_interruption is None:
                        cleanup_interruption = exc
                    # Preserve the close error while making a bounded second
                    # effort to terminate/reap the tree and release its handle.
                    try:
                        windows_job.terminate()
                        windows_job.close()
                    except BaseException as secondary:
                        cleanup_error += f" {secondary}"
                try:
                    process.wait(timeout=2.0)
                except BaseException as exc:
                    cleanup_error = f"Cannot reap worker after Windows job cleanup: {exc}"
                    if not isinstance(exc, Exception) and cleanup_interruption is None:
                        cleanup_interruption = exc
            # A dead worker may still have live descendants in its owned group.
            # Kill that group even when the worker return code is already known.
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    cleanup_error = f"Cannot clean the owned worker group: {exc}"
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as exc:
                        cleanup_error = f"Cannot close worker output channel: {exc}"
                        if not isinstance(exc, Exception) and cleanup_interruption is None:
                            cleanup_interruption = exc
            for reader in started_readers:
                try:
                    reader.join(timeout=1.0)
                except BaseException as exc:
                    cleanup_error = f"Cannot join worker output reader: {exc}"
                    if not isinstance(exc, Exception) and cleanup_interruption is None:
                        cleanup_interruption = exc
            if cleanup_interruption is not None and active_error is None:
                raise cleanup_interruption
            if cleanup_error is not None:
                if isinstance(active_error, ProductError):
                    active_error.details["supervisor_cleanup_error"] = cleanup_error
                elif active_error is not None and hasattr(active_error, "add_note"):
                    active_error.add_note(cleanup_error)
                elif active_error is None:
                    raise ProductError("cleanup_failure", cleanup_error, {"partial_result": terminal_result})
            elif terminal_result is not None and process.returncode != 0 and active_error is None:
                raise ProductError("worker_failure", "Worker emitted a result but did not exit successfully.",
                                   {"returncode": process.returncode, "partial_result": terminal_result})

    @staticmethod
    def _create_windows_job(process: subprocess.Popen[bytes]) -> WindowsJob | None:
        if os.name != "nt":
            return None
        job = WindowsJob()
        try:
            job.assign(int(process._handle))
        except BaseException as original:
            try:
                job.close()
            except BaseException as cleanup:
                WindowsJob._attach_cleanup(original, cleanup)
            raise
        return job

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes], windows_job: WindowsJob | None = None) -> None:
        if windows_job is not None:
            windows_job.terminate()
            process.wait(timeout=2.0)
            return
        if process.poll() is not None and os.name != "posix":
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except OSError:
                pass
            process.wait(timeout=2.0)
