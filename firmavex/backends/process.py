"""Owned process trees and bounded draining, without shell interpretation."""

import os
import signal
import subprocess
import threading
import sys
import math
import time


class _Drain:
    """Read available pipe bytes promptly; retain a bounded diagnostic suffix."""

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


class Processes:
    def __init__(self, cancel, limits):
        self.cancel, self.limits = cancel, limits
        self.children = []
        self.cleanup = []
        self.deadline = time.monotonic() + limits.timeout_seconds

    def check(self):
        if self.cancel.is_set():
            raise Cancelled("Execution cancelled")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Backend deadline exceeded")
        for child, out, err, job in self.children:
            if (
                out is not None
                and err is not None
                and out.total + err.total > self.limits.log_bytes
            ):
                raise RuntimeError("Output limit exceeded")

    def spawn(self, args, cwd):
        self.check()
        if getattr(sys, "frozen", False):
            raise RuntimeError(
                "New backend execution requires installed Python; frozen launcher integration is not qualified"
            )
        options = dict(
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        job = None
        if os.name == "posix":
            options["start_new_session"] = True
        else:
            # Windows execution is not qualified for new backends yet.
            raise RuntimeError(
                "New backends require native Windows qualification before execution"
            )
        # Set limits in a fresh interpreter, avoiding preexec_fn in Qt/threaded hosts.
        launcher = "import os,resource,sys; memory=int(sys.argv[1]); size=int(sys.argv[2]); cpu=int(sys.argv[3]); resource.setrlimit(resource.RLIMIT_AS,(memory,memory)); resource.setrlimit(resource.RLIMIT_FSIZE,(size,size)); resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu)); os.execv(sys.argv[4],sys.argv[4:])"
        command = [
            sys.executable,
            "-c",
            launcher,
            str(self.limits.memory_bytes),
            str(self.limits.artifact_bytes),
            str(math.ceil(self.limits.timeout_seconds) + 1),
            *args,
        ]
        child = subprocess.Popen(command, **options)
        self.children.append((child, None, None, job))
        out = _Drain(child.stdout, self.limits.log_bytes)
        self.children[-1] = (child, out, None, job)
        err = _Drain(child.stderr, self.limits.log_bytes)
        self.children[-1] = (child, out, err, job)
        out.thread.start()
        err.thread.start()
        return child, out, err

    def run(self, args, cwd):
        child, out, err = self.spawn(args, cwd)
        deadline = time.monotonic() + self.limits.timeout_seconds
        while child.poll() is None or out.thread.is_alive() or err.thread.is_alive():
            self.check()
            if out.total + err.total > self.limits.log_bytes:
                raise RuntimeError("Output limit exceeded")
            if time.monotonic() >= deadline:
                raise TimeoutError("Process deadline exceeded")
            total = 0
            for path in cwd.iterdir():
                if path.is_symlink():
                    raise RuntimeError("Symlink artifact rejected")
                if path.is_file():
                    total += path.stat().st_size
            if total > self.limits.artifact_bytes:
                raise RuntimeError("Aggregate artifact limit exceeded")
            time.sleep(0.01)
        out.thread.join(2)
        err.thread.join(2)
        if out.total + err.total > self.limits.log_bytes:
            raise RuntimeError("Output limit exceeded")
        return child.returncode, out.text(), err.text()

    def close(self):
        errors = []
        cancellation = None
        for child, out, err, job in reversed(self.children):

            def attempt(action):
                nonlocal cancellation
                try:
                    action()
                except ProcessLookupError:
                    pass
                except BaseException as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    if not isinstance(exc, Exception):
                        cancellation = exc

            attempt(lambda: os.killpg(child.pid, signal.SIGTERM))
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            except BaseException as exc:
                errors.append(str(exc))
                if not isinstance(exc, Exception):
                    cancellation = exc
            attempt(lambda: os.killpg(child.pid, signal.SIGKILL))
            attempt(lambda: child.wait(timeout=2))
            for drain, stream in ((out, child.stdout), (err, child.stderr)):
                if drain:
                    if drain.thread.ident is not None:
                        attempt(lambda: drain.thread.join(2))
                    if drain.thread.is_alive() or drain.error:
                        errors.append("Output reader cleanup failed")
                    else:
                        attempt(drain.stream.close)
                else:
                    attempt(stream.close)
            self.cleanup.append(
                {
                    "pid": child.pid,
                    "returncode": child.poll(),
                    "reaped": child.poll() is not None,
                }
            )
        if cancellation is not None:
            for error in errors:
                cancellation.add_note(error)
            raise cancellation
        if errors:
            raise RuntimeError("; ".join(errors))
