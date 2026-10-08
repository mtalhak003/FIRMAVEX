"""Immutable campaign records and conditional per-benchmark summaries."""

import json
from dataclasses import asdict, dataclass, field
from statistics import median

from src.firmavex.evaluation.api import ExperimentResult, ExperimentSpec as BenchmarkDescription, InputSpace
from src.firmavex.experiments.api import ExperimentRecord, ExperimentSpec
from src.firmavex.protocols.protocol import BASELINE_STRATEGIES, EvaluationProtocol
from src.firmavex.strategies.api import InvalidOutputReason, StrategyMetadata, StrategyRun, TerminationReason


def validate_record(
    spec: ExperimentSpec, record: ExperimentRecord, expected_space: InputSpace | None = None,
) -> InputSpace:
    """Validate a returned record's declaration and public comparison domain.

    The evaluator's result and execution counters remain authoritative. This
    boundary checks identity and immutable record types, without recounting
    firmware attempts or deriving a termination reason from execution counts.
    """
    if type(spec) is not ExperimentSpec or type(record) is not ExperimentRecord:
        raise ValueError("Campaign runs require canonical ExperimentSpec and ExperimentRecord records.")
    if (
        type(record.declaration) is not ExperimentSpec
        or type(record.description) is not BenchmarkDescription
        or type(record.description.input_space) is not InputSpace
        or type(record.run) is not StrategyRun
        or type(record.run.evaluation) is not ExperimentResult
        or type(record.run.strategy) is not StrategyMetadata
        or type(record.run.termination) is not TerminationReason
        or (record.run.invalid_output is not None and type(record.run.invalid_output) is not InvalidOutputReason)
    ):
        raise ValueError("Campaign outcomes must contain canonical immutable public records.")
    if record.declaration != spec or record.run.strategy != spec.strategy:
        raise ValueError("ExperimentRecord declaration or strategy differs from the campaign plan.")
    if (record.description.benchmark_id, record.description.execution_budget) != (spec.benchmark_id, spec.execution_budget):
        raise ValueError("ExperimentRecord public description differs from the campaign plan.")
    evaluation = record.run.evaluation
    space = record.description.input_space
    if any(type(getattr(space, name)) is not int for name in ("width", "minimum", "maximum")):
        raise ValueError("Public InputSpace fields must be exact integer scalars.")
    if type(record.description.benchmark_id) is not str or type(record.description.execution_budget) is not int:
        raise ValueError("Public benchmark description fields must be canonical scalars.")
    for name in ("benchmark_id", "strategy_id"):
        if type(getattr(evaluation, name)) is not str:
            raise ValueError(f"Evaluator field {name} must be a string scalar.")
    for name in (
        "execution_budget", "attempted_executions", "successful_executions",
        "infrastructure_failures", "failure_triggering_executions", "budget_remaining",
    ):
        if type(getattr(evaluation, name)) is not int:
            raise ValueError(f"Evaluator field {name} must be an exact integer scalar.")
    for name in ("failure_found", "budget_exhausted", "aborted"):
        if type(getattr(evaluation, name)) is not bool:
            raise ValueError(f"Evaluator field {name} must be a boolean scalar.")
    if (evaluation.benchmark_id, evaluation.execution_budget, evaluation.strategy_id, evaluation.random_seed) != (
        spec.benchmark_id, spec.execution_budget, spec.strategy.name, spec.strategy.seed,
    ):
        raise ValueError("ExperimentRecord evaluator identity differs from the campaign plan.")
    eligible_discovery = (
        not evaluation.aborted
        and record.run.termination not in (TerminationReason.SESSION_ABORTED, TerminationReason.INVALID_OUTPUT)
        and evaluation.failure_found
    )
    if eligible_discovery and (type(evaluation.first_failure_execution) is not int or evaluation.first_failure_execution <= 0):
        raise ValueError("Discovered valid runs require a positive integer first-failure execution index.")
    for name in ("first_failure_execution", "random_seed"):
        if getattr(evaluation, name) is not None and type(getattr(evaluation, name)) is not int:
            raise ValueError(f"Evaluator field {name} must be an exact integer or None.")
    if evaluation.time_to_first_failure_seconds is not None and type(evaluation.time_to_first_failure_seconds) not in (int, float):
        raise ValueError("Evaluator timing must be a numeric scalar or None.")
    if evaluation.reproducibility is not None and type(evaluation.reproducibility) is not bool:
        raise ValueError("Evaluator reproducibility must be a boolean scalar or None.")
    if expected_space is not None and (type(expected_space) is not InputSpace or space != expected_space):
        raise ValueError("Comparable experiments must expose the same public InputSpace.")
    return space


@dataclass(frozen=True)
class StrategySummary:
    """One benchmark and strategy; discovery cost is conditional on discovery.

    ``seeds`` records any seeded strategy's complete declared schedule.
    ``random_seeds`` retains its original random-baseline meaning. An empty
    generic schedule on a random summary means legacy omission and is filled
    from ``random_seeds``; any nonempty schedule must match it exactly. Baseline
    serialization omits the additive generic field to preserve its schema.
    """

    benchmark_id: str
    strategy_name: str
    execution_budget: int
    planned_runs: int
    completed_records: int
    valid_runs: int
    discovered_runs: int
    non_discovered_valid_runs: int
    infrastructure_aborted_runs: int
    invalid_strategy_runs: int
    discovery_rate: float | None
    discovery_executions: tuple[int | None, ...]
    first_failure_executions: tuple[int, ...]
    minimum_first_failure_execution: int | None
    median_first_failure_execution: int | float | None
    maximum_first_failure_execution: int | None
    random_seeds: tuple[int, ...]
    seeds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for name in ("benchmark_id", "strategy_name"):
            if type(getattr(self, name)) is not str:
                raise ValueError(f"Summary field {name} must be a string scalar.")
        for name in (
            "execution_budget", "planned_runs", "completed_records", "valid_runs",
            "discovered_runs", "non_discovered_valid_runs", "infrastructure_aborted_runs", "invalid_strategy_runs",
        ):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"Summary field {name} must be an exact integer scalar.")
        for name in ("minimum_first_failure_execution", "maximum_first_failure_execution"):
            if getattr(self, name) is not None and type(getattr(self, name)) is not int:
                raise ValueError(f"Summary field {name} must be an exact integer scalar or None.")
        for name in ("median_first_failure_execution", "discovery_rate"):
            if getattr(self, name) is not None and type(getattr(self, name)) not in (int, float):
                raise ValueError(f"Summary field {name} must be a numeric scalar or None.")
        for name in ("discovery_executions", "first_failure_executions", "random_seeds", "seeds"):
            values = getattr(self, name)
            if type(values) is not tuple:
                raise ValueError("Summary samples and seed schedules must be immutable tuples.")
            for value in values:
                if name == "discovery_executions" and value is None:
                    continue
                if type(value) is not int:
                    raise ValueError("Summary sample and seed elements must be exact integers.")
                if name not in ("random_seeds", "seeds") and value <= 0:
                    raise ValueError("Summary discovery indices must be positive integers.")
        if self.strategy_name == "random":
            if not self.seeds:
                # Preserve legacy construction that supplied only random_seeds.
                object.__setattr__(self, "seeds", self.random_seeds)
            elif self.seeds != self.random_seeds:
                raise ValueError("Random summary seeds must match random_seeds in value and order.")
        elif self.random_seeds:
            raise ValueError("Only random summaries may declare random_seeds.")
        if self.strategy_name == "enumerative" and self.seeds:
            raise ValueError("Enumerative summaries must not declare seeds.")

    def to_dict(self) -> dict:
        """Fresh versioned data for this benchmark/strategy summary alone."""
        data = asdict(self)
        for name in ("discovery_executions", "first_failure_executions", "random_seeds", "seeds"):
            data[name] = list(getattr(self, name))
        if self.strategy_name in BASELINE_STRATEGIES:
            del data["seeds"]
        return {"schema_version": 1, **data}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _summarize(records: tuple[ExperimentRecord, ...]) -> StrategySummary:
    declaration = records[0].declaration
    aborted = invalid = valid = discovered = 0
    discovery_executions = []
    samples = []
    for record in records:
        run = record.run
        result = run.evaluation
        # Even an earlier trigger is ineligible if the final run was aborted.
        if result.aborted or run.termination is TerminationReason.SESSION_ABORTED:
            aborted += 1
            discovery_executions.append(None)
        elif run.termination is TerminationReason.INVALID_OUTPUT:
            invalid += 1
            discovery_executions.append(None)
        else:
            valid += 1
            if result.failure_found:
                discovered += 1
                samples.append(result.first_failure_execution)
                discovery_executions.append(result.first_failure_execution)
            else:
                discovery_executions.append(None)
    return StrategySummary(
        benchmark_id=declaration.benchmark_id,
        strategy_name=declaration.strategy.name,
        execution_budget=declaration.execution_budget,
        planned_runs=len(records),
        completed_records=len(records),
        valid_runs=valid,
        discovered_runs=discovered,
        non_discovered_valid_runs=valid - discovered,
        infrastructure_aborted_runs=aborted,
        invalid_strategy_runs=invalid,
        discovery_rate=discovered / valid if valid else None,
        discovery_executions=tuple(discovery_executions),
        first_failure_executions=tuple(samples),
        minimum_first_failure_execution=min(samples) if samples else None,
        median_first_failure_execution=median(samples) if samples else None,
        maximum_first_failure_execution=max(samples) if samples else None,
        random_seeds=tuple(record.declaration.strategy.seed for record in records) if declaration.strategy.name == "random" else (),
        seeds=tuple(record.declaration.strategy.seed for record in records if record.declaration.strategy.seed is not None),
    )


@dataclass(frozen=True)
class CampaignResult:
    """Complete ordered records, retaining actual per-run data unchanged.

    No result is manufactured for an interrupted/incomplete campaign. Overall
    counts describe run classification, not another firmware execution ledger.
    """

    protocol: EvaluationProtocol
    records: tuple[ExperimentRecord, ...]
    summaries: tuple[StrategySummary, ...] = field(init=False)

    def __post_init__(self) -> None:
        if type(self.protocol) is not EvaluationProtocol or type(self.records) is not tuple:
            raise ValueError("CampaignResult requires an immutable EvaluationProtocol and tuple of records.")
        plan = self.protocol.expand()
        if len(self.records) != len(plan):
            raise ValueError("CampaignResult requires one completed record for every planned experiment.")
        spaces = {}
        groups = {}
        for spec, record in zip(plan, self.records):
            spaces[spec.benchmark_id] = validate_record(spec, record, spaces.get(spec.benchmark_id))
            key = (spec.benchmark_id, spec.strategy.name)
            groups.setdefault(key, []).append(record)
        object.__setattr__(self, "summaries", tuple(_summarize(tuple(records)) for records in groups.values()))

    @property
    def planned_run_count(self) -> int:
        return sum(summary.planned_runs for summary in self.summaries)

    @property
    def completed_record_count(self) -> int:
        return len(self.records)

    @property
    def valid_search_run_count(self) -> int:
        return sum(summary.valid_runs for summary in self.summaries)

    @property
    def infrastructure_aborted_run_count(self) -> int:
        return sum(summary.infrastructure_aborted_runs for summary in self.summaries)

    @property
    def invalid_strategy_run_count(self) -> int:
        return sum(summary.invalid_strategy_runs for summary in self.summaries)

    def to_dict(self) -> dict:
        """Fresh machine-readable data; raw records retain timing/termination."""
        return {
            "schema_version": 1,
            "protocol": self.protocol.to_dict(),
            "records": [record.to_dict() for record in self.records],
            "counts": {
                "planned_runs": self.planned_run_count,
                "completed_records": self.completed_record_count,
                "valid_search_runs": self.valid_search_run_count,
                "infrastructure_aborted_runs": self.infrastructure_aborted_run_count,
                "invalid_strategy_runs": self.invalid_strategy_run_count,
            },
            "summaries": [summary.to_dict() for summary in self.summaries],
        }

    def to_json(self) -> str:
        """Stable keys/format, exact integer literals, and no automatic writes."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
