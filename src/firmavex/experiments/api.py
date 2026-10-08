"""Single-experiment declarations and records, without independent metrics."""

import json
import re
from dataclasses import asdict, dataclass

from src.firmavex.evaluation.api import ExperimentResult, ExperimentSpec as BenchmarkDescription, InputSpace
from src.firmavex.strategies.api import StrategyMetadata, StrategyRun
from src.firmavex.strategies.guided import guided_metadata


def _validate_strategy(metadata: StrategyMetadata) -> None:
    if type(metadata) is not StrategyMetadata:
        raise ValueError("Strategy selection must be a StrategyMetadata record.")
    if metadata.name == "guided":
        if type(metadata.seed) is not int:
            raise ValueError("Choose the enumerative or random baseline, or declare guided with an explicit integer seed and complete configuration.")
        try:
            canonical = guided_metadata(metadata.seed, **dict(metadata.configuration))
        except TypeError as exc:
            raise ValueError("Guided configuration requires exactly archive_size and mutation_attempts.") from exc
        if metadata != canonical:
            raise ValueError("Guided configuration must declare archive_size and mutation_attempts completely.")
        return
    if metadata.configuration:
        raise ValueError("Frozen baselines accept only empty configuration.")
    if metadata.name == "enumerative":
        if metadata.seed is not None:
            raise ValueError("Enumerative experiments must not declare a seed.")
    elif metadata.name == "random":
        if type(metadata.seed) is not int:
            raise ValueError("Random experiments require an explicit integer seed.")
    else:
        raise ValueError("Choose the enumerative or random baseline, or the guided strategy.")


@dataclass(frozen=True)
class ExperimentSpec:
    """Declared intent; distinct from evaluation.api's public description."""

    benchmark_id: str
    strategy: StrategyMetadata
    execution_budget: int

    def __post_init__(self) -> None:
        if type(self.benchmark_id) is not str or re.fullmatch(r"b-[0-9a-f]{32}", self.benchmark_id) is None:
            raise ValueError("Benchmark ID must be an opaque b- identifier.")
        _validate_strategy(self.strategy)
        # Declaration validation only; the evaluator alone enforces admission.
        if type(self.execution_budget) is not int or self.execution_budget < 0:
            raise ValueError("Execution budget must be a nonnegative integer.")


def _check_identity(spec: ExperimentSpec, result: ExperimentResult) -> None:
    if type(result) is not ExperimentResult:
        raise ValueError("Experiment outcome must be an evaluator ExperimentResult.")
    declared = (spec.benchmark_id, spec.execution_budget, spec.strategy.name, spec.strategy.seed)
    actual = (result.benchmark_id, result.execution_budget, result.strategy_id, result.random_seed)
    if actual != declared:
        raise ValueError("Evaluator identity, budget, or seed differs from the experiment declaration.")


def _check_description(spec: ExperimentSpec, description: BenchmarkDescription) -> None:
    if type(description) is not BenchmarkDescription or type(description.input_space) is not InputSpace:
        raise ValueError("Experiment sessions must expose the immutable public benchmark description.")
    if (description.benchmark_id, description.execution_budget) != (spec.benchmark_id, spec.execution_budget):
        raise ValueError("Public session description differs from the experiment declaration.")


def _metadata_dict(metadata: StrategyMetadata) -> dict:
    return {"name": metadata.name, "configuration": dict(metadata.configuration), "seed": metadata.seed}


@dataclass(frozen=True)
class ExperimentRecord:
    """Keep declared intent and the actual StrategyRun; never recount trials."""

    declaration: ExperimentSpec
    description: BenchmarkDescription
    run: StrategyRun

    def __post_init__(self) -> None:
        if type(self.declaration) is not ExperimentSpec or type(self.run) is not StrategyRun:
            raise ValueError("Experiment records require immutable specification and strategy-run records.")
        _check_description(self.declaration, self.description)
        if self.run.strategy != self.declaration.strategy:
            raise ValueError("Actual strategy metadata differs from the experiment declaration.")
        _check_identity(self.declaration, self.run.evaluation)

    def to_dict(self) -> dict:
        """Fresh JSON-compatible data; no paths, diagnostics, or object reprs."""
        return {
            "schema_version": 1,
            "declaration": {
                "benchmark_id": self.declaration.benchmark_id,
                "strategy": _metadata_dict(self.declaration.strategy),
                "execution_budget": self.declaration.execution_budget,
            },
            "description": asdict(self.description),
            "run": {
                "strategy": _metadata_dict(self.run.strategy),
                "evaluation": asdict(self.run.evaluation),
                "termination": self.run.termination.value,
                "invalid_output": None if self.run.invalid_output is None else self.run.invalid_output.value,
            },
        }

    def to_json(self) -> str:
        """Stable keys/format and exact integer literals; no automatic writes."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
