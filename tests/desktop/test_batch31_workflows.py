"""Desktop failure/retry journeys; no guest execution or native qualification.

Project/static checks below use the real bundled ELF and filesystem. Controller
responses are explicitly synthetic and cannot become firmware evidence.
"""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from firmavex.desktop import window as ui
from firmavex.desktop.projects import DesktopProject
from firmavex.product.config import load_config
from firmavex.product.services import prepare_example_project
from tests.desktop.test_batch29_exports import response
from tests.desktop.test_window import view
from tests.desktop.test_universal import select, view as backend_view


@pytest.fixture
def real_projects(tmp_path):
    prepared = prepare_example_project(tmp_path / 'bundled image α & #1')
    assert prepared['firmware_executed'] is False
    assert prepared['compiler_required'] is False
    config = load_config(prepared['config_file'])
    first = DesktopProject.create(tmp_path / 'first project α', config.firmware, config)
    second = DesktopProject.create(tmp_path / 'second project β', config.firmware, config)
    return first, second, config


def project_bytes(project):
    """Inventory only an owned temporary project, never a checkout/evidence root."""
    return {str(path.relative_to(project.root)): path.read_bytes()
            for path in project.root.rglob('*') if path.is_file()}


@pytest.mark.parametrize('choice', [QMessageBox.No, QMessageBox.Yes], ids=['keep-edits', 'discard-edits'])
@pytest.mark.parametrize('route', ['open', 'recent'])
def test_open_project_confirms_unsaved_edits_and_preserves_saved_bytes(
        view, real_projects, qtbot, monkeypatch, choice, route):
    window, controller = view
    first, second, _ = real_projects
    window._adopt_project((first, first.load_config()))
    original_first, original_second = project_bytes(first), project_bytes(second)
    window.maximum_edit.setText('invalid unsaved value')
    prompts = []
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: prompts.append(args) or choice)
    if route == 'recent':
        from firmavex.desktop.recents import remember
        remember(window.data_root, second.root)
        window._refresh_recents()
        window.recent_projects.setCurrentIndex(window.recent_projects.findData(str(second.root)))
        window.open_recent_project()
    else:
        window.open_project(second.root)
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert len(prompts) == 1 and prompts[0][-1] == QMessageBox.No
    if choice == QMessageBox.No:
        assert window.project is first
        assert window.maximum_edit.text() == 'invalid unsaved value'
    else:
        assert window.project.root == second.root
        assert window.maximum_edit.text() == str(second.load_config().input_max)
    assert project_bytes(first) == original_first and project_bytes(second) == original_second
    assert controller.calls == []


def test_successful_project_switch_clears_previous_result_and_export_context(
        view, real_projects, qtbot):
    window, controller = view
    first, second, _ = real_projects
    window._adopt_project((first, first.load_config()))
    old_run = first.root / 'runs' / 'previous'
    old_run.mkdir()
    sentinel = old_run / 'saved-result.txt'
    sentinel.write_bytes(b'original saved evidence is retained')
    window.active_run = old_run
    window._show_result({'state': 'completed', 'outcome': 'configured_failure_observed',
                        'measurement_mode': 'synthetic_test', 'triggering_input': [2, 1]})
    window._last_export = first.root / 'previous-export'
    window.progress_bar.setRange(0, 16)
    window.progress_bar.setValue(7)
    window.attempts_table.setRowCount(1)
    window.open_project(second.root)
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert window.project.root == second.root
    assert window.active_run is None and window.result_record is None and window.inspection is None
    assert window._last_export is None
    assert not window.export_button.isEnabled() and not window.open_export_button.isEnabled()
    assert window.result_text.toPlainText() == '' and window.report_view.toPlainText() == ''
    assert window.progress_bar.value() == 0 and window.attempts_table.rowCount() == 0
    assert sentinel.read_bytes() == b'original saved evidence is retained'
    assert controller.calls == []


def test_failed_project_open_retains_unsaved_editor_and_prior_result(
        view, real_projects, qtbot, monkeypatch):
    window, controller = view
    first, _, _ = real_projects
    window._adopt_project((first, first.load_config()))
    before = project_bytes(first)
    window.maximum_edit.setText('unsaved invalid value')
    old_run = first.root / 'runs' / 'retained'
    previous = {'state': 'completed', 'outcome': 'domain_exhausted',
                'measurement_mode': 'synthetic_test'}
    window.active_run = old_run
    window._show_result(previous)
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window.open_project(first.root.parent / 'missing project')
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert window.project is first and window.maximum_edit.text() == 'unsaved invalid value'
    assert window.active_run == old_run and window.result_record == previous
    assert 'desktop_project_error' in window.status_label.text()
    assert 'missing' in window.status_label.text()
    assert project_bytes(first) == before and controller.calls == []
    assert window.open_button.isEnabled()


@pytest.mark.parametrize('method,command', [
    ('prepare_builtin_example', 'prepare_example'), ('build_example', 'build_example')])
@pytest.mark.parametrize('choice', [QMessageBox.No, QMessageBox.Yes], ids=['keep-edits', 'discard-edits'])
def test_example_replacement_requires_explicit_discard_before_worker_dispatch(
        view, real_projects, monkeypatch, method, command, choice):
    window, controller = view
    first, _, _ = real_projects
    window._adopt_project((first, first.load_config()))
    before = project_bytes(first)
    window.maximum_edit.setText('unsaved invalid value')
    prompts = []
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: prompts.append(args) or choice)
    getattr(window, method)()
    assert len(prompts) == 1 and prompts[0][-1] == QMessageBox.No
    assert window.project is first and project_bytes(first) == before
    assert window.maximum_edit.text() == 'unsaved invalid value'
    if choice == QMessageBox.No:
        assert not controller.calls and not window.busy
    else:
        assert controller.calls[0][0] == command and window.busy
        controller.finish(error={'category': 'cancelled', 'message': 'Synthetic preparation cancelled'})
        assert window.project is first and window.maximum_edit.text() == 'unsaved invalid value'


def test_gui_import_open_and_static_retry_use_actual_bundled_elf_without_tools(
        view, real_projects, qtbot, tmp_path):
    window, controller = view
    _, _, config = real_projects
    window._load_fields(config)
    invalid = tmp_path / 'invalid firmware.bin'
    invalid.write_bytes(b'not an ELF image')
    window.firmware_edit.setText(str(invalid))
    assert window.check_selected_firmware()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert 'static check failed' in window.firmware_status.text()
    assert not window._checking_selected_firmware
    window.firmware_edit.setText(str(config.firmware))
    assert window.check_selected_firmware()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert 'Static ELF check passed' in window.firmware_status.text()
    assert 'no runtime tools or guest execution' in window.validation_text.toPlainText()
    destination = tmp_path / 'imported project γ & #2'
    window.project_dir_edit.setText(str(destination))
    original = config.firmware.read_bytes()
    window.create_project()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert window.project.root == destination
    assert window.project.firmware_path.read_bytes() == original
    saved = project_bytes(window.project)
    assert window.new_project()
    assert window.project is None
    window.open_project(destination)
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert window.project.root == destination and project_bytes(window.project) == saved
    assert controller.calls == []


@pytest.mark.parametrize('kind', ['file', 'existing-directory'])
def test_invalid_import_destination_retains_existing_files_and_can_retry(
        view, real_projects, qtbot, tmp_path, kind):
    window, controller = view
    _, _, config = real_projects
    window._load_fields(config)
    destination = tmp_path / 'existing user data'
    if kind == 'file':
        sentinel = destination
    else:
        destination.mkdir()
        sentinel = destination / 'keep.txt'
    sentinel.write_bytes(b'existing user data must not be overwritten')
    window.project_dir_edit.setText(str(destination))
    window.create_project()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert window.project is None and 'Choose a new' in window.status_label.text()
    assert sentinel.read_bytes() == b'existing user data must not be overwritten'
    assert window.create_button.isEnabled()
    fresh = tmp_path / 'new user project'
    window.project_dir_edit.setText(str(fresh))
    window.create_project()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert window.project.root == fresh
    assert window.project.firmware_path.read_bytes() == config.firmware.read_bytes()
    assert sentinel.read_bytes() == b'existing user data must not be overwritten'
    assert controller.calls == []


def test_failed_recent_reset_can_retry_without_changing_project(
        view, real_projects, qtbot, monkeypatch):
    from firmavex.desktop import recents
    window, controller = view
    first, _, _ = real_projects
    window._adopt_project((first, first.load_config()))
    before = project_bytes(first)
    index = window.data_root / 'recent-projects.json'
    index.write_bytes(b'corrupt preferences')
    window._refresh_recents()
    original_clear = recents.clear
    calls = []
    def denied_once(root):
        calls.append(root)
        if len(calls) == 1:
            raise PermissionError('Synthetic sharing violation; preferences remain unchanged')
        return original_clear(root)
    monkeypatch.setattr(recents, 'clear', denied_once)
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    assert window.clear_recent_projects()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert index.read_bytes() == b'corrupt preferences'
    assert 'sharing violation' in window.status_label.text()
    assert window.clear_recents_button.isEnabled()
    assert window.clear_recent_projects()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert recents.load(window.data_root) == [] and len(calls) == 2
    assert window.project is first and project_bytes(first) == before and controller.calls == []


def test_runtime_missing_then_rejected_then_ready_is_explicit_synthetic_feedback(backend_view, tmp_path):
    window, controller = backend_view
    select(window, 'verilog-icarus')
    window.source_edit.setText(str(tmp_path / 'trusted example.v'))
    window.trust_box.setChecked(True)
    for error in [{'category': 'missing_dependency', 'message': 'Synthetic Icarus absent'},
                  {'category': 'unsupported_platform', 'message': 'Synthetic runtime identity rejected'}]:
        window.check_runtime()
        controller.finish(error=error)
        assert not window._ready and not window.run_button.isEnabled()
        assert error['message'] in window.runtime_status_label.text()
        assert window.check_button.isEnabled()
    window.check_runtime()
    controller.finish({'status': 'tools_available', 'measurement_mode': 'synthetic_test'})
    assert window._ready and 'synthetic test feedback' in window.runtime_status_label.text()
    assert window.run_button.isEnabled()
    assert [command for command, _ in controller.calls] == ['backend_check'] * 3


def test_export_failure_retry_and_file_manager_failure_retain_source_result(
        view, qtbot, tmp_path, monkeypatch):
    window, controller = view
    source = tmp_path / 'saved run'
    source.mkdir()
    sentinel = source / 'keep.txt'
    sentinel.write_bytes(b'unchanged source archive bytes')
    previous = {'state': 'completed', 'outcome': 'domain_exhausted',
                'measurement_mode': 'synthetic_test'}
    window.active_run = source
    window._show_result(previous)
    failed = tmp_path / 'failed report'
    window._start('export', {'run_dir': str(source), 'output_dir': str(failed)}, output=failed)
    controller.finish(error={'category': 'io_error', 'message': 'Synthetic access denied'})
    assert not window.open_export_button.isEnabled() and 'did not complete' in window.export_status.text()
    destination = tmp_path / 'new report'; destination.mkdir()
    window._start('export', {'run_dir': str(source), 'output_dir': str(destination)}, output=destination)
    controller.finish(response(destination))
    assert window.open_export_button.isEnabled() and window._last_export == destination
    opened = []
    def denied_then_open(url):
        opened.append(url)
        return len(opened) > 1
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', denied_then_open)
    window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert 'could not open' in window.status_label.text()
    assert str(destination) in window.export_status.text() and window.open_export_button.isEnabled()
    window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert len(opened) == 2 and all(url.isLocalFile() for url in opened)
    assert all(Path(url.toLocalFile()) == destination for url in opened)
    assert window.active_run == source and window.result_record == previous
    assert sentinel.read_bytes() == b'unchanged source archive bytes'
    assert [command for command, _ in controller.calls] == ['export', 'export']


def test_cancelled_operation_can_reopen_unknown_state_and_explicitly_recover_ui_only(
        view, tmp_path, monkeypatch):
    window, controller = view
    source = tmp_path / 'interrupted synthetic run'
    window._start('run', {'config': 'synthetic-only'}, output=source)
    window.cancel_job()
    assert controller.cancelled and not window.cancel_button.isEnabled()
    controller.finish(error={'category': 'cancelled', 'message': 'Synthetic interruption after admission'})
    assert window.result_record is None and window.active_run == source
    window.open_run(source)
    controller.finish({'state': 'interrupted', 'recovery_required': True, 'result': None})
    assert window.recover_button.isEnabled() and not window.reproduce_button.isEnabled()
    assert 'Unknown execution accounting remains unknown' in window.report_view.toPlainText()
    prompts = []
    def keep_state(*args):
        prompts.append(args)
        return QMessageBox.No
    monkeypatch.setattr(ui.QMessageBox, 'question', keep_state)
    window.recover_current_run()
    assert len(controller.calls) == 2 and prompts[0][-1] == QMessageBox.No
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window.recover_current_run()
    assert controller.calls[-1] == ('recover', {'run_dir': str(source)})
    controller.finish({'state': 'interrupted', 'recovery_required': False, 'result': None})
    assert not window.recover_button.isEnabled() and window.result_record is None
    assert window.active_run == source and not window.reproduce_button.isEnabled()
    assert 'Unknown execution accounting remains unknown' in window.report_view.toPlainText()
    assert [command for command, _ in controller.calls] == ['run', 'inspect', 'recover']
