import itertools
import random
import tracemalloc
from collections import Counter
from dataclasses import FrozenInstanceError, asdict
from unittest.mock import Mock, call

import pytest

from src.firmavex.evaluation.api import ExperimentSpec, InputSpace, TrialFeedback, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.monitor.monitor import observe_symbol
from src.firmavex.strategies import random as random_module
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.random import RandomStrategy, _decode_index
from src.firmavex.strategies.runner import run_strategy


# Declared test seeds, not selected using firmware outcomes. No seed sweeps.
SEED = 42
ID = "b-3874d6a4a92f46758d73854abf0a08df"


def description(space, budget=100):
    return ExperimentSpec(ID, space, budget)


def candidates(strategy):
    return [trial.values for trial in iter(strategy.propose, None)]


def sequence(space, seed=SEED):
    strategy = RandomStrategy(seed)
    strategy.start(description(space))
    return candidates(strategy)


@pytest.mark.parametrize("space", [
    InputSpace(1, 0, 2), InputSpace(2, 0, 2), InputSpace(3, 1, 2),
    InputSpace(2, 5, 7), InputSpace(4, 9, 9),
    InputSpace(1, 0xFFFFFFFF, 0xFFFFFFFF), InputSpace(2, 0xFFFFFFFE, 0xFFFFFFFF),
])
def test_seeded_sequence_is_reproducible_unique_complete_and_in_bounds(space):
    strategy = RandomStrategy(SEED)
    strategy.start(description(space))
    actual = candidates(strategy)
    expected = set(itertools.product(range(space.minimum, space.maximum + 1), repeat=space.width))
    assert len(actual) == len(set(actual)) == len(expected)
    assert set(actual) == expected
    assert actual == sequence(space)
    assert all(space.accepts(values) and len(values) == space.width for values in actual)
    for _ in range(5):
        assert strategy.propose() is None


def test_two_predeclared_seeds_produce_different_orders():
    space = InputSpace(3, 0, 3)
    assert sequence(space, seed=42) != sequence(space, seed=99)


@pytest.mark.parametrize("seed", [0, -7, 2 ** 130])
def test_all_explicit_integer_seeds_are_preserved_and_reproduce(seed):
    first, second = RandomStrategy(seed), RandomStrategy(seed)
    spec = description(InputSpace(2, 1, 3))
    first.start(spec)
    second.start(spec)
    assert first.metadata.seed == seed
    assert candidates(first) == candidates(second)


@pytest.mark.parametrize("seed", [None, True, False, 1.5, "42", [], {}, object()])
def test_invalid_seeds_fail_before_rng_or_firmware_use(monkeypatch, seed):
    engine = Mock()
    monkeypatch.setattr(random_module, "Random", engine)
    with pytest.raises(ValueError, match="explicit integer seed"):
        RandomStrategy(seed)
    engine.assert_not_called()


def test_seed_argument_is_required():
    with pytest.raises(TypeError):
        RandomStrategy()


def test_propose_requires_start_and_returns_immutable_trial_input():
    strategy = RandomStrategy(SEED)
    with pytest.raises(RuntimeError, match="must be started"):
        strategy.propose()
    strategy.start(description(InputSpace(2, 3, 4)))
    candidate = strategy.propose()
    assert type(candidate) is TrialInput and type(candidate.values) is tuple
    snapshot = candidate.values
    with pytest.raises(FrozenInstanceError):
        candidate.values = (9, 9)
    strategy.propose()
    assert candidate.values == snapshot


@pytest.mark.parametrize("exhaust_first", [False, True])
def test_repeated_start_resets_rng_and_sampling_before_and_after_exhaustion(exhaust_first):
    strategy = RandomStrategy(SEED)
    spec = description(InputSpace(2, 0, 2))
    strategy.start(spec)
    strategy.propose()
    if exhaust_first:
        candidates(strategy)
        assert strategy.propose() is None
    strategy.start(spec)
    assert candidates(strategy) == sequence(spec.input_space)


def test_restart_with_different_space_discards_prior_mapping():
    strategy = RandomStrategy(SEED)
    strategy.start(description(InputSpace(3, 0, 2)))
    for _ in range(5):
        strategy.propose()
    space = InputSpace(1, 5, 7)
    strategy.start(description(space))
    assert candidates(strategy) == sequence(space)


def test_metadata_is_stable_immutable_and_hides_rng_and_sampling_state():
    strategy = RandomStrategy(SEED)
    metadata = strategy.metadata
    assert metadata == StrategyMetadata("random", (), seed=SEED)
    assert asdict(metadata) == {"name": "random", "configuration": (), "seed": SEED}
    strategy.start(description(InputSpace(2, 0, 2)))
    strategy.propose()
    assert strategy.metadata is metadata
    with pytest.raises(FrozenInstanceError):
        metadata.seed = 99
    assert {name for name in dir(strategy) if not name.startswith("_")} == {"metadata", "start", "propose", "observe"}


def test_global_random_state_is_neither_used_nor_mutated(monkeypatch):
    state = random.getstate()
    forbidden = Mock(side_effect=AssertionError("Global RNG must not be used"))
    for name in ("seed", "random", "randrange", "randint", "choice", "shuffle", "sample", "getrandbits"):
        monkeypatch.setattr(random, name, forbidden)
    strategy = RandomStrategy(SEED)
    spec = description(InputSpace(2, 0, 3))
    strategy.start(spec)
    first = candidates(strategy)
    strategy.start(spec)
    assert candidates(strategy) == first
    assert random.getstate() == state
    forbidden.assert_not_called()


@pytest.mark.parametrize("status", ["safe", "triggered", "infrastructure_failure", "budget_exhausted", "session_aborted", "invalid_input"])
def test_public_feedback_does_not_change_order(status):
    space = InputSpace(2, 0, 2)
    strategy = RandomStrategy(SEED)
    strategy.start(description(space))
    actual = []
    for trial in iter(strategy.propose, None):
        actual.append(trial.values)
        strategy.observe(trial, TrialFeedback(status, 999, 0))
    assert actual == sequence(space)


def test_benchmark_id_and_budget_do_not_change_seeded_order():
    space = InputSpace(2, 1, 3)
    first, second = RandomStrategy(SEED), RandomStrategy(SEED)
    first.start(description(space, budget=1))
    second.start(ExperimentSpec("b-" + "0" * 32, space, 1000))
    assert candidates(first) == candidates(second)


@pytest.mark.parametrize("space", [InputSpace(1, 5, 7), InputSpace(2, 0, 2), InputSpace(3, 1, 2), InputSpace(4, 9, 9)])
def test_index_mapping_matches_enumerative_last_position_fastest_order(space):
    enumerative = EnumerativeStrategy()
    enumerative.start(description(space))
    expected = [trial.values for trial in iter(enumerative.propose, None)]
    base = space.maximum - space.minimum + 1
    assert [_decode_index(index, space, base).values for index in range(base ** space.width)] == expected


def test_every_legal_uniform_draw_path_maps_to_exactly_one_permutation(monkeypatch):
    # Structural verification, not a statistical test or seed search. All 4!
    # legal draw paths have probability 1/(4*3*2*1) under uniform slot draws.
    permutations = Counter()
    domain = list(itertools.product(range(2), repeat=2))
    for path in itertools.product(range(4), range(3), range(2), (0,)):
        engine = Mock()
        engine.randrange.side_effect = path
        factory = Mock(return_value=engine)
        monkeypatch.setattr(random_module, "Random", factory)
        strategy = RandomStrategy(SEED)
        strategy.start(description(InputSpace(2, 0, 1)))
        actual = tuple(candidates(strategy))
        assert len(actual) == len(set(actual)) == 4
        assert set(actual) == set(domain)
        assert strategy.propose() is None
        assert engine.randrange.call_args_list == [call(4), call(3), call(2), call(1)]
        factory.assert_called_once_with(SEED)
        engine.seed.assert_called_once_with(SEED)
        permutations[actual] += 1
    assert set(permutations) == set(itertools.permutations(domain))
    assert set(permutations.values()) == {1}


def test_huge_domain_uses_small_initial_state_and_sparse_proposal_memory():
    # The domain has 2**128 tuples; index arithmetic exceeds machine-size ranges.
    spec = description(InputSpace(8, 0, 65535))
    tracemalloc.start()
    try:
        strategy = RandomStrategy(SEED)
        strategy.start(spec)
        _, initial_peak = tracemalloc.get_traced_memory()
        seen = set()
        for _ in range(256):
            candidate = strategy.propose()
            assert spec.input_space.accepts(candidate.values)
            seen.add(candidate.values)
        _, proposal_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(seen) == 256
    assert initial_peak < 64 * 1024
    assert proposal_peak < 512 * 1024


def make_session(executor, budget, space=InputSpace(2, 0, 2)):
    return EvaluationSession(ID, space, budget, "random", executor, random_seed=SEED)


@pytest.mark.parametrize("trigger_index", [1, 4, 9])
def test_runner_discovery_keeps_evaluator_index_and_stops_dispatch(trigger_index):
    space = InputSpace(2, 0, 2)
    expected = sequence(space)
    # Fake-executor outcome placement tests termination, not benchmark tuning.
    trigger = expected[trigger_index - 1]
    executor = Mock(side_effect=lambda values: Observation(True, values == trigger))
    owner = make_session(executor, budget=10, space=space)
    strategy = RandomStrategy(SEED)
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.FAILURE_DISCOVERED
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == trigger_index
    assert record.evaluation.first_failure_execution == trigger_index
    assert record.evaluation.time_to_first_failure_seconds is not None
    assert record.evaluation.infrastructure_failures == 0
    assert [item.args[0] for item in executor.call_args_list] == expected[:trigger_index]
    assert strategy.propose.call_count == trigger_index


@pytest.mark.parametrize("budget", [0, 1, 4, 9, 12])
def test_runner_respects_budget_and_domain_exhaustion_without_extra_execution(budget):
    executor = Mock(return_value=Observation(True))
    owner = make_session(executor, budget)
    strategy = RandomStrategy(SEED)
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    expected = sequence(InputSpace(2, 0, 2))
    count = min(budget, len(expected))
    assert [item.args[0] for item in executor.call_args_list] == expected[:count]
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == count
    assert record.evaluation.infrastructure_failures == 0
    assert record.evaluation.budget_remaining == budget - count
    assert not record.evaluation.failure_found
    if budget > len(expected):
        assert record.termination is TerminationReason.STRATEGY_STOPPED
        assert strategy.propose.call_count == count + 1
    else:
        assert record.termination is TerminationReason.BUDGET_EXHAUSTED
        assert strategy.propose.call_count == count


@pytest.mark.parametrize("safe_prefix", [0, 2])
def test_infrastructure_failure_aborts_before_later_proposals(safe_prefix):
    executor = Mock(side_effect=[Observation(True)] * safe_prefix + [Observation(False, True, stderr="private GDB error"), Observation(True, True)])
    owner = make_session(executor, budget=9)
    strategy = RandomStrategy(SEED)
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
    assert "private GDB error" in owner.diagnostics()[0]["stderr"]
    assert "private GDB error" not in str(asdict(record))


def test_same_seed_replays_dispatched_candidates_with_deterministic_executor():
    dispatched = []
    for _ in range(2):
        executor = Mock(return_value=Observation(True))
        owner = make_session(executor, budget=5)
        record = run_strategy(RandomStrategy(SEED), owner.strategy_api())
        assert record.evaluation.attempted_executions == 5
        dispatched.append([item.args[0] for item in executor.call_args_list])
    assert dispatched[0] == dispatched[1]


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_runner_preserves_control_flow_interruption_and_aborted_accounting(interruption_type):
    interruption = interruption_type("private cancellation")
    executor = Mock(side_effect=[interruption, Observation(True, True)])
    owner = make_session(executor, budget=3)
    with pytest.raises(interruption_type) as caught:
        run_strategy(RandomStrategy(SEED), owner.strategy_api())
    assert caught.value is interruption
    result = owner.result()
    assert result.aborted
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0
    record = run_strategy(RandomStrategy(SEED), owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation == result
    executor.assert_called_once()


def test_production_strategy_receives_only_public_records():
    secret = "private source.c /firmware/image.elf GDB output"
    owner = make_session(Mock(return_value=Observation(True, stdout=secret, stderr=secret)), budget=1)
    strategy = RandomStrategy(SEED)
    strategy.start = Mock(wraps=strategy.start)
    strategy.observe = Mock(wraps=strategy.observe)
    record = run_strategy(strategy, owner.strategy_api())
    spec, = strategy.start.call_args.args
    assert type(spec) is ExperimentSpec
    assert asdict(spec) == {
        "benchmark_id": ID, "input_space": {"width": 2, "minimum": 0, "maximum": 2}, "execution_budget": 1,
    }
    candidate, feedback = strategy.observe.call_args.args
    assert type(candidate) is TrialInput
    assert type(feedback) is TrialFeedback
    assert asdict(feedback) == {
        "status": "safe", "execution_index": 1, "budget_remaining": 0, "execution_signature": None,
    }
    for item in (spec, candidate, feedback, strategy.metadata):
        for hidden in ("source", "image", "registry", "evaluator", "diagnostics", "execute", "_executor"):
            assert not hasattr(item, hidden)
    assert secret not in str([asdict(spec), asdict(feedback), asdict(record)])


def test_real_arm_dispatch_with_predeclared_seed_and_tiny_test_domain(cortex_m_corpus):
    # SEED=42 was declared independently of firmware outcomes. This bounded
    # administrator test setup proves dispatch, not random-search discovery.
    benchmark, image = cortex_m_corpus["threshold"]
    space = InputSpace(1, 0, 2)
    expected = sequence(space, seed=SEED)

    def execute(values):
        observed = observe_symbol(
            str(image), benchmark.failure_symbol, benchmark.breakpoint,
            input_values={benchmark.input_symbol: values[0]},
        )
        success = observed["success"] and observed["value"] in (0, 1)
        return Observation(success, success and observed["value"] == 1, observed["stdout"], observed["stderr"])

    executor = Mock(side_effect=execute)
    owner = make_session(executor, budget=5, space=space)
    record = run_strategy(RandomStrategy(SEED), owner.strategy_api())
    assert record.termination is TerminationReason.STRATEGY_STOPPED, owner.diagnostics()
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == 3
    assert record.evaluation.infrastructure_failures == 0 and not record.evaluation.aborted
    assert not record.evaluation.failure_found
    assert record.evaluation.budget_remaining == 2
    assert record.strategy == StrategyMetadata("random", seed=SEED)
    assert record.evaluation.random_seed == SEED
    assert [item.args[0] for item in executor.call_args_list] == expected
