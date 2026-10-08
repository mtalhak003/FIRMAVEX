"""Immutable campaign declarations, preserving the frozen baseline preset."""

import json
from dataclasses import dataclass

from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.strategies.api import StrategyMetadata
from src.firmavex.strategies.guided import guided_metadata


BASELINE_STRATEGIES = ("enumerative", "random")
SUPPORTED_STRATEGIES = (*BASELINE_STRATEGIES, "guided")
STANDARD_RANDOM_SEEDS = tuple(range(10))


def _json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class EvaluationProtocol:
    """Administrative intent; partition information is never a strategy input.

    The standard preset includes both baselines and seeds 0..9. Explicit custom
    declarations may select a canonical subset and a different seed tuple.
    Guided runs require their own explicit schedule and use the strategy's
    declared default configuration, without changing the frozen standard.
    """

    benchmark_ids: tuple[str, ...]
    execution_budget: int
    partition: str
    random_seeds: tuple[int, ...] = STANDARD_RANDOM_SEEDS
    strategies: tuple[str, ...] = BASELINE_STRATEGIES
    guided_seeds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.benchmark_ids) is not tuple or not self.benchmark_ids:
            raise ValueError("Benchmark IDs must be a nonempty ordered immutable tuple.")
        if type(self.execution_budget) is not int or self.execution_budget <= 0:
            raise ValueError("Campaign execution budget must be a positive integer.")
        if type(self.partition) is not str or self.partition not in {"development", "held_out"}:
            raise ValueError("Campaign partition must be development or held_out.")
        if type(self.strategies) is not tuple or not self.strategies:
            raise ValueError("Campaign strategies must be a nonempty immutable tuple.")
        if any(type(name) is not str or name not in SUPPORTED_STRATEGIES for name in self.strategies):
            raise ValueError("Supported strategies are enumerative, random, and guided.")
        if self.strategies != tuple(name for name in SUPPORTED_STRATEGIES if name in self.strategies):
            raise ValueError("Strategies must be unique and ordered enumerative before random before guided.")
        if type(self.random_seeds) is not tuple or any(type(seed) is not int for seed in self.random_seeds):
            raise ValueError("Random seeds must be an immutable tuple of integers.")
        if len(set(self.random_seeds)) != len(self.random_seeds):
            raise ValueError("Random seeds must be unique; duplicate seeds are invalid.")
        if "random" in self.strategies and not self.random_seeds:
            raise ValueError("Random campaigns require a nonempty seed schedule.")
        if "random" not in self.strategies and self.random_seeds:
            raise ValueError("A campaign without random must declare an empty seed schedule.")
        if type(self.guided_seeds) is not tuple or any(type(seed) is not int for seed in self.guided_seeds):
            raise ValueError("Guided seeds must be an immutable tuple of integers.")
        if len(set(self.guided_seeds)) != len(self.guided_seeds):
            raise ValueError("Guided seeds must be unique; duplicate seeds are invalid.")
        if "guided" in self.strategies and not self.guided_seeds:
            raise ValueError("Guided campaigns require a nonempty explicit seed schedule.")
        if "guided" not in self.strategies and self.guided_seeds:
            raise ValueError("A campaign without guided must declare an empty guided seed schedule.")
        # Reuse the existing single-run declaration's opaque-ID validation.
        for identifier in self.benchmark_ids:
            ExperimentSpec(identifier, StrategyMetadata("enumerative"), self.execution_budget)
        if len(set(self.benchmark_ids)) != len(self.benchmark_ids):
            raise ValueError("Duplicate benchmark IDs are invalid.")

    @property
    def is_standard(self) -> bool:
        return self.strategies == BASELINE_STRATEGIES and self.random_seeds == STANDARD_RANDOM_SEEDS

    def expand(self) -> tuple[ExperimentSpec, ...]:
        """Validate/materialize the complete plan without dispatching firmware."""
        return tuple(
            ExperimentSpec(
                identifier,
                guided_metadata(seed) if name == "guided" else StrategyMetadata(name, seed=seed),
                self.execution_budget,
            )
            for identifier in self.benchmark_ids
            for name in self.strategies
            for seed in (
                (None,) if name == "enumerative"
                else self.random_seeds if name == "random"
                else self.guided_seeds
            )
        )

    def to_dict(self) -> dict:
        data = {
            "schema_version": 1,
            "kind": "standard_baseline_v1" if self.is_standard else "custom_baseline_v1",
            "benchmark_ids": list(self.benchmark_ids),
            "execution_budget": self.execution_budget,
            "partition": self.partition,
            "strategies": list(self.strategies),
            "random_seeds": list(self.random_seeds),
            "run_order": "benchmark_then_enumerative_then_random_seed",
            "infrastructure_abort_policy": "continue_independent_experiments",
        }
        if "guided" in self.strategies:
            data.update(
                kind="custom_search_v1", guided_seeds=list(self.guided_seeds),
                run_order="benchmark_then_enumerative_then_random_seed_then_guided_seed",
            )
        return data

    def to_json(self) -> str:
        return _json(self.to_dict())

    def plan_to_dict(self) -> dict:
        """A serialized expansion of existing specs, without a new plan type."""
        return {
            "schema_version": 1,
            "protocol": self.to_dict(),
            "experiments": [
                {
                    "benchmark_id": spec.benchmark_id,
                    "strategy": {"name": spec.strategy.name, "configuration": dict(spec.strategy.configuration), "seed": spec.strategy.seed},
                    "execution_budget": spec.execution_budget,
                }
                for spec in self.expand()
            ],
        }

    def plan_to_json(self) -> str:
        return _json(self.plan_to_dict())


def standard_baseline_protocol(
    *, benchmark_ids: tuple[str, ...], execution_budget: int, partition: str,
) -> EvaluationProtocol:
    """The pre-guided-search standard: enum once and exactly random seeds 0..9."""
    return EvaluationProtocol(
        benchmark_ids, execution_budget, partition,
        random_seeds=STANDARD_RANDOM_SEEDS, strategies=BASELINE_STRATEGIES,
    )
