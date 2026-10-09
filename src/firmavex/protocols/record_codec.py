"""Strict recovery decoding, separate from existing official serializers.

These checks reject contradictory durable records; they never recount trials,
repair counters, change classifications, or mutate evaluator-owned results.
"""

import math
from dataclasses import fields

from src.firmavex.evaluation.api import (
    ExperimentResult, ExperimentSpec as BenchmarkDescription, InputSpace,
)
from src.firmavex.experiments.api import ExperimentRecord, ExperimentSpec
from src.firmavex.protocols.results import validate_record
from src.firmavex.strategies.api import (
    InvalidOutputReason, StrategyMetadata, StrategyRun, TerminationReason,
)


_COUNTERS = (
    "execution_budget", "attempted_executions", "successful_executions",
    "infrastructure_failures", "failure_triggering_executions", "budget_remaining",
)
_FLAGS = ("failure_found", "budget_exhausted", "aborted")
_EVALUATION_FIELDS = frozenset(field.name for field in fields(ExperimentResult))


def _object(value, keys, name: str) -> dict:
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != set(keys):
        raise ValueError(f"{name} must contain exactly its documented JSON fields.")
    return value


def _integer(value, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an exact integer scalar.")
    return value


def _string(value, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be a string scalar.")
    return value


def _metadata(payload) -> StrategyMetadata:
    value = _object(payload, ("name", "configuration", "seed"), "Strategy metadata")
    configuration = value["configuration"]
    if type(configuration) is not dict or any(type(key) is not str for key in configuration):
        raise ValueError("Strategy configuration must be a JSON object with string keys.")
    # StrategyMetadata checks exact seed types and finite immutable scalars.
    return StrategyMetadata(value["name"], tuple(configuration.items()), value["seed"])


def _validate_metadata(metadata: StrategyMetadata) -> None:
    if type(metadata) is not StrategyMetadata:
        raise ValueError("Durable strategy metadata must be a canonical immutable record.")
    recreated = StrategyMetadata(metadata.name, metadata.configuration, metadata.seed)
    if recreated != metadata:
        raise ValueError("Durable strategy metadata must have canonical configuration ordering.")


def _validate_spec(spec: ExperimentSpec) -> None:
    if type(spec) is not ExperimentSpec:
        raise ValueError("Durable records require a canonical ExperimentSpec.")
    _validate_metadata(spec.strategy)
    # Revalidate even deliberately forged dataclasses without changing them.
    ExperimentSpec(spec.benchmark_id, spec.strategy, spec.execution_budget)


def validate_evaluation(spec: ExperimentSpec, result: ExperimentResult) -> None:
    """Check a final or partial authoritative ledger without changing it."""
    _validate_spec(spec)
    if type(result) is not ExperimentResult:
        raise ValueError("Durable evaluation must be a canonical ExperimentResult.")
    for name in ("benchmark_id", "strategy_id"):
        _string(getattr(result, name), f"Evaluator {name}")
    for name in _COUNTERS:
        if _integer(getattr(result, name), f"Evaluator {name}") < 0:
            raise ValueError(f"Evaluator {name} cannot be negative.")
    for name in _FLAGS:
        if type(getattr(result, name)) is not bool:
            raise ValueError(f"Evaluator {name} must be an exact boolean scalar.")
    for name in ("first_failure_execution", "random_seed"):
        value = getattr(result, name)
        if value is not None:
            _integer(value, f"Evaluator {name}")
    if result.reproducibility is not None and type(result.reproducibility) is not bool:
        raise ValueError("Evaluator reproducibility must be a boolean or None.")
    if (result.benchmark_id, result.execution_budget, result.strategy_id, result.random_seed) != (
        spec.benchmark_id, spec.execution_budget, spec.strategy.name, spec.strategy.seed,
    ):
        raise ValueError("Evaluator identity, budget, or seed differs from the durable declaration.")
    if result.attempted_executions > result.execution_budget:
        raise ValueError("Evaluator attempts exceed the declared execution budget.")
    if result.attempted_executions != result.successful_executions + result.infrastructure_failures:
        raise ValueError("Evaluator attempts must equal successful executions plus infrastructure failures.")
    if result.budget_remaining != result.execution_budget - result.attempted_executions:
        raise ValueError("Evaluator remaining budget contradicts attempted executions.")
    if result.budget_exhausted != (result.budget_remaining == 0):
        raise ValueError("Evaluator budget-exhausted flag contradicts remaining budget.")
    if result.infrastructure_failures > 1 or result.aborted != (result.infrastructure_failures > 0):
        raise ValueError("Evaluator abort state contradicts the serial infrastructure-failure ledger.")
    if result.failure_triggering_executions > result.successful_executions:
        raise ValueError("Evaluator triggers exceed successful executions.")
    if result.failure_found != (result.failure_triggering_executions > 0):
        raise ValueError("Evaluator discovery flag contradicts triggering executions.")
    timing = result.time_to_first_failure_seconds
    if result.failure_found:
        if (
            result.first_failure_execution is None
            or not 1 <= result.first_failure_execution <= result.successful_executions
        ):
            raise ValueError("Evaluator discovery requires an index within successful executions.")
        if result.failure_triggering_executions > result.successful_executions - result.first_failure_execution + 1:
            raise ValueError("Evaluator trigger count contradicts its first-discovery index.")
        if (
            type(timing) not in (int, float) or timing < 0
            or (type(timing) is float and not math.isfinite(timing))
        ):
            raise ValueError("Evaluator discovery timing must be finite and nonnegative.")
    elif result.first_failure_execution is not None or timing is not None:
        raise ValueError("An undiscovered evaluation must not contain first-discovery measurements.")


def decode_evaluation(payload, spec: ExperimentSpec) -> ExperimentResult:
    """Decode official evaluator fields, including interrupted partial ledgers."""
    value = _object(payload, _EVALUATION_FIELDS, "Evaluator result")
    result = ExperimentResult(**value)
    validate_evaluation(spec, result)
    return result


def validate_durable_record(
    spec: ExperimentSpec, record: ExperimentRecord, expected_space: InputSpace | None = None,
) -> InputSpace:
    """Validate a completed durable record while retaining its actual objects."""
    _validate_spec(spec)
    space = validate_record(spec, record, expected_space)
    if space.width < 1 or not 0 <= space.minimum <= space.maximum <= 0xFFFFFFFF:
        raise ValueError("Durable public InputSpace is outside the uint32 domain.")
    _validate_metadata(record.declaration.strategy)
    _validate_metadata(record.run.strategy)
    result = record.run.evaluation
    validate_evaluation(spec, result)
    reason = record.run.termination
    invalid = record.run.invalid_output
    if (reason is TerminationReason.INVALID_OUTPUT) != (invalid is not None):
        raise ValueError("Durable invalid-output classification requires exactly one invalid-output reason.")
    if result.aborted:
        consistent = reason is TerminationReason.SESSION_ABORTED
    elif result.failure_found:
        consistent = reason is TerminationReason.FAILURE_DISCOVERED
    elif result.budget_exhausted:
        consistent = reason is TerminationReason.BUDGET_EXHAUSTED
    else:
        consistent = reason in (TerminationReason.STRATEGY_STOPPED, TerminationReason.INVALID_OUTPUT)
    if not consistent:
        raise ValueError("Durable termination contradicts authoritative evaluator state.")
    return space


def decode_record(
    payload, spec: ExperimentSpec, expected_space: InputSpace | None = None,
) -> ExperimentRecord:
    """Decode unchanged official ExperimentRecord JSON, rejecting extra data."""
    value = _object(payload, ("schema_version", "declaration", "description", "run"), "Experiment record")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported ExperimentRecord schema version.")
    declaration = _object(value["declaration"], ("benchmark_id", "strategy", "execution_budget"), "Declaration")
    declared = ExperimentSpec(
        declaration["benchmark_id"], _metadata(declaration["strategy"]), declaration["execution_budget"],
    )
    description = _object(value["description"], ("benchmark_id", "input_space", "execution_budget"), "Description")
    space = _object(description["input_space"], ("width", "minimum", "maximum"), "Input space")
    public_description = BenchmarkDescription(
        _string(description["benchmark_id"], "Description benchmark_id"), InputSpace(**space),
        _integer(description["execution_budget"], "Description execution_budget"),
    )
    run = _object(value["run"], ("strategy", "evaluation", "termination", "invalid_output"), "Strategy run")
    termination_text = _string(run["termination"], "Termination")
    invalid_text = run["invalid_output"]
    if invalid_text is not None:
        _string(invalid_text, "Invalid-output reason")
    try:
        termination = TerminationReason(termination_text)
        invalid = None if invalid_text is None else InvalidOutputReason(invalid_text)
    except ValueError as exc:
        raise ValueError("Unsupported durable termination or invalid-output classification.") from exc
    record = ExperimentRecord(
        declared, public_description,
        StrategyRun(decode_evaluation(run["evaluation"], spec), _metadata(run["strategy"]), termination, invalid),
    )
    validate_durable_record(spec, record, expected_space)
    if record.to_dict() != value:
        raise ValueError("Durable ExperimentRecord does not round-trip through the official schema.")
    return record
