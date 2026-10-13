"""Concrete adapters. New tools are executed only on qualified POSIX paths."""

import json
import os
from pathlib import Path
import re
import shutil
import socket
import time
import uuid
from types import SimpleNamespace
from elftools.elf.elffile import ELFFile
from firmavex.product.tools import file_identity
from firmavex.product.runtime import _allocate_port, _debugger_script, _parse_completion
from .api import Result, profiles
from .process import Processes


def tool(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Missing runtime dependency: {name}")
    return str(Path(path).resolve())


def snapshot(source, destination, maximum):
    source = source.expanduser().resolve(strict=True)
    if not source.is_file() or source.stat().st_size > maximum:
        raise ValueError("Input must be a bounded regular file")
    before = file_identity(source)
    shutil.copyfile(source, destination)
    after = file_identity(source)
    copied = file_identity(destination)
    if before != after or before["sha256"] != copied["sha256"]:
        raise RuntimeError("Input changed during snapshot")
    return copied


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
        result = services.run_project(
            request.source, output / "arm-run", cancel_event=cancel
        )
        return Result(
            result.get("status", result.get("classification", "completed")),
            {"legacy_result": result, "adapter": "unchanged product services"},
        )


class RiscvBackend:
    profile = profiles["riscv32-virt"]

    def execute(self, request, output, cancel):
        if os.name != "posix":
            raise RuntimeError("RISC-V native Windows execution is not qualified")
        image = output / "firmware.elf"
        identity = snapshot(request.source, image, request.limits.artifact_bytes)
        with image.open("rb") as stream:
            elf = ELFFile(stream)
            if (
                elf.elfclass != 32
                or not elf.little_endian
                or elf["e_machine"] != "EM_RISCV"
                or elf["e_type"] != "ET_EXEC"
            ):
                raise ValueError(
                    "Expected static ELF32 little-endian RISC-V executable"
                )
            segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
            if not segments or not 0x80000000 <= elf["e_entry"] < 0x88000000:
                raise ValueError("ELF entry outside virt RAM")
            if any(
                s["p_vaddr"] < 0x80000000
                or s["p_vaddr"] + s["p_memsz"] > 0x88000000
                or s["p_filesz"] > s["p_memsz"]
                for s in segments
            ):
                raise ValueError("ELF load segments outside supported memory map")
            symbols = elf.get_section_by_name(".symtab")
            for name in (
                "input_a",
                "input_b",
                "failure_flag",
                "input_ready",
                "benchmark_complete",
            ):
                found = symbols.get_symbol_by_name(name) if symbols else None
                if not found or len(found) != 1 or found[0]["st_shndx"] == "SHN_UNDEF":
                    raise ValueError(f"Required symbol missing/ambiguous: {name}")
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
            qemu, gdb = tool("qemu-system-riscv32"), tool("gdb-multiarch")
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
            script.write_text(_debugger_script(config, request.values, port, marker))
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


class IcarusBackend:
    profile = profiles["verilog-icarus"]

    def execute(self, request, output, cancel):
        source = output / "testbench.v"
        identity = snapshot(request.source, source, request.limits.artifact_bytes)
        # A single self-contained testbench is the supported initial boundary.
        text = source.read_text(encoding="ascii")
        tasks = re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", text)
        if set(tasks) - {"display", "finish", "dumpfile", "dumpvars", "time"}:
            raise ValueError("Unsupported simulator system task")
        dumps = re.findall(r"\$dumpfile\s*\((.*?)\)", text, re.S)
        if any(value.strip() != '"waveform.vcd"' for value in dumps):
            raise ValueError("Waveform output must be the owned waveform.vcd")
        if re.search(r"`\s*include|\$\s*(system|fopen|readmemh|readmemb)\b", text):
            raise ValueError(
                "External file/system operations are unsupported in this profile"
            )
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
            compiler, simulator = tool("iverilog"), tool("vvp")
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
                [simulator, str(output / "simulation.vvp")], output
            )
            evidence.update(
                stdout=stdout,
                stderr=stderr,
                returncode=code,
                measurement_mode="real_simulation",
            )
            matches = re.findall(
                r"^FIRMAVEX_TEST_RESULT=(PASS|FAIL)$", stdout, re.MULTILINE
            )
            if len(matches) != 1 or code != 0:
                return Result("invalid_output", evidence)
            if (
                sum(p.stat().st_size for p in output.iterdir() if p.is_file())
                > request.limits.artifact_bytes
            ):
                raise RuntimeError("Aggregate artifact limit exceeded")
            for path in output.glob("*.vcd"):
                if (
                    path.is_symlink()
                    or path.stat().st_size > request.limits.artifact_bytes
                ):
                    raise RuntimeError("Invalid waveform artifact")
                evidence["artifacts"].append({"name": path.name, **file_identity(path)})
            return Result("passed" if matches[0] == "PASS" else "triggered", evidence)
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
