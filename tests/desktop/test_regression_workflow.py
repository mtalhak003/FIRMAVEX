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
