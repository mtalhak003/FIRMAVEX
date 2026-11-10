"""Backend presentation checks; synthetic controller feedback is not native evidence."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from tests.desktop.test_universal import Controller, ready, select, view


@pytest.mark.parametrize('profile,architecture,tool,placeholder', [
    ('cortex-m3-mps2', 'armv7-m', 'qemu-system-arm', 'ARM project'),
    ('riscv32-virt', 'rv32im', 'qemu-system-riscv32', 'RV32IM ELF'),
    ('verilog-icarus', 'verilog', 'iverilog', 'testbench'),
])
def test_backend_readiness_and_compatible_input_are_visible_before_dispatch(view, profile, architecture, tool, placeholder):
    window, controller = view
    select(window, profile)
    text = window.runtime_status_label.text()
    assert 'Not checked' in text and architecture in text and tool in text
    assert 'not native qualification' in text
    assert placeholder in window.source_edit.placeholderText()
    assert window.runtime_status_label.textFormat() == Qt.TextFormat.PlainText
    assert not window.run_button.isEnabled() and not controller.calls


def test_missing_tools_keep_persistent_actionable_not_ready_state(view):
    window, controller = view
    select(window, 'verilog-icarus')
    window.check_runtime()
    assert 'Checking verilog' in window.runtime_status_label.text()
    controller.finish({'status': 'missing_dependency', 'error': {'message': 'Icarus is missing'}})
    assert 'Icarus is missing' in window.runtime_status_label.text()
    assert 'setup/repair' in window.runtime_status_label.text()
    assert not window._ready and not window.run_button.isEnabled()
    assert window.progress_bar.format() == 'Stopped'
    window.prepare_example()
    controller.finish({'source': '/trusted/counter.v', 'execution_performed': False})
    window.trust_box.setChecked(True)
    assert 'Icarus is missing' in window.runtime_status_label.text()
    assert not window.run_button.isEnabled()
    assert [row[0] for row in controller.calls] == ['backend_check', 'backend_prepare']


def test_runtime_rejection_is_not_relabelled_as_availability_or_qualification(view):
    window, controller = view
    ready(window, controller)
    window.check_runtime()
    controller.finish(error={'category': 'unsupported_platform', 'message': 'Unqualified runtime identity'})
    assert not window._ready
    assert 'Unqualified runtime identity' in window.runtime_status_label.text()
    assert 'Next:' in window.runtime_status_label.text()
    assert not window.run_button.isEnabled()
    assert 'failed' in window.job_state_label.text()


def test_busy_runtime_check_does_not_invalidate_the_active_operation(view):
    window, controller = view
    ready(window, controller)
    before = window.runtime_status_label.text()
    window._start('backend_export', {})
    calls = list(controller.calls)
    window.check_runtime()
    assert window.runtime_status_label.text() == before and window._ready
    assert controller.calls == calls
    controller.finish(error={'category': 'io_error', 'message': 'Write refused'})
    assert window.runtime_status_label.text() == before


def test_switching_target_clears_readiness_and_never_auto_executes(view):
    window, controller = view
    ready(window, controller)
    assert 'Last check: tools available' in window.runtime_status_label.text()
    assert 'synthetic test feedback' in window.runtime_status_label.text()
    select(window, 'riscv32-virt')
    assert not window._ready and 'Not checked for rv32im' in window.runtime_status_label.text()
    assert len(controller.calls) == 1


def test_selecting_an_arm_context_invalidates_visible_readiness_even_for_same_target(view, tmp_path):
    window, controller = view
    ready(window, controller)
    context = {'source': str(tmp_path/'project.json'), 'project': str(tmp_path/'project'),
               'sha256': 'a'*64, 'firmware_sha256': 'b'*64}
    window.select_arm_context(context)
    assert not window._ready and window.runtime_status_label.text().startswith('Not checked')
    assert not window.trust_box.isChecked() and len(controller.calls) == 1


def test_recorded_outcome_waits_for_idle_before_terminal_presentation(view, tmp_path):
    window, controller = view
    window._start('backend_execute', {}, output=tmp_path/'run')
    controller.event.emit({'payload': {'stage': 'finished', 'status': 'passed'}})
    assert 'Testing selected backend' in window.job_state_label.text()
    assert window.progress_bar.maximum() == 0
    controller.result.emit({'status': 'passed', 'evidence': {'measurement_mode': 'synthetic_test'}})
    assert 'Final record received' in window.job_state_label.text()
    assert not window.run_button.isEnabled() and window.progress_bar.maximum() == 0
    controller.busy = False
    controller.busy_changed.emit(False)
    controller.idle.emit()
    assert 'Recorded outcome: passed' in window.job_state_label.text()
    assert 'not a general correctness claim' in window.job_state_label.text()
    assert window.progress_bar.value() == 1 and window.progress_bar.format() == 'Finished'


def test_cancel_request_remains_visible_despite_late_finished_progress(view, tmp_path):
    window, controller = view
    window._start('backend_execute', {}, output=tmp_path/'run')
    window.cancel()
    status = window.status_label.text()
    controller.event.emit({'payload': {'stage': 'finished', 'message': 'Backend finished'}})
    window._refresh()
    assert window.status_label.text() == status
    assert 'Cancellation requested' in window.job_state_label.text()
    assert not window.cancel_button.isEnabled() and not window.run_button.isEnabled()
    controller.finish(error={'category': 'cancelled', 'message': 'Stopped after owned cleanup'})
    assert 'cancelled' in window.job_state_label.text()
    assert window.progress_bar.format() == 'Stopped'


def test_infrastructure_outcome_is_terminal_without_being_presented_as_success(view, tmp_path):
    window, controller = view
    window._start('backend_execute', {}, output=tmp_path/'run')
    record = {'status': 'infrastructure_failure', 'evidence': {'cleanup_verified': False}}
    controller.finish(record)
    assert window.record == record
    assert 'Recorded outcome: infrastructure_failure' in window.job_state_label.text()
    assert window.progress_bar.format() == 'Stopped'
    assert not window.reproduce_button.isEnabled()


def test_rejected_start_preserves_prior_saved_result_and_clear_state(view, tmp_path, monkeypatch):
    window, controller = view
    prior = {'status': 'triggered', 'evidence': {'measurement_mode': 'synthetic_test'}}
    window.active_run, window.record = tmp_path/'old', prior
    window.result_view.setPlainText('Prior JSON')
    window.summary_view.setPlainText('Prior explanation')
    window.result_context_label.setText('Prior saved context')
    monkeypatch.setattr(controller, 'start', lambda *args: False)
    assert not window._start('backend_execute', {}, output=tmp_path/'new')
    assert window.active_run == tmp_path/'old' and window.record == prior
    assert window.result_view.toPlainText() == 'Prior JSON'
    assert window.summary_view.toPlainText() == 'Prior explanation'
    assert window.result_context_label.text() == 'Prior saved context'
    assert 'Operation not started' in window.job_state_label.text()
    assert 'Operation not started' in window.status_label.text()
    assert window._job is None and not controller.busy


def test_export_success_shows_exact_destination_and_index_count_without_changing_result(view, tmp_path):
    window, controller = view
    prior = {'status': 'passed', 'evidence': {'measurement_mode': 'synthetic_test'}}
    window.active_run, window.record = tmp_path/'run', prior
    window.result_view.setPlainText('Saved evidence')
    destination = str(tmp_path/'report <literal>')
    window._start('backend_export', {}, output=Path(destination))
    controller.finish({'status': 'exported', 'destination': destination,
                       'files': {'REPORT.md': 'a'*64, 'result.json': 'b'*64}})
    assert destination in window.export_feedback_label.text()
    assert '2 files listed in checksums.json' in window.export_feedback_label.text()
    assert 'REPORT.md' in window.export_feedback_label.text()
    assert window.export_feedback_label.textFormat() == Qt.TextFormat.PlainText
    assert window.active_run == tmp_path/'run' and window.record == prior
    assert window.result_view.toPlainText() == 'Saved evidence'


@pytest.mark.parametrize('record', [{'status': 'exported'}, {'destination': '/tmp/not-confirmed'}, {'status': 'failed'}])
def test_unconfirmed_export_response_never_claims_a_successful_export(view, record):
    window, controller = view
    window._start('backend_export', {})
    controller.finish(record)
    assert 'did not confirm' in window.export_feedback_label.text()
    assert 'not confirmed' in window.status_label.text()
    assert window.progress_bar.format() == 'Stopped'


@pytest.mark.parametrize('category', ['cancelled', 'io_error', 'invalid_input'])
def test_export_error_preserves_saved_result_and_gives_safe_retry_guidance(view, tmp_path, category):
    window, controller = view
    previous = {'status': 'passed', 'evidence': {}}
    window.active_run, window.record = tmp_path/'run', previous
    window._start('backend_export', {}, output=tmp_path/'export')
    controller.finish(error={'category': category, 'message': 'Destination unavailable'})
    assert 'Destination unavailable' in window.export_feedback_label.text()
    assert 'partial files' in window.export_feedback_label.text()
    assert 'new folder' in window.export_feedback_label.text()
    assert 'Next:' in window.operation_view.toPlainText() or 'Next:' in window.status_label.text()
    assert window.active_run == tmp_path/'run' and window.record == previous
    assert window.export_button.isEnabled()


@pytest.mark.parametrize('command', ['backend_export', 'backend_check'])
def test_rejected_administrative_start_has_no_stuck_pending_feedback(view, monkeypatch, command):
    window, controller = view
    monkeypatch.setattr(controller, 'start', lambda *args: False)
    if command == 'backend_check': window.check_runtime()
    else: assert not window._start(command, {})
    assert not window.busy
    label = window.runtime_status_label if command == 'backend_check' else window.export_feedback_label
    assert 'not started' in label.text()
    assert 'in progress' not in label.text() and 'Checking' not in label.text()


def test_exported_response_for_a_different_destination_is_not_confirmed(view, tmp_path):
    from tests.desktop.test_batch29_exports import response
    window, controller = view
    window._start('backend_export', {}, output=tmp_path/'requested')
    controller.finish(response(tmp_path/'different', backend=True))
    assert 'did not confirm' in window.export_feedback_label.text()
    assert window.progress_bar.format() == 'Stopped'


def test_cancel_request_racing_completed_result_preserves_recorded_outcome(view, tmp_path):
    window, controller = view
    window._start('backend_execute', {}, output=tmp_path/'run')
    window.cancel()
    record = {'status': 'passed', 'evidence': {'measurement_mode': 'synthetic_test'}}
    controller.finish(record)
    assert window.record == record
    assert 'Cancellation was requested.' in window.job_state_label.text()
    assert 'Recorded outcome: passed' in window.job_state_label.text()
    assert window.progress_bar.format() == 'Finished'


def test_empty_result_does_not_present_a_successful_execution(view, tmp_path):
    window, controller = view
    window._start('backend_execute', {}, output=tmp_path/'run')
    controller.finish({})
    assert window.record == {} and 'unknown' in window.job_state_label.text()
    assert window.progress_bar.format() == 'Stopped'
    assert not window.reproduce_button.isEnabled()


def test_saved_result_navigation_keeps_readable_tabs_and_scrollable_controls(view, qtbot):
    window, controller = view
    window.resize(760, 580)
    qtbot.waitUntil(lambda: window.history_scroll.viewport().width() > 0)
    assert window.history_scroll.widgetResizable()
    assert window.history_scroll.widget().isAncestorOf(window.history)
    assert window.tabs.usesScrollButtons() and window.tabs.elideMode() == Qt.TextElideMode.ElideNone
    assert window.tabs.tabText(0) == 'Summary'
    assert controller.calls == []  # Navigation/layout never dispatches work.
