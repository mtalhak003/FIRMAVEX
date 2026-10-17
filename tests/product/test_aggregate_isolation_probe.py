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
