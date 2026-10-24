"""Bounded actual ARM desktop workflow; never a research performance campaign."""
import json
import os
from pathlib import Path
import shutil
import pytest


from tests.desktop.process_identity import assert_process_not_running
from tests.desktop.path_identity import assert_same_path


def test_real_desktop_builtin_search_reproduction_export_and_cancel(qtbot,tmp_path,monkeypatch):
    from firmavex.product.tools import discover
    try:
        discover()
    except Exception as error:
        if os.environ.get('FIRMAVEX_REQUIRE_RUNTIME') == '1':
            pytest.fail('Required real runtime unavailable: ' + str(error))
        pytest.skip('Real ARM runtime required; never substitute synthetic execution')
    from firmavex.desktop.window import MainWindow
    from firmavex.product.store import RunStore
    from firmavex.product.services import inspect_run
    from PySide6.QtCore import QTimer
    w=MainWindow(data_root=tmp_path/'independent desktop data')
    qtbot.addWidget(w); w.show()
    ticks=[]
    timer=QTimer(); timer.setInterval(20); timer.timeout.connect(lambda:ticks.append(True)); timer.start()
    # Full managed-runtime integrity checks read a large vendor inventory.
    # Bound administrative preflight separately from guest execution timeouts.
    preflight_timeout = 120000
    try:
        w.check_tools()
        qtbot.waitUntil(lambda:not w.busy,timeout=preflight_timeout)
        assert len(ticks) > 0  # Verification must not block the GUI event loop.
        assert 'mps2-an385' not in w.status_label.text() or 'unsupported' not in w.status_label.text()
        w.prepare_builtin_example()
        qtbot.waitUntil(lambda:w.project is not None and not w.busy,timeout=30000)
        assert w.configuration().compiler is None
        assert w.configuration().input_symbols==('product_inputs[0]','product_inputs[1]')
        w.start_run()
        qtbot.waitUntil(lambda:w.result_record is not None and not w.busy,timeout=preflight_timeout)
        search=w.result_record; source=w.active_run
        assert search['success'] and search['measurement_mode']=='real_firmware'
        assert search['triggering_input']==[2,1] and search['accounting']['attempted_executions']==10
        assert search['accounting']['infrastructure_failures']==0
        assert w.attempts_table.rowCount()==10 and w.reproduce_button.isEnabled()
        assert 'Charged evaluator attempts: 10' in w.report_view.toPlainText()
        assert 'waiting for worker cleanup' not in w.status_label.text()
        w.reproduce()
        qtbot.waitUntil(lambda:w.result_record is not search and not w.busy,timeout=preflight_timeout)
        replay=w.result_record; replay_path=w.active_run
        assert replay['outcome']=='reproduced_in_emulator'
        assert replay['reproduction']['matching_observations']==3
        assert replay['accounting']['attempted_executions']==3
        # Counts in the display must come from the persisted reproduction, not
        # the UI repetition control or an inferred success verdict.
        saved_replay=json.loads((replay_path/'result.json').read_text())
        assert saved_replay == replay
        def assert_replay_summary():
            text=w.report_view.toPlainText()
            assert 'ARM reproduction summary' in text
            assert 'Saved replay input: '+json.dumps(saved_replay['reproduction']['input']) in text
            for label,key in [('Requested repetitions','requested_attempts'),
                              ('Completed observations','completed_observations'),
                              ('Matching failure observations','matching_observations')]:
                assert label+': '+str(saved_replay['reproduction'][key]) in text
            assert 'Infrastructure failures: '+str(saved_replay['accounting']['infrastructure_failures']) in text
            assert 'Evidence completeness: '+saved_replay['execution_evidence'] in text
        assert_replay_summary()
        retained={p.relative_to(replay_path):p.read_bytes() for p in replay_path.rglob('*') if p.is_file()}
        w.open_run(replay_path)
        qtbot.waitUntil(lambda:not w.busy,timeout=preflight_timeout)
        assert w.result_record == saved_replay
        assert_replay_summary()
        # Export is a read-only archive operation, not another execution.
        monkeypatch.setattr('firmavex.desktop.window.QFileDialog.getExistingDirectory',lambda *a:str(tmp_path))
        w.export_result()
        qtbot.waitUntil(lambda:not w.busy,timeout=10000)
        exports=list(tmp_path.glob('firmavex-report-*'))
        assert len(exports)==1 and (exports[0]/'SHA256SUMS').is_file()
        # Text export uses platform newlines; retained evidence keeps LF bytes.
        assert (exports[0]/'report.md').read_text(encoding='utf-8')==retained[Path('report.md')].decode('utf-8').replace('\r\n','\n')
        assert 'ARM reproduction summary' not in (exports[0]/'report.md').read_text()
        assert {p.relative_to(replay_path):p.read_bytes() for p in replay_path.rglob('*') if p.is_file()}==retained
        for run in (source,replay_path):
            inspection=inspect_run(run)
            assert inspection['accounting_verification']['status']=='receipt_accounting_consistent'
            with RunStore(run) as store:
                snapshot=store.snapshot()
            for attempt in snapshot['attempts']:
                evidence=attempt['record']['evidence']
                assert evidence['cleanup_verified'] and evidence['measurement_mode']=='real_firmware'
                assert all(p['reaped'] for p in evidence['cleanup']['processes'])
                for child in evidence['cleanup']['processes']:
                    assert_process_not_running(child)
        # A required unreachable completion function gives enough time to
        # cancel a charged fresh attempt. It is not counted as safe firmware.
        w.complete_edit.setText('Default_Handler'); w.timeout_spin.setValue(5)
        w.start_run()
        qtbot.waitUntil(lambda:w.controller.busy,timeout=15000)
        def admitted():
            try:
                with RunStore(w._job_output) as store:
                    return any(event['kind']=='trial_requested' for event in store.snapshot()['events'])
            except Exception:
                return False
        qtbot.waitUntil(admitted,timeout=preflight_timeout)
        QTimer.singleShot(100,w.cancel_job)
        qtbot.waitUntil(lambda:not w.busy,timeout=20000)
        assert w.result_record is not None,w.validation_text.toPlainText()
        cancelled=w.result_record
        assert cancelled['state']=='cancelled' and not cancelled['success']
        assert cancelled['accounting']['attempted_executions']==1
        assert cancelled['accounting']['infrastructure_failures']==1
        assert cancelled['accounting']['aborted']
        assert cancelled['execution_evidence']=='incomplete'
        assert len(ticks)>20  # The GUI event loop ran throughout real work.
    finally:
        timer.stop()
        if w.busy:
            w.controller.cancel()
            qtbot.waitUntil(lambda:not w.busy,timeout=20000)
        w.close()


def test_real_arm_import_preflight_execute_and_project_reopen(qtbot, tmp_path, monkeypatch):
    """Actual ARM GUI import and static validation; no synthetic worker."""
    from firmavex.product.tools import discover
    try:
        discover()
    except Exception as error:
        if os.environ.get('FIRMAVEX_REQUIRE_RUNTIME') == '1': pytest.fail(str(error))
        pytest.skip('Real ARM runtime required; no synthetic substitute')
    from firmavex.desktop.window import MainWindow
    import tempfile
    with tempfile.TemporaryDirectory(prefix='fx21-') as temporary:
        root = Path(temporary)
        window = MainWindow(data_root=root / 'data')
        qtbot.addWidget(window); window.show()
        def done(): qtbot.waitUntil(lambda: not window.busy, timeout=120000)
        try:
            window.prepare_builtin_example(); done()
            original = window.project
            source = root / 'custom.elf'
            source.write_bytes(original.firmware_path.read_bytes() + b'Batch 21 custom import fixture')
            retained = {p.relative_to(original.root): p.read_bytes() for p in original.root.rglob('*') if p.is_file()}
            imported_bytes = source.read_bytes()
            parent = root / 'projects'; parent.mkdir()
            monkeypatch.setattr('firmavex.desktop.window.QFileDialog.getOpenFileName', lambda *a: (str(source), ''))
            monkeypatch.setattr('firmavex.desktop.window.QFileDialog.getExistingDirectory', lambda *a: str(parent))
            window.revision_button.click(); done()
            assert window.project
            assert_same_path(window.project.root.parent, parent)
            assert not window.project.root.samefile(original.root)
            assert window.project.firmware_path.read_bytes() == imported_bytes
            revision = window.project.root
            revision_files = {p.relative_to(revision): p.read_bytes() for p in revision.rglob('*') if p.is_file()}
            # The new-project form must honor its selected ELF even while a
            # different managed image remains pinned in the current project.
            second_source = root / 'second-custom.elf'
            second_bytes = imported_bytes + b'new-project form selection'
            second_source.write_bytes(second_bytes)
            window.firmware_edit.setText(str(second_source))
            window.project_dir_edit.setText(str(root / 'imported-from-form'))
            assert window.configuration().firmware == window.project.firmware_path
            window.create_button.click(); done()
            assert_same_path(window.project.root, root / 'imported-from-form')
            assert window.project.firmware_path.read_bytes() == second_bytes
            assert {p.relative_to(revision): p.read_bytes() for p in revision.rglob('*') if p.is_file()} == revision_files
            assert window.active_run is None
            window.validate_configuration(); done()
            assert '"success": true' in window.validation_text.toPlainText(), window.validation_text.toPlainText()
            source.unlink()
            window.start_run(); done()
            assert window.result_record and window.result_record['outcome'] == 'configured_failure_observed'
            result = window.active_run
            evidence = {p.relative_to(result): p.read_bytes() for p in result.rglob('*') if p.is_file()}
            imported = window.project.root
            window.open_project(imported); done()
            assert_same_path(window.project.root, imported)
            window.open_run(result); done()
            assert window.result_record['measurement_mode'] == 'real_firmware'
            assert {p.relative_to(result): p.read_bytes() for p in result.rglob('*') if p.is_file()} == evidence
            assert {p.relative_to(original.root): p.read_bytes() for p in original.root.rglob('*') if p.is_file()} == retained
        finally:
            if window.busy:
                window.controller.cancel(); done()
            window.close()
