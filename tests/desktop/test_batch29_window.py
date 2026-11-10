"""Real Qt workflow checks; synthetic controller results are not firmware evidence."""
from pathlib import Path
import threading

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from firmavex.desktop import window as ui
from firmavex.desktop.recents import load
from firmavex.product.errors import ProductError
from tests.desktop.test_window import adopt, view


def test_new_project_really_unpins_old_project_and_clears_result_selection(view, tmp_path, monkeypatch):
    window, controller = view
    project = adopt(window, tmp_path)
    project.root.mkdir()
    retained = project.root / 'saved-result.txt'
    retained.write_bytes(b'previous authoritative bytes must stay unchanged')
    window.active_run = project.root / 'runs' / 'old'
    window._show_result({'state': 'completed', 'outcome': 'configured_failure_observed',
        'measurement_mode': 'synthetic_test', 'triggering_input': [2, 1]})
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: pytest.fail('Clean editor needs no discard prompt'))
    assert window.new_project() is True
    assert window.project is None and window.active_run is None and window.result_record is None
    assert window.firmware_edit.text() == '' and window.navigation.currentRow() == 1
    assert window.inputs_edit.text() == 'product_inputs[0], product_inputs[1]'
    assert not window.run_button.isEnabled() and not window.reproduce_button.isEnabled()
    assert not window.export_button.isEnabled() and window.trigger_label.text() == 'Triggering input: unavailable'
    assert retained.read_bytes() == b'previous authoritative bytes must stay unchanged'
    assert controller.calls == []


@pytest.mark.parametrize('choice', [QMessageBox.No, QMessageBox.Yes])
def test_new_project_requires_explicit_discard_of_unsaved_edits(view, tmp_path, monkeypatch, choice):
    window, controller = view
    project = adopt(window, tmp_path)
    window.maximum_edit.setText('not a valid integer')
    seen = []
    def question(*args):
        seen.append(args)
        return choice
    monkeypatch.setattr(ui.QMessageBox, 'question', question)
    assert window.new_project() is (choice == QMessageBox.Yes)
    assert seen[0][-1] == QMessageBox.No
    if choice == QMessageBox.No:
        assert window.project is project and window.maximum_edit.text() == 'not a valid integer'
    else:
        assert window.project is None and window.maximum_edit.text() == '3'
    assert project.saved == [] and controller.calls == []


def test_new_menu_action_starts_fresh_form_instead_of_only_navigating(view, tmp_path):
    window, controller = view
    adopt(window, tmp_path)
    menu = window.file_menu
    assert menu.menuAction().text() == '&File'
    action = next(action for action in menu.actions()
                  if action.text() == '&New project')
    action.trigger()
    assert window.project is None and window.firmware_edit.text() == ''
    assert controller.calls == []


def test_new_project_cannot_reset_an_admitted_job(view, tmp_path, monkeypatch):
    window, controller = view
    project = adopt(window, tmp_path)
    window._start('run', {'config': 'synthetic', 'output_dir': 'synthetic'})
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: pytest.fail('Busy job must not prompt'))
    assert window.new_project() is False
    assert window.project is project and controller.busy
    assert len(controller.calls) == 1


def test_saved_configuration_does_not_mark_a_different_import_selection_as_saved(view, tmp_path, qtbot, monkeypatch):
    window, _ = view
    project = adopt(window, tmp_path)
    window.firmware_edit.setText(str(tmp_path / 'different-build.elf'))
    window.save_configuration()
    qtbot.waitUntil(lambda: not window.busy)
    assert project.saved[0].firmware == project.firmware_path
    seen = []
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: seen.append(True) or QMessageBox.No)
    assert window.new_project() is False and seen


def test_static_selected_elf_check_uses_real_validator_without_runtime_or_project_creation(view, tmp_path, qtbot):
    from firmavex.product.services import prepare_example_project
    from firmavex.product.config import load_config
    window, controller = view
    prepared = prepare_example_project(tmp_path / 'prepared-image')
    config = load_config(prepared['config_file'])
    window._load_fields(config)
    original = config.firmware.read_bytes()
    destination = Path(window.project_dir_edit.text())
    assert window.check_selected_firmware() is True
    qtbot.waitUntil(lambda: not window.busy, timeout=10000)
    assert 'Static ELF check passed' in window.firmware_status.text()
    assert 'no runtime tools or guest execution' in window.validation_text.toPlainText()
    assert 'mps2-an385' in window.validation_text.toPlainText()
    assert window.project is None and not destination.exists() and controller.calls == []
    assert config.firmware.read_bytes() == original
    window.inputs_edit.setText('changed_inputs[0]')
    assert 'has not been checked' in window.firmware_status.text()


def test_static_check_respects_selected_import_image_without_changing_open_project(view, tmp_path, qtbot, monkeypatch):
    window, controller = view
    project = adopt(window, tmp_path)
    selected = tmp_path / 'new-selected.elf'
    window.firmware_edit.setText(str(selected))
    seen = []
    monkeypatch.setattr(ui, 'inspect_elf', lambda config: seen.append(config) or {'synthetic_static_check': True})
    window.check_selected_firmware()
    qtbot.waitUntil(lambda: not window.busy)
    assert seen[0].firmware == selected
    assert window.configuration().firmware == project.firmware_path
    assert project.saved == [] and controller.calls == []


@pytest.mark.parametrize('kind', ['missing', 'raw-bin', 'invalid-binding'])
def test_invalid_selected_firmware_reports_error_without_creating_project_or_dispatch(view, tmp_path, qtbot, kind):
    window, controller = view
    if kind == 'missing':
        window.firmware_edit.setText(str(tmp_path / 'missing.elf'))
    else:
        source = tmp_path / 'image.bin'
        source.write_bytes(b'not compatible ELF bytes')
        window.firmware_edit.setText(str(source))
        if kind == 'invalid-binding': window.inputs_edit.setText('arbitrary + expression')
    window.check_selected_firmware()
    qtbot.waitUntil(lambda: not window.busy)
    assert 'static check failed' in window.firmware_status.text()
    assert 'Static ELF check passed' not in window.firmware_status.text()
    assert not window._checking_selected_firmware and controller.calls == [] and window.project is None


def test_empty_image_check_is_clear_and_not_dispatched(view):
    window, controller = view
    assert not window.check_firmware_button.isEnabled()
    assert window.check_selected_firmware() is False
    assert 'Choose the ELF image' in window.firmware_status.text()
    assert controller.calls == []


def test_static_check_is_background_responsive_and_not_a_cancellable_guest_job(view, qtbot, tmp_path, monkeypatch):
    window, controller = view
    window.firmware_edit.setText(str(tmp_path / 'selected.elf'))
    entered, release = threading.Event(), threading.Event()
    def inspect(config):
        entered.set()
        assert release.wait(2)
        raise ProductError('unsupported_firmware', 'Synthetic static incompatibility')
    monkeypatch.setattr(ui, 'inspect_elf', inspect)
    ticks = []
    QTimer.singleShot(10, lambda: ticks.append(True))
    window.check_selected_firmware()
    try:
        assert window.busy and not window.cancel_button.isEnabled()
        qtbot.waitUntil(lambda: entered.is_set() and bool(ticks), timeout=1000)
        assert window.busy
    finally:
        release.set()
        qtbot.waitUntil(lambda: not window.busy)
    assert 'Synthetic static incompatibility' in window.firmware_status.text()
    assert controller.calls == []


@pytest.mark.parametrize('choice', [QMessageBox.No, QMessageBox.Yes])
def test_explicit_recent_reset_recovers_corrupt_index_without_touching_project_data(view, tmp_path, qtbot, monkeypatch, choice):
    window, controller = view
    project = adopt(window, tmp_path)
    project.root.mkdir()
    saved = project.root / 'result.txt'; saved.write_bytes(b'keep saved data')
    index = window.data_root / 'recent-projects.json'; index.write_bytes(b'{bad JSON')
    window._refresh_recents()
    assert window.clear_recents_button.isEnabled() and not window.open_recent_button.isEnabled()
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: choice)
    assert window.clear_recent_projects() is (choice == QMessageBox.Yes)
    qtbot.waitUntil(lambda: not window.busy)
    if choice == QMessageBox.No:
        assert index.read_bytes() == b'{bad JSON'
    else:
        assert load(window.data_root) == [] and 'shortcuts cleared' in window.recent_hint.text()
    assert window.project is project and saved.read_bytes() == b'keep saved data'
    assert controller.calls == []


def test_successful_export_retains_destination_and_opens_only_after_cleanup(view, tmp_path, qtbot, monkeypatch):
    window, controller = view
    source = tmp_path / 'saved-run'
    destination = tmp_path / 'report with spaces'; destination.mkdir()
    window.active_run = source
    window._start('export', {'run_dir': str(source), 'output_dir': str(destination)}, output=destination)
    controller.result.emit({'success': True, 'firmware_executed': False, 'output_directory': str(destination),
        'files': {'report.md': {'sha256': 'a'*64, 'size_bytes': 1},
                  'evidence.json': {'sha256': 'b'*64, 'size_bytes': 1}}})
    assert not window.open_export_button.isEnabled()
    controller.finish()
    assert window.open_export_button.isEnabled() and window._last_export == destination
    assert str(destination) in window.export_status.text()
    seen = []
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda url: seen.append(url) or True)
    window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy)
    assert len(seen) == 1 and seen[0].isLocalFile() and Path(seen[0].toLocalFile()) == destination
    assert window.active_run == source and len(controller.calls) == 1


@pytest.mark.parametrize('category', ['cancelled', 'output_exists', 'worker_interrupted', 'missing_dependency'])
def test_export_failure_or_cancellation_never_enables_successful_destination(view, tmp_path, category):
    window, controller = view
    source = tmp_path / 'source'; source.mkdir()
    original = source / 'report.md'; original.write_bytes(b'authoritative report')
    window.active_run = source
    window._start('export', {'run_dir': str(source), 'output_dir': str(tmp_path / 'partial')}, output=tmp_path / 'partial')
    controller.finish(error={'category': category, 'message': 'Synthetic failure', 'details': {}})
    assert window._last_export is None and not window.open_export_button.isEnabled()
    assert 'did not complete' in window.export_status.text()
    assert window.active_run == source and original.read_bytes() == b'authoritative report'


def test_open_export_failure_is_actionable_and_never_executes_guest(view, tmp_path, qtbot, monkeypatch):
    window, controller = view
    destination = tmp_path / 'existing-report'; destination.mkdir()
    window._last_export = destination
    window._refresh_enabled()
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda url: False)
    window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy)
    assert 'system file manager could not open' in window.status_label.text()
    assert controller.calls == []


def test_failed_export_result_envelope_is_not_presented_as_complete(view, tmp_path):
    window, controller = view
    window._start('export', {'run_dir': 'synthetic', 'output_dir': 'synthetic'}, output=tmp_path / 'report')
    controller.finish({'success': False})
    assert window._last_export is None and 'did not complete' in window.export_status.text()
    assert not window.open_export_button.isEnabled()


@pytest.mark.parametrize('fault', ['empty', 'missing-path', 'wrong-destination', 'missing-manifest'])
def test_unconfirmed_export_payload_cannot_enable_open_folder(view, tmp_path, fault):
    from tests.desktop.test_batch29_exports import response
    window, controller = view
    destination = tmp_path/'requested-report'
    window._start('export', {}, output=destination)
    record = response(destination)
    if fault == 'empty': record = {}
    elif fault == 'missing-path': record.pop('output_directory')
    elif fault == 'wrong-destination': record['output_directory'] = str(tmp_path/'unrelated')
    else: record.pop('files')
    controller.finish(record)
    assert window._last_export is None and not window.open_export_button.isEnabled()
    assert 'did not complete' in window.export_status.text()


def test_local_export_rejection_clears_previous_success_without_changing_saved_result(view, tmp_path, monkeypatch):
    window, controller = view
    previous = tmp_path/'old-export'; previous.mkdir()
    window._last_export = previous
    window.export_status.setText('Export complete: ' + str(previous))
    window.active_run = tmp_path/'saved-run'
    record = {'outcome': 'configured_failure_observed', 'triggering_input': [2, 1]}
    window.result_record = record
    monkeypatch.setattr(ui.QFileDialog, 'getExistingDirectory', lambda *args: str(Path(ui.__file__).parents[2]))
    window.export_result()
    assert window._last_export is None and not window.open_export_button.isEnabled()
    assert 'did not complete' in window.export_status.text()
    assert window.result_record is record and window.active_run == tmp_path/'saved-run'
    assert previous.is_dir() and not controller.calls


def test_export_start_rejection_leaves_no_pending_or_completed_claim(view, tmp_path, monkeypatch):
    window, controller = view
    monkeypatch.setattr(controller, 'start', lambda *args: False)
    assert not window._start('export', {}, output=tmp_path/'never-created')
    assert window._job is None and window._last_export is None
    assert 'Export not started' in window.export_status.text()
    assert not window.open_export_button.isEnabled()


def test_user_derived_labels_use_plain_text(view):
    window, _ = view
    for label in (window.project_label, window.status_label, window.firmware_status, window.export_status,
                  window.run_path_label, window.outcome_label, window.trigger_label, window.evidence_label):
        assert label.textFormat() == Qt.PlainText
