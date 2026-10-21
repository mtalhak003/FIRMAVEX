"""Concrete adapters, with explicit native candidate qualification gates."""

import json
import os
from pathlib import Path
import re
import socket
import time
import uuid
from types import SimpleNamespace
from firmavex.product.tools import file_identity
from firmavex.product.runtime import _allocate_port, _debugger_script, _parse_completion
from .api import Result, profiles
from .process import Processes, emit_process_event, inspect_artifacts


def tool(name):
    from .tools import find
    return find(name)


def require_native_candidate(profile=None):
    """An explicit candidate environment enables actual CI tests, never support claims."""
    if profile is None:
        if os.name == "nt" and os.environ.get("FIRMAVEX_QUALIFY_BACKENDS") != "1":
            raise RuntimeError("Native Windows target requires explicit qualification")
        return
    from .qualification import require_windows_qualification
    require_windows_qualification(profile)

def snapshot(source, destination, maximum):
    from .security import read_bytes, checked_path
    destination = checked_path(destination, exists=False)
    with destination.open("xb") as stream:
        stream.write(read_bytes(source, maximum))
    return file_identity(destination)


def riscv_debugger_script(config, values, port, marker):
    """Reuse observation semantics; flush RV administrative progress over pipes."""
    lines = _debugger_script(config, values, port, marker).splitlines()
    result = []
    for line in lines:
        result.append(line)
        if line.lstrip().startswith('gdb.write(settings["marker"]'):
            result.append("    gdb.flush(gdb.STDOUT)")
    return "\n".join(result) + "\n"


def finish(processes, primary, evidence=None):
    try:
        processes.close()
    except BaseException as cleanup:
        if evidence is not None:
            evidence["cleanup_verified"] = False
            cleanup.backend_evidence = evidence
        if primary is not None:
            primary.add_note(f"Cleanup failed: {cleanup}")
            if hasattr(primary, "backend_evidence"):
                primary.backend_evidence["cleanup_verified"] = False
            if not isinstance(cleanup, Exception) and isinstance(primary, Exception):
                raise
        else:
            raise
        return False
    return True


class ArmBackend:
    profile = profiles["cortex-m3-mps2"]

    def execute(self, request, output, cancel):
        from firmavex.product.config import load_config
        from firmavex.product import services

        # Delegate the entire established search/accounting path unchanged.
        try:
            result = services.run_project(
                request.source, output / "arm-run", cancel_event=cancel,
                event_callback=emit_process_event,
            )
        except BaseException as original:
            # The established service persists charged interruption accounting
            # and re-raises. Retain it at the adapter boundary without changing
            # cancellation semantics or inferring absent receipts.
            try:
                snapshot, artifacts = services._read_run(output / "arm-run")
                retained = snapshot.get("result")
                if retained is not None:
                    original.backend_evidence = {
                        "legacy_result": retained,
                        "adapter": "unchanged product services",
                        "triggering_input": retained.get("triggering_input"),
                        "measurement_mode": retained.get("measurement_mode", "unverified"),
                        "cleanup_verified": (snapshot.get("accounting_verification", {}).get("status") == "receipt_accounting_consistent"
                                             and all(item["record"].get("evidence", {}).get("cleanup_verified") is True for item in snapshot["attempts"])),
                        "accounting_verification": snapshot.get("accounting_verification", {"status": "unknown"}),
                    }
            except BaseException as inspection:
                original.add_note(f"Retained ARM interruption evidence could not be verified: {type(inspection).__name__}: {inspection}")
            raise
        outcome = result.get("outcome")
        accounting = result.get("accounting") or {}
        complete = result.get("execution_evidence") == "complete"
        if (
            accounting.get("aborted") is True
            or result.get("success") is not True
            or not complete
            or result.get("state") != "completed"
        ):
            status = (
                "invalid_output"
                if outcome == "invalid_output"
                else "infrastructure_failure"
            )
        elif outcome == "configured_failure_observed":
            status = "triggered"
        elif outcome in {"domain_exhausted", "no_failure_within_budget"}:
            status = "not_discovered"
        else:
            status = "invalid_output"
        return Result(
            status,
            {
                "legacy_result": result,
                "adapter": "unchanged product services",
                "triggering_input": result.get("triggering_input"),
                "measurement_mode": result.get("measurement_mode", "unverified"),
                "cleanup_verified": complete
                and result.get("success") is True
                and not accounting.get("aborted", False),
            },
        )


class RiscvBackend:
    profile = profiles["riscv32-virt"]

    def execute(self, request, output, cancel):
        require_native_candidate(self.profile.id)
        image = output / "firmware.elf"
        identity = snapshot(request.source, image, request.limits.artifact_bytes)
        from .inputs import rv32
        rv32(image.read_bytes())
        from .tools import find_many
        selections = find_many(("qemu-system-riscv32", "gdb-multiarch"))
        processes = Processes(cancel, request.limits)
        primary = None
        evidence = {
            "firmware": identity,
            "values": list(request.values),
            "backend": self.profile.id,
            "measurement_mode": "unverified",
            "tools": {},
            "completion_observed": False,
        }
        try:
            qemu, gdb = selections["qemu-system-riscv32"], selections["gdb-multiarch"]
            for name, path in (("qemu", qemu), ("gdb", gdb)):
                code, stdout, stderr = processes.run([path, "--version"], output)
                if code:
                    raise RuntimeError(f"{name} version probe failed: {stderr}")
                evidence["tools"][name] = {
                    "identity": file_identity(path),
                    "version": stdout.splitlines()[0],
                }
            port = _allocate_port()
            child, qout, qerr = processes.spawn(
                [
                    qemu,
                    "-M",
                    "virt",
                    "-cpu",
                    "rv32",
                    "-m",
                    "128M",
                    "-smp",
                    "1",
                    "-bios",
                    "none",
                    "-kernel",
                    str(image),
                    "-display",
                    "none",
                    "-serial",
                    "null",
                    "-monitor",
                    "none",
                    "-S",
                    "-gdb",
                    f"tcp:127.0.0.1:{port}",
                ],
                output,
            )
            deadline = time.monotonic() + min(5, request.limits.timeout_seconds)
            while True:
                processes.check()
                if child.poll() is not None:
                    raise RuntimeError("QEMU startup failed: " + qerr.text())
                try:
                    with socket.create_connection(("127.0.0.1", port), 0.05):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Debugger endpoint timeout")
                    time.sleep(0.02)
            emit_process_event({"type": "backend_stage", "stage": "debugger_ready", "pid": child.pid})
            config = SimpleNamespace(
                input_symbols=("input_a", "input_b"),
                ready_breakpoint="input_ready",
                completion_breakpoint="benchmark_complete",
                failure_symbol="failure_flag",
                failure_value=1,
                collect_signature=False,
            )
            marker = "FIRMAVEX_BACKEND_" + uuid.uuid4().hex + "="
            script = output / "observe.gdb"
            script.write_text(riscv_debugger_script(config, request.values, port, marker), encoding="utf-8")
            code, stdout, stderr = processes.run(
                [
                    gdb,
                    "--nx",
                    "--nh",
                    "--batch",
                    "-iex",
                    "set auto-load off",
                    "-iex",
                    "set python dont-write-bytecode on",
                    str(image),
                    "-x",
                    str(script),
                ],
                output,
                progress_marker=marker[:-1] + "_PROGRESS=",
            )
            evidence.update(stdout=stdout, stderr=stderr)
            if code:
                raise RuntimeError("GDB observation failed: " + stderr)
            observed = _parse_completion(stdout, marker, config, request.values)
            evidence.update(
                observation=observed,
                completion_observed=True,
                measurement_mode="real_firmware",
            )
            if identity["sha256"] != file_identity(image)["sha256"]:
                raise RuntimeError("Firmware snapshot changed")
            for record in evidence["tools"].values():
                if file_identity(record["identity"]["path"]) != record["identity"]:
                    raise RuntimeError("Runtime executable changed during execution")
            return Result("triggered" if observed["triggered"] else "passed", evidence)
        except BaseException as exc:
            primary = exc
            exc.backend_evidence = evidence
            raise
        finally:
            evidence["process_logs"] = [
                {
                    "pid": p.pid,
                    "stdout": out.text() if out else "",
                    "stderr": err.text() if err else "",
                }
                for p, out, err, job in processes.children
            ]
            cleaned = finish(processes, primary, evidence)
            evidence["cleanup"] = processes.cleanup
            evidence["cleanup_verified"] = cleaned


def _icarus_status(stdout, returncode):
    """One exact result line, accepting native LF or CRLF transport endings."""
    matches = re.findall(r"^FIRMAVEX_TEST_RESULT=(PASS|FAIL)\r?$", stdout, re.MULTILINE)
    if len(matches) != 1 or returncode != 0:
        return "invalid_output"
    return "passed" if matches[0] == "PASS" else "triggered"


class IcarusBackend:
    profile = profiles["verilog-icarus"]

    def execute(self, request, output, cancel):
        require_native_candidate(self.profile.id)
        source = output / "testbench.v"
        identity = snapshot(request.source, source, request.limits.artifact_bytes)
        from .inputs import verilog
        verilog(source.read_text(encoding="ascii"))
        from .tools import find_many
        selections = find_many(("iverilog", "vvp"))
        processes = Processes(cancel, request.limits)
        primary = None
        evidence = {
            "source": identity,
            "backend": self.profile.id,
            "measurement_mode": "unverified",
            "tools": {},
            "artifacts": [],
        }
        try:
            compiler, simulator = selections["iverilog"], selections["vvp"]
            for name, path in (("compiler", compiler), ("simulator", simulator)):
                code, stdout, stderr = processes.run([path, "-V"], output)
                if code:
                    raise RuntimeError("Simulator capability probe failed")
                evidence["tools"][name] = {
                    "identity": file_identity(path),
                    "version": (stdout or stderr).splitlines()[0],
                }
            code, stdout, stderr = processes.run(
                [
                    compiler,
                    "-g2012",
                    "-s",
                    "testbench",
                    "-o",
                    str(output / "simulation.vvp"),
                    str(source),
                ],
                output,
            )
            evidence["compile_stdout"], evidence["compile_stderr"] = stdout, stderr
            if code:
                return Result("invalid_input", evidence)
            code, stdout, stderr = processes.run(
                [simulator, "-i", str(output / "simulation.vvp")], output,
                output_stage="simulation_output",
            )
            evidence.update(
                stdout=stdout,
                stderr=stderr,
                returncode=code,
                measurement_mode="real_simulation",
            )
            status = _icarus_status(stdout, code)
            if status == "invalid_output":
                return Result(status, evidence)
            inspect_artifacts(output, request.limits.artifact_bytes)
            for record in evidence["tools"].values():
                if file_identity(record["identity"]["path"]) != record["identity"]:
                    raise RuntimeError("Runtime executable changed during simulation")
            for path in output.glob("*.vcd"):
                if (
                    path.is_symlink()
                    or path.stat().st_size > request.limits.artifact_bytes
                ):
                    raise RuntimeError("Invalid waveform artifact")
                evidence["artifacts"].append({"name": path.name, **file_identity(path)})
            return Result(status, evidence)
        except BaseException as exc:
            primary = exc
            exc.backend_evidence = evidence
            raise
        finally:
            evidence["process_logs"] = [
                {
                    "pid": p.pid,
                    "stdout": out.text() if out else "",
                    "stderr": err.text() if err else "",
                }
                for p, out, err, job in processes.children
            ]
            cleaned = finish(processes, primary, evidence)
            evidence["cleanup"], evidence["cleanup_verified"] = (
                processes.cleanup,
                cleaned,
            )
