import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from firmavex.product.config import ProductConfig
from firmavex.product.runtime import (FirmwareExecutor, _allocate_port, _cleanup,
                                      _debugger_script, _Drain, _parse_completion, _spawn)
from firmavex.product.tools import Toolchain


@pytest.fixture
def config(tmp_path):
    firmware = tmp_path / "firmware.elf"
    firmware.write_bytes(b"unit-test-only")
    return ProductConfig(firmware=firmware, input_symbols=("inputs[0]", "inputs[1]"),
                         ready_breakpoint="ready", completion_breakpoint="complete",
                         failure_symbol="failure", input_max=3)


def marker_record(config, values=(2, 1)):
    return {"success": True, "ready_reached": True,
            "inputs_read_back": dict(zip(config.input_symbols, values)),
            "completion_reached": True, "observed_value": 1, "triggered": True}


def test_exact_completed_observation_parser(config):
    data = marker_record(config)
    assert _parse_completion("M=" + json.dumps(data), "M=", config, (2, 1)) == data


@pytest.mark.parametrize("change", [
    {"completion_reached": False}, {"ready_reached": False}, {"success": 1},
    {"triggered": False}, {"observed_value": True}, {"observed_value": -1},
    {"inputs_read_back": {"inputs[0]": 1, "inputs[1]": 1}},
    {"inputs_read_back": {"inputs[0]": True, "inputs[1]": 1}},
    {"extra": "untrusted"},
])
def test_malformed_completion_fails_closed(config, change):
    data = marker_record(config)
    data.update(change)
    with pytest.raises(ValueError):
        _parse_completion("M=" + json.dumps(data), "M=", config, (2, 1))


@pytest.mark.parametrize("output", ["", "M={}\nM={}", "M=not-json", "M=[]"])
def test_missing_duplicate_and_malformed_markers(config, output):
    with pytest.raises(ValueError):
        _parse_completion(output, "M=", config, (2, 1))


def test_script_enforces_input_ready_and_completion_lifecycle(config):
    script = _debugger_script(config, (2, 1), 54321, "MARKER=")
    assert script.index("continue_to(ready)") < script.index("set variable")
    assert script.index("Input readback mismatch") < script.index("ready.delete()")
    assert script.index("ready.delete()") < script.index('if settings["signature"]')
    assert "BreakpointEvent" in script and "tuple(_product_stop_events[0].breakpoints) != (target,)" in script
    assert "unsigned32" in script and "pending" in script
    assert "sha256" in script and "Signature continuation" in script


def test_socket_port_is_not_fixed():
    assert 0 < _allocate_port() < 65536


def test_output_drained_and_bounded():
    import firmavex.product.runtime as runtime
    data = b"x" * (runtime.LOG_LIMIT + 100)
    drain = _Drain(io.BytesIO(data))
    drain.thread.join(timeout=2)
    assert drain.total == len(data)
    assert len(drain.data) == runtime.LOG_LIMIT
    assert drain.error is None


def test_cleanup_real_host_child_is_reaped():
    process, stdout, stderr = _spawn([sys.executable, "-c", "import time; print('started',flush=True); time.sleep(60)"])
    result = _cleanup([("host_unit_test", process, stdout, stderr)])
    assert result["success"]
    assert process.poll() is not None
    assert result["processes"][0]["reaped"]
    assert not stdout.thread.is_alive() and not stderr.thread.is_alive()


@pytest.mark.parametrize("which_reader", [1, 2])
@pytest.mark.parametrize("control_flow", [False, True])
def test_spawn_reader_start_failure_reaps_child(monkeypatch, which_reader, control_flow):
    import firmavex.product.runtime as runtime
    actual_popen, actual_start = runtime.subprocess.Popen, threading.Thread.start
    owned = []
    calls = 0
    failure = KeyboardInterrupt("reader start interrupted") if control_flow else RuntimeError("reader start failed")
    def popen(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        owned.append(child)
        return child
    def start(thread):
        nonlocal calls
        calls += 1
        if calls == which_reader:
            raise failure
        return actual_start(thread)
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)
    monkeypatch.setattr(threading.Thread, "start", start)
    with pytest.raises(type(failure)) as caught:
        _spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    assert caught.value is failure
    assert len(owned) == 1 and owned[0].poll() is not None
    assert owned[0].stdout.closed and owned[0].stderr.closed


def test_spawn_second_reader_construction_failure_reaps_child(monkeypatch):
    import firmavex.product.runtime as runtime
    actual_popen, actual_drain = runtime.subprocess.Popen, runtime._Drain
    owned, readers = [], []
    def popen(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        owned.append(child)
        return child
    def drain(stream, **kwargs):
        if readers:
            raise RuntimeError("reader allocation failed")
        reader = actual_drain(stream, **kwargs)
        readers.append(reader)
        return reader
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)
    monkeypatch.setattr(runtime, "_Drain", drain)
    with pytest.raises(RuntimeError, match="reader allocation failed"):
        _spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    assert owned[0].poll() is not None
    assert owned[0].stdout.closed and owned[0].stderr.closed
    assert readers[0].thread.ident is None


def test_cleanup_escalates_after_termination_timeout(monkeypatch):
    monkeypatch.setattr("firmavex.product.windows_process.snapshot", lambda handle: {"terminated": True})
    calls = []
    class Process:
        pid = 123
        _handle = 123
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): calls.append("terminate")
        def kill(self): calls.append("kill"); self.returncode = -9
        def wait(self, timeout):
            calls.append("wait")
            if self.returncode is None:
                raise subprocess.TimeoutExpired("owned", timeout)
            return self.returncode
    result = _cleanup([("owned", Process(), _Drain(io.BytesIO()), _Drain(io.BytesIO()))])
    assert result["success"]
    assert calls == ["terminate", "wait", "kill", "wait"]


def test_cleanup_preserves_original_keyboard_interrupt_and_attempts_reap(monkeypatch):
    monkeypatch.setattr("firmavex.product.windows_process.snapshot", lambda handle: {"terminated": True})
    original = KeyboardInterrupt("original")
    calls = []
    class Process:
        pid = 123
        _handle = 123
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): calls.append("terminate"); raise SystemExit("secondary cleanup cancellation")
        def kill(self): calls.append("kill"); self.returncode = -9
        def wait(self, timeout):
            calls.append("wait")
            if self.returncode is None:
                raise subprocess.TimeoutExpired("owned", timeout)
            return self.returncode
    result = _cleanup([("owned", Process(), _Drain(io.BytesIO()), _Drain(io.BytesIO()))], original)
    assert not result["success"]
    assert result["processes"][0]["reaped"]
    assert "SystemExit" in " ".join(original.__notes__)
    assert "kill" in calls


def test_cleanup_new_control_flow_exception_propagates_after_reaping(monkeypatch):
    monkeypatch.setattr("firmavex.product.windows_process.snapshot", lambda handle: {"terminated": True})
    calls = []
    class Process:
        pid = 123
        _handle = 123
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): raise KeyboardInterrupt("cleanup cancellation")
        def kill(self): calls.append("kill"); self.returncode = -9
        def wait(self, timeout):
            if self.returncode is None:
                raise subprocess.TimeoutExpired("owned", timeout)
            return self.returncode
    with pytest.raises(KeyboardInterrupt, match="cleanup cancellation"):
        _cleanup([("owned", Process(), _Drain(io.BytesIO()), _Drain(io.BytesIO()))])
    assert calls == ["kill"]


def test_pre_dispatch_cancellation_propagates_and_has_cleanup(config):
    event = threading.Event()
    event.set()
    executor = FirmwareExecutor(config, Toolchain("unused", "unused"), event)
    with pytest.raises(KeyboardInterrupt):
        executor.execute((0, 0))
    assert executor.last_evidence["classification"] == "interrupted"
    assert executor.last_evidence["cleanup_verified"]
    assert not executor.last_evidence["guest_dispatched"]
    assert executor.last_evidence["measurement_mode"] != "real_firmware"


@pytest.mark.parametrize("values", [(4, 0), (True, 0), (0,), [0, 0]])
def test_invalid_input_never_starts_tools(config, values):
    executor = FirmwareExecutor(config, Toolchain("unused", "unused"))
    with pytest.raises(ValueError):
        executor.execute(values)
    assert executor.last_evidence is None


def test_missing_firmware_is_infrastructure_failure(config):
    config.firmware.unlink()
    receipt = FirmwareExecutor(config, Toolchain("unused", "unused")).execute((0, 0))
    assert not receipt.observation.success
    assert receipt.observation.execution_signature is None
    assert receipt.evidence["cleanup_verified"]
    assert receipt.evidence["classification"] == "infrastructure_failure"
    assert not receipt.evidence["completion_reached"]


@pytest.fixture
def fake_debugger(monkeypatch):
    """Exercise the actual emitted GDB Python, including the shared collector."""
    import types
    callbacks, targets, output = [], [], []
    state = {"inputs[0]": 99, "inputs[1]": 99, "failure": 0, "$pc": 0,
             "steps": 0, "unexpected": False}
    class GdbError(RuntimeError): pass
    class StopEvent: pass
    class BreakpointEvent(StopEvent):
        def __init__(self, target): self.breakpoints = (target,)
    class Kind:
        code = 1
        sizeof = 4
        def strip_typedefs(self): return self
        def unqualified(self): return self
        def __str__(self): return "unsigned int"
    class Value:
        type = Kind()
        def __init__(self, value): self.value = value
        def __int__(self): return self.value
    class Breakpoint:
        pending = False
        def __init__(self, name, internal=False):
            self.name = name
            self.locations = (SimpleNamespace(address=0x100 if name == "ready" else 0x200),)
            targets.append(self)
        def delete(self): targets.remove(self)
    namespace = {}
    def emit(event):
        for callback in tuple(callbacks): callback(event)
    def complete():
        state["failure"] = int((state["inputs[0]"], state["inputs[1]"]) == (2, 1))
        state["$pc"] = 0x200
        emit(BreakpointEvent(next(target for target in targets if target.name == "complete")))
    def execute(command, to_string=False):
        if command.startswith("python exec("):
            exec(eval(command[len("python exec("):-1]), namespace)
        elif command == "continue":
            if any(target.name == "ready" for target in targets):
                state["inputs[0]"] = state["inputs[1]"] = 0
                state["$pc"] = 0x100
                emit(BreakpointEvent(next(target for target in targets if target.name == "ready")))
            elif state["unexpected"]:
                emit(StopEvent())
            else:
                complete()
        elif command == "stepi":
            state["steps"] += 1
            if state["steps"] == 3:
                complete()
            else:
                state["$pc"] += 2
                emit(StopEvent())
        elif command.startswith("set variable "):
            name, value = command[len("set variable "):].split(" = ")
            state[name] = int(value)
        return ""
    module = types.ModuleType("gdb")
    module.GdbError, module.StopEvent, module.BreakpointEvent = GdbError, StopEvent, BreakpointEvent
    module.TYPE_CODE_INT = 1
    module.events = SimpleNamespace(stop=SimpleNamespace(connect=callbacks.append, disconnect=callbacks.remove))
    module.Breakpoint, module.breakpoints = Breakpoint, lambda: tuple(targets)
    module.parse_and_eval = lambda name: Value(state[name])
    module.execute, module.write = execute, output.append
    state["flushes"] = 0
    def flush():
        state["flushes"] += 1
    module.flush = flush
    monkeypatch.setitem(sys.modules, "gdb", module)
    def run(script):
        body = script[len("python\n"):].removesuffix("\nend\n")
        exec(body, namespace)
        return "".join(output)
    return state, run, callbacks


@pytest.mark.parametrize("signature", [False, True])
@pytest.mark.parametrize("values,triggered", [((0, 0), False), ((2, 1), True)])
def test_debugger_executes_startup_then_injects_and_observes(config, fake_debugger, signature, values, triggered):
    from dataclasses import replace
    from src.firmavex.monitor.signature import _parse_signature
    state, run, callbacks = fake_debugger
    config = replace(config, collect_signature=signature)
    output = run(_debugger_script(config, values, 54321, "M="))
    data = _parse_completion(output, "M=", config, values)
    assert data["triggered"] is triggered
    assert state["flushes"] == 2
    assert (state["inputs[0]"], state["inputs[1]"]) == values
    assert callbacks == []
    if signature:
        import hashlib
        from src.firmavex.monitor.signature import DOMAIN_PREFIX
        expected = hashlib.sha256(DOMAIN_PREFIX + b"".join(pc.to_bytes(4, "big")
                                  for pc in (0x100, 0x102, 0x104)) + b"\x00").hexdigest()
        assert _parse_signature(output).digest == expected


def test_debugger_unexpected_stop_cannot_be_success(config, fake_debugger):
    from dataclasses import replace
    state, run, callbacks = fake_debugger
    state["unexpected"] = True
    with pytest.raises(RuntimeError, match="required breakpoint"):
        run(_debugger_script(replace(config, collect_signature=False), (2, 1), 1234, "M="))
    assert callbacks == []


def test_cancellation_not_replaced_by_cleanup_exception(config, monkeypatch):
    import firmavex.product.runtime as runtime
    event = threading.Event()
    event.set()
    def failed_cleanup(*args): raise RuntimeError("cleanup broke")
    monkeypatch.setattr(runtime, "_cleanup", failed_cleanup)
    executor = FirmwareExecutor(config, Toolchain("unused", "unused"), event)
    with pytest.raises(KeyboardInterrupt) as caught:
        executor.execute((0, 0))
    assert "cleanup broke" in " ".join(caught.value.__notes__)
    assert not executor.last_evidence["cleanup_verified"]


@pytest.fixture(scope="module")
def actual_product_example(tmp_path_factory):
    from firmavex.product.example import build_example
    from firmavex.product.config import load_config
    from firmavex.product.tools import discover
    built = build_example(tmp_path_factory.mktemp("product_runtime") / "example")
    config = load_config(built["config_file"])
    return config, discover(config)


@pytest.mark.parametrize("signature", [False, True])
@pytest.mark.parametrize("values,triggered", [((0, 0), False), ((2, 1), True)])
def test_actual_arm_firmware_input_after_startup(actual_product_example, signature, values, triggered):
    from dataclasses import replace
    config, tools = actual_product_example
    receipt = FirmwareExecutor(replace(config, collect_signature=signature), tools).execute(values)
    assert receipt.observation.success, receipt.observation.stderr
    assert receipt.observation.triggered is triggered
    assert receipt.evidence["measurement_mode"] == "real_firmware"
    assert all(receipt.evidence[key] for key in ("guest_dispatched", "input_injected", "completion_reached", "cleanup_verified"))
    assert all(process["reaped"] for process in receipt.evidence["cleanup"]["processes"])
    assert (receipt.observation.execution_signature is not None) is signature
    assert receipt.evidence["observation"]["inputs_read_back"] == dict(zip(config.input_symbols, values))


def test_actual_missing_completion_is_failure_despite_trigger(actual_product_example):
    from dataclasses import replace
    config, tools = actual_product_example
    # The bound includes debugger startup. 400 ms could expire before input
    # injection on native Windows, never exercising the missing-completion case.
    # Keep every evidence/timeout assertion, but allow real initialization.
    receipt = FirmwareExecutor(replace(config, completion_breakpoint="Default_Handler", timeout_seconds=5.0), tools).execute((2, 1))
    assert not receipt.observation.success
    assert not receipt.observation.triggered
    assert receipt.observation.execution_signature is None
    assert receipt.evidence["guest_dispatched"] and receipt.evidence["input_injected"]
    assert not receipt.evidence["completion_reached"]
    assert receipt.evidence["error_category"] == "timeout"
    assert receipt.evidence["cleanup_verified"]


def test_actual_cancellation_charged_and_aborted(actual_product_example):
    from dataclasses import replace
    from src.firmavex.evaluation.evaluator import EvaluationSession
    from src.firmavex.evaluation.api import TrialInput
    config, tools = actual_product_example
    config = replace(config, completion_breakpoint="Default_Handler", timeout_seconds=5.0)
    event = threading.Event()
    executor = FirmwareExecutor(config, tools, event)
    session = EvaluationSession("product-example", config.input_space, 3, "reproduction",
                                lambda values: executor.execute(values).observation)
    timer = threading.Timer(0.3, event.set)
    timer.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            session.execute(TrialInput((2, 1)))
    finally:
        timer.cancel()
        timer.join(timeout=1)
    result = session.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.aborted
    assert session.execute(TrialInput((2, 1))).status == "session_aborted"
    assert executor.last_evidence["cleanup_verified"]
