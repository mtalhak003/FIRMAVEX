"""Owned process trees, resource admission and bounded draining; never a shell."""

from dataclasses import asdict
from contextlib import contextmanager
from contextvars import ContextVar
import ctypes
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import time

MAX_ADMISSION_BYTES = 65536
_observer = ContextVar("firmavex_backend_process_observer", default=None)


@contextmanager
def observe_processes(callback):
    """Optional local progress sink, scoped to this caller/thread only."""
    if not callable(callback):
        raise TypeError("Process observer must be callable")
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


def emit_process_event(event):
    """Emit administrative progress without changing execution/strategy feedback."""
    callback = _observer.get()
    if callback is not None:
        callback(dict(event))


class _Drain:
    """Drain promptly, retaining only a bounded diagnostic suffix."""

    def __init__(self, stream, limit):
        self.stream, self.limit = stream, min(limit, 524288)
        self.data = bytearray()
        self.total = 0
        self.error = None
        self.thread = threading.Thread(target=self._read, daemon=True)

    def _read(self):
        try:
            while chunk := self.stream.read1(8192):
                self.total += len(chunk)
                self.data.extend(chunk)
                if len(self.data) > self.limit:
                    del self.data[: -self.limit]
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def text(self):
        return bytes(self.data).decode("utf-8", errors="replace")


class Cancelled(Exception):
    pass


def launcher_command():
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "firmavex.backends.launcher"]
    executable = Path(sys.executable).resolve()
    if executable.name.lower() in {"firmavex", "firmavex.exe"}:
        console = executable
    else:
        console = executable.with_name("FIRMAVEX.exe" if os.name == "nt" else "FIRMAVEX")
    if not console.is_file():
        raise RuntimeError("Required frozen launcher FIRMAVEX console is missing")
    return [str(console), "--backend-child"]


def _windows_job(child, limits):
    from firmavex.product.windows_job import (
        ExtendedLimitInformation, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, WindowsJob,
    )
    job = WindowsJob()
    try:
        record = ExtendedLimitInformation()
        record.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | 0x100 | 0x2
        record.BasicLimitInformation.PerProcessUserTimeLimit = (math.ceil(limits.timeout_seconds) + 1) * 10000000
        record.ProcessMemoryLimit = limits.memory_bytes
        if not job._api.SetInformationJobObject(job._handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                               ctypes.byref(record), ctypes.sizeof(record)):
            raise job._failure("SetInformationJobObject backend limits")
        job.assign(int(child._handle))
        return job
    except BaseException as exc:
        try:
            job.close()
        except BaseException as cleanup:
            exc.add_note(f"Job cleanup failed: {cleanup}")
        raise


def inspect_artifacts(cwd, maximum):
    """Bounded inventory; links, special files and hardlinks fail closed."""
    total, count = 0, 0
    pending = [Path(cwd)]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > 10000:
                    raise RuntimeError("Artifact count limit exceeded")
                metadata = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    raise RuntimeError("Symlink artifact rejected")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                    total += metadata.st_size
                else:
                    raise RuntimeError("Nonregular or hardlinked artifact rejected")
                if total > maximum:
                    raise RuntimeError("Aggregate artifact limit exceeded")
    return total


class Processes:
    def __init__(self, cancel, limits):
        self.cancel, self.limits = cancel, limits
        self.children = []
        self.cleanup = []
        self.directories = set()
        self.deadline = time.monotonic() + limits.timeout_seconds
        self._closed = False
        self._cleanup_failure = None

    def check(self):
        if self._closed:
            raise RuntimeError("Process owner is already closed")
        if self.cancel.is_set():
            raise Cancelled("Execution cancelled")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Backend deadline exceeded")
        for child, out, err, job in self.children:
            if out is not None and err is not None:
                if out.error or err.error:
                    raise RuntimeError("Output reader failed")
                if out.total + err.total > self.limits.log_bytes:
                    raise RuntimeError("Output limit exceeded")
        for directory in self.directories:
            inspect_artifacts(directory, self.limits.artifact_bytes)

    def spawn(self, args, cwd):
        from .launcher import validate
        self.check()
        cwd = Path(cwd)
        if not cwd.is_absolute() or not cwd.is_dir() or cwd.is_symlink():
            raise ValueError("Execution working directory must be an absolute owned directory")
        record = {"schema_version": 1, "argv": args, "limits": asdict(self.limits)}
        validate(record)
        payload = (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")
        if len(payload) > MAX_ADMISSION_BYTES:
            raise ValueError("Child admission is oversized")
        command = launcher_command()
        options = dict(cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.name == "posix":
            options["start_new_session"] = True
        elif os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            raise RuntimeError("Unsupported backend process platform")
        child = subprocess.Popen(command, **options)
        self.children.append((child, None, None, None))
        self.directories.add(cwd)
        if os.name == "nt":
            job = _windows_job(child, self.limits)
            self.children[-1] = (child, None, None, job)
        else:
            job = None
        out = _Drain(child.stdout, self.limits.log_bytes)
        self.children[-1] = (child, out, None, job)
        err = _Drain(child.stderr, self.limits.log_bytes)
        self.children[-1] = (child, out, err, job)
        out.thread.start()
        err.thread.start()
        child.stdin.write(payload)
        child.stdin.close()
        emit_process_event({"type": "backend_stage", "stage": "process_started", "pid": child.pid, "executable": args[0], "argv": list(args)})
        return child, out, err

    def run(self, args, cwd, *, progress_marker=None, output_stage=None):
        child, out, err = self.spawn(args, cwd)
        delivered = set()
        observed_out_bytes = 0
        while child.poll() is None or out.thread.is_alive() or err.thread.is_alive():
            self.check()
            text = out.text()
            if output_stage and text and out.total != observed_out_bytes:
                observed_out_bytes = out.total
                emit_process_event({"type": "backend_stage", "stage": output_stage, "pid": child.pid, "stdout_preview": text[-4096:]})
            if progress_marker:
                for line in text.splitlines():
                    if line.startswith(progress_marker):
                        try:
                            state = json.loads(line[len(progress_marker):])
                        except ValueError:
                            continue  # A line may still be in flight in the reader.
                        stage = {"ready": "input_ready", "injected": "input_injected"}.get(state.get("stage")) if type(state) is dict else None
                        if stage and stage not in delivered:
                            delivered.add(stage)
                            emit_process_event({"type": "backend_stage", "stage": stage, "pid": child.pid})
            time.sleep(0.01)
        self.check()
        return child.returncode, out.text(), err.text()

    def close(self):
        if self._closed:
            if self._cleanup_failure is not None:
                raise self._cleanup_failure
            return
        errors, cancellation = [], None
        for child, out, err, job in reversed(self.children):
            def attempt(action):
                nonlocal cancellation
                try:
                    action()
                except ProcessLookupError:
                    pass
                except BaseException as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    if not isinstance(exc, Exception) and cancellation is None:
                        cancellation = exc

            if os.name == "posix":
                attempt(lambda: os.killpg(child.pid, signal.SIGTERM))
            elif job is not None:
                attempt(job.terminate)
            elif child.poll() is None:
                attempt(child.terminate)
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            except BaseException as exc:
                errors.append(str(exc))
                if not isinstance(exc, Exception) and cancellation is None:
                    cancellation = exc
            if os.name == "posix":
                attempt(lambda: os.killpg(child.pid, signal.SIGKILL))
            elif job is not None:
                attempt(job.close)
            elif child.poll() is None:
                attempt(child.kill)
            attempt(lambda: child.wait(timeout=2))
            if child.stdin is not None and not child.stdin.closed:
                attempt(child.stdin.close)
            for drain, stream in ((out, child.stdout), (err, child.stderr)):
                if drain:
                    if drain.thread.ident is not None:
                        attempt(lambda: drain.thread.join(2))
                    if drain.thread.is_alive() or drain.error:
                        errors.append("Output reader cleanup failed")
                    else:
                        attempt(drain.stream.close)
                elif stream is not None:
                    attempt(stream.close)
            self.cleanup.append({"pid": child.pid, "returncode": child.poll(), "reaped": child.poll() is not None})
        # Keep child records available for evidence and caller inspection.
        self._closed = True
        if cancellation is not None:
            for error in errors:
                cancellation.add_note(error)
            self._cleanup_failure = cancellation
            raise cancellation
        if errors:
            self._cleanup_failure = RuntimeError("; ".join(errors))
            raise self._cleanup_failure
