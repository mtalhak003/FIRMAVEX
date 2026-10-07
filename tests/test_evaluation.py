import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, FrozenInstanceError
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.evaluation import registry as registry_module


ID = "b-3874d6a4a92f46758d73854abf0a08df"
SPACE = InputSpace(4, 0, 15)
TRIAL = TrialInput((1, 2, 3, 4))


def session(executor, budget=3):
    return EvaluationSession(ID, SPACE, budget, "controlled-test", executor, random_seed=42)


def test_accounting_and_first_failure_are_evaluator_owned(monkeypatch):
    clock = Mock(side_effect=[100.0, 102.5])
    monkeypatch.setattr("src.firmavex.evaluation.evaluator.time.monotonic", clock)
    run = session(Mock(side_effect=[Observation(True), Observation(True, True), Observation(True, True)]))
    assert run.execute(TRIAL).status == "safe"
    assert run.execute(TRIAL).status == "triggered"
    assert run.execute(TRIAL).status == "triggered"
    result = run.result()
    assert result.attempted_executions == result.successful_executions == 3
    assert result.infrastructure_failures == 0
    assert result.failure_triggering_executions == 2
    assert result.failure_found is True
    assert result.first_failure_execution == 2
    assert result.time_to_first_failure_seconds == 2.5
    assert result.budget_remaining == 0 and result.budget_exhausted
    assert result.random_seed == 42
    assert result.reproducibility is None


def test_budget_exhaustion_is_not_no_failure_exists():
    executor = Mock(return_value=Observation(True))
    run = session(executor, budget=1)
    assert run.execute(TRIAL).status == "safe"
    for _ in range(5):
        feedback = run.execute(TRIAL)
        assert feedback.status == "budget_exhausted"
        assert feedback.execution_index is None
    executor.assert_called_once_with(TRIAL.values)
    assert run.result().failure_found is False
    assert run.result().budget_exhausted


def test_zero_budget_never_executes():
    executor = Mock()
    run = session(executor, budget=0)
    assert run.execute(TRIAL).status == "budget_exhausted"
    assert run.result().attempted_executions == 0
    executor.assert_not_called()


@pytest.mark.parametrize("outcome", [
    Observation(False, True, "source filename secret", "GDB secret symbol"),
    RuntimeError("secret path"),
    {"unexpected": "malformed executor result"},
])
def test_infrastructure_failure_counts_and_aborts_without_feedback_leak(outcome):
    executor = Mock(side_effect=[outcome, Observation(True, True)])
    run = session(executor)
    feedback = run.execute(TRIAL)
    assert feedback.status == "infrastructure_failure"
    assert feedback.execution_index == 1 and feedback.budget_remaining == 2
    assert run.execute(TRIAL).status == "session_aborted"
    executor.assert_called_once()
    result = run.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == result.failure_triggering_executions == 0
    assert not result.failure_found and result.aborted
    assert result.first_failure_execution is None
    assert "secret" not in json.dumps(asdict(feedback))
    assert run.diagnostics()[0]["execution_index"] == 1
    assert run.diagnostics()[0]["values"] == TRIAL.values


def test_failure_on_last_budget_slot_is_distinct_from_exhaustion():
    run = session(Mock(return_value=Observation(False)), budget=1)
    assert run.execute(TRIAL).status == "infrastructure_failure"
    assert run.result().budget_exhausted and run.result().aborted
    assert run.execute(TRIAL).status == "session_aborted"


@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("budget", [1, 2])
def test_interrupted_execution_is_charged_aborted_and_reraised(interruption_type, budget):
    interruption = interruption_type("private interruption diagnostic /firmware/secret.elf")
    executor = Mock(side_effect=[interruption, Observation(True, True)])
    owner = session(executor, budget=budget)
    run = owner.strategy_api()
    with pytest.raises(interruption_type) as caught:
        run.execute(TRIAL)
    assert caught.value is interruption
    result = run.result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == result.failure_triggering_executions == 0
    assert result.aborted and not result.failure_found
    assert result.first_failure_execution is None
    assert result.budget_remaining == budget - 1
    assert result.budget_exhausted == (budget == 1)
    diagnostic, = owner.diagnostics()
    assert diagnostic["execution_index"] == 1
    assert diagnostic["values"] == TRIAL.values
    assert interruption_type.__name__ in diagnostic["stderr"]
    assert str(interruption) in diagnostic["stderr"]
    for _ in range(5):
        feedback = run.execute(TRIAL)
        assert feedback.status == "session_aborted"
        assert feedback.execution_index is None
        assert feedback.budget_remaining == budget - 1
        assert run.result() == result
    executor.assert_called_once_with(TRIAL.values)
    assert result.attempted_executions <= result.execution_budget
    public_records = json.dumps([asdict(run.describe()), asdict(feedback), asdict(run.result())])
    for private in ("private interruption diagnostic", "secret.elf", interruption_type.__name__):
        assert private not in public_records
    assert not hasattr(run, "diagnostics")


def test_trigger_then_infrastructure_failure_preserves_discovery_and_aborts():
    executor = Mock(side_effect=[
        Observation(True, True), Observation(False, stderr="executor failed"), Observation(True, True),
    ])
    run = session(executor)
    assert run.execute(TRIAL).status == "triggered"
    discovery = run.result()
    assert run.execute(TRIAL).status == "infrastructure_failure"
    result = run.result()
    assert result.aborted and result.failure_found
    assert result.attempted_executions == 2
    assert result.successful_executions == result.infrastructure_failures == 1
    assert result.failure_triggering_executions == 1
    assert result.first_failure_execution == discovery.first_failure_execution == 1
    assert result.time_to_first_failure_seconds == discovery.time_to_first_failure_seconds
    assert run.execute(TRIAL).status == "session_aborted"
    assert executor.call_count == 2
    assert run.result() == result


@pytest.mark.parametrize("values", [(1, 2), (1, 2, 3, 16), (1, 2, 3, -1), (True, 2, 3, 4), [1, 2, 3, 4]])
def test_invalid_inputs_do_not_execute_or_consume_budget(values):
    executor = Mock()
    run = session(executor)
    assert run.execute(TrialInput(values)).status == "invalid_input"
    assert run.result().attempted_executions == 0
    executor.assert_not_called()


@pytest.mark.parametrize("budget", [-1, True, 1.5])
def test_invalid_budgets_rejected(budget):
    with pytest.raises(ValueError):
        session(Mock(), budget=budget)


def test_concurrent_api_requests_are_serialized_and_cannot_overdraw_budget():
    executor = Mock(return_value=Observation(True))
    run = session(executor, budget=3)
    with ThreadPoolExecutor(max_workers=8) as pool:
        feedback = list(pool.map(lambda _: run.execute(TRIAL), range(20)))
    assert sum(item.status == "safe" for item in feedback) == 3
    assert executor.call_count == 3
    assert run.result().attempted_executions == 3


def test_public_records_are_opaque_and_immutable():
    owner = session(Mock(return_value=Observation(True)))
    run = owner.strategy_api()
    assert {name for name in dir(run) if not name.startswith("_")} == {"describe", "execute", "result"}
    assert not hasattr(run, "diagnostics")
    assert not hasattr(run, "source")
    spec = asdict(run.describe())
    assert set(spec) == {"benchmark_id", "input_space", "execution_budget"}
    assert spec["benchmark_id"] == ID
    assert spec["input_space"] == {"width": 4, "minimum": 0, "maximum": 15}
    with pytest.raises(FrozenInstanceError):
        run.describe().execution_budget = 1000
    feedback = asdict(run.execute(TRIAL))
    assert set(feedback) == {"status", "execution_index", "budget_remaining", "execution_signature"}
    assert feedback["execution_signature"] is None
    allowed_result = {
        "benchmark_id", "strategy_id", "execution_budget", "attempted_executions",
        "successful_executions", "infrastructure_failures", "failure_triggering_executions",
        "failure_found", "first_failure_execution", "time_to_first_failure_seconds",
        "budget_remaining", "budget_exhausted", "aborted", "random_seed", "reproducibility",
    }
    assert set(asdict(run.result())) == allowed_result
    serialized = json.dumps([spec, feedback, asdict(run.result())])
    for forbidden in (".c", ".elf", "source", "symbol", "ground_truth", "trigger_interval", "threshold", "held_out"):
        assert forbidden not in serialized


def register_fake_image(monkeypatch, registry, identifier, path):
    def build(*args, **kwargs):
        path.write_bytes(b"controlled image")
        return {"success": True, "output_file": str(path)}

    monkeypatch.setattr(registry_module, "build_cortex_m_firmware", build)
    assert registry.build(identifier, path)["success"]


def test_registry_separates_administrator_splits_without_revealing_them(tmp_path, monkeypatch):
    registry = BenchmarkRegistry()
    development = registry.select("development")
    held_out = registry.select("held_out")
    assert len(development) == 6 and len(held_out) == 2
    assert not {item.benchmark_id for item in development} & {item.benchmark_id for item in held_out}
    for benchmark in (*development, *held_out):
        assert benchmark.name not in benchmark.benchmark_id
        register_fake_image(monkeypatch, registry, benchmark.benchmark_id, tmp_path / f"{benchmark.benchmark_id}.elf")
        run = registry.open_session(benchmark.benchmark_id, 1, "test")
        assert set(asdict(run.describe())) == {"benchmark_id", "input_space", "execution_budget"}
    with pytest.raises(ValueError):
        registry.select("all")
    with pytest.raises(ValueError):
        registry.open_session("unknown", 1, "test")


def test_missing_image_is_charged_as_infrastructure_failure(tmp_path, monkeypatch):
    registry = BenchmarkRegistry()
    benchmark = registry.select("development")[0]
    image = tmp_path / "missing.elf"
    register_fake_image(monkeypatch, registry, benchmark.benchmark_id, image)
    run = registry.open_session(benchmark.benchmark_id, 2, "test")
    image.unlink()
    assert run.execute(TRIAL).status == "infrastructure_failure"
    assert run.result().attempted_executions == 1
    assert run.result().infrastructure_failures == 1
    assert "image unavailable" in run.diagnostics()[0]["stderr"]


def test_sessions_cannot_use_unregistered_or_replaced_images(tmp_path, monkeypatch):
    registry = BenchmarkRegistry()
    identifier = registry.select("development")[0].benchmark_id
    with pytest.raises(ValueError, match="successfully built"):
        registry.open_session(identifier, 1, "test")
    image = tmp_path / "image.elf"
    register_fake_image(monkeypatch, registry, identifier, image)
    run = registry.open_session(identifier, 1, "test")
    image.write_bytes(b"other benchmark")
    observe = Mock()
    monkeypatch.setattr(registry_module, "observe_symbol", observe)
    assert run.execute(TRIAL).status == "infrastructure_failure"
    assert run.result().attempted_executions == 1
    assert "image changed" in run.diagnostics()[0]["stderr"]
    observe.assert_not_called()


def test_failed_rebuild_invalidates_registered_image(tmp_path, monkeypatch):
    registry = BenchmarkRegistry()
    identifier = registry.select("development")[0].benchmark_id
    register_fake_image(monkeypatch, registry, identifier, tmp_path / "image.elf")
    monkeypatch.setattr(registry_module, "build_cortex_m_firmware", Mock(return_value={"success": False}))
    assert registry.build(identifier, tmp_path / "image.elf")["success"] is False
    with pytest.raises(ValueError, match="successfully built"):
        registry.open_session(identifier, 1, "test")
