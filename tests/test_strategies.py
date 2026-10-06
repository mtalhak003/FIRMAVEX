import json
from dataclasses import FrozenInstanceError, asdict, fields
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import ExperimentSpec, InputSpace, TrialFeedback, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.strategies.api import (
    InvalidOutputReason, StrategyMetadata, StrategyRun, TerminationReason,
)
from src.firmavex.strategies.runner import run_strategy


ID = "b-3874d6a4a92f46758d73854abf0a08df"
TRIAL = TrialInput((1, 2, 3, 4))
METADATA = StrategyMetadata("test-double", (("mode", "fixed"),), seed=42)


class FixedStrategy:
    """Test-only lifecycle probe; not a production search baseline."""

    def __init__(self, candidates, metadata=METADATA):
        self.metadata = metadata
        self.start = Mock()
        self.propose = Mock(side_effect=candidates)
        self.observe = Mock()


def make_session(executor, budget=3, space=InputSpace(4, 0, 15)):
    return EvaluationSession(ID, space, budget, METADATA.name, executor, random_seed=METADATA.seed)


def test_lifecycle_exposes_only_public_records_and_no_adapter():
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor)
    strategy = FixedStrategy([TRIAL, None])
    record = run_strategy(strategy, owner.strategy_api())
    description, = strategy.start.call_args.args
    assert type(description) is ExperimentSpec
    assert asdict(description) == {
        "benchmark_id": ID,
        "input_space": {"width": 4, "minimum": 0, "maximum": 15},
        "execution_budget": 3,
    }
    candidate, feedback = strategy.observe.call_args.args
    assert candidate is TRIAL
    assert type(feedback) is TrialFeedback
    assert asdict(feedback) == {"status": "safe", "execution_index": 1, "budget_remaining": 2}
    for public in (description, description.input_space, candidate, feedback):
        assert not any(callable(getattr(public, field.name)) for field in fields(public))
        for hidden in ("source", "image", "registry", "evaluator", "diagnostics", "execute", "_execute", "_executor"):
            assert not hasattr(public, hidden)
    with pytest.raises(FrozenInstanceError):
        description.execution_budget = 999
    with pytest.raises(FrozenInstanceError):
        feedback.execution_index = 999
    assert record.termination is TerminationReason.STRATEGY_STOPPED
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == 1


def test_discovery_stops_before_another_proposal_even_on_last_slot():
    executor = Mock(return_value=Observation(True, True))
    owner = make_session(executor, budget=1)
    strategy = FixedStrategy([TRIAL])
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.FAILURE_DISCOVERED
    assert record.evaluation.failure_found and record.evaluation.budget_exhausted
    assert record.evaluation.first_failure_execution == 1
    assert record.evaluation.time_to_first_failure_seconds is not None
    strategy.propose.assert_called_once()
    strategy.observe.assert_called_once()
    executor.assert_called_once_with(TRIAL.values)


def test_budget_exhaustion_stops_before_consuming_another_candidate():
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor, budget=2)
    strategy = FixedStrategy([TRIAL, TRIAL, TRIAL])
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.BUDGET_EXHAUSTED
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == 2
    assert record.evaluation.infrastructure_failures == 0
    assert not record.evaluation.failure_found
    assert strategy.propose.call_count == strategy.observe.call_count == executor.call_count == 2


@pytest.mark.parametrize("prior_trials", [0, 1])
def test_strategy_stop_never_consumes_an_extra_execution(prior_trials):
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor)
    strategy = FixedStrategy([TRIAL] * prior_trials + [None])
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.STRATEGY_STOPPED
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == executor.call_count == prior_trials
    assert record.evaluation.budget_remaining == 3 - prior_trials
    assert not record.evaluation.failure_found


@pytest.mark.parametrize("candidate, reason", [
    ((1, 2, 3, 4), InvalidOutputReason.CANDIDATE_TYPE),
    ({"values": (1, 2, 3, 4)}, InvalidOutputReason.CANDIDATE_TYPE),
    (TrialInput([1, 2, 3, 4]), InvalidOutputReason.CANDIDATE_TYPE),
    (TrialInput((1, 2)), InvalidOutputReason.WIDTH),
    (TrialInput((1, 2, 3, 16)), InvalidOutputReason.VALUES),
    (TrialInput((1, 2, 3, -1)), InvalidOutputReason.VALUES),
    (TrialInput((True, 2, 3, 4)), InvalidOutputReason.VALUES),
    (TrialInput((1.0, 2, 3, 4)), InvalidOutputReason.VALUES),
])
def test_invalid_output_is_rejected_before_dispatch_without_budget_charge(candidate, reason):
    executor = Mock()
    owner = make_session(executor)
    adapter = Mock(wraps=owner.strategy_api())
    strategy = FixedStrategy([candidate, TRIAL])
    initial = owner.result()
    record = run_strategy(strategy, adapter)
    assert record.termination is TerminationReason.INVALID_OUTPUT
    assert record.invalid_output is reason
    assert record.evaluation == initial == owner.result()
    assert record.evaluation.infrastructure_failures == 0
    assert not record.evaluation.aborted
    adapter.execute.assert_not_called()
    executor.assert_not_called()
    strategy.observe.assert_not_called()
    strategy.propose.assert_called_once()


def test_candidate_subclasses_cannot_attach_extra_strategy_state():
    class ExtendedCandidate(TrialInput):
        extra = "unapproved state"

    executor = Mock()
    owner = make_session(executor)
    record = run_strategy(FixedStrategy([ExtendedCandidate(TRIAL.values)]), owner.strategy_api())
    assert record.invalid_output is InvalidOutputReason.CANDIDATE_TYPE
    executor.assert_not_called()


def test_invalid_output_after_execution_preserves_existing_accounting():
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor)
    strategy = FixedStrategy([TRIAL, TrialInput((1, 2)), TRIAL])
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.INVALID_OUTPUT
    assert record.invalid_output is InvalidOutputReason.WIDTH
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == 1
    assert record.evaluation.infrastructure_failures == 0
    assert record.evaluation.budget_remaining == 2
    assert not record.evaluation.aborted
    executor.assert_called_once()
    strategy.observe.assert_called_once()


def test_input_width_and_bounds_come_from_description():
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor, budget=1, space=InputSpace(2, 10, 20))
    candidate = TrialInput((10, 20))
    strategy = FixedStrategy([candidate])
    record = run_strategy(strategy, owner.strategy_api())
    assert strategy.start.call_args.args[0].input_space == InputSpace(2, 10, 20)
    assert record.termination is TerminationReason.BUDGET_EXHAUSTED
    executor.assert_called_once_with((10, 20))


def test_infrastructure_failure_stops_without_leaking_administrator_diagnostics():
    secret = "private source.c /firmware/image.elf GDB stderr secret"
    executor = Mock(side_effect=[Observation(False, stdout=secret, stderr=secret), Observation(True, True)])
    owner = make_session(executor)
    strategy = FixedStrategy([TRIAL, TRIAL])
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation.aborted
    assert record.evaluation.attempted_executions == record.evaluation.infrastructure_failures == 1
    assert record.evaluation.successful_executions == 0
    assert strategy.observe.call_args.args[1].status == "infrastructure_failure"
    assert secret in owner.diagnostics()[0]["stderr"]
    public = [asdict(record), asdict(strategy.start.call_args.args[0]), asdict(strategy.observe.call_args.args[1])]
    serialized = json.dumps(public)
    for forbidden in ("source.c", "image.elf", "GDB", "stderr", "secret", "held_out", "manifest", "oracle"):
        assert forbidden not in serialized
    strategy.propose.assert_called_once()
    executor.assert_called_once()


@pytest.mark.parametrize("state", ["zero_budget", "discovery", "aborted", "discovery_then_aborted"])
def test_already_terminal_session_does_not_start_strategy(state):
    owner = make_session(Mock(side_effect=[Observation(True, True), Observation(False)]), budget=0 if state == "zero_budget" else 3)
    if state in {"discovery", "discovery_then_aborted"}:
        owner.execute(TRIAL)
    if state == "aborted":
        owner = make_session(Mock(return_value=Observation(False)))
        owner.execute(TRIAL)
    if state == "discovery_then_aborted":
        owner.execute(TRIAL)
    initial = owner.result()
    strategy = FixedStrategy([])
    record = run_strategy(strategy, owner.strategy_api())
    expected = {"zero_budget": TerminationReason.BUDGET_EXHAUSTED, "discovery": TerminationReason.FAILURE_DISCOVERED}
    assert record.termination is expected.get(state, TerminationReason.SESSION_ABORTED)
    assert record.evaluation == initial
    strategy.start.assert_not_called()
    strategy.propose.assert_not_called()
    strategy.observe.assert_not_called()


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_runner_preserves_interruption_semantics_and_evaluator_accounting(interruption_type):
    interruption = interruption_type("administrator-owned interruption")
    executor = Mock(side_effect=[interruption, Observation(True, True)])
    owner = make_session(executor)
    strategy = FixedStrategy([TRIAL, TRIAL])
    with pytest.raises(interruption_type) as caught:
        run_strategy(strategy, owner.strategy_api())
    assert caught.value is interruption
    result = owner.result()
    assert result.aborted
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0
    strategy.observe.assert_not_called()
    record = run_strategy(FixedStrategy([]), owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation == result
    executor.assert_called_once()


def test_strategy_cannot_forge_counters_or_feedback():
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor, budget=1)
    strategy = FixedStrategy([TRIAL])
    strategy.attempted_executions = 999
    strategy.failure_found = True
    strategy.observe.return_value = {"execution_index": 0, "failure_found": True, "budget_remaining": 999}
    record = run_strategy(strategy, owner.strategy_api())
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == 1
    assert record.evaluation.budget_remaining == 0
    assert not record.evaluation.failure_found


def test_run_retains_exact_evaluator_result_object():
    owner = make_session(Mock(return_value=Observation(True)), budget=1)
    snapshots = []
    adapter = Mock(wraps=owner.strategy_api())

    def result():
        snapshots.append(owner.result())
        return snapshots[-1]

    adapter.result.side_effect = result
    record = run_strategy(FixedStrategy([TRIAL]), adapter)
    assert record.evaluation is snapshots[-1]


def test_metadata_and_run_records_are_immutable_canonical_public_snapshots():
    metadata = StrategyMetadata("test-double", (("z", False), ("a", 1), ("scale", 1.5), ("optional", None)), seed=7)
    assert metadata.configuration == (("a", 1), ("optional", None), ("scale", 1.5), ("z", False))
    assert metadata == StrategyMetadata("test-double", tuple(reversed(metadata.configuration)), seed=7)
    assert json.dumps(asdict(metadata), allow_nan=False) == json.dumps(asdict(StrategyMetadata("test-double", metadata.configuration, seed=7)), allow_nan=False)
    owner = make_session(Mock())
    record = run_strategy(FixedStrategy([None], metadata), owner.strategy_api())
    assert record.strategy is metadata
    assert {field.name for field in fields(StrategyMetadata)} == {"name", "configuration", "seed"}
    assert {field.name for field in fields(StrategyRun)} == {"evaluation", "strategy", "termination", "invalid_output"}
    with pytest.raises(FrozenInstanceError):
        metadata.seed = 8
    with pytest.raises(FrozenInstanceError):
        record.termination = TerminationReason.FAILURE_DISCOVERED


@pytest.mark.parametrize("kwargs", [
    {"name": ""}, {"name": 1}, {"seed": True}, {"seed": "7"},
    {"configuration": []}, {"configuration": (["a", 1],)},
    {"configuration": (("a", 1), ("a", 2))}, {"configuration": (("", 1),)},
    {"configuration": (("a", {}),)}, {"configuration": (("a", Mock()),)},
    {"configuration": (("a", float("nan")),)}, {"configuration": (("a", float("inf")),)},
])
def test_metadata_rejects_mutable_or_ambiguous_configuration(kwargs):
    with pytest.raises(ValueError):
        StrategyMetadata(**({"name": "test-double"} | kwargs))


def test_invalid_metadata_is_rejected_without_session_access():
    strategy = FixedStrategy([], metadata={"name": "mutable"})
    adapter = Mock()
    with pytest.raises(ValueError, match="StrategyMetadata"):
        run_strategy(strategy, adapter)
    assert adapter.mock_calls == []


def test_metadata_snapshot_survives_strategy_replacing_its_metadata():
    strategy = FixedStrategy([None])
    strategy.start.side_effect = lambda description: setattr(strategy, "metadata", StrategyMetadata("changed", seed=99))
    owner = make_session(Mock())
    record = run_strategy(strategy, owner.strategy_api())
    assert record.strategy is METADATA
    assert strategy.metadata.name == "changed"
    assert record.evaluation == owner.result()


@pytest.mark.parametrize("callback", ["start", "propose", "observe"])
def test_strategy_callback_errors_propagate_without_fabricated_execution(callback):
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor)
    strategy = FixedStrategy([TRIAL])
    error = RuntimeError("strategy callback failed")
    getattr(strategy, callback).side_effect = error
    with pytest.raises(RuntimeError) as caught:
        run_strategy(strategy, owner.strategy_api())
    assert caught.value is error
    result = owner.result()
    assert result.attempted_executions == (1 if callback == "observe" else 0)
    assert result.infrastructure_failures == 0 and not result.aborted


def test_runner_with_real_registry_arm_image_and_strategy_adapter(tmp_path):
    registry = BenchmarkRegistry()
    benchmark = registry.select("development")[0]
    built = registry.build(benchmark.benchmark_id, tmp_path / "trial.elf")
    assert built["success"], built["stderr"]
    owner = registry.open_session(benchmark.benchmark_id, 1, METADATA.name, random_seed=METADATA.seed)
    space = owner.describe().input_space
    candidate = TrialInput((space.minimum,) * space.width)
    strategy = FixedStrategy([candidate])
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.BUDGET_EXHAUSTED, owner.diagnostics()
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == 1
    assert record.evaluation.infrastructure_failures == 0
    assert strategy.observe.call_args.args[1].status == "safe"
