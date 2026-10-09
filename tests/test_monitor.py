import asyncio
import json
import subprocess
from dataclasses import asdict
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession
from src.firmavex.monitor import monitor
from src.firmavex.monitor.monitor import observe_symbol


def test_observe_firmavex_marker(cortex_m_firmware):
    result = observe_symbol(
        cortex_m_firmware["minimal"],
        symbol="firmavex_marker",
        breakpoint="minimal.c:7",
    )

    assert result["success"] is True
    assert result["symbol"] == "firmavex_marker"
    assert result["value"] == 0xF1A5


@pytest.fixture
def interrupted_monitor(monkeypatch, tmp_path):
    image = tmp_path / "interrupted.elf"
    image.touch()
    qemu = Mock()
    qemu.poll.return_value = None
    gdb = Mock()
    monkeypatch.setattr(monitor, "_allocate_gdb_port", lambda: 41001)
    monkeypatch.setattr(monitor.subprocess, "Popen", Mock(return_value=qemu))
    monkeypatch.setattr(monitor.subprocess, "run", gdb)
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    return image, qemu, gdb


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
@pytest.mark.parametrize("operation", ["poll", "terminate", "wait", "kill", "reap", "stderr close"])
def test_cleanup_failure_preserves_original_interruption(interrupted_monitor, exception_type, operation):
    image, qemu, gdb = interrupted_monitor
    interruption = exception_type("original cancellation")
    secondary = OSError(f"{operation} failed")
    gdb.side_effect = interruption
    if operation == "poll":
        qemu.poll.side_effect = [None, secondary]
    elif operation == "terminate":
        qemu.terminate.side_effect = secondary
        qemu.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), 0]
    elif operation == "wait":
        qemu.wait.side_effect = [secondary, 0]
    elif operation == "kill":
        qemu.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), 0]
        qemu.kill.side_effect = secondary
    elif operation == "reap":
        qemu.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), secondary]
    else:
        qemu.stderr.close.side_effect = secondary

    with pytest.raises(exception_type) as raised:
        observe_symbol(str(image), "failure", "complete")

    assert raised.value is interruption
    assert any(f"QEMU cleanup {operation} failed: OSError" in note for note in interruption.__notes__)
    qemu.terminate.assert_called_once()
    qemu.stderr.close.assert_called_once()
    if operation in {"terminate", "wait", "kill", "reap"}:
        qemu.kill.assert_called_once()
        assert qemu.wait.call_count == 2
        assert all(call.kwargs == {"timeout": 2} for call in qemu.wait.call_args_list)
    else:
        qemu.wait.assert_called_once_with(timeout=2)


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_multiple_cleanup_errors_do_not_skip_remaining_stages(interrupted_monitor, exception_type):
    image, qemu, gdb = interrupted_monitor
    interruption = exception_type("original cancellation")
    gdb.side_effect = interruption
    qemu.poll.side_effect = [None, OSError("poll failed")]
    qemu.terminate.side_effect = OSError("terminate failed")
    qemu.wait.side_effect = [OSError("wait failed"), subprocess.TimeoutExpired("qemu", 2)]
    qemu.kill.side_effect = OSError("kill failed")
    qemu.stderr.close.side_effect = OSError("close failed")

    with pytest.raises(exception_type) as raised:
        observe_symbol(str(image), "failure", "complete")

    assert raised.value is interruption
    assert len(interruption.__notes__) == 6
    qemu.terminate.assert_called_once()
    qemu.kill.assert_called_once()
    assert qemu.wait.call_count == 2
    qemu.stderr.close.assert_called_once()


def test_cleanup_failure_without_interruption_is_not_silently_successful(interrupted_monitor):
    image, qemu, gdb = interrupted_monitor
    gdb.return_value = subprocess.CompletedProcess([], 0, "FIRMAVEX_VALUE=0x1\n", "")
    primary = OSError("terminate failed")
    qemu.terminate.side_effect = primary
    qemu.wait.side_effect = [OSError("wait failed"), 0]
    qemu.stderr.close.side_effect = OSError("close failed")

    with pytest.raises(OSError) as raised:
        observe_symbol(str(image), "failure", "complete")

    assert raised.value is primary
    assert len(primary.__notes__) == 3
    qemu.kill.assert_called_once()
    assert qemu.wait.call_count == 2
    qemu.stderr.close.assert_called_once()


def test_diagnostic_formatting_failure_cannot_replace_interruption(interrupted_monitor):
    class UnprintableCleanupError(OSError):
        def __str__(self):
            raise RuntimeError("diagnostic formatting failed")

    image, qemu, gdb = interrupted_monitor
    interruption = KeyboardInterrupt("original cancellation")
    gdb.side_effect = interruption
    qemu.terminate.side_effect = UnprintableCleanupError()

    with pytest.raises(KeyboardInterrupt) as raised:
        observe_symbol(str(image), "failure", "complete")

    assert raised.value is interruption
    assert interruption.__notes__ == [
        "QEMU cleanup terminate failed: UnprintableCleanupError: <diagnostic unavailable>"
    ]
    qemu.wait.assert_called_once_with(timeout=2)
    qemu.stderr.close.assert_called_once()


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_monitor_cleanup_failure_keeps_evaluator_interruption_accounting(interrupted_monitor, exception_type):
    image, qemu, gdb = interrupted_monitor
    interruption = exception_type("private cancellation diagnostic")
    gdb.side_effect = interruption
    qemu.stderr.close.side_effect = OSError("private cleanup diagnostic")
    owner = EvaluationSession(
        "b-3874d6a4a92f46758d73854abf0a08df", InputSpace(1, 0, 15), 2,
        "monitor-cleanup-test",
        lambda values: observe_symbol(
            str(image), "failure", "complete", input_values={"input": values[0]},
            collect_signature=True,
        ),
    )
    public = owner.strategy_api()

    with pytest.raises(exception_type) as raised:
        public.execute(TrialInput((0,)))

    assert raised.value is interruption
    result = public.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == result.failure_triggering_executions == 0
    assert result.aborted and not result.failure_found
    assert result.budget_remaining == 1
    feedback = public.execute(TrialInput((1,)))
    assert feedback.status == "session_aborted"
    assert feedback.execution_signature is None
    assert public.result() == result
    gdb.assert_called_once()
    assert "private cancellation diagnostic" in owner.diagnostics()[0]["stderr"]
    assert "private cleanup diagnostic" in interruption.__notes__[0]
    records = json.dumps([asdict(public.describe()), asdict(feedback), asdict(result)])
    assert "private" not in records


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_cleanup_cancellation_outranks_ordinary_observation_error(interrupted_monitor, exception_type):
    image, qemu, gdb = interrupted_monitor
    observation_error = RuntimeError("ordinary observation failure")
    interruption = exception_type("cancellation during cleanup")
    gdb.side_effect = observation_error
    qemu.wait.side_effect = [interruption, 0]
    owner = EvaluationSession(
        "b-3874d6a4a92f46758d73854abf0a08df", InputSpace(1, 0, 15), 2,
        "monitor-cleanup-test",
        lambda _: observe_symbol(str(image), "failure", "complete"),
    )

    with pytest.raises(exception_type) as caught:
        owner.execute(TrialInput((0,)))
    assert caught.value is interruption
    assert interruption.__cause__ is observation_error
    assert "QEMU cleanup wait failed" in interruption.__notes__[0]
    result = owner.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0 and result.aborted
    assert owner.execute(TrialInput((1,))).status == "session_aborted"
    gdb.assert_called_once()
    qemu.kill.assert_called_once()
    assert qemu.wait.call_count == 2
    qemu.stderr.close.assert_called_once()


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, RuntimeError])
def test_unrelated_caller_handler_cannot_hide_cleanup_failure(interrupted_monitor, exception_type):
    image, qemu, gdb = interrupted_monitor
    gdb.return_value = subprocess.CompletedProcess([], 0, "FIRMAVEX_VALUE=0x1\n", "")
    cleanup_error = OSError("cleanup failed")
    qemu.stderr.close.side_effect = cleanup_error
    caller_error = exception_type("unrelated caller exception")

    try:
        raise caller_error
    except exception_type:
        with pytest.raises(OSError) as raised:
            observe_symbol(str(image), "failure", "complete")

    assert raised.value is cleanup_error
    assert not hasattr(caller_error, "__notes__")
    qemu.wait.assert_called_once_with(timeout=2)
    qemu.stderr.close.assert_called_once()


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
@pytest.mark.parametrize("operation", ["wait", "kill", "reap", "stderr close"])
def test_new_cleanup_cancellation_outranks_earlier_ordinary_error(interrupted_monitor, exception_type, operation):
    image, qemu, gdb = interrupted_monitor
    gdb.return_value = subprocess.CompletedProcess([], 0, "FIRMAVEX_VALUE=0x1\n", "")
    ordinary_error = OSError("terminate failed")
    interruption = exception_type("cleanup cancellation")
    qemu.terminate.side_effect = ordinary_error
    if operation == "wait":
        qemu.wait.side_effect = [interruption, 0]
    elif operation == "kill":
        qemu.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), 0]
        qemu.kill.side_effect = interruption
    elif operation == "reap":
        qemu.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), interruption]
    else:
        qemu.stderr.close.side_effect = interruption

    with pytest.raises(exception_type) as raised:
        observe_symbol(str(image), "failure", "complete")

    assert raised.value is interruption
    assert any("terminate failed: OSError: terminate failed" in note for note in interruption.__notes__)
    assert any(f"QEMU cleanup {operation} failed: {exception_type.__name__}" in note for note in interruption.__notes__)
    assert not hasattr(ordinary_error, "__notes__")
    qemu.stderr.close.assert_called_once()
    if operation != "stderr close":
        qemu.kill.assert_called_once()
        assert qemu.wait.call_count == 2
