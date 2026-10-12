"""Bounded actual ARM desktop workflow; never a research performance campaign."""
import json
import os
from pathlib import Path
import shutil
import pytest


def test_real_desktop_build_import_search_reproduction_export_and_cancel(qtbot,tmp_path,monkeypatch):
    if not shutil.which('arm-none-eabi-gcc') or not shutil.which('qemu-system-arm') or not (shutil.which('arm-none-eabi-gdb') or shutil.which('gdb-multiarch')):
        if os.environ.get('FIRMAVEX_REQUIRE_RUNTIME')=='1':
            pytest.fail('Required actual ARM runtime tools are missing')
        pytest.skip('Actual ARM runtime tools required; no synthetic firmware substitute')
    from firmavex.desktop.window import MainWindow
    from firmavex.product.store import RunStore
    from firmavex.product.services import inspect_run
    from PySide6.QtCore import QTimer
    w=MainWindow(data_root=tmp_path/'independent desktop data')
    qtbot.addWidget(w); w.show()
    ticks=[]
    timer=QTimer(); timer.setInterval(20); timer.timeout.connect(lambda:ticks.append(True)); timer.start()
    try:
        w.check_tools()
        qtbot.waitUntil(lambda:not w.busy,timeout=15000)
        assert 'mps2-an385' not in w.status_label.text() or 'unsupported' not in w.status_label.text()
        w.build_example()
        qtbot.waitUntil(lambda:w.project is not None and not w.busy,timeout=30000)
        assert w.configuration().input_symbols==('product_inputs[0]','product_inputs[1]')
        w.start_run()
        qtbot.waitUntil(lambda:w.result_record is not None and not w.busy,timeout=45000)
        search=w.result_record; source=w.active_run
        assert search['success'] and search['measurement_mode']=='real_firmware'
        assert search['triggering_input']==[2,1] and search['accounting']['attempted_executions']==10
        assert search['accounting']['infrastructure_failures']==0
        assert w.attempts_table.rowCount()==10 and w.reproduce_button.isEnabled()
        assert 'Charged evaluator attempts: 10' in w.report_view.toPlainText()
        assert 'waiting for worker cleanup' not in w.status_label.text()
        w.reproduce()
        qtbot.waitUntil(lambda:w.result_record is not search and not w.busy,timeout=30000)
        replay=w.result_record; replay_path=w.active_run
        assert replay['outcome']=='reproduced_in_emulator'
        assert replay['reproduction']['matching_observations']==3
        assert replay['accounting']['attempted_executions']==3
        # Export is a read-only archive operation, not another execution.
        monkeypatch.setattr('firmavex.desktop.window.QFileDialog.getExistingDirectory',lambda *a:str(tmp_path))
        w.export_result()
        qtbot.waitUntil(lambda:not w.busy,timeout=10000)
        exports=list(tmp_path.glob('firmavex-report-*'))
        assert len(exports)==1 and (exports[0]/'SHA256SUMS').is_file()
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
                    with pytest.raises(ProcessLookupError): os.kill(child['pid'],0)
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
        qtbot.waitUntil(admitted,timeout=15000)
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
