import io
import socket
import subprocess
from unittest.mock import Mock

import pytest

from src.firmavex.generator import search
from src.firmavex.minimizer import minimizer
from src.firmavex.monitor import monitor


@pytest.mark.parametrize("failure_index", [0, 1])
def test_search_aborts_before_later_trigger(monkeypatch, failure_index):
    observations = [
        {"success": True, "value": 0},
    ] * failure_index + [
        {"success": False, "value": 1, "stdout": "partial", "stderr": "GDB disconnected"},
        {"success": True, "value": 1},
    ]
    observe = Mock(side_effect=observations)
    monkeypatch.setattr(search, "observe_symbol", observe)
    result = search.search_failure("test.elf", "input", "failure", "complete", range(3))
    assert result["success"] is False
    assert result["failure_found"] is False
    assert result["triggering_input"] is None
    assert result["execution_count"] == failure_index + 1
    assert observe.call_count == failure_index + 1
    assert [item["input"] for item in result["executions"]] == list(range(failure_index + 1))
    assert result["executions"][-1]["failure_detected"] is False
    assert result["error"]["input"] == failure_index
    assert result["error"]["stdout"] == "partial"
    assert result["error"]["stderr"] == "GDB disconnected"


def test_search_aborts_without_consuming_later_candidates(monkeypatch):
    def candidates():
        yield 7
        pytest.fail("Search consumed a candidate after an observation failure")

    monkeypatch.setattr(search, "observe_symbol", Mock(return_value={"success": False, "value": None}))
    result = search.search_failure("test.elf", "input", "failure", "complete", candidates())
    assert result["success"] is False
    assert result["execution_count"] == 1
    assert result["error"]["stderr"] == ""


@pytest.mark.parametrize("failure_index", [0, 1])
def test_minimizer_aborts_before_later_trigger(monkeypatch, failure_index):
    observations = [{"success": True, "value": 0}] * failure_index + [
        {"success": False, "value": 1, "stdout": "partial", "stderr": "GDB disconnected"},
        {"success": True, "value": 1},
    ]
    observe = Mock(side_effect=observations)
    monkeypatch.setattr(minimizer, "observe_symbol", observe)
    result = minimizer.minimize_integer_failure(
        "test.elf", "input", 9, "failure", "complete", minimum_input=7,
    )
    assert result["success"] is False
    assert result["minimal_input"] is None
    assert result["execution_count"] == failure_index + 1
    assert observe.call_count == failure_index + 1
    assert result["executions"] == [
        {"input": 7 + index, "success": True, "failure_value": 0, "failure_detected": False}
        for index in range(failure_index)
    ] + [
        {"input": 7 + failure_index, "success": False, "failure_value": 1, "failure_detected": False}
    ]
    assert result["error"]["input"] == 7 + failure_index
    assert result["error"]["stdout"] == "partial"
    assert result["error"]["stderr"] == "GDB disconnected"


def test_minimizer_failure_without_optional_diagnostics(monkeypatch):
    observe = Mock(return_value={"success": False, "value": None})
    monkeypatch.setattr(minimizer, "observe_symbol", observe)
    result = minimizer.minimize_integer_failure("test.elf", "input", 10, "failure", "complete")
    assert result["success"] is False
    assert result["minimal_input"] is None
    assert result["execution_count"] == 1
    assert result["error"]["input"] == 0
    assert result["error"]["stdout"] == result["error"]["stderr"] == ""
    observe.assert_called_once()


def test_minimizer_success_preserves_result_fields(monkeypatch):
    observe = Mock(side_effect=[{"success": True, "value": 0}, {"success": True, "value": 3}])
    monkeypatch.setattr(minimizer, "observe_symbol", observe)
    result = minimizer.minimize_integer_failure(
        "test.elf", "input", 10, "failure", "complete", minimum_input=7, failure_value=3,
    )
    assert result == {
        "success": True, "minimal_input": 8, "execution_count": 2,
        "executions": [
            {"input": 7, "success": True, "failure_value": 0, "failure_detected": False},
            {"input": 8, "success": True, "failure_value": 3, "failure_detected": True},
        ],
    }
    assert observe.call_count == 2


@pytest.fixture
def fake_monitor(monkeypatch, tmp_path):
    image = tmp_path / "test.elf"
    image.touch()
    qemu = Mock()
    qemu.poll.return_value = None
    qemu.stderr = io.StringIO("QEMU startup error")
    launch = Mock(return_value=qemu)
    gdb = Mock(return_value=subprocess.CompletedProcess([], 0, "FIRMAVEX_VALUE=0x1\n", ""))
    monkeypatch.setattr(monitor.subprocess, "Popen", launch)
    monkeypatch.setattr(monitor.subprocess, "run", gdb)
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    return image, qemu, launch, gdb


def test_monitor_uses_same_isolated_loopback_port_for_qemu_and_gdb(monkeypatch, fake_monitor):
    image, qemu, launch, gdb = fake_monitor
    monkeypatch.setattr(monitor, "_allocate_gdb_port", Mock(side_effect=[41001, 41002]))
    for port in (41001, 41002):
        qemu.stderr = io.StringIO()
        result = monitor.observe_symbol(str(image), "failure", "complete")
        assert result["success"] is True
        assert result["value"] == 1
        assert f"tcp:127.0.0.1:{port}" in launch.call_args.args[0]
        assert f"target remote 127.0.0.1:{port}" in gdb.call_args.args[0]
        assert qemu.stderr.closed
    assert qemu.terminate.call_count == 2
    assert qemu.wait.call_count == 2


def test_port_allocator_avoids_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = monitor._allocate_gdb_port()
        assert port != occupied.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as available:
            available.bind(("127.0.0.1", port))


def test_port_allocation_failure_is_structured(monkeypatch, fake_monitor):
    image, _, launch, gdb = fake_monitor
    monkeypatch.setattr(monitor, "_allocate_gdb_port", Mock(side_effect=OSError("no ports")))
    result = monitor.observe_symbol(str(image), "failure", "complete")
    assert result["success"] is False
    assert "no ports" in result["stderr"]
    launch.assert_not_called()
    gdb.assert_not_called()


def test_qemu_start_failure_is_structured(fake_monitor):
    image, _, launch, gdb = fake_monitor
    launch.side_effect = FileNotFoundError("qemu-system-arm")
    result = monitor.observe_symbol(str(image), "failure", "complete")
    assert result["success"] is False
    assert "Unable to start QEMU" in result["stderr"]
    gdb.assert_not_called()


def test_exited_qemu_does_not_connect_gdb_to_another_process(fake_monitor):
    image, qemu, _, gdb = fake_monitor
    qemu.poll.return_value = 1
    result = monitor.observe_symbol(str(image), "failure", "complete")
    assert result["success"] is False
    assert "QEMU startup error" in result["stderr"]
    gdb.assert_not_called()
    qemu.terminate.assert_not_called()
    qemu.wait.assert_called_once()
    assert qemu.stderr.closed


def test_qemu_exit_during_gdb_run_invalidates_observation(fake_monitor):
    image, qemu, _, _ = fake_monitor
    qemu.poll.side_effect = [None, 1, 1]
    result = monitor.observe_symbol(str(image), "failure", "complete")
    assert result["success"] is False
    assert result["value"] is None
    assert "QEMU exited during observation" in result["stderr"]
    assert result["stdout"] == "FIRMAVEX_VALUE=0x1\n"
    qemu.wait.assert_called_once()
    assert qemu.stderr.closed


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("gdb", 1), FileNotFoundError("gdb")])
def test_gdb_failure_returns_failure_and_cleans_up(fake_monitor, error):
    image, qemu, _, gdb = fake_monitor
    gdb.side_effect = error
    result = monitor.observe_symbol(str(image), "failure", "complete")
    assert result["success"] is False
    assert result["value"] is None
    assert result["stderr"]
    qemu.terminate.assert_called_once()
    qemu.wait.assert_called_once()
    assert qemu.stderr.closed


def test_cleanup_kills_qemu_if_termination_times_out(fake_monitor):
    image, qemu, _, _ = fake_monitor
    qemu.wait.side_effect = [subprocess.TimeoutExpired("qemu", 2), 0]
    result = monitor.observe_symbol(str(image), "failure", "complete")
    assert result["success"] is True
    qemu.terminate.assert_called_once()
    qemu.kill.assert_called_once()
    assert qemu.wait.call_count == 2
    assert qemu.stderr.closed


def test_monitor_injects_multiple_symbols_and_actions_before_continuing(fake_monitor):
    image, _, _, gdb = fake_monitor
    inputs = {"first": 9, "second": 12, "actions[0]": 3, "actions[1]": 11}
    result = monitor.observe_symbol(str(image), "failure", "complete", input_values=inputs)
    assert result["success"] is True
    command = gdb.call_args.args[0]
    for name, value in inputs.items():
        assignment = f"set variable {name} = {value}"
        assert command.index(assignment) < command.index("continue")


@pytest.mark.parametrize("inputs", [{"x;quit": 1}, {"x": -1}, {"x": True}, {"x": 0x100000000}, {1: 2}, [1, 2]])
def test_invalid_multi_inputs_never_launch_firmware(fake_monitor, inputs):
    image, _, launch, _ = fake_monitor
    result = monitor.observe_symbol(str(image), "failure", "complete", input_values=inputs)
    assert result["success"] is False
    launch.assert_not_called()


def test_monitor_rejects_ambiguous_old_and_new_injection(fake_monitor):
    image, _, launch, _ = fake_monitor
    result = monitor.observe_symbol(str(image), "failure", "complete", set_symbol="old", set_value=1, input_values={"new": 2})
    assert result["success"] is False
    launch.assert_not_called()
