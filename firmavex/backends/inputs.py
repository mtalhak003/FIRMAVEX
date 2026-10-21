"""Shared static input restrictions; these never establish runtime behavior."""
import io
import re
from elftools.elf.elffile import ELFFile


def rv32(data):
    elf = ELFFile(io.BytesIO(data))
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


def verilog(text):
    # A single self-contained testbench is the supported initial boundary.
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
