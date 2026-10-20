"""Actual compiler-free unified GUI execution; never synthetic qualification."""

import json
import os
from pathlib import Path

import pytest


def _require(profile):
    from firmavex.backends.compatibility import check
    try:
        readiness = check(profile)
        ready = readiness.get("status") in {"tools_available", "ready"} or readiness.get("success") is True
        if not ready:
            raise RuntimeError(json.dumps(readiness))
    except Exception as error:
        if os.environ.get("FIRMAVEX_REQUIRE_BACKENDS") == "1":
            pytest.fail("Required native runtime unavailable: " + str(error))
        pytest.skip("Native tools required; no synthetic substitute: " + str(error))


def _assert_cleanup(record):
    evidence = record["evidence"]
    assert evidence["cleanup_verified"] is True
    if "legacy_result" in evidence:
        # Legacy receipt accounting is verified by the adapter and the worker.
        assert evidence["legacy_result"]["execution_evidence"] == "complete"
        assert not evidence["legacy_result"]["accounting"]["aborted"]
        return
    assert evidence["cleanup"] and all(child["reaped"] for child in evidence["cleanup"])
    if os.name == "posix":
        for child in evidence["cleanup"]:
            with pytest.raises(ProcessLookupError):
                os.kill(child["pid"], 0)


def test_real_malformed_verilog_diagnostics_inspection_and_export(qtbot, tmp_path, monkeypatch):
    """Actual compiler failure; display must not modify evidence or exports."""
    import hashlib
    from firmavex.desktop.universal import UniversalWindow
    from firmavex.backends.report import export

    _require("verilog-icarus")
    source = tmp_path / "malformed.v"
    source.write_text("module testbench; initial begin broken syntax end endmodule\n")
    window = UniversalWindow(data_root=tmp_path / "compiler diagnostics data")
    qtbot.addWidget(window)
    window.show()
    try:
        window.profile_combo.setCurrentIndex(window.profile_combo.findData("verilog-icarus"))
        window.check_runtime()
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
        assert window._ready, window.result_view.toPlainText()
        window.source_edit.setText(str(source))
        window.trust_box.setChecked(True)
        window.execute()
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
        record = window.record
        assert record["status"] == "invalid_input", record
        assert record["evidence"]["measurement_mode"] == "unverified"
        _assert_cleanup(record)
        stderr = record["evidence"]["compile_stderr"]
        assert stderr.strip() and "syntax error" in stderr.lower()
        assert "Compiler diagnostics" in window.summary_view.toPlainText()
        assert "syntax error" in window.summary_view.toPlainText().lower()
        run = window.active_run
        before = {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
        # Establish an export baseline, then inspect the saved run and export via UI.
        baseline = tmp_path / "baseline-export"
        export(run, baseline)
        window.inspect(run)
        qtbot.waitUntil(lambda: not window.busy, timeout=15000)
        assert window.record == record
        assert "Compiler diagnostics" in window.summary_view.toPlainText()
        assert not window.trust_box.isChecked()
        monkeypatch.setattr("firmavex.desktop.universal.QFileDialog.getExistingDirectory", lambda *a: str(tmp_path))
        window.export()
        qtbot.waitUntil(lambda: not window.busy, timeout=15000)
        destinations = list(tmp_path.glob("firmavex-backend-export-*"))
        assert len(destinations) == 1
        destination = destinations[0]
        baseline_files = {p.name: p.read_bytes() for p in baseline.iterdir()}
        assert {p.name: p.read_bytes() for p in destination.iterdir()} == baseline_files
        assert json.loads((destination / "result.json").read_text()) == record
        assert (destination / "compile_stderr.txt").read_bytes() == stderr.encode("utf-8")
        for name, digest in json.loads((destination / "checksums.json").read_text()).items():
            assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
        assert {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()} == before
    finally:
        if window.busy:
            window.cancel()
            qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        window.close()


@pytest.mark.parametrize("profile,status,mode", [
    ("cortex-m3-mps2", "triggered", "real_firmware"),
    ("riscv32-virt", "triggered", "real_firmware"),
    ("verilog-icarus", "passed", "real_simulation"),
])
def test_real_unified_example_execution_reproduction_history_export(qtbot, tmp_path, monkeypatch, profile, status, mode):
    _require(profile)
    from PySide6.QtCore import QTimer
    from firmavex.desktop.universal import UniversalWindow
    from firmavex.backends.engine import inspect_run

    window = UniversalWindow(data_root=tmp_path / "independent native GUI data")
    qtbot.addWidget(window)
    window.show()
    window.profile_combo.setCurrentIndex(window.profile_combo.findData(profile))
    ticks = []
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    try:
        window.check_runtime()
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
        assert window._ready, window.result_view.toPlainText()
        window.prepare_example()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        assert window.source_edit.text() and window._example_source == window.source_edit.text(), window.result_view.toPlainText()
        assert not window.trust_box.isChecked()
        window.trust_box.setChecked(True)
        window.execute()
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
        assert window.record is not None, window.result_view.toPlainText()
        first = window.active_run
        assert window.record["status"] == status, window.result_view.toPlainText()
        assert window.record["evidence"]["measurement_mode"] == mode
        _assert_cleanup(window.record)
        if profile == "cortex-m3-mps2":
            accounting = window.record["evidence"]["legacy_result"]["accounting"]
            assert accounting["attempted_executions"] == 10
            assert accounting["infrastructure_failures"] == 0
            assert window.record["evidence"]["triggering_input"] == [2, 1]
        if profile == "riscv32-virt":
            assert window.record["evidence"]["completion_observed"] is True
            assert window.record["evidence"]["values"] == [2, 1]
        if profile == "verilog-icarus":
            assert (first / "waveform.vcd").is_file()
        assert window.reproduce_button.isEnabled()
        window.trust_box.setChecked(True)
        window.reproduce()
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
        assert window.record is not None, window.result_view.toPlainText()
        assert window.record["status"] == status, window.result_view.toPlainText()
        _assert_cleanup(window.record)
        second = window.active_run
        assert first != second and inspect_run(first)["status"] == status
        monkeypatch.setattr("firmavex.desktop.universal.QFileDialog.getExistingDirectory", lambda *a: str(tmp_path))
        window.export()
        qtbot.waitUntil(lambda: not window.busy, timeout=15000)
        exports = list(tmp_path.glob("firmavex-backend-export-*"))
        assert len(exports) == 1 and (exports[0] / "REPORT.md").is_file()
        assert (exports[0] / "checksums.json").is_file()
        if profile == "verilog-icarus":
            assert list(exports[0].rglob("*.vcd"))
        # Reopening uses a read-only worker request, not another execution.
        snapshot = (first / "result.json").read_bytes()
        window.inspect(first)
        qtbot.waitUntil(lambda: not window.busy, timeout=15000)
        assert window.record["status"] == status
        assert not window.trust_box.isChecked()
        assert (first / "result.json").read_bytes() == snapshot
        assert window.history.count() == 2 and len(ticks) > 5
    finally:
        timer.stop()
        if window.busy:
            window.cancel()
            qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        window.close()


def test_real_unified_cancel_icarus_after_simulator_dispatch(qtbot, tmp_path):
    _require("verilog-icarus")
    from firmavex.desktop.universal import UniversalWindow
    from firmavex.backends.engine import inspect_run

    source = tmp_path / "trusted infinite testbench.v"
    marker = "FIRMAVEX_SIMULATION_STARTED"
    source.write_text('module testbench; reg clock=0; initial $display("' + marker + '"); always #1 clock=~clock; endmodule\n', encoding="ascii")
    window = UniversalWindow(data_root=tmp_path / "native cancellation data")
    qtbot.addWidget(window)
    window.show()
    window.profile_combo.setCurrentIndex(window.profile_combo.findData("verilog-icarus"))
    simulation_events = []

    def cancel_dispatched(envelope):
        payload = envelope.get("payload", {})
        if (payload.get("type") == "backend_stage" and payload.get("stage") == "simulation_output"
                and marker in payload.get("stdout_preview", "")):
            simulation_events.append(payload)
            window.cancel()

    window.controller.event.connect(cancel_dispatched)
    try:
        window.check_runtime()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        assert window._ready, window.result_view.toPlainText()
        window.source_edit.setText(str(source))
        window.trust_box.setChecked(True)
        window.execute()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        assert simulation_events, window.result_view.toPlainText()
        record = inspect_run(window.active_run)
        assert record["status"] == "cancelled", record
        assert any(marker in item.get("stdout", "") for item in record["evidence"]["process_logs"])
        _assert_cleanup(record)
        assert not window.reproduce_button.isEnabled()
        assert window.export_button.isEnabled()
    finally:
        if window.busy:
            window.cancel()
            qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        window.close()
