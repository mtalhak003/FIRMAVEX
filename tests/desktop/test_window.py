"""UI tests use explicitly synthetic records, never firmware measurements."""
from pathlib import Path
import threading
import time
import pytest
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from firmavex.desktop import window as ui
from firmavex.product.config import ProductConfig
from firmavex.product.errors import ProductError

class SyntheticController(QObject):
    event = Signal(dict)
    result = Signal(dict)
    error = Signal(dict)
    busy_changed = Signal(bool)
    idle = Signal()
    def __init__(self):
        super().__init__()
        self.busy = False
        self.calls = []
        self.cancelled = False
    def start(self, command, payload):
        if self.busy: return False
        self.calls.append((command, dict(payload)))
        self.busy = True
        self.busy_changed.emit(True)
        return True
    def cancel(self):
        if not self.busy: return False
        self.cancelled = True
        return True
    def shutdown(self):
        if self.busy:
            self.cancel()
            return False
        return True
    def finish(self, value=None, error=None):
        if value is not None:
            assert value.get('measurement_mode') != 'real_firmware'
            self.result.emit(value)
        if error is not None: self.error.emit(error)
        self.busy = False
        self.busy_changed.emit(False)
        self.idle.emit()

class SyntheticProject:
    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.config_path = root / 'project.json'
        self.firmware_path = config.firmware
        self.saved = []
        self.delay = 0
        self.fail = None
        self.owner_thread = threading.get_ident()
    def load_config(self): return self.config
    def save_config(self, config):
        assert threading.get_ident() != self.owner_thread
        time.sleep(self.delay)
        if self.fail: raise self.fail
        self.saved.append(config)
        return self.config_path
    def new_run_directory(self, kind='run'):
        assert threading.get_ident() != self.owner_thread
        return self.root / 'runs' / (kind + '-synthetic')
    def command_config(self, record):
        assert threading.get_ident() != self.owner_thread
        return self.root / 'commands' / 'immutable-synthetic.json'

@pytest.fixture
def view(qtbot, tmp_path):
    ctrl = SyntheticController()
    w = ui.MainWindow(ctrl, data_root=tmp_path/'app-data')
    qtbot.addWidget(w)
    w.show()
    yield w, ctrl
    qtbot.waitUntil(lambda: w._local_task is None, timeout=3000)
    if ctrl.busy: ctrl.finish(error={'category':'cancelled','message':'synthetic cleanup','details':{}})
    w.close()

def adopt(w, tmp_path):
    config = ProductConfig(firmware=tmp_path/'firmware.elf', input_symbols=('inputs[0]','inputs[1]'),
                           ready_breakpoint='ready', completion_breakpoint='complete', failure_symbol='failure', input_max=3, execution_budget=16)
    project = SyntheticProject(tmp_path/'project', config)
    w._adopt_project((project, config))
    return project

def test_welcome_opens_without_build_or_firmware_dispatch(view):
    w,c = view
    assert c.calls == [] and not w.busy
    assert w.navigation.count() == 4
    assert w.doctor_button.isEnabled() and not w.run_button.isEnabled()
    assert 'no hardware validation' in w.warning.text()


def test_recent_projects_are_explicit_verified_and_removable(view, tmp_path, qtbot, monkeypatch):
    from firmavex.desktop.recents import remember, load
    w, controller = view
    assert not w.open_recent_button.isEnabled()
    missing = tmp_path / 'moved-project'
    remember(w.data_root, missing)
    w._refresh_recents()
    assert controller.calls == [] and w.project is None
    w.open_recent_project()
    qtbot.waitUntil(lambda: not w.busy)
    assert w.project is None and controller.calls == []
    # Opening a remembered path still goes through the existing project verifier.
    verified = SyntheticProject(missing, ProductConfig(firmware=tmp_path / 'firmware.elf',
        input_symbols=('inputs[0]', 'inputs[1]'), ready_breakpoint='ready',
        completion_breakpoint='complete', failure_symbol='failure'))
    monkeypatch.setattr(ui.DesktopProject, 'open', lambda path: verified)
    w.open_recent_project()
    qtbot.waitUntil(lambda: not w.busy)
    assert w.project is verified and controller.calls == []
    assert load(w.data_root)[0] == str(missing)
    w.forget_recent_project()
    assert load(w.data_root) == [] and w.project is verified
    assert not w.open_recent_button.isEnabled()


@pytest.mark.parametrize('command', ['reproduce', 'inspect'])
@pytest.mark.parametrize('outcome', ['reproduced_in_emulator', 'reproduction_inconsistent',
                                    'infrastructure_failure', 'cancelled'])
def test_arm_replay_summary_fresh_and_saved(view, tmp_path, command, outcome):
    from copy import deepcopy
    import json
    w, c = view
    record = {'kind': 'firmavex_product_result', 'state': 'completed', 'outcome': outcome,
              'measurement_mode': 'synthetic_test', 'execution_evidence': 'incomplete',
              'triggering_input': [2, 1], 'parent': {'operation': 'reproduction'},
              'accounting': {'infrastructure_failures': 1},
              'reproduction': {'input': [2, 1], 'requested_attempts': 3,
                               'completed_observations': 1, 'matching_observations': 1,
                               'status': 'indeterminate'}}
    original = deepcopy(record)
    if command == 'inspect':
        w.open_run(tmp_path / 'saved')
        envelope = {'result': record}
    else:
        w._start('reproduce', {}, output=tmp_path / 'fresh')
        envelope = record
    c.finish(envelope)
    text = w.report_view.toPlainText()
    assert 'ARM reproduction summary' in text and 'Saved replay input: [2, 1]' in text
    assert 'Matching failure observations: 1' in text
    assert 'Recorded reproduction status: indeterminate' in text
    assert 'Recorded outcome: ' + outcome in text
    assert 'Evidence completeness: incomplete' in text
    assert w.result_record == original
    assert json.loads(w.result_text.toPlainText()) == envelope
    assert not w.reproduce_button.isEnabled()  # Synthetic evidence never enables replay.
    assert w.export_button.isEnabled() and len(c.calls) == 1
    w._show_result({'state': 'completed', 'outcome': 'domain_exhausted'})
    assert 'ARM reproduction summary' not in w.report_view.toPlainText()

@pytest.mark.parametrize('minimum,maximum', [('0','4294967295'), ('0x10','0xFF')])
def test_full_uint32_and_hex_input_configuration(view, tmp_path, minimum, maximum):
    w,c = view
    adopt(w,tmp_path)
    w.minimum_edit.setText(minimum); w.maximum_edit.setText(maximum)
    config=w.configuration()
    assert config.input_max==int(maximum,16 if maximum.startswith('0x') else 10)
    assert config.input_symbols==('inputs[0]','inputs[1]')

@pytest.mark.parametrize('field,value', [('maximum_edit','4294967296'),('minimum_edit','-1'),('failure_value_edit','not an integer'),('inputs_edit','bad expression + 1')])
def test_invalid_user_configuration_is_clear_and_never_dispatched(view,tmp_path,field,value):
    w,c=view; adopt(w,tmp_path)
    getattr(w,field).setText(value)
    w.start_run()
    assert c.calls==[] and not w.busy
    assert 'invalid_configuration' in w.status_label.text()

@pytest.mark.parametrize('strategy', ['enumerative','random','guided'])
def test_strategy_controls_and_explicit_metadata(view,tmp_path,strategy):
    w,c=view; adopt(w,tmp_path)
    w.strategy_combo.setCurrentText(strategy); w.seed_edit.setText('-17')
    config=w.configuration()
    assert config.seed==(None if strategy=='enumerative' else -17)
    assert w.seed_edit.isEnabled()==(strategy!='enumerative')
    assert w.archive_spin.isEnabled()==(strategy=='guided')

def test_save_and_run_are_async_responsive_and_single_admission(view,tmp_path,qtbot):
    w,c=view; project=adopt(w,tmp_path); project.delay=.15
    ticks=[]; QTimer.singleShot(10,lambda:ticks.append(True))
    w.start_run(); w.start_run()
    assert w.busy and not w.run_button.isEnabled()
    qtbot.waitUntil(lambda:bool(ticks),timeout=500)
    assert not project.saved
    qtbot.waitUntil(lambda:len(c.calls)==1,timeout=2000)
    assert len(project.saved)==1 and c.calls[0][0]=='run'
    assert c.calls[0][1]['config']==str(project.root/'commands'/'immutable-synthetic.json')
    assert w.active_run==project.root/'runs'/'run-synthetic'
    assert not w.save_button.isEnabled()

def test_storage_error_is_not_a_success_or_firmware_dispatch(view,tmp_path,qtbot):
    w,c=view; project=adopt(w,tmp_path)
    project.fail=ProductError('project_busy','Another project writer is active.')
    w.validate_configuration()
    qtbot.waitUntil(lambda:not w.busy)
    assert not c.calls and 'project_busy' in w.status_label.text()

def test_tool_check_uses_worker_and_preserves_missing_dependency(view):
    w,c=view; w.check_tools()
    assert c.calls==[('doctor',{})]
    c.finish(error={'category':'missing_dependency','message':'Install ARM-capable GDB','details':{}})
    assert 'missing_dependency' in w.status_label.text()
    assert 'Install ARM-capable GDB' in w.validation_text.toPlainText()

def test_failed_validation_record_is_not_labeled_passed(view,tmp_path,qtbot):
    w,c=view; adopt(w,tmp_path); w.validate_configuration()
    qtbot.waitUntil(lambda:c.busy)
    c.finish({'success':False,'measurement_mode':'synthetic_test'})
    assert 'operation_failed' in w.status_label.text()
    assert 'Validation passed' not in w.validation_text.toPlainText()

def test_progress_counts_exact_vectors_and_limits_table(view):
    w,c=view; w._prepare_progress(600)
    for index in range(1,503):
        w._event({'kind':'progress','payload':{'type':'trial_complete','input':[index,1],
                  'accounting':{'attempted_executions':index,'successful_executions':index,'infrastructure_failures':0},
                  'feedback':{'status':'safe','execution_signature':{'digest':'a'*64,'truncated':False}}}})
    assert w.attempts_table.rowCount()==500
    assert w.attempts_table.item(499,1).text()=='[502, 1]'
    assert w.attempts_table.item(499,2).text()=='Condition not observed'
    assert w.progress_bar.value()==502
    assert 'Charged attempts: 502' in w.accounting_label.text()

def test_failed_result_keeps_failure_classification_and_report(view):
    w,c=view
    record={'state':'failed','success':False,'outcome':'infrastructure_failure',
            'measurement_mode':'synthetic_test','execution_evidence':'incomplete',
            'triggering_input':[2,1],'accounting':{'attempted_executions':2,'infrastructure_failures':1,'successful_executions':1}}
    w.active_run=Path('/synthetic/run'); w._show_result(record)
    assert 'infrastructure failure' in w.outcome_label.text()
    assert 'Charged evaluator attempts: 2' in w.report_view.toPlainText()
    assert not w.reproduce_button.isEnabled()
    assert w.export_button.isEnabled()

def test_missing_receipts_remain_explicit_in_dashboard(view):
    w,c=view
    record={'state':'cancelled','success':False,'outcome':'cancelled','measurement_mode':'synthetic_test','execution_evidence':'incomplete','accounting':{'attempted_executions':1},'triggering_input':None}
    w._show_result(record,inspection={'result':record,'accounting_verification':{'status':'incomplete_receipts','execution_verification':'failed'}})
    assert 'verification failed: missing receipts' in w.evidence_label.text()

def test_cancellation_and_close_wait_for_cleanup_without_blocking(view,qtbot):
    w,c=view; w._start('run',{'config':'synthetic','output_dir':'synthetic'})
    w.close()
    assert c.cancelled and w.isVisible()
    assert 'Closing after cancellation' in w.status_label.text()
    c.finish(error={'category':'cancelled','message':'cancelled synthetic test','details':{}})
    qtbot.waitUntil(lambda:not w.isVisible())

def test_failed_reproduction_cannot_point_to_previous_discovery(view,tmp_path):
    w,c=view; w.active_run=tmp_path/'old'; w.result_record={'measurement_mode':'synthetic_test','triggering_input':[2,1]}
    w._start('reproduce',{'run_dir':'old','output_dir':'new'},output=tmp_path/'new')
    c.finish(error={'category':'worker_interrupted','message':'inspect the interrupted run','details':{}})
    assert w.active_run==tmp_path/'new' and w.result_record is None
    assert not w.reproduce_button.isEnabled()

def test_invalid_idle_configuration_does_not_erase_previous_result(view,tmp_path):
    w,c=view; adopt(w,tmp_path)
    w._start('run',{'config':'synthetic','output_dir':'synthetic'},output=tmp_path/'run')
    record={'state':'completed','success':True,'outcome':'domain_exhausted','measurement_mode':'synthetic_test','execution_evidence':'complete','accounting':{},'triggering_input':None}
    c.finish(record)
    w.maximum_edit.setText('bad'); w.start_run()
    assert w.result_record==record

def test_export_refuses_application_source_directory(view,monkeypatch):
    w,c=view; w.active_run=Path('/synthetic/run')
    monkeypatch.setattr(ui.QFileDialog,'getExistingDirectory',lambda *a:str(Path(ui.__file__).resolve().parents[2]))
    w.export_result()
    assert c.calls==[] and 'desktop_project_error' in w.status_label.text()


def test_runtime_verification_is_background_and_does_not_dispatch(view, monkeypatch, qtbot):
    w, ctrl = view
    from firmavex.product import runtime_pack
    monkeypatch.setattr(runtime_pack, 'active_tools', lambda: {'qemu': '/verified/tool'})
    w.verify_runtime_pack()
    qtbot.waitUntil(lambda: w._local_task is None)
    assert '/verified/tool' in w.tool_details.toPlainText()
    assert ctrl.calls == []
    assert 'do not establish native' in w.tool_status.text()


def test_runtime_setup_controls_disabled_while_execution_active(view):
    w, ctrl = view
    ctrl.busy = True
    w._refresh_enabled()
    assert not w.runtime_install_button.isEnabled()
    assert not w.runtime_verify_button.isEnabled()
