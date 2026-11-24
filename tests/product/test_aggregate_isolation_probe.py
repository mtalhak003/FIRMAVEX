import json
from pathlib import Path
import sys
import pytest
from tools import aggregate_isolation_probe as p


def test_fixed_commands_have_independent_quotas():
    command=p.unit_command('test.service','runner','pids',source='/checkout',python='/python',namespace_output='/output')
    for flag in ('--property=MemoryMax=128M','--property=TasksMax=8','--property=CPUQuota=50%',
                 '--property=ProtectControlGroups=yes','--property=User=runner','--property=KillMode=control-group'):
        assert flag in command
    assert '--wait' not in command  # RemainAfterExit would otherwise keep --wait blocked.
    assert '--service-type=exec' in command
    with pytest.raises(ValueError):p.unit_command('test','runner','arbitrary',source='/',python='/',namespace_output='/')


def test_missing_supervisor_is_blocked_not_qualified(tmp_path,monkeypatch):
    monkeypatch.setattr(p,'admission',lambda:{'linux':True,'administrator':False,'systemd_running':False,'systemd_run_available':True})
    result=p.assess(source=Path(p.__file__).resolve().parents[1],python=sys.executable,user='runner',output=tmp_path/'out')
    assert result['status']=='blocked'
    assert result['untrusted_execution_authorized'] is False
    assert result['checks']=={}
    assert json.loads((tmp_path/'out/assessment.json').read_text())['status']=='blocked'


def test_no_arbitrary_python_or_source_launch(tmp_path):
    with pytest.raises(ValueError,match='Only this checkout'):
        p.assess(source=tmp_path,python=sys.executable,user='runner',output=tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_memory_probe_touches_pages_and_fork_probe_is_bounded():
    assert '4096' in p.GUESTS['memory']
    assert 'range(16)' in p.GUESTS['pids']
    assert 'waitpid' in p.GUESTS['pids']
    for code in p.GUESTS.values():compile(code,'fixed_guest','exec')
    for mode in (*p.GUESTS,'namespace'):
        command=p.unit_command('fixed.service','runner',mode,source='/checkout',python='/python',namespace_output='/output/guest/namespace.json')
        compile(command[-1],'fixed_bootstrap','exec')
        assert 'Supervisor admission not granted' in command[-1]


@pytest.mark.parametrize('fault',['quota','cleanup'])
def test_synthetic_supervisor_failure_aborts_later_admissions(tmp_path,monkeypatch,fault):
    # Simulated systemd API exercises fail-closed orchestration only. It is not
    # native cgroup enforcement or sandbox qualification evidence.
    from types import SimpleNamespace
    monkeypatch.setattr(p,'admission',lambda:{'linux':True,'administrator':True,'systemd_running':True,'systemd_run_available':True})
    monkeypatch.setattr(p,'guest_account',lambda user:SimpleNamespace(pw_uid=1234,pw_gid=1234))
    monkeypatch.setattr(p.os,'chown',lambda *args:None,raising=False)
    admitted=[]
    def run(command,**kwargs):
        if command[0]=='systemd-run':
            admitted.append(command)
            path=Path(next(v.split('append:',1)[1] for v in command if v.startswith('--property=StandardOutput=')))
            path.write_text(json.dumps({'wall':2.0,'cpu':1.0}))
            return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        if command[:2]==['systemctl','show']:
            if 'MemoryMax' in command:
                fields={'ActiveState':'active','SubState':'exited','MemoryMax':'1' if fault=='quota' else str(128*1024**2),
                        'MemorySwapMax':'0','TasksMax':'64','CPUQuotaPerSecUSec':'500ms','ExecMainStatus':'0','ExecMainCode':'1'}
                return SimpleNamespace(returncode=0,stdout='\n'.join(k+'='+v for k,v in fields.items())+'\n')
            return SimpleNamespace(returncode=0,stdout='ActiveState=inactive\nControlGroup=\n')
        return SimpleNamespace(returncode=1 if fault=='cleanup' and command[1]=='stop' else 0,stdout='',stderr='')
    monkeypatch.setattr(p.subprocess,'run',run)
    result=p.assess(source=Path(p.__file__).resolve().parents[1],python=sys.executable,user='runner',output=tmp_path/'out')
    assert result['status']=='failed'
    assert result['untrusted_execution_authorized'] is False
    assert len(admitted)==1
    assert result['units'][0]['cleanup_verified'] is (fault!='cleanup')


class SyntheticControl(BaseException):
    """Invented control flow; never a native enforcement result."""


@pytest.fixture
def synthetic_failure(tmp_path,monkeypatch):
    # No systemd process or guest is launched. Inject faults through the existing
    # supervisor boundary while retaining actual assessment persistence.
    from types import SimpleNamespace
    state=SimpleNamespace(primary=RuntimeError('synthetic supervisor failure'),
                          cleanup=None,persistence=None,admitted=[],writes=[],output=tmp_path/'out')
    monkeypatch.setattr(p,'admission',lambda:{'linux':True,'administrator':True,
        'systemd_running':True,'systemd_run_available':True})
    monkeypatch.setattr(p,'guest_account',lambda user:SimpleNamespace(pw_uid=1234,pw_gid=1234))
    monkeypatch.setattr(p.os,'chown',lambda *args:None,raising=False)
    def run(command,**kwargs):
        if command[0]=='systemd-run':
            state.admitted.append(command)
            return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        if command[:2]==['systemctl','show']:
            if 'MemoryMax' in command:
                raise state.primary
            return SimpleNamespace(returncode=0,stdout='ActiveState=inactive\nControlGroup=\n')
        if command[:2]==['systemctl','stop']:
            if state.cleanup is not None:raise state.cleanup
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        if command[:2]==['systemctl','reset-failed']:
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        pytest.fail('Unexpected supervisor command')
    monkeypatch.setattr(p.subprocess,'run',run)
    write=Path.write_text
    def write_text(path,data,*args,**kwargs):
        if path==state.output/'assessment.json':
            state.writes.append(json.loads(data))
            if state.persistence is not None:raise state.persistence
        return write(path,data,*args,**kwargs)
    monkeypatch.setattr(Path,'write_text',write_text)
    return state


def assess_synthetic(state):
    return p.assess(source=Path(p.__file__).resolve().parents[1],python=sys.executable,
                    user='synthetic',output=state.output)


def assert_no_later_probe(state):
    assert len(state.admitted)==1
    assert len(state.writes)==1
    record=state.writes[0]
    assert len(record['units'])==1
    assert record['status']=='failed'
    assert record['untrusted_execution_authorized'] is False
    assert record['sandbox_qualification']=='not_established'
    return record


@pytest.mark.parametrize('factory',[KeyboardInterrupt,SystemExit,SyntheticControl],
                         ids=['keyboard','exit','other-control'])
@pytest.mark.parametrize('stage',['cleanup','persistence'])
def test_new_control_flow_overrides_ordinary_failure_without_later_admission(synthetic_failure,factory,stage):
    state=synthetic_failure
    control=factory('synthetic secondary interruption')
    setattr(state,stage,control)
    with pytest.raises(type(control)) as caught:
        assess_synthetic(state)
    assert caught.value is control
    assert any(repr(state.primary) in note and 'interrupted after:' in note for note in control.__notes__)
    record=assert_no_later_probe(state)
    if stage=='cleanup':
        assert record['diagnostic']==repr(control)
        assert record['units'][0]['cleanup_verified'] is False
        assert record['units'][0]['cleanup_failure']==repr(control)
        assert json.loads((state.output/'assessment.json').read_text())==record
    else:
        assert record['diagnostic']==repr(state.primary)
        assert record['units'][0]['cleanup_verified'] is True
        assert not (state.output/'assessment.json').exists()


@pytest.mark.parametrize('primary_factory',[KeyboardInterrupt,SystemExit,SyntheticControl],
                         ids=['keyboard-primary','exit-primary','other-primary'])
@pytest.mark.parametrize('secondary_factory',[OSError,KeyboardInterrupt,SystemExit,SyntheticControl],
                         ids=['ordinary-secondary','keyboard-secondary','exit-secondary','other-secondary'])
@pytest.mark.parametrize('stage',['cleanup','persistence'])
def test_original_control_identity_wins_over_secondary_faults(synthetic_failure,primary_factory,secondary_factory,stage):
    state=synthetic_failure
    state.primary=primary_factory('synthetic primary control')
    secondary=secondary_factory('synthetic secondary fault')
    setattr(state,stage,secondary)
    with pytest.raises(type(state.primary)) as caught:
        assess_synthetic(state)
    assert caught.value is state.primary
    assert any(repr(secondary) in note for note in state.primary.__notes__)
    record=assert_no_later_probe(state)
    assert record['diagnostic']==repr(state.primary)
    if stage=='cleanup':
        assert record['units'][0]['cleanup_verified'] is False
        assert record['units'][0]['cleanup_failure']==repr(secondary)
        assert json.loads((state.output/'assessment.json').read_text())==record
    else:
        assert record['units'][0]['cleanup_verified'] is True
        assert not (state.output/'assessment.json').exists()


@pytest.mark.parametrize('stage',['cleanup','persistence'])
def test_ordinary_secondary_failure_preserves_failed_assessment_semantics(synthetic_failure,stage):
    state=synthetic_failure
    error=OSError('synthetic ordinary secondary failure')
    setattr(state,stage,error)
    result=assess_synthetic(state)
    assert result==assert_no_later_probe(state)
    assert result['diagnostic']==repr(state.primary)
    assert any(repr(error) in note for note in state.primary.__notes__)
    if stage=='cleanup':
        assert result['units'][0]['cleanup_verified'] is False
        assert json.loads((state.output/'assessment.json').read_text())==result
    else:
        assert not (state.output/'assessment.json').exists()


@pytest.mark.parametrize('factory',[KeyboardInterrupt,SystemExit,SyntheticControl],
                         ids=['keyboard','exit','other-control'])
def test_cleanup_control_survives_later_ordinary_persistence_failure(synthetic_failure,factory):
    state=synthetic_failure
    state.cleanup=factory('synthetic cleanup control')
    state.persistence=OSError('synthetic persistence failure')
    with pytest.raises(type(state.cleanup)) as caught:
        assess_synthetic(state)
    assert caught.value is state.cleanup
    assert any(repr(state.primary) in note for note in state.cleanup.__notes__)
    assert any(repr(state.persistence) in note for note in state.cleanup.__notes__)
    assert assert_no_later_probe(state)['diagnostic']==repr(state.cleanup)


def test_original_control_wins_across_both_secondary_control_failures(synthetic_failure):
    state=synthetic_failure
    state.primary=KeyboardInterrupt('synthetic original cancellation')
    state.cleanup=SystemExit('synthetic cleanup termination')
    state.persistence=SyntheticControl('synthetic persistence control')
    with pytest.raises(KeyboardInterrupt) as caught:
        assess_synthetic(state)
    assert caught.value is state.primary
    assert any(repr(state.cleanup) in note for note in state.primary.__notes__)
    assert any(repr(state.persistence) in note for note in state.primary.__notes__)
    assert assert_no_later_probe(state)['diagnostic']==repr(state.primary)
