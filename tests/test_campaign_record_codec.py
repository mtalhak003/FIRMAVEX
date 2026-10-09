"""Strict durable boundaries leave the existing official schemas untouched."""

import json
from dataclasses import asdict, replace

import pytest

from src.firmavex.evaluation.api import InputSpace, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.api import ExperimentRecord, ExperimentSpec
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.record_codec import (
    decode_evaluation, decode_record, validate_durable_record, validate_evaluation,
)
from src.firmavex.protocols.results import CampaignResult
from src.firmavex.strategies.api import (
    InvalidOutputReason, StrategyMetadata, StrategyRun, TerminationReason,
)
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.guided import GuidedStrategy
from src.firmavex.strategies.random import RandomStrategy
from src.firmavex.strategies.runner import run_strategy


ID = "b-" + "a" * 32
SPACE = InputSpace(2, 0, 2)


def make_record(kind="discovery", *, strategy=None, budget=3, space=SPACE):
    strategy = EnumerativeStrategy() if strategy is None else strategy
    observations = iter({
        "discovery": (Observation(True), Observation(True, True)),
        "abort": (Observation(True), Observation(False)),
        "safe": (),
        "invalid": (),
    }[kind])
    owner = EvaluationSession(
        ID, space, budget, strategy.metadata.name,
        lambda _: next(observations, Observation(True)), random_seed=strategy.metadata.seed,
    )
    spec = ExperimentSpec(ID, strategy.metadata, budget)
    if kind == "invalid":
        run = StrategyRun(owner.result(), spec.strategy, TerminationReason.INVALID_OUTPUT, InvalidOutputReason.WIDTH)
    else:
        run = run_strategy(strategy, owner.strategy_api())
    return ExperimentRecord(spec, owner.describe(), run), owner


def changed_payload(record, path, value):
    payload = json.loads(record.to_json())
    current = payload
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    return payload


@pytest.mark.parametrize("kind,budget,space,strategy", [
    ("discovery", 3, SPACE, None),
    ("safe", 3, SPACE, None),
    ("safe", 0, SPACE, None),
    ("safe", 3, InputSpace(1, 0, 0), None),
    ("abort", 3, SPACE, None),
    ("invalid", 3, SPACE, None),
    ("safe", 1, SPACE, RandomStrategy(-(2 ** 130))),
    ("safe", 1, SPACE, GuidedStrategy(2 ** 130, archive_size=32, mutation_attempts=8)),
])
def test_all_real_runner_classifications_round_trip_official_schema(kind, budget, space, strategy):
    record, owner = make_record(kind, strategy=strategy, budget=budget, space=space)
    before = record.to_json()
    decoded = decode_record(json.loads(before), record.declaration, space)
    assert decoded == record
    assert decoded.to_json() == before
    assert decoded.run.evaluation == owner.result()
    assert validate_durable_record(record.declaration, record, space) is space
    assert record.to_json() == before


def test_fresh_record_validation_preserves_authoritative_object_identity_and_measurements(monkeypatch):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", iter((100.0, 104.25)).__next__)
    record, _ = make_record()
    run, result = record.run, record.run.evaluation
    assert validate_durable_record(record.declaration, record) is record.description.input_space
    assert record.run is run and record.run.evaluation is result
    assert result.time_to_first_failure_seconds == 4.25
    assert decode_record(record.to_dict(), record.declaration).run.evaluation.time_to_first_failure_seconds == 4.25


def test_discovery_then_infrastructure_abort_retains_discovery_and_abort_classification():
    observations = iter((Observation(True, True), Observation(False)))
    owner = EvaluationSession(ID, SPACE, 3, "enumerative", lambda _: next(observations))
    spec = ExperimentSpec(ID, StrategyMetadata("enumerative"), 3)
    owner.execute(TrialInput((0, 0)))
    owner.execute(TrialInput((0, 1)))
    result = owner.result()
    record = ExperimentRecord(spec, owner.describe(), StrategyRun(result, spec.strategy, TerminationReason.SESSION_ABORTED))
    decoded = decode_record(record.to_dict(), spec)
    assert decoded.run.evaluation == result
    assert decoded.run.evaluation.failure_found and decoded.run.evaluation.aborted
    assert decoded.run.evaluation.first_failure_execution == 1
    assert decoded.run.evaluation.attempted_executions == 2
    assert decoded.run.evaluation.infrastructure_failures == 1
    assert decoded.run.termination is TerminationReason.SESSION_ABORTED


@pytest.mark.parametrize("count", (0, 1, 2, 3))
def test_partial_nonterminal_and_budget_exhausted_ledgers_decode_without_fabricating_completion(count):
    owner = EvaluationSession(ID, SPACE, 3, "enumerative", lambda _: Observation(True))
    spec = ExperimentSpec(ID, StrategyMetadata("enumerative"), 3)
    for index in range(count):
        owner.execute(TrialInput((0, index)))
    result = owner.result()
    validate_evaluation(spec, result)
    decoded = decode_evaluation(asdict(result), spec)
    assert decoded == result
    assert decoded.attempted_executions == count
    assert not decoded.aborted and not decoded.failure_found


@pytest.mark.parametrize("error_type", (KeyboardInterrupt, SystemExit))
def test_interrupted_admitted_ledger_is_decoded_as_partial_aborted_data(error_type):
    error = error_type("administrator-only diagnostics")

    def interrupt(_):
        raise error

    owner = EvaluationSession(ID, SPACE, 3, "enumerative", interrupt)
    spec = ExperimentSpec(ID, StrategyMetadata("enumerative"), 3)
    with pytest.raises(error_type) as caught:
        owner.execute(TrialInput((0, 0)))
    assert caught.value is error
    decoded = decode_evaluation(asdict(owner.result()), spec)
    assert decoded.attempted_executions == decoded.infrastructure_failures == 1
    assert decoded.successful_executions == 0 and decoded.aborted
    assert "administrator-only" not in json.dumps(asdict(decoded))


@pytest.mark.parametrize("path", [
    (), ("declaration",), ("description",), ("description", "input_space"),
    ("declaration", "strategy"), ("run",), ("run", "strategy"), ("run", "evaluation"),
])
@pytest.mark.parametrize("mutation", ("extra", "missing", "non_object"))
def test_unknown_missing_or_noncanonical_json_objects_are_rejected(path, mutation):
    record, _ = make_record()
    payload = record.to_dict()
    current = payload
    for key in path:
        current = current[key]
    if mutation == "extra":
        current["private_extra"] = "arbitrary hidden state"
    elif mutation == "missing":
        current.pop(next(iter(current)))
    elif path:
        current = payload
        for key in path[:-1]:
            current = current[key]
        current[path[-1]] = []
    else:
        payload = []
    with pytest.raises(ValueError):
        decode_record(payload, record.declaration)


@pytest.mark.parametrize("version", (True, False, 0, 2, 1.0, "1", None))
def test_schema_version_requires_supported_exact_integer(version):
    record, _ = make_record()
    with pytest.raises(ValueError, match="schema version"):
        decode_record(changed_payload(record, ("schema_version",), version), record.declaration)


@pytest.mark.parametrize("name", [
    "execution_budget", "attempted_executions", "successful_executions",
    "infrastructure_failures", "failure_triggering_executions", "budget_remaining",
])
@pytest.mark.parametrize("value", (True, -1, 1.0, "1"))
def test_counter_scalars_reject_bool_negative_and_coerced_values(name, value):
    record, _ = make_record()
    with pytest.raises(ValueError):
        decode_record(changed_payload(record, ("run", "evaluation", name), value), record.declaration)


@pytest.mark.parametrize("name", ("failure_found", "budget_exhausted", "aborted"))
@pytest.mark.parametrize("value", (0, 1, "false", None))
def test_flags_require_exact_bool(name, value):
    record, _ = make_record()
    with pytest.raises(ValueError, match="boolean scalar"):
        decode_record(changed_payload(record, ("run", "evaluation", name), value), record.declaration)


@pytest.mark.parametrize("changes", [
    {"attempted_executions": 4},
    {"successful_executions": 1},
    {"budget_remaining": 2},
    {"budget_exhausted": True},
    {"aborted": True},
    {"failure_triggering_executions": 3},
    {"failure_found": False},
    {"first_failure_execution": 0},
    {"first_failure_execution": 3},
    {"first_failure_execution": None},
    {"failure_triggering_executions": 2, "first_failure_execution": 2},
    {"attempted_executions": 3, "successful_executions": 1, "infrastructure_failures": 2,
     "budget_remaining": 0, "budget_exhausted": True, "aborted": True, "first_failure_execution": 1},
])
def test_contradictory_ledger_is_rejected_without_repairing_results(changes):
    record, _ = make_record()
    payload = record.to_dict()
    payload["run"]["evaluation"].update(changes)
    with pytest.raises(ValueError):
        decode_record(payload, record.declaration)


@pytest.mark.parametrize("value", (True, float("nan"), float("inf"), float("-inf"), -0.1, "1.0", None))
def test_discovery_timing_must_be_finite_nonnegative_numeric(value):
    record, _ = make_record()
    with pytest.raises(ValueError, match="timing"):
        decode_record(changed_payload(record, ("run", "evaluation", "time_to_first_failure_seconds"), value), record.declaration)


@pytest.mark.parametrize("changes", [
    {"first_failure_execution": 1}, {"time_to_first_failure_seconds": 0.0},
    {"failure_found": True}, {"failure_triggering_executions": 1},
])
def test_non_discoveries_cannot_contain_invented_discovery_measurements(changes):
    record, _ = make_record("safe")
    payload = record.to_dict()
    payload["run"]["evaluation"].update(changes)
    with pytest.raises(ValueError):
        decode_record(payload, record.declaration)


@pytest.mark.parametrize("field", ("first_failure_execution", "random_seed", "reproducibility"))
def test_nullable_scalars_reject_wrong_exact_types(field):
    record, _ = make_record(strategy=RandomStrategy(0))
    value = 1 if field == "reproducibility" else True
    with pytest.raises(ValueError):
        decode_record(changed_payload(record, ("run", "evaluation", field), value), record.declaration)


@pytest.mark.parametrize("kind,space", [
    ("discovery", SPACE), ("safe", SPACE), ("abort", SPACE),
    ("safe", InputSpace(1, 0, 0)), ("invalid", SPACE),
])
@pytest.mark.parametrize("reason", list(TerminationReason))
def test_durable_termination_agrees_with_authoritative_state(kind, space, reason):
    record, _ = make_record(kind, space=space)
    actual_reason = record.run.termination
    invalid = InvalidOutputReason.WIDTH if reason is TerminationReason.INVALID_OUTPUT else None
    changed = replace(record, run=replace(record.run, termination=reason, invalid_output=invalid))
    allowed = (
        (TerminationReason.STRATEGY_STOPPED, TerminationReason.INVALID_OUTPUT)
        if actual_reason in (TerminationReason.STRATEGY_STOPPED, TerminationReason.INVALID_OUTPUT)
        else (actual_reason,)
    )
    if reason in allowed:
        assert decode_record(changed.to_dict(), record.declaration).run.termination is reason
    else:
        with pytest.raises(ValueError, match="termination"):
            decode_record(changed.to_dict(), record.declaration)


@pytest.mark.parametrize("kind,invalid", [("invalid", None), ("discovery", "candidate_width")])
def test_invalid_reason_is_required_only_for_invalid_output(kind, invalid):
    record, _ = make_record(kind)
    with pytest.raises(ValueError, match="invalid-output"):
        decode_record(changed_payload(record, ("run", "invalid_output"), invalid), record.declaration)


@pytest.mark.parametrize("path,value", [
    (("run", "termination"), "invented"), (("run", "termination"), 1),
    (("run", "invalid_output"), "invented"), (("run", "invalid_output"), True),
])
def test_enum_values_are_known_exact_strings(path, value):
    record, _ = make_record()
    with pytest.raises(ValueError):
        decode_record(changed_payload(record, path, value), record.declaration)


@pytest.mark.parametrize("field,value", [
    ("width", 0), ("width", True), ("minimum", True), ("maximum", False),
    ("minimum", -1), ("minimum", 3), ("maximum", 0x100000000), ("width", 1.0),
])
def test_invalid_input_spaces_are_rejected(field, value):
    record, _ = make_record()
    with pytest.raises(ValueError):
        decode_record(changed_payload(record, ("description", "input_space", field), value), record.declaration)


@pytest.mark.parametrize("space", (InputSpace(1, 0, 2), InputSpace(2, 1, 2), InputSpace(2, 0, 3)))
def test_comparable_space_mismatch_is_rejected(space):
    record, _ = make_record()
    with pytest.raises(ValueError, match="same public InputSpace"):
        decode_record(record.to_dict(), record.declaration, space)


@pytest.mark.parametrize("path,value", [
    (("declaration", "strategy", "seed"), True),
    (("declaration", "strategy", "configuration"), []),
    (("declaration", "strategy", "configuration"), {"x": []}),
    (("declaration", "strategy", "configuration"), {"x": float("nan")}),
    (("declaration", "strategy", "configuration"), {1: "value"}),
    (("declaration", "strategy", "name"), True),
    (("declaration", "execution_budget"), True),
    (("description", "execution_budget"), True),
    (("description", "benchmark_id"), True),
    (("run", "evaluation", "benchmark_id"), True),
    (("run", "evaluation", "strategy_id"), True),
])
def test_declaration_metadata_and_description_fail_closed(path, value):
    record, _ = make_record()
    with pytest.raises(ValueError):
        decode_record(changed_payload(record, path, value), record.declaration)


@pytest.mark.parametrize("changes", [
    {"execution_budget": 4}, {"benchmark_id": "b-" + "b" * 32},
    {"strategy": StrategyMetadata("random", seed=0)},
])
def test_expected_plan_identity_cannot_be_replaced_by_payload(changes):
    record, _ = make_record()
    with pytest.raises(ValueError):
        decode_record(record.to_dict(), replace(record.declaration, **changes))


@pytest.mark.parametrize("component", ("record", "result", "space", "spec"))
def test_canonical_record_subclasses_with_extra_state_are_rejected(component):
    record, _ = make_record()
    spec = record.declaration
    if component == "record":
        class ExtendedRecord(ExperimentRecord):
            private_state = "hidden"
        record = ExtendedRecord(record.declaration, record.description, record.run)
    elif component == "result":
        class ExtendedResult(type(record.run.evaluation)):
            private_state = "hidden"
        object.__setattr__(record.run, "evaluation", ExtendedResult(**asdict(record.run.evaluation)))
    elif component == "space":
        class ExtendedSpace(InputSpace):
            private_state = "hidden"
        object.__setattr__(record.description, "input_space", ExtendedSpace(2, 0, 2))
    else:
        class ExtendedSpec(ExperimentSpec):
            private_state = "hidden"
        spec = ExtendedSpec(spec.benchmark_id, spec.strategy, spec.execution_budget)
    with pytest.raises(ValueError):
        validate_durable_record(spec, record)


def test_official_standard_record_and_campaign_serialization_remain_identical():
    protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=(0,), strategies=("enumerative", "random"))
    records = tuple(make_record("safe", budget=1, strategy=EnumerativeStrategy() if spec.strategy.name == "enumerative" else RandomStrategy(0))[0] for spec in protocol.expand())
    original = CampaignResult(protocol, records)
    before = original.to_json()
    decoded = tuple(decode_record(record.to_dict(), spec, SPACE) for spec, record in zip(protocol.expand(), records))
    assert CampaignResult(protocol, decoded).to_json() == before
    assert original.to_json() == before
    assert set(records[0].to_dict()) == {"schema_version", "declaration", "description", "run"}
    assert records[0].to_dict()["run"]["evaluation"] == {
        "benchmark_id": ID, "strategy_id": "enumerative", "execution_budget": 1,
        "attempted_executions": 1, "successful_executions": 1, "infrastructure_failures": 0,
        "failure_triggering_executions": 0, "failure_found": False, "first_failure_execution": None,
        "time_to_first_failure_seconds": None, "budget_remaining": 0, "budget_exhausted": True,
        "aborted": False, "random_seed": None, "reproducibility": None,
    }
    assert "journal" not in before and "attempt_id" not in before
