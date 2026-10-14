"""Fresh, supervised Cortex-M3 execution for the user-firmware product path.

This adapter does not change the research monitor or evaluator accounting.
Raw logs and operational evidence belong to the administrator, not strategies.
"""

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import uuid

from src.firmavex.evaluation.evaluator import Observation
from src.firmavex.monitor.signature import _collector_command, _parse_signature
from firmavex.product.tools import Toolchain, discover, file_identity
from firmavex.product.firmware import inspect_elf


LOG_LIMIT = 512 * 1024


@contextmanager
def _debugger_directory():
    directory = tempfile.TemporaryDirectory(prefix="firmavex-product-gdb-")
    primary = None
    try:
        yield directory.name
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            directory.cleanup()
        except BaseException as secondary:
            if primary is None or (isinstance(primary, Exception)
                                   and not isinstance(secondary, Exception)):
                raise
            try:
                primary.add_note(f"Debugger temporary-file cleanup failed: {secondary}")
            except BaseException:
                pass


@dataclass(frozen=True)
class ExecutionReceipt:
    observation: Observation
    evidence: dict


class _Drain:
    """Drain continuously, retaining bounded trailing output with loss counts."""

    def __init__(self, stream, *, start=True):
        self.stream = stream
        self.data = bytearray()
        self.total = 0
        self.error = None
        self.thread = threading.Thread(target=self._read, daemon=True)
        if start:
            self.thread.start()

    def _read(self):
        try:
            while chunk := getattr(self.stream, "read1", self.stream.read)(8192):
                self.total += len(chunk)
                self.data.extend(chunk)
                if len(self.data) > LOG_LIMIT:
                    del self.data[:-LOG_LIMIT]
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def text(self):
        return bytes(self.data).decode("utf-8", errors="replace")


def _allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _spawn(command: list[str], *, env=None):
    options = {"env": {**(os.environ if env is None else env), "PYTHONDONTWRITEBYTECODE": "1"}, "stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
               "stderr": subprocess.PIPE}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    # Inherit the supervised worker's process group so forced worker cleanup
    # can also reap QEMU/GDB. Direct API calls own the explicit child handles.
    process = subprocess.Popen(command, **options)
    drains = []
    try:
        # Register both drain objects before starting either reader. Setup
        # failure must not strand a child that the caller cannot yet own.
        drains.append(_Drain(process.stdout, start=False))
        drains.append(_Drain(process.stderr, start=False))
        for drain in drains:
            drain.thread.start()
        return process, drains[0], drains[1]
    except BaseException as primary:
        errors = []
        def attempt(operation, action):
            try:
                return action()
            except BaseException as secondary:
                errors.append(f"Spawn cleanup {operation}: {type(secondary).__name__}: {secondary}")
                return None
        if attempt("poll", process.poll) is None:
            attempt("terminate", process.terminate)
        try:
            process.wait(timeout=2)
        except BaseException as secondary:
            if not isinstance(secondary, subprocess.TimeoutExpired):
                errors.append(f"Spawn cleanup wait: {type(secondary).__name__}: {secondary}")
            attempt("kill", process.kill)
            attempt("reap", lambda: process.wait(timeout=2))
        for drain in drains:
            if drain.thread.ident is not None:
                attempt("reader join", lambda: drain.thread.join(timeout=2))
                if drain.thread.is_alive():
                    errors.append("Spawn cleanup reader did not stop.")
        for stream in (process.stdout, process.stderr):
            attempt("stream close", stream.close)
        if attempt("final poll", process.poll) is None:
            errors.append("Spawn cleanup child was not reaped.")
        for error in errors:
            try:
                primary.add_note(error)
            except BaseException:
                pass
        raise


def _cleanup(processes, primary: BaseException | None = None) -> dict:
    """Reap both subprocesses; cleanup must not replace cancellation."""
    errors = []
    cancellation = None
    statuses = []
    # Stop GDB first, then QEMU. Every owned child gets every applicable stage.
    for name, process, stdout, stderr in reversed(processes):
        def attempt(operation, action):
            nonlocal cancellation
            try:
                return action()
            except BaseException as exc:
                errors.append(f"{name} {operation}: {type(exc).__name__}: {exc}")
                if not isinstance(exc, Exception) and cancellation is None:
                    cancellation = exc
                return None
        running = attempt("poll", process.poll) is None
        if running:
            attempt("terminate", process.terminate)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            attempt("kill", process.kill)
            attempt("reap", lambda: process.wait(timeout=2))
        except BaseException as exc:
            errors.append(f"{name} wait: {type(exc).__name__}: {exc}")
            if not isinstance(exc, Exception) and cancellation is None:
                cancellation = exc
            attempt("kill", process.kill)
            attempt("reap", lambda: process.wait(timeout=2))
        for label, drain in (("stdout", stdout), ("stderr", stderr)):
            attempt(f"{label} drain", lambda: drain.thread.join(timeout=2))
            if drain.thread.is_alive():
                errors.append(f"{name} {label} reader did not stop.")
            if drain.error:
                errors.append(f"{name} {label} reader: {drain.error}")
            attempt(f"{label} close", drain.stream.close)
        code = attempt("final poll", process.poll)
        if code is None:
            errors.append(f"{name} was not reaped.")
        statuses.append({"name": name, "pid": process.pid, "return_code": code,
                         "reaped": code is not None})
    if primary is not None:
        for error in errors:
            try:
                primary.add_note(error)
            except Exception:
                pass
    if cancellation is not None and (primary is None or isinstance(primary, Exception)):
        raise cancellation
    return {"success": not errors, "processes": statuses, "errors": errors,
            "ownership": "direct child handles; inherited supervisor group"}


def _debugger_script(config, values, port, marker) -> str:
    """Use stop events, not human-readable breakpoint output, as authority."""
    settings = {"inputs": dict(zip(config.input_symbols, values)),
                "ready": config.ready_breakpoint,
                "complete": config.completion_breakpoint,
                "failure_symbol": config.failure_symbol,
                "failure_value": config.failure_value,
                "port": port, "marker": marker,
                "signature": config.collect_signature}
    body = f'''
import gdb
import json
settings = {settings!r}
_product_stop_events = []
def stop(event):
    _product_stop_events.append(event)
def unsigned32(name):
    value = gdb.parse_and_eval(name)
    kind = value.type.strip_typedefs().unqualified()
    if kind.code != gdb.TYPE_CODE_INT or kind.sizeof != 4 or str(kind) not in ("unsigned int", "unsigned long", "unsigned long int"):
        raise gdb.GdbError("Expected a typed uint32 symbol: " + name)
    return value
def breakpoint(name):
    target = gdb.Breakpoint(name, internal=False)
    if target.pending:
        raise gdb.GdbError("Unresolved required breakpoint: " + name)
    return target
def continue_to(target):
    _product_stop_events.clear()
    gdb.execute("continue", to_string=True)
    if len(_product_stop_events) != 1 or not isinstance(_product_stop_events[0], gdb.BreakpointEvent) or tuple(_product_stop_events[0].breakpoints) != (target,):
        raise gdb.GdbError("Execution did not stop at the required breakpoint.")
gdb.events.stop.connect(stop)
try:
    gdb.execute("set pagination off")
    gdb.execute("set confirm off")
    gdb.execute("set breakpoint pending off")
    gdb.execute("target remote 127.0.0.1:" + str(settings["port"]))
    ready = breakpoint(settings["ready"])
    completion = breakpoint(settings["complete"])
    if len(gdb.breakpoints() or ()) != 2:
        raise gdb.GdbError("Unexpected breakpoint state.")
    continue_to(ready)
    gdb.write(settings["marker"][:-1] + "_PROGRESS=" + json.dumps({{"stage": "ready"}}) + "\\n")
    gdb.flush()
    # Fail early if both names resolve to the same executable location.
    ready_addresses = {{location.address for location in ready.locations}}
    complete_addresses = {{location.address for location in completion.locations}}
    if ready_addresses & complete_addresses:
        raise gdb.GdbError("Ready and completion breakpoints share an address.")
    injected = {{}}
    for name, value in settings["inputs"].items():
        unsigned32(name)
        gdb.execute("set variable " + name + " = " + str(value))
        if int(unsigned32(name)) != value:
            raise gdb.GdbError("Input readback mismatch: " + name)
        injected[name] = value
    ready.delete()
    gdb.write(settings["marker"][:-1] + "_PROGRESS=" + json.dumps({{"stage": "injected"}}) + "\\n")
    gdb.flush()
    if settings["signature"]:
        gdb.execute({_collector_command()!r})
    else:
        continue_to(completion)
    observed = int(unsigned32(settings["failure_symbol"]))
    gdb.write(settings["marker"] + json.dumps({{"success": True, "ready_reached": True, "inputs_read_back": injected, "completion_reached": True, "observed_value": observed, "triggered": observed == settings["failure_value"]}}, sort_keys=True) + "\\n")
finally:
    gdb.events.stop.disconnect(stop)
'''
    return "python\n" + body + "\nend\n"


def _parse_completion(stdout, marker, config, values) -> dict:
    lines = [line[len(marker):] for line in stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise ValueError("Expected exactly one completed-observation marker.")
    data = json.loads(lines[0])
    if type(data) is not dict or set(data) != {"success", "ready_reached", "inputs_read_back",
                                             "completion_reached", "observed_value", "triggered"}:
        raise ValueError("Malformed completed-observation record.")
    if any(data[key] is not True for key in ("success", "ready_reached", "completion_reached")):
        raise ValueError("Required execution stages were not observed.")
    if data["inputs_read_back"] != dict(zip(config.input_symbols, values)) or any(
        type(value) is not int for value in data["inputs_read_back"].values()
    ):
        raise ValueError("Injected input readback does not match the admitted input.")
    if type(data["observed_value"]) is not int or not 0 <= data["observed_value"] <= 0xffffffff:
        raise ValueError("Failure observation is not uint32.")
    if type(data["triggered"]) is not bool or data["triggered"] != (data["observed_value"] == config.failure_value):
        raise ValueError("Contradictory failure observation.")
    return data


class FirmwareExecutor:
    def __init__(self, config, tools: Toolchain | None = None,
                 cancel_event: threading.Event | None = None, event_callback=None):
        self.config = config
        self.tools = tools or discover(config)
        self.cancel_event = cancel_event or threading.Event()
        self.event_callback = event_callback
        self.last_evidence = None

    def _cancel(self):
        if self.cancel_event.is_set():
            raise KeyboardInterrupt("Product firmware execution cancelled.")

    def execute(self, values: tuple[int, ...]) -> ExecutionReceipt:
        if not self.config.input_space.accepts(values):
            raise ValueError("Executor inputs are outside the configured domain.")
        started = time.monotonic()
        evidence = {"schema_version": 1, "backend": "qemu-mps2-an385-gdb",
                    "attempt_id": uuid.uuid4().hex, "inputs": list(values),
                    "started_at_utc": datetime.now(timezone.utc).isoformat(),
                    "tools": self.tools.to_dict(), "guest_dispatch_observed": False,
                    "completion_observed": False, "failure_condition_observed": False,
                    "guest_dispatched": False, "completion_reached": False,
                    "input_injected": False, "cleanup_verified": False,
                    "measurement_mode": "unverified_runtime_observation",
                    "diagnostics": {}, "atomic_snapshot": False}
        self.last_evidence = evidence
        processes = []
        primary = None
        observed = Observation(False, stderr="Execution did not complete.")
        marker = None
        try:
            self._cancel()
            image = inspect_elf(self.config)
            identity = file_identity(self.config.firmware)
            if image["firmware_sha256"] != identity["sha256"]:
                raise RuntimeError("Firmware changed during static validation.")
            evidence["firmware"] = identity
            evidence["firmware_validation"] = image
            for name, path in (("qemu", self.tools.qemu), ("gdb", self.tools.gdb)):
                actual = file_identity(path)
                claimed = self.tools.identities.get(name)
                if claimed is not None and any(actual[key] != claimed.get(key)
                                               for key in actual):
                    raise RuntimeError(f"{name} executable changed after discovery.")
            port = _allocate_port()
            evidence["gdb_port"] = port
            command = [self.tools.qemu, "-M", "mps2-an385", "-kernel", str(self.config.firmware),
                       "-display", "none", "-serial", "null", "-monitor", "none",
                       "-S", "-gdb", f"tcp:127.0.0.1:{port}"]
            qemu, qout, qerr = _spawn(command)
            processes.append(("qemu", qemu, qout, qerr))
            evidence["qemu_pid"] = qemu.pid
            deadline = time.monotonic() + self.config.startup_timeout_seconds
            while True:
                self._cancel()
                if qemu.poll() is not None:
                    raise RuntimeError("QEMU exited before its debugger endpoint became ready.")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("QEMU debugger endpoint startup timed out.")
                    time.sleep(0.02)
            marker = "FIRMAVEX_PRODUCT_OBSERVATION_" + uuid.uuid4().hex + "="
            with _debugger_directory() as directory:
                script = Path(directory) / "observe.gdb"
                script.write_text(_debugger_script(self.config, values, port, marker), encoding="utf-8")
                command = [self.tools.gdb, "--nx", "--nh", "--batch", "-iex", "set auto-load off", "-iex", "set python dont-write-bytecode on",
                           str(self.config.firmware), "-x", str(script)]
                gdb, gout, gerr = _spawn(command)
                processes.append(("gdb", gdb, gout, gerr))
                evidence["gdb_pid"] = gdb.pid
                deadline = time.monotonic() + self.config.timeout_seconds
                emitted_stages = set()
                while gdb.poll() is None:
                    if self.event_callback is not None:
                        prefix = marker[:-1] + "_PROGRESS="
                        for line in gout.text().splitlines():
                            if not line.startswith(prefix):
                                continue
                            try:
                                progress = json.loads(line[len(prefix):])
                            except ValueError:
                                continue
                            if progress in ({"stage": "ready"}, {"stage": "injected"}) and progress["stage"] not in emitted_stages:
                                emitted_stages.add(progress["stage"])
                                self.event_callback({"type": "runtime_stage", "stage": progress["stage"], "attempt_id": evidence["attempt_id"]})
                    self._cancel()
                    if qemu.poll() is not None:
                        raise RuntimeError("QEMU exited during debugger observation.")
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"GDB observation timed out after {self.config.timeout_seconds} seconds.")
                    time.sleep(0.02)
                gout.thread.join(timeout=2)
                gerr.thread.join(timeout=2)
                if gdb.returncode != 0:
                    raise RuntimeError(f"GDB observation failed with exit code {gdb.returncode}.")
                if qemu.poll() is not None:
                    raise RuntimeError("QEMU exited before observation verification.")
                data = _parse_completion(gout.text(), marker, self.config, values)
                signature = _parse_signature(gout.text()) if self.config.collect_signature else None
                if file_identity(self.config.firmware) != identity:
                    raise RuntimeError("Firmware changed during execution.")
                for name, path in (("qemu", self.tools.qemu), ("gdb", self.tools.gdb)):
                    claimed = self.tools.identities.get(name)
                    if claimed is not None and any(file_identity(path)[key] != claimed.get(key)
                                                   for key in ("path", "sha256", "size_bytes")):
                        raise RuntimeError(f"{name} executable changed during execution.")
                evidence.update(guest_dispatch_observed=True, completion_observed=True,
                                guest_dispatched=True, completion_reached=True,
                                input_injected=True, observed_value=data["observed_value"],
                                failure_condition_observed=data["triggered"],
                                observation=data, classification="configured_failure_observed"
                                if data["triggered"] else "completed_without_configured_failure")
                if signature is not None:
                    evidence["execution_signature"] = {"digest": signature.digest,
                                                         "truncated": signature.truncated}
                observed = Observation(True, data["triggered"], gout.text(), gerr.text(), signature)
                if all(name in self.tools.identities for name in ("qemu", "gdb")):
                    evidence["measurement_mode"] = "real_firmware"
        except Exception as exc:
            evidence["classification"] = "infrastructure_failure"
            evidence["error"] = f"{type(exc).__name__}: {exc}"
            evidence["error_category"] = ("timeout" if isinstance(exc, TimeoutError)
                                           else "runtime_observation_failed")
            observed = Observation(False, stderr=evidence["error"])
        except BaseException as exc:
            primary = exc
            evidence["classification"] = "interrupted"
            evidence["error"] = f"{type(exc).__name__}: {exc}"
            evidence["error_category"] = "cancelled"
            raise
        finally:
            try:
                try:
                    cleanup = _cleanup(processes, primary)
                except BaseException as secondary:
                    evidence["cleanup"] = {"success": False, "errors": [str(secondary)]}
                    if primary is None or (isinstance(primary, Exception)
                                           and not isinstance(secondary, Exception)):
                        raise
                    try:
                        primary.add_note(f"Runtime cleanup failed: {secondary}")
                    except BaseException:
                        pass
                    cleanup = evidence["cleanup"]
                evidence["cleanup"] = cleanup
                evidence["cleanup_verified"] = cleanup["success"]
                if not cleanup["success"]:
                    evidence["classification"] = "infrastructure_failure"
                    evidence["error_category"] = "cleanup_failed"
                    observed = Observation(False, stdout=observed.stdout,
                                           stderr=observed.stderr + "\nCleanup failed: " + "; ".join(cleanup["errors"]))
            finally:
                for name, process, stdout, stderr in processes:
                    evidence["diagnostics"][name] = {
                        "stdout": stdout.text(), "stderr": stderr.text(),
                        "stdout_discarded_bytes": max(0, stdout.total - LOG_LIMIT),
                        "stderr_discarded_bytes": max(0, stderr.total - LOG_LIMIT),
                        "return_code": process.returncode}
                    if name == "gdb" and marker is not None:
                        prefix = marker[:-1] + "_PROGRESS="
                        for line in stdout.text().splitlines():
                            if line.startswith(prefix):
                                try:
                                    progress = json.loads(line[len(prefix):])
                                    if progress == {"stage": "ready"}:
                                        evidence["guest_dispatched"] = True
                                        evidence["guest_dispatch_observed"] = True
                                    elif progress == {"stage": "injected"}:
                                        evidence["input_injected"] = True
                                except (ValueError, TypeError):
                                    pass
                evidence["duration_seconds"] = time.monotonic() - started
                evidence["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
                evidence["stdout"] = "\n".join(item["stdout"] for item in evidence["diagnostics"].values())
                evidence["stderr"] = "\n".join(item["stderr"] for item in evidence["diagnostics"].values())
        if not observed.success:
            stdout = "\n".join(item["stdout"] for item in evidence["diagnostics"].values())
            stderr = "\n".join(item["stderr"] for item in evidence["diagnostics"].values())
            observed = Observation(False, stdout=stdout, stderr=observed.stderr + "\n" + stderr)
        return ExecutionReceipt(observed, evidence)
