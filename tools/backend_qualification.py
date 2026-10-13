"""Bounded real-tool qualification; separate from every research campaign."""

import argparse
import hashlib
import json
import platform
from pathlib import Path
import statistics
import subprocess
import time
from firmavex.backends import Request, execute
from firmavex.backends.examples import prepare
from firmavex.backends.report import reproduce, export


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    prepare("riscv32-virt", root / "rv-build")
    prepare("verilog-icarus", root / "hdl-build")
    observations = []
    for name, profile, source, values, expected in (
        ("rv-safe", "riscv32-virt", root / "rv-build/firmware.elf", (0, 0), "passed"),
        (
            "rv-trigger",
            "riscv32-virt",
            root / "rv-build/firmware.elf",
            (2, 1),
            "triggered",
        ),
        ("hdl-pass", "verilog-icarus", root / "hdl-build/counter.v", (), "passed"),
    ):
        result = execute(Request(profile, source, values), root / name)
        if (
            result["status"] != expected
            or result["evidence"].get("cleanup_verified") is not True
        ):
            raise RuntimeError(f"Qualification failed: {name}: {result}")
        observations.append(
            {
                "name": name,
                "status": result["status"],
                "elapsed_seconds": result["evidence"]["elapsed_seconds"],
                "measurement_mode": result["evidence"]["measurement_mode"],
                "tools": result["evidence"]["tools"],
            }
        )
        export(root / name, root / (name + "-report"))
    replay = reproduce(root / "rv-trigger", root / "rv-replay")
    if not replay["outcome_matches"]:
        raise RuntimeError("Reproduction mismatch")
    # Measure Python administration only. Not a search comparison or speedup.
    samples = []
    data = bytes(1024 * 1024)
    for _ in range(5):
        start = time.perf_counter()
        for __ in range(1000):
            hashlib.sha256(data).digest()
        samples.append((time.perf_counter() - start) / 1000)
    serialization = []
    for _ in range(5):
        start = time.perf_counter()
        for __ in range(1000):
            json.dumps(observations, sort_keys=True)
        serialization.append((time.perf_counter() - start) / 1000)
    record = {
        "schema_version": 1,
        "scope": "bounded backend qualification, not research or hardware validation",
        "host": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True)
        ),
        "observations": observations,
        "reproduction_status": replay["status"],
        "administration_measurements": {
            "sha256_1MiB_median_seconds": statistics.median(samples),
            "serialize_three_observations_median_seconds": statistics.median(
                serialization
            ),
        },
    }
    (root / "qualification.json").write_text(
        json.dumps(record, sort_keys=True, indent=2)
    )
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
