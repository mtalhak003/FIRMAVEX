import json
from dataclasses import FrozenInstanceError, asdict, replace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.api import ExperimentRecord, ExperimentSpec
from src.firmavex.strategies.api import InvalidOutputReason, StrategyMetadata, StrategyRun, TerminationReason
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.random import RandomStrategy
from src.firmavex.strategies.runner import run_strategy


ID = "b-3874d6a4a92f46758d73854abf0a08df"


def make_record(strategy=None, observations=None, budget=3):
    strategy = EnumerativeStrategy() if strategy is None else strategy
    metadata = strategy.metadata
    executor = Mock(side_effect=[Observation(True), Observation(True, True)] if observations is None else observations)
    owner = EvaluationSession(ID, InputSpace(2, 0, 2), budget, metadata.name, executor, random_seed=metadata.seed)
    declaration = ExperimentSpec(ID, metadata, budget)
    description = owner.describe()
    run = run_strategy(strategy, owner.strategy_api())
    return ExperimentRecord(declaration, description, run), owner


def test_record_retains_authoritative_objects_and_all_evaluator_fields(monkeypatch):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", Mock(side_effect=[100.0, 105.0]))
    record, owner = make_record()
    result = record.run.evaluation
    assert result == owner.result()
    assert record.run.strategy == record.declaration.strategy
    assert record.description == owner.describe()
    assert result.benchmark_id == ID and result.strategy_id == "enumerative"
    assert result.execution_budget == record.declaration.execution_budget == 3
    assert result.attempted_executions == result.successful_executions == 2
    assert result.infrastructure_failures == 0 and result.failure_triggering_executions == 1
    assert result.failure_found and not result.aborted
    assert result.first_failure_execution == 2 and result.time_to_first_failure_seconds == 5.0
    assert result.budget_remaining == 1 and not result.budget_exhausted
    assert record.run.termination is TerminationReason.FAILURE_DISCOVERED
    serialized = record.to_dict()
    assert serialized["run"]["evaluation"] == asdict(result)
    assert serialized["declaration"]["strategy"] == serialized["run"]["strategy"] == {
        "name": "enumerative", "configuration": {}, "seed": None,
    }
    assert serialized["description"]["input_space"] == {"width": 2, "minimum": 0, "maximum": 2}


def test_record_construction_preserves_existing_run_and_result_identity():
    record, _ = make_record()
    second = ExperimentRecord(record.declaration, record.description, record.run)
    assert second.declaration is record.declaration
    assert second.description is record.description
    assert second.run is record.run
    assert second.run.evaluation is record.run.evaluation


def test_record_and_nested_public_records_are_immutable():
    record, _ = make_record()
    with pytest.raises(FrozenInstanceError):
        record.run = None
    with pytest.raises(FrozenInstanceError):
        record.run.evaluation.attempted_executions = 999
    with pytest.raises(FrozenInstanceError):
        record.description.input_space.width = 999
    with pytest.raises(FrozenInstanceError):
        record.declaration.execution_budget = 999


@pytest.mark.parametrize("seed", [0, -7, 42, 2 ** 130])
def test_json_preserves_exact_integer_seed(seed):
    record, _ = make_record(RandomStrategy(seed), [Observation(True)], budget=1)
    data = json.loads(record.to_json())
    for metadata in (data["declaration"]["strategy"], data["run"]["strategy"]):
        assert metadata["name"] == "random" and metadata["configuration"] == {}
        assert type(metadata["seed"]) is int and metadata["seed"] == seed
    assert data["run"]["evaluation"]["random_seed"] == seed


def test_equivalent_records_serialize_equivalently_and_round_trip_as_data():
    first, _ = make_record(observations=[Observation(True)], budget=1)
    second = ExperimentRecord(replace(first.declaration), replace(first.description), replace(first.run))
    assert first == second
    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json()) == first.to_dict()
    assert first.to_json() == json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert set(first.to_dict()) == {"schema_version", "declaration", "description", "run"}
    assert first.to_dict()["schema_version"] == 1


def test_serialization_nulls_and_enum_values_are_explicit():
    record, _ = make_record(observations=[], budget=0)
    data = json.loads(record.to_json())
    assert data["declaration"]["strategy"]["seed"] is None
    assert data["run"]["evaluation"]["first_failure_execution"] is None
    assert data["run"]["evaluation"]["time_to_first_failure_seconds"] is None
    assert data["run"]["invalid_output"] is None
    assert data["run"]["termination"] == "budget_exhausted"


@pytest.mark.parametrize("reason", list(TerminationReason))
def test_serialization_preserves_termination_and_validation_enums(reason):
    record, _ = make_record(observations=[], budget=0)
    invalid = InvalidOutputReason.WIDTH if reason is TerminationReason.INVALID_OUTPUT else None
    changed = ExperimentRecord(record.declaration, record.description, replace(record.run, termination=reason, invalid_output=invalid))
    data = changed.to_dict()["run"]
    assert type(data["termination"]) is str and data["termination"] == reason.value
    assert data["invalid_output"] == (None if invalid is None else "candidate_width")


def test_mutating_serialized_data_cannot_mutate_record():
    record, _ = make_record()
    data = record.to_dict()
    data["run"]["evaluation"]["attempted_executions"] = 999
    data["run"]["strategy"]["configuration"]["injected"] = "mutable"
    data["description"]["input_space"]["width"] = 999
    assert record.run.evaluation.attempted_executions == 2
    assert record.run.strategy.configuration == ()
    assert record.description.input_space.width == 2


def test_infrastructure_abort_is_preserved_without_private_diagnostics():
    secret = "private source.c /firmware/image.elf GDB stderr held_out oracle"
    record, owner = make_record(observations=[Observation(False, True, stdout=secret, stderr=secret)])
    result = record.run.evaluation
    assert result.aborted and not result.failure_found
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0
    assert record.run.termination is TerminationReason.SESSION_ABORTED
    assert owner.diagnostics()[0]["stderr"] == secret
    for forbidden in ("source.c", "image.elf", "GDB", "stderr", "held_out", "oracle", "0x"):
        assert forbidden not in record.to_json()


@pytest.mark.parametrize("change", [
    {"benchmark_id": "b-" + "0" * 32}, {"execution_budget": 4},
    {"strategy_id": "random"}, {"random_seed": 42},
])
def test_record_rejects_mismatched_evaluator_identity_budget_or_seed(change):
    record, _ = make_record()
    changed = replace(record.run, evaluation=replace(record.run.evaluation, **change))
    with pytest.raises(ValueError, match="differs from the experiment declaration"):
        ExperimentRecord(record.declaration, record.description, changed)


def test_record_rejects_mismatched_actual_strategy_metadata():
    record, _ = make_record()
    changed = replace(record.run, strategy=StrategyMetadata("random", seed=42))
    with pytest.raises(ValueError, match="Actual strategy metadata"):
        ExperimentRecord(record.declaration, record.description, changed)


def test_record_rejects_mismatched_public_description():
    record, _ = make_record()
    with pytest.raises(ValueError, match="Public session description"):
        ExperimentRecord(record.declaration, replace(record.description, execution_budget=999), record.run)


def test_record_rejects_live_or_mutable_outcome_objects():
    record, _ = make_record()
    with pytest.raises(ValueError, match="immutable specification"):
        ExperimentRecord(record.declaration, record.description, {})
    changed = StrategyRun(Mock(), record.run.strategy, record.run.termination)
    with pytest.raises(ValueError, match="evaluator ExperimentResult"):
        ExperimentRecord(record.declaration, record.description, changed)


def test_record_rejects_live_objects_inside_public_description():
    record, _ = make_record()
    with pytest.raises(ValueError, match="immutable public benchmark description"):
        ExperimentRecord(record.declaration, replace(record.description, input_space=Mock()), record.run)


def test_json_has_no_nonfinite_or_repr_fallback():
    record, _ = make_record()
    changed = replace(record.run, evaluation=replace(record.run.evaluation, time_to_first_failure_seconds=float("nan")))
    invalid = ExperimentRecord(record.declaration, record.description, changed)
    with pytest.raises(ValueError):
        invalid.to_json()
