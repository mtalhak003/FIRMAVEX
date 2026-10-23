"""Synthetic worker UI reproductions; native acceptance is tested separately."""
import copy
from pathlib import Path

import pytest

from tests.desktop.test_universal import view
from tests.product.test_regression import setup_set
from firmavex.product import regression


def displayed_run(window, controller, tmp_path, backend):
    record = {'status': 'passed', 'evidence': {'measurement_mode': 'synthetic_test', 'cleanup_verified': True,
        'admission': {'profile': {'id': backend}, 'attempt_id': 'prior-run', 'values': [0, 0] if backend == 'riscv32-virt' else []}}}
    window.inspect(tmp_path / 'prior-run')
    controller.finish(record)
    return record


@pytest.mark.parametrize('backend', ['cortex-m3-mps2', 'riscv32-virt', 'verilog-icarus'])
def test_regression_administration_preserves_individual_evidence(view, tmp_path, backend):
    window, controller = view
    record = displayed_run(window, controller, tmp_path, backend)
    context, evidence, summary = window.result_context_label.text(), window.result_view.toPlainText(), window.summary_view.toPlainText()
    window.regression_panel.start('list', root=str(tmp_path / 'sets'))
    controller.finish({'entries': [], 'execution_performed': False})
    assert window.result_view.toPlainText() == evidence
    assert window.summary_view.toPlainText() == summary
    assert window.result_context_label.text() == context and window.record == record
    assert window.active_run == tmp_path / 'prior-run'


@pytest.mark.parametrize('backend', ['cortex-m3-mps2', 'riscv32-virt', 'verilog-icarus'])
def test_regression_error_stays_in_context_and_preserves_evidence(view, tmp_path, backend):
    window, controller = view
    displayed_run(window, controller, tmp_path, backend)
    before = (window.result_context_label.text(), window.result_view.toPlainText(), window.summary_view.toPlainText())
    panel = window.regression_panel
    panel.start('export', directory=str(tmp_path / 'missing'), output_dir=str(tmp_path / 'report'))
    controller.finish(error={'category': 'invalid_input', 'message': 'Reports must be outside original evidence storage', 'details': {}})
    assert window.tabs.currentWidget() is panel
    assert before == (window.result_context_label.text(), window.result_view.toPlainText(), window.summary_view.toPlainText())
    assert 'new report folder' in panel.report.toPlainText()
    assert not panel.trust.isChecked() and panel.pending is None


def test_partial_regression_error_recovers_recorded_summary_without_rerun(view, tmp_path):
    window, controller = view
    _, _, saved = setup_set(tmp_path)
    partial = {'kind': 'firmavex_regression_run', 'schema_version': 1, 'set_id': saved['set_id'],
        'revision': saved['revision'], 'name': saved['name'], 'run_id': 'a' * 32, 'state': 'cancelled',
        'directory': str(Path(saved['directory']) / 'runs' / 'partial'), 'entries': [],
        'counts': {'passed': 0, 'failed': 0, 'cancelled': 1, 'infrastructure_error': 0, 'not_run': 0, 'unavailable': 0},
        'scope': 'Synthetic partial presentation only'}
    entry = saved['entries'][0]
    partial['entries'] = [{**entry, 'status': 'cancelled', 'category': 'cancelled', 'evidence': None, 'diagnostic': 'cancelled'}]
    panel = window.regression_panel
    panel.start('execute', directory=saved['directory'], output_dir=partial['directory'], trust='trusted_project')
    calls = copy.deepcopy(controller.calls)
    controller.finish(error={'category': 'cancelled', 'message': 'Execution interrupted', 'details': {'partial_result': partial}})
    assert panel.current_run == partial
    assert panel.results.item(0, 2).text() == 'cancelled'
    assert window.tabs.currentWidget() is panel
    assert controller.calls == calls and not panel.trust.isChecked()


def test_regression_vector_accepts_normal_form_decimal_notation(view, tmp_path):
    window, controller = view
    config, _, _ = setup_set(tmp_path, profile='riscv32-virt')
    window._apply_configuration(config)
    panel = window.regression_panel
    panel.add()
    panel.entries.item(0, 2).setText('08, 01')
    assert panel._values()[0]['values'] == [8, 1]
    assert not controller.calls


@pytest.mark.parametrize('values', ['-1, 0', '4294967296, 0', '1, 2, 3', 'x' * 129],
                         ids=['negative', 'overflow', 'extra-value', 'oversized'])
def test_invalid_regression_vectors_get_local_recovery_without_dispatch(view, tmp_path, values):
    window, controller = view
    config, _, _ = setup_set(tmp_path, profile='riscv32-virt')
    window._apply_configuration(config)
    panel = window.regression_panel
    panel.name.setText('valid set name'); panel.add()
    panel.entries.item(0, 2).setText(values)
    panel.save()
    assert not controller.calls
    assert window.tabs.currentWidget() is panel
    assert 'exactly two uint32' in panel.report.toPlainText()
    assert 'Save a new revision' in panel.report.toPlainText()
    assert not panel.trust.isChecked()


def test_verilog_input_values_are_rejected_without_dispatch(view, tmp_path):
    window, controller = view
    config, _, _ = setup_set(tmp_path)
    window._apply_configuration(config)
    panel = window.regression_panel; panel.add()
    panel.entries.item(0, 2).setText('1,2')
    panel.save()
    assert not controller.calls
    assert 'leave the values cell empty' in panel.report.toPlainText()


@pytest.mark.parametrize('partial', [None, {}, {'kind': 'firmavex_regression_run'}, 'unsupported'])
def test_missing_partial_records_do_not_invent_outcomes(view, tmp_path, partial):
    window, controller = view
    panel = window.regression_panel
    panel.start('execute', directory='selected', output_dir=str(tmp_path / 'new-run'), trust='trusted_project')
    controller.finish(error={'category': 'worker_interrupted', 'message': 'Worker interrupted', 'details': {'partial_result': partial}})
    assert panel.current_run is None and panel.results.rowCount() == 0
    assert str(tmp_path / 'new-run') in panel.report.toPlainText()
    assert 'No validated partial summary' in panel.report.toPlainText()
    assert 'Inspect retained partial entries' in panel.report.toPlainText()
    assert not panel.trust.isChecked()
