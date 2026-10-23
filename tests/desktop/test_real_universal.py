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
        assert "Failure diagnosis" in window.summary_view.toPlainText()
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
        if profile == "cortex-m3-mps2":
            saved_replay = json.loads((second / "result.json").read_text())
            assert window.record == saved_replay
            nested = saved_replay["evidence"]["legacy_result"]
            def assert_arm_summary():
                text = window.summary_view.toPlainText()
                assert "ARM reproduction summary" in text
                assert "Saved replay input: " + json.dumps(nested["reproduction"]["input"]) in text
                for label, key in [("Requested repetitions", "requested_attempts"),
                                   ("Completed observations", "completed_observations"),
                                   ("Matching failure observations", "matching_observations")]:
                    assert label + ": " + str(nested["reproduction"][key]) in text
                assert "Recorded reproduction status: " + nested["reproduction"]["status"] in text
            assert_arm_summary()
            retained = {p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()}
            from firmavex.backends.report import export as baseline_export
            baseline = tmp_path / "arm-baseline-export"
            baseline_export(second, baseline)
            window.inspect(second)
            qtbot.waitUntil(lambda: not window.busy, timeout=15000)
            assert window.record == saved_replay
            assert_arm_summary()
        monkeypatch.setattr("firmavex.desktop.universal.QFileDialog.getExistingDirectory", lambda *a: str(tmp_path))
        window.export()
        qtbot.waitUntil(lambda: not window.busy, timeout=15000)
        exports = list(tmp_path.glob("firmavex-backend-export-*"))
        assert len(exports) == 1 and (exports[0] / "REPORT.md").is_file()
        if profile == "cortex-m3-mps2":
            assert {p.name: p.read_bytes() for p in exports[0].iterdir()} == {
                p.name: p.read_bytes() for p in baseline.iterdir()}
            assert {p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()} == retained
        assert (exports[0] / "checksums.json").is_file()
        if profile == "verilog-icarus":
            assert list(exports[0].rglob("*.vcd"))
        # Actual UI comparison and verification complete the individual-run audit.
        from PySide6.QtCore import Qt
        before_review = {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()}
        first_item = next(window.history.item(i) for i in range(window.history.count())
                          if window.history.item(i).data(Qt.ItemDataRole.UserRole) == str(first))
        second_item = next(window.history.item(i) for i in range(window.history.count())
                           if window.history.item(i).data(Qt.ItemDataRole.UserRole) == str(second))
        window.history.setCurrentItem(first_item); window.pin_button.click()
        window.history.setCurrentItem(second_item); window.compare_button.click()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        assert window.comparison_view.rowCount() > 6
        assert window.tabs.currentWidget() is window.comparison_panel
        target = second / 'arm-run' if profile == 'cortex-m3-mps2' else second
        monkeypatch.setattr('firmavex.desktop.universal.QFileDialog.getExistingDirectory', lambda *a: str(target))
        window.verify_folder()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        expected_verification = 'unavailable' if profile == 'riscv32-virt' else 'verified'
        assert window._verification_session['status'] == expected_verification, window.verification_label.text()
        # RV32's default individual verifier lacks a listed artifact inventory;
        # aggregate regression verification separately checks the retained input.
        monkeypatch.setattr('firmavex.desktop.universal.QFileDialog.getExistingDirectory', lambda *a: str(tmp_path))
        window.export_verification_report()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        assert len(list(tmp_path.glob('firmavex-verification-*/verification.txt'))) == 1
        assert {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()} == before_review
        if profile == 'verilog-icarus':
            import shutil
            damaged = tmp_path / 'damaged-evidence-copy'
            shutil.copytree(second, damaged)
            (damaged / 'waveform.vcd').unlink()
            monkeypatch.setattr('firmavex.desktop.universal.QFileDialog.getExistingDirectory', lambda *a: str(damaged))
            window.verify_folder()
            qtbot.waitUntil(lambda: not window.busy, timeout=30000)
            assert window._verification_session['status'] == 'failed'
            assert any(item['state'] == 'missing_artifact' for item in window._verification_session['items'])
            assert {p.relative_to(second): p.read_bytes() for p in second.rglob('*') if p.is_file()} == before_review
        displayed = (window.result_view.toPlainText(), window.result_context_label.text(), window.record)
        window.regression_panel.refresh_dashboard()
        qtbot.waitUntil(lambda: not window.busy, timeout=30000)
        assert displayed == (window.result_view.toPlainText(), window.result_context_label.text(), window.record)
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


@pytest.mark.parametrize('profile', ['cortex-m3-mps2', 'riscv32-virt', 'verilog-icarus'])
def test_real_custom_configuration_workflow(qtbot, tmp_path, monkeypatch, profile):
    """Native custom fixtures, immutable snapshots and associated ordinary runs."""
    _require(profile)
    from firmavex.backends.bundled import catalog
    from firmavex.desktop.universal import UniversalWindow
    import tempfile
    with tempfile.TemporaryDirectory(prefix='fx17-') as temporary:
        window = UniversalWindow(data_root=Path(temporary) / 'w')
        qtbot.addWidget(window)
        window.show()
        source = tmp_path / 'custom input'
        if profile == 'cortex-m3-mps2':
            from firmavex.product.services import prepare_example_project
            from firmavex.product.config import load_config
            from firmavex.desktop.projects import DesktopProject
            from firmavex.product.workspace import arm_context
            from dataclasses import replace
            prepared = prepare_example_project(Path(temporary) / 'example')
            config = load_config(prepared['config_file'])
            source.write_bytes(config.firmware.read_bytes() + b'custom ARM fixture revision')
            project = DesktopProject.create(Path(temporary) / 'p', source, replace(config, firmware=source))
            context = arm_context(project, project.load_config())
        elif profile == 'riscv32-virt':
            source.write_bytes(catalog()[1] + b'custom fixture revision')
        else:
            source.write_text('module testbench; initial begin $display("FIRMAVEX_TEST_RESULT=PASS"); $finish; end endmodule', encoding='ascii')
        original = source.read_bytes()
        try:
            window.profile_combo.setCurrentIndex(window.profile_combo.findData(profile))
            if profile == 'cortex-m3-mps2':
                window.select_arm_context(context)
            else:
                window.source_edit.setText(str(source))
            if profile == 'riscv32-virt':
                window.values_edit.setText('00, 00')
            window.configuration_name.setText('Native custom fixture')
            window.preflight()
            qtbot.waitUntil(lambda: not window.busy, timeout=30000)
            assert 'static_checks_passed' in window.operation_view.toPlainText()
            if profile == 'cortex-m3-mps2':
                root, manifest_path, input_path = project.root, project.config_path, project.firmware_path
            else:
                window.save_named_configuration()
                qtbot.waitUntil(lambda: not window.busy, timeout=30000)
                saved = window._saved_configuration
                assert saved is not None, window.operation_view.toPlainText()
                root = Path(saved['configuration'])
                manifest_path, input_path = root / 'configuration.json', root / 'input'
            manifest = manifest_path.read_bytes()
            expected = 'triggered' if profile == 'cortex-m3-mps2' else 'passed'
            source.unlink()
            if profile != 'cortex-m3-mps2':
                window.configuration_clear.click()
                window.list_configurations()
                qtbot.waitUntil(lambda: not window.busy, timeout=30000)
                window.configurations.setCurrentIndex(window.configurations.findData(str(root)))
                window.open_named_configuration()
                qtbot.waitUntil(lambda: not window.busy, timeout=30000)
                assert window._saved_configuration['identity'] == saved['identity']
                assert not window.trust_box.isChecked()
            window.check_runtime()
            qtbot.waitUntil(lambda: not window.busy, timeout=120000)
            assert window._ready and not window.trust_box.isChecked()
            window.trust_box.setChecked(True)
            window.execute()
            qtbot.waitUntil(lambda: not window.busy, timeout=120000)
            assert window.record and window.record['status'] == expected, window.result_view.toPlainText()
            _assert_cleanup(window.record)
            first = window.active_run
            assert first.parent == root / 'runs' and window.history.count() == 1
            window.reproduce()
            qtbot.waitUntil(lambda: not window.busy, timeout=120000)
            assert window.record and window.record['status'] == expected
            _assert_cleanup(window.record)
            assert window.history.count() == 2
            before = {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}
            window.inspect(first)
            qtbot.waitUntil(lambda: not window.busy, timeout=15000)
            assert not window.trust_box.isChecked()
            monkeypatch.setattr('firmavex.desktop.universal.QFileDialog.getExistingDirectory', lambda *a: str(tmp_path))
            window.export()
            qtbot.waitUntil(lambda: not window.busy, timeout=30000)
            assert list(tmp_path.glob('firmavex-backend-export-*/REPORT.md'))
            assert manifest_path.read_bytes() == manifest
            assert input_path.read_bytes() == original
            assert {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()} == before
        finally:
            if window.busy:
                window.controller.cancel()
                qtbot.waitUntil(lambda: not window.busy, timeout=20000)
            window.close()


def _regression_failure_details(result, presentation):
    """Expose bounded retained errors when a native GUI assertion fails."""
    from firmavex.backends.engine import inspect_run
    rows = []
    if type(result) is dict:
        for entry in result.get('entries', [])[:16]:
            if not entry.get('evidence'):
                continue
            try:
                record = inspect_run(Path(result['directory']) / entry['evidence'])
                evidence = record['evidence']
                rows.append({'entry_id': entry['id'], 'status': record['status'],
                             'error': str(evidence.get('error', 'unavailable'))[:4096],
                             'cleanup_verified': evidence.get('cleanup_verified')})
            except Exception as error:
                rows.append({'entry_id': entry['id'], 'inspection_error': str(error)[:600]})
    return json.dumps({'presentation': presentation[:4096], 'retained_errors': rows}, indent=2)


@pytest.mark.parametrize('profile', ['riscv32-virt', 'verilog-icarus'])
def test_real_regression_dashboard_verify_and_text_report(qtbot, tmp_path, monkeypatch, profile):
    """Native desktop: create/save/run/diagnose/rerun/compare/verify/export."""
    from firmavex.backends.api import Request, request_to_dict
    from firmavex.backends.bundled import catalog
    from firmavex.desktop.universal import UniversalWindow
    from firmavex.desktop import regression as regression_ui
    from firmavex.product import workspace
    _require(profile)
    source = tmp_path / ('firmware.elf' if profile == 'riscv32-virt' else 'testbench.v')
    if profile == 'riscv32-virt':
        source.write_bytes(catalog()[1])
    else:
        source.write_text('module testbench; initial begin $display("FIRMAVEX_TEST_RESULT=PASS"); $finish; end endmodule')
    window = UniversalWindow(data_root=tmp_path / 'desktop-data')
    qtbot.addWidget(window)
    window.show()
    panel = window.regression_panel
    def done():
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
    try:
        panel.name.setText('native regression dashboard')
        for index in range(2):
            if profile == 'verilog-icarus' and index:
                source.write_text(source.read_text().replace('PASS', 'FAIL'))
            values = ((0, 0) if index == 0 else (2, 1)) if profile == 'riscv32-virt' else ()
            config = workspace.save(tmp_path / 'configs', str(index), request_to_dict(Request(profile, source, values)))
            window._saved_configuration = config
            panel.add()
        if profile == 'riscv32-virt':
            panel.entries.item(0, 2).setText('00, 00')
        panel.save(); done()
        assert panel.saved is not None, panel.report.toPlainText()
        assert not panel.trust.isChecked()
        panel.trust.setChecked(True); panel.run(); done()
        first = panel.current_run
        assert first and first['counts']['passed'] == first['counts']['failed'] == 1, _regression_failure_details(first, panel.report.toPlainText())
        panel.open_entry(0, 0); done()
        assert 'Failure diagnosis' in window.summary_view.toPlainText()
        individual = (window.active_run, window.record, window.result_view.toPlainText(), window.result_context_label.text())
        panel.previous_run = first
        panel.trust.setChecked(True); panel.run(); done()
        second = panel.current_run
        assert second and second['rerun_of'] == first['run_id']
        panel.compare(); done()
        assert panel.comparison.item(0, 3).text() == 'same'
        before = {p.relative_to(Path(second['directory'])): p.read_bytes() for p in Path(second['directory']).rglob('*') if p.is_file()}
        panel.verify_current(); done()
        assert panel.aggregate_review and panel.aggregate_review['status'] == 'verified', panel.report.toPlainText()
        assert panel.artifacts.rowCount() >= 2
        panel.refresh_dashboard(); done()
        assert panel.sessions.rowCount() == 2
        report_parent = tmp_path / 'reports'; report_parent.mkdir()
        monkeypatch.setattr(regression_ui.QFileDialog, 'getExistingDirectory', lambda *a: str(report_parent))
        panel.export_report(); done()
        reports = list(report_parent.glob('*/regression.txt'))
        assert len(reports) == 1, panel.report.toPlainText()
        report = reports[0].read_text()
        assert second['run_id'] in report and 'Comparison:' in report
        assert 'Fresh verification: verified' in panel.report.toPlainText()
        assert before == {p.relative_to(Path(second['directory'])): p.read_bytes() for p in Path(second['directory']).rglob('*') if p.is_file()}
        assert not panel.trust.isChecked()
        assert individual == (window.active_run, window.record, window.result_view.toPlainText(), window.result_context_label.text())
        # Actual worker rejection stays in the regression panel and leaves
        # evidence untouched, with actionable export recovery guidance.
        monkeypatch.setattr(regression_ui.QFileDialog, 'getExistingDirectory', lambda *a: second['directory'])
        panel.export_report(); done()
        assert window.tabs.currentWidget() is panel
        assert 'new report folder outside original evidence' in panel.report.toPlainText()
        assert panel.current_run['run_id'] == second['run_id']
        assert individual == (window.active_run, window.record, window.result_view.toPlainText(), window.result_context_label.text())
        assert before == {p.relative_to(Path(second['directory'])): p.read_bytes() for p in Path(second['directory']).rglob('*') if p.is_file()}
    finally:
        window.close()
        qtbot.waitUntil(lambda: not window.busy, timeout=120000)
