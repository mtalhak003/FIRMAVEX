"""Synthetic public-history checks, not firmware-outcome tuning or seed sweeps."""

import ast
import inspect
import itertools
import random
import tracemalloc
from dataclasses import FrozenInstanceError, asdict
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import (
    ExecutionSignature, ExperimentSpec, InputSpace, TrialFeedback, TrialInput,
)
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.strategies import guided as guided_module
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.guided import GuidedStrategy, guided_metadata
from src.firmavex.strategies.random import RandomStrategy
from src.firmavex.strategies.runner import run_strategy


SEED = 42  # Declared independently of firmware outcomes.
ID = "b-3874d6a4a92f46758d73854abf0a08df"
SIGNATURE_A = ExecutionSignature("a" * 64)
SIGNATURE_B = ExecutionSignature("b" * 64)


def description(space, budget=100):
    return ExperimentSpec(ID, space, budget)


def feedback(signature=None, *, status="safe", index=1, remaining=99):
    return TrialFeedback(status, index, remaining, signature)


def collect(strategy, signature_for_index=lambda index: None):
    result = []
    for index, trial in enumerate(iter(strategy.propose, None)):
        result.append(trial.values)
        strategy.observe(trial, feedback(signature_for_index(index)))
    return result


def replay(space, *, seed=SEED, archive_size=32, mutation_attempts=8, signatures=None):
    strategy = GuidedStrategy(seed, archive_size=archive_size, mutation_attempts=mutation_attempts)
    strategy.start(description(space))
    return collect(strategy, signatures or (lambda index: ExecutionSignature(f"{index:064x}")))


@pytest.mark.parametrize("space", [
    InputSpace(1, 0, 2), InputSpace(2, 0, 2), InputSpace(3, 1, 2),
    InputSpace(2, 5, 7), InputSpace(4, 9, 9),
    InputSpace(1, 0xFFFFFFFF, 0xFFFFFFFF), InputSpace(2, 0xFFFFFFFE, 0xFFFFFFFF),
])
def test_guidance_remains_unique_in_bounds_complete_and_finitely_exhausted(space):
    strategy = GuidedStrategy(SEED, archive_size=2, mutation_attempts=2)
    strategy.start(description(space))
    actual = collect(strategy, lambda index: ExecutionSignature(f"{index:064x}"))
    expected = set(itertools.product(range(space.minimum, space.maximum + 1), repeat=space.width))
    assert len(actual) == len(set(actual)) == len(expected)
    assert set(actual) == expected
    assert all(space.accepts(values) for values in actual)
    assert actual == replay(space, archive_size=2, mutation_attempts=2)
    for _ in range(5):
        assert strategy.propose() is None


@pytest.mark.parametrize("seed", [0, -7, 2 ** 130])
def test_exact_integer_seed_is_preserved_and_replays(seed):
    space = InputSpace(2, 1, 3)
    strategy = GuidedStrategy(seed)
    assert strategy.metadata.seed == seed
    assert replay(space, seed=seed) == replay(space, seed=seed)


@pytest.mark.parametrize("signature", [None, SIGNATURE_A])
def test_missing_or_constant_signature_still_exhausts_the_complete_domain(signature):
    space = InputSpace(3, 0, 2)
    strategy = GuidedStrategy(SEED)
    strategy.start(description(space))
    actual = collect(strategy, lambda index: signature)
    assert len(actual) == len(set(actual)) == 27
    assert set(actual) == set(itertools.product(range(3), repeat=3))
    assert all(space.accepts(values) for values in actual)
    assert actual == replay(space, signatures=lambda index: signature)
    assert all(strategy.propose() is None for _ in range(5))


def test_positive_large_archive_setting_has_no_platform_integer_cap():
    # Public settings use exact Python integers, like seeds and domain indices.
    strategy = GuidedStrategy(SEED, archive_size=2 ** 130)
    assert strategy.metadata == guided_metadata(SEED, archive_size=2 ** 130)
    strategy.start(description(InputSpace(1, 0, 0)))
    trial = strategy.propose()
    strategy.observe(trial, feedback(SIGNATURE_A))
    assert list(strategy._parents) == [trial]
    assert strategy.propose() is None


@pytest.mark.parametrize("seed", [None, True, False, 1.5, "42", [], {}, object()])
def test_invalid_seeds_fail_before_rng_construction(monkeypatch, seed):
    engine = Mock()
    monkeypatch.setattr(guided_module, "Random", engine)
    with pytest.raises(ValueError, match="explicit integer seed"):
        GuidedStrategy(seed)
    with pytest.raises(ValueError, match="explicit integer seed"):
        guided_metadata(seed)
    engine.assert_not_called()


@pytest.mark.parametrize("name", ["archive_size", "mutation_attempts"])
@pytest.mark.parametrize("value", [0, -1, True, False, None, 1.5, "8"])
def test_configuration_requires_positive_exact_integers(monkeypatch, name, value):
    engine = Mock()
    monkeypatch.setattr(guided_module, "Random", engine)
    with pytest.raises(ValueError, match=f"{name} must be a positive integer"):
        GuidedStrategy(SEED, **{name: value})
    with pytest.raises(ValueError, match=f"{name} must be a positive integer"):
        guided_metadata(SEED, **{name: value})
    engine.assert_not_called()


def test_seed_is_required_and_metadata_helper_does_not_instantiate_sampler(monkeypatch):
    with pytest.raises(TypeError):
        GuidedStrategy()
    with pytest.raises(TypeError):
        guided_metadata()
    sampler, engine = Mock(), Mock()
    monkeypatch.setattr(guided_module, "RandomStrategy", sampler)
    monkeypatch.setattr(guided_module, "Random", engine)
    assert guided_metadata(SEED, archive_size=2, mutation_attempts=3) == StrategyMetadata(
        "guided", (("archive_size", 2), ("mutation_attempts", 3)), SEED,
    )
    sampler.assert_not_called()
    engine.assert_not_called()


def test_metadata_is_complete_immutable_stable_and_has_only_public_configuration():
    strategy = GuidedStrategy(SEED)
    metadata = strategy.metadata
    assert metadata == guided_metadata(SEED)
    assert asdict(metadata) == {
        "name": "guided", "configuration": (("archive_size", 32), ("mutation_attempts", 8)), "seed": SEED,
    }
    strategy.start(description(InputSpace(2, 0, 2)))
    trial = strategy.propose()
    strategy.observe(trial, feedback(SIGNATURE_A))
    assert strategy.metadata is metadata
    with pytest.raises(FrozenInstanceError):
        metadata.seed = 99
    assert {name for name in dir(strategy) if not name.startswith("_")} == {"metadata", "start", "propose", "observe"}


def test_lifecycle_requires_start_and_preserves_immutable_trial_snapshots():
    strategy = GuidedStrategy(SEED)
    with pytest.raises(RuntimeError, match="must be started"):
        strategy.propose()
    with pytest.raises(RuntimeError, match="must be started"):
        strategy.observe(TrialInput((0,)), feedback())
    strategy.start(description(InputSpace(2, 0, 2)))
    trial = strategy.propose()
    assert type(trial) is TrialInput and type(trial.values) is tuple
    snapshot = trial.values
    with pytest.raises(FrozenInstanceError):
        trial.values = (9, 9)
    strategy.observe(trial, feedback(SIGNATURE_A))
    strategy.propose()
    assert trial.values == snapshot


@pytest.mark.parametrize("exhaust_first", [False, True])
def test_start_resets_rng_visited_signatures_archive_and_exhaustion(exhaust_first):
    space = InputSpace(2, 0, 2)
    strategy = GuidedStrategy(SEED)
    strategy.start(description(space))
    trial = strategy.propose()
    strategy.observe(trial, feedback(SIGNATURE_A))
    if exhaust_first:
        collect(strategy, lambda index: SIGNATURE_B)
        assert strategy.propose() is None
    strategy.start(description(space))
    assert not strategy._visited and not strategy._seen_signatures and not strategy._parents
    assert collect(strategy, lambda index: ExecutionSignature(f"{index:064x}")) == replay(space)


def test_start_with_new_public_shape_discards_previous_state():
    strategy = GuidedStrategy(SEED)
    strategy.start(description(InputSpace(3, 0, 2)))
    for _ in range(5):
        trial = strategy.propose()
        strategy.observe(trial, feedback(SIGNATURE_A))
    space = InputSpace(1, 5, 7)
    strategy.start(description(space))
    assert collect(strategy, lambda index: SIGNATURE_A) == replay(space, signatures=lambda index: SIGNATURE_A)


def test_global_random_state_is_neither_read_nor_mutated(monkeypatch):
    state = random.getstate()
    forbidden = Mock(side_effect=AssertionError("Global RNG must not be used"))
    for name in ("seed", "random", "randrange", "randint", "choice", "shuffle", "sample", "getrandbits"):
        monkeypatch.setattr(random, name, forbidden)
    first = replay(InputSpace(2, 0, 3))
    assert replay(InputSpace(2, 0, 3)) == first
    assert random.getstate() == state
    forbidden.assert_not_called()


def test_new_signature_causally_changes_future_proposals_with_same_public_history():
    # Same two dispatched candidates, seed, status and counters. Only the second
    # signature changes; future proposals must demonstrate actual adaptation.
    repeated, novel = GuidedStrategy(SEED), GuidedStrategy(SEED)
    spec = description(InputSpace(3, 0, 3))
    for strategy in (repeated, novel):
        strategy.start(spec)
    first = repeated.propose()
    assert novel.propose() == first
    for strategy in (repeated, novel):
        strategy.observe(first, feedback(SIGNATURE_A))
    second = repeated.propose()
    assert novel.propose() == second
    repeated.observe(second, feedback(SIGNATURE_A, index=2, remaining=98))
    novel.observe(second, feedback(SIGNATURE_B, index=2, remaining=98))
    repeated_tail = collect(repeated, lambda index: SIGNATURE_A)
    novel_tail = collect(novel, lambda index: SIGNATURE_A)
    assert repeated_tail != novel_tail
    assert len(set(repeated_tail)) == len(repeated_tail)
    assert set(repeated_tail) == set(novel_tail)


def test_signature_text_is_opaque_and_only_equality_pattern_matters():
    space = InputSpace(3, 0, 2)
    first = replay(space, signatures=lambda index: SIGNATURE_A if index % 3 else SIGNATURE_B)
    second = replay(space, signatures=lambda index: SIGNATURE_B if index % 3 else SIGNATURE_A)
    assert first == second


def test_signature_truncation_is_part_of_equality_without_separate_reward():
    strategy = GuidedStrategy(SEED)
    strategy.start(description(InputSpace(2, 0, 3)))
    first = strategy.propose()
    strategy.observe(first, feedback(SIGNATURE_A))
    second = strategy.propose()
    strategy.observe(second, feedback(ExecutionSignature(SIGNATURE_A.digest, True)))
    assert list(strategy._parents) == [first, second]
    assert len(strategy._seen_signatures) == 2


def test_repeated_signatures_never_replace_or_duplicate_fifo_parents():
    strategy = GuidedStrategy(SEED, archive_size=2)
    strategy.start(description(InputSpace(3, 0, 3)))
    first = strategy.propose()
    strategy.observe(first, feedback(SIGNATURE_A))
    second = strategy.propose()
    strategy.observe(second, feedback(SIGNATURE_B))
    third = strategy.propose()
    strategy.observe(third, feedback(ExecutionSignature("c" * 64)))
    assert list(strategy._parents) == [second, third]
    assert len(strategy._seen_signatures) == 3
    fourth = strategy.propose()
    strategy.observe(fourth, feedback(SIGNATURE_A))
    assert list(strategy._parents) == [second, third]
    assert len(strategy._seen_signatures) == 3


@pytest.mark.parametrize("status", [
    "safe", "triggered", "infrastructure_failure", "budget_exhausted", "session_aborted", "invalid_input",
])
def test_without_signatures_order_is_exactly_unchanged_random_fallback(status):
    spec = description(InputSpace(2, 0, 2))
    strategy, fallback = GuidedStrategy(SEED), RandomStrategy(SEED)
    strategy.start(spec)
    fallback.start(spec)
    actual = []
    for trial in iter(strategy.propose, None):
        actual.append(trial)
        strategy.observe(trial, feedback(status=status))
    assert actual == list(iter(fallback.propose, None))
    assert not strategy._parents and not strategy._seen_signatures


def test_id_budget_and_feedback_accounting_fields_do_not_affect_guided_order():
    first, second = GuidedStrategy(SEED), GuidedStrategy(SEED)
    space = InputSpace(2, 0, 3)
    first.start(description(space, budget=1))
    second.start(ExperimentSpec("b-" + "0" * 32, space, 10 ** 10))
    for index in range(16):
        candidate = first.propose()
        assert second.propose() == candidate
        signature = SIGNATURE_A if index % 2 else SIGNATURE_B
        first.observe(candidate, feedback(signature, index=1, remaining=0))
        second.observe(candidate, feedback(signature, index=99999, remaining=10 ** 10))
    assert first.propose() is second.propose() is None


def test_one_mutation_changes_exactly_one_coordinate_within_public_bounds():
    strategy = GuidedStrategy(SEED)
    space = InputSpace(4, 7, 11)
    strategy.start(description(space))
    parent = strategy.propose()
    strategy.observe(parent, feedback(SIGNATURE_A))
    candidate = strategy.propose()
    assert space.accepts(candidate.values)
    assert sum(before != after for before, after in zip(parent.values, candidate.values)) == 1


def test_mutation_collision_attempts_are_bounded_then_fallback_skips_prior_proposals():
    strategy = GuidedStrategy(SEED, mutation_attempts=2)
    strategy.start(description(InputSpace(2, 0, 2)))
    parent = strategy.propose()
    strategy.observe(parent, feedback(SIGNATURE_A))
    strategy._rng = Mock()
    strategy._rng.randrange.return_value = 0
    mutation = strategy.propose()
    assert mutation != parent
    strategy._rng.randrange.reset_mock()
    remaining = TrialInput(next(
        values for values in itertools.product(range(3), repeat=2)
        if values not in (parent.values, mutation.values)
    ))
    strategy._fallback.propose = Mock(side_effect=[parent, mutation, remaining, None])
    final = strategy.propose()
    assert final == remaining
    assert strategy._rng.randrange.call_count == 3 * 2
    assert strategy._fallback.propose.call_count == 3


def test_sparse_state_is_bounded_by_proposals_not_enormous_domain():
    spec = description(InputSpace(8, 0, 65535))  # 2**128 tuples.
    tracemalloc.start()
    try:
        strategy = GuidedStrategy(SEED, archive_size=2)
        strategy.start(spec)
        _, initial_peak = tracemalloc.get_traced_memory()
        seen = set()
        for index in range(256):
            candidate = strategy.propose()
            assert spec.input_space.accepts(candidate.values)
            seen.add(candidate.values)
            strategy.observe(candidate, feedback(ExecutionSignature(f"{index:064x}")))
        _, proposal_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(seen) == len(strategy._visited) == len(strategy._seen_signatures) == 256
    assert len(strategy._parents) == 2
    assert initial_peak < 128 * 1024
    assert proposal_peak < 1024 * 1024


@pytest.mark.parametrize("candidate", [
    TrialInput([0, 0]), TrialInput((True, 0)), TrialInput((0,)), TrialInput((9, 9)), (0, 0),
])
def test_invalid_observed_candidates_cannot_enter_archive(candidate):
    strategy = GuidedStrategy(SEED)
    strategy.start(description(InputSpace(2, 0, 2)))
    strategy.propose()
    with pytest.raises(ValueError, match="canonical previously proposed input"):
        strategy.observe(candidate, feedback(SIGNATURE_A))
    assert not strategy._parents and not strategy._seen_signatures


def test_canonical_but_unproposed_input_cannot_enter_archive():
    strategy = GuidedStrategy(SEED)
    strategy.start(description(InputSpace(2, 0, 2)))
    with pytest.raises(ValueError, match="previously proposed input"):
        strategy.observe(TrialInput((0, 0)), feedback(SIGNATURE_A))


def test_subclassed_input_feedback_and_signature_are_rejected():
    class ExtendedInput(TrialInput):
        extra = "extra state"

    class ExtendedFeedback(TrialFeedback):
        extra = "extra state"

    class ExtendedSignature(ExecutionSignature):
        extra = "extra state"

    strategy = GuidedStrategy(SEED)
    strategy.start(description(InputSpace(2, 0, 2)))
    trial = strategy.propose()
    with pytest.raises(ValueError, match="canonical previously proposed input"):
        strategy.observe(ExtendedInput(trial.values), feedback())
    with pytest.raises(ValueError, match="canonical immutable TrialFeedback"):
        strategy.observe(trial, ExtendedFeedback("safe", 1, 9))
    forged = feedback()
    object.__setattr__(forged, "execution_signature", ExtendedSignature("a" * 64))
    with pytest.raises(ValueError, match="canonical immutable ExecutionSignature"):
        strategy.observe(trial, forged)
    assert not strategy._parents and not strategy._seen_signatures


@pytest.mark.parametrize("field, value", [("digest", "invalid"), ("truncated", 1)])
def test_forged_signature_fields_are_revalidated_before_archiving(field, value):
    strategy = GuidedStrategy(SEED)
    strategy.start(description(InputSpace(2, 0, 2)))
    trial = strategy.propose()
    signature = ExecutionSignature("a" * 64)
    object.__setattr__(signature, field, value)
    forged = feedback()
    object.__setattr__(forged, "execution_signature", signature)
    with pytest.raises(ValueError):
        strategy.observe(trial, forged)
    assert not strategy._parents and not strategy._seen_signatures


def make_session(executor, budget, space=InputSpace(2, 0, 2)):
    return EvaluationSession(ID, space, budget, "guided", executor, random_seed=SEED)


@pytest.mark.parametrize("trigger_index", [1, 4, 9])
def test_runner_keeps_evaluator_discovery_accounting_and_stops_dispatch(trigger_index):
    observations = [Observation(True, execution_signature=SIGNATURE_A)] * (trigger_index - 1)
    observations += [Observation(True, True, execution_signature=SIGNATURE_B), Observation(True)]
    executor = Mock(side_effect=observations)
    owner = make_session(executor, budget=12)
    strategy = GuidedStrategy(SEED)
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    assert record.termination is TerminationReason.FAILURE_DISCOVERED
    assert record.evaluation == owner.result()
    assert record.evaluation.first_failure_execution == trigger_index
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == trigger_index
    assert record.evaluation.infrastructure_failures == 0
    assert executor.call_count == strategy.propose.call_count == trigger_index
    assert record.strategy == guided_metadata(SEED)


@pytest.mark.parametrize("budget", [0, 1, 4, 9, 12])
def test_runner_respects_evaluator_budget_and_finite_domain_exhaustion(budget):
    executor = Mock(return_value=Observation(True, execution_signature=SIGNATURE_A))
    owner = make_session(executor, budget)
    strategy = GuidedStrategy(SEED)
    strategy.propose = Mock(wraps=strategy.propose)
    record = run_strategy(strategy, owner.strategy_api())
    count = min(budget, 9)
    assert record.evaluation == owner.result()
    assert record.evaluation.attempted_executions == record.evaluation.successful_executions == count
    assert record.evaluation.infrastructure_failures == 0
    assert record.evaluation.budget_remaining == budget - count
    assert executor.call_count == count
    assert len({call.args[0] for call in executor.call_args_list}) == count
    assert record.termination is (
        TerminationReason.STRATEGY_STOPPED if budget > 9 else TerminationReason.BUDGET_EXHAUSTED
    )
    assert strategy.propose.call_count == count + (budget > 9)


@pytest.mark.parametrize("safe_prefix", [0, 2])
def test_infrastructure_abort_cannot_be_masked_by_later_trigger(safe_prefix):
    executor = Mock(side_effect=[Observation(True, execution_signature=SIGNATURE_A)] * safe_prefix + [
        Observation(False, True, stderr="private GDB error"), Observation(True, True),
    ])
    owner = make_session(executor, budget=9)
    record = run_strategy(GuidedStrategy(SEED), owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation == owner.result()
    assert record.evaluation.aborted and not record.evaluation.failure_found
    assert record.evaluation.attempted_executions == safe_prefix + 1
    assert record.evaluation.successful_executions == safe_prefix
    assert record.evaluation.infrastructure_failures == 1
    assert executor.call_count == safe_prefix + 1
    assert "private GDB error" in owner.diagnostics()[0]["stderr"]
    assert "private GDB error" not in str(asdict(record))


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_control_flow_interruption_preserves_evaluator_abort_and_propagation(interruption_type):
    interruption = interruption_type("private cancellation")
    executor = Mock(side_effect=[interruption, Observation(True, True)])
    owner = make_session(executor, budget=3)
    with pytest.raises(interruption_type) as caught:
        run_strategy(GuidedStrategy(SEED), owner.strategy_api())
    assert caught.value is interruption
    result = owner.result()
    assert result.aborted and result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0
    record = run_strategy(GuidedStrategy(SEED), owner.strategy_api())
    assert record.termination is TerminationReason.SESSION_ABORTED
    assert record.evaluation == result
    executor.assert_called_once()


def test_callbacks_receive_only_canonical_public_records_without_admin_diagnostics():
    secret = "private firmware.c /image.elf GDB diagnostics"
    owner = make_session(Mock(return_value=Observation(True, stdout=secret, stderr=secret, execution_signature=SIGNATURE_A)), 1)
    strategy = GuidedStrategy(SEED)
    strategy.start = Mock(wraps=strategy.start)
    strategy.observe = Mock(wraps=strategy.observe)
    record = run_strategy(strategy, owner.strategy_api())
    spec, = strategy.start.call_args.args
    trial, observed = strategy.observe.call_args.args
    assert type(spec) is ExperimentSpec and type(trial) is TrialInput and type(observed) is TrialFeedback
    assert observed.execution_signature == SIGNATURE_A
    for item in (spec, trial, observed, strategy.metadata):
        for hidden in ("source", "image", "registry", "evaluator", "diagnostics", "execute", "_executor"):
            assert not hasattr(item, hidden)
    assert secret not in str([asdict(spec), asdict(observed), asdict(record)])


def test_production_imports_and_calls_preserve_the_cooperative_information_boundary():
    # Administrator-only structural guard; this is not process isolation.
    tree = ast.parse(inspect.getsource(guided_module))
    allowed_imports = {
        "collections", "random", "src.firmavex.evaluation.api",
        "src.firmavex.strategies.api", "src.firmavex.strategies.random",
    }
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    assert {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} <= allowed_imports
    forbidden_functions = {
        "open", "eval", "exec", "compile", "__import__", "getattr", "setattr",
        "vars", "globals", "locals",
    }
    forbidden_attributes = {
        "open", "read", "read_text", "read_bytes", "write", "write_text",
        "Popen", "run", "check_call", "check_output", "system", "connect",
        "benchmark_id", "execution_budget", "execution_index", "budget_remaining",
        "stdout", "stderr", "diagnostics", "execute", "executor", "registry",
        "source", "manifest", "oracle", "partition",
    }
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in forbidden_functions
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in forbidden_attributes
        for node in ast.walk(tree)
    )
