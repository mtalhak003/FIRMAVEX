"""Synthetic desktop project storage tests; no guest execution is simulated."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from firmavex.desktop import projects
from firmavex.desktop.projects import DesktopProject, application_data_directory
from firmavex.product.config import ProductConfig
from firmavex.product.errors import ProductError


@pytest.fixture
def source(tmp_path, monkeypatch):
    firmware = tmp_path / "original.elf"
    firmware.write_bytes(b"synthetic unit-test image; not ARM execution")
    config = ProductConfig(firmware=firmware, input_symbols=("inputs[0]", "inputs[1]"),
                           ready_breakpoint="ready", completion_breakpoint="complete",
                           failure_symbol="failure", input_max=3, execution_budget=16)

    def synthetic_inspection(config):
        data = config.firmware.read_bytes()
        return {"firmware_sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data), "unit_test_only": True}

    monkeypatch.setattr(projects, "inspect_elf", synthetic_inspection)
    return firmware, config


@pytest.fixture
def project(tmp_path, source):
    return DesktopProject.create(tmp_path / "user project", *source)


def test_create_copies_source_unchanged_and_rebinds_config(project, source):
    firmware, config = source
    assert project.firmware_path.read_bytes() == firmware.read_bytes()
    assert project.load_config() == replace(config, firmware=project.firmware_path)
    assert project.config_path == project.root / "project.json"
    assert json.loads(project.config_path.read_text())["firmware"] == "firmware.elf"
    marker = json.loads((project.root / projects.MARKER).read_text())
    assert marker["consistency"] == {"atomic": False, "status": "stable_observed"}
    assert marker["firmware"]["sha256"] == hashlib.sha256(firmware.read_bytes()).hexdigest()


def test_open_and_load_are_read_only(project):
    before = {str(path.relative_to(project.root)): path.read_bytes()
              for path in project.root.rglob("*") if path.is_file()}
    reopened = DesktopProject.open(project.root)
    reopened.load_config()
    after = {str(path.relative_to(project.root)): path.read_bytes()
             for path in project.root.rglob("*") if path.is_file()}
    assert before == after


def test_save_retains_versioned_records_and_all_fields(project):
    before = project.config_path.read_bytes()
    old_records = list((project.root / "configurations").iterdir())
    config = replace(project.load_config(), strategy="guided", seed=42,
                     execution_budget=500, timeout_seconds=30,
                     guided_archive_size=7, guided_mutation_attempts=2)
    record = project.save_config(config)
    assert record.read_bytes() == project.config_path.read_bytes()
    assert old_records[0].read_bytes() == before
    assert len(list((project.root / "configurations").iterdir())) == 2
    assert project.load_config() == config


def test_repeated_save_has_fresh_history_and_same_config(project):
    config = project.load_config()
    first = project.save_config(config)
    second = project.save_config(config)
    assert first != second
    assert first.read_bytes() == second.read_bytes()


def test_import_never_overwrites_existing_directory(tmp_path, source):
    root = tmp_path / "existing"
    root.mkdir()
    sentinel = root / "sentinel"
    sentinel.write_text("preserve")
    with pytest.raises(ProductError, match="nonexistent"):
        DesktopProject.create(root, *source)
    assert sentinel.read_text() == "preserve"


def test_import_rejects_existing_empty_directory(tmp_path, source):
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ProductError):
        DesktopProject.create(root, *source)
    assert root.is_dir()


def test_create_rejects_configuration_for_another_image(tmp_path, source):
    firmware, config = source
    other = tmp_path / "other.elf"
    other.write_bytes(b"another image")
    with pytest.raises(ProductError, match="selected for import"):
        DesktopProject.create(tmp_path / "new", firmware, replace(config, firmware=other))
    assert not (tmp_path / "new").exists()


def test_import_rejects_source_symlink(tmp_path, source):
    firmware, config = source
    link = tmp_path / "source-link.elf"
    link.symlink_to(firmware)
    with pytest.raises(ProductError, match="regular file"):
        DesktopProject.create(tmp_path / "new", link, config)


def test_root_symlink_rejected_without_modifying_target(tmp_path, source):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ProductError, match="symbolic"):
        DesktopProject.create(link, *source)
    assert list(target.iterdir()) == []


def test_install_and_source_directories_rejected(source):
    repository = Path(projects.__file__).resolve().parents[2]
    with pytest.raises(ProductError, match="outside"):
        DesktopProject.create(repository / "unwanted-project", *source)
    assert not (repository / "unwanted-project").exists()


def test_missing_or_incompatible_image_does_not_create_project(tmp_path, source, monkeypatch):
    firmware, config = source
    monkeypatch.setattr(projects, "inspect_elf",
                        lambda config: (_ for _ in ()).throw(ProductError("unsupported_firmware", "bad image")))
    with pytest.raises(ProductError, match="bad image"):
        DesktopProject.create(tmp_path / "new", firmware, config)
    assert not (tmp_path / "new").exists()


def test_source_changes_after_validation_reject_import(tmp_path, source, monkeypatch):
    firmware, config = source
    original = projects.inspect_elf

    def change_after_validation(config):
        result = original(config)
        firmware.write_bytes(b"changed after validation")
        return result

    monkeypatch.setattr(projects, "inspect_elf", change_after_validation)
    with pytest.raises(ProductError) as failure:
        DesktopProject.create(tmp_path / "new", firmware, config)
    assert failure.value.category == "artifact_changed"
    assert not (tmp_path / "new").exists()


def test_import_copy_validation_failure_cleans_only_new_project(tmp_path, source, monkeypatch):
    firmware, config = source
    original = projects.inspect_elf

    def reject_copied(config):
        if config.firmware != firmware:
            raise ProductError("unsupported_firmware", "import validation failed")
        return original(config)

    monkeypatch.setattr(projects, "inspect_elf", reject_copied)
    with pytest.raises(ProductError, match="import validation failed"):
        DesktopProject.create(tmp_path / "new", firmware, config)
    assert firmware.is_file()
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("method", ["open", "load_config", "new_run_directory", "save_config"])
def test_modified_imported_firmware_rejected_everywhere(project, method):
    config = project.load_config()
    project.firmware_path.write_bytes(b"tampered")
    with pytest.raises(ProductError) as failure:
        if method == "open":
            DesktopProject.open(project.root)
        elif method == "save_config":
            project.save_config(config)
        else:
            getattr(project, method)()
    assert failure.value.category == "artifact_changed"


@pytest.mark.parametrize("name", ["firmware.elf", "project.json", projects.MARKER])
def test_project_file_symlinks_rejected(project, tmp_path, name):
    path = project.root / name
    outside = tmp_path / "outside"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ProductError, match="regular file"):
        DesktopProject.open(project.root)


@pytest.mark.parametrize("name", ["runs", "configurations"])
def test_project_subdirectory_symlinks_rejected(project, tmp_path, name):
    directory = project.root / name
    directory.rename(project.root / f"original-{name}")
    outside = tmp_path / f"outside-{name}"
    outside.mkdir()
    directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProductError, match="symbolic link"):
        DesktopProject.open(project.root)


def test_modified_active_configuration_requires_saved_record(project):
    value = json.loads(project.config_path.read_text())
    value["input_max"] = 9
    project.config_path.write_text(json.dumps(value))
    with pytest.raises(ProductError, match="matching immutable"):
        project.load_config()


def test_config_cannot_switch_firmware(project, source):
    with pytest.raises(ProductError, match="imported firmware"):
        project.save_config(replace(project.load_config(), firmware=source[0]))


def test_modified_history_rejects_save(project):
    record = next((project.root / "configurations").iterdir())
    record.write_text("changed")
    with pytest.raises(ProductError) as failure:
        project.save_config(replace(project.load_config(), input_max=7))
    # load_config already detects the modified record before save is reached.
    assert failure.value.category == "artifact_changed"


def test_modified_inactive_history_rejects_open(project):
    first = next((project.root / "configurations").iterdir())
    project.save_config(replace(project.load_config(), input_max=7))
    first.write_text("changed historical configuration")
    with pytest.raises(ProductError) as failure:
        DesktopProject.open(project.root)
    assert failure.value.category == "artifact_changed"


def test_duplicate_history_version_rejected(project):
    first = next((project.root / "configurations").iterdir())
    value = json.loads(first.read_text())
    value["execution_budget"] = 20
    data = projects._encoded(value)
    duplicate = first.parent / f"000001-{hashlib.sha256(data).hexdigest()}.json"
    duplicate.write_bytes(data)
    with pytest.raises(ProductError, match="repeated version"):
        project.load_config()


def test_dangling_active_symlink_is_not_overwritten(project, tmp_path):
    config = project.load_config()
    project.config_path.unlink()
    project.config_path.symlink_to(tmp_path / "missing")
    with pytest.raises(ProductError, match="regular file"):
        project.save_config(config)
    assert project.config_path.is_symlink()


def test_cleanup_does_not_replace_original_interruption(tmp_path, source, monkeypatch):
    original = projects.inspect_elf
    interrupt = KeyboardInterrupt("original cancellation")

    def interrupted_validation(config):
        if config.firmware != source[0]:
            raise interrupt
        return original(config)

    monkeypatch.setattr(projects, "inspect_elf", interrupted_validation)
    monkeypatch.setattr(projects.shutil, "rmtree",
                        lambda *args: (_ for _ in ()).throw(OSError("cleanup failed")))
    with pytest.raises(KeyboardInterrupt) as failure:
        DesktopProject.create(tmp_path / "new", *source)
    assert failure.value is interrupt
    assert "cleanup failed" in failure.value.__notes__[0]


def test_unexpected_history_entry_rejects_save(project):
    config = project.load_config()
    (project.root / "configurations" / "unrelated.txt").write_text("preserve")
    with pytest.raises(ProductError, match="Unexpected"):
        project.save_config(config)


def test_atomic_replace_failure_preserves_active_and_history(project, monkeypatch):
    old = project.config_path.read_bytes()
    updated = replace(project.load_config(), execution_budget=200)
    monkeypatch.setattr(projects.os, "replace",
                        lambda *args: (_ for _ in ()).throw(OSError("test replacement failure")))
    with pytest.raises(OSError, match="replacement failure"):
        project.save_config(updated)
    assert project.config_path.read_bytes() == old
    assert project.load_config().execution_budget == 16
    assert len(list((project.root / "configurations").iterdir())) == 2
    assert not list(project.root.glob(".project-*.tmp"))


def test_write_lock_rejects_competing_writer(project):
    config = project.load_config()
    with projects._write_lock(project.root):
        with pytest.raises(ProductError) as failure:
            project.save_config(config)
    assert failure.value.category == "project_busy"


def test_run_destinations_unique_nonexistent_and_inside_project(project):
    first = project.new_run_directory()
    second = project.new_run_directory("reproduction")
    assert first != second
    assert first.parent == second.parent == project.root / "runs"
    assert not first.exists() and not second.exists()


@pytest.mark.parametrize("kind", ["../outside", "Uppercase", "", "a" * 33, False, None])
def test_run_kind_validation(project, kind):
    with pytest.raises(ProductError):
        project.new_run_directory(kind)


@pytest.mark.parametrize("marker", [[], {"schema_version": True}, {"schema_version": 2}])
def test_malformed_marker_rejected(project, marker):
    (project.root / projects.MARKER).write_text(json.dumps(marker))
    with pytest.raises(ProductError):
        DesktopProject.open(project.root)


@pytest.mark.parametrize("content", ['{"kind":1,"kind":2}', '{"bad":NaN}', 'not json'])
def test_noncanonical_json_rejected(project, content):
    (project.root / projects.MARKER).write_text(content)
    with pytest.raises(ProductError):
        DesktopProject.open(project.root)


def test_observable_mid_read_change_fails_closed(project, monkeypatch):
    path = project.firmware_path
    original = projects._regular
    count = 0

    def changing_regular(candidate):
        nonlocal count
        if candidate == path:
            count += 1
            if count == 2:
                path.write_bytes(b"modified while reading")
        return original(candidate)

    monkeypatch.setattr(projects, "_regular", changing_regular)
    with pytest.raises(ProductError) as failure:
        project.load_config()
    assert failure.value.category == "artifact_changed"


def test_application_data_linux_uses_absolute_xdg_without_creation(tmp_path, monkeypatch):
    target = tmp_path / "data"
    monkeypatch.setattr(projects.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(target))
    assert application_data_directory() == target / "FIRMAVEX"
    assert not target.exists()


def test_application_data_linux_ignores_relative_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(projects.sys, "platform", "linux")
    monkeypatch.setattr(projects.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", "relative")
    assert application_data_directory() == tmp_path / ".local" / "share" / "FIRMAVEX"


def test_application_data_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(projects.sys, "platform", "darwin")
    monkeypatch.setattr(projects.Path, "home", classmethod(lambda cls: tmp_path))
    assert application_data_directory() == tmp_path / "Library" / "Application Support" / "FIRMAVEX"


def test_application_data_windows_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setattr(projects.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "WindowsData"))
    assert application_data_directory() == tmp_path / "WindowsData" / "FIRMAVEX"


def test_command_admission_preserves_saved_settings_after_another_window_edit(project):
    selected=project.load_config()
    record=project.save_config(selected)
    original=record.read_bytes()
    # A second owner changes the mutable active config before first dispatch.
    second=DesktopProject.open(project.root)
    second.save_config(replace(selected,execution_budget=999, strategy='random', seed=7))
    command=project.command_config(record)
    from firmavex.product.config import load_config
    admitted=load_config(command)
    assert admitted.execution_budget==16 and admitted.strategy=='enumerative' and admitted.seed is None
    assert admitted.firmware==project.firmware_path
    assert project.load_config().execution_budget==999
    assert record.read_bytes()==original


def test_command_rejects_foreign_record_and_changed_saved_bytes(project,tmp_path):
    config=project.load_config();record=project.save_config(config)
    foreign=tmp_path/record.name;foreign.write_bytes(record.read_bytes())
    with pytest.raises(ProductError): project.command_config(foreign)
    record.write_bytes(record.read_bytes()+b' ')
    with pytest.raises(ProductError) as failure: project.command_config(record)
    assert failure.value.category=='artifact_changed'


def test_command_snapshot_directory_cannot_redirect_writes(project,tmp_path):
    destination=tmp_path/'foreign';destination.mkdir()
    (project.root/'commands').symlink_to(destination,target_is_directory=True)
    record=project.save_config(project.load_config())
    with pytest.raises(ProductError): project.command_config(record)
    assert list(destination.iterdir())==[]
