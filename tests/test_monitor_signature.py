"""Runtime collection tests, independent of corpus predicates and oracle data."""

import ast
import hashlib
import io
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.firmavex.compiler.cortex_m import SUPPORT_DIR
from src.firmavex.evaluation.api import ExecutionSignature, TrialInput
from src.firmavex.evaluation import registry as registry_module
from src.firmavex.monitor import monitor, signature
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.runner import run_strategy


class StopEvent:
    pass


class BreakpointEvent(StopEvent):
    def __init__(self, *breakpoints):
        self.breakpoints = breakpoints


class SignalEvent(StopEvent):
    pass


def collect_fake(monkeypatch, pcs, *, cap=4096, final_event="completion", continuation="completion", pending=False):
    """Execute the actual generated GDB Python with controlled stop events."""
    target = SimpleNamespace(pending=pending)
    callbacks = []
    writes = []
    state = {
        "position": 0, "continue_calls": 0, "read_positions": [],
        "sampled_pcs": [], "commands": [], "completed": False,
    }

    def read_pc(expression):
        assert expression == "$pc"
        # The completion stop has a PC too, but it must never be sampled.
        assert state["position"] < len(pcs), "Collector sampled the completion-breakpoint PC"
        state["read_positions"].append(state["position"])
        pc = pcs[state["position"]]
        state["sampled_pcs"].append(pc)
        return pc

    def execute(command, **kwargs):
        state["commands"].append(command)
        if command == "stepi":
            state["position"] += 1
            finished = state["position"] == len(pcs)
            outcome = final_event if finished else "step"
        else:
            assert command == "continue"
            state["continue_calls"] += 1
            state["position"] = len(pcs)
            outcome = continuation
        if outcome == "error":
            raise RuntimeError("private GDB command failure")
        event = {
            "completion": BreakpointEvent(target),
            "other": BreakpointEvent(object()),
            "signal": SignalEvent(),
            "step": StopEvent(),
            "exit": None,
        }[outcome]
        if event is not None:
            state["completed"] = outcome == "completion"
            for callback in callbacks:
                callback(event)

    gdb = SimpleNamespace(
        breakpoints=lambda: (target,),
        events=SimpleNamespace(stop=SimpleNamespace(connect=callbacks.append, disconnect=callbacks.remove)),
        parse_and_eval=read_pc,
        execute=execute, write=writes.append,
        GdbError=RuntimeError, StopEvent=StopEvent, BreakpointEvent=BreakpointEvent,
    )
    monkeypatch.setitem(sys.modules, "gdb", gdb)
    monkeypatch.setattr(signature, "MAX_PC_SAMPLES", cap)
    script = ast.literal_eval(signature._collector_command()[len("python exec("):-1])
    try:
        exec(script, {})
    except BaseException:
        assert not writes, "Collection failure published a partial signature"
        raise
    finally:
        assert not callbacks
    state["output"] = "".join(writes)
    return signature._parse_signature(state["output"]), state


def test_collector_canonical_ordered_digest_and_deterministic_replay(monkeypatch):
    pcs = [0x8, 0x12, 0x8, 0x16]
    collected, state = collect_fake(monkeypatch, pcs)
    material = signature.DOMAIN_PREFIX + b"".join(pc.to_bytes(4, "big") for pc in pcs) + b"\x00"
    assert collected == ExecutionSignature(hashlib.sha256(material).hexdigest())
    assert collect_fake(monkeypatch, pcs)[0] == collected
    assert collect_fake(monkeypatch, [0x8, 0x8, 0x12, 0x16])[0] != collected
    assert state["continue_calls"] == 0


def test_collector_cap_marks_prefix_and_requires_successful_completion(monkeypatch):
    result, state = collect_fake(monkeypatch, [8, 10, 12], cap=2)
    material = signature.DOMAIN_PREFIX + b"\x00\x00\x00\x08\x00\x00\x00\x0a\x01"
    assert result == ExecutionSignature(hashlib.sha256(material).hexdigest(), True)
    assert state["continue_calls"] == 1
    assert collect_fake(monkeypatch, [8, 10, 12], cap=2)[0] == result
    # Exact completion on the last permitted step is not truncation.
    assert collect_fake(monkeypatch, [8, 10], cap=2)[0].truncated is False


@pytest.mark.parametrize("execution_length", [4095, 4096, 4097])
def test_literal_4096_boundary_counts_reads_steps_and_excludes_completion_pc(monkeypatch, execution_length):
    assert signature.MAX_PC_SAMPLES == 4096
    # Repetition is intentional: each visit remains in the ordered hash input.
    pcs = ([8, 18, 8, 22] * ((execution_length + 3) // 4))[:execution_length]
    result, state = collect_fake(monkeypatch, pcs)
    sample_count = min(execution_length, 4096)
    truncated = execution_length > 4096
    assert result.truncated is truncated
    assert state["read_positions"] == list(range(sample_count))
    assert state["sampled_pcs"] == pcs[:sample_count]
    assert state["commands"] == ["stepi"] * sample_count + (["continue"] if truncated else [])
    assert state["continue_calls"] == int(truncated) and state["completed"]
    assert state["position"] == execution_length
    material = signature.DOMAIN_PREFIX + b"".join(pc.to_bytes(4, "big") for pc in pcs[:sample_count]) + bytes([int(truncated)])
    assert result.digest == hashlib.sha256(material).hexdigest()


@pytest.mark.parametrize("pc", [0, 0xffffffff])
def test_collector_accepts_uint32_endpoints_without_changing_encoding(monkeypatch, pc):
    result, state = collect_fake(monkeypatch, [pc])
    assert state["sampled_pcs"] == [pc]
    material = signature.DOMAIN_PREFIX + pc.to_bytes(4, "big") + b"\x00"
    assert result == ExecutionSignature(hashlib.sha256(material).hexdigest())


@pytest.mark.parametrize("outcome", ["other", "signal", "exit", "error"])
def test_collector_rejects_unexpected_stop_without_partial_signal(monkeypatch, outcome):
    with pytest.raises(RuntimeError):
        collect_fake(monkeypatch, [8], final_event=outcome)


@pytest.mark.parametrize("outcome", ["other", "signal", "exit", "error", "step"])
def test_collector_rejects_failed_or_incomplete_continuation(monkeypatch, outcome):
    with pytest.raises(RuntimeError):
        collect_fake(monkeypatch, [8, 10], cap=1, continuation=outcome)


def test_collector_rejects_unresolved_breakpoint(monkeypatch):
    with pytest.raises(RuntimeError, match="resolved completion breakpoint"):
        collect_fake(monkeypatch, [8], pending=True)


@pytest.mark.parametrize("pc", [-1, 0x100000000])
def test_collector_rejects_non_cortex_m_program_counter(monkeypatch, pc):
    with pytest.raises(RuntimeError, match="non-uint32"):
        collect_fake(monkeypatch, [pc])


@pytest.mark.parametrize("output", [
    "", "FIRMAVEX_SIGNATURE_V1=private/path.c:0",
    "FIRMAVEX_SIGNATURE_V1=" + "A" * 64 + ":0",
    "FIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":2",
    "FIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":0 extra",
    ("FIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":0\n") * 2,
])
def test_parser_rejects_missing_malformed_and_duplicate_markers(output):
    with pytest.raises(ValueError):
        signature._parse_signature(output)


@pytest.fixture
def fake_monitor(monkeypatch, tmp_path):
    image = tmp_path / "test.elf"
    image.touch()
    qemu = Mock()
    qemu.poll.return_value = None
    qemu.stderr = io.StringIO()
    launch = Mock(return_value=qemu)
    gdb = Mock(return_value=subprocess.CompletedProcess(
        [], 0, "FIRMAVEX_VALUE=0x0\nFIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":0\n", "",
    ))
    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    monkeypatch.setattr(monitor.subprocess, "run", gdb)
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    return image, qemu, launch, gdb


def registered_fake_session(monkeypatch, image):
    """Use real registry/evaluator plumbing with a test-only dummy image."""
    registry = registry_module.BenchmarkRegistry()
    identifier = registry.select("development")[0].benchmark_id

    def build(*args, **kwargs):
        image.write_bytes(b"test-only dummy image")
        return {"success": True, "output_file": str(image)}

    monkeypatch.setattr(registry_module, "build_cortex_m_firmware", build)
    assert registry.build(identifier, image)["success"]
    return registry.open_session(identifier, 2, "signature-lifecycle-audit")


@pytest.mark.parametrize("execution_length", [4095, 4096, 4097])
@pytest.mark.parametrize("failure_value", [0, 1])
def test_cap_transition_preserves_failure_truth_through_monitor_registry_and_evaluator(monkeypatch, fake_monitor, execution_length, failure_value):
    image, qemu, _, gdb = fake_monitor
    collected, state = collect_fake(monkeypatch, [8] * execution_length)
    gdb.return_value = subprocess.CompletedProcess(
        [], 0, state["output"] + f"FIRMAVEX_VALUE=0x{failure_value:x}\n", "",
    )
    owner = registered_fake_session(monkeypatch, image)
    feedback = owner.execute(TrialInput((0, 0, 0, 0)))
    assert feedback.execution_signature == collected
    assert collected.truncated is (execution_length > 4096)
    assert feedback.status == ("triggered" if failure_value else "safe")
    result = owner.result()
    assert result.attempted_executions == result.successful_executions == 1
    assert result.failure_found is bool(failure_value)
    assert result.failure_triggering_executions == failure_value
    assert result.infrastructure_failures == 0 and not result.aborted
    command = gdb.call_args.args[0]
    collector_index = next(index for index, item in enumerate(command) if item.startswith("python exec("))
    flag_read_index = next(index for index, item in enumerate(command) if item.startswith("printf"))
    assert collector_index < flag_read_index and state["completed"]
    assert qemu.stderr.closed


@pytest.mark.parametrize("collect_signature", [False, True])
def test_single_subprocess_timeout_covers_whole_gdb_command_sequence(fake_monitor, collect_signature):
    image, _, _, gdb = fake_monitor
    result = monitor.observe_symbol(str(image), "failure", "complete", timeout=0.125, collect_signature=collect_signature)
    assert result["success"]
    gdb.assert_called_once()
    assert gdb.call_args.kwargs["timeout"] == 0.125
    command = gdb.call_args.args[0]
    assert command[-1].startswith("printf")
    assert any(item.startswith("python exec(") for item in command) is collect_signature


@pytest.mark.parametrize("as_bytes", [False, True])
def test_collection_timeout_through_registry_charges_aborts_and_keeps_partial_markers_private(monkeypatch, fake_monitor, as_bytes):
    image, qemu, launch, gdb = fake_monitor
    owner = registered_fake_session(monkeypatch, image)
    # Even apparently valid markers inside timed-out output must be discarded.
    output = "private-PC=0x1234 source.c image.elf held_out\nFIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":1\nFIRMAVEX_VALUE=0x1\n"
    stderr = "private GDB stepping failure"
    gdb.side_effect = subprocess.TimeoutExpired(
        "gdb", 5, output=output.encode() if as_bytes else output,
        stderr=stderr.encode() if as_bytes else stderr,
    )
    feedback = owner.execute(TrialInput((0, 0, 0, 0)))
    assert feedback.status == "infrastructure_failure" and feedback.execution_signature is None
    result = owner.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == result.failure_triggering_executions == 0
    assert result.aborted and not result.failure_found and result.budget_remaining == 1
    diagnostics, = owner.diagnostics()
    assert diagnostics["stdout"] == output
    assert stderr in diagnostics["stderr"] and "timed out" in diagnostics["stderr"]
    public = json.dumps([asdict(owner.describe()), asdict(feedback), asdict(result)])
    for private in ("private-PC", "source.c", "image.elf", "held_out", "GDB", "stdout", "stderr", "FIRMAVEX_SIGNATURE"):
        assert private not in public
    assert owner.execute(TrialInput((0, 0, 0, 0))).status == "session_aborted"
    assert owner.result() == result
    launch.assert_called_once()
    gdb.assert_called_once()
    qemu.terminate.assert_called_once()
    assert qemu.stderr.closed


def test_monitor_collects_after_inputs_before_symbol_read_and_preserves_legacy_default(fake_monitor):
    image, qemu, _, gdb = fake_monitor
    result = monitor.observe_symbol(str(image), "failure", "complete", input_values={"actions[0]": 1}, collect_signature=True)
    assert result["success"] and result["value"] == 0
    assert result["execution_signature"] == ExecutionSignature("a" * 64)
    command = gdb.call_args.args[0]
    collector = next(item for item in command if item.startswith("python exec("))
    assert command.index("set variable actions[0] = 1") < command.index("break complete") < command.index(collector)
    assert command.index(collector) < next(index for index, item in enumerate(command) if item.startswith("printf"))
    assert qemu.stderr.closed
    qemu.stderr = io.StringIO()
    legacy = monitor.observe_symbol(str(image), "failure", "complete")
    assert set(legacy) == {"success", "symbol", "value", "stdout", "stderr"}
    assert "continue" in gdb.call_args.args[0]


@pytest.mark.parametrize("bad_output", [
    "FIRMAVEX_VALUE=0x1\n",
    "FIRMAVEX_VALUE=0x1\nFIRMAVEX_SIGNATURE_V1=bad:0\n",
])
def test_monitor_missing_or_malformed_collection_is_failure_and_cleans_up(fake_monitor, bad_output):
    image, qemu, _, gdb = fake_monitor
    gdb.return_value = subprocess.CompletedProcess([], 0, bad_output, "private collection error")
    result = monitor.observe_symbol(str(image), "failure", "complete", collect_signature=True)
    assert result["success"] is False and result["value"] is None
    assert "execution_signature" not in result
    assert "Runtime signature collection failed" in result["stderr"]
    assert "private collection error" in result["stderr"]
    qemu.terminate.assert_called_once()
    qemu.wait.assert_called_once()
    assert qemu.stderr.closed


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("gdb", 5), FileNotFoundError("GDB Python unavailable"), KeyboardInterrupt()])
def test_monitor_collection_errors_and_interruption_cleanup(fake_monitor, error):
    image, qemu, _, gdb = fake_monitor
    gdb.side_effect = error
    if isinstance(error, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            monitor.observe_symbol(str(image), "failure", "complete", collect_signature=True)
    else:
        result = monitor.observe_symbol(str(image), "failure", "complete", collect_signature=True)
        assert result["success"] is False and "execution_signature" not in result
    qemu.terminate.assert_called_once()
    assert qemu.stderr.closed


@pytest.mark.parametrize("output, stderr", [("private PC log", "private GDB error"), (b"private PC log", b"private GDB error")])
def test_monitor_timeout_retains_partial_private_diagnostics_without_signature(fake_monitor, output, stderr):
    image, qemu, _, gdb = fake_monitor
    gdb.side_effect = subprocess.TimeoutExpired("gdb", 5, output=output, stderr=stderr)
    result = monitor.observe_symbol(str(image), "failure", "complete", collect_signature=True)
    assert result["success"] is False and "execution_signature" not in result
    assert result["stdout"] == "private PC log"
    assert "private GDB error" in result["stderr"] and "timed out" in result["stderr"]
    assert qemu.stderr.closed


@pytest.mark.parametrize("return_code, stdout", [
    (1, "FIRMAVEX_VALUE=0x1\nFIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":0\n"),
    (0, "FIRMAVEX_SIGNATURE_V1=" + "a" * 64 + ":0\n"),
])
def test_monitor_does_not_publish_signature_after_failed_failure_flag_observation(fake_monitor, return_code, stdout):
    image, qemu, _, gdb = fake_monitor
    gdb.return_value = subprocess.CompletedProcess([], return_code, stdout, "private debugger error")
    result = monitor.observe_symbol(str(image), "failure", "complete", collect_signature=True)
    assert result["success"] is False and result["value"] is None
    assert "execution_signature" not in result
    assert qemu.stderr.closed


def test_monitor_qemu_exit_invalidates_even_complete_signature(fake_monitor):
    image, qemu, _, _ = fake_monitor
    qemu.poll.side_effect = [None, 1, 1]
    result = monitor.observe_symbol(str(image), "failure", "complete", collect_signature=True)
    assert result["success"] is False and result["value"] is None
    assert "execution_signature" not in result
    assert qemu.stderr.closed


@pytest.mark.parametrize("option", [1, None, "true"])
def test_monitor_rejects_non_boolean_collection_option(fake_monitor, option):
    image, _, launch, _ = fake_monitor
    assert not monitor.observe_symbol(str(image), "failure", "complete", collect_signature=option)["success"]
    launch.assert_not_called()


@pytest.mark.parametrize("collected", [None, "private source.c", {"digest": "a" * 64}, object()])
def test_registry_required_signature_failure_aborts_once_and_keeps_raw_diagnostics_private(monkeypatch, tmp_path, collected):
    registry = registry_module.BenchmarkRegistry()
    identifier = registry.select("development")[0].benchmark_id
    image = tmp_path / "dummy.elf"

    def build(*args, **kwargs):
        image.write_bytes(b"test-only dummy image")
        return {"success": True, "output_file": str(image)}

    monkeypatch.setattr(registry_module, "build_cortex_m_firmware", build)
    assert registry.build(identifier, image)["success"]
    raw = "private source.c image.elf GDB held_out raw-PC=0x1234"
    observed = Mock(return_value={"success": True, "value": 1, "stdout": raw, "stderr": raw, "execution_signature": collected})
    monkeypatch.setattr(registry_module, "observe_symbol", observed)
    owner = registry.open_session(identifier, 3, "signature-test")
    feedback = owner.execute(TrialInput((0, 0, 0, 0)))
    assert observed.call_args.kwargs["collect_signature"] is True
    assert feedback.status == "infrastructure_failure" and feedback.execution_signature is None
    result = owner.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0 and result.aborted and not result.failure_found
    assert raw in owner.diagnostics()[0]["stdout"] and raw in owner.diagnostics()[0]["stderr"]
    assert owner.execute(TrialInput((0, 0, 0, 0))).status == "session_aborted"
    assert owner.result() == result and observed.call_count == 1
    public = json.dumps([asdict(owner.describe()), asdict(feedback), asdict(result)])
    assert raw not in public and "stdout" not in public and "stderr" not in public


def test_real_cortex_m_signature_replay_and_safe_behavior_difference_reaches_strategy(monkeypatch, tmp_path):
    """Exactly three fresh firmware executions through the full opaque path."""
    identifier = "b-00000000000000000000000000000017"
    fixture = Path(__file__).parent / "fixtures/cortex_m/runtime_signature.c"
    shutil.copyfile(fixture, tmp_path / fixture.name)
    shutil.copyfile(SUPPORT_DIR / "corpus_v2/harness.c", tmp_path / "harness.c")
    manifest = {
        "version": 2, "target": "mps2-an385",
        "interface": {"width": 4, "input_domain": [0, 15], "input_symbol": "firmavex_actions",
                      "failure_symbol": "firmavex_failure", "breakpoint": "benchmark_complete"},
        "benchmarks": [{"id": identifier, "name": "instrumentation_probe", "source": fixture.name, "split": "development"}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(registry_module, "CORPUS_DIR", tmp_path)
    registry = registry_module.BenchmarkRegistry()
    build = registry.build(identifier, tmp_path / "probe.elf")
    assert build["success"], build["stderr"]
    owner = registry.open_session(identifier, 3, "instrumentation-probe")

    class Probe:
        metadata = StrategyMetadata("instrumentation-probe")

        def start(self, description):
            self.description = description
            self.candidates = iter([TrialInput((0, 0, 0, 0)), TrialInput((0, 0, 0, 0)), TrialInput((1, 0, 0, 0))])
            self.feedback = []

        def propose(self):
            return next(self.candidates, None)

        def observe(self, candidate, feedback):
            self.feedback.append(feedback)

    probe = Probe()
    run = run_strategy(probe, owner.strategy_api())
    assert run.termination is TerminationReason.BUDGET_EXHAUSTED, owner.diagnostics()
    assert len(probe.feedback) == 3 and all(item.status == "safe" for item in probe.feedback)
    signals = [item.execution_signature for item in probe.feedback]
    assert all(type(item) is ExecutionSignature and not item.truncated for item in signals)
    assert signals[0] == signals[1] and signals[0] != signals[2]
    assert run.evaluation.attempted_executions == run.evaluation.successful_executions == 3
    assert run.evaluation.infrastructure_failures == 0 and not run.evaluation.aborted
    assert not run.evaluation.failure_found
    public = json.dumps([asdict(probe.description), *(asdict(item) for item in probe.feedback)])
    for private in (str(tmp_path), fixture.name, "runtime_sink", "firmavex_failure", "benchmark_complete", "stdout", "stderr", "development", "0x"):
        assert private not in public
