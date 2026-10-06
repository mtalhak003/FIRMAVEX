"""Versioned corpus descriptors and builds; no evaluation oracle is loaded."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from src.firmavex.compiler.cortex_m import SUPPORT_DIR, build_cortex_m_firmware


@dataclass(frozen=True)
class Benchmark:
    name: str
    corpus_version: int
    source: Path
    input_symbol: str
    failure_symbol: str
    breakpoint: str
    input_min: int
    input_max: int


def load_benchmarks() -> tuple[Benchmark, ...]:
    """Read only build/instrumentation metadata, never test ground truth."""
    manifest = json.loads((SUPPORT_DIR / "corpus/manifest.json").read_text())
    interface = manifest["interface"]
    return tuple(
        Benchmark(
            name=entry["name"],
            corpus_version=manifest["version"],
            source=SUPPORT_DIR / "corpus" / entry["source"],
            input_symbol=interface["input_symbol"],
            failure_symbol=interface["failure_symbol"],
            breakpoint=interface["breakpoint"],
            input_min=interface["input_domain"][0],
            input_max=interface["input_domain"][1],
        )
        for entry in manifest["benchmarks"]
    )


def build_benchmark(benchmark: Benchmark, output_file: str | Path) -> dict:
    return build_cortex_m_firmware(
        benchmark.source,
        output_file,
        extra_sources=(SUPPORT_DIR / "corpus/harness.c",),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Cortex-M3 corpus v1")
    parser.add_argument("--output-dir", type=Path, default=Path("build/cortex_m/v1"))
    args = parser.parse_args()
    for benchmark in load_benchmarks():
        result = build_benchmark(benchmark, args.output_dir / f"{benchmark.name}.elf")
        if not result["success"]:
            parser.exit(1, result["stderr"] + "\n")
        print(result["output_file"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
