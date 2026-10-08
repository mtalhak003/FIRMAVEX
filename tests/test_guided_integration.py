"""Synthetic registration/record checks; no comparative firmware campaign."""

import json
from dataclasses import FrozenInstanceError, asdict, replace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import (
    ExecutionSignature, ExperimentSpec as Description, InputSpace, TrialFeedback, TrialInput,
)
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments import runner as runner_module
from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.experiments.runner import ExperimentRunner, create_strategy
from src.firmavex.protocols.protocol import (
    BASELINE_STRATEGIES, STANDARD_RANDOM_SEEDS, EvaluationProtocol, standard_baseline_protocol,
)
from src.firmavex.protocols.results import CampaignResult
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.guided import GuidedStrategy, guided_metadata


ID = "b-" + "a" * 32
OTHER_ID = "b-" + "b" * 32
SIGNATURE = ExecutionSignature("a" * 64)
PRIVATE = "private firmware.c /probe.elf GDB oracle partition held_out"


class Sessions:
    """Administrative fake executor provider, never given to the strategy."""

    def __init__(self, outcome=None, partition="development"):
        self.outcome = outcome or Observation(True, stdout=PRIVATE, execution_signature=SIGNATURE)
        self.partition = partition
        self.calls = []
        self.owners = []
        self.executors = []

    def open_session(self, identifier, budget, strategy_id, *, random_seed=None):
        self.calls.append((identifier, budget, strategy_id, random_seed))
        executor = Mock(side_effect=self.outcome) if isinstance(self.outcome, BaseException) else Mock(return_value=self.outcome)
        owner = EvaluationSession(identifier, InputSpace(2, 0, 2), budget, strategy_id, executor, random_seed=random_seed)
        self.owners.append(owner)
        self.executors.append(executor)
        return owner


def json_text(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


@pytest.mark.parametrize("seed", [0, -7, 2 ** 130])
def test_guided_factory_preserves_complete_configuration_and_exact_seed(seed):
    metadata = guided_metadata(seed, archive_size=3, mutation_attempts=2)
    spec = ExperimentSpec(ID, metadata, 4)
    strategy = create_strategy(spec.strategy)
    assert type(strategy) is GuidedStrategy and strategy.metadata == metadata
    assert dict(metadata.configuration) == {"archive_size": 3, "mutation_attempts": 2}
    with pytest.raises(FrozenInstanceError):
        spec.strategy.seed = 99


@pytest.mark.parametrize("configuration", [
    (), (("archive_size", 32),), (("mutation_attempts", 8),),
    (("archive_size", 32), ("mutation_attempts", 8), ("unknown", 1)),
    (("archive_size", True), ("mutation_attempts", 8)),
    (("archive_size", 0), ("mutation_attempts", 8)),
    (("archive_size", 32), ("mutation_attempts", -1)),
])
def test_guided_declarations_reject_incomplete_unknown_or_invalid_settings(configuration):
    metadata = StrategyMetadata("guided", configuration, 42)
    with pytest.raises(ValueError):
        ExperimentSpec(ID, metadata, 2)
    with pytest.raises(ValueError):
        create_strategy(metadata)


def test_guided_declaration_requires_an_explicit_seed():
    metadata = StrategyMetadata("guided", guided_metadata(42).configuration)
    with pytest.raises(ValueError, match="explicit integer seed"):
        ExperimentSpec(ID, metadata, 2)


def test_registered_guided_uses_common_runner_public_records_and_evaluator_accounting(monkeypatch):
    metadata = guided_metadata(42, archive_size=3, mutation_attempts=2)
    strategy = create_strategy(metadata)
    strategy.start = Mock(wraps=strategy.start)
    strategy.observe = Mock(wraps=strategy.observe)
    strategy.propose = Mock(wraps=strategy.propose)
    monkeypatch.setattr(runner_module, "create_strategy", lambda selected: strategy)
    delegated = Mock(wraps=runner_module.run_strategy)
    monkeypatch.setattr(runner_module, "run_strategy", delegated)
    provider = Sessions()
    runner = ExperimentRunner(provider)
    spec = ExperimentSpec(ID, metadata, 3)
    record = runner.run(spec)
    assert provider.calls == [(ID, 3, "guided", 42)]
    delegated.assert_called_once()
    assert delegated.call_args.args[0] is strategy
    assert record.run.evaluation == runner.last_session.result()
    assert record.run.evaluation.attempted_executions == record.run.evaluation.successful_executions == 3
    assert record.run.evaluation.infrastructure_failures == 0
    assert record.run.termination is TerminationReason.BUDGET_EXHAUSTED
    assert strategy.propose.call_count == strategy.observe.call_count == 3
    description, = strategy.start.call_args.args
    assert type(description) is Description
    assert set(asdict(description)) == {"benchmark_id", "input_space", "execution_budget"}
    for call in strategy.observe.call_args_list:
        candidate, feedback = call.args
        assert type(candidate) is TrialInput and type(feedback) is TrialFeedback
        assert feedback.execution_signature is SIGNATURE
        assert set(asdict(feedback)) == {"status", "execution_index", "budget_remaining", "execution_signature"}
        assert PRIVATE not in json_text(asdict(feedback))
    assert PRIVATE not in record.to_json()
    assert record.to_dict()["declaration"]["strategy"] == {
        "name": "guided", "configuration": {"archive_size": 3, "mutation_attempts": 2}, "seed": 42,
    }


def test_admin_partition_and_diagnostics_cannot_change_registered_guided_order():
    spec = ExperimentSpec(ID, guided_metadata(42), 4)
    left = Sessions(partition="development")
    right = Sessions(
        Observation(True, stdout="different private output", stderr="different private diagnostic", execution_signature=SIGNATURE),
        partition="held_out",
    )
    first = ExperimentRunner(left).run(spec)
    second = ExperimentRunner(right).run(spec)
    assert left.executors[0].call_args_list == right.executors[0].call_args_list
    assert first.to_json() == second.to_json()


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_registered_guided_propagates_charged_interruption_without_a_record(interruption_type):
    interruption = interruption_type(PRIVATE)
    runner = ExperimentRunner(Sessions(interruption))
    with pytest.raises(interruption_type) as caught:
        runner.run(ExperimentSpec(ID, guided_metadata(42), 2))
    assert caught.value is interruption
    result = runner.last_session.result()
    assert result.aborted and result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0
    assert PRIVATE in runner.last_session.diagnostics()[0]["stderr"]


def test_explicit_protocol_keeps_independent_seed_schedules_and_existing_order():
    protocol = EvaluationProtocol(
        (ID, OTHER_ID), 4, "development", random_seeds=(9, 7),
        strategies=("enumerative", "random", "guided"), guided_seeds=(42, 3),
    )
    expected = [("enumerative", None), ("random", 9), ("random", 7), ("guided", 42), ("guided", 3)]
    plan = protocol.expand()
    assert [(item.benchmark_id, item.strategy.name, item.strategy.seed) for item in plan] == [
        (identifier, name, seed) for identifier in (ID, OTHER_ID) for name, seed in expected
    ]
    assert all(item.strategy == guided_metadata(item.strategy.seed) for item in plan if item.strategy.name == "guided")
    assert not protocol.is_standard
    data = protocol.to_dict()
    assert data["kind"] == "custom_search_v1"
    assert data["random_seeds"] == [9, 7] and data["guided_seeds"] == [42, 3]
    assert data["run_order"] == "benchmark_then_enumerative_then_random_seed_then_guided_seed"
    assert json.loads(protocol.plan_to_json())["protocol"] == data


@pytest.mark.parametrize("schedule", [None, [42], (True,), (1.0,), ("42",), (42, 42), ()])
def test_guided_protocol_requires_a_valid_nonempty_explicit_seed_schedule(schedule):
    with pytest.raises(ValueError):
        EvaluationProtocol((ID,), 2, "development", random_seeds=(), strategies=("guided",), guided_seeds=schedule)


def test_guided_only_protocol_never_inherits_the_random_seed_schedule():
    with pytest.raises(ValueError, match="without random"):
        EvaluationProtocol((ID,), 2, "development", strategies=("guided",), guided_seeds=(42,))
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(), strategies=("guided",), guided_seeds=(42,))
    assert protocol.expand() == (ExperimentSpec(ID, guided_metadata(42), 2),)
    with pytest.raises(ValueError, match="without guided"):
        EvaluationProtocol((ID,), 2, "development", guided_seeds=(42,))


@pytest.mark.parametrize("names", [("guided", "random"), ("guided", "guided"), ("unknown",), ("guided", "enumerative")])
def test_protocol_preserves_canonical_unique_strategy_order(names):
    with pytest.raises(ValueError):
        EvaluationProtocol((ID,), 2, "development", random_seeds=(7,), strategies=names, guided_seeds=(42,))


def test_frozen_standard_json_and_plan_match_the_pre_guided_schema_exactly():
    assert BASELINE_STRATEGIES == ("enumerative", "random")
    assert STANDARD_RANDOM_SEEDS == tuple(range(10))
    protocol = standard_baseline_protocol(benchmark_ids=(ID,), execution_budget=3, partition="held_out")
    expected = {
        "schema_version": 1, "kind": "standard_baseline_v1", "benchmark_ids": [ID],
        "execution_budget": 3, "partition": "held_out", "strategies": ["enumerative", "random"],
        "random_seeds": list(range(10)), "run_order": "benchmark_then_enumerative_then_random_seed",
        "infrastructure_abort_policy": "continue_independent_experiments",
    }
    assert protocol.is_standard and protocol.guided_seeds == ()
    assert protocol.to_json() == json_text(expected)
    assert EvaluationProtocol((ID,), 3, "held_out").to_json() == json_text(expected)
    old_plan = {
        "schema_version": 1, "protocol": expected,
        "experiments": [
            {"benchmark_id": ID, "strategy": {"name": name, "configuration": {}, "seed": seed}, "execution_budget": 3}
            for name, seed in [("enumerative", None)] + [("random", seed) for seed in range(10)]
        ],
    }
    assert protocol.plan_to_json() == json_text(old_plan)


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 7)])
def test_baseline_summary_json_matches_legacy_fields_exactly(name, seed):
    protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=() if seed is None else (seed,), strategies=(name,))
    record = ExperimentRunner(Sessions()).run(protocol.expand()[0])
    summary, = CampaignResult(protocol, (record,)).summaries
    expected = {
        "schema_version": 1, "benchmark_id": ID, "strategy_name": name, "execution_budget": 1,
        "planned_runs": 1, "completed_records": 1, "valid_runs": 1, "discovered_runs": 0,
        "non_discovered_valid_runs": 1, "infrastructure_aborted_runs": 0, "invalid_strategy_runs": 0,
        "discovery_rate": 0.0, "discovery_executions": [None], "first_failure_executions": [],
        "minimum_first_failure_execution": None, "median_first_failure_execution": None,
        "maximum_first_failure_execution": None, "random_seeds": [] if seed is None else [seed],
    }
    assert summary.to_json() == json_text(expected)
    assert summary.seeds == (() if seed is None else (seed,))


def test_guided_summary_keeps_all_seeds_and_existing_abort_and_discovery_metrics(monkeypatch):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", lambda: 100.0)
    protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=(), strategies=("guided",), guided_seeds=(7, 11, 13))
    # Outcomes are controlled executor fixtures, never firmware measurements.
    outcomes = [Observation(True, True, execution_signature=SIGNATURE), Observation(True, execution_signature=SIGNATURE), Observation(False, stderr=PRIVATE)]
    records = tuple(ExperimentRunner(Sessions(outcome)).run(spec) for spec, outcome in zip(protocol.expand(), outcomes))
    result = CampaignResult(protocol, records)
    summary, = result.summaries
    assert summary.seeds == (7, 11, 13) and summary.random_seeds == ()
    assert summary.valid_runs == 2 and summary.discovered_runs == 1
    assert summary.infrastructure_aborted_runs == 1 and summary.non_discovered_valid_runs == 1
    assert summary.discovery_rate == 0.5
    assert summary.discovery_executions == (1, None, None) and summary.first_failure_executions == (1,)
    assert summary.to_dict()["seeds"] == [7, 11, 13]
    assert records[2].run.termination is TerminationReason.SESSION_ABORTED
    assert PRIVATE not in result.to_json()
    assert json.loads(result.to_json())["records"] == [record.to_dict() for record in records]


@pytest.mark.parametrize("schedule", [[7], (True,), (None,), (1.0,)])
def test_generic_summary_seed_schedule_is_immutable_and_exact_integer(schedule):
    protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=(), strategies=("guided",), guided_seeds=(7,))
    summary, = CampaignResult(protocol, (ExperimentRunner(Sessions()).run(protocol.expand()[0]),)).summaries
    with pytest.raises(ValueError):
        replace(summary, seeds=schedule)


def make_summary(name):
    if name == "enumerative":
        protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=(), strategies=(name,))
    elif name == "random":
        protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=(7,), strategies=(name,))
    else:
        protocol = EvaluationProtocol((ID,), 1, "development", random_seeds=(), strategies=(name,), guided_seeds=(7,))
    record = ExperimentRunner(Sessions()).run(protocol.expand()[0])
    summary, = CampaignResult(protocol, (record,)).summaries
    return summary


@pytest.mark.parametrize("name, random_seeds, seeds, expected", [
    ("random", (7,), (7,), (7,)),
    ("random", (7,), (), (7,)),
    ("random", (-7, 0, 2 ** 130), (-7, 0, 2 ** 130), (-7, 0, 2 ** 130)),
    ("random", (-7, 0, 2 ** 130), (), (-7, 0, 2 ** 130)),
    ("random", (), (), ()),
    ("enumerative", (), (), ()),
    ("guided", (), (7,), (7,)),
    ("guided", (), (-7, 0, 2 ** 130), (-7, 0, 2 ** 130)),
])
def test_summary_seed_schedules_accept_consistent_or_legacy_combinations(name, random_seeds, seeds, expected):
    summary = replace(make_summary(name), random_seeds=random_seeds, seeds=seeds)
    assert summary.random_seeds == random_seeds and summary.seeds == expected
    if name == "random":
        assert summary.seeds == summary.random_seeds
    with pytest.raises(FrozenInstanceError):
        summary.seeds = ()


@pytest.mark.parametrize("random_seeds, seeds", [
    ((7,), (999,)), ((7, 9), (9, 7)), ((7, 9), (7,)), ((), (7,)),
])
def test_random_summary_rejects_conflicting_values_order_length_or_missing_legacy_schedule(random_seeds, seeds):
    with pytest.raises(ValueError, match="must match random_seeds"):
        replace(make_summary("random"), random_seeds=random_seeds, seeds=seeds)


def test_replacing_only_the_random_schedule_cannot_leave_stale_generic_seeds():
    with pytest.raises(ValueError, match="must match random_seeds"):
        replace(make_summary("random"), random_seeds=(999,))


@pytest.mark.parametrize("name", ["enumerative", "guided"])
def test_nonrandom_summary_rejects_a_random_only_seed_schedule(name):
    with pytest.raises(ValueError, match="Only random summaries"):
        replace(make_summary(name), random_seeds=(7,))


def test_enumerative_summary_rejects_a_generic_seed_schedule():
    with pytest.raises(ValueError, match="Enumerative summaries"):
        replace(make_summary("enumerative"), seeds=(7,))


@pytest.mark.parametrize("value", [False, True])
def test_random_summary_validates_exact_integer_types_before_schedule_comparison(value):
    with pytest.raises(ValueError, match="exact integers"):
        replace(make_summary("random"), random_seeds=(int(value),), seeds=(value,))


def test_legacy_random_summary_construction_preserves_official_serialization():
    summary = make_summary("random")
    old_fields = asdict(summary)
    del old_fields["seeds"]
    legacy = type(summary)(**old_fields)
    assert legacy == summary and legacy.seeds == legacy.random_seeds == (7,)
    assert legacy.to_dict() == summary.to_dict() and legacy.to_json() == summary.to_json()
    assert "seeds" not in legacy.to_dict()


def test_generic_dataclass_forms_change_while_official_baseline_forms_stay_frozen():
    protocol = standard_baseline_protocol(benchmark_ids=(ID,), execution_budget=1, partition="development")
    summary = make_summary("random")
    assert asdict(protocol)["guided_seeds"] == ()
    assert "guided_seeds" not in protocol.to_dict()
    assert asdict(summary)["seeds"] == (7,)
    assert "seeds" not in summary.to_dict()
    assert json.loads(summary.to_json())["random_seeds"] == [7]
