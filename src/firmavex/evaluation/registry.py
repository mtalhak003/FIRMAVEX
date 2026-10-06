"""Evaluator-owned corpus v2 registry/build/instrumentation, without an oracle."""

import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from src.firmavex.compiler.cortex_m import SUPPORT_DIR, build_cortex_m_firmware
from src.firmavex.evaluation.api import InputSpace
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.monitor.monitor import observe_symbol


CORPUS_DIR = SUPPORT_DIR / "corpus_v2"


@dataclass(frozen=True)
class BenchmarkSpec:
    """Trusted evaluator record. Do not send this to a strategy."""

    benchmark_id: str
    name: str
    split: str
    source: Path


class BenchmarkRegistry:
    def __init__(self):
        manifest = json.loads((CORPUS_DIR / "manifest.json").read_text())
        if manifest["version"] != 2 or manifest["target"] != "mps2-an385":
            raise ValueError("Unsupported corpus version/target.")
        interface = manifest["interface"]
        self.input_space = InputSpace(interface["width"], *interface["input_domain"])
        self._input_symbol = interface["input_symbol"]
        self._failure_symbol = interface["failure_symbol"]
        self._breakpoint = interface["breakpoint"]
        self._specs = {}
        self._images: dict[str, tuple[Path, str]] = {}
        for entry in manifest["benchmarks"]:
            identifier = entry["id"]
            if re.fullmatch(r"b-[0-9a-f]{32}", identifier) is None or identifier in self._specs:
                raise ValueError("Benchmark IDs must be unique opaque identifiers.")
            source = (CORPUS_DIR / entry["source"]).resolve()
            if entry["split"] not in {"development", "held_out"} or not source.is_relative_to(CORPUS_DIR.resolve()) or not source.is_file():
                raise ValueError("Invalid corpus source/split.")
            self._specs[identifier] = BenchmarkSpec(identifier, entry["name"], entry["split"], source)

    def select(self, split: str) -> tuple[BenchmarkSpec, ...]:
        """Administrator selects a split; strategy descriptions omit split labels."""
        if split not in {"development", "held_out"}:
            raise ValueError("Choose development or held_out.")
        return tuple(item for item in self._specs.values() if item.split == split)

    def build(self, benchmark_id: str, output_file: str | Path) -> dict:
        if benchmark_id not in self._specs:
            raise ValueError("Unknown opaque benchmark ID.")
        self._images.pop(benchmark_id, None)
        result = build_cortex_m_firmware(
            self._specs[benchmark_id].source, output_file,
            extra_sources=(CORPUS_DIR / "harness.c",),
        )
        if result["success"]:
            try:
                image = Path(result["output_file"]).resolve()
                self._images[benchmark_id] = (image, hashlib.sha256(image.read_bytes()).hexdigest())
            except OSError as exc:
                result.update(success=False, return_code=-1, stderr=f"Unable to register built image: {exc}")
        return result

    def open_session(
        self, benchmark_id: str, execution_budget: int,
        strategy_id: str, *, random_seed: int | None = None,
    ) -> EvaluationSession:
        if benchmark_id not in self._specs:
            raise ValueError("Unknown opaque benchmark ID.")
        if benchmark_id not in self._images:
            raise ValueError("Benchmark must be successfully built by this registry before opening a session.")
        image, digest = self._images[benchmark_id]

        def execute(values: tuple[int, ...]) -> Observation:
            try:
                if hashlib.sha256(image.read_bytes()).hexdigest() != digest:
                    return Observation(False, stderr="Registered benchmark image changed; rebuild required.")
            except OSError as exc:
                return Observation(False, stderr=f"Registered benchmark image unavailable: {exc}")
            observed = observe_symbol(
                str(image), self._failure_symbol, self._breakpoint,
                input_values={f"{self._input_symbol}[{index}]": value for index, value in enumerate(values)},
            )
            success = observed["success"] and observed["value"] in (0, 1)
            return Observation(
                success, success and observed["value"] == 1,
                observed.get("stdout", ""), observed.get("stderr", ""),
            )

        return EvaluationSession(
            benchmark_id, self.input_space, execution_budget, strategy_id, execute,
            random_seed=random_seed,
        )
