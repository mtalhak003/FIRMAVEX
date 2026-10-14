"""Bounded actual-runtime qualification of source or frozen backend workers.

This operator tool has no synthetic executor injection seam. It never runs a
research campaign and only writes inside a fresh, caller-selected directory.
The opt-in candidate environment flag does not establish public support.
"""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import threading

from elftools.elf.elffile import ELFFile

from firmavex.backends import Limits, Request
from firmavex.backends.api import request_to_dict
from firmavex.product.errors import ProductError
from firmavex.product.supervisor import Supervisor


PROFILES = ("cortex-m3-mps2", "riscv32-virt", "verilog-icarus")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pid_active(pid):
    """Existence query only: Windows os.kill(pid, 0) can terminate a process."""
    _require(type(pid) is int and pid > 0, "Invalid owned process identity")
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
    library.OpenProcess.restype = ctypes.c_void_p
    library.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    library.GetExitCodeProcess.restype = ctypes.c_int32
    library.CloseHandle.argtypes = [ctypes.c_void_p]
    library.CloseHandle.restype = ctypes.c_int32
    handle = library.OpenProcess(0x1000, False, pid)
    if not handle:
        _require(ctypes.get_last_error() == 87, "Cannot independently inspect owned PID")
        return False
    try:
        code = ctypes.c_uint32()
        _require(bool(library.GetExitCodeProcess(handle, ctypes.byref(code))), "Process query failed")
        return code.value == 259
    finally:
        _require(bool(library.CloseHandle(handle)), "Process query handle cleanup failed")


def _verify_cleanup(record):
    evidence = record["evidence"]
    _require(evidence.get("cleanup_verified") is True, "Backend cleanup is not verified")
    for child in evidence.get("cleanup", []):
        _require(child.get("reaped") is True, "Owned subprocess was not reaped")
        _require(not _pid_active(child["pid"]), "Owned subprocess remains active")


def _arm_receipts(directory, expected, *, cancelled=False):
    """Validate existing SQLite receipts without inferring physical execution."""
    database = Path(directory) / "arm-run" / "run.sqlite3"
    connection = sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True)
    try:
        rows = connection.execute("select record from attempts order by sequence").fetchall()
    finally:
        connection.close()
    _require(len(rows) == expected, "Missing ARM evaluator execution receipts")
    receipts = [json.loads(row[0])["evidence"] for row in rows]
    for evidence in receipts:
        _require(evidence.get("cleanup_verified") is True, "ARM cleanup is not verified")
        for child in evidence["cleanup"]["processes"]:
            _require(child["reaped"] is True, "ARM owned process was not reaped")
            _require(not _pid_active(child["pid"]), "ARM owned subprocess remains active")
        if not cancelled:
            _require(evidence.get("measurement_mode") == "real_firmware", "ARM receipt is not real firmware")
            for field in ("guest_dispatched", "input_injected", "completion_reached"):
                _require(evidence.get(field) is True, "ARM completion evidence is incomplete")
        else:
            _require(evidence.get("guest_dispatched") is True and evidence.get("input_injected") is True,
                     "ARM cancellation occurred before actual guest dispatch/input readback")
    return receipts


def verify_completed(record, profile, expected):
    """Reject labels alone, contradictory outcomes, and missing native evidence."""
    _require(type(record.get("schema_version")) is int and record["schema_version"] == 1, "Unexpected result schema")
    if record.get("status") != expected:
        evidence = record.get("evidence", {})
        exc = ValueError(f"Unexpected {profile} outcome: {record.get('status')}")
        exc.details = {key: evidence.get(key) for key in
                       ("returncode", "stdout", "stderr", "compile_stdout", "compile_stderr", "cleanup_verified", "error")}
        raise exc
    evidence = record["evidence"]
    _require(evidence.get("cleanup_verified") is True, "Completion has unverified cleanup")
    if profile == "cortex-m3-mps2":
        legacy = evidence["legacy_result"]
        accounting = legacy["accounting"]
        _require(legacy["measurement_mode"] == "real_firmware", "ARM result is not real firmware")
        _require(legacy["triggering_input"] == [2, 1], "Unexpected ARM triggering vector")
        _require(accounting["attempted_executions"] == 10 and accounting["successful_executions"] == 10, "ARM accounting changed")
        _require(accounting["infrastructure_failures"] == 0 and accounting["aborted"] is False, "ARM run aborted")
    else:
        expected_mode = "real_firmware" if profile == "riscv32-virt" else "real_simulation"
        _require(evidence.get("measurement_mode") == expected_mode, "Execution was not established by the actual runtime")
        _require(bool(evidence.get("tools")), "No actual tool identities were recorded")
        for tool in evidence["tools"].values():
            identity = tool["identity"]
            digest = identity.get("sha256")
            _require(type(digest) is str and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
                     and type(tool.get("version")) is str and bool(tool["version"]), "Missing tool digest/version")
        if profile == "riscv32-virt":
            _require(evidence.get("completion_observed") is True, "RISC-V completion is missing")
            _require(evidence["observation"]["success"] is True, "RISC-V observation failed")
        else:
            _require(evidence["returncode"] == 0, "HDL simulator failed")
            _require(bool(evidence.get("artifacts")), "The example waveform was not recorded")
        _verify_cleanup(record)


def _rv_loop(image, destination):
    """Create an administratively declared RV32 loop, never change a catalog image."""
    data = bytearray(Path(image).read_bytes())
    with Path(image).open("rb") as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name(".symtab").get_symbol_by_name("input_ready")
        _require(len(symbols or []) == 1, "Required example symbol missing")
        size = symbols[0]["st_size"]
        _require(size >= 4 and size % 4 == 0, "Unsupported RV32 example function shape")
        # A symbolic GDB breakpoint can resolve after the function prologue.
        # Preserve it, and replace the last return instruction with a loop.
        address = symbols[0]["st_value"] + size - 4
        offsets = [segment["p_offset"] + address - segment["p_vaddr"] for segment in elf.iter_segments()
                   if segment["p_type"] == "PT_LOAD" and segment["p_vaddr"] <= address < segment["p_vaddr"] + segment["p_filesz"]]
        _require(len(offsets) == 1, "Ambiguous example instruction location")
        offset = offsets[0]
    # JAL x0, 0: the ready breakpoint is reached, then completion cannot occur.
    data[offset:offset + 4] = bytes.fromhex("6f000000")
    Path(destination).write_bytes(data)


def _record(path, record):
    Path(path).write_text(json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _runtime_notice(profile, record, receipts, *, frozen):
    evidence = record["evidence"]
    if profile == "cortex-m3-mps2":
        identities = receipts[0]["tools"]["identities"]
        tools = {name: {"sha256": item["sha256"], "version": item["version"]}
                 for name, item in identities.items() if name in {"qemu", "gdb"}}
    else:
        tools = {name: {"sha256": item["identity"]["sha256"], "version": item["version"]}
                 for name, item in evidence["tools"].items()}
    summary = {"profile": profile, "host": platform.system(), "architecture": platform.machine(),
               "execution_path": "frozen" if frozen else "source", "status": record["status"],
               "measurement_mode": evidence["measurement_mode"], "real_execution_and_reproduction_verified": True,
               "tools": tools}
    print("::notice title=Universal runtime qualification::" + json.dumps(summary, sort_keys=True))
    return summary


def qualify(output, engine=None):
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    worker = None
    if engine is not None:
        engine = Path(engine).resolve(strict=True)
        _require(engine.is_file(), "Frozen console engine is missing")
        worker = [str(engine), "--firmavex-worker"]
    supervisor = Supervisor(worker_argv=worker)
    observations = []
    runtime_evidence = []
    prepared = {}
    for profile in PROFILES:
        readiness = supervisor.execute("backend_check", {"profile": profile}, timeout=120)
        _record(output / (profile + "-readiness.json"), readiness)
        prepared[profile] = supervisor.execute("backend_prepare", {"profile": profile, "output_dir": str(output / (profile + "-project"))}, timeout=120)
        source = Path(prepared[profile]["source"])
        vectors = [("search", (), "triggered")] if profile == "cortex-m3-mps2" else (
            [("safe", (0, 0), "passed"), ("trigger", (2, 1), "triggered")]
            if profile == "riscv32-virt" else [("pass", (), "passed")])
        for name, values, expected in vectors:
            directory = output / (profile + "-" + name)
            request = Request(profile, source, values)
            result = supervisor.execute("backend_execute", {"request": request_to_dict(request), "output_dir": str(directory), "trust": "trusted_example"}, timeout=120)
            verify_completed(result, profile, expected)
            _require(supervisor.execute("backend_inspect", {"run_dir": str(directory)}) == result, "Saved result differs from authoritative execution result")
            exported = supervisor.execute("backend_export", {"run_dir": str(directory), "output_dir": str(directory) + "-report"})
            _require(exported["status"] == "exported", "Report export failed")
            receipts = _arm_receipts(directory, 10) if profile == "cortex-m3-mps2" else None
            if profile == "verilog-icarus":
                _require((Path(exported["destination"]) / "waveform.vcd").is_file(), "Export omitted the waveform")
            replay_dir = Path(str(directory) + "-replay")
            replay = supervisor.execute("backend_reproduce", {"run_dir": str(directory), "output_dir": str(replay_dir), "trust": "trusted_example"}, timeout=120)
            _require(replay["outcome_matches"] is True and replay["status"] == expected, "Native reproduction failed")
            if profile == "cortex-m3-mps2":
                _arm_receipts(replay_dir, 3)
            else:
                _verify_cleanup(replay["result"])
            observations.append({"profile": profile, "case": name, "status": result["status"], "measurement_mode": result["evidence"]["measurement_mode"], "reproduced": True})
            runtime_evidence.append(_runtime_notice(profile, result, receipts, frozen=engine is not None))
    # Independently declared failing assertion; this is not a failing compiler.
    hdl_source = output / "hdl-declared-failure.v"
    hdl_text = Path(prepared["verilog-icarus"]["source"]).read_text(encoding="ascii")
    _require("count===3" in hdl_text, "The declared HDL example assertion changed")
    hdl_source.write_text(hdl_text.replace("count===3", "count===4"), encoding="ascii")
    failure_directory = output / "hdl-declared-failure"
    result = supervisor.execute("backend_execute", {"request": request_to_dict(Request("verilog-icarus", hdl_source)), "output_dir": str(failure_directory), "trust": "trusted_project"}, timeout=120)
    verify_completed(result, "verilog-icarus", "triggered")
    replay = supervisor.execute("backend_reproduce", {"run_dir": str(failure_directory), "output_dir": str(output / "hdl-declared-failure-replay"), "trust": "trusted_project"}, timeout=120)
    _require(replay["outcome_matches"] is True and replay["status"] == "triggered", "Declared HDL failure did not reproduce")
    observations.append({"profile": "verilog-icarus", "case": "declared-failure", "status": "triggered", "measurement_mode": result["evidence"]["measurement_mode"], "reproduced": True})
    for profile in PROFILES:
        observations.append(_cancel_case(supervisor, output, profile, Path(prepared[profile]["source"])))
    record = {"schema_version": 1, "kind": "firmavex_unified_native_qualification", "scope": "bounded declared examples only; not hardware, hostile-workload, or research qualification", "host": {"os": platform.system(), "architecture": platform.machine(), "python": platform.python_version()}, "execution_path": "frozen-console-worker" if engine else "source-supervised-worker", "frozen_engine_sha256": _sha256(engine) if engine else None, "observations": observations, "runtime_evidence": runtime_evidence, "synthetic_execution_used": False}
    _record(output / "qualification.json", record)
    print("::notice title=Unified native qualification::" + json.dumps(record, sort_keys=True))
    return record


def _cancel_case(supervisor, output, profile, source):
    cancel = threading.Event()
    run = output / (profile + "-cancel")
    cancellation_observed = []
    if profile == "cortex-m3-mps2":
        config = json.loads(source.read_text(encoding="utf-8"))
        config["firmware"] = str((source.parent / config["firmware"]).resolve())
        config["completion_breakpoint"] = "Default_Handler"
        config["timeout_seconds"] = 10
        candidate = output / "arm-cancel-project.json"
        _record(candidate, config)
        values = ()
    elif profile == "riscv32-virt":
        candidate = output / "rv-cancel-loop.elf"
        _rv_loop(source, candidate)
        values = (2, 1)
    else:
        candidate = output / "hdl-cancel-loop.v"
        candidate.write_text('module testbench; initial begin $dumpfile("waveform.vcd"); $dumpvars(0,testbench); $display("FIRMAVEX_SIMULATION_STARTED"); forever #1; end endmodule\n', encoding="ascii")
        values = ()
    def on_event(event):
        payload = event.get("payload", {})
        # These stages are emitted from actual debugger readback/simulator
        # output, never from executable names or caller-supplied labels.
        if profile in {"cortex-m3-mps2", "riscv32-virt"} and payload.get("stage") in {"injected", "input_injected"}:
            cancellation_observed.append("GDB guest input readback")
            cancel.set()
        elif (profile == "verilog-icarus" and payload.get("stage") == "simulation_output"
              and "FIRMAVEX_SIMULATION_STARTED" in payload.get("stdout_preview", "")):
            cancellation_observed.append("actual simulation started")
            cancel.set()

    limits = Limits() if profile == "cortex-m3-mps2" else Limits(timeout_seconds=20)
    try:
        result = supervisor.execute("backend_execute", {"request": request_to_dict(Request(profile, candidate, values, limits)), "output_dir": str(run), "trust": "trusted_project"}, cancel_event=cancel, event_callback=on_event, timeout=60)
    except ProductError as exc:
        # Existing ARM execution deliberately re-raises control-flow
        # cancellation after persisting its charged attempt. Inspect that
        # authoritative result; never retry or infer a completed trial.
        if not cancel.is_set() or exc.category != "cancelled":
            raise
        result = supervisor.execute("backend_inspect", {"run_dir": str(run)})
        _require(result.get("status") == "cancelled", "Interrupted backend has no authoritative cancelled result")
    _require(bool(cancellation_observed), "Cancellation did not reach its declared actual execution stage")
    if profile == "cortex-m3-mps2":
        legacy = json.loads((run / "arm-run/result.json").read_text(encoding="utf-8"))
        _require(legacy["state"] == "cancelled" and legacy["accounting"]["aborted"] is True, "ARM cancellation accounting changed")
        _require(legacy["accounting"]["attempted_executions"] == 1 and legacy["accounting"]["infrastructure_failures"] == 1, "ARM cancellation lost its charged attempt")
        _arm_receipts(run, 1, cancelled=True)
    else:
        _require(result["status"] == "cancelled", "Backend did not preserve cancellation")
        _verify_cleanup(result)
    _require(supervisor.execute("backend_inspect", {"run_dir": str(run)}) == result, "Cancelled result was not durably persisted")
    return {"profile": profile, "case": "in-flight-cancellation", "status": result["status"], "cancelled_at": cancellation_observed, "cleanup_verified": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", type=Path, help="Frozen FIRMAVEX console executable; no child Python interpreter is used.")
    args = parser.parse_args(argv)
    try:
        qualify(args.output, args.engine)
    except Exception as exc:
        details = getattr(exc, "details", {})
        record = {"type": type(exc).__name__, "message": str(exc), "details": details}
        text = json.dumps(record, sort_keys=True, default=str)[-10000:]
        print("::error title=Actual unified backend qualification failed::" + text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
