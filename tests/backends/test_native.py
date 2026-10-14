"""Actual native backend qualification, never synthetic execution evidence."""

import os
from pathlib import Path
import threading
import pytest

from firmavex.backends import Limits, Request
from firmavex.backends import engine
from firmavex.backends.bundled import prepare_builtin_riscv
from firmavex.backends.examples import prepare
from firmavex.backends.process import observe_processes
from firmavex.backends.tools import find
from elftools.elf.elffile import ELFFile


def require(*names):
    if os.name == "nt" and os.environ.get("FIRMAVEX_QUALIFY_BACKENDS") != "1":
        pytest.skip("Native Windows candidate qualification has not been explicitly enabled")
    try:
        for name in names:
            find(name)
    except RuntimeError as exc:
        if os.environ.get("FIRMAVEX_REQUIRE_BACKENDS") == "1":
            pytest.fail(str(exc))
        pytest.skip(str(exc))


def execute(request, output, cancel=None, trust="trusted_example"):
    return engine.execute_trusted(request, output, cancel, trust=trust)


@pytest.mark.parametrize("values,expected", [((0, 0), "passed"), ((2, 1), "triggered")])
def test_actual_native_rv32_example(tmp_path, values, expected):
    require("qemu-system-riscv32", "gdb-multiarch")
    prepared = prepare_builtin_riscv(tmp_path / "example")
    result = execute(Request("riscv32-virt", Path(prepared["source"]), values), tmp_path / "run")
    assert result["status"] == expected, result
    evidence = result["evidence"]
    assert evidence["measurement_mode"] == "real_firmware"
    assert evidence["observation"]["inputs_read_back"] == {"input_a": values[0], "input_b": values[1]}
    assert evidence["completion_observed"]
    assert evidence["cleanup_verified"]
    assert all(record["reaped"] for record in evidence["cleanup"])
    assert engine.inspect_run(tmp_path / "run") == result


def test_actual_native_hdl_pass_fail_waveform(tmp_path):
    require("iverilog", "vvp")
    prepare("verilog-icarus", tmp_path / "example")
    source = tmp_path / "example/counter.v"
    passing = execute(Request("verilog-icarus", source), tmp_path / "passing")
    failing_source = tmp_path / "failure.v"
    failing_source.write_text(source.read_text().replace("count===3", "count===4"))
    failing = execute(Request("verilog-icarus", failing_source), tmp_path / "failing", trust="trusted_project")
    for result, status in [(passing, "passed"), (failing, "triggered")]:
        assert result["status"] == status, result
        assert result["evidence"]["measurement_mode"] == "real_simulation"
        assert result["evidence"]["cleanup_verified"]
        assert any(record["name"] == "waveform.vcd" for record in result["evidence"]["artifacts"])


def test_actual_native_hdl_cancel_after_guest_output(tmp_path):
    require("iverilog", "vvp")
    source = tmp_path / "loop.v"
    source.write_text('module testbench; initial begin $display("simulation has started"); forever #1; end endmodule')
    cancel = threading.Event()
    observations = []
    def progress(event):
        observations.append(event)
        if event["stage"] == "simulation_output":
            cancel.set()
    with observe_processes(progress):
        result = execute(Request("verilog-icarus", source), tmp_path / "out", cancel, trust="trusted_project")
    assert any(event["stage"] == "simulation_output" for event in observations)
    assert result["status"] == "cancelled", result
    assert result["evidence"]["cleanup_verified"]
    assert all(record["reaped"] for record in result["evidence"]["cleanup"])


@pytest.mark.parametrize("cancelled", [False, True])
def test_actual_native_rv32_inflight_timeout_or_cancel(tmp_path, cancelled):
    require("qemu-system-riscv32", "gdb-multiarch")
    prepared = prepare_builtin_riscv(tmp_path / "example")
    source = Path(prepared["source"])
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = elf.get_section_by_name(".symtab").get_symbol_by_name("input_ready")[0]
        address = symbol["st_value"] + symbol["st_size"] - 4
        segment = next(segment for segment in elf.iter_segments()
                       if segment["p_type"] == "PT_LOAD"
                       and segment["p_vaddr"] <= address < segment["p_vaddr"] + segment["p_filesz"])
        offset = address - segment["p_vaddr"] + segment["p_offset"]
    data = bytearray(source.read_bytes())
    # Replace the final return with RV32IM JAL zero,0. Keep the function entry
    # and source-line ready breakpoint intact; after injection the guest loops
    # rather than reaching completion. No compiler
    # or original project file is altered by this separate test fixture.
    data[offset:offset + 4] = bytes.fromhex("6f000000")
    loop = tmp_path / "loop.elf"
    loop.write_bytes(data)
    cancel = threading.Event()
    observations = []
    def progress(event):
        observations.append(event)
        if cancelled and event["stage"] == "input_injected":
            cancel.set()
    with observe_processes(progress):
        result = execute(Request("riscv32-virt", loop, (2, 1), Limits(3)),
                         tmp_path / "out", cancel, trust="trusted_project")
    assert any(event["stage"] == "input_injected" for event in observations), result
    assert result["status"] == ("cancelled" if cancelled else "infrastructure_failure"), result
    if not cancelled:
        assert "TimeoutError" in result["evidence"]["error"]
    assert result["evidence"]["completion_observed"] is False
    assert result["evidence"]["measurement_mode"] != "real_firmware"
    assert result["evidence"]["cleanup_verified"]
    assert all(record["reaped"] for record in result["evidence"]["cleanup"])


def test_windows_new_backend_gate_remains_closed_without_qualification(monkeypatch):
    from firmavex.backends import implementations
    monkeypatch.setattr(implementations.os, "name", "nt")
    monkeypatch.delenv("FIRMAVEX_QUALIFY_BACKENDS", raising=False)
    with pytest.raises(RuntimeError, match="qualification"):
        implementations.require_native_candidate()


def test_windows_candidate_gate_is_explicit(monkeypatch):
    from firmavex.backends import implementations
    monkeypatch.setattr(implementations.os, "name", "nt")
    monkeypatch.setenv("FIRMAVEX_QUALIFY_BACKENDS", "1")
    implementations.require_native_candidate()


@pytest.mark.parametrize("verification,expected_cleanup", [("receipt_accounting_consistent", True), ("incomplete_receipts", False)])
def test_arm_interruption_retains_authoritative_accounting(tmp_path, monkeypatch, verification, expected_cleanup):
    from firmavex.backends.implementations import ArmBackend
    from firmavex.product import services
    original = KeyboardInterrupt("original cancellation")
    accounting = {"attempted_executions": 1, "infrastructure_failures": 1, "aborted": True}
    result = {"state": "cancelled", "accounting": accounting, "measurement_mode": "real_firmware", "triggering_input": None}
    def interrupted(*args, **kwargs):
        raise original
    monkeypatch.setattr(services, "run_project", interrupted)
    monkeypatch.setattr(services, "_read_run", lambda directory: ({
        "result": result, "attempts": [{"record": {"evidence": {"cleanup_verified": True}}}],
        "accounting_verification": {"status": verification},
    }, {}))
    with pytest.raises(KeyboardInterrupt) as raised:
        ArmBackend().execute(Request("cortex-m3-mps2", tmp_path / "project.json"), tmp_path, threading.Event())
    assert raised.value is original
    assert original.backend_evidence["legacy_result"]["accounting"] == accounting
    assert original.backend_evidence["cleanup_verified"] is expected_cleanup


def test_arm_interruption_inspection_failure_preserves_original(tmp_path, monkeypatch):
    from firmavex.backends.implementations import ArmBackend
    from firmavex.product import services
    original = KeyboardInterrupt("original interruption")
    def interrupted(*args, **kwargs):
        raise original
    def inaccessible(*args):
        raise OSError("evidence unavailable")
    monkeypatch.setattr(services, "run_project", interrupted)
    monkeypatch.setattr(services, "_read_run", inaccessible)
    with pytest.raises(KeyboardInterrupt) as raised:
        ArmBackend().execute(Request("cortex-m3-mps2", tmp_path / "project.json"), tmp_path, threading.Event())
    assert raised.value is original
    assert "evidence unavailable" in original.__notes__[0]
    assert not hasattr(original, "backend_evidence")
