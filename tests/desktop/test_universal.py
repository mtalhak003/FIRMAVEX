"""Synthetic presentation tests; native execution lives in test_real_backends."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal, Qt

from firmavex.desktop.universal import UniversalWindow


class Controller(QObject):
    event = Signal(dict)
    result = Signal(dict)
    error = Signal(dict)
    busy_changed = Signal(bool)
    idle = Signal()

    def __init__(self):
        super().__init__()
        self.busy, self.calls, self.cancelled = False, [], False

    def start(self, command, payload):
        if self.busy:
            return False
        self.calls.append((command, payload))
        self.busy = True
        self.busy_changed.emit(True)
        return True

    def cancel(self):
        self.cancelled = self.busy
        return self.busy

    def shutdown(self):
        self.cancel()
        return not self.busy

    def finish(self, record=None, error=None):
        if record is not None:
            self.result.emit(record)
        if error is not None:
            self.error.emit(error)
        self.busy = False
        self.busy_changed.emit(False)
        self.idle.emit()


@pytest.fixture
def view(qtbot, tmp_path):
    controller = Controller()
    window = UniversalWindow(controller, data_root=tmp_path / "user data")
    qtbot.addWidget(window)
    window.show()
    yield window, controller
    if controller.busy:
        controller.finish(error={"category": "cancelled", "message": "synthetic cleanup"})
    window.close()


def select(window, profile):
    window.profile_combo.setCurrentIndex(window.profile_combo.findData(profile))


def ready(window, controller):
    window.check_runtime()
    controller.finish({"status": "tools_available", "measurement_mode": "synthetic_test"})


def test_opening_workspace_or_history_never_dispatches(view):
    window, controller = view
    window.refresh_history()
    assert not controller.calls
    assert window.profile_combo.count() == 3
    assert not window.run_button.isEnabled()
    assert not window.reproduce_button.isEnabled()
    assert "not a security sandbox" in window.notice.text()


@pytest.mark.parametrize("profile,values_visible,timeout_enabled,capability", [
    ("cortex-m3-mps2", False, False, "search"),
    ("riscv32-virt", True, True, "symbol-observation"),
    ("verilog-icarus", False, True, "testbench"),
])
def test_controls_follow_capabilities(view, profile, values_visible, timeout_enabled, capability):
    window, _ = view
    select(window, profile)
    assert window.values_edit.isVisible() == values_visible
    assert window.timeout_spin.isEnabled() == timeout_enabled
    assert capability in window.capability_label.text()
    assert "native qualification" in window.capability_label.text()


def test_readiness_never_runs_a_guest_and_missing_tools_stay_unavailable(view):
    window, controller = view
    select(window, "verilog-icarus")
    window.check_runtime()
    assert controller.calls == [("backend_check", {"profile": "verilog-icarus"})]
    controller.finish({"status": "missing_dependency", "reason": "Install Icarus"})
    assert not window._ready and not window.run_button.isEnabled()
    assert "nothing executed" in window.status_label.text()


def test_failed_check_error_cannot_retain_old_ready_state(view):
    window, controller = view
    ready(window, controller)
    window.check_runtime()
    controller.finish(error={"category": "missing_dependency", "message": "GDB missing"})
    assert not window._ready and "GDB missing" in window.status_label.text()


@pytest.mark.parametrize("profile,source", [
    ("cortex-m3-mps2", "project.json"), ("riscv32-virt", "user.elf"), ("verilog-icarus", "counter.v"),
])
def test_untrusted_user_input_is_rejected_before_dispatch(view, profile, source):
    window, controller = view
    select(window, profile)
    ready(window, controller)
    window.source_edit.setText(source)
    before = len(controller.calls)
    window.execute()
    assert len(controller.calls) == before
    assert "untrusted" in window.status_label.text()


def test_readiness_required_even_when_a_trust_box_is_checked(view):
    window, controller = view
    window.source_edit.setText("project.json")
    window.trust_box.setChecked(True)
    window.execute()
    assert not controller.calls and "readiness" in window.status_label.text()


def test_valid_rv_request_preserves_values_limits_and_explicit_trust(view):
    window, controller = view
    select(window, "riscv32-virt")
    ready(window, controller)
    window.source_edit.setText("firmware with spaces.elf")
    window.trust_box.setChecked(True)
    window.values_edit.setText("0xffffffff, 2")
    window.timeout_spin.setValue(17.5)
    window.artifact_spin.setValue(3)
    window.execute()
    command, payload = controller.calls[-1]
    assert command == "backend_execute"
    assert payload["trust"] == "trusted_project"
    assert payload["request"]["values"] == [0xFFFFFFFF, 2]
    assert payload["request"]["limits"]["timeout_seconds"] == 17.5
    assert payload["request"]["limits"]["artifact_bytes"] == 3 * 1024 * 1024
    assert Path(payload["output_dir"]).parent == window.data_root / "runs"
    assert not window.profile_combo.isEnabled() and window.cancel_button.isEnabled()


@pytest.mark.parametrize("values", ["-1, 0", "4294967296, 0", "1", "1 2 3", "one, two", ""])
def test_invalid_rv_vectors_do_not_dispatch(view, values):
    window, controller = view
    select(window, "riscv32-virt")
    ready(window, controller)
    window.source_edit.setText("firmware.elf")
    window.trust_box.setChecked(True)
    window.values_edit.setText(values)
    before = len(controller.calls)
    window.execute()
    assert len(controller.calls) == before
    assert "invalid_input" in window.status_label.text()


@pytest.mark.parametrize("source", [{"path": "/owned/counter.v"}, "/owned/counter.v"])
def test_builtin_preparation_marks_only_the_exact_returned_source_trusted(view, source):
    window, controller = view
    select(window, "verilog-icarus")
    window.prepare_example()
    assert controller.calls[-1][0] == "backend_prepare"
    controller.finish({"source": source, "execution_performed": False})
    assert window.source_edit.text() == "/owned/counter.v"
    assert not window.trust_box.isChecked()
    window.trust_box.setChecked(True)
    assert window._trust() == "trusted_example"
    assert not window._ready and "no target execution" in window.status_label.text()
    window.source_edit.setText("/unknown/counter.v")
    assert not window.trust_box.isChecked() and window._example_source is None


def test_arm_example_uses_project_configuration_not_an_elf_path(view):
    window, controller = view
    window.prepare_example()
    controller.finish({"config_file": "/owned/project.json", "firmware_file": "/owned/example.elf"})
    assert window.source_edit.text() == "/owned/project.json"


def test_prepared_example_still_requires_runtime_trust_acknowledgement(view):
    window, controller = view
    select(window, "verilog-icarus")
    ready(window, controller)
    window.prepare_example()
    controller.finish({"source": "/owned/counter.v", "execution_performed": False})
    before = len(controller.calls)
    window.execute()
    assert len(controller.calls) == before and not window.run_button.isEnabled()
    window.trust_box.setChecked(True)
    window.execute()
    assert controller.calls[-1][0] == "backend_execute"
    assert controller.calls[-1][1]["trust"] == "trusted_example"


def test_switching_profile_invalidates_trust_and_readiness(view):
    window, controller = view
    ready(window, controller)
    window.source_edit.setText("project.json")
    window.trust_box.setChecked(True)
    select(window, "verilog-icarus")
    assert not window._ready and not window.trust_box.isChecked()
    assert window.source_edit.text() == ""


def test_result_failure_is_not_labeled_as_success_or_reproducible(view):
    window, controller = view
    window._start("backend_execute", {}, output=Path("/owned/failed"))
    controller.finish({"status": "infrastructure_failure", "evidence": {"error": "timeout", "cleanup_verified": False}})
    assert window.record["status"] == "infrastructure_failure"
    assert "infrastructure_failure" in window.status_label.text()
    assert not window.reproduce_button.isEnabled() and window.export_button.isEnabled()
    assert "timeout" in window.result_view.toPlainText()


def test_saved_record_is_read_only_and_reproduction_requires_new_trust(view):
    window, controller = view
    window.source_edit.setText("/owned/counter.v")
    window.trust_box.setChecked(True)
    window.inspect(Path("/saved/run"))
    assert controller.calls[-1] == ("backend_inspect", {"run_dir": str(Path("/saved/run"))})
    controller.finish({"status": "triggered", "evidence": {"measurement_mode": "synthetic_test"}})
    assert not window.trust_box.isChecked() and not window.reproduce_button.isEnabled()
    window.trust_box.setChecked(True)
    assert window.reproduce_button.isEnabled()
    window.reproduce()
    command, payload = controller.calls[-1]
    assert command == "backend_reproduce" and Path(payload["run_dir"]) == Path("/saved/run")
    assert payload["trust"] == "trusted_project"
    assert window.active_run != Path("/saved/run") and window.record is None


def test_history_survives_reopening_and_ignores_links(view, tmp_path, qtbot):
    window, controller = view
    root = window.data_root / "runs"
    (root / "completed-run").mkdir(parents=True)
    try:
        (root / "linked-run").symlink_to(root / "completed-run", target_is_directory=True)
    except OSError:
        pass
    window.refresh_history()
    assert window.history.count() == 1 and not controller.calls
    window.open_history_item(window.history.item(0))
    assert controller.calls[-1][0] == "backend_inspect"
    controller.finish({"status": "incomplete", "evidence": {"accounting": "unknown"}})
    assert not window.reproduce_button.isEnabled()


def test_cancel_and_close_wait_for_worker_cleanup(view, qtbot):
    window, controller = view
    window._start("backend_execute", {}, output=Path("/owned/cancelled"))
    window.close()
    assert controller.cancelled and window.isVisible()
    assert "process-tree cleanup" in window.status_label.text()
    controller.finish({"status": "cancelled", "evidence": {"cleanup_verified": True}})
    qtbot.waitUntil(lambda: not window.isVisible())


def test_export_uses_a_fresh_directory_and_preserves_the_run(view, tmp_path, monkeypatch):
    window, controller = view
    window.active_run = Path("/owned/run")
    window.record = {"status": "passed", "evidence": {}}
    monkeypatch.setattr("firmavex.desktop.universal.QFileDialog.getExistingDirectory", lambda *a: str(tmp_path))
    window.export()
    command, payload = controller.calls[-1]
    assert command == "backend_export" and Path(payload["run_dir"]) == Path("/owned/run")
    assert Path(payload["output_dir"]).parent == tmp_path
    assert not Path(payload["output_dir"]).exists()
    assert window.active_run == Path("/owned/run")


def test_ui_diagnostic_and_event_previews_are_bounded(view):
    window, controller = view
    window._progress({"kind": "progress", "payload": {"message": "actual worker phase", "diagnostic": "x" * 100000}})
    assert len(window.log_view.toPlainText()) <= 8192
    assert "actual worker phase" in window.status_label.text()
    window._result({"status": "infrastructure_failure", "evidence": {"error": "x" * 100000}})
    assert len(window.result_view.toPlainText()) < 66000
    assert "complete record remains on disk" in window.result_view.toPlainText()


def test_main_window_keeps_old_navigation_and_opens_workspace_without_execution(qtbot, tmp_path):
    from firmavex.desktop.window import MainWindow
    window = MainWindow(Controller(), data_root=tmp_path / "application")
    qtbot.addWidget(window)
    window.show()
    assert window.navigation.count() == 4
    window.show_backends()
    child = window._universal_window
    assert child is not None and child.isVisible() and not child.busy
    assert child.windowModality() == Qt.WindowModality.WindowModal
    assert window.navigation.count() == 4
    child.arm_configuration_requested.emit()
    assert window.navigation.currentRow() == 1 and not child.isVisible()
    window.close()


def test_main_close_preserves_a_running_backend_until_cleanup(qtbot, tmp_path):
    from firmavex.desktop.window import MainWindow
    main = MainWindow(Controller(), data_root=tmp_path / "application")
    qtbot.addWidget(main)
    main.show()
    controller = Controller()
    child = UniversalWindow(controller, data_root=tmp_path / "application", parent=main)
    main._universal_window = child
    child.controller.idle.connect(main._backend_idle)
    child.show()
    child._start("backend_execute", {}, output=Path("/owned/active"))
    main.close()
    assert main.isVisible() and child.isVisible() and controller.cancelled
    assert main._closing and child._closing
    controller.finish({"status": "cancelled", "evidence": {"cleanup_verified": True}})
    qtbot.waitUntil(lambda: not main.isVisible() and not child.isVisible())


def test_human_summary_preserves_raw_evidence_and_qualification_limits(view):
    window, controller = view
    window._job = 'backend_inspect'
    record = {'schema_version':1, 'status':'infrastructure_failure',
              'evidence':{'measurement_mode':'synthetic_test','cleanup_verified':False}}
    window._result(record)
    assert 'could not be completed reliably' in window.summary_view.toPlainText()
    assert 'synthetic_test' in window.result_view.toPlainText()
    assert window.record == record
    assert not window.reproduce_button.isEnabled()
