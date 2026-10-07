import itertools
import json
import tracemalloc
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import ExperimentSpec, InputSpace, TrialFeedback, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.monitor.monitor import observe_symbol
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.runner import run_strategy


ID = "b-3874d6a4a92f46758d73854abf0a08df"


def description(space, budget=100):
    return ExperimentSpec(ID, space, budget)


def remaining_candidates(strategy):
    return [trial.values for trial in iter(strategy.propose, None)]


@pytest.mark.parametrize("space", [
    InputSpace(1, 0, 2), InputSpace(2, 0, 2), InputSpace(3, 1, 2),
    InputSpace(2, 5, 7), InputSpace(4, 9, 9),
    InputSpace(1, 0xFFFFFFFF, 0xFFFFFFFF), InputSpace(2, 0xFFFFFFFE, 0xFFFFFFFF),
])
def test_complete_cartesian_product_is_ordered_unique_and_finitely_exhausted(space):
    strategy = EnumerativeStrategy()
    strategy.start(description(space))
    actual = remaining_candidates(strategy)
    expected = list(itertools.product(range(space.minimum, space.maximum + 1), repeat=space.width))
    assert actual == expected
    assert len(actual) == len(set(actual)) == (space.maximum - space.minimum + 1) ** space.width
    assert all(space.accepts(values) for values in actual)
    for _ in range(5):
        assert strategy.propose() is None


def test_explicit_lexicographic_order_last_position_changes_fastest():
    strategy = EnumerativeStrategy()
    strategy.start(description(InputSpace(2, 0, 2)))
    assert remaining_candidates(strategy) == [
        (0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2),
    ]


def test_propose_requires_start_and_candidates_are_immutable():
    strategy = EnumerativeStrategy()
    with pytest.raises(RuntimeError, match="must be started"):
        strategy.propose()
    strategy.start(description(InputSpace(2, 3, 4)))
    candidate = strategy.propose()
    assert type(candidate) is TrialInput
    assert type(candidate.values) is tuple
    with pytest.raises(FrozenInstanceError):
        candidate.values = (9, 9)
    assert candidate.values == (3, 3)
    assert strategy.propose().values == (3, 4)


def test_fresh_equivalent_strategies_produce_identical_sequences():
    first, second = EnumerativeStrategy(), EnumerativeStrategy()
    spec = description(InputSpace(3, 2, 3))
    first.start(spec)
    second.start(spec)
    assert remaining_candidates(first) == remaining_candidates(second)


@pytest.mark.parametrize("exhaust_first", [False, True])
def test_repeated_start_resets_before_and_after_domain_exhaustion(exhaust_first):
    strategy = EnumerativeStrategy()
    spec = description(InputSpace(2, 0, 1))
    strategy.start(spec)
    assert strategy.propose().values == (0, 0)
    if exhaust_first:
        remaining_candidates(strategy)
        assert strategy.propose() is None
    strategy.start(spec)
    assert remaining_candidates(strategy) == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_restart_uses_new_public_shape_and_bounds():
    strategy = EnumerativeStrategy()
    strategy.start(description(InputSpace(2, 0, 2)))
    strategy.propose()
    strategy.start(description(InputSpace(1, 5, 6)))
    assert remaining_candidates(strategy) == [(5,), (6,)]


def test_large_domain_initialization_and_proposals_use_bounded_memory():
    # A cached range/product pool would allocate megabytes; a full product is
    # infeasible. The cursor needs only eight values regardless of domain size.
    strategy = EnumerativeStrategy()
    spec = description(InputSpace(8, 0, 65535))
    tracemalloc.start()
    try:
        strategy.start(spec)
        candidates = [strategy.propose().values for _ in range(8)]
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert candidates == [(0,) * 7 + (value,) for value in range(8)]
    assert peak < 512 * 1024


def test_metadata_is_stable_and_contains_no_cursor_or_seed():
    strategy = EnumerativeStrategy()
    metadata = strategy.metadata
    assert metadata == StrategyMetadata("enumerative", (), None)
    assert asdict(metadata) == {"name": "enumerative", "configuration": (), "seed": None}
    strategy.start(description(InputSpace(2, 0, 1)))
    strategy.propose()
    assert strategy.metadata is metadata
    assert strategy.metadata == EnumerativeStrategy().metadata
    with pytest.raises(FrozenInstanceError):
        metadata.name = "changed"
    assert {name for name in dir(strategy) if not name.startswith("_")} == {"metadata", "start", "propose", "observe"}


@pytest.mark.parametrize("status", ["safe", "triggered", "infrastructure_failure", "budget_exhausted", "session_aborted", "invalid_input"])
def test_public_feedback_never_guides_or_changes_enumeration(status):
    strategy = EnumerativeStrategy()
    strategy.start(description(InputSpace(2, 0, 1)))
    candidate = strategy.propose()
    strategy.observe(candidate, TrialFeedback(status, 999, 0))
    assert remaining_candidates(strategy) == [(0, 1), (1, 0), (1, 1)]


def test_only_public_input_shape_affects_enumeration():
    first, second = EnumerativeStrategy(), EnumerativeStrategy()
    space = InputSpace(2, 1, 2)
    first.start(description(space, budget=1))
    second.start(ExperimentSpec("b-" + "0" * 32, space, 1000))
    assert remaining_candidates(first) == remaining_candidates(second)


def make_session(executor, budget, space=InputSpace(2, 0, 2)):
    return EvaluationSession(ID, space, budget, "enumerative", executor)


def test_strategy_lifecycle_receives_only_public_description_and_feedback():
    secret = "private source.c /firmware/image.elf GDB output"
    owner = make_session(Mock(return_value=Observation(True, stdout=secret, stderr=secret)), budget=1)
    strategy = EnumerativeStrategy()
    strategy.start = Mock(wraps=strategy.start)
    strategy.observe = Mock(wraps=strategy.observe)
    record = run_strategy(strategy, owner.strategy_api())
    spec, = strategy.start.call_args.args
    assert type(spec) is ExperimentSpec
    assert asdict(spec) == {
        "benchmark_id": ID, "input_space": {"width": 2, "minimum": 0, "maximum": 2}, "execution_budget": 1,
    }
    candidate, feedback = strategy.observe.call_args.args
    assert type(candidate) is TrialInput and candidate.values == (0, 0)
    assert type(feedback) is TrialFeedback
    assert asdict(feedback) == {
        "status": "safe", "execution_index": 1, "budget_remaining": 0, "execution_signature": None,
    }
    for item in (spec, candidate, feedback, strategy.metadata):
        for hidden in ("source", "image", "registry", "evaluator", "diagnostics", "execute", "_executor"):
            assert not hasattr(item, hidden)
    assert secret not in json.dumps([asdict(spec), asdict(feedback), asdict(record)])


@pytest.mark.parametrize("trigger", [(0, 0), (1, 1), (2, 2)])
def test_runner_discovery_uses_real_index_and_stops_dispatch_immediately(trigger):
    executor = Mock(side_effect=lambda values: Observation(True, values == trigger))
    owner = make_session(executor, budget=10)
    strategy = EnumerativeStrategy()
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    ordered = list(itertools.product(range(3), repeat=2))
    index = ordered.index(trigger) + 1
    assert [call.args[0] for call in executor.call_args_list] == ordered[:index]
    assert strategy.propose.call_count == index
    assert record.termination is TerminationReason.FAILURE_DISCOVERED
    result = record.evaluation
    assert result == owner.result()
    assert result.attempted_executions == result.successful_executions == index
    assert result.first_failure_execution == index
    assert result.time_to_first_failure_seconds is not None
    assert result.infrastructure_failures == 0
    assert result.failure_triggering_executions == 1


@pytest.mark.parametrize("budget", [0, 1, 4, 9, 12])
def test_runner_budget_and_domain_exhaustion_do_not_charge_extra_executions(budget):
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor, budget)
    strategy = EnumerativeStrategy()
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    ordered = list(itertools.product(range(3), repeat=2))
    expected = min(budget, len(ordered))
    assert [call.args[0] for call in executor.call_args_list] == ordered[:expected]
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == expected
    assert record.evaluation.infrastructure_failures == 0
    assert not record.evaluation.failure_found
    assert record.evaluation.budget_remaining == budget - expected
    if budget > len(ordered):
        assert record.termination is TerminationReason.STRATEGY_STOPPED
        assert strategy.propose.call_count == expected + 1
        assert not record.evaluation.budget_exhausted
    else:
        assert record.termination is TerminationReason.BUDGET_EXHAUSTED
        assert strategy.propose.call_count == expected


@pytest.mark.parametrize("safe_prefix", [0, 2])
def test_infrastructure_failure_aborts_without_dispatching_later_candidates(safe_prefix):
    secret = "private GDB stderr /firmware/source.c"
    executor = Mock(side_effect=[Observation(True)] * safe_prefix + [Observation(False, stderr=secret), Observation(True, True)])
    owner = make_session(executor, budget=9)
    strategy = EnumerativeStrategy()
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation == owner.result()
    assert record.evaluation.aborted
    assert record.evaluation.attempted_executions == safe_prefix + 1
    assert record.evaluation.successful_executions == safe_prefix
    assert record.evaluation.infrastructure_failures == 1
    assert not record.evaluation.failure_found
    assert strategy.propose.call_count == executor.call_count == safe_prefix + 1
    assert secret in owner.diagnostics()[0]["stderr"]
    assert secret not in json.dumps(asdict(record))


def test_aborted_session_never_starts_enumeration_or_dispatches_again():
    executor = Mock(return_value=Observation(False))
    owner = make_session(executor, budget=3)
    owner.execute(TrialInput((0, 0)))
    strategy = EnumerativeStrategy()
    strategy.start = Mock(wraps=strategy.start)
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation == owner.result()
    strategy.start.assert_not_called()
    executor.assert_called_once()


def test_real_arm_threshold_discovery_through_opaque_adapter(cortex_m_corpus):
    # Administrator-only fixture/instrumentation. The production strategy gets
    # only the public scalar domain, never the descriptor, ELF, or oracle.
    benchmark, image = cortex_m_corpus["threshold"]

    def execute(values):
        observed = observe_symbol(
            str(image), benchmark.failure_symbol, benchmark.breakpoint,
            input_values={benchmark.input_symbol: values[0]},
        )
        success = observed["success"] and observed["value"] in (0, 1)
        return Observation(success, success and observed["value"] == 1, observed["stdout"], observed["stderr"])

    executor = Mock(side_effect=execute)
    owner = make_session(executor, budget=8, space=InputSpace(1, benchmark.input_min, benchmark.input_max))
    strategy = EnumerativeStrategy()
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    # Ground truth validates the result after the run; it is not strategy input.
    oracle = json.loads((Path(__file__).parent / "data/cortex_m_v1_ground_truth.json").read_text())
    first_trigger = oracle["benchmarks"]["threshold"]["trigger_intervals"][0][0]
    index = first_trigger - benchmark.input_min + 1
    result = record.evaluation
    assert record.termination is TerminationReason.FAILURE_DISCOVERED, owner.diagnostics()
    assert result == owner.result()
    assert result.attempted_executions == result.successful_executions == result.first_failure_execution == index
    assert result.infrastructure_failures == 0 and not result.aborted
    assert result.failure_triggering_executions == 1
    assert result.budget_remaining == 8 - index
    assert strategy.propose.call_count == executor.call_count == index
    assert [call.args[0] for call in executor.call_args_list] == [(value,) for value in range(benchmark.input_min, first_trigger + 1)]
