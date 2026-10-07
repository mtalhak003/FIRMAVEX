"""Campaign-scale coverage uses fake executors; one test runs two ARM trials."""

import ast
import inspect
from dataclasses import FrozenInstanceError, asdict, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace, StrategyHandle, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.experiments import runner as experiment_runner_module
from src.firmavex.experiments.api import ExperimentRecord
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.monitor.monitor import observe_symbol
from src.firmavex.protocols import runner as campaign_runner_module
from src.firmavex.protocols.protocol import EvaluationProtocol, standard_baseline_protocol
from src.firmavex.protocols.runner import CampaignRunner
from src.firmavex.strategies.api import TerminationReason


ID_A = "b-" + "a" * 32
ID_B = "b-" + "b" * 32
SPACE = InputSpace(2, 0, 2)
RUN_EXPERIMENT = ExperimentRunner.run


class FakeRegistry:
    """Only the administrator sees selection metadata and session ownership."""

    def __init__(self, executor=None, *, space=SPACE, partition="development", identifiers=(ID_A, ID_B)):
        self.input_space = space
        self.partition = partition
        self.identifiers = identifiers
        self.executor = executor if executor is not None else Mock(return_value=Observation(True))
        self.owners = []
        self.select = Mock(side_effect=self._select)
        self.open_session = Mock(side_effect=self._open)

    def _select(self, partition):
        if partition != self.partition:
            return ()
        # Deliberately include private fields to ensure selection is admin-only.
        return tuple(SimpleNamespace(
            benchmark_id=identifier, source="/private/firmware.c", name="private-predicate",
            split=partition,
        ) for identifier in reversed(self.identifiers))

    def _open(self, benchmark_id, execution_budget, strategy_id, *, random_seed=None):
        owner = EvaluationSession(
            benchmark_id, self.input_space, execution_budget, strategy_id,
            self.executor, random_seed=random_seed,
        )
        self.owners.append(owner)
        return owner


def protocol(**changes):
    return EvaluationProtocol(**({
        "benchmark_ids": (ID_B, ID_A), "execution_budget": 2,
        "partition": "development", "random_seeds": (0, 1),
    } | changes))


def record_for(spec, space=SPACE):
    """A real lower-layer record from a tiny fake-executor experiment."""
    registry = FakeRegistry(space=space)
    return RUN_EXPERIMENT(ExperimentRunner(registry), spec)


def test_campaign_delegates_every_plan_item_once_to_one_existing_experiment_runner(monkeypatch):
    registry = FakeRegistry()
    declaration = protocol()
    original = ExperimentRunner.run
    seen, records = [], []

    def run(instance, spec):
        seen.append((instance, spec))
        record = original(instance, spec)
        records.append(record)
        return record

    monkeypatch.setattr(ExperimentRunner, "run", run)
    result = CampaignRunner(registry).run(declaration)
    assert tuple(spec for _, spec in seen) == declaration.expand()
    assert len({id(instance) for instance, _ in seen}) == 1
    assert all(type(instance) is ExperimentRunner for instance, _ in seen)
    assert result.protocol is declaration
    assert len(result.records) == len(records) == 6
    assert result.planned_run_count == result.completed_record_count == result.valid_search_run_count == 6
    assert result.infrastructure_aborted_run_count == result.invalid_strategy_run_count == 0
    assert all(actual is delegated for actual, delegated in zip(result.records, records))
    assert [record.declaration for record in result.records] == list(declaration.expand())
    assert registry.select.call_count == 1
    registry.select.assert_called_with("development")
    assert registry.open_session.call_count == 6
    for call, spec in zip(registry.open_session.call_args_list, declaration.expand()):
        assert call.args == (spec.benchmark_id, spec.execution_budget, spec.strategy.name)
        assert call.kwargs == {"random_seed": spec.strategy.seed}


def test_single_runner_is_constructed_once_and_reused_across_campaign_requests(monkeypatch):
    factory = Mock(wraps=ExperimentRunner)
    monkeypatch.setattr(campaign_runner_module, "ExperimentRunner", factory)
    registry = FakeRegistry()
    runner = CampaignRunner(registry)
    runner.run(protocol())
    runner.run(protocol())
    factory.assert_called_once_with(registry)
    assert type(runner.experiment_runner) is ExperimentRunner
    assert len(registry.owners) == 12
    assert len({id(owner) for owner in registry.owners}) == 12


def test_campaign_reuses_authoritative_record_accounting_instead_of_recounting_executions():
    registry = FakeRegistry()
    result = CampaignRunner(registry).run(protocol())
    for record, owner in zip(result.records, registry.owners):
        assert record.run.evaluation == owner.result()
        assert record.description == owner.describe()
        assert record.run.evaluation.attempted_executions == 2
        assert record.run.evaluation.successful_executions == 2
        assert record.run.evaluation.budget_remaining == 0
    assert registry.executor.call_count == 12


def test_campaign_runner_has_no_direct_firmware_or_strategy_execution_path():
    tree = ast.parse(inspect.getsource(campaign_runner_module))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert "ExperimentRunner" in imported
    assert not imported.intersection({"observe_symbol", "run_strategy"})
    direct_execution = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute", "_execute", "propose", "observe"}
    ]
    assert direct_execution == []


def test_campaign_structural_output_is_deterministic_with_safe_fake_execution():
    declaration = protocol()
    first = CampaignRunner(FakeRegistry()).run(declaration)
    second = CampaignRunner(FakeRegistry()).run(declaration)
    assert first.to_json() == second.to_json()
    assert first.to_dict() == second.to_dict()


def test_campaign_result_keeps_immutable_ordered_exact_records():
    result = CampaignRunner(FakeRegistry()).run(protocol())
    assert type(result.records) is tuple
    assert all(type(record) is ExperimentRecord for record in result.records)
    with pytest.raises(FrozenInstanceError):
        result.records = ()
    with pytest.raises(TypeError):
        result.records[0] = result.records[1]
    with pytest.raises(FrozenInstanceError):
        result.records[0].declaration = result.records[1].declaration


@pytest.mark.parametrize("identifiers", [(ID_A, "b-" + "c" * 32), ("b-" + "c" * 32, ID_A)])
def test_unknown_benchmark_anywhere_in_plan_rejects_entire_campaign_before_first_session(identifiers):
    registry = FakeRegistry()
    declaration = protocol(benchmark_ids=identifiers)
    with pytest.raises(ValueError):
        CampaignRunner(registry).run(declaration)
    registry.open_session.assert_not_called()
    registry.executor.assert_not_called()


@pytest.mark.parametrize("declared, actual", [("development", "held_out"), ("held_out", "development")])
def test_wrong_partition_membership_rejects_campaign_before_dispatch(declared, actual):
    registry = FakeRegistry(partition=actual)
    with pytest.raises(ValueError):
        CampaignRunner(registry).run(protocol(partition=declared))
    registry.select.assert_called_once_with(declared)
    registry.open_session.assert_not_called()
    registry.executor.assert_not_called()


@pytest.mark.parametrize("space", [
    None, Mock(), InputSpace(0, 0, 2), InputSpace(True, 0, 2),
    InputSpace(1, True, 2), InputSpace(1, 0, False), InputSpace(1, 3, 2),
    InputSpace(1, -1, 2), InputSpace(1, 0, 0x100000000),
])
def test_invalid_registry_domain_is_rejected_before_any_session(space):
    registry = FakeRegistry(space=space)
    with pytest.raises(ValueError):
        CampaignRunner(registry).run(protocol())
    registry.open_session.assert_not_called()
    registry.executor.assert_not_called()


def test_runner_rejects_nonprotocol_input_before_registry_access():
    registry = FakeRegistry()
    with pytest.raises(ValueError):
        CampaignRunner(registry).run({"execution_budget": 2})
    registry.select.assert_not_called()
    registry.open_session.assert_not_called()


@pytest.mark.parametrize("bad_kind", ["wrong_declaration", "wrong_domain", "non_record"])
def test_invalid_child_record_stops_immediately_before_later_plan_items(monkeypatch, bad_kind):
    declaration = protocol()
    first_spec = declaration.expand()[0]
    record = record_for(first_spec)
    if bad_kind == "wrong_declaration":
        bad_record = record_for(replace(first_spec, execution_budget=1))
    elif bad_kind == "wrong_domain":
        bad_record = replace(record, description=replace(record.description, input_space=InputSpace(1, 0, 255)))
    else:
        bad_record = {"declaration": first_spec}
    delegate = Mock(return_value=bad_record)
    monkeypatch.setattr(ExperimentRunner, "run", delegate)
    registry = FakeRegistry()
    with pytest.raises(ValueError):
        CampaignRunner(registry).run(declaration)
    delegate.assert_called_once_with(first_spec)
    registry.open_session.assert_not_called()
    registry.executor.assert_not_called()


def test_ordinary_infrastructure_abort_is_retained_and_later_fresh_experiments_continue():
    secret = "/private/image.elf GDB stderr oracle details"
    executor = Mock(side_effect=[
        Observation(False, True, stdout=secret, stderr=secret),
        Observation(True), Observation(True),
    ])
    registry = FakeRegistry(executor)
    declaration = protocol(benchmark_ids=(ID_A,), execution_budget=1)
    result = CampaignRunner(registry).run(declaration)
    assert [record.declaration for record in result.records] == list(declaration.expand())
    assert len(result.records) == len(registry.owners) == executor.call_count == 3
    assert result.planned_run_count == result.completed_record_count == 3
    assert result.valid_search_run_count == 2
    assert result.infrastructure_aborted_run_count == 1
    aborted, *later = result.records
    assert aborted.run.termination is TerminationReason.SESSION_ABORTED
    assert aborted.run.evaluation.aborted and not aborted.run.evaluation.failure_found
    assert aborted.run.evaluation.attempted_executions == aborted.run.evaluation.infrastructure_failures == 1
    assert all(not record.run.evaluation.aborted for record in later)
    assert all(record.run.evaluation.attempted_executions == 1 for record in later)
    assert registry.owners[0].diagnostics()[0]["stderr"] == secret
    assert secret not in result.to_json()


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_interruption_propagates_stops_campaign_and_retains_admin_charged_abort(interruption_type):
    interruption = interruption_type("private interruption diagnostics")
    executor = Mock(side_effect=[Observation(True), Observation(True), interruption, Observation(True)])
    registry = FakeRegistry(executor)
    runner = CampaignRunner(registry)
    declaration = protocol(benchmark_ids=(ID_A,))
    with pytest.raises(interruption_type) as caught:
        runner.run(declaration)
    assert caught.value is interruption
    assert executor.call_count == 3
    assert registry.open_session.call_count == 2
    owner = runner.experiment_runner.last_session
    assert owner is registry.owners[1]
    interrupted = owner.result()
    assert interrupted.attempted_executions == interrupted.infrastructure_failures == 1
    assert interrupted.successful_executions == 0 and interrupted.aborted
    assert owner.strategy_api().execute(TrialInput((0, 0))).status == "session_aborted"
    assert owner.result() == interrupted
    assert executor.call_count == 3
    assert "private interruption diagnostics" in owner.diagnostics()[0]["stderr"]


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_unrecorded_child_exception_propagates_without_later_dispatch(monkeypatch, error_type):
    error = error_type("private administrative error")
    delegate = Mock(side_effect=error)
    monkeypatch.setattr(ExperimentRunner, "run", delegate)
    registry = FakeRegistry()
    with pytest.raises(error_type) as caught:
        CampaignRunner(registry).run(protocol())
    assert caught.value is error
    assert delegate.call_count == 1
    registry.open_session.assert_not_called()


def test_actual_registry_admin_selection_works_without_building_or_executing_firmware(monkeypatch):
    registry = BenchmarkRegistry()
    benchmarks = registry.select("held_out")
    ids = tuple(item.benchmark_id for item in benchmarks[:2])
    declaration = standard_baseline_protocol(benchmark_ids=ids, execution_budget=1, partition="held_out")
    delegate = Mock(side_effect=lambda spec: record_for(spec, registry.input_space))
    monkeypatch.setattr(ExperimentRunner, "run", delegate)
    open_session = Mock(side_effect=AssertionError("must not open real registry session"))
    monkeypatch.setattr(registry, "open_session", open_session)
    result = CampaignRunner(registry).run(declaration)
    assert delegate.call_count == len(result.records) == 22
    open_session.assert_not_called()
    for benchmark in benchmarks:
        assert str(benchmark.source) not in result.to_json()
        assert benchmark.name not in result.to_json()


def test_partition_metadata_never_changes_strategy_inputs_feedback_or_metadata(monkeypatch):
    original = experiment_runner_module.create_strategy
    instances = []

    def create(metadata):
        strategy = original(metadata)
        strategy.start = Mock(wraps=strategy.start)
        strategy.observe = Mock(wraps=strategy.observe)
        instances.append(strategy)
        return strategy

    monkeypatch.setattr(experiment_runner_module, "create_strategy", create)
    results = []
    for partition in ("development", "held_out"):
        registry = FakeRegistry(partition=partition)
        declaration = protocol(benchmark_ids=(ID_A,), partition=partition, execution_budget=1, random_seeds=(0,))
        results.append(CampaignRunner(registry).run(declaration))
    assert len(instances) == 4
    for first, second in zip(instances[:2], instances[2:]):
        assert first.metadata == second.metadata
        assert first.start.call_args == second.start.call_args
        assert first.observe.call_args_list == second.observe.call_args_list
        description, = first.start.call_args.args
        assert set(asdict(description)) == {"benchmark_id", "input_space", "execution_budget"}
        for call in first.observe.call_args_list:
            candidate, feedback = call.args
            assert type(candidate) is TrialInput
            assert set(asdict(feedback)) == {"status", "execution_index", "budget_remaining"}
        for value in (description, first.metadata, candidate, feedback):
            assert not hasattr(value, "partition")
            assert not hasattr(value, "source")
    assert results[0].records == results[1].records
    assert "development" in results[0].to_json()
    assert "held_out" in results[1].to_json()


def test_real_arm_legacy_threshold_campaign_is_bounded_to_two_executions(cortex_m_corpus):
    """Development-labelled legacy fixture: budget 1, enum + test-only seed 0."""
    benchmark, image = cortex_m_corpus["threshold"]

    def execute(values):
        observed = observe_symbol(
            str(image), benchmark.failure_symbol, benchmark.breakpoint,
            input_values={benchmark.input_symbol: values[0]},
        )
        success = observed["success"] and observed["value"] in (0, 1)
        return Observation(
            success, success and observed["value"] == 1,
            observed.get("stdout", ""), observed.get("stderr", ""),
        )

    executor = Mock(side_effect=execute)
    registry = FakeRegistry(
        executor, space=InputSpace(1, benchmark.input_min, benchmark.input_max), identifiers=(ID_A,),
    )
    declaration = protocol(benchmark_ids=(ID_A,), execution_budget=1, random_seeds=(0,))
    assert not declaration.is_standard
    result = CampaignRunner(registry).run(declaration)
    assert len(result.records) == len(registry.owners) == executor.call_count == 2
    assert result.planned_run_count == result.completed_record_count == result.valid_search_run_count == 2
    assert result.infrastructure_aborted_run_count == 0
    assert [call.args[0] for call in executor.call_args_list] == [(0,), (197,)]
    assert [record.run.strategy.seed for record in result.records] == [None, 0]
    assert all(type(owner.strategy_api()) is StrategyHandle for owner in registry.owners)
    outcomes = ((TerminationReason.BUDGET_EXHAUSTED, False, None), (TerminationReason.FAILURE_DISCOVERED, True, 1))
    for record, owner, (termination, discovered, first_execution) in zip(result.records, registry.owners, outcomes):
        assert record.run.evaluation == owner.result()
        assert record.description == owner.describe()
        assert record.run.termination is termination, owner.diagnostics()
        evaluation = record.run.evaluation
        assert evaluation.attempted_executions == evaluation.successful_executions == 1
        assert evaluation.infrastructure_failures == 0
        assert not evaluation.aborted and evaluation.failure_found is discovered
        assert evaluation.first_failure_execution == first_execution
        assert evaluation.execution_budget == 1 and evaluation.budget_remaining == 0
    assert result.protocol.partition == "development"
