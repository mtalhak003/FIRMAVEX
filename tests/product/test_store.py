"""Product archives retain observations without inventing evaluator counts."""

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from firmavex.product.errors import ProductError
from firmavex.product.store import RunStore


@pytest.fixture
def archive(tmp_path):
    with RunStore(tmp_path / "run", create=True) as store:
        store.initialize({"measurement_mode": "synthetic_test", "firmware_sha256": "a" * 64})
        yield store


def test_new_archive_initializes_once_and_preserves_exact_records(archive):
    vector = [0, 9, 15]
    metadata = archive.snapshot()["metadata"]
    assert archive.append_event("admitted", {"input": vector}) == 1
    assert archive.append_event("observed", {"completed": True}) == 2
    assert archive.record_attempt({"input": vector, "success": True, "triggered": True}) == 1
    vector[0] = 12
    result = {"state": "completed", "success": True, "triggering_input": [0, 9, 15],
              "attempted_executions": 1, "successful_executions": 1, "infrastructure_failures": 0}
    archive.finish(result)
    result["triggering_input"][0] = 13
    snapshot = archive.snapshot()
    assert snapshot["metadata"] == metadata
    assert snapshot["attempts"][0]["record"]["input"] == [0, 9, 15]
    assert snapshot["result"]["triggering_input"] == [0, 9, 15]
    assert snapshot["state"] == "completed"
    with pytest.raises(ProductError, match="initialized once"):
        archive.initialize({})


def test_archive_does_not_calculate_physical_execution_counts(archive):
    archive.record_attempt({"input": [7], "success": False})
    archive.finish({"state": "failed", "success": False, "attempted_executions": 3,
                    "successful_executions": 1, "infrastructure_failures": 1,
                    "accounting_status": "authoritative_evaluator"})
    snapshot = archive.snapshot()
    assert snapshot["result"]["attempted_executions"] == 3
    assert "physical_firmware_executions" not in json.dumps(snapshot)


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled", "interrupted"])
def test_all_terminal_states_preserved(archive, terminal):
    archive.finish({"state": terminal, "success": terminal == "completed"})
    assert archive.snapshot()["state"] == terminal
    with pytest.raises(ProductError, match="not active"):
        archive.record_attempt({"input": [1]})
    with pytest.raises(ProductError, match="not active"):
        archive.append_event("unexpected", {})
    with pytest.raises(ProductError, match="not active"):
        archive.finish({"state": terminal})


def test_create_never_overwrites_existing_directory_or_file(tmp_path):
    for target in (tmp_path / "directory", tmp_path / "file"):
        if target.name == "directory":
            target.mkdir()
        else:
            target.write_text("keep")
        with pytest.raises(ProductError):
            RunStore(target, create=True)
    assert (tmp_path / "file").read_text() == "keep"


def test_create_rejects_dangling_symlink(tmp_path):
    target = tmp_path / "link"
    target.symlink_to(tmp_path / "absent", target_is_directory=True)
    with pytest.raises(ProductError, match="symbolic"):
        RunStore(target, create=True)
    assert not (tmp_path / "absent").exists()


def test_inspection_is_readonly_and_preserves_running_state(archive):
    root = archive.root
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()}
    with RunStore(root) as reader:
        assert reader.snapshot()["state"] == "running"
        with pytest.raises(ProductError, match="read-only"):
            reader.append_event("bad", {})
        with pytest.raises(ProductError, match="read-only"):
            reader.write_json("new.json", {})
    after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir() if p.is_file()}
    assert after == before


def test_readonly_inspection_does_not_create_missing_root(tmp_path):
    with pytest.raises(ProductError):
        RunStore(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()


def test_live_writer_excludes_explicit_recovery(archive):
    with pytest.raises(ProductError, match="another writer"):
        RunStore.recover_interrupted(archive.root)
    assert archive.snapshot()["state"] == "running"


def test_another_process_writer_excludes_recovery_and_allows_inspection(tmp_path):
    root = tmp_path / "run"
    code = (
        "import sys; from pathlib import Path; from firmavex.product.store import RunStore; "
        "s=RunStore(Path(sys.argv[1]),create=True); s.initialize({}); "
        "print('owned', flush=True); sys.stdin.read(); s.close()"
    )
    process = subprocess.Popen([sys.executable, "-c", code, str(root)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "owned"
        with pytest.raises(ProductError, match="another writer"):
            RunStore.recover_interrupted(root)
        with RunStore(root) as reader:
            assert reader.snapshot()["state"] == "running"
    finally:
        process.communicate(input="release", timeout=5)
    assert process.returncode == 0
    assert RunStore.recover_interrupted(root)["state"] == "interrupted"


def test_brief_readonly_inspection_does_not_abort_writer_commit(archive):
    code = (
        "import sqlite3,sys; from pathlib import Path; "
        "db=sqlite3.connect(Path(sys.argv[1]).as_uri()+'?mode=ro', uri=True); "
        "db.execute('BEGIN'); db.execute('SELECT state FROM run').fetchone(); "
        "print('reading', flush=True); sys.stdin.readline(); db.rollback(); db.close()"
    )
    process = subprocess.Popen([sys.executable, "-c", code, str(archive.root / "run.sqlite3")],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    release = None
    try:
        assert process.stdout.readline().strip() == "reading"

        def end_inspection():
            process.stdin.write("release\n")
            process.stdin.flush()

        release = threading.Timer(0.1, end_inspection)
        release.start()
        assert archive.append_event("committed", {}) == 1
    finally:
        if release is not None:
            release.join(timeout=3)
        process.communicate(timeout=3)
    assert process.returncode == 0
    assert archive.snapshot()["events"][0]["kind"] == "committed"


def test_lock_release_and_recovery_keep_unknown_accounting(tmp_path):
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({"revision": "abc"})
        store.record_attempt({"input": [4], "triggered": False})
        store.append_event("admitted", {"input": [5]})
    with RunStore(root) as reader:
        assert reader.snapshot()["state"] == "running"
    result = RunStore.recover_interrupted(root)
    assert result["state"] == "interrupted"
    assert result["metadata"] == {"revision": "abc"}
    assert result["attempts"][0]["record"]["input"] == [4]
    assert result["result"]["accounting_status"] == "unknown"
    assert "attempted_executions" not in result["result"]
    assert result["events"][-1]["kind"] == "recovery"
    assert RunStore.recover_interrupted(root) == result


def test_recovery_preserves_completed_result_byte_for_byte(tmp_path):
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({"revision": "abc"})
        store.finish({"state": "completed", "success": True, "attempted_executions": 0})
    before = (root / "run.sqlite3").read_bytes()
    assert RunStore.recover_interrupted(root)["state"] == "completed"
    assert (root / "run.sqlite3").read_bytes() == before


def test_recovery_handles_loss_before_metadata_initialized(tmp_path):
    root = tmp_path / "run"
    RunStore(root, create=True).close()
    snapshot = RunStore.recover_interrupted(root)
    assert snapshot["state"] == "interrupted"
    assert snapshot["events"][0]["payload"]["previous_state"] == "created"
    assert snapshot["result"]["accounting_status"] == "unknown"


def test_process_exit_releases_writer_ownership(tmp_path):
    root = tmp_path / "run"
    code = (
        "import os,sys; from pathlib import Path; from firmavex.product.store import RunStore; "
        "s=RunStore(Path(sys.argv[1]),create=True); s.initialize({'measurement_mode':'synthetic_test'}); "
        "s.append_event('admitted', {'input':[8]}); os._exit(23)"
    )
    process = subprocess.run([sys.executable, "-c", code, str(root)], capture_output=True, text=True)
    assert process.returncode == 23, process.stderr
    assert RunStore.recover_interrupted(root)["state"] == "interrupted"


def test_context_manager_releases_lock_after_keyboard_interrupt(tmp_path):
    root = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        with RunStore(root, create=True) as store:
            store.initialize({})
            raise KeyboardInterrupt("cancel")
    assert RunStore.recover_interrupted(root)["state"] == "interrupted"


@pytest.mark.parametrize("record", [{}, {"input": []}, {"input": [True]}, {"input": [1.5]}, {"input": (1,)}])
def test_attempt_requires_exact_retained_vector(archive, record):
    with pytest.raises(ProductError):
        archive.record_attempt(record)
    assert archive.snapshot()["attempts"] == []


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), Path("x"), {"set"}, (1,), {1: "key"}])
def test_records_reject_noncanonical_json(archive, invalid):
    with pytest.raises(ProductError):
        archive.append_event("bad", {"value": invalid})
    assert archive.snapshot()["events"] == []


@pytest.mark.parametrize("result", [
    {"state": "running"},
    {"state": []},
    {"state": "completed", "success": False},
    {"state": "failed", "success": True},
    {"state": "completed", "success": 1},
    {"state": "completed", "aborted": True},
    {"state": "completed", "attempted_executions": True},
    {"state": "completed", "attempted_executions": -1},
    {"state": "completed", "attempted_executions": 1, "successful_executions": 2},
    {"state": "failed", "attempted_executions": 1, "successful_executions": 1, "infrastructure_failures": 1},
])
def test_contradictory_results_rejected(archive, result):
    with pytest.raises(ProductError):
        archive.finish(result)
    assert archive.snapshot()["state"] == "running"


def test_failed_transaction_rolls_back_without_losing_previous_events(archive):
    archive.append_event("before", {})
    archive._db().execute("CREATE TRIGGER reject_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'disk error'); END")
    with pytest.raises(ProductError, match="persist"):
        archive.append_event("lost", {})
    assert [e["kind"] for e in archive.snapshot()["events"]] == ["before"]
    assert not archive._db().in_transaction


@pytest.mark.parametrize("change", [
    "UPDATE run SET result='{}'",
    "UPDATE run SET state='unknown'",
    "UPDATE run SET metadata='{\"x\":NaN}'",
    "UPDATE run SET metadata='{\"x\":1,\"x\":2}'",
    "UPDATE events SET kind=''",
    "UPDATE events SET sequence=3",
    "UPDATE attempts SET record='{\"input\":[true]}'",
    "UPDATE attempts SET sequence=3",
])
def test_inspection_rejects_inconsistent_or_malformed_records(tmp_path, change):
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({})
        store.append_event("event", {})
        store.record_attempt({"input": [3]})
    db = sqlite3.connect(root / "run.sqlite3")
    db.execute(change)
    db.commit()
    db.close()
    with pytest.raises(ProductError):
        RunStore(root)


def test_truncated_database_rejected_without_rewriting(tmp_path):
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({})
    database = root / "run.sqlite3"
    database.write_bytes(database.read_bytes()[:80])
    before = database.read_bytes()
    with pytest.raises(ProductError):
        RunStore(root)
    assert database.read_bytes() == before


def test_artifacts_are_immutable_and_verified(archive, tmp_path):
    source = tmp_path / "firmware.elf"
    source.write_bytes(b"actual input bytes")
    image = archive.add_artifact("image/firmware.elf", source)
    config = archive.write_json("config.json", {"z": 2, "a": 1})
    assert image == {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "size_bytes": source.stat().st_size}
    assert (archive.root / "config.json").read_bytes() == b'{"a":1,"z":2}\n'
    with pytest.raises(ProductError):
        archive.write_json("config.json", {"overwritten": True})
    with RunStore(archive.root) as reader:
        assert reader.verify_artifacts() == {"config.json": config, "image/firmware.elf": image}
    (archive.root / "image/firmware.elf").write_bytes(b"changed")
    with pytest.raises(ProductError, match="identity mismatch"):
        archive.verify_artifacts()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "run.sqlite3", ".writer.lock",
                                 "run.sqlite3-journal", "x\\y", "C:relative", "./alias", "a//b"])
def test_artifacts_cannot_escape_or_replace_metadata(archive, name):
    with pytest.raises(ProductError):
        archive.write_json(name, {})


def test_artifact_parent_symlinks_rejected(archive, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (archive.root / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProductError, match="symbolic"):
        archive.write_json("alias/config.json", {})
    assert list(outside.iterdir()) == []


def test_terminal_archive_cannot_add_artifacts(archive):
    archive.finish({"state": "completed", "success": True})
    with pytest.raises(ProductError):
        archive.write_json("late.json", {})
    assert not (archive.root / "late.json").exists()


def test_text_artifact_is_utf8_and_exclusive(archive):
    text = "# Evidence\ntrigger input: [3, 5] — preliminary\n"
    identity = archive.write_text("report.md", text)
    assert (archive.root / "report.md").read_text() == text
    assert archive.verify_artifacts()["report.md"] == identity
    with pytest.raises(ProductError):
        archive.write_text("report.md", "overwrite")


@pytest.mark.parametrize("text", [b"bytes", 1, "\ud800"])
def test_invalid_text_artifacts_rejected(archive, text):
    with pytest.raises(ProductError):
        archive.write_text("bad.md", text)
    assert not (archive.root / "bad.md").exists()


def test_unregistered_artifact_from_interrupted_write_is_not_verified(archive):
    (archive.root / "unregistered.elf").write_bytes(b"incomplete copy")
    with pytest.raises(ProductError, match="Unregistered artifact"):
        archive.verify_artifacts()


def test_artifact_database_registration_failure_exposes_incomplete_inventory(archive):
    archive._db().execute("CREATE TRIGGER reject_artifact BEFORE INSERT ON artifacts BEGIN SELECT RAISE(ABORT, 'disk error'); END")
    with pytest.raises(ProductError):
        archive.write_json("orphan.json", {"input": [9]})
    with pytest.raises(ProductError, match="Unregistered artifact"):
        archive.verify_artifacts()


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interrupted_transaction_preserves_original_exception(archive, interruption):
    original = interruption("stop now")

    def action(db):
        db.execute("INSERT INTO events VALUES (1, 'partial', '{}')")
        raise original

    with pytest.raises(interruption) as error:
        archive._mutate(action)
    assert error.value is original
    assert archive.snapshot()["events"] == []
    assert not archive._db().in_transaction


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_failed_rollback_cannot_replace_control_flow_interruption(archive, interruption, monkeypatch):
    class FailedRollback:
        in_transaction = True

        def execute(self, command):
            if command == "ROLLBACK":
                raise sqlite3.OperationalError("rollback failed")

    monkeypatch.setattr(archive, "_db", lambda **kwargs: FailedRollback())
    original = interruption("cancel")

    def action(db):
        raise original

    with pytest.raises(interruption) as error:
        archive._mutate(action)
    assert error.value is original


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_cleanup_failure_cannot_replace_original_interruption(tmp_path, interruption):
    root = tmp_path / "run"
    store = RunStore(root, create=True)
    store.initialize({})
    connection = store._connection

    class FailedClose:
        def close(self):
            connection.close()
            raise sqlite3.OperationalError("close failed")

    store._connection = FailedClose()
    original = interruption("cancel")
    with pytest.raises(interruption) as error:
        with store:
            raise original
    assert error.value is original
    assert RunStore.recover_interrupted(root)["state"] == "interrupted"


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_constructor_cleanup_cannot_replace_original_interruption(tmp_path, interruption, monkeypatch):
    original = interruption("schema creation cancelled")
    real_close = RunStore.close

    def fail_schema(store):
        raise original

    def fail_close(store):
        real_close(store)
        raise sqlite3.OperationalError("constructor close failed")

    monkeypatch.setattr(RunStore, "_create_schema", fail_schema)
    monkeypatch.setattr(RunStore, "close", fail_close)
    with pytest.raises(interruption) as caught:
        RunStore(tmp_path / "run", create=True)
    assert caught.value is original


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_recovery_cleanup_cannot_replace_original_interruption(tmp_path, interruption, monkeypatch):
    root = tmp_path / "run"
    with RunStore(root, create=True) as store:
        store.initialize({})
    original = interruption("recovery inspection cancelled")
    real_snapshot, real_close = RunStore.snapshot, RunStore.close
    calls = 0
    interrupted = False

    def interrupted_snapshot(store):
        nonlocal calls, interrupted
        calls += 1
        if calls == 2:
            interrupted = True
            raise original
        return real_snapshot(store)

    def failed_cleanup(store):
        real_close(store)
        if interrupted:
            raise sqlite3.OperationalError("recovery close failed")

    monkeypatch.setattr(RunStore, "snapshot", interrupted_snapshot)
    monkeypatch.setattr(RunStore, "close", failed_cleanup)
    with pytest.raises(interruption) as caught:
        RunStore.recover_interrupted(root)
    assert caught.value is original


def test_source_change_during_read_rejected(archive, tmp_path, monkeypatch):
    source = tmp_path / "image.elf"
    source.write_bytes(b"old")
    real_open = Path.open

    class ChangingReader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self):
            value = self.handle.read()
            with real_open(source, "wb") as write:
                write.write(b"new contents")
            return value

    def changing_open(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        return ChangingReader(handle) if path == source and args == ("rb",) else handle

    monkeypatch.setattr(Path, "open", changing_open)
    with pytest.raises(ProductError, match="changed during"):
        archive.add_artifact("image.elf", source)
    assert not (archive.root / "image.elf").exists()


def test_closed_store_fails_clearly(archive):
    archive.close()
    with pytest.raises(ProductError, match="closed"):
        archive.snapshot()
