"""Signal plumbing uses fake executors; it never evaluates a corpus predicate."""

import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import (
    ExecutionSignature, ExperimentSpec as Description, InputSpace, TrialFeedback, TrialInput,
)
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.protocols.protocol import standard_baseline_protocol
from src.firmavex.protocols.runner import CampaignRunner
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.random import RandomStrategy
from src.firmavex.strategies.runner import run_strategy


ID = "b-" + "a" * 32
SPACE = InputSpace(2, 0, 2)
TRIAL = TrialInput((0, 1))
SIGNATURE = ExecutionSignature("a" * 64)
PRIVATE = "private source.c /firmware/image.elf GDB held_out oracle"


def session(executor, budget=3):
    return EvaluationSession(ID, SPACE, budget, "signature-test", executor)


class StringSubclass(str):
    pass


class ExtendedSignature(ExecutionSignature):
    administrator_data = PRIVATE


@pytest.mark.parametrize("digest", [
    "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 64 + "\n",
    0, True, False, b"a" * 64, StringSubclass("a" * 64),
])
def test_signature_rejects_noncanonical_digest(digest):
    with pytest.raises(ValueError):
        ExecutionSignature(digest)


@pytest.mark.parametrize("truncated", [0, 1, None, "false", []])
def test_signature_requires_an_exact_boolean_truncation_flag(truncated):
    with pytest.raises(ValueError):
        ExecutionSignature("a" * 64, truncated)


def test_signature_and_feedback_are_immutable_data_only():
    signature = ExecutionSignature("0123456789abcdef" * 4, True)
    feedback = TrialFeedback("safe", 1, 2, signature)
    assert asdict(signature) == {"digest": "0123456789abcdef" * 4, "truncated": True}
    assert feedback.execution_signature is signature
    with pytest.raises(FrozenInstanceError):
        signature.digest = "0" * 64
    with pytest.raises(FrozenInstanceError):
        signature.truncated = False
    with pytest.raises(FrozenInstanceError):
        feedback.execution_signature = None
    assert not any(callable(value) for value in asdict(signature).values())


@pytest.mark.parametrize("signature", [
    "a" * 64, {"digest": "a" * 64, "truncated": False},
    ExtendedSignature("a" * 64), Mock(digest="a" * 64, truncated=False),
])
def test_feedback_rejects_noncanonical_signature_records(signature):
    with pytest.raises(ValueError):
        TrialFeedback("safe", 1, 2, signature)


@pytest.mark.parametrize("status", [
    "infrastructure_failure", "budget_exhausted", "invalid_input", "session_aborted",
])
def test_non_execution_feedback_cannot_carry_a_signature(status):
    with pytest.raises(ValueError):
        TrialFeedback(status, None, 2, SIGNATURE)


def test_legacy_feedback_and_observation_construction_defaults_to_absence():
    assert TrialFeedback("safe", 1, 2).execution_signature is None
    assert Observation(True).execution_signature is None
    owner = session(Mock(return_value=Observation(True)))
    assert owner.execute(TRIAL).execution_signature is None
    assert owner.result().attempted_executions == owner.result().successful_executions == 1


@pytest.mark.parametrize("triggered", [False, True])
def test_evaluator_forwards_signature_without_recounting_or_exposing_diagnostics(monkeypatch, triggered):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", Mock(return_value=10.0))
    signature = ExecutionSignature("b" * 64, True)
    owner = session(Mock(return_value=Observation(True, triggered, PRIVATE, PRIVATE, signature)))
    adapter = owner.strategy_api()
    feedback = adapter.execute(TRIAL)
    assert feedback.execution_signature is signature
    assert feedback.status == ("triggered" if triggered else "safe")
    assert feedback.execution_index == 1 and feedback.budget_remaining == 2
    result = adapter.result()
    assert result.attempted_executions == result.successful_executions == 1
    assert result.infrastructure_failures == 0 and not result.aborted
    assert result.failure_triggering_executions == int(triggered)
    assert result.failure_found == triggered
    assert result.first_failure_execution == (1 if triggered else None)
    assert result.time_to_first_failure_seconds == (0.0 if triggered else None)
    assert not hasattr(adapter, "diagnostics")
    public = json.dumps([asdict(adapter.describe()), asdict(feedback), asdict(result)])
    for forbidden in (PRIVATE, "source.c", "image.elf", "GDB", "held_out", "oracle", "stdout", "stderr"):
        assert forbidden not in public
    assert set(asdict(feedback)) == {"status", "execution_index", "budget_remaining", "execution_signature"}


@pytest.mark.parametrize("signature", [
    "a" * 64, {"digest": "a" * 64}, ExtendedSignature("a" * 64), object(),
])
def test_malformed_executor_signal_aborts_charged_execution_and_preserves_admin_diagnostics(signature):
    executor = Mock(side_effect=[
        Observation(True, True, PRIVATE, PRIVATE, signature), Observation(True, True, execution_signature=SIGNATURE),
    ])
    owner = session(executor)
    adapter = owner.strategy_api()
    feedback = adapter.execute(TRIAL)
    assert feedback.status == "infrastructure_failure"
    assert feedback.execution_signature is None
    assert feedback.execution_index == 1 and feedback.budget_remaining == 2
    result = adapter.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == result.failure_triggering_executions == 0
    assert result.aborted and not result.failure_found
    assert result.first_failure_execution is None
    diagnostic, = owner.diagnostics()
    assert diagnostic["execution_index"] == 1 and diagnostic["values"] == TRIAL.values
    assert PRIVATE in diagnostic["stdout"] and PRIVATE in diagnostic["stderr"]
    for _ in range(3):
        later = adapter.execute(TRIAL)
        assert later.status == "session_aborted" and later.execution_signature is None
        assert later.execution_index is None and later.budget_remaining == 2
    executor.assert_called_once_with(TRIAL.values)
    assert adapter.result() == result
    assert PRIVATE not in json.dumps([asdict(adapter.describe()), asdict(feedback), asdict(result)])


@pytest.mark.parametrize("field, value", [("digest", PRIVATE), ("truncated", 1)])
def test_observation_boundary_rechecks_fields_of_a_forged_frozen_record(field, value):
    signature = ExecutionSignature("a" * 64)
    # Simulate a malformed administrator executor bypassing constructor checks.
    object.__setattr__(signature, field, value)
    with pytest.raises(ValueError):
        TrialFeedback("safe", 1, 2, signature)
    executor = Mock(return_value=Observation(True, execution_signature=signature))
    owner = session(executor)
    feedback = owner.execute(TRIAL)
    assert feedback.status == "infrastructure_failure" and feedback.execution_signature is None
    assert owner.result().attempted_executions == owner.result().infrastructure_failures == 1
    assert owner.result().successful_executions == 0 and owner.result().aborted
    assert owner.execute(TRIAL).status == "session_aborted"
    executor.assert_called_once_with(TRIAL.values)


def test_malformed_signal_after_discovery_preserves_discovery_but_aborts(monkeypatch):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", Mock(return_value=10.0))
    executor = Mock(side_effect=[
        Observation(True, True, execution_signature=SIGNATURE),
        Observation(True, True, PRIVATE, PRIVATE, {"digest": "a" * 64}),
        Observation(True, True, execution_signature=SIGNATURE),
    ])
    owner = session(executor)
    assert owner.execute(TRIAL).status == "triggered"
    discovery = owner.result()
    feedback = owner.execute(TRIAL)
    result = owner.result()
    assert feedback.status == "infrastructure_failure" and feedback.execution_signature is None
    assert result.aborted and result.failure_found
    assert result.attempted_executions == 2
    assert result.successful_executions == result.infrastructure_failures == result.failure_triggering_executions == 1
    assert result.first_failure_execution == discovery.first_failure_execution == 1
    assert result.time_to_first_failure_seconds == discovery.time_to_first_failure_seconds
    assert owner.execute(TRIAL).status == "session_aborted"
    assert owner.result() == result and executor.call_count == 2


def test_unsuccessful_observation_never_forwards_even_a_valid_signature():
    owner = session(Mock(return_value=Observation(False, True, PRIVATE, PRIVATE, SIGNATURE)))
    feedback = owner.execute(TRIAL)
    assert feedback.status == "infrastructure_failure" and feedback.execution_signature is None
    result = owner.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == result.failure_triggering_executions == 0
    assert result.aborted and not result.failure_found
    assert owner.diagnostics()[0]["stderr"] == PRIVATE


def test_invalid_or_exhausted_requests_do_not_reuse_a_previous_signal_or_consume_budget():
    executor = Mock(return_value=Observation(True, execution_signature=SIGNATURE))
    owner = session(executor, budget=1)
    invalid = owner.execute(TrialInput((3, 0)))
    assert invalid.status == "invalid_input" and invalid.execution_signature is None
    assert owner.result().attempted_executions == 0
    assert owner.execute(TRIAL).execution_signature is SIGNATURE
    for _ in range(3):
        exhausted = owner.execute(TRIAL)
        assert exhausted.status == "budget_exhausted" and exhausted.execution_signature is None
        assert exhausted.execution_index is None and exhausted.budget_remaining == 0
    executor.assert_called_once_with(TRIAL.values)
    assert owner.result().attempted_executions == owner.result().successful_executions == 1
    zero_executor = Mock()
    assert session(zero_executor, budget=0).execute(TRIAL).execution_signature is None
    zero_executor.assert_not_called()


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_interruption_after_signal_does_not_reuse_signal_or_weaken_abort_accounting(interruption_type):
    interruption = interruption_type(PRIVATE)
    executor = Mock(side_effect=[Observation(True, execution_signature=SIGNATURE), interruption, Observation(True, True)])
    owner = session(executor)
    assert owner.execute(TRIAL).execution_signature is SIGNATURE
    with pytest.raises(interruption_type) as caught:
        owner.execute(TRIAL)
    assert caught.value is interruption
    result = owner.result()
    assert result.attempted_executions == 2 and result.successful_executions == 1
    assert result.infrastructure_failures == 1 and result.aborted and not result.failure_found
    assert owner.execute(TRIAL).execution_signature is None
    assert owner.result() == result and executor.call_count == 2
    assert PRIVATE in owner.diagnostics()[0]["stderr"]


def test_common_runner_delivers_signal_but_ignores_strategy_counter_forgery():
    owner = session(Mock(return_value=Observation(True, execution_signature=SIGNATURE)), budget=1)
    strategy = EnumerativeStrategy()
    strategy.observe = Mock(return_value={
        "execution_index": 0, "budget_remaining": 999, "failure_found": True,
        "execution_signature": ExecutionSignature("f" * 64),
    })
    run = run_strategy(strategy, owner.strategy_api())
    candidate, feedback = strategy.observe.call_args.args
    assert candidate.values == (0, 0) and feedback.execution_signature is SIGNATURE
    assert run.termination is TerminationReason.BUDGET_EXHAUSTED
    assert run.evaluation == owner.result()
    assert run.evaluation.attempted_executions == run.evaluation.successful_executions == 1
    assert run.evaluation.budget_remaining == 0 and not run.evaluation.failure_found


@pytest.mark.parametrize("factory", [EnumerativeStrategy, lambda: RandomStrategy(42)])
@pytest.mark.parametrize("status", ["safe", "triggered"])
def test_frozen_baselines_ignore_varying_signatures_and_replay_after_reset(factory, status):
    strategy = factory()
    description = Description(ID, SPACE, 9)
    strategy.start(description)
    expected = list(iter(strategy.propose, None))
    strategy.start(description)
    actual = []
    for index, candidate in enumerate(iter(strategy.propose, None), start=1):
        actual.append(candidate)
        signature = None if index % 3 == 0 else ExecutionSignature(hashlib.sha256(bytes(candidate.values)).hexdigest(), index % 2 == 0)
        strategy.observe(candidate, TrialFeedback(status, index, 9 - index, signature))
    assert actual == expected
    assert strategy.propose() is None
    strategy.start(description)
    assert list(iter(strategy.propose, None)) == expected
    assert strategy.metadata.configuration == ()
    assert strategy.metadata.seed == (42 if strategy.metadata.name == "random" else None)


class FakeRegistry:
    """Administrative provider for tiny synthetic execution/serialization tests."""

    input_space = SPACE

    def __init__(self, with_signatures, partition="development"):
        self.with_signatures = with_signatures
        self.partition = partition
        self.owners = []
        self.executed = []

    def select(self, partition):
        assert partition == self.partition
        return (SimpleNamespace(benchmark_id=ID, source=PRIVATE, name=PRIVATE, split=partition),)

    def open_session(self, benchmark_id, execution_budget, strategy_id, *, random_seed=None):
        dispatched = []
        self.executed.append(dispatched)

        def execute(values):
            dispatched.append(values)
            signature = None
            if self.with_signatures:
                signature = ExecutionSignature(hashlib.sha256(bytes(values)).hexdigest(), sum(values) % 2 == 0)
            return Observation(True, values == TRIAL.values, PRIVATE, PRIVATE, signature)

        owner = EvaluationSession(benchmark_id, self.input_space, execution_budget, strategy_id, execute, random_seed=random_seed)
        self.owners.append(owner)
        return owner


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 42)])
def test_signal_does_not_change_experiment_records_execution_order_or_metrics(monkeypatch, name, seed):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", Mock(return_value=10.0))
    spec = ExperimentSpec(ID, StrategyMetadata(name, seed=seed), 5)
    plain, signaled = FakeRegistry(False), FakeRegistry(True)
    original = ExperimentRunner(plain).run(spec)
    observed = ExperimentRunner(signaled).run(spec)
    assert plain.executed == signaled.executed
    assert original == observed and original.to_json() == observed.to_json()
    assert observed.run.evaluation == signaled.owners[0].result()
    data = observed.to_dict()
    assert data["schema_version"] == 1
    assert set(data) == {"schema_version", "declaration", "description", "run"}
    assert "execution_signature" not in observed.to_json() and PRIVATE not in observed.to_json()


@pytest.mark.parametrize("partition", ["development", "held_out"])
def test_signal_preserves_frozen_standard_plan_campaign_records_and_summary_metrics(monkeypatch, partition):
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", Mock(return_value=10.0))
    protocol = standard_baseline_protocol(benchmark_ids=(ID,), execution_budget=3, partition=partition)
    before = protocol.to_json(), protocol.plan_to_json()
    plan = protocol.expand()
    assert protocol.strategies == ("enumerative", "random")
    assert protocol.random_seeds == tuple(range(10)) and protocol.is_standard
    assert [(spec.strategy.name, spec.strategy.seed) for spec in plan] == [("enumerative", None)] + [("random", seed) for seed in range(10)]
    plain, signaled = FakeRegistry(False, partition), FakeRegistry(True, partition)
    original = CampaignRunner(plain).run(protocol)
    observed = CampaignRunner(signaled).run(protocol)
    assert plain.executed == signaled.executed
    assert original.records == observed.records and original.summaries == observed.summaries
    assert original.to_json() == observed.to_json()
    assert before == (protocol.to_json(), protocol.plan_to_json())
    assert len(observed.records) == 11
    assert "execution_signature" not in observed.to_json() and PRIVATE not in observed.to_json()
    for record, owner in zip(observed.records, signaled.owners):
        assert record.run.evaluation == owner.result()
