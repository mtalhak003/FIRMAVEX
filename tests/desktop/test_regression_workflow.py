"""Cross-platform Qt workflow over real manifests and synthetic worker transport."""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QTableWidgetItem

from tests.desktop.test_universal import view
from tests.product.test_regression import setup_set
from firmavex.product import regression, workspace


def test_open_test_set_never_executes_or_grants_consent(view, tmp_path):
    window, controller = view
    _, _, saved = setup_set(tmp_path)
    panel = window.regression_panel
    panel.start('open', directory=saved['directory'])
    controller.finish(regression.open_set(saved['directory']))
    assert panel.entries.rowCount() == 3 and not panel.trust.isChecked()
    assert not panel.run_button.isEnabled() and not panel.dirty
    assert panel.saved['revision'] in panel.context.text()
    assert [c[0] for c in controller.calls] == ['backend_regression']
    assert panel.report.isReadOnly()


def test_edit_reorder_save_and_explicit_execute(view, tmp_path):
    window, controller = view
    config, entries, saved = setup_set(tmp_path)
    panel = window.regression_panel
    panel.start('open', directory=saved['directory'])
    controller.finish(regression.open_set(saved['directory']))
    panel.trust.setChecked(True)
    assert panel.run_button.isEnabled()
    panel.entries.item(0, 0).setText('edited test')
    assert panel.dirty and not panel.trust.isChecked() and not panel.run_button.isEnabled()
    panel.entries.selectRow(0); panel.move(1)
    assert panel._values()[1]['id'] == entries[0]['id']
    panel.save()
    payload = controller.calls[-1][1]
    assert payload['parent'] == saved['directory']
    revised = regression.operation(payload)
    controller.finish(revised)
    panel.trust.setChecked(True); panel.run_button.click()
    assert controller.calls[-1][1]['action'] == 'execute'
    assert controller.calls[-1][1]['trust'] == 'trusted_project'
    assert controller.calls[-1][1]['directory'] == revised['directory']
    assert not panel.trust.isChecked()
    assert not panel.entries.isEnabled()


def test_add_selected_config_preserves_entry_id_when_replaced(view, tmp_path):
    window, controller = view
    config, _, saved = setup_set(tmp_path)
    panel = window.regression_panel
    window._saved_configuration = config
    panel.add()
    identity = panel._values()[0]['id']
    panel.entries.selectRow(0); panel.replace()
    assert panel._values()[0]['id'] == identity
    for _ in range(30): panel.add()
    assert panel.entries.rowCount() == 16
    assert not controller.calls


def test_results_show_counts_and_explicit_evidence_navigation(view, tmp_path, monkeypatch):
    from tests.product.test_regression import fake_executor, output
    window, controller = view
    _, _, saved = setup_set(tmp_path)
    fake_executor(monkeypatch)
    run = regression.execute(saved['directory'], output(saved), trust='trusted_project')
    panel = window.regression_panel
    panel.start('inspect', directory=run['directory'])
    controller.finish(regression.inspect(run['directory']))
    assert panel.results.rowCount() == 3
    assert panel.results.item(1, 2).text() == 'failed'
    assert '"passed": 2' in panel.report.toPlainText()
    assert not controller.busy
    panel.open_entry(0, 0)
    assert controller.calls[-1][0] == 'backend_inspect'
    assert Path(controller.calls[-1][1]['run_dir']).name == run['entries'][0]['id']


def test_list_named_sets_and_clear_previous_without_execution(view, tmp_path):
    window, controller = view
    _, _, saved = setup_set(tmp_path)
    panel = window.regression_panel
    panel.start('list', root=str(tmp_path / 'sets'))
    controller.finish(regression.listing(tmp_path / 'sets'))
    assert panel.saved_sets.currentText().startswith('My set')
    assert panel.saved is None and not panel.trust.isChecked()
    panel.open_listed()
    assert controller.calls[-1][1]['action'] == 'open'
    controller.finish(regression.open_set(saved['directory']))
    panel.previous_run = {'directory': 'old', 'set_id': saved['set_id']}
    panel.trust.setChecked(True)
    panel.clear_previous()
    assert panel.previous_run is None and not panel.trust.isChecked()


def test_dashboard_verification_comparison_and_export_workflow(view, tmp_path, monkeypatch):
    from tests.product.test_regression_review import session
    from firmavex.product import regression_review
    from firmavex.desktop import regression as regression_ui
    window, controller = view
    saved, run = session(tmp_path, monkeypatch)
    panel = window.regression_panel
    panel.saved = saved
    panel.refresh_dashboard()
    payload = controller.calls[-1][1]
    controller.finish(regression.operation(payload))
    assert panel.sessions.rowCount() == 1
    assert 'configuration' in panel.dashboard_revisions.accessibleName().lower()
    panel.dashboard_search.setText('no-match')
    assert panel.sessions.isRowHidden(0)
    panel.dashboard_search.clear()
    panel.open_dashboard_session(0, 0)
    controller.finish(regression.inspect(run['directory']))
    assert panel.current_run['run_id'] == run['run_id']
    panel.verify_current()
    assert not panel.verify_button.isEnabled()
    assert panel.results.item(0, 4).text() == 'unverified'
    controller.finish(regression.operation(controller.calls[-1][1]))
    assert panel.aggregate_review['status'] == 'verified'
    assert panel.artifacts.rowCount() == 6
    assert panel.results.item(0, 4).text() == 'verified'
    panel.previous_run = regression.inspect(run['directory'])
    panel.compare()
    assert panel.comparison.rowCount() == 0
    controller.finish(regression.operation(controller.calls[-1][1]))
    assert panel.comparison.item(0, 3).text() == 'same'
    monkeypatch.setattr(regression_ui.QFileDialog, 'getExistingDirectory', lambda *a: str(tmp_path))
    panel.export_report()
    assert panel.results.item(0, 4).text() == 'unverified'
    payload = controller.calls[-1][1]
    assert payload['action'] == 'export'
    controller.finish(regression.operation(payload))
    assert 'Fresh verification: verified' in panel.report.toPlainText()
    assert sorted(p.name for p in Path(payload['output_dir']).iterdir()) == ['regression.txt']
    assert not panel.trust.isChecked()


def test_native_failure_context_preserves_retained_launch_error(tmp_path, monkeypatch):
    import json
    from firmavex.backends.engine import _write
    from tests.product.test_regression_review import session
    from tests.desktop.test_real_universal import _regression_failure_details
    _, run = session(tmp_path, monkeypatch)
    record_path = Path(run['directory']) / run['entries'][0]['evidence'] / 'result.json'
    record = json.loads(record_path.read_text())
    record['status'] = 'infrastructure_failure'
    record['evidence']['error'] = 'OSError: [WinError 267] The directory name is invalid'
    _write(record_path, record)
    details = json.loads(_regression_failure_details(run, 'native execution stopped'))
    assert 'WinError 267' in details['retained_errors'][0]['error']
    assert details['retained_errors'][0]['status'] == 'infrastructure_failure'
    assert len(_regression_failure_details(run, 'x' * 100000)) < 10000
