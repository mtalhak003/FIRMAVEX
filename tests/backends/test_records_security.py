"""Filesystem/trust/evidence regressions; synthetic tests are not qualification."""

from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import threading

import pytest
from firmavex.backends.api import Request, Result
from firmavex.backends import engine, report, security


def _hdl(tmp_path):
    source = tmp_path / "input.v"
    source.write_bytes(files("firmavex.backends").joinpath("examples/counter.v").read_bytes())
    return Request("verilog-icarus", source)


def _synthetic(monkeypatch, callback=None):
    from firmavex.backends.implementations import IcarusBackend
    def run(self, request, output, cancel):
        if callback:
            callback(request, output, cancel)
        return Result("passed", {"measurement_mode": "synthetic_test", "cleanup_verified": True})
    monkeypatch.setattr(IcarusBackend, "execute", run)


def _stored(tmp_path, artifacts=None):
    output = tmp_path / "run"
    output.mkdir()
    admission = {"attempt_id": "0" * 32, "profile": {"id": "verilog-icarus"}, "values": []}
    record = {"schema_version": 1, "status": "passed", "evidence": {
        "admission": admission, "measurement_mode": "synthetic_test", "cleanup_verified": True,
        "artifacts": artifacts or [], "stdout": "synthetic stdout\n", "stderr": "diagnostic\n",
        "process_logs": [{"pid": 1, "stdout": "child out\n", "stderr": "child error\n"}]}}
    engine._write(output / "admission.json", admission)
    engine._write(output / "result.json", record)
    return output, record


@pytest.mark.parametrize("trust", ["untrusted", "real_firmware", "", None, True, {}, []])
def test_untrusted_and_invalid_labels_reject_before_admission(tmp_path, monkeypatch, trust):
    request = _hdl(tmp_path)
    called = []
    _synthetic(monkeypatch, lambda *args: called.append(True))
    with pytest.raises(ValueError, match="Untrusted"):
        engine.execute_trusted(request, tmp_path / "run", trust=trust)
    assert not called and not (tmp_path / "run").exists()


def test_trust_must_be_explicit(tmp_path):
    with pytest.raises(TypeError):
        engine.execute_trusted(_hdl(tmp_path), tmp_path / "run")


def test_source_marker_does_not_authorize_modified_example(tmp_path, monkeypatch):
    request = _hdl(tmp_path)
    request.source.write_text("module testbench; initial $finish; endmodule")
    (tmp_path / "build.json").write_text(json.dumps({"profile": request.profile, "trusted": True}))
    called = []
    _synthetic(monkeypatch, lambda *args: called.append(True))
    with pytest.raises(ValueError, match="does not match"):
        engine.execute_trusted(request, tmp_path / "run", trust="trusted_example")
    assert not called and not (tmp_path / "run").exists()


def test_trusted_project_snapshots_before_dispatch(tmp_path, monkeypatch):
    request = _hdl(tmp_path)
    original = request.source.read_bytes()
    def check(snapshot, output, cancel):
        assert snapshot.source != request.source
        assert snapshot.source.parent == output
        assert snapshot.source.read_bytes() == original
        request.source.write_bytes(b"modified after snapshot")
        assert snapshot.source.read_bytes() == original
    _synthetic(monkeypatch, check)
    result = engine.execute_trusted(request, tmp_path / "run", trust="trusted_project")
    assert result["status"] == "passed"
    assert result["evidence"]["admission"]["trust"] == "trusted_project"
    assert result["evidence"]["admission"]["sandboxed"] is False
    assert result["evidence"]["measurement_mode"] == "synthetic_test"


def test_example_changed_after_preflight_never_dispatches(tmp_path, monkeypatch):
    request = _hdl(tmp_path)
    original = security.prepare_trusted_request
    def changed(request, output, trust):
        request.source.write_bytes(b"changed before snapshot")
        return original(request, output, trust)
    monkeypatch.setattr(security, "prepare_trusted_request", changed)
    called = []
    _synthetic(monkeypatch, lambda *args: called.append(True))
    result = engine.execute_trusted(request, tmp_path / "run", trust="trusted_example")
    assert result["status"] == "infrastructure_failure"
    assert "does not match" in result["evidence"]["error"]
    assert not called


def test_verified_builtin_riscv_image_is_accepted_and_forgery_is_not(tmp_path):
    from firmavex.backends.bundled import prepare_builtin_riscv
    prepare_builtin_riscv(tmp_path / "example")
    source = tmp_path / "example/firmware.elf"
    request = Request("riscv32-virt", source, (2, 1))
    security.validate_trust(request, "trusted_example")
    source.write_bytes(b"forged ELF")
    (source.parent / "build.json").write_text(json.dumps({"firmware": {"sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}))
    with pytest.raises(ValueError, match="verified bundled"):
        security.validate_trust(request, "trusted_example")


def test_verified_arm_example_checks_configuration_and_image(tmp_path):
    from firmavex.product.bundled_example import prepare_example
    prepare_example(tmp_path / "example")
    request = Request("cortex-m3-mps2", tmp_path / "example/project.json")
    security.validate_trust(request, "trusted_example")
    configuration = json.loads(request.source.read_text())
    configuration["qemu"] = str(tmp_path / "untrusted executable")
    request.source.write_text(json.dumps(configuration))
    with pytest.raises(ValueError, match="configuration differs"):
        security.validate_trust(request, "trusted_example")
    configuration["qemu"] = None
    request.source.write_text(json.dumps(configuration))
    (request.source.parent / "example.elf").write_bytes(b"bad")
    with pytest.raises(ValueError, match="does not match"):
        security.validate_trust(request, "trusted_example")


def test_arm_trusted_snapshot_does_not_refer_to_original_firmware(tmp_path):
    from firmavex.product.bundled_example import prepare_example
    prepare_example(tmp_path / "example")
    request = Request("cortex-m3-mps2", tmp_path / "example/project.json")
    output = security.fresh_directory(tmp_path / "snapshot")
    snapshot = security.prepare_trusted_request(request, output, "trusted_example")
    config = json.loads(snapshot.source.read_text())
    assert Path(config["firmware"]).parent == output
    assert Path(config["firmware"]).read_bytes() == (tmp_path / "example/example.elf").read_bytes()


@pytest.mark.parametrize("spelling", ["../bad", "name\nfile", "name\x00file"])
def test_unsafe_path_spellings_rejected(tmp_path, spelling):
    with pytest.raises(ValueError, match="Unsafe"):
        security.checked_path(tmp_path / spelling, exists=False)


def test_source_and_parent_symlinks_are_rejected(tmp_path):
    request = _hdl(tmp_path)
    try:
        (tmp_path / "link.v").symlink_to(request.source)
        (tmp_path / "linked-directory").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink privilege unavailable")
    for path in (tmp_path / "link.v", tmp_path / "linked-directory/input.v"):
        with pytest.raises(ValueError, match="Symlink"):
            security.read_bytes(path, 1024)


def test_special_file_rejected_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("Named pipes require POSIX")
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    with pytest.raises(ValueError, match="regular"):
        security.read_bytes(pipe, 1024)


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_ambiguous_json_rejected(tmp_path, text):
    path = tmp_path / "json"
    path.write_text(text)
    with pytest.raises(ValueError):
        security.read_json(path)


def test_bounded_json_read(tmp_path):
    path = tmp_path / "json"
    path.write_bytes(b"x" * 100)
    with pytest.raises(ValueError, match="byte limit"):
        security.read_json(path, 50)


def test_mid_read_changes_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "input"
    path.write_bytes(b"first")
    original = security.handle_state
    calls = 0
    def mutate(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"other")
        return original(fd)
    monkeypatch.setattr(security, "handle_state", mutate)
    with pytest.raises(ValueError, match="changed during capture"):
        security.read_bytes(path, 1024)


@pytest.mark.parametrize("patch", [{"schema_version": True}, {"schema_version": 2}, {"status": "invented"},
                                    {"evidence": []}, {"unexpected": 1}])
def test_malformed_results_rejected(tmp_path, patch):
    output, record = _stored(tmp_path)
    record.update(patch)
    engine._write(output / "result.json", record)
    with pytest.raises(ValueError, match="Invalid backend result"):
        engine.inspect_run(output)


def test_completed_real_record_without_cleanup_rejected(tmp_path):
    output, record = _stored(tmp_path)
    record["evidence"].update(measurement_mode="real_simulation", cleanup_verified=False)
    engine._write(output / "result.json", record)
    with pytest.raises(ValueError, match="verified cleanup"):
        engine.inspect_run(output)


def test_result_admission_mismatch_rejected(tmp_path):
    output, record = _stored(tmp_path)
    changed = {**record["evidence"]["admission"], "attempt_id": "1" * 32}
    engine._write(output / "admission.json", changed)
    with pytest.raises(ValueError, match="does not match"):
        engine.inspect_run(output)


def test_result_changed_during_inspection_rejected(tmp_path, monkeypatch):
    output, record = _stored(tmp_path)
    original = engine.read_json
    def mutate(path, *args):
        read = original(path, *args)
        if path.name == "admission.json":
            record["status"] = "triggered"
            engine._write(output / "result.json", record)
        return read
    monkeypatch.setattr(engine, "read_json", mutate)
    with pytest.raises(ValueError, match="changed during inspection"):
        engine.inspect_run(output)


def test_atomic_persistence_cancellation_leaves_no_temporary_file(tmp_path, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt("interrupted write")
    monkeypatch.setattr(engine.os, "replace", interrupt)
    with pytest.raises(KeyboardInterrupt, match="interrupted write"):
        engine._write(tmp_path / "result.json", {"schema_version": 1})
    assert list(tmp_path.iterdir()) == []


def test_live_ownership_distinguished_without_inferring_accounting(tmp_path, monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    def hold(*args):
        entered.set()
        assert finish.wait(10)
    _synthetic(monkeypatch, hold)
    output = tmp_path / "run"
    errors = []
    def run():
        try:
            engine.execute(_hdl(tmp_path), output)
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(10)
        record = engine.inspect_run(output)
        assert record["status"] == "incomplete"
        assert record["evidence"]["lifecycle"].startswith("running;")
        assert record["evidence"]["accounting"].startswith("unknown;")
    finally:
        finish.set()
        thread.join(10)
    assert not thread.is_alive() and not errors
    assert engine.inspect_run(output)["status"] == "passed"


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_interrupted_persistence_releases_ownership_and_preserves_original(tmp_path, monkeypatch, interruption):
    from firmavex.backends.implementations import IcarusBackend
    def interrupt(*args):
        raise interruption("original control flow")
    monkeypatch.setattr(IcarusBackend, "execute", interrupt)
    original = engine._write
    def broken(path, record):
        if path.name == "result.json":
            raise OSError("disk unavailable")
        original(path, record)
    monkeypatch.setattr(engine, "_write", broken)
    output = tmp_path / "run"
    with pytest.raises(interruption, match="original control flow") as caught:
        engine.execute(_hdl(tmp_path), output)
    assert "disk unavailable" in caught.value.__notes__[0]
    result = engine.inspect_run(output)
    assert result["evidence"]["lifecycle"].startswith("interrupted;")
    assert result["evidence"]["accounting"].startswith("unknown;")


def test_export_copies_real_artifact_bytes_and_logs_with_checksums(tmp_path):
    payload = b"$date unit-test waveform $end\n"
    artifact = {"name": "waveform.vcd", "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}
    output, record = _stored(tmp_path, [artifact])
    (output / "waveform.vcd").write_bytes(payload)
    destination = tmp_path / "export"
    exported = report.export(output, destination)
    assert (destination / "waveform.vcd").read_bytes() == payload
    assert (destination / "stdout.txt").read_text() == "synthetic stdout\n"
    assert (destination / "process-0000-stderr.txt").read_text() == "child error\n"
    for name, expected in exported["files"].items():
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected
    assert engine.inspect_run(output) == record


@pytest.mark.parametrize("name", ["../escape.vcd", "/tmp/escape", "folder/wave.vcd", "folder\\wave.vcd", "C:escape", "result.json"])
def test_export_rejects_unsafe_names_and_reserved_collisions_before_output(tmp_path, name):
    output, record = _stored(tmp_path, [{"name": name, "sha256": "0" * 64, "size_bytes": 0}])
    with pytest.raises(ValueError):
        report.export(output, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_export_changed_waveform_rejected(tmp_path):
    payload = b"original"
    output, record = _stored(tmp_path, [{"name": "waveform.vcd", "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}])
    (output / "waveform.vcd").write_bytes(b"modified")
    with pytest.raises(ValueError, match="no longer matches"):
        report.export(output, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_export_symlink_waveform_rejected(tmp_path):
    payload = b"external"
    external = tmp_path / "external"
    external.write_bytes(payload)
    output, record = _stored(tmp_path, [{"name": "waveform.vcd", "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}])
    try:
        (output / "waveform.vcd").symlink_to(external)
    except OSError:
        pytest.skip("Symlink privilege unavailable")
    with pytest.raises(ValueError, match="Symlink"):
        report.export(output, tmp_path / "export")


def test_case_colliding_artifacts_rejected(tmp_path):
    payload = b"x"
    metadata = {"sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": 1}
    output, record = _stored(tmp_path, [{"name": "wave.vcd", **metadata}, {"name": "WAVE.vcd", **metadata}])
    (output / "wave.vcd").write_bytes(payload)
    with pytest.raises(ValueError, match="collision"):
        report.export(output, tmp_path / "export")


def test_export_never_overwrites_existing_outputs(tmp_path):
    output, record = _stored(tmp_path)
    destination = tmp_path / "export"
    destination.mkdir()
    saved = destination / "retain"
    saved.write_bytes(b"untouched")
    with pytest.raises(FileExistsError):
        report.export(output, destination)
    assert saved.read_bytes() == b"untouched"


def test_export_retention_limit_prevents_creation(tmp_path, monkeypatch):
    output, record = _stored(tmp_path)
    monkeypatch.setattr(report, "EXPORT_BYTES", 10)
    with pytest.raises(ValueError, match="retention limit"):
        report.export(output, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_hardlinked_input_is_rejected(tmp_path):
    path = tmp_path / "original"
    path.write_bytes(b"bytes")
    try:
        os.link(path, tmp_path / "alias")
    except OSError:
        pytest.skip("Hardlinks unavailable")
    with pytest.raises(ValueError, match="regular"):
        security.read_bytes(path, 100)


def test_deeply_nested_json_is_a_structured_invalid_input(tmp_path):
    path = tmp_path / "json"
    path.write_text("[" * 1500 + "0" + "]" * 1500)
    with pytest.raises(ValueError, match="nesting"):
        security.read_json(path)


def test_replay_dispatches_verified_bytes_even_if_original_changes(tmp_path, monkeypatch):
    output, record = _stored(tmp_path)
    source = output / "testbench.v"
    data = b"verified input bytes"
    source.write_bytes(data)
    record["evidence"]["source"] = {"sha256": hashlib.sha256(data).hexdigest()}
    record["evidence"]["admission"]["limits"] = {"timeout_seconds": 10, "log_bytes": 524288,
                                                   "artifact_bytes": 16777216, "memory_bytes": 2147483648}
    engine._write(output / "result.json", record)
    engine._write(output / "admission.json", record["evidence"]["admission"])
    temporary_sources = []
    def dispatch(request, destination, cancel):
        temporary_sources.append(request.source)
        source.write_bytes(b"changed archive input")
        assert request.source != source
        assert request.source.read_bytes() == data
        return {"status": "passed", "evidence": {"measurement_mode": "synthetic_test"}}
    monkeypatch.setattr(report, "execute", dispatch)
    replay = report.reproduce(output, tmp_path / "replay")
    assert replay["outcome_matches"]
    assert not temporary_sources[0].parent.exists()


def test_export_aggregate_record_and_report_limit_checked_before_creation(tmp_path, monkeypatch):
    output, record = _stored(tmp_path)
    monkeypatch.setattr(report, "EXPORT_BYTES", 1000)
    with pytest.raises(ValueError, match="including report"):
        report.export(output, tmp_path / "export")
    assert not (tmp_path / "export").exists()


@pytest.mark.parametrize("failure,expected", [(OSError, "infrastructure_failure"), (KeyboardInterrupt, "cancelled"), (SystemExit, "cancelled")])
def test_ownership_cleanup_failure_cannot_leave_successful_result(tmp_path, monkeypatch, failure, expected):
    _synthetic(monkeypatch)
    original = engine._Ownership.close
    def broken(self):
        original(self)
        raise failure("final ownership failure")
    monkeypatch.setattr(engine._Ownership, "close", broken)
    with pytest.raises(failure, match="final ownership failure"):
        engine.execute(_hdl(tmp_path), tmp_path / "run")
    result = engine.inspect_run(tmp_path / "run")
    assert result["status"] == expected
    assert result["evidence"]["original_status"] == "passed"
    assert "ownership failure" in result["evidence"]["error"]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_cleanup_control_flow_not_swallowed_after_ordinary_failure(tmp_path, monkeypatch, interruption):
    from firmavex.backends.implementations import IcarusBackend
    def invalid(*args):
        raise ValueError("ordinary backend failure")
    monkeypatch.setattr(IcarusBackend, "execute", invalid)
    original = engine._Ownership.close
    def interrupted(self):
        original(self)
        raise interruption("cancel during ownership cleanup")
    monkeypatch.setattr(engine._Ownership, "close", interrupted)
    with pytest.raises(interruption, match="cancel during ownership cleanup"):
        engine.execute(_hdl(tmp_path), tmp_path / "run")
    assert engine.inspect_run(tmp_path / "run")["status"] == "infrastructure_failure"


def test_interrupted_readonly_archive_inspection_does_not_write(tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    admission = {"attempt_id": "a" * 32}
    engine._write(output / "admission.json", admission)
    ownership = engine._Ownership(output, admission["attempt_id"])
    ownership.close()
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    for path in output.iterdir():
        path.chmod(0o400)
    try:
        result = engine.inspect_run(output)
        assert result["evidence"]["lifecycle"].startswith("interrupted;")
        assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    finally:
        for path in output.iterdir():
            path.chmod(0o600)


def test_arm_archive_read_failure_prevents_export_creation(tmp_path, monkeypatch):
    from firmavex.product import services
    output, record = _stored(tmp_path)
    record["evidence"]["admission"]["profile"]["id"] = "cortex-m3-mps2"
    engine._write(output / "admission.json", record["evidence"]["admission"])
    engine._write(output / "result.json", record)
    archive = output / "arm-run"
    archive.mkdir()
    (archive / "run.sqlite3").write_bytes(b"synthetic sqlite placeholder")
    def fail(*args):
        raise ValueError("authoritative archive unreadable")
    monkeypatch.setattr(services, "_read_run", fail)
    with pytest.raises(ValueError, match="archive unreadable"):
        report.export(output, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_arm_authoritative_logs_export_without_changing_classification(tmp_path, monkeypatch):
    from firmavex.product import services
    output, record = _stored(tmp_path)
    record["evidence"]["admission"]["profile"]["id"] = "cortex-m3-mps2"
    record["evidence"]["legacy_result"] = {"measurement_mode": "synthetic_test", "success": True}
    engine._write(output / "admission.json", record["evidence"]["admission"])
    engine._write(output / "result.json", record)
    archive = output / "arm-run"
    archive.mkdir()
    (archive / "run.sqlite3").write_bytes(b"synthetic sqlite placeholder")
    snapshot = {"schema_version": 1, "result": record["evidence"]["legacy_result"], "attempts": [
        {"sequence": 1, "record": {"input": [2, 1], "evidence": {"stdout": "synthetic attempt stdout", "stderr": "attempt stderr", "measurement_mode": "synthetic_test"}}}]}
    monkeypatch.setattr(services, "_read_run", lambda *args: (snapshot, {}))
    exported = report.export(output, tmp_path / "export")
    assert (tmp_path / "export/arm-attempt-000001-stdout.txt").read_text() == "synthetic attempt stdout"
    saved = json.loads((tmp_path / "export/arm-evidence.json").read_text())
    assert saved["result"]["measurement_mode"] == "synthetic_test"
    assert saved["inspection_is_not_execution_verification"] is True
    assert "arm-evidence.json" in exported["files"]


def test_actual_arm_export_retains_authoritative_receipts_readonly(tmp_path):
    import shutil
    missing = [name for name in ("qemu-system-arm",) if not shutil.which(name)]
    if not any(shutil.which(name) for name in ("arm-none-eabi-gdb","gdb-multiarch","gdb")):
        missing.append("ARM-capable GDB")
    if missing:
        if os.environ.get("FIRMAVEX_REQUIRE_BACKENDS") == "1":
            pytest.fail("Missing actual ARM tools: " + str(missing))
        pytest.skip("Actual ARM tools unavailable")
    from firmavex.product.bundled_example import prepare_example
    prepare_example(tmp_path / "example")
    output = tmp_path / "run"
    observed = engine.execute_trusted(Request("cortex-m3-mps2", tmp_path / "example/project.json"), output, trust="trusted_example")
    assert observed["status"] == "triggered", observed
    assert observed["evidence"]["triggering_input"] == [2, 1]
    before = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in output.rglob("*") if path.is_file()}
    report.export(output, tmp_path / "export")
    archive = json.loads((tmp_path / "export/arm-evidence.json").read_text())
    assert archive["result"] == observed["evidence"]["legacy_result"]
    assert len(archive["attempts"]) == archive["result"]["accounting"]["attempted_executions"] == 10
    assert archive["result"]["measurement_mode"] == "real_firmware"
    assert all(attempt["record"]["evidence"]["cleanup_verified"] for attempt in archive["attempts"])
    assert (tmp_path / "export/arm-attempt-000010-stdout.txt").read_text()
    after = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in output.rglob("*") if path.is_file()}
    assert after == before


def test_same_size_rewrite_with_deferred_metadata_fails_closed(tmp_path, monkeypatch):
    """Model NTFS metadata deferral, rather than relying on timestamp granularity."""
    path = tmp_path / "input"
    path.write_bytes(b"first")
    state = security.path_state(path)
    calls = 0

    def capture(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"other")
        return state

    monkeypatch.setattr(security, "path_state", lambda *args: state)
    monkeypatch.setattr(security, "handle_state", capture)
    with pytest.raises(ValueError, match="changed during capture"):
        security.read_bytes(path, 1024)
