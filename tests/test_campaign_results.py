"""Synthetic campaign summaries: real evaluator records, no firmware trials."""

import json
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation import evaluator as evaluator_module
from src.firmavex.evaluation.api import InputSpace, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.api import ExperimentRecord
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.results import CampaignResult, validate_record
from src.firmavex.strategies.api import InvalidOutputReason, StrategyRun, TerminationReason


ID = "b-" + "1" * 32
OTHER_ID = "b-" + "2" * 32
SPACE = InputSpace(1, 0, 63)


def protocol(seeds=tuple(range(10)), *, strategies=("random",), ids=(ID,), budget=12):
    return EvaluationProtocol(
        benchmark_ids=ids, execution_budget=budget, partition="development",
        random_seeds=seeds, strategies=strategies,
    )


def record_for(spec, *, discovery=None, abort=None, space=SPACE, invalid=False):
    """Use existing single-run execution and evaluator-owned accounting."""
    calls = 0

    def execute(values):
        nonlocal calls
        calls += 1
        if calls == abort:
            return Observation(False, stderr="/private/image.elf GDB raw diagnostic")
        return Observation(True, calls == discovery)

    owner = EvaluationSession(
        spec.benchmark_id, space, spec.execution_budget, spec.strategy.name,
        execute, random_seed=spec.strategy.seed,
    )
    if invalid:
        run = StrategyRun(owner.result(), spec.strategy, TerminationReason.INVALID_OUTPUT, InvalidOutputReason.WIDTH)
        return ExperimentRecord(spec, owner.describe(), run)
    provider = Mock()
    provider.open_session.return_value = owner
    return ExperimentRunner(provider).run(spec)


def random_result(discoveries, *, aborts=()):
    declared = protocol(tuple(range(len(discoveries))))
    records = tuple(
        record_for(spec, discovery=discovery, abort=1 if index in aborts else None)
        for index, (spec, discovery) in enumerate(zip(declared.expand(), discoveries))
    )
    return CampaignResult(declared, records)


@pytest.mark.parametrize("discoveries, expected", [
    ((1, 2, 3, 4, None, None, None, None, None, None), 0.4),
    ((None,) * 10, 0.0),
])
def test_discovery_rate_uses_all_valid_declared_random_trials(discoveries, expected):
    result = random_result(discoveries)
    summary, = result.summaries
    assert summary.planned_runs == summary.completed_records == summary.valid_runs == 10
    assert summary.discovered_runs == sum(value is not None for value in discoveries)
    assert summary.non_discovered_valid_runs == 10 - summary.discovered_runs
    assert summary.infrastructure_aborted_runs == summary.invalid_strategy_runs == 0
    assert summary.discovery_rate == expected
    assert summary.discovery_executions == discoveries
    assert result.planned_run_count == result.completed_record_count == result.valid_search_run_count == 10


def test_no_valid_trials_has_undefined_rate_and_conditional_costs():
    result = random_result((None,) * 10, aborts=range(10))
    summary, = result.summaries
    assert summary.valid_runs == summary.discovered_runs == summary.non_discovered_valid_runs == 0
    assert summary.infrastructure_aborted_runs == 10
    assert summary.discovery_rate is None
    assert summary.discovery_executions == (None,) * 10
    assert summary.first_failure_executions == ()
    assert summary.minimum_first_failure_execution is None
    assert summary.median_first_failure_execution is None
    assert summary.maximum_first_failure_execution is None
    assert result.infrastructure_aborted_run_count == 10
    assert result.valid_search_run_count == 0


def test_aborted_trials_are_excluded_from_valid_discovery_denominator():
    result = random_result((2, None, 4, None, 8, None, None, None, None, None), aborts=(8, 9))
    summary, = result.summaries
    assert summary.planned_runs == summary.completed_records == 10
    assert summary.valid_runs == 8 and summary.discovered_runs == 3
    assert summary.non_discovered_valid_runs == 5
    assert summary.infrastructure_aborted_runs == 2
    assert summary.discovery_rate == 3 / 8
    assert summary.first_failure_executions == (2, 4, 8)
    assert summary.discovery_executions == (2, None, 4, None, 8, None, None, None, None, None)
    assert result.valid_search_run_count == 8 and result.infrastructure_aborted_run_count == 2


@pytest.mark.parametrize("samples, minimum, center, maximum", [
    ((2, 5, 9), 2, 5, 9),
    ((2, 4, 8, 10), 2, 6, 10),
    ((2, 3), 2, 2.5, 3),
    ((9, 2, 5), 2, 5, 9),
])
def test_conditional_execution_cost_statistics_use_standard_median(samples, minimum, center, maximum):
    result = random_result(samples + (None,))
    summary, = result.summaries
    assert summary.first_failure_executions == samples
    assert summary.discovery_executions == samples + (None,)
    assert summary.minimum_first_failure_execution == minimum
    assert summary.median_first_failure_execution == center
    assert summary.maximum_first_failure_execution == maximum
    assert summary.discovery_rate == len(samples) / (len(samples) + 1)
    assert result.records[-1].run.evaluation.first_failure_execution is None


def test_non_discovery_has_no_synthetic_budget_or_penalty_cost():
    result = random_result((None, None))
    summary, = result.summaries
    assert summary.discovery_executions == (None, None)
    assert summary.first_failure_executions == ()
    assert summary.minimum_first_failure_execution is None
    assert summary.median_first_failure_execution is None
    assert summary.maximum_first_failure_execution is None
    for record in result.records:
        assert record.run.evaluation.first_failure_execution is None
        assert record.run.evaluation.attempted_executions == 12
        assert record.run.termination is TerminationReason.BUDGET_EXHAUSTED


@pytest.mark.parametrize("outcome, index, termination", [
    ("discovered", 7, TerminationReason.FAILURE_DISCOVERED),
    ("budget", None, TerminationReason.BUDGET_EXHAUSTED),
    ("domain", None, TerminationReason.STRATEGY_STOPPED),
    ("aborted", None, TerminationReason.SESSION_ABORTED),
])
def test_enumerative_summary_is_one_actual_deterministic_run(outcome, index, termination):
    declared = protocol((), strategies=("enumerative",))
    spec, = declared.expand()
    kwargs = {
        "discovered": {"discovery": index}, "budget": {},
        "domain": {"space": InputSpace(1, 0, 1)}, "aborted": {"abort": 2},
    }[outcome]
    record = record_for(spec, **kwargs)
    result = CampaignResult(declared, (record,))
    summary, = result.summaries
    assert summary.planned_runs == summary.completed_records == 1
    assert summary.random_seeds == ()
    assert summary.discovery_executions == (index,)
    assert result.records[0] is record
    assert record.run.termination is termination
    assert record.run.evaluation.first_failure_execution == index
    if outcome == "aborted":
        assert summary.valid_runs == 0 and summary.infrastructure_aborted_runs == 1
        assert summary.discovery_rate is None
    else:
        assert summary.valid_runs == 1 and summary.infrastructure_aborted_runs == 0
        assert summary.discovery_rate == float(outcome == "discovered")
    if outcome == "domain":
        assert record.run.evaluation.attempted_executions == 2
        assert record.run.evaluation.budget_remaining == 10


def test_all_declared_random_seeds_survive_even_when_unfavorable_or_aborted():
    declared = protocol((9, 1, -4, 2**100))
    records = tuple(
        record_for(spec, discovery=5 if index == 1 else None, abort=1 if index == 2 else None)
        for index, spec in enumerate(declared.expand())
    )
    result = CampaignResult(declared, records)
    summary, = result.summaries
    assert summary.random_seeds == (9, 1, -4, 2**100)
    assert tuple(record.run.evaluation.random_seed for record in result.records) == summary.random_seeds
    assert tuple(record.run.strategy.seed for record in result.records) == summary.random_seeds
    assert summary.planned_runs == summary.completed_records == 4
    assert summary.valid_runs == 3 and summary.discovered_runs == 1
    assert summary.discovery_rate == 1 / 3
    assert summary.first_failure_executions == (5,)
    assert summary.discovery_executions == (None, 5, None, None)


def test_summaries_are_scoped_by_benchmark_and_strategy_in_plan_order():
    declared = protocol((0, 1), strategies=("enumerative", "random"), ids=(OTHER_ID, ID))
    records = tuple(record_for(spec, discovery=1 if spec.benchmark_id == OTHER_ID else 4) for spec in declared.expand())
    result = CampaignResult(declared, records)
    assert [(summary.benchmark_id, summary.strategy_name) for summary in result.summaries] == [
        (OTHER_ID, "enumerative"), (OTHER_ID, "random"), (ID, "enumerative"), (ID, "random"),
    ]
    assert [summary.planned_runs for summary in result.summaries] == [1, 2, 1, 2]
    assert [summary.first_failure_executions for summary in result.summaries] == [(1,), (1, 1), (4,), (4, 4)]
    assert all(summary.execution_budget == 12 for summary in result.summaries)
    assert result.planned_run_count == result.completed_record_count == result.valid_search_run_count == 6
    assert result.infrastructure_aborted_run_count == result.invalid_strategy_run_count == 0


def test_invalid_strategy_output_is_separate_from_infrastructure_and_valid_non_discovery():
    declared = protocol((0, 1, 2))
    specs = declared.expand()
    records = (record_for(specs[0], invalid=True), record_for(specs[1], discovery=3), record_for(specs[2]))
    result = CampaignResult(declared, records)
    summary, = result.summaries
    assert summary.valid_runs == 2 and summary.discovered_runs == 1
    assert summary.non_discovered_valid_runs == 1
    assert summary.invalid_strategy_runs == 1 and summary.infrastructure_aborted_runs == 0
    assert summary.discovery_rate == 0.5
    assert summary.discovery_executions == (None, 3, None)
    assert result.invalid_strategy_run_count == 1
    assert result.records[0].run.invalid_output is InvalidOutputReason.WIDTH


def test_discovery_followed_by_infrastructure_abort_preserves_raw_discovery_but_excludes_sample():
    declared = protocol((), strategies=("enumerative",))
    spec, = declared.expand()
    owner = EvaluationSession(ID, SPACE, 12, "enumerative", Mock(side_effect=[
        Observation(True, True), Observation(False, stderr="private interrupted GDB diagnostics"),
    ]))
    owner.execute(TrialInput((0,)))
    owner.execute(TrialInput((1,)))
    authoritative = owner.result()
    record = ExperimentRecord(spec, owner.describe(), StrategyRun(authoritative, spec.strategy, TerminationReason.SESSION_ABORTED))
    result = CampaignResult(declared, (record,))
    summary, = result.summaries
    assert result.records[0].run.evaluation is authoritative
    assert authoritative.aborted and authoritative.failure_found
    assert authoritative.first_failure_execution == 1
    assert authoritative.attempted_executions == 2 and authoritative.infrastructure_failures == 1
    assert summary.valid_runs == summary.discovered_runs == 0
    assert summary.infrastructure_aborted_runs == 1
    assert summary.discovery_executions == (None,) and summary.first_failure_executions == ()
    assert summary.discovery_rate is None
    assert result.to_dict()["records"][0]["run"]["evaluation"]["first_failure_execution"] == 1
    assert "private" not in result.to_json()


@pytest.mark.parametrize("aborted_flag, reason", [
    (True, TerminationReason.FAILURE_DISCOVERED),
    (False, TerminationReason.SESSION_ABORTED),
    (True, TerminationReason.INVALID_OUTPUT),
])
def test_evaluator_abort_or_authoritative_abort_termination_takes_precedence(aborted_flag, reason):
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec, discovery=1)
    changed = replace(record, run=replace(record.run, evaluation=replace(record.run.evaluation, aborted=aborted_flag), termination=reason))
    summary, = CampaignResult(declared, (changed,)).summaries
    assert summary.infrastructure_aborted_runs == 1
    assert summary.invalid_strategy_runs == summary.valid_runs == summary.discovered_runs == 0
    assert summary.discovery_executions == (None,)


def test_campaign_and_summary_are_immutable_and_keep_exact_record_objects():
    declared = protocol((0, 1))
    records = tuple(record_for(spec) for spec in declared.expand())
    result = CampaignResult(declared, records)
    assert result.protocol is declared and result.records is records
    assert all(actual is original for actual, original in zip(result.records, records))
    with pytest.raises(FrozenInstanceError):
        result.records = ()
    with pytest.raises(FrozenInstanceError):
        result.summaries[0].valid_runs = 999
    with pytest.raises(TypeError):
        result.records[0] = records[1]


@pytest.mark.parametrize("kind", ["missing", "extra", "reordered", "duplicate"])
def test_campaign_requires_exact_complete_record_sequence(kind):
    declared = protocol((0, 1, 2))
    records = tuple(record_for(spec) for spec in declared.expand())
    changed = {"missing": records[:-1], "extra": records + (records[0],),
               "reordered": tuple(reversed(records)), "duplicate": (records[0], records[0], records[2])}[kind]
    with pytest.raises(ValueError, match="every planned experiment|differs from the campaign plan"):
        CampaignResult(declared, changed)


@pytest.mark.parametrize("kind", ["mutable_records", "extended_record", "live_record", "mutable_protocol", "extended_protocol"])
def test_campaign_rejects_noncanonical_or_mutable_types(kind):
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec)
    supplied_protocol, supplied_records = declared, (record,)
    if kind == "mutable_records":
        supplied_records = [record]
    elif kind == "extended_record":
        class ExtendedRecord(ExperimentRecord):
            source_path = "/private/source.c"

        supplied_records = (ExtendedRecord(record.declaration, record.description, record.run),)
    elif kind == "live_record":
        supplied_records = (Mock(),)
    elif kind == "mutable_protocol":
        supplied_protocol = declared.to_dict()
    else:
        class ExtendedProtocol(EvaluationProtocol):
            pass

        supplied_protocol = ExtendedProtocol(
            benchmark_ids=declared.benchmark_ids, execution_budget=declared.execution_budget,
            partition=declared.partition, random_seeds=declared.random_seeds, strategies=declared.strategies,
        )
    with pytest.raises(ValueError, match="immutable EvaluationProtocol|canonical ExperimentSpec"):
        CampaignResult(supplied_protocol, supplied_records)


@pytest.mark.parametrize("different_space", [InputSpace(2, 0, 63), InputSpace(1, 1, 63), InputSpace(1, 0, 62)])
def test_all_comparable_strategy_runs_must_use_identical_public_input_space(different_space):
    declared = protocol((0,), strategies=("enumerative", "random"))
    specs = declared.expand()
    records = (record_for(specs[0]), record_for(specs[1], space=different_space))
    with pytest.raises(ValueError, match="same public InputSpace"):
        CampaignResult(declared, records)


def test_different_benchmarks_may_expose_different_public_input_spaces():
    declared = protocol((0,), ids=(ID, OTHER_ID))
    specs = declared.expand()
    records = (record_for(specs[0], space=InputSpace(1, 0, 1)), record_for(specs[1], space=InputSpace(2, 0, 2)))
    result = CampaignResult(declared, records)
    assert result.records[0].description.input_space != result.records[1].description.input_space
    assert len(result.summaries) == 2


def test_validate_record_returns_domain_and_can_check_before_later_campaign_dispatch():
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec)
    assert validate_record(spec, record) is record.description.input_space
    assert validate_record(spec, record, SPACE) == SPACE
    with pytest.raises(ValueError, match="same public InputSpace"):
        validate_record(spec, record, InputSpace(1, 0, 1))


@pytest.mark.parametrize("changed_spec", ["budget", "benchmark", "seed"])
def test_validate_record_rejects_declaration_identity_mismatch(changed_spec):
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec)
    changes = {"budget": {"execution_budget": 13}, "benchmark": {"benchmark_id": OTHER_ID},
               "seed": {"strategy": replace(spec.strategy, seed=1)}}[changed_spec]
    with pytest.raises(ValueError, match="differs from the campaign plan"):
        validate_record(replace(spec, **changes), record)


def test_campaign_json_has_schema_counts_seed_order_nulls_and_original_timing():
    declared = protocol((2**130, -1, 4))
    specs = declared.expand()
    records = (record_for(specs[0], discovery=2), record_for(specs[1]), record_for(specs[2], abort=1))
    result = CampaignResult(declared, records)
    payload = json.loads(result.to_json())
    assert payload["schema_version"] == 1
    assert payload["counts"] == {"planned_runs": 3, "completed_records": 3, "valid_search_runs": 2,
                                  "infrastructure_aborted_runs": 1, "invalid_strategy_runs": 0}
    assert payload["summaries"][0]["discovery_rate"] == 0.5
    assert payload["summaries"][0]["discovery_executions"] == [2, None, None]
    assert payload["summaries"][0]["random_seeds"] == [2**130, -1, 4]
    assert [entry["run"]["strategy"]["seed"] for entry in payload["records"]] == [2**130, -1, 4]
    assert payload["records"][0]["run"]["evaluation"]["time_to_first_failure_seconds"] == records[0].run.evaluation.time_to_first_failure_seconds
    assert payload["records"][1]["run"]["evaluation"]["first_failure_execution"] is None
    assert payload["records"][2]["run"]["termination"] == "session_aborted"
    for forbidden in ("private", "image.elf", "stdout", "stderr", "oracle", "source_path"):
        assert forbidden not in result.to_json()
    assert "mean" not in payload["summaries"][0]
    assert "global_discovery_rate" not in payload
    assert "campaign_id" not in payload


def test_serialized_data_is_fresh_and_cannot_mutate_result():
    result = random_result((2, None))
    before = result.to_json()
    payload = result.to_dict()
    payload["counts"]["valid_search_runs"] = 999
    payload["records"][0]["run"]["evaluation"]["first_failure_execution"] = 999
    payload["summaries"][0]["valid_runs"] = 999
    assert result.to_json() == before


def test_summary_has_standalone_versioned_deterministic_serialization():
    result = random_result((2, None, 4), aborts=(1,))
    summary, = result.summaries
    payload = json.loads(summary.to_json())
    assert payload["schema_version"] == 1
    assert payload["benchmark_id"] == ID and payload["strategy_name"] == "random"
    assert payload["discovery_rate"] == 1.0
    assert payload["discovery_executions"] == [2, None, 4]
    assert payload["first_failure_executions"] == [2, 4]
    assert payload["random_seeds"] == [0, 1, 2]
    assert summary.to_json() == json.dumps(summary.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert result.to_dict()["summaries"][0] == summary.to_dict()
    changed = summary.to_dict()
    changed["valid_runs"] = 999
    assert summary.valid_runs == 2


def test_campaign_and_summary_data_roundtrip_through_json_without_shape_changes():
    result = random_result((2, None, 4), aborts=(1,))
    assert json.loads(result.to_json()) == result.to_dict()
    assert json.loads(result.summaries[0].to_json()) == result.summaries[0].to_dict()


@pytest.mark.parametrize("field", ["discovery_executions", "first_failure_executions", "random_seeds"])
def test_direct_summary_construction_rejects_mutable_sample_or_seed_containers(field):
    summary, = random_result((2, None)).summaries
    with pytest.raises(ValueError, match="immutable tuples"):
        replace(summary, **{field: list(getattr(summary, field))})


@pytest.mark.parametrize("field", ["discovery_executions", "first_failure_executions", "random_seeds"])
@pytest.mark.parametrize("value", [True, 1.5, "2", [], (2,)])
def test_direct_summary_construction_rejects_non_integer_or_mutable_elements(field, value):
    summary, = random_result((2, None)).summaries
    with pytest.raises(ValueError, match="exact integers"):
        replace(summary, **{field: (value,)})


@pytest.mark.parametrize("field, value", [
    ("benchmark_id", []), ("planned_runs", []), ("execution_budget", True),
    ("minimum_first_failure_execution", "7"), ("median_first_failure_execution", {}),
    ("discovery_rate", False),
])
def test_direct_summary_construction_rejects_mutable_or_wrongly_typed_scalar_fields(field, value):
    summary, = random_result((2, None)).summaries
    with pytest.raises(ValueError, match="scalar"):
        replace(summary, **{field: value})


@pytest.mark.parametrize("index", [None, 0, -1, True, 1.5, "7", [], (7,)])
def test_eligible_discovery_requires_positive_exact_integer_authoritative_index(index):
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec, discovery=1)
    changed = replace(record, run=replace(record.run, evaluation=replace(record.run.evaluation, first_failure_execution=index)))
    with pytest.raises(ValueError, match="positive integer first-failure execution index"):
        validate_record(spec, changed)
    with pytest.raises(ValueError, match="positive integer first-failure execution index"):
        CampaignResult(declared, (changed,))


@pytest.mark.parametrize("field, value", [
    ("infrastructure_failures", []), ("attempted_executions", True),
    ("successful_executions", "0"), ("failure_triggering_executions", 0.0),
    ("budget_remaining", {}), ("failure_found", 0), ("aborted", []),
    ("budget_exhausted", "false"), ("first_failure_execution", []),
    ("random_seed", False), ("time_to_first_failure_seconds", []),
    ("time_to_first_failure_seconds", True), ("reproducibility", "private source path"),
])
def test_canonical_record_wrappers_cannot_hide_mutable_or_wrongly_typed_evaluator_fields(field, value):
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec)
    changed = replace(record, run=replace(record.run, evaluation=replace(record.run.evaluation, **{field: value})))
    with pytest.raises(ValueError, match="scalar|exact integer or None"):
        validate_record(spec, changed)
    with pytest.raises(ValueError, match="scalar|exact integer or None"):
        CampaignResult(declared, (changed,))


@pytest.mark.parametrize("field, value", [("width", True), ("minimum", []), ("maximum", "63")])
def test_public_input_space_requires_immutable_exact_integer_fields(field, value):
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec)
    space = replace(record.description.input_space, **{field: value})
    changed = replace(record, description=replace(record.description, input_space=space))
    with pytest.raises(ValueError, match="InputSpace fields.*exact integer scalars"):
        validate_record(spec, changed)


def test_equivalent_fake_campaigns_have_identical_structural_serialization(monkeypatch):
    monkeypatch.setattr(evaluator_module.time, "monotonic", lambda: 100.0)
    first = random_result((2, None, 4), aborts=(1,))
    second = random_result((2, None, 4), aborts=(1,))
    assert first.to_json() == second.to_json()
    assert first.to_json() == json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)


def test_nonfinite_per_run_timing_is_not_serialized_as_invalid_json():
    declared = protocol((0,))
    spec, = declared.expand()
    record = record_for(spec, discovery=1)
    record = replace(record, run=replace(record.run, evaluation=replace(record.run.evaluation, time_to_first_failure_seconds=float("nan"))))
    result = CampaignResult(declared, (record,))
    with pytest.raises(ValueError):
        result.to_json()
