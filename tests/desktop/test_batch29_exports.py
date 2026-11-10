"""Export confirmation and real worker transport over synthetic saved records."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from firmavex.desktop.workflow import confirmed_export
from tests.product.test_services import project, SyntheticExecutor, factory


def response(destination, backend=False):
    if backend:
        return {'status': 'exported', 'destination': str(destination),
                'files': {'REPORT.md': 'a'*64, 'result.json': 'b'*64}}
    return {'success': True, 'output_directory': str(destination), 'firmware_executed': False,
            'files': {'report.md': {'sha256': 'a'*64, 'size_bytes': 1},
                      'evidence.json': {'sha256': 'b'*64, 'size_bytes': 2}}}


@pytest.mark.parametrize('backend', [False, True])
def test_confirmation_uses_worker_destination_and_manifest_without_filesystem_work(tmp_path, backend):
    destination = tmp_path/'new report with spaces'
    value = response(destination, backend)
    before = deepcopy(value)
    assert confirmed_export(value, destination, backend=backend) == destination
    assert value == before and not destination.exists()


@pytest.mark.parametrize('backend', [False, True])
@pytest.mark.parametrize('fault', ['missing-status', 'failed', 'missing-path', 'wrong-path', 'relative-path',
    'control-path', 'no-request', 'missing-files', 'wrong-report-case', 'bad-digest'])
def test_malformed_or_unrelated_export_reply_cannot_confirm_completion(tmp_path, backend, fault):
    destination = tmp_path/'requested'
    record = response(destination, backend)
    status = 'status' if backend else 'success'
    path = 'destination' if backend else 'output_directory'
    requested = destination
    if fault == 'missing-status': record.pop(status)
    elif fault == 'failed': record[status] = 'failed' if backend else False
    elif fault == 'missing-path': record.pop(path)
    elif fault == 'wrong-path': record[path] = str(tmp_path/'different')
    elif fault == 'relative-path': record[path] = 'relative-report'
    elif fault == 'control-path': record[path] = str(destination)+'\n'
    elif fault == 'no-request': requested = None
    elif fault == 'missing-files': record['files'] = {}
    elif fault == 'wrong-report-case':
        name = 'REPORT.md' if backend else 'report.md'
        record['files'][name.swapcase()] = record['files'].pop(name)
    else:
        if backend: record['files']['REPORT.md'] = 'invalid'
        else: record['files']['report.md']['sha256'] = 'invalid'
    assert confirmed_export(record, requested, backend=backend) is None


@pytest.mark.parametrize('value', [True, -1, '1', None])
def test_arm_export_file_sizes_require_nonnegative_exact_integers(tmp_path, value):
    record = response(tmp_path)
    record['files']['report.md']['size_bytes'] = value
    assert confirmed_export(record, tmp_path) is None


def test_confirmation_does_not_accept_truthy_success_or_traversal_spelling(tmp_path):
    value = response(tmp_path)
    value['success'] = 1
    assert confirmed_export(value, tmp_path) is None
    value['success'] = True
    value['output_directory'] = str(tmp_path/'unused'/'..')
    assert confirmed_export(value, tmp_path) is None


def test_real_supervised_arm_export_updates_gui_and_preserves_source_archive(qtbot, tmp_path, project, monkeypatch):
    from firmavex.desktop.window import MainWindow
    from firmavex.product import services
    from tests.product.test_services import archive_bytes
    config, _ = project
    source = tmp_path/'synthetic-arm-run'
    record = services.run_project(config, source, _executor_factory=factory(SyntheticExecutor()))
    assert record['measurement_mode'] == 'synthetic_test'
    before = archive_bytes(source)
    window = MainWindow(data_root=tmp_path/'desktop-data')
    qtbot.addWidget(window)
    window.active_run = source
    monkeypatch.setattr('firmavex.desktop.window.QFileDialog.getExistingDirectory', lambda *args: str(tmp_path))
    window.export_result()
    qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert window._last_export is not None, window.validation_text.toPlainText()
    destination = window._last_export
    assert window.open_export_button.isEnabled()
    assert 'Export complete' in window.export_status.text()
    assert (destination/'report.md').is_file() and (destination/'SHA256SUMS').is_file()
    exported = json.loads((destination/'evidence.json').read_text())
    assert exported['result']['measurement_mode'] == 'synthetic_test'
    assert archive_bytes(source) == before
    window.close()


def test_real_supervised_backend_export_uses_actual_report_filename_and_checksums(qtbot, tmp_path, monkeypatch):
    from firmavex.desktop.universal import UniversalWindow
    from tests.product.test_verification import saved, archive
    source = Path(saved(tmp_path/'synthetic-backend-run'))
    before = archive(source)
    window = UniversalWindow(data_root=tmp_path/'backend-data')
    qtbot.addWidget(window)
    window.active_run = source
    window.record = json.loads((source/'result.json').read_text())
    monkeypatch.setattr('firmavex.desktop.universal.QFileDialog.getExistingDirectory', lambda *args: str(tmp_path))
    window.export()
    qtbot.waitUntil(lambda: not window.busy, timeout=15000)
    assert 'Export complete' in window.status_label.text(), window.operation_view.toPlainText()
    destination = Path(window._output)
    assert 'REPORT.md' in window.export_feedback_label.text()
    manifest = json.loads((destination/'checksums.json').read_text())
    assert {'REPORT.md', 'result.json'} <= manifest.keys()
    for name, digest in manifest.items():
        assert hashlib.sha256((destination/name).read_bytes()).hexdigest() == digest
    assert json.loads((destination/'result.json').read_text())['evidence']['measurement_mode'] == 'synthetic_test'
    assert archive(source) == before
    window.close()
