import itertools
from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import ExperimentSpec as BenchmarkDescription, InputSpace, StrategyHandle, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.evaluation import registry as registry_module
from src.firmavex.experiments import runner as runner_module
from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.monitor.monitor import observe_symbol
from src.firmavex.strategies.api import InvalidOutputReason, StrategyMetadata, TerminationReason
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.random import RandomStrategy


ID = "b-3874d6a4a92f46758d73854abf0a08df"
SPACE = InputSpace(2, 0, 2)


class FakeSessions:
    """Administrator-side provider; each request opens a real fresh evaluator."""

    def __init__(self, executor, space=SPACE):
        self.executor = executor
        self.space = space
        self.owners = []
        self.open_session = Mock(side_effect=self._open)

    def _open(self, benchmark_id, execution_budget, strategy_id, *, random_seed=None):
        owner = EvaluationSession(benchmark_id, self.space, execution_budget, strategy_id, self.executor, random_seed=random_seed)
        self.owners.append(owner)
        return owner


def declaration(name="enumerative", seed=None, budget=3):
    return ExperimentSpec(ID, StrategyMetadata(name, seed=seed), budget)


def expected_order(name, seed):
    if name == "enumerative":
        return list(itertools.product(range(3), repeat=2))
    strategy = RandomStrategy(seed)
    owner = EvaluationSession(ID, SPACE, 0, name, Mock(), random_seed=seed)
    strategy.start(owner.describe())
    return [trial.values for trial in iter(strategy.propose, None)]


@pytest.mark.parametrize("name, seed, strategy_type", [
    ("enumerative", None, EnumerativeStrategy), ("random", 42, RandomStrategy),
])
def test_experiment_selects_baseline_and_passes_exact_declared_session_parameters(monkeypatch, name, seed, strategy_type):
    original = runner_module.create_strategy
    constructed = []

    def create(metadata):
        strategy = original(metadata)
        constructed.append(strategy)
        return strategy

    factory = Mock(side_effect=create)
    monkeypatch.setattr(runner_module, "create_strategy", factory)
    executor = Mock(return_value=Observation(True))
    provider = FakeSessions(executor)
    spec = declaration(name, seed, budget=3)
    record = ExperimentRunner(provider).run(spec)
    factory.assert_called_once_with(spec.strategy)
    provider.open_session.assert_called_once_with(ID, 3, name, random_seed=seed)
    assert type(constructed[0]) is strategy_type
    assert record.declaration is spec
    assert record.run.strategy == spec.strategy
    assert record.run.evaluation == provider.owners[0].result()
    assert record.run.evaluation.random_seed == seed
    assert record.description == provider.owners[0].describe()
    assert [item.args[0] for item in executor.call_args_list] == expected_order(name, seed)[:3]


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 42)])
@pytest.mark.parametrize("trigger_index", [1, 4, 8])
def test_discovery_record_retains_exact_evaluator_first_trigger_index(name, seed, trigger_index):
    ordered = expected_order(name, seed)
    trigger = ordered[trigger_index - 1]
    executor = Mock(side_effect=lambda values: Observation(True, values == trigger))
    provider = FakeSessions(executor)
    record = ExperimentRunner(provider).run(declaration(name, seed, budget=9))
    result = record.run.evaluation
    assert record.run.termination is TerminationReason.FAILURE_DISCOVERED
    assert result == provider.owners[0].result()
    assert result.failure_found and not result.aborted
    assert result.attempted_executions == result.successful_executions == result.first_failure_execution == trigger_index
    assert result.infrastructure_failures == 0
    assert result.time_to_first_failure_seconds is not None
    assert [item.args[0] for item in executor.call_args_list] == ordered[:trigger_index]
    provider.open_session.assert_called_once()


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 42)])
@pytest.mark.parametrize("budget", [0, 2, 9, 12])
def test_budget_and_domain_stop_records_preserve_real_usage(name, seed, budget):
    executor = Mock(return_value=Observation(True))
    provider = FakeSessions(executor)
    record = ExperimentRunner(provider).run(declaration(name, seed, budget))
    ordered = expected_order(name, seed)
    count = min(budget, len(ordered))
    assert record.run.evaluation == provider.owners[0].result()
    assert record.run.evaluation.attempted_executions == record.run.evaluation.successful_executions == count
    assert record.run.evaluation.execution_budget == record.declaration.execution_budget == budget
    assert record.run.evaluation.budget_remaining == budget - count
    assert record.run.evaluation.infrastructure_failures == 0
    assert not record.run.evaluation.failure_found and not record.run.evaluation.aborted
    assert [item.args[0] for item in executor.call_args_list] == ordered[:count]
    expected = TerminationReason.STRATEGY_STOPPED if budget > len(ordered) else TerminationReason.BUDGET_EXHAUSTED
    assert record.run.termination is expected


def test_same_seed_reproduces_dispatch_and_records_without_outcome_selection():
    records, sequences = [], []
    for seed in (42, 42, 99):
        executor = Mock(return_value=Observation(True))
        provider = FakeSessions(executor)
        records.append(ExperimentRunner(provider).run(declaration("random", seed, budget=5)))
        sequences.append([item.args[0] for item in executor.call_args_list])
    assert sequences[0] == sequences[1]
    assert sequences[0] != sequences[2]
    assert records[0].to_json() == records[1].to_json()
    assert [record.run.strategy.seed for record in records] == [42, 42, 99]


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 42)])
def test_infrastructure_abort_is_not_clean_non_discovery(name, seed):
    secret = "private image.elf GDB stdout/stderr held_out oracle"
    executor = Mock(side_effect=[Observation(True), Observation(False, True, stdout=secret, stderr=secret), Observation(True, True)])
    provider = FakeSessions(executor)
    record = ExperimentRunner(provider).run(declaration(name, seed, budget=5))
    result = record.run.evaluation
    assert record.run.termination is TerminationReason.SESSION_ABORTED
    assert result.aborted and not result.failure_found
    assert result.attempted_executions == 2 and result.successful_executions == 1
    assert result.infrastructure_failures == 1
    assert result.first_failure_execution is None
    assert result == provider.owners[0].result()
    assert executor.call_count == 2
    assert provider.owners[0].diagnostics()[0]["stderr"] == secret
    assert secret not in record.to_json()


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 42)])
@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_interruption_propagates_without_fabricating_completed_record(name, seed, interruption_type):
    interruption = interruption_type("private cancellation")
    executor = Mock(side_effect=[interruption, Observation(True, True)])
    provider = FakeSessions(executor)
    runner = ExperimentRunner(provider)
    with pytest.raises(interruption_type) as caught:
        runner.run(declaration(name, seed, budget=3))
    assert caught.value is interruption
    owner = provider.owners[0]
    assert runner.last_session is owner
    result = owner.result()
    assert result.aborted
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0
    assert owner.strategy_api().execute(TrialInput((0, 0))).status == "session_aborted"
    assert owner.result() == result
    executor.assert_called_once()


def test_run_requires_validated_declaration_before_provider_access():
    provider = Mock()
    with pytest.raises(ValueError, match="ExperimentSpec declaration"):
        ExperimentRunner(provider).run({"strategy": "enumerative"})
    provider.open_session.assert_not_called()


def test_administrator_can_inspect_latest_session_without_serializing_it():
    secret = "administrator-owned GDB diagnostics"
    provider = FakeSessions(Mock(return_value=Observation(False, stderr=secret)))
    runner = ExperimentRunner(provider)
    assert runner.last_session is None
    record = runner.run(declaration(budget=1))
    first = runner.last_session
    assert first is provider.owners[0]
    assert first.diagnostics()[0]["stderr"] == secret
    assert secret not in record.to_json()
    runner.run(declaration(budget=0))
    assert runner.last_session is provider.owners[1] and runner.last_session is not first


def test_failed_new_session_creation_clears_previous_admin_handle():
    provider = FakeSessions(Mock(return_value=Observation(True)))
    runner = ExperimentRunner(provider)
    runner.run(declaration(budget=1))
    assert runner.last_session is not None
    provider.open_session.side_effect = ValueError("Unknown or unbuilt benchmark")
    with pytest.raises(ValueError, match="Unknown or unbuilt"):
        runner.run(declaration(budget=1))
    assert runner.last_session is None


@pytest.mark.parametrize("metadata, budget", [
    (StrategyMetadata("enumerative", seed=42), 3),
    (StrategyMetadata("random"), 3),
    (StrategyMetadata("enumerative"), -1),
])
def test_invalid_intent_never_reaches_session_or_firmware(metadata, budget):
    provider = Mock()
    with pytest.raises(ValueError):
        ExperimentRunner(provider).run(ExperimentSpec(ID, metadata, budget))
    assert provider.mock_calls == []


@pytest.mark.parametrize("change", [
    {"benchmark_id": "b-" + "0" * 32}, {"budget": 999},
    {"strategy_id": "random"}, {"seed": 42},
])
def test_mismatched_provider_identity_budget_or_seed_is_rejected_before_dispatch(change):
    args = {"benchmark_id": ID, "budget": 3, "strategy_id": "enumerative", "seed": None} | change
    executor = Mock()
    owner = EvaluationSession(args["benchmark_id"], SPACE, args["budget"], args["strategy_id"], executor, random_seed=args["seed"])
    provider = Mock()
    provider.open_session.return_value = owner
    with pytest.raises(ValueError, match="differs from the experiment declaration"):
        ExperimentRunner(provider).run(declaration())
    executor.assert_not_called()
    assert owner.result().attempted_executions == 0


def test_reused_provider_session_is_rejected_without_another_execution():
    executor = Mock(return_value=Observation(True))
    owner = EvaluationSession(ID, SPACE, 3, "enumerative", executor)
    owner.execute(TrialInput((0, 0)))
    provider = Mock()
    provider.open_session.return_value = owner
    with pytest.raises(ValueError, match="fresh, unused"):
        ExperimentRunner(provider).run(declaration())
    assert owner.result().attempted_executions == 1
    executor.assert_called_once()


@pytest.mark.parametrize("kind", ["extended_description", "live_input_space"])
def test_provider_cannot_forward_extended_or_live_description_objects(monkeypatch, kind):
    owner = EvaluationSession(ID, SPACE, 3, "enumerative", Mock())
    description = owner.describe()
    if kind == "extended_description":
        class ExtendedDescription(BenchmarkDescription):
            source_path = "/private/source.c"

        description = ExtendedDescription(ID, SPACE, 3)
    else:
        description = replace(description, input_space=Mock())
    adapter = Mock()
    adapter.describe.return_value = description
    supplied_owner = Mock()
    supplied_owner.strategy_api.return_value = adapter
    provider = Mock()
    provider.open_session.return_value = supplied_owner
    delegate = Mock()
    monkeypatch.setattr(runner_module, "run_strategy", delegate)
    with pytest.raises(ValueError, match="immutable public benchmark description"):
        ExperimentRunner(provider).run(declaration())
    delegate.assert_not_called()
    adapter.execute.assert_not_called()


def test_factory_metadata_mismatch_fails_before_session_creation(monkeypatch):
    monkeypatch.setattr(runner_module, "create_strategy", Mock(return_value=RandomStrategy(99)))
    provider = Mock()
    with pytest.raises(ValueError, match="Constructed strategy metadata"):
        ExperimentRunner(provider).run(declaration("random", 42))
    provider.open_session.assert_not_called()


def test_experiment_delegates_once_and_retains_exact_strategy_run(monkeypatch):
    original = runner_module.run_strategy
    captured = []

    def execute(strategy, adapter):
        assert type(adapter) is StrategyHandle
        run = original(strategy, adapter)
        captured.append(run)
        return run

    delegate = Mock(side_effect=execute)
    monkeypatch.setattr(runner_module, "run_strategy", delegate)
    provider = FakeSessions(Mock(return_value=Observation(True)))
    record = ExperimentRunner(provider).run(declaration(budget=1))
    delegate.assert_called_once()
    assert record.run is captured[0]
    assert record.run.evaluation is captured[0].evaluation
    assert record.run.evaluation == provider.owners[0].result()


def test_invalid_output_termination_is_preserved_without_execution(monkeypatch):
    strategy = EnumerativeStrategy()
    strategy.propose = Mock(return_value=TrialInput((0,)))
    monkeypatch.setattr(runner_module, "create_strategy", Mock(return_value=strategy))
    executor = Mock()
    provider = FakeSessions(executor)
    record = ExperimentRunner(provider).run(declaration())
    assert record.run.termination is TerminationReason.INVALID_OUTPUT
    assert record.run.invalid_output is InvalidOutputReason.WIDTH
    assert record.run.evaluation.attempted_executions == 0
    assert record.run.evaluation.infrastructure_failures == 0
    assert not record.run.evaluation.aborted
    assert record.to_dict()["run"]["invalid_output"] == "candidate_width"
    executor.assert_not_called()


def test_administrative_paths_and_partition_never_enter_strategy_records(monkeypatch):
    strategy = EnumerativeStrategy()
    strategy.start = Mock(wraps=strategy.start)
    strategy.observe = Mock(wraps=strategy.observe)
    monkeypatch.setattr(runner_module, "create_strategy", Mock(return_value=strategy))
    provider = FakeSessions(Mock(return_value=Observation(True, stdout="private GDB log", stderr="private stderr")))
    provider.source_path = "/private/source.c"
    provider.elf_path = "/private/image.elf"
    provider.partition = "held_out"
    record = ExperimentRunner(provider).run(declaration(budget=1))
    description, = strategy.start.call_args.args
    assert set(asdict(description)) == {"benchmark_id", "input_space", "execution_budget"}
    candidate, feedback = strategy.observe.call_args.args
    assert type(candidate) is TrialInput
    assert set(asdict(feedback)) == {"status", "execution_index", "budget_remaining"}
    for forbidden in ("source.c", "image.elf", "held_out", "private", "GDB", "stderr", "oracle", "manifest"):
        assert forbidden not in record.to_json()


def test_existing_benchmark_registry_satisfies_production_session_provider(tmp_path, monkeypatch):
    registry = BenchmarkRegistry()
    benchmark = registry.select("development")[0]
    image = tmp_path / "controlled.elf"

    def build(*args, **kwargs):
        image.write_bytes(b"controlled registered image")
        return {"success": True, "output_file": str(image)}

    monkeypatch.setattr(registry_module, "build_cortex_m_firmware", build)
    assert registry.build(benchmark.benchmark_id, image)["success"]
    observe = Mock(return_value={"success": True, "value": 0, "stdout": "", "stderr": ""})
    monkeypatch.setattr(registry_module, "observe_symbol", observe)
    spec = ExperimentSpec(benchmark.benchmark_id, StrategyMetadata("enumerative"), 1)
    record = ExperimentRunner(registry).run(spec)
    assert record.run.termination is TerminationReason.BUDGET_EXHAUSTED
    assert record.run.evaluation.attempted_executions == 1
    assert record.description.input_space == registry.input_space
    observe.assert_called_once()
    for hidden in (benchmark.name, benchmark.source.name, str(image), "development", "held_out"):
        assert hidden not in record.to_json()


def test_real_arm_threshold_experiment_uses_existing_runner_adapter_and_evaluator(cortex_m_corpus):
    benchmark, image = cortex_m_corpus["threshold"]

    def execute(values):
        observed = observe_symbol(
            str(image), benchmark.failure_symbol, benchmark.breakpoint,
            input_values={benchmark.input_symbol: values[0]},
        )
        success = observed["success"] and observed["value"] in (0, 1)
        return Observation(success, success and observed["value"] == 1, observed["stdout"], observed["stderr"])

    executor = Mock(side_effect=execute)
    provider = FakeSessions(executor, InputSpace(1, benchmark.input_min, benchmark.input_max))
    record = ExperimentRunner(provider).run(declaration(budget=8))
    result = record.run.evaluation
    assert record.run.termination is TerminationReason.FAILURE_DISCOVERED, provider.owners[0].diagnostics()
    assert result == provider.owners[0].result()
    assert result.attempted_executions == result.successful_executions == result.first_failure_execution == 7
    assert result.failure_found and not result.aborted
    assert result.infrastructure_failures == 0
    assert result.budget_remaining == 1 and result.execution_budget == 8
    assert [item.args[0] for item in executor.call_args_list] == [(value,) for value in range(7)]
    assert record.run.strategy == StrategyMetadata("enumerative")
    assert record.to_dict()["run"]["evaluation"]["first_failure_execution"] == 7
