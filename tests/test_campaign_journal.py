"""Snapshot mechanics and hostile recovery data, using synthetic unit records."""

from copy import deepcopy
from dataclasses import asdict
import errno
import hashlib
import json
from pathlib import Path
from asyncio import CancelledError
import stat
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.protocols import journal
from src.firmavex.protocols.journal import JournalError, JournalStore, attempt_id, canonical_json, experiment_id, export_recovery_history, new_journal, validate_journal
from src.firmavex.protocols.protocol import EvaluationProtocol


ID = "b-" + "1" * 32
SPACE = InputSpace(1, 0, 1)


@pytest.fixture
def inputs(tmp_path):
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(0,))
    empty = hashlib.sha256(b"").hexdigest()
    artifact = {"path": str(tmp_path / "unit-image"), "requested_path": str(tmp_path / "unit-image"), "size_bytes": 1, "sha256": "a" * 64}
    context = {
        "schema_version": 1, "kind": "firmavex_recovery_context",
        "plan_sha256": journal.fingerprint(protocol.plan_to_dict()),
        "consistency": {"status": "stable_observed", "atomic": False},
        "preset": {"name": "synthetic_unit_fixture", "verification": "administrator_declared_not_verified"},
        "environment": {
            "repository": str(tmp_path / "checkout"),
            "git": {"revision": "1" * 40, "dirty": False, "status_short": "", "tracked_diff_sha256": empty, "index_diff_sha256": empty, "untracked_files": []},
            "tools": {name: {"status": "unavailable", "executable": None, "version": None, "error": "synthetic unit fixture"} for name in ("arm-none-eabi-gcc", "qemu-system-arm", "arm-none-eabi-gdb")},
            "python": {"version": "unit", "implementation": "unit", "executable": "/unit/python"},
            "host": {"system": "unit", "release": "", "platform": "", "os_release": None, "version": "", "machine": "", "processor": "", "cpu_count": 1, "cpu_affinity": [0]},
        },
        "benchmarks": [{"benchmark_id": ID, "firmware_image": artifact, "source_inputs": [dict(artifact)], "build": {"verification": "administrator_supplied_not_verified", "metadata": {"purpose": "synthetic test"}}}],
    }
    return protocol, context


def complete_first(protocol, context):
    class Provider:
        def open_session(self, identifier, budget, strategy, *, random_seed=None):
            return EvaluationSession(identifier, SPACE, budget, strategy, lambda _: Observation(True), random_seed=random_seed)

    payload = new_journal(protocol, context, SPACE)
    spec = protocol.expand()[0]
    record = ExperimentRunner(Provider()).run(spec)
    identifier = experiment_id(payload["plan_sha256"], 0)
    attempt = {
        "position": 0, "experiment_id": identifier, "number": 1,
        "attempt_id": attempt_id(identifier, 1), "restart_of": None,
        "status": "completed", "partial_evaluation": None, "diagnostics": [], "error": None, "capture_error": None,
    }
    payload["attempts"].append(attempt)
    payload["completed"].append({"position": 0, "experiment_id": identifier, "attempt_id": attempt["attempt_id"], "record": record.to_dict()})
    payload["campaign_state"] = "running"
    return payload, record


def test_initial_journal_and_deterministic_serialization(inputs, tmp_path):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    assert validate_journal(payload, protocol, context, SPACE) == ()
    assert payload["campaign_state"] == "planned"
    assert payload["completed"] == payload["attempts"] == []
    assert canonical_json(payload) == canonical_json(deepcopy(payload))
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    store = JournalStore(tmp_path / "journal.json")
    with store.locked():
        store.write(payload, create=True)
        first = store.path.read_bytes()
        store.write(payload)
        assert store.path.read_bytes() == first
        assert store.read() == payload
        assert store.directory_sync_supported is True
        with pytest.raises(JournalError, match="already exists"):
            store.write(payload, create=True)


def test_stable_identity_uses_entire_plan_position_and_attempt(inputs):
    protocol, context = inputs
    digest = journal.fingerprint(protocol.plan_to_dict())
    first, second = [experiment_id(digest, position) for position in (0, 1)]
    assert first != second
    assert attempt_id(first, 1) != attempt_id(first, 2)
    changed = deepcopy(protocol.plan_to_dict())
    changed["experiments"][0]["execution_budget"] = 999
    assert experiment_id(journal.fingerprint(changed), 0) != first


def test_completed_record_roundtrip_is_unchanged(inputs):
    protocol, context = inputs
    payload, record = complete_first(protocol, context)
    decoded, = validate_journal(payload, protocol, context, SPACE)
    assert decoded.to_json() == record.to_json()
    assert decoded.run.evaluation == record.run.evaluation


@pytest.mark.parametrize("mutation", ["duplicate", "reorder", "missing", "extra", "identity", "classification", "partial", "completion", "version", "policy", "number", "restart", "plan", "context", "space", "scalar", "last_error"])
def test_corrupt_semantic_history_is_rejected_even_with_fresh_checksum(inputs, mutation):
    protocol, context = inputs
    payload, _ = complete_first(protocol, context)
    entry = payload["completed"][0]
    attempt = payload["attempts"][0]
    if mutation == "duplicate":
        payload["completed"].append(deepcopy(entry))
    elif mutation == "reorder":
        entry["position"] = 1
    elif mutation == "missing":
        payload["completed"] = []
    elif mutation == "extra":
        payload["extra"] = "not supported"
    elif mutation == "identity":
        entry["experiment_id"] = "e-" + "0" * 64
    elif mutation == "classification":
        entry["record"]["run"]["termination"] = "failure_discovered"
    elif mutation == "partial":
        attempt["partial_evaluation"] = entry["record"]["run"]["evaluation"]
    elif mutation == "completion":
        payload["campaign_state"] = "completed"
    elif mutation == "version":
        payload["schema_version"] = 2
    elif mutation == "policy":
        payload["recovery_policy"] = "silently_resume_guest"
    elif mutation == "number":
        attempt["number"] = 2
    elif mutation == "restart":
        attempt["restart_of"] = attempt["attempt_id"]
    elif mutation == "plan":
        payload["plan"]["experiments"].reverse()
    elif mutation == "context":
        payload["context"]["environment"]["git"]["revision"] = "2" * 40
    elif mutation == "space":
        payload["input_space"]["maximum"] = 999
    elif mutation == "scalar":
        entry["position"] = False
    else:
        payload["last_error"] = {"position": 0, "attempt_id": [], "type": "KeyboardInterrupt", "message": "test"}
    with pytest.raises(ValueError):
        validate_journal(payload, protocol, context, SPACE)


@pytest.mark.parametrize("content", ["{", '{"schema_version":1,"schema_version":1}', '{"x":NaN}', '{"x":Infinity}', '{"schema_version":2,"payload_sha256":"x","payload":{}}'])
def test_read_rejects_malformed_duplicate_nonfinite_and_version_data(tmp_path, content):
    store = JournalStore(tmp_path / "journal.json")
    store.path.write_text(content)
    with pytest.raises(ValueError):
        store.read()


def test_checksum_detects_accidental_corruption(tmp_path):
    store = JournalStore(tmp_path / "journal.json")
    with store.locked():
        store.write({"value": "original"})
        document = json.loads(store.path.read_text())
        document["payload"]["value"] = "changed"
        store.path.write_text(json.dumps(document))
        with pytest.raises(JournalError, match="checksum"):
            store.read()


@pytest.mark.parametrize("stage", ["serialize", "file_fsync", "replace"])
def test_pre_replacement_failure_preserves_previous_valid_snapshot(tmp_path, monkeypatch, stage):
    store = JournalStore(tmp_path / "journal.json")
    with store.locked():
        store.write({"value": "old"})
        before = store.path.read_bytes()
        failure = OSError("injected write failure")
        if stage == "file_fsync":
            monkeypatch.setattr(journal.os, "fsync", lambda _: (_ for _ in ()).throw(failure))
        elif stage == "replace":
            monkeypatch.setattr(journal.os, "replace", lambda *_: (_ for _ in ()).throw(failure))
        data = {"value": float("nan")} if stage == "serialize" else {"value": "new"}
        with pytest.raises((ValueError, OSError)):
            store.write(data)
        assert store.path.read_bytes() == before
        assert store.read() == {"value": "old"}
        assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("unsupported", [True, False])
def test_directory_fsync_unsupported_is_explicit_and_other_failure_propagates(tmp_path, monkeypatch, unsupported):
    store = JournalStore(tmp_path / "journal.json")
    actual = journal.os.fsync
    calls = 0

    def sync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EINVAL if unsupported else errno.EIO, "directory sync unavailable")
        actual(descriptor)

    with store.locked():
        monkeypatch.setattr(journal.os, "fsync", sync)
        if unsupported:
            store.write({"value": "new"})
            assert store.directory_sync_supported is False
        else:
            with pytest.raises(OSError):
                store.write({"value": "new"})
        assert store.read() == {"value": "new"}  # replacement happened; old state is not promised.


def test_single_writer_lock_refuses_a_second_owner(tmp_path):
    first, second = [JournalStore(tmp_path / "journal.json") for _ in range(2)]
    with first.locked():
        with pytest.raises(JournalError, match="already owned"):
            with second.locked():
                pytest.fail("Concurrent writer admitted.")
    with second.locked():
        pass


def test_cleanup_failure_does_not_replace_interruption(tmp_path, monkeypatch):
    store = JournalStore(tmp_path / "journal.json")
    original = KeyboardInterrupt("original cancellation")
    actual_close = journal.os.close

    def close(descriptor):
        actual_close(descriptor)
        raise OSError("secondary close failure")

    with pytest.raises(KeyboardInterrupt) as caught:
        with store.locked():
            monkeypatch.setattr(journal.os, "close", close)
            raise original
    assert caught.value is original
    assert "secondary close failure" in " ".join(original.__notes__)


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_temp_stream_close_failure_preserves_original_sync_interruption(tmp_path, monkeypatch, exception_type):
    store = JournalStore(tmp_path / "journal.json")
    original = exception_type("original file sync interruption")
    factory = journal.tempfile.NamedTemporaryFile

    def faulty_stream(**kwargs):
        stream = factory(**kwargs)
        close = stream.close

        def fail_close():
            close()
            raise OSError("secondary stream close failure")

        monkeypatch.setattr(stream, "close", fail_close)
        return stream

    with store.locked():
        store.write({"value": "old"})
        previous = store.path.read_bytes()
        monkeypatch.setattr(journal.tempfile, "NamedTemporaryFile", faulty_stream)
        monkeypatch.setattr(journal.os, "fsync", lambda _: (_ for _ in ()).throw(original))
        with pytest.raises(exception_type) as caught:
            store.write({"value": "new"})
        assert caught.value is original
        assert "secondary stream close failure" in " ".join(original.__notes__)
        assert store.path.read_bytes() == previous
        assert not list(tmp_path.glob("*.tmp"))


def append_attempt(payload, *, status="running", partial=None):
    position = len(payload["completed"])
    previous = payload["attempts"][-1] if payload["attempts"] else None
    number = previous["number"] + 1 if previous and previous["position"] == position else 1
    identifier = experiment_id(payload["plan_sha256"], position)
    attempt = {
        "position": position, "experiment_id": identifier, "number": number,
        "attempt_id": attempt_id(identifier, number),
        "restart_of": previous["attempt_id"] if number > 1 else None,
        "status": status, "partial_evaluation": partial, "diagnostics": [],
        "error": {"type": "KeyboardInterrupt", "message": f"interruption {number}"} if status == "interrupted" else None,
        "capture_error": None,
    }
    payload["attempts"].append(attempt)
    payload["campaign_state"] = "interrupted" if status == "interrupted" else "running"
    if status == "interrupted":
        payload["last_error"] = {"position": position, "attempt_id": attempt["attempt_id"], **attempt["error"]}
    return attempt


def complete_remaining(payload, protocol):
    class Provider:
        def open_session(self, identifier, budget, strategy, *, random_seed=None):
            return EvaluationSession(identifier, SPACE, budget, strategy, lambda _: Observation(True), random_seed=random_seed)

    for position in range(len(payload["completed"]), len(protocol.expand())):
        attempt = append_attempt(payload)
        record = ExperimentRunner(Provider()).run(protocol.expand()[position])
        attempt["status"] = "completed"
        payload["completed"].append({
            "position": position, "experiment_id": attempt["experiment_id"],
            "attempt_id": attempt["attempt_id"], "record": record.to_dict(),
        })
    payload["campaign_state"] = "completed"


def boundary_error(payload, *, position=None):
    payload["campaign_state"] = "interrupted"
    payload["last_error"] = {
        "position": len(payload["completed"]) if position is None else position,
        "attempt_id": None, "type": "KeyboardInterrupt", "message": "boundary cancellation",
    }


@pytest.mark.parametrize("state", [
    "planned", "initial_boundary", "active", "completed_boundary_running",
    "interrupted_active", "interrupted_completed_boundary", "pending_finalization",
    "restart_running", "restart_admission_boundary", "complete",
    "complete_with_restart", "complete_with_initial_boundary",
])
def test_legitimate_campaign_states_and_historical_errors_are_accepted(inputs, state):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    if state == "initial_boundary":
        boundary_error(payload)
    elif state == "active":
        append_attempt(payload)
    elif state == "completed_boundary_running":
        payload, _ = complete_first(protocol, context)
    elif state == "interrupted_active":
        append_attempt(payload, status="interrupted")
    elif state == "interrupted_completed_boundary":
        payload, _ = complete_first(protocol, context)
        boundary_error(payload)
    elif state == "pending_finalization":
        complete_remaining(payload, protocol)
        boundary_error(payload)
    elif state == "restart_running":
        append_attempt(payload, status="interrupted")
        append_attempt(payload)
    elif state == "restart_admission_boundary":
        append_attempt(payload, status="interrupted")
        boundary_error(payload)
    elif state == "complete":
        complete_remaining(payload, protocol)
    elif state == "complete_with_restart":
        append_attempt(payload, status="interrupted")
        append_attempt(payload, status="interrupted")
        complete_remaining(payload, protocol)
    elif state == "complete_with_initial_boundary":
        boundary_error(payload)
        complete_remaining(payload, protocol)
    assert len(validate_journal(payload, protocol, context, SPACE)) == len(payload["completed"])


@pytest.mark.parametrize("mutation", [
    "running_empty", "running_interrupted_without_error", "running_interrupted_with_error",
    "interrupted_boundary_wrong_position", "interrupted_missing_error", "interrupted_active_running",
    "interrupted_older_attempt_error", "error_type_mismatch", "error_message_mismatch",
    "completed_unresolved_attempt", "completed_missing_prefix", "planned_with_error",
    "future_error_position", "wrong_active_error_position",
])
def test_contradictory_campaign_state_and_error_location_are_rejected(inputs, mutation):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    if mutation == "running_empty":
        payload["campaign_state"] = "running"
    elif mutation.startswith("running_interrupted"):
        append_attempt(payload, status="interrupted")
        payload["campaign_state"] = "running"
        if mutation.endswith("without_error"):
            payload["last_error"] = None
    elif mutation == "interrupted_boundary_wrong_position":
        payload, _ = complete_first(protocol, context)
        boundary_error(payload, position=0)
    elif mutation == "interrupted_missing_error":
        append_attempt(payload, status="interrupted")
        payload["last_error"] = None
    elif mutation == "interrupted_active_running":
        append_attempt(payload)
        boundary_error(payload)
    elif mutation == "interrupted_older_attempt_error":
        append_attempt(payload, status="interrupted")
        previous_error = deepcopy(payload["last_error"])
        append_attempt(payload, status="interrupted")
        payload["last_error"] = previous_error
    elif mutation.startswith("error_"):
        append_attempt(payload, status="interrupted")
        payload["last_error"]["type" if mutation == "error_type_mismatch" else "message"] = "contradiction"
    elif mutation == "completed_unresolved_attempt":
        payload, _ = complete_first(protocol, context)
        append_attempt(payload)
        payload["campaign_state"] = "completed"
    elif mutation == "completed_missing_prefix":
        payload["campaign_state"] = "completed"
    elif mutation == "planned_with_error":
        boundary_error(payload)
        payload["campaign_state"] = "planned"
    elif mutation == "future_error_position":
        boundary_error(payload, position=1)
    elif mutation == "wrong_active_error_position":
        payload, _ = complete_first(protocol, context)
        append_attempt(payload, status="interrupted")
        payload["last_error"]["position"] = 0
    with pytest.raises(JournalError):
        validate_journal(payload, protocol, context, SPACE)


def test_recovery_export_uninterrupted_completion_is_deterministic_and_detached(inputs):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    complete_remaining(payload, protocol)
    official = deepcopy(payload["completed"])
    history = export_recovery_history(payload, protocol, context, SPACE)
    assert canonical_json(history) == canonical_json(export_recovery_history(deepcopy(payload), protocol, context, SPACE))
    summary = history["summary"]
    assert summary["final_campaign_completed"] is True
    assert summary["interruption_observed"] is False
    assert summary["restart_attempts"] == summary["interrupted_attempts"] == summary["unknown_accounting_attempts"] == 0
    assert summary["experiment_attempts_recorded"] == summary["completed_experiments"] == 2
    assert summary["physical_firmware_executions"] == summary["known_completed_firmware_executions"] == 4
    assert history["journal_sha256"] == journal.fingerprint(payload)
    assert history["completed_records_sha256"] == journal.fingerprint([entry["record"] for entry in official])
    assert history["plan_sha256"] == payload["plan_sha256"]
    assert all(attempt["accounting_status"] == "completed_authoritative" for attempt in history["attempts"])
    history["attempts"][0]["evaluation"]["attempted_executions"] = 999
    assert payload["completed"] == official


def test_recovery_export_preserves_repeated_restarts_unknown_and_known_abandoned_work(inputs):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    spec = protocol.expand()[0]
    owner = EvaluationSession(ID, SPACE, spec.execution_budget, spec.strategy.name, lambda _: Observation(True))
    from src.firmavex.evaluation.api import TrialInput
    owner.execute(TrialInput((0,)))
    first = append_attempt(payload, status="interrupted")
    second = append_attempt(payload, status="interrupted", partial=asdict(owner.result()))
    third = append_attempt(payload, status="interrupted")
    third["diagnostics"] = [{"stderr": "private administrator diagnostic"}]
    complete_remaining(payload, protocol)
    history = export_recovery_history(payload, protocol, context, SPACE)
    attempts = history["attempts"]
    assert [attempt["number"] for attempt in attempts] == [1, 2, 3, 4, 1]
    assert attempts[1]["restart_of"] == first["attempt_id"]
    assert attempts[2]["restart_of"] == second["attempt_id"]
    assert attempts[3]["restart_of"] == third["attempt_id"]
    assert len({attempt["attempt_id"] for attempt in attempts}) == 5
    assert [attempt["accounting_status"] for attempt in attempts] == ["unknown", "partial_authoritative", "unknown", "completed_authoritative", "completed_authoritative"]
    assert attempts[0]["evaluation"] is attempts[2]["evaluation"] is None
    assert attempts[1]["evaluation"]["attempted_executions"] == 1
    summary = history["summary"]
    assert summary["final_campaign_completed"] is True
    assert summary["interruption_observed"] is True
    assert summary["restart_attempts"] == summary["interrupted_attempts"] == 3
    assert summary["experiment_attempts_recorded"] == 5
    assert summary["known_completed_firmware_executions"] == 4
    assert summary["known_abandoned_firmware_executions"] == 1
    assert summary["known_physical_firmware_executions"] == 5
    assert summary["unknown_abandoned_attempts"] == summary["unknown_accounting_attempts"] == 2
    assert summary["physical_firmware_executions"] is None
    assert history["attempts"][2]["diagnostics"] == third["diagnostics"]
    assert len(payload["completed"]) == 2  # abandoned attempts never enter official results.


@pytest.mark.parametrize("charged_executions", [0, 1])
def test_recovery_export_known_partial_counts_distinguish_zero_from_unknown(inputs, charged_executions):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    spec = protocol.expand()[0]
    owner = EvaluationSession(ID, SPACE, spec.execution_budget, spec.strategy.name, lambda _: Observation(True))
    from src.firmavex.evaluation.api import TrialInput
    if charged_executions:
        owner.execute(TrialInput((0,)))
    append_attempt(payload, status="interrupted", partial=asdict(owner.result()))
    complete_remaining(payload, protocol)
    history = export_recovery_history(payload, protocol, context, SPACE)
    assert history["attempts"][0]["accounting_status"] == "partial_authoritative"
    assert history["attempts"][0]["evaluation"]["attempted_executions"] == charged_executions
    assert history["summary"]["unknown_accounting_attempts"] == 0
    assert history["summary"]["known_abandoned_firmware_executions"] == charged_executions
    assert history["summary"]["physical_firmware_executions"] == 4 + charged_executions


@pytest.mark.parametrize("state", ["running", "interrupted", "completed_boundary"])
def test_recovery_export_distinguishes_incomplete_campaigns_and_unknown_counts(inputs, state):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    if state == "completed_boundary":
        complete_remaining(payload, protocol)
        boundary_error(payload)
    else:
        append_attempt(payload, status=state)
    history = export_recovery_history(payload, protocol, context, SPACE)
    assert history["summary"]["final_campaign_completed"] is False
    if state != "completed_boundary":
        assert history["summary"]["physical_firmware_executions"] is None
        assert history["attempts"][0]["evaluation"] is None
    else:
        assert history["summary"]["completed_experiments"] == 2
        assert history["summary"]["physical_firmware_executions"] == 4


def test_recovery_export_rejects_invalid_history_before_publishing_counts(inputs):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    payload["campaign_state"] = "completed"
    with pytest.raises(JournalError):
        export_recovery_history(payload, protocol, context, SPACE)


@pytest.mark.parametrize("value", [None, 0, 1, "false", {}, {"directory_sync_unsupported_observed": True, "extra": True}])
def test_durability_metadata_has_exact_schema_and_boolean(inputs, value):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    payload["durability"] = value
    with pytest.raises(JournalError):
        validate_journal(payload, protocol, context, SPACE)


def test_unsupported_directory_sync_is_archived_once_and_retained_in_recovery(inputs, tmp_path, monkeypatch):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    store = JournalStore(tmp_path / "journal.json")
    actual = journal.os.fsync
    calls = []

    def sync(descriptor):
        calls.append(descriptor)
        if len(calls) % 2 == 0:
            raise OSError(errno.EINVAL, "directory synchronization unsupported")
        actual(descriptor)

    with store.locked():
        monkeypatch.setattr(journal.os, "fsync", sync)
        store.write(payload, create=True)
        assert len(calls) == 4  # two replacements, never an unbounded retry.
        assert payload["durability"]["directory_sync_unsupported_observed"] is True
        recovered_store = JournalStore(store.path)
        recovered = recovered_store.read()
        assert recovered_store.directory_sync_supported is False
        assert validate_journal(recovered, protocol, context, SPACE) == ()
        history = export_recovery_history(recovered, protocol, context, SPACE)
        assert history["durability"] == {"directory_sync_unsupported_observed": True}
        recovered_store.write(recovered)
        assert len(calls) == 6  # the retained flag needs no second metadata write.
        monkeypatch.setattr(journal.os, "fsync", actual)
        recovered_store.write(recovered)
        assert recovered_store.read()["durability"]["directory_sync_unsupported_observed"] is True


def test_failure_recording_unsupported_directory_sync_propagates_with_valid_prior_snapshot(inputs, tmp_path, monkeypatch):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    store = JournalStore(tmp_path / "journal.json")
    actual_sync = journal.os.fsync
    actual_replace = journal.os.replace
    sync_calls = replace_calls = 0

    def sync(descriptor):
        nonlocal sync_calls
        sync_calls += 1
        if sync_calls == 2:
            raise OSError(errno.EINVAL, "unsupported directory sync")
        actual_sync(descriptor)

    def replace(*args):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("failed to archive durability limitation")
        actual_replace(*args)

    with store.locked():
        monkeypatch.setattr(journal.os, "fsync", sync)
        monkeypatch.setattr(journal.os, "replace", replace)
        with pytest.raises(OSError, match="failed to archive"):
            store.write(payload, create=True)
        previous = store.read()
        assert previous["durability"]["directory_sync_unsupported_observed"] is False
        assert validate_journal(previous, protocol, context, SPACE) == ()
        assert not list(tmp_path.glob("*.tmp"))


def test_failed_durability_archive_is_retained_when_later_sync_succeeds(inputs, tmp_path, monkeypatch):
    protocol, context = inputs
    payload = new_journal(protocol, context, SPACE)
    store = JournalStore(tmp_path / "journal.json")
    actual_sync, actual_replace = journal.os.fsync, journal.os.replace
    sync_calls = replace_calls = 0

    def sync(descriptor):
        nonlocal sync_calls
        sync_calls += 1
        if sync_calls == 2:
            raise OSError(errno.EINVAL, "observed unsupported synchronization")
        actual_sync(descriptor)

    def replace(*args):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("metadata replacement failed")
        actual_replace(*args)

    with store.locked():
        monkeypatch.setattr(journal.os, "fsync", sync)
        monkeypatch.setattr(journal.os, "replace", replace)
        with pytest.raises(OSError, match="metadata replacement failed"):
            store.write(payload, create=True)
        persisted = store.read()
        assert persisted["durability"]["directory_sync_unsupported_observed"] is False
        monkeypatch.setattr(journal.os, "fsync", actual_sync)
        monkeypatch.setattr(journal.os, "replace", actual_replace)
        store.write(persisted)
        assert store.directory_sync_supported is True
        history = export_recovery_history(store.read(), protocol, context, SPACE)
        assert history["durability"]["directory_sync_unsupported_observed"] is True


@pytest.mark.parametrize("operation", ["write", "flush"])
def test_stream_failure_preserves_snapshot_and_removes_temporary_file(tmp_path, monkeypatch, operation):
    store = JournalStore(tmp_path / "journal.json")
    factory = journal.tempfile.NamedTemporaryFile
    original = OSError(f"temporary stream {operation} failed")

    def faulty_stream(**kwargs):
        stream = factory(**kwargs)

        def fail(*args):
            raise original

        monkeypatch.setattr(stream, operation, fail)
        return stream

    with store.locked():
        store.write({"value": "previous"})
        previous = store.path.read_bytes()
        monkeypatch.setattr(journal.tempfile, "NamedTemporaryFile", faulty_stream)
        with pytest.raises(OSError) as caught:
            store.write({"value": "new"})
        assert caught.value is original
        assert store.path.read_bytes() == previous
        assert store.read() == {"value": "previous"}
        assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("stage", ["lock", "stream", "directory"])
def test_handled_caller_interruption_does_not_own_journal_cleanup(tmp_path, monkeypatch, stage):
    store = JournalStore(tmp_path / "journal.json")
    earlier = KeyboardInterrupt("previously handled interruption")
    cleanup_error = OSError(f"{stage} cleanup failed")
    actual_close = journal.os.close
    factory = journal.tempfile.NamedTemporaryFile

    def close(descriptor):
        directory = stat.S_ISDIR(journal.os.fstat(descriptor).st_mode)
        actual_close(descriptor)
        if (stage == "directory" and directory) or (stage == "lock" and not directory):
            raise cleanup_error

    def stream_factory(**kwargs):
        stream = factory(**kwargs)
        close_stream = stream.close

        def fail_close():
            close_stream()
            raise cleanup_error

        monkeypatch.setattr(stream, "close", fail_close)
        return stream

    monkeypatch.setattr(journal.os, "close", close)
    if stage == "stream":
        monkeypatch.setattr(journal.tempfile, "NamedTemporaryFile", stream_factory)
    try:
        raise earlier
    except KeyboardInterrupt:
        with pytest.raises(OSError) as caught:
            with store.locked():
                if stage != "lock":
                    store.write({"value": "new"})
        assert caught.value is cleanup_error
    assert not hasattr(earlier, "__notes__")
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("target", ["descriptor", "stream"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit, CancelledError])
def test_journal_cleanup_cancellation_outranks_ordinary_primary(monkeypatch, target, exception_type):
    original = RuntimeError("ordinary persistence failure")
    interruption = exception_type("cleanup cancellation")
    with pytest.raises(exception_type) as caught:
        if target == "descriptor":
            monkeypatch.setattr(journal.os, "close", Mock(side_effect=interruption))
            journal._close(123, original)
        else:
            stream = Mock()
            stream.close.side_effect = interruption
            journal._close_stream(stream, original)
    assert caught.value is interruption
    assert interruption.__cause__ is original


def test_temporary_unlink_cancellation_outranks_ordinary_write_failure(tmp_path, monkeypatch):
    store = JournalStore(tmp_path / "journal.json")
    original = OSError("temporary write failed")
    interruption = KeyboardInterrupt("temporary cleanup cancelled")
    factory = journal.tempfile.NamedTemporaryFile
    unlink = Path.unlink

    def faulty_stream(**kwargs):
        stream = factory(**kwargs)
        monkeypatch.setattr(stream, "write", Mock(side_effect=original))
        return stream

    with store.locked():
        store.write({"value": "previous"})
        previous = store.path.read_bytes()
        monkeypatch.setattr(journal.tempfile, "NamedTemporaryFile", faulty_stream)
        monkeypatch.setattr(Path, "unlink", Mock(side_effect=interruption))
        with pytest.raises(KeyboardInterrupt) as caught:
            store.write({"value": "new"})
        assert caught.value is interruption
        assert interruption.__cause__ is original
        assert store.path.read_bytes() == previous
        # The interrupted removal itself failed; release only this test's temp.
        for temporary in tmp_path.glob("*.tmp"):
            unlink(temporary)
