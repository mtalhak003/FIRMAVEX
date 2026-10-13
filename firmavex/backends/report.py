"""Read-only reporting and explicit fresh reproduction, not implicit recovery."""

import hashlib
import json
from pathlib import Path
from .api import Request, Limits
from .engine import execute, inspect_run, _write
from firmavex.product.tools import file_identity


def export(output, destination):
    record = inspect_run(output)
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    _write(destination / "result.json", record)
    evidence = record["evidence"]
    admission = evidence.get("admission", {})
    diagnostic = (
        str(evidence.get("error", "none"))[:1024].replace("`", "'").replace("\n", " ")
    )
    text = (
        "# FIRMAVEX backend result\n\n"
        f"Status: **{record['status']}**\n\n"
        f"Target: `{admission.get('profile',{}).get('id','unknown')}`\n\n"
        f"Request vector: `{admission.get('values',[])}`\n\n"
        f"Search triggering vector: `{evidence.get('triggering_input','not a search result')}`\n\n"
        f"Diagnostic: `{diagnostic}`\n\n"
        f"Elapsed wall time: {evidence.get('elapsed_seconds','unknown')} seconds.\n\n"
        f"Measurement classification: `{evidence.get('measurement_mode','legacy or unknown')}`\n\n"
        f"Cleanup verified: `{evidence.get('cleanup_verified','see legacy result')}`\n\n"
        "This is a local tool observation, not hardware validation or a security guarantee.\n"
        "HDL results express the supplied testbench assertion, not proof of design correctness.\n"
    )
    (destination / "REPORT.md").write_text(text)
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in destination.iterdir()
    }
    _write(destination / "checksums.json", hashes)
    return {"status": "exported", "destination": str(destination), "files": hashes}


def reproduce(output, destination, cancel=None):
    output = Path(output).resolve()
    record = inspect_run(output)
    if record["status"] not in {"passed", "triggered"}:
        raise ValueError("Only completed observations may be reproduced")
    evidence = record["evidence"]
    profile = evidence["admission"]["profile"]["id"]
    if profile not in {"riscv32-virt", "verilog-icarus"}:
        raise ValueError("Use the existing product reproduction command for ARM")
    name = "firmware.elf" if profile == "riscv32-virt" else "testbench.v"
    expected = evidence["firmware" if profile == "riscv32-virt" else "source"]["sha256"]
    if file_identity(output / name)["sha256"] != expected:
        raise ValueError("Saved input artifact no longer matches evidence")
    request = Request(
        profile,
        output / name,
        tuple(evidence["admission"]["values"]),
        Limits(**evidence["admission"]["limits"]),
    )
    result = execute(request, Path(destination), cancel)
    # Return actual outcome, never force agreement with the original.
    return {
        "status": result["status"],
        "original_status": record["status"],
        "outcome_matches": result["status"] == record["status"],
        "result": result,
    }
