"""Synthetic orchestration tests with real evaluator/strategies/archive storage.

No firmware is dispatched by these tests. Runtime and ELF/tool probes are
explicitly injected; every saved measurement must remain synthetic_test.
"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

import pytest

from firmavex.product import services
from firmavex.product.config import ProductConfig
from firmavex.product.errors import ProductError
from firmavex.product.runtime import ExecutionReceipt
from firmavex.product.store import RunStore
from firmavex.product.tools import Toolchain
from src.firmavex.evaluation.api import ExecutionSignature
from src.firmavex.evaluation.evaluator import Observation
from src.firmavex.strategies.api import StrategyMetadata


@pytest.fixture
def project(tmp_path, monkeypatch):
    image = tmp_path / "original firmware.elf"
    image.write_bytes(b"synthetic file bytes, not ARM firmware")
    config = ProductConfig(firmware=image, input_symbols=("inputs[0]", "inputs[1]"),
                           ready_breakpoint="input_ready", completion_breakpoint="test_complete",
                           failure_symbol="failure", input_max=3, execution_budget=16)
    tools = Toolchain("/synthetic/qemu", "/synthetic/gdb", identities={
        "qemu": {"path": "/synthetic/qemu", "sha256": "a" * 64, "size_bytes": 10, "version": "synthetic QEMU"},
        "gdb": {"path": "/synthetic/gdb", "sha256": "b" * 64, "size_bytes": 20, "version": "synthetic GDB"}})

    def inspect(config):
        return {"firmware_sha256": hashlib.sha256(config.firmware.read_bytes()).hexdigest(),
                "machine": "synthetic_test_not_real_firmware"}

    monkeypatch.setattr(services, "inspect_elf", inspect)
    monkeypatch.setattr(services, "discover", lambda *args, **kwargs: tools)
    return config, tools


class SyntheticExecutor:
    def __init__(self, action=None, evidence_override=None):
        self.calls = []
        self.action = action or (lambda values, index: Observation(True, values == (2, 1)))
        self.evidence_override = evidence_override or {}
        self.last_evidence = None

    def execute(self, values):
        self.calls.append(values)
        evidence = {"guest_dispatched": True, "input_injected": True, "completion_reached": True,
                    "cleanup_verified": True, "measurement_mode": "real_firmware",
                    "stdout": "synthetic private stdout", "stderr": "synthetic private stderr"}
        evidence.update(self.evidence_override)
        self.last_evidence = evidence
        return ExecutionReceipt(self.action(values, len(self.calls)), evidence)


def factory(executor):
    return lambda *args: executor


def snapshot(path):
    with RunStore(path) as store:
        return store.snapshot()


def archive_bytes(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def mutate_metadata(path, edit):
    db = sqlite3.connect(path / "run.sqlite3")
    metadata = json.loads(db.execute("SELECT metadata FROM run").fetchone()[0])
    edit(metadata)
    db.execute("UPDATE run SET metadata=?", (json.dumps(metadata, sort_keys=True),))
    db.commit()
    db.close()


def mutate_first_attempt(path, edit):
    db = sqlite3.connect(path / "run.sqlite3")
    record = json.loads(db.execute("SELECT record FROM attempts WHERE sequence=1").fetchone()[0])
    edit(record)
    db.execute("UPDATE attempts SET record=? WHERE sequence=1", (json.dumps(record, sort_keys=True),))
    db.commit()
    db.close()


def test_search_retains_exact_first_trigger_and_authoritative_accounting(project, tmp_path):
    config, tools = project
    executor = SyntheticExecutor()
    events = []
    result = services.run_project(config, tmp_path / "run", event_callback=events.append,
                                  _executor_factory=factory(executor))
    assert result["state"] == "completed"
    assert result["outcome"] == "configured_failure_observed"
    assert result["triggering_input"] == [2, 1]
    assert result["accounting"]["attempted_executions"] == 10
    assert result["accounting"]["successful_executions"] == 10
    assert result["accounting"]["infrastructure_failures"] == 0
    assert result["accounting"]["first_failure_execution"] == 10
    assert result["measurement_mode"] == "synthetic_test"
    assert executor.calls == [(a, b) for a in range(3) for b in range(4) if (a, b) <= (2, 1)]
    saved = snapshot(tmp_path / "run")
    assert saved["result"] == result
    assert [attempt["record"]["input"] for attempt in saved["attempts"]] == [list(v) for v in executor.calls]
    assert all(attempt["record"]["evidence"]["measurement_mode"] == "synthetic_test"
               for attempt in saved["attempts"])
    assert saved["metadata"]["tools"] == tools.to_dict()
    assert json.loads((tmp_path / "run/result.json").read_text()) == result
    report = (tmp_path / "run/report.md").read_text()
    assert "Charged evaluator attempts: 10" in report
    assert "not independently verified physical executions" in report
    assert "not proof that firmware is safe" in report
    assert [event["type"] for event in events] == ["trial_complete"] * 10


@pytest.mark.parametrize("strategy,seed", [("enumerative", None), ("random", 17), ("guided", 17)])
def test_existing_strategies_dispatch_unique_valid_candidates(project, tmp_path, strategy, seed):
    config, _ = project
    config = replace(config, strategy=strategy, seed=seed, input_max=1, execution_budget=10)
    executor = SyntheticExecutor(lambda values, index: Observation(
        True, False, execution_signature=ExecutionSignature(hashlib.sha256(bytes(values)).hexdigest())))
    result = services.run_project(config, tmp_path / strategy, _executor_factory=factory(executor))
    assert result["outcome"] == "domain_exhausted"
    assert len(executor.calls) == len(set(executor.calls)) == 4
    assert set(executor.calls) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert result["accounting"]["attempted_executions"] == 4


def test_no_discovery_budget_is_censoring_not_safety_claim(project, tmp_path):
    config, _ = project
    executor = SyntheticExecutor(lambda values, index: Observation(True, False))
    result = services.run_project(replace(config, execution_budget=3), tmp_path / "run",
                                  _executor_factory=factory(executor))
    assert result["outcome"] == "no_failure_within_budget"
    assert result["triggering_input"] is None
    assert result["accounting"]["attempted_executions"] == 3
    assert result["accounting"]["budget_exhausted"] is True
    assert result["accounting"]["failure_found"] is False


@pytest.mark.parametrize("missing", ["guest_dispatched", "input_injected", "completion_reached", "cleanup_verified"])
def test_trigger_cannot_override_missing_execution_evidence(project, tmp_path, missing):
    config, _ = project
    executor = SyntheticExecutor(lambda values, index: Observation(True, True), {missing: False})
    result = services.run_project(config, tmp_path / "run", _executor_factory=factory(executor))
    assert len(executor.calls) == 1
    assert result["state"] == "failed"
    assert result["outcome"] == "infrastructure_failure"
    assert result["triggering_input"] is None
    assert result["accounting"]["failure_found"] is False
    assert result["accounting"]["attempted_executions"] == 1
    assert result["accounting"]["infrastructure_failures"] == 1
    assert result["execution_evidence"] == "incomplete"
    assert snapshot(tmp_path / "run")["result"] == result


def test_failed_observation_aborts_before_later_trigger_and_retains_raw_diagnostics(project, tmp_path):
    config, _ = project
    executor = SyntheticExecutor(lambda values, index: Observation(
        False, stdout="underlying QEMU stdout", stderr="underlying GDB stderr") if index == 1
        else Observation(True, True))
    result = services.run_project(config, tmp_path / "run", _executor_factory=factory(executor))
    assert executor.calls == [(0, 0)]
    assert result["state"] == "failed"
    assert result["triggering_input"] is None
    assert result["accounting"]["aborted"] is True
    assert result["accounting"]["attempted_executions"] == 1
    assert "underlying QEMU stdout" in result["error"]["stdout"]
    assert "underlying GDB stderr" in result["error"]["stderr"]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interruption_after_charge_preserves_original_and_interrupted_evidence(project, tmp_path, interruption):
    config, _ = project
    original = interruption("administrator cancellation reason")

    def action(values, index):
        raise original

    executor = SyntheticExecutor(action)
    with pytest.raises(interruption) as caught:
        services.run_project(config, tmp_path / "run", _executor_factory=factory(executor))
    assert caught.value is original
    saved = snapshot(tmp_path / "run")
    assert saved["state"] == "cancelled"
    result = saved["result"]
    assert result["accounting"]["attempted_executions"] == 1
    assert result["accounting"]["successful_executions"] == 0
    assert result["accounting"]["infrastructure_failures"] == 1
    assert result["accounting"]["aborted"] is True
    assert result["error"]["exception_type"] == interruption.__name__
    assert result["error"]["message"] == "administrator cancellation reason"
    assert len(executor.calls) == 1
    attempt = saved["attempts"][0]["record"]
    assert attempt["input"] == [0, 0]
    assert attempt["interrupted"] is True
    assert attempt["evidence"]["stdout"] == "synthetic private stdout"
    assert attempt["evidence"]["stderr"] == "synthetic private stderr"


def test_cancellation_before_admission_consumes_no_execution(project, tmp_path):
    config, _ = project
    cancel = threading.Event()
    cancel.set()
    executor = SyntheticExecutor()
    with pytest.raises(KeyboardInterrupt):
        services.run_project(config, tmp_path / "run", cancel_event=cancel,
                             _executor_factory=factory(executor))
    saved = snapshot(tmp_path / "run")
    assert executor.calls == []
    assert saved["attempts"] == []
    assert saved["result"]["accounting"]["attempted_executions"] == 0
    assert saved["state"] == "cancelled"


def test_cancel_between_trials_preserves_completed_observation(project, tmp_path):
    config, _ = project
    cancel = threading.Event()
    executor = SyntheticExecutor(lambda values, index: Observation(True, False))

    def completed(event):
        if event.get("type") == "trial_complete":
            cancel.set()

    with pytest.raises(KeyboardInterrupt):
        services.run_project(config, tmp_path / "run", cancel_event=cancel,
                             event_callback=completed, _executor_factory=factory(executor))
    result = snapshot(tmp_path / "run")["result"]
    assert executor.calls == [(0, 0)]
    assert result["accounting"]["attempted_executions"] == 1
    assert result["accounting"]["successful_executions"] == 1
    assert result["accounting"]["infrastructure_failures"] == 0
    assert result["state"] == "cancelled"


def test_reproduction_reuses_exact_vector_and_separate_authoritative_counts(project, tmp_path):
    config, _ = project
    parent = tmp_path / "search"
    result = services.run_project(config, parent, _executor_factory=factory(SyntheticExecutor()))
    before = archive_bytes(parent)
    replay = SyntheticExecutor()
    reproduced = services.reproduce_run(parent, tmp_path / "reproduction", attempts=3,
                                        _executor_factory=factory(replay))
    assert replay.calls == [(2, 1)] * 3
    assert reproduced["outcome"] == "reproduced_in_emulator"
    assert reproduced["reproduction"] == {
        "requested_attempts": 3, "completed_observations": 3, "matching_observations": 3,
        "status": "reproduced_in_emulator", "input": [2, 1]}
    assert reproduced["accounting"]["attempted_executions"] == 3
    assert reproduced["accounting"]["execution_budget"] == 3
    assert reproduced["parent"]["run_id"] == result["run_id"]
    assert reproduced["measurement_mode"] == "synthetic_test"
    assert archive_bytes(parent) == before


def test_inconsistent_reproduction_is_not_labeled_reproduced(project, tmp_path):
    config, _ = project
    parent = tmp_path / "search"
    services.run_project(config, parent, _executor_factory=factory(SyntheticExecutor()))
    executor = SyntheticExecutor(lambda values, index: Observation(True, index != 2))
    result = services.reproduce_run(parent, tmp_path / "replay", 3, _executor_factory=factory(executor))
    assert result["outcome"] == "reproduction_inconsistent"
    assert result["reproduction"]["matching_observations"] == 2
    assert result["reproduction"]["completed_observations"] == 3
    assert result["accounting"]["attempted_executions"] == 3


def test_trigger_then_reproduction_infrastructure_failure_keeps_discovery(project, tmp_path):
    config, _ = project
    parent = tmp_path / "search"
    services.run_project(config, parent, _executor_factory=factory(SyntheticExecutor()))
    executor = SyntheticExecutor(lambda values, index: Observation(True, True) if index == 1
                                 else Observation(False, stderr="replay debugger failure"))
    result = services.reproduce_run(parent, tmp_path / "replay", 3, _executor_factory=factory(executor))
    assert executor.calls == [(2, 1), (2, 1)]
    assert result["state"] == "failed"
    assert result["outcome"] == "infrastructure_failure"
    assert result["triggering_input"] == [2, 1]
    assert result["accounting"]["failure_found"] is True
    assert result["accounting"]["first_failure_execution"] == 1
    assert result["accounting"]["aborted"] is True
    assert result["accounting"]["infrastructure_failures"] == 1
    assert result["reproduction"]["status"] == "indeterminate"


@pytest.mark.parametrize("attempts", [0, 101, True, 1.5, "3"])
def test_reproduction_requires_explicit_bounded_integer(project, tmp_path, attempts):
    with pytest.raises(ProductError, match="1 to 100"):
        services.reproduce_run(tmp_path / "absent", tmp_path / "new", attempts)
    assert not (tmp_path / "new").exists()


def test_synthetic_search_cannot_be_promoted_to_real_reproduction(project, tmp_path):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    with pytest.raises(ProductError) as error:
        services.reproduce_run(tmp_path / "run", tmp_path / "new")
    assert error.value.category == "synthetic_result"
    assert not (tmp_path / "new").exists()


def test_no_saved_trigger_reproduction_fails_before_dispatch(project, tmp_path):
    config, _ = project
    services.run_project(replace(config, execution_budget=1), tmp_path / "run",
                         _executor_factory=factory(SyntheticExecutor(lambda values, index: Observation(True))))
    executor = SyntheticExecutor()
    with pytest.raises(ProductError) as error:
        services.reproduce_run(tmp_path / "run", tmp_path / "new", _executor_factory=factory(executor))
    assert error.value.category == "no_saved_trigger"
    assert executor.calls == []


def test_readonly_inspection_and_export_preserve_original_archive(project, tmp_path):
    config, _ = project
    root = tmp_path / "run"
    services.run_project(config, root, _executor_factory=factory(SyntheticExecutor()))
    before = archive_bytes(root)
    inspection = services.inspect_run(root)
    assert inspection["inspection_is_not_execution_verification"] is True
    assert inspection["recovery_required"] is False
    assert inspection["attempts_recorded"] == 10
    exported = services.export_run(root, tmp_path / "export")
    assert exported["firmware_executed"] is False
    assert exported["private_administrative_export"] is True
    assert archive_bytes(root) == before
    evidence = json.loads((tmp_path / "export/evidence.json").read_text())
    assert evidence["result"]["measurement_mode"] == "synthetic_test"
    for name, identity in exported["files"].items():
        assert hashlib.sha256((tmp_path / "export" / name).read_bytes()).hexdigest() == identity["sha256"]


def test_existing_output_refused_without_overwrite_or_dispatch(project, tmp_path):
    config, _ = project
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("retain")
    executor = SyntheticExecutor()
    with pytest.raises(ProductError):
        services.run_project(config, output, _executor_factory=factory(executor))
    assert executor.calls == []
    assert (output / "keep.txt").read_text() == "retain"


def test_export_existing_destination_refused(project, tmp_path):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    output = tmp_path / "export"
    output.mkdir()
    (output / "keep").write_text("retain")
    with pytest.raises(ProductError, match="existing"):
        services.export_run(tmp_path / "run", output)
    assert (output / "keep").read_text() == "retain"


@pytest.mark.parametrize("artifact", ["firmware.elf", "project.json", "result.json", "report.md"])
def test_missing_artifacts_fail_inspection_and_reproduction(project, tmp_path, artifact):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    (tmp_path / "run" / artifact).unlink()
    with pytest.raises(ProductError):
        services.inspect_run(tmp_path / "run")
    with pytest.raises(ProductError):
        services.reproduce_run(tmp_path / "run", tmp_path / "new", _executor_factory=factory(SyntheticExecutor()))
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("artifact", ["firmware.elf", "project.json", "result.json", "report.md"])
def test_tampered_artifacts_fail_closed(project, tmp_path, artifact):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    with (tmp_path / "run" / artifact).open("ab") as target:
        target.write(b"unrecorded change")
    with pytest.raises(ProductError):
        services.inspect_run(tmp_path / "run")


def test_metadata_image_identity_contradiction_is_not_authoritative(project, tmp_path):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    mutate_metadata(tmp_path / "run", lambda metadata: metadata["firmware"].update(firmware_sha256="0" * 64))
    with pytest.raises(ProductError):
        services.inspect_run(tmp_path / "run")


def test_metadata_configuration_contradiction_is_not_authoritative(project, tmp_path):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    mutate_metadata(tmp_path / "run", lambda metadata: metadata["configuration"].update(execution_budget=999))
    with pytest.raises(ProductError):
        services.inspect_run(tmp_path / "run")


@pytest.mark.parametrize("edit", [
    lambda record: record.update(input=[99, 99]),
    lambda record: record.update(input=[0]),
    lambda record: record["feedback"].update(execution_index=999),
    lambda record: record["feedback"].update(budget_remaining=999),
])
def test_retained_input_and_feedback_contradictions_rejected(project, tmp_path, edit):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    mutate_first_attempt(tmp_path / "run", edit)
    with pytest.raises(ProductError):
        services.inspect_run(tmp_path / "run")


def test_toolchain_change_reproduction_rejected(project, tmp_path, monkeypatch):
    config, tools = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    different = Toolchain(tools.qemu, tools.gdb, identities={**tools.identities, "extra": {"changed": True}})
    monkeypatch.setattr(services, "discover", lambda *args: different)
    executor = SyntheticExecutor()
    with pytest.raises(ProductError) as error:
        services.reproduce_run(tmp_path / "run", tmp_path / "new", _executor_factory=factory(executor))
    assert error.value.category == "toolchain_changed"
    assert executor.calls == []


def test_firmware_change_during_import_rejected_without_admission(project, tmp_path, monkeypatch):
    config, _ = project
    actual_inspect = services.inspect_elf

    def changing_inspect(value):
        result = actual_inspect(value)
        if value.firmware == config.firmware:
            config.firmware.write_bytes(b"changed after original static inspection")
        return result

    monkeypatch.setattr(services, "inspect_elf", changing_inspect)
    executor = SyntheticExecutor()
    with pytest.raises(ProductError) as error:
        services.run_project(config, tmp_path / "run", _executor_factory=factory(executor))
    assert error.value.category == "firmware_changed"
    assert executor.calls == []
    assert snapshot(tmp_path / "run")["attempts"] == []


def test_invalid_strategy_output_is_not_domain_exhaustion(project, tmp_path, monkeypatch):
    config, _ = project

    class InvalidStrategy:
        metadata = StrategyMetadata("enumerative")

        def start(self, description):
            pass

        def propose(self):
            return "invalid candidate"

        def observe(self, candidate, feedback):
            raise AssertionError("Invalid output should not be observed")

    monkeypatch.setattr(services, "create_strategy", lambda metadata: InvalidStrategy())
    executor = SyntheticExecutor()
    result = services.run_project(config, tmp_path / "run", _executor_factory=factory(executor))
    assert result["state"] == "failed"
    assert result["outcome"] == "invalid_output"
    assert result["accounting"]["attempted_executions"] == 0
    assert executor.calls == []


def test_unfinished_inspection_is_readonly_and_recovery_is_explicit(project, tmp_path):
    config, tools = project
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({"configuration": config.to_dict(), "tools": tools.to_dict()})
    before = archive_bytes(root)
    inspection = services.inspect_run(root)
    assert inspection["state"] == "running"
    assert inspection["recovery_required"] is True
    assert archive_bytes(root) == before
    recovered = services.recover_run(root)
    assert recovered["state"] == "interrupted"
    assert recovered["result"]["accounting_status"] == "unknown"


def test_export_unfinished_run_refused(project, tmp_path):
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({})
    with pytest.raises(ProductError, match="terminal"):
        services.export_run(root, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_executor_construction_error_preserves_failed_zero_dispatch_result(project, tmp_path):
    config, _ = project
    original = ProductError("dependency_failed", "synthetic executor setup error")

    def fail_factory(*args):
        raise original

    with pytest.raises(ProductError) as caught:
        services.run_project(config, tmp_path / "run", _executor_factory=fail_factory)
    assert caught.value is original
    saved = snapshot(tmp_path / "run")
    assert saved["state"] == "failed"
    assert saved["attempts"] == []
    assert saved["result"]["accounting"] is None
    assert saved["result"]["error"]["category"] == "dependency_failed"
    assert services.inspect_run(tmp_path / "run")["state"] == "failed"
    assert "Charged evaluator attempts: unknown" in (tmp_path / "run/report.md").read_text()


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_preowner_cancellation_does_not_invent_counters(project, tmp_path, interruption):
    config, _ = project
    original = interruption("cancelled during executor construction")

    def fail_factory(*args):
        raise original

    with pytest.raises(interruption) as caught:
        services.run_project(config, tmp_path / "run", _executor_factory=fail_factory)
    assert caught.value is original
    saved = snapshot(tmp_path / "run")
    assert saved["state"] == "cancelled"
    assert saved["attempts"] == []
    assert saved["result"]["accounting"] is None


def test_uncommitted_result_json_recovery_retains_unknown_database_accounting(project, tmp_path, monkeypatch):
    config, tools = project
    root = tmp_path / "run"
    declared = {
        "schema_version": 1, "run_id": "unfinished-run", "configuration": config.to_dict(),
        "tools": tools.to_dict(), "measurement_mode": "synthetic_test", "operation": "search",
        "firmware": services.inspect_elf(config),
    }
    uncommitted = {"kind": "firmavex_product_result", "state": "completed", "success": True,
                   "triggering_input": [2, 1], "accounting": {"attempted_executions": 10}}
    with RunStore(root, create=True) as store:
        store.initialize(declared)
        store.add_artifact("firmware.elf", config.firmware)
        saved_config = config.to_dict()
        saved_config["firmware"] = "firmware.elf"
        store.write_json("project.json", saved_config)
        store.write_json("result.json", uncommitted)
    before = (root / "result.json").read_bytes()
    inspection = services.inspect_run(root)
    assert inspection["state"] == "running"
    assert inspection["result"] is None
    recovered = services.recover_run(root)
    assert recovered["state"] == "interrupted"
    assert recovered["result"]["accounting_status"] == "unknown"
    assert recovered["uncommitted_result_artifact"] is True
    assert "attempted_executions" not in recovered["result"]
    assert (root / "result.json").read_bytes() == before
    assert services.inspect_run(root)["uncommitted_result_artifact"] is True
    calls = []

    def capture_restart(*args, **kwargs):
        calls.append((args, kwargs))
        return {"restart_authorized": True}

    monkeypatch.setattr(services, "_execute_project", capture_restart)
    assert services.restart_run(root, tmp_path / "new-run") == {"restart_authorized": True}
    assert calls[0][1]["parent"]["operation"] == "restart"
    assert "Fresh full search" in calls[0][1]["parent"]["warning"]
    assert calls[0][0][1] == tmp_path / "new-run"
    assert (root / "result.json").read_bytes() == before


def test_completed_search_cannot_be_automatically_restarted(project, tmp_path, monkeypatch):
    config, _ = project
    services.run_project(config, tmp_path / "run", _executor_factory=factory(SyntheticExecutor()))
    monkeypatch.setattr(services, "_execute_project", lambda *args, **kwargs: pytest.fail("unexpected dispatch"))
    with pytest.raises(ProductError) as caught:
        services.restart_run(tmp_path / "run", tmp_path / "new")
    assert caught.value.category == "restart_not_authorized"


def test_progress_callback_error_preserves_completed_trial_and_original_exception(project, tmp_path):
    config, _ = project
    executor = SyntheticExecutor(lambda values, index: Observation(True, True))
    original = RuntimeError("UI event channel failed")

    def fail_callback(event):
        raise original

    with pytest.raises(RuntimeError) as caught:
        services.run_project(config, tmp_path / "run", event_callback=fail_callback,
                             _executor_factory=factory(executor))
    assert caught.value is original
    saved = snapshot(tmp_path / "run")
    assert saved["result"]["state"] == "failed"
    assert saved["result"]["triggering_input"] == [0, 0]
    assert saved["result"]["accounting"]["attempted_executions"] == 1
    assert saved["result"]["accounting"]["successful_executions"] == 1
    assert saved["result"]["accounting"]["infrastructure_failures"] == 0
    assert executor.calls == [(0, 0)]


def test_persistence_failure_after_admission_is_not_reported_as_completed(project, tmp_path, monkeypatch):
    config, _ = project
    executor = SyntheticExecutor(lambda values, index: Observation(True, True))
    original = ProductError("persistence_error", "attempt database unavailable")

    def fail_attempt(store, record):
        raise original

    monkeypatch.setattr(RunStore, "record_attempt", fail_attempt)
    with pytest.raises(ProductError) as caught:
        services.run_project(config, tmp_path / "run", _executor_factory=factory(executor))
    assert caught.value is original
    saved = snapshot(tmp_path / "run")
    assert saved["state"] in {"failed", "running"}
    assert saved["state"] != "completed"
    assert executor.calls == [(0, 0)]
    inspection = services.inspect_run(tmp_path / "run")
    assert inspection["accounting_verification"]["status"] == "incomplete_receipts"
    assert inspection["accounting_verification"]["execution_verification"] == "failed"
    assert inspection["accounting_verification"]["missing_receipts"] == 1
    assert inspection["result"]["triggering_input"] == [0, 0]
    assert inspection["result"]["accounting"]["attempted_executions"] == 1


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interruption_and_receipt_write_failure_remain_original_and_explicitly_incomplete(
    project, tmp_path, monkeypatch, interruption
):
    config, _ = project
    original = interruption("cancel firmware now")

    def interrupt(values, index):
        raise original

    def fail_receipt(store, record):
        raise ProductError("persistence_error", "receipt transaction failed")

    monkeypatch.setattr(RunStore, "record_attempt", fail_receipt)
    executor = SyntheticExecutor(interrupt)
    root = tmp_path / "run"
    with pytest.raises(interruption) as caught:
        services.run_project(config, root, _executor_factory=factory(executor))
    assert caught.value is original
    inspection = services.inspect_run(root)
    assert inspection["state"] == "cancelled"
    assert inspection["attempts_recorded"] == 0
    assert inspection["accounting_verification"]["missing_receipts"] == 1
    assert inspection["accounting_verification"]["execution_verification"] == "failed"
    assert inspection["result"]["accounting"]["attempted_executions"] == 1
    assert inspection["result"]["accounting"]["infrastructure_failures"] == 1
    assert executor.calls == [(0, 0)]
    before = archive_bytes(root)
    recovered = services.recover_run(root)
    assert recovered["state"] == "cancelled"
    assert recovered["accounting_verification"]["status"] == "incomplete_receipts"
    assert archive_bytes(root) == before
    calls = []

    def authorize_fresh_restart(*args, **kwargs):
        calls.append((args, kwargs))
        return {"authorized": True}

    monkeypatch.setattr(services, "_execute_project", authorize_fresh_restart)
    assert services.restart_run(root, tmp_path / "fresh") == {"authorized": True}
    assert calls[0][1]["parent"]["operation"] == "restart"
    assert "abandoned work may be repeated" in calls[0][1]["parent"]["warning"]


def test_completed_result_cannot_silently_lose_all_execution_receipts(project, tmp_path):
    config, _ = project
    root = tmp_path / "run"
    services.run_project(config, root, _executor_factory=factory(SyntheticExecutor()))
    db = sqlite3.connect(root / "run.sqlite3")
    db.execute("DELETE FROM attempts")
    db.commit()
    db.close()
    with pytest.raises(ProductError, match="missing execution receipts"):
        services.inspect_run(root)


def test_reproduction_pins_original_tools_after_active_runtime_changes(project, tmp_path, monkeypatch):
    config, original = project
    parent = tmp_path / 'original'
    services.run_project(config, parent, _executor_factory=factory(SyntheticExecutor()))
    saved = services.load_config(parent / 'project.json')
    assert saved.qemu == original.qemu and saved.gdb == original.gdb
    seen = []
    def require_saved(configuration, **kwargs):
        seen.append((configuration.qemu, configuration.gdb))
        assert configuration.qemu == original.qemu
        assert configuration.gdb == original.gdb
        return original
    monkeypatch.setattr(services, 'discover', require_saved)
    result = services.reproduce_run(parent, tmp_path / 'replayed', 3,
                                   _executor_factory=factory(SyntheticExecutor()))
    assert result['reproduction']['matching_observations'] == 3
    assert len(seen) >= 2
