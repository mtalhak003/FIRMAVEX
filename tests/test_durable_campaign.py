"""Small fake-executor campaigns through the unchanged experiment runner."""

import json
import hashlib
from asyncio import CancelledError
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.protocols.durable import DurableCampaignRunner
from src.firmavex.protocols.journal import JournalStore, fingerprint, validate_journal
from src.firmavex.protocols.provenance import TOOLS
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.runner import CampaignRunner
from src.firmavex.strategies.api import TerminationReason


ID = "b-" + "a" * 32
SPACE = InputSpace(1, 0, 2)


class Registry:
    def __init__(self, executor=None, *, partition="development", space=SPACE):
        self.input_space = space
        self.partition = partition
        self.executor = executor if executor is not None else Mock(return_value=Observation(True))
        self.owners = []
        self.opened = []

    def select(self, partition):
        return (SimpleNamespace(benchmark_id=ID, split=self.partition),) if partition == self.partition else ()

    def open_session(self, identifier, budget, strategy, *, random_seed=None):
        self.opened.append((identifier, budget, strategy, random_seed))
        owner = EvaluationSession(identifier, self.input_space, budget, strategy, self.executor, random_seed=random_seed)
        self.owners.append(owner)
        return owner


def protocol(**updates):
    return EvaluationProtocol(**({
        "benchmark_ids": (ID,), "execution_budget": 1, "partition": "development",
        "random_seeds": (0, 1),
    } | updates))


@pytest.fixture
def setup(tmp_path):
    # Complete immutable evidence fixture; executions remain explicitly fake.
    declaration = protocol()
    empty = hashlib.sha256(b"").hexdigest()
    context = {
        "schema_version": 1,
        "kind": "firmavex_recovery_context", "plan_sha256": fingerprint(declaration.plan_to_dict()),
        "consistency": {"status": "stable_observed", "atomic": False},
        "preset": {"name": "synthetic_fixture", "verification": "administrator_declared_not_verified"},
        "environment": {
            "repository": str(tmp_path / "repository"),
            "git": {"revision": "1" * 40, "dirty": False, "status_short": "",
                    "tracked_diff_sha256": empty, "index_diff_sha256": empty, "untracked_files": []},
            "tools": {name: {"status": "unavailable", "executable": None, "version": None,
                              "error": "synthetic unit test"} for name in TOOLS},
            "python": {"version": "test", "implementation": "CPython", "executable": "/synthetic/python"},
            "host": {"system": "test", "release": "test", "platform": "test", "os_release": None,
                     "version": "test", "machine": "test", "processor": "", "cpu_count": 1, "cpu_affinity": [0]},
        },
        "benchmarks": [{
            "benchmark_id": ID,
            "firmware_image": {"path": "/synthetic/image.elf", "requested_path": "/synthetic/image.elf",
                               "size_bytes": 1, "sha256": "1" * 64},
            "source_inputs": [{"path": "/synthetic/source.c", "requested_path": "/synthetic/source.c",
                               "size_bytes": 1, "sha256": "2" * 64}],
            "build": {"verification": "administrator_supplied_not_verified", "metadata": {"test_only": True}},
        }],
    }
    (tmp_path / "repository").mkdir()
    provider = Mock(side_effect=lambda current: deepcopy(context))
    path = tmp_path / "campaign.json"
    return declaration, context, provider, path


def test_incremental_checkpoints_precede_every_later_dispatch(setup, monkeypatch):
    declared, context, provider, path = setup
    registry = Registry()
    runner = DurableCampaignRunner(registry, path, provider)
    snapshots = []
    original_write = runner._store.write

    def write(payload, **kwargs):
        original_write(payload, **kwargs)
        snapshots.append(deepcopy(payload))

    monkeypatch.setattr(runner._store, "write", write)
    original_open = registry.open_session

    def open_session(*args, **kwargs):
        snapshot = JournalStore(path).read()
        assert len(snapshot["completed"]) == len(registry.owners)
        assert snapshot["attempts"][-1]["status"] == "running"
        return original_open(*args, **kwargs)

    monkeypatch.setattr(registry, "open_session", open_session)
    result = runner.run(declared)
    assert snapshots[0]["campaign_state"] == "planned"
    assert [len(entry["completed"]) for entry in snapshots] == [0, 0, 1, 1, 2, 2, 3, 3]
    assert snapshots[-1]["campaign_state"] == "completed"
    assert len(result.records) == len(registry.owners) == 3
    assert registry.opened == [(ID, 1, spec.strategy.name, spec.strategy.seed) for spec in declared.expand()]
    assert tuple(validate_journal(snapshots[-1], declared, context, SPACE)) == result.records
    provider.assert_called_once_with(declared)


def test_official_serialization_matches_existing_nondurable_runner(setup):
    declared, _, provider, path = setup
    expected = CampaignRunner(Registry()).run(declared)
    actual = DurableCampaignRunner(Registry(), path, provider).run(declared)
    assert actual.to_dict() == expected.to_dict()
    assert actual.to_json() == expected.to_json()
    assert "attempt_id" not in actual.to_json()
    assert "context" not in actual.to_json()


def test_completed_recovery_dispatches_nothing_and_captures_fresh_context(setup):
    declared, _, provider, path = setup
    first = DurableCampaignRunner(Registry(), path, provider).run(declared)
    registry = Registry()
    recovered = DurableCampaignRunner(registry, path, provider).run(declared, resume=True)
    assert recovered.to_json() == first.to_json()
    assert registry.owners == []
    assert registry.executor.call_count == 0
    assert provider.call_count == 2


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, CancelledError])
def test_interrupted_execution_preserves_charged_partial_ledger_and_original(setup, exception_type):
    declared, _, provider, path = setup
    error = exception_type("private interruption diagnostics")
    registry = Registry(Mock(side_effect=[Observation(True), error]))
    runner = DurableCampaignRunner(registry, path, provider)
    with pytest.raises(exception_type) as caught:
        runner.run(declared)
    assert caught.value is error
    payload = JournalStore(path).read()
    assert payload["campaign_state"] == "interrupted"
    assert len(payload["completed"]) == 1
    attempt = payload["attempts"][-1]
    assert attempt["position"] == 1 and attempt["status"] == "interrupted"
    partial = attempt["partial_evaluation"]
    assert partial["attempted_executions"] == partial["infrastructure_failures"] == 1
    assert partial["successful_executions"] == 0 and partial["aborted"]
    assert partial == runner.experiment_runner.last_session.result().__dict__
    assert "private interruption diagnostics" in attempt["diagnostics"][0]["stderr"]
    assert payload["last_error"]["attempt_id"] == attempt["attempt_id"]
    assert registry.executor.call_count == 2
    recovered = Registry()
    with pytest.raises(ValueError, match="explicit restart"):
        DurableCampaignRunner(recovered, path, provider).run(declared, resume=True)
    assert recovered.owners == []


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_explicit_restart_uses_new_attempt_and_keeps_old_accounting_separate(setup, exception_type):
    declared, _, provider, path = setup
    registry = Registry(Mock(side_effect=[Observation(True), exception_type("stop")]))
    with pytest.raises(exception_type):
        DurableCampaignRunner(registry, path, provider).run(declared)
    old = JournalStore(path).read()["attempts"][-1]
    resumed_registry = Registry()
    result = DurableCampaignRunner(resumed_registry, path, provider).run(declared, resume=True, restart_interrupted=True)
    payload = JournalStore(path).read()
    earlier, restarted = payload["attempts"][1:3]
    assert earlier == old
    assert restarted["number"] == 2 and restarted["restart_of"] == old["attempt_id"]
    assert restarted["attempt_id"] != old["attempt_id"]
    assert earlier["partial_evaluation"]["attempted_executions"] == 1
    assert result.records[1].run.evaluation.attempted_executions == 1
    assert result.records[1].run.evaluation.infrastructure_failures == 0
    assert len(resumed_registry.owners) == 2
    assert payload["campaign_state"] == "completed"


@pytest.mark.parametrize("after_replacement", [False, True])
def test_completion_checkpoint_interruption_preserves_actual_durable_prefix(setup, monkeypatch, after_replacement):
    declared, _, provider, path = setup
    registry = Registry()
    runner = DurableCampaignRunner(registry, path, provider)
    original = runner._store.write
    interruption = KeyboardInterrupt("checkpoint interruption")
    injected = False

    def write(payload, **kwargs):
        nonlocal injected
        if not injected and len(payload["completed"]) == 1:
            injected = True
            if after_replacement:
                original(payload, **kwargs)
            raise interruption
        return original(payload, **kwargs)

    monkeypatch.setattr(runner._store, "write", write)
    with pytest.raises(KeyboardInterrupt) as caught:
        runner.run(declared)
    assert caught.value is interruption
    snapshot = JournalStore(path).read()
    assert len(snapshot["completed"]) == int(after_replacement)
    assert snapshot["attempts"][0]["status"] == ("completed" if after_replacement else "interrupted")
    if after_replacement:
        assert snapshot["last_error"]["attempt_id"] is None
    else:
        assert snapshot["attempts"][0]["partial_evaluation"]["successful_executions"] == 1
    recovered_registry = Registry()
    DurableCampaignRunner(recovered_registry, path, provider).run(
        declared, resume=True, restart_interrupted=not after_replacement,
    )
    assert len(recovered_registry.owners) == 3 - int(after_replacement)


def test_ordinary_infrastructure_abort_is_durable_completed_outcome_and_continues(setup):
    declared, _, provider, path = setup
    registry = Registry(Mock(side_effect=[Observation(False, stderr="private failure"), Observation(True), Observation(True)]))
    result = DurableCampaignRunner(registry, path, provider).run(declared)
    assert result.infrastructure_aborted_run_count == 1
    assert result.records[0].run.termination is TerminationReason.SESSION_ABORTED
    snapshot = JournalStore(path).read()
    assert len(snapshot["completed"]) == 3
    assert all(attempt["status"] == "completed" for attempt in snapshot["attempts"])
    assert snapshot["completed"][0]["record"] == result.records[0].to_dict()


def test_lost_running_attempt_requires_explicit_restart_without_invented_counts(setup):
    declared, _, provider, path = setup
    interruption = KeyboardInterrupt("before dispatch")
    runner = DurableCampaignRunner(Registry(), path, provider)
    original = runner._store.write

    def write(payload, **kwargs):
        original(payload, **kwargs)
        if payload["attempts"] and payload["attempts"][-1]["status"] == "running":
            raise interruption

    runner._store.write = write
    with pytest.raises(KeyboardInterrupt):
        runner.run(declared)
    payload = JournalStore(path).read()
    current = payload["attempts"][-1]
    current.update(status="running", partial_evaluation=None, diagnostics=[], error=None, capture_error=None)
    payload.update(campaign_state="running", last_error=None)
    JournalStore(path).write(payload)
    registry = Registry()
    with pytest.raises(ValueError, match="explicit restart"):
        DurableCampaignRunner(registry, path, provider).run(declared, resume=True)
    assert registry.owners == []
    DurableCampaignRunner(registry, path, provider).run(declared, resume=True, restart_interrupted=True)
    old, new = JournalStore(path).read()["attempts"][:2]
    assert old["status"] == "interrupted" and old["error"]["type"] == "LostAttempt"
    assert old["partial_evaluation"] is None
    assert new["number"] == 2 and new["restart_of"] == old["attempt_id"]


@pytest.mark.parametrize("failure", [KeyboardInterrupt("original"), SystemExit("original")])
def test_secondary_checkpoint_and_capture_failures_preserve_original(setup, monkeypatch, failure):
    declared, _, provider, path = setup
    runner = DurableCampaignRunner(Registry(Mock(side_effect=failure)), path, provider)
    original_write = runner._store.write

    def write(payload, **kwargs):
        if payload["campaign_state"] == "interrupted":
            raise SystemExit("secondary storage failure")
        return original_write(payload, **kwargs)

    monkeypatch.setattr(runner._store, "write", write)
    with pytest.raises(type(failure)) as caught:
        runner.run(declared)
    assert caught.value is failure
    assert any("secondary storage failure" in note for note in failure.__notes__)
    assert JournalStore(path).read()["attempts"][-1]["status"] == "running"


@pytest.mark.parametrize("change", ["plan", "context", "input_space"])
def test_recovery_mismatch_stops_before_any_dispatch(setup, change):
    declared, context, provider, path = setup
    DurableCampaignRunner(Registry(), path, provider).run(declared)
    registry = Registry(space=InputSpace(1, 0, 1) if change == "input_space" else SPACE)
    requested = replace(declared, execution_budget=2) if change == "plan" else declared
    if change == "context":
        context["environment"]["repository"] += "-different"
    with pytest.raises(ValueError):
        DurableCampaignRunner(registry, path, provider).run(requested, resume=True)
    assert registry.owners == []


def test_corrupt_journal_stops_before_dispatch(setup):
    declared, _, provider, path = setup
    DurableCampaignRunner(Registry(), path, provider).run(declared)
    path.write_text("{broken journal")
    registry = Registry()
    with pytest.raises(ValueError):
        DurableCampaignRunner(registry, path, provider).run(declared, resume=True)
    assert registry.owners == []


def test_invalid_returned_classification_is_not_persisted_as_completion(setup, monkeypatch):
    declared, _, provider, path = setup
    registry = Registry()
    original = ExperimentRunner.run

    def invalid(instance, spec):
        record = original(instance, spec)
        return replace(record, run=replace(record.run, termination=TerminationReason.FAILURE_DISCOVERED))

    monkeypatch.setattr(ExperimentRunner, "run", invalid)
    with pytest.raises(ValueError, match="termination contradicts"):
        DurableCampaignRunner(registry, path, provider).run(declared)
    snapshot = JournalStore(path).read()
    assert snapshot["completed"] == []
    assert snapshot["attempts"][-1]["status"] == "interrupted"
    assert snapshot["attempts"][-1]["partial_evaluation"]["successful_executions"] == 1
    assert len(registry.owners) == 1


@pytest.mark.parametrize("options", [
    {"restart_interrupted": True}, {"resume": 1}, {"restart_interrupted": 0},
])
def test_invalid_recovery_options_dispatch_nothing(setup, options):
    declared, _, provider, path = setup
    registry = Registry()
    with pytest.raises(ValueError):
        DurableCampaignRunner(registry, path, provider).run(declared, **options)
    assert registry.owners == []
    assert not path.exists()


def test_existing_journal_requires_explicit_resume_and_is_not_replaced(setup):
    declared, _, provider, path = setup
    DurableCampaignRunner(Registry(), path, provider).run(declared)
    previous = path.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        DurableCampaignRunner(Registry(), path, provider).run(declared)
    assert path.read_bytes() == previous


def test_journal_inside_repository_is_rejected(setup):
    declared, context, provider, _ = setup
    path = Path(context["environment"]["repository"]) / "new-dir" / "campaign.json"
    registry = Registry()
    with pytest.raises(ValueError, match="outside the repository"):
        DurableCampaignRunner(registry, path, provider).run(declared)
    assert not path.exists() and registry.owners == []
    assert not path.parent.exists()


@pytest.mark.parametrize("checkpoint", ["initial", "final"])
def test_interruption_after_boundary_replacement_retains_records_and_needs_no_restart(setup, monkeypatch, checkpoint):
    declared, _, provider, path = setup
    registry = Registry()
    runner = DurableCampaignRunner(registry, path, provider)
    original = runner._store.write
    error = KeyboardInterrupt(checkpoint + " boundary")
    fired = False

    def write(payload, **kwargs):
        nonlocal fired
        original(payload, **kwargs)
        target = "planned" if checkpoint == "initial" else "completed"
        if not fired and payload["campaign_state"] == target:
            fired = True
            raise error

    monkeypatch.setattr(runner._store, "write", write)
    with pytest.raises(KeyboardInterrupt) as caught:
        runner.run(declared)
    assert caught.value is error
    saved = JournalStore(path).read()
    expected = 0 if checkpoint == "initial" else 3
    assert saved["campaign_state"] == "interrupted"
    assert len(saved["completed"]) == len(registry.owners) == expected
    assert saved["last_error"]["position"] == expected
    assert saved["last_error"]["attempt_id"] is None
    assert all(attempt["status"] == "completed" for attempt in saved["attempts"])
    recovered_registry = Registry()
    result = DurableCampaignRunner(recovered_registry, path, provider).run(declared, resume=True)
    assert len(result.records) == 3 and len(recovered_registry.owners) == 3 - expected
    assert JournalStore(path).read()["last_error"] == saved["last_error"]


def test_initial_checkpoint_failure_dispatches_no_experiment(setup, monkeypatch):
    declared, _, provider, path = setup
    registry = Registry()
    runner = DurableCampaignRunner(registry, path, provider)
    error = OSError("initial write failed")
    monkeypatch.setattr(runner._store, "write", Mock(side_effect=error))
    with pytest.raises(OSError) as caught:
        runner.run(declared)
    assert caught.value is error
    assert registry.owners == [] and not path.exists()


@pytest.mark.parametrize("capture", ["result", "diagnostics"])
def test_partial_capture_error_is_retained_without_replacing_interruption(setup, monkeypatch, capture):
    declared, _, provider, path = setup
    registry = Registry(Mock(side_effect=KeyboardInterrupt("original cancellation")))
    original_open = registry.open_session

    def open_session(*args, **kwargs):
        owner = original_open(*args, **kwargs)
        if capture == "result":
            original_result = owner.result
            calls = 0

            def result():
                nonlocal calls
                calls += 1
                if owner._aborted:
                    raise SystemExit("partial result unavailable")
                return original_result()

            monkeypatch.setattr(owner, "result", result)
        else:
            monkeypatch.setattr(owner, "diagnostics", Mock(side_effect=SystemExit("diagnostics unavailable")))
        return owner

    monkeypatch.setattr(registry, "open_session", open_session)
    with pytest.raises(KeyboardInterrupt, match="original cancellation"):
        DurableCampaignRunner(registry, path, provider).run(declared)
    attempt = JournalStore(path).read()["attempts"][-1]
    assert attempt["status"] == "interrupted"
    assert "unavailable" in attempt["capture_error"]
    if capture == "result":
        assert attempt["partial_evaluation"] is None
        assert attempt["diagnostics"][0]["execution_index"] == 1
    else:
        assert attempt["partial_evaluation"]["attempted_executions"] == 1
        assert attempt["diagnostics"] == []


def test_unrecorded_strategy_error_preserves_no_invented_accounting(setup, monkeypatch):
    declared, _, provider, path = setup
    error = RuntimeError("strategy construction error")
    monkeypatch.setattr("src.firmavex.experiments.runner.create_strategy", Mock(side_effect=error))
    registry = Registry()
    with pytest.raises(RuntimeError) as caught:
        DurableCampaignRunner(registry, path, provider).run(declared)
    assert caught.value is error
    attempt = JournalStore(path).read()["attempts"][-1]
    assert attempt["status"] == "interrupted" and attempt["partial_evaluation"] is None
    assert attempt["diagnostics"] == [] and registry.owners == []


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, CancelledError])
def test_same_runner_restart_before_new_owner_does_not_copy_old_ledger(setup, monkeypatch, exception_type):
    declared, _, provider, path = setup
    first = exception_type("first admitted execution")
    registry = Registry(Mock(side_effect=first))
    runner = DurableCampaignRunner(registry, path, provider)
    with pytest.raises(exception_type) as caught:
        runner.run(declared)
    assert caught.value is first
    earlier = JournalStore(path).read()["attempts"][0]
    assert earlier["partial_evaluation"]["attempted_executions"] == 1
    assert earlier["diagnostics"]

    dispatch = runner.experiment_runner.run
    interruption = exception_type("restart before evaluator creation")
    monkeypatch.setattr(runner.experiment_runner, "run", Mock(side_effect=interruption))
    with pytest.raises(exception_type) as caught:
        runner.run(declared, resume=True, restart_interrupted=True)
    assert caught.value is interruption
    first_attempt, second_attempt = JournalStore(path).read()["attempts"]
    assert first_attempt == earlier
    assert second_attempt["number"] == 2
    assert second_attempt["restart_of"] == earlier["attempt_id"]
    assert second_attempt["attempt_id"] != earlier["attempt_id"]
    assert second_attempt["partial_evaluation"] is None
    assert second_attempt["diagnostics"] == []
    assert second_attempt["capture_error"] is None
    assert registry.executor.call_count == len(registry.owners) == 1

    monkeypatch.setattr(runner.experiment_runner, "run", dispatch)
    registry.executor.side_effect = None
    registry.executor.return_value = Observation(True)
    result = runner.run(declared, resume=True, restart_interrupted=True)
    assert len(result.records) == 3
    assert registry.executor.call_count == 4
    assert JournalStore(path).read()["attempts"][1] == second_attempt


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, CancelledError])
def test_next_experiment_before_new_owner_does_not_inherit_completed_diagnostics(setup, monkeypatch, exception_type):
    declared, _, provider, path = setup
    registry = Registry(Mock(return_value=Observation(False, stderr="previous experiment diagnostics")))
    runner = DurableCampaignRunner(registry, path, provider)
    dispatch = runner.experiment_runner.run
    interruption = exception_type("next experiment before evaluator creation")

    def interrupt_second(spec):
        if spec == declared.expand()[1]:
            raise interruption
        return dispatch(spec)

    monkeypatch.setattr(runner.experiment_runner, "run", interrupt_second)
    with pytest.raises(exception_type) as caught:
        runner.run(declared)
    assert caught.value is interruption
    snapshot = JournalStore(path).read()
    saved = snapshot["completed"][0]
    pending = snapshot["attempts"][-1]
    assert saved["record"]["run"]["evaluation"]["infrastructure_failures"] == 1
    assert pending["position"] == 1 and pending["partial_evaluation"] is None
    assert pending["diagnostics"] == [] and pending["capture_error"] is None
    assert registry.executor.call_count == len(registry.owners) == 1

    monkeypatch.setattr(runner.experiment_runner, "run", dispatch)
    registry.executor.return_value = Observation(True)
    result = runner.run(declared, resume=True, restart_interrupted=True)
    assert result.infrastructure_aborted_run_count == 1
    assert registry.executor.call_count == len(registry.owners) == 3
    assert JournalStore(path).read()["completed"][0] == saved


def test_multiple_same_runner_restarts_keep_unknown_and_fresh_accounting_separate(setup, monkeypatch):
    declared, _, provider, path = setup
    first = KeyboardInterrupt("first interrupted evaluator")
    registry = Registry(Mock(side_effect=[Observation(True), first]))
    runner = DurableCampaignRunner(registry, path, provider)
    with pytest.raises(KeyboardInterrupt) as caught:
        runner.run(declared)
    assert caught.value is first
    completed = JournalStore(path).read()["completed"][0]
    dispatch = runner.experiment_runner.run

    for interruption in (SystemExit("before second owner"), CancelledError("before third owner")):
        monkeypatch.setattr(runner.experiment_runner, "run", Mock(side_effect=interruption))
        with pytest.raises(type(interruption)) as caught:
            runner.run(declared, resume=True, restart_interrupted=True)
        assert caught.value is interruption
        latest = JournalStore(path).read()["attempts"][-1]
        assert latest["partial_evaluation"] is None and latest["diagnostics"] == []
    assert registry.executor.call_count == 2

    monkeypatch.setattr(runner.experiment_runner, "run", dispatch)
    fresh_interruption = KeyboardInterrupt("fresh fourth evaluator")
    registry.executor.side_effect = fresh_interruption
    with pytest.raises(KeyboardInterrupt) as caught:
        runner.run(declared, resume=True, restart_interrupted=True)
    assert caught.value is fresh_interruption
    fresh = JournalStore(path).read()["attempts"][-1]
    assert fresh["partial_evaluation"]["attempted_executions"] == 1
    assert fresh["partial_evaluation"]["infrastructure_failures"] == 1
    assert "fresh fourth evaluator" in fresh["diagnostics"][0]["stderr"]
    assert "first interrupted evaluator" not in fresh["diagnostics"][0]["stderr"]

    registry.executor.side_effect = None
    registry.executor.return_value = Observation(True)
    result = runner.run(declared, resume=True, restart_interrupted=True)
    snapshot = JournalStore(path).read()
    attempts = [entry for entry in snapshot["attempts"] if entry["position"] == 1]
    assert [entry["number"] for entry in attempts] == [1, 2, 3, 4, 5]
    assert len({entry["attempt_id"] for entry in attempts}) == 5
    assert [entry["restart_of"] for entry in attempts] == [None, *[entry["attempt_id"] for entry in attempts[:-1]]]
    assert [entry["partial_evaluation"] is None for entry in attempts] == [False, True, True, False, True]
    assert snapshot["completed"][0] == completed
    assert snapshot["campaign_state"] == "completed"
    assert registry.executor.call_count == len(registry.owners) == 5
    assert result.records[1].run.evaluation.attempted_executions == 1


def test_durability_metadata_storage_failure_stops_before_dispatch(setup, monkeypatch):
    import errno
    import os
    import stat
    from src.firmavex.protocols import journal

    declared, context, provider, path = setup
    registry = Registry()
    runner = DurableCampaignRunner(registry, path, provider)
    original = OSError("cannot archive unsupported directory synchronization")
    write_once = runner._store._write_once
    fsync = journal.os.fsync

    def sync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.EINVAL, "directory synchronization unsupported")
        fsync(descriptor)

    def write(payload, **kwargs):
        if payload["durability"]["directory_sync_unsupported_observed"]:
            raise original
        return write_once(payload, **kwargs)

    monkeypatch.setattr(journal.os, "fsync", sync)
    monkeypatch.setattr(runner._store, "_write_once", write)
    with pytest.raises(OSError) as caught:
        runner.run(declared)
    assert caught.value is original
    assert registry.owners == [] and registry.executor.call_count == 0
    persisted = JournalStore(path).read()
    assert validate_journal(persisted, declared, context, SPACE) == ()
    assert persisted["campaign_state"] == "planned" and persisted["attempts"] == []
