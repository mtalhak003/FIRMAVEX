import json
import io
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import versioned_install_ci as v
from firmavex.product.errors import ProductError
from firmavex.product import platform_support as policy


def test_refuses_personal_machine_installer_changes(tmp_path,monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
    with pytest.raises(ValueError,match='Disposable'):v.Qualification(tmp_path,tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_snapshot_detects_changed_authoritative_files(tmp_path):
    (tmp_path/'result.json').write_text('{"authoritative":true}')
    (tmp_path/'run.sqlite3').write_bytes(b'synthetic fixture, not real firmware evidence')
    before=v.snapshot(tmp_path)
    assert before==v.snapshot(tmp_path)
    (tmp_path/'run.sqlite3').write_bytes(b'changed')
    assert before!=v.snapshot(tmp_path)


def test_environment_restored_after_control_flow(monkeypatch):
    import os
    monkeypatch.setenv('FIRMAVEX_TEST_ORIGINAL','present')
    with pytest.raises(KeyboardInterrupt):
        with v.environment({'FIRMAVEX_TEST_REPLACEMENT':'temporary'}):
            assert 'FIRMAVEX_TEST_ORIGINAL' not in os.environ
            raise KeyboardInterrupt('preserve')
    assert os.environ['FIRMAVEX_TEST_ORIGINAL']=='present'
    assert 'FIRMAVEX_TEST_REPLACEMENT' not in os.environ


def test_receipt_failure_does_not_replace_cancellation(tmp_path,monkeypatch):
    qualification=object.__new__(v.Qualification)
    qualification.revision='test';qualification.rows=[];qualification.root=tmp_path
    def interrupted(self):raise KeyboardInterrupt('original cancellation')
    monkeypatch.setattr(v.Qualification,'linux',interrupted)
    monkeypatch.setattr(v.Qualification,'windows',interrupted)
    def failed(*a,**k):raise OSError('no storage')
    monkeypatch.setattr(Path,'write_bytes',failed)
    with pytest.raises(KeyboardInterrupt,match='original cancellation') as found:qualification.execute()
    assert 'persistence failed' in ' '.join(found.value.__notes__)


def test_cleanup_failure_preserves_original_cancellation():
    def failed():raise OSError('cleanup denied')
    with pytest.raises(KeyboardInterrupt,match='original') as found:
        with v.preserving_cleanup(failed):raise KeyboardInterrupt('original')
    assert 'cleanup denied' in ' '.join(found.value.__notes__)
    with pytest.raises(OSError,match='cleanup denied'):
        with v.preserving_cleanup(failed):pass


def test_installer_commands_resolve_before_strict_process_admission(monkeypatch,tmp_path):
    tool=tmp_path/'native-tool';tool.write_bytes(b'fixture')
    observed=[]
    def which(name, *, path):
        observed.append((name,path));return str(tool) if name=='native-tool' else None
    monkeypatch.setattr(v.shutil,'which',which)
    assert v.absolute_command(['native-tool','literal argument'],{'PATH':'selected-path'})==[str(tool.resolve()),'literal argument']
    assert observed==[('native-tool','selected-path')]
    with pytest.raises(ValueError,match='unavailable'):v.absolute_command(['missing-tool'],{'PATH':'selected-path'})


def test_native_installer_waiter_keeps_arguments_as_data_and_waits_descendants(tmp_path,monkeypatch):
    shell=tmp_path/'pwsh';shell.write_bytes(b'not executed synthetic fixture')
    monkeypatch.setattr(v.shutil,'which',lambda *args,**kwargs:str(shell))
    args=[str(tmp_path/'installer with spaces.exe'),'/LOG='+str(tmp_path/'a;literal.log'),'/VERYSILENT']
    command,env=v.windows_installer_command(args,{'PATH':'selected'})
    assert command[0]==str(shell.resolve())
    assert command[-1]==v.INSTALLER_WAIT_SCRIPT
    assert '-Wait -PassThru' in command[-1]
    assert args[0] not in command[-1]
    value=json.loads(env['FIRMAVEX_INSTALLER_WAIT'])
    assert value=={'executable':args[0],'command_line':v.subprocess.list2cmdline(args[1:])}
    assert env['PATH']=='selected'


@pytest.mark.parametrize('removed',[False,True])
def test_uninstaller_parent_exit_alone_cannot_qualify_removal(tmp_path,removed):
    qualification=object.__new__(v.Qualification)
    qualification.logs=tmp_path;qualification.rows=[{}]
    destination=tmp_path/'application';destination.mkdir()
    engine=destination/'FIRMAVEX.exe';engine.write_bytes(b'synthetic fixture')
    def run(*args):
        if removed:engine.unlink()
        return 0,'',''
    qualification.run=run
    checked=[];qualification.unchanged=lambda:checked.append(True)
    if removed:
        qualification.uninstall_windows('uninstall',destination)
        assert checked==[True]
        assert qualification.rows[-1]['installed_executables_absent'] is True
    else:
        with pytest.raises(RuntimeError,match='left installed executables'):
            qualification.uninstall_windows('uninstall',destination)
        assert not checked
        assert 'installed_executables_absent' not in qualification.rows[-1]


# Invented failure receipts only: none of these cases installs or executes tools.


@pytest.fixture
def synthetic_lifecycle(tmp_path, monkeypatch):
    qualification=object.__new__(v.Qualification)
    qualification.revision='synthetic-revision'
    qualification.rows=[]
    qualification.root=tmp_path
    qualification.saved_hashes={'synthetic-result': 'a' * 64}
    state=SimpleNamespace(error=None, calls=0)
    def operate(self):
        state.calls+=1
        if state.error is not None:
            raise state.error
        return {'measurement': 'synthetic test fixture, not installer acceptance'}
    monkeypatch.setattr(v.Qualification,'linux',operate)
    monkeypatch.setattr(v.Qualification,'windows',operate)
    def no_process(*args, **kwargs):
        raise AssertionError('Synthetic lifecycle receipt attempted process dispatch')
    monkeypatch.setattr(v.subprocess,'Popen',no_process)
    return qualification,state


def qualification_claim():
    identities={name: {'version':version,'sha256':digest}
                for name,(version,digest) in policy.WINDOWS_EXECUTABLES.items()}
    return policy._qualification_details(identities,'AMD64')


def gate_error(value):
    return ProductError('unsupported_platform','Synthetic qualified runtime rejection',
                        {'qualification':value})


def execute_failure(synthetic_lifecycle, error):
    qualification,state=synthetic_lifecycle
    state.error=error
    with pytest.raises(type(error)) as caught:
        qualification.execute()
    assert caught.value is error
    assert state.calls==1
    record=json.loads((qualification.root/'versioned-lifecycle.json').read_bytes())
    assert record['passed'] is False
    assert record['failure']['type']==type(error).__name__
    assert record['failure']['diagnostic']==str(error)
    return record


@pytest.mark.parametrize('role', ['qemu','gdb'])
def test_failed_gate_retains_recomputed_runtime_identity_comparison(synthetic_lifecycle,role):
    claim=qualification_claim()
    observed=claim['tools'][role]['observed']
    observed.update(version='QEMU emulator version 11.1.3' if role=='qemu' else 'GNU gdb (GDB) 18.2',
                    sha256='f' * 64)
    before=deepcopy(claim)
    record=execute_failure(synthetic_lifecycle,gate_error(claim))
    diagnostic=record['failure']['runtime_qualification']
    assert diagnostic['required_profile']==policy.WINDOWS_PROFILE_ID
    assert diagnostic['profile_version']==policy.WINDOWS_PROFILE_VERSION
    for name,(version,digest) in policy.WINDOWS_EXECUTABLES.items():
        row=diagnostic['tools'][name]
        assert row['expected']=={'version':version,'sha256':digest}
        assert row['matches']==dict.fromkeys(('version','sha256'), name!=role)
        assert row['observed']==claim['tools'][name]['observed']
    assert diagnostic['host_architecture']=='x86_64'
    assert claim==before


@pytest.mark.parametrize('tools', [None, [], {}, {'qemu':None,'gdb':[]},
                                  {'qemu':{'observed':[]},'gdb':{'observed':'private path'}}],
                         ids=['none','list','empty','malformed-rows','malformed-observations'])
def test_missing_or_malformed_identity_containers_remain_unavailable(synthetic_lifecycle,tools):
    claim=qualification_claim();claim['tools']=tools
    record=execute_failure(synthetic_lifecycle,gate_error(claim))
    for row in record['failure']['runtime_qualification']['tools'].values():
        assert row['observed']=={'version':None,'sha256':None}
        assert row['matches']=={'version':None,'sha256':None}


@pytest.mark.parametrize('value', [None, [], {}, {'schema_version':True},
    {**qualification_claim(),'schema_version':True},
    {**qualification_claim(),'schema_version':2},
    {**qualification_claim(),'profile_version':True},
    {**qualification_claim(),'profile_version':2},
    {**qualification_claim(),'required_profile':'unapproved-runtime-profile'},
    {**qualification_claim(),'required_profile':None}],
    ids=['none','list','empty','partial','bool-schema','future-schema','bool-profile-version',
         'future-profile-version','unknown-profile','missing-profile'])
def test_unsupported_runtime_diagnostic_contract_is_not_projected(synthetic_lifecycle,value):
    record=execute_failure(synthetic_lifecycle,gate_error(value))
    assert 'runtime_qualification' not in record['failure']


def test_runtime_projection_ignores_private_metadata_and_untrusted_expected_matches(synthetic_lifecycle):
    marker='PRIVATE-CREDENTIAL-DO-NOT-COPY'
    claim=qualification_claim()
    claim.update(host_architecture=marker,environment={'secret':marker},path=marker)
    for role in ('qemu','gdb'):
        claim['tools'][role].update(expected={'version':marker,'sha256':marker},
                                  matches={'version':False,'sha256':False},path=marker)
        claim['tools'][role]['observed'].update(path=marker,environment={'TOKEN':marker})
    claim['tools']['unexpected']={'observed':{'version':marker,'sha256':marker}}
    error=gate_error(claim)
    error.details.update(environment={'TOKEN':marker},executable_path=marker)
    record=execute_failure(synthetic_lifecycle,error)
    assert marker not in json.dumps(record)
    comparison=record['failure']['runtime_qualification']
    assert comparison['host_architecture']=='unknown'
    assert set(comparison['tools'])=={'qemu','gdb'}
    for role in ('qemu','gdb'):
        version,digest=policy.WINDOWS_EXECUTABLES[role]
        assert comparison['tools'][role]['expected']=={'version':version,'sha256':digest}
        assert comparison['tools'][role]['matches']=={'version':True,'sha256':True}
        assert set(comparison['tools'][role]['observed'])=={'version','sha256'}


@pytest.mark.parametrize('observed', [
    {'version':r'C:\Private\credential.exe','sha256':'not a digest'},
    {'version':'QEMU emulator version 11.1.3\nPRIVATE-CREDENTIAL','sha256':'F' * 64},
    {'version':None,'sha256':True},
    {'version':{'private':'metadata'},'sha256':[]}],
    ids=['path','multiline-upperhex','missing-bool','malformed-fields'])
def test_malformed_identity_values_are_omitted_not_echoed(synthetic_lifecycle,observed):
    claim=qualification_claim()
    claim['tools']['qemu']['observed']=observed
    record=execute_failure(synthetic_lifecycle,gate_error(claim))
    row=record['failure']['runtime_qualification']['tools']['qemu']
    assert row['observed']=={'version':None,'sha256':None}
    assert row['matches']=={'version':None,'sha256':None}
    encoded=json.dumps(record)
    assert 'PRIVATE-CREDENTIAL' not in encoded and 'credential.exe' not in encoded


def test_successful_lifecycle_does_not_project_runtime_failure(synthetic_lifecycle,monkeypatch):
    qualification,state=synthetic_lifecycle
    def forbidden(*args):raise AssertionError('Successful lifecycle requested failure projection')
    monkeypatch.setattr(v,'_runtime_qualification_failure',forbidden)
    result=qualification.execute()
    assert result['passed'] is True and 'failure' not in result
    assert state.calls==1
    saved=json.loads((qualification.root/'versioned-lifecycle.json').read_bytes())
    assert saved==result


@pytest.mark.parametrize('error', [KeyboardInterrupt('synthetic cancellation'),SystemExit(31),
                                  BaseException('synthetic control')],
                         ids=['keyboard','exit','base'])
def test_original_control_flow_skips_optional_projection(synthetic_lifecycle,monkeypatch,error):
    def forbidden(*args):raise AssertionError('Cancellation requested runtime projection')
    monkeypatch.setattr(v,'_runtime_qualification_failure',forbidden)
    record=execute_failure(synthetic_lifecycle,error)
    assert 'runtime_qualification' not in record['failure']


@pytest.mark.parametrize('error', [RuntimeError('synthetic generic failure'),
    ProductError('missing_dependency','Synthetic missing tool',{'qualification':qualification_claim()})],
    ids=['ordinary','other-category'])
def test_unrelated_failure_does_not_acquire_runtime_identity_claim(synthetic_lifecycle,monkeypatch,error):
    def forbidden(*args):raise AssertionError('Unrelated failure requested qualification projection')
    monkeypatch.setattr(v,'_runtime_qualification_failure',forbidden)
    record=execute_failure(synthetic_lifecycle,error)
    assert 'runtime_qualification' not in record['failure']


def test_optional_projection_error_preserves_original_gate_failure(synthetic_lifecycle,monkeypatch):
    error=gate_error(qualification_claim())
    def failed(*args):raise OSError('PRIVATE-PROJECTION-DETAIL')
    monkeypatch.setattr(policy,'_qualification_details',failed)
    record=execute_failure(synthetic_lifecycle,error)
    assert 'runtime_qualification' not in record['failure']
    assert record['failure']['runtime_qualification_status']=='projection_unavailable'
    assert 'PRIVATE-PROJECTION-DETAIL' not in json.dumps(record)
    assert error.__notes__==['Runtime qualification identity projection was unavailable.']


@pytest.mark.parametrize('control',[KeyboardInterrupt('projection interruption'),SystemExit(37)],
                         ids=['keyboard','exit'])
def test_new_projection_control_flow_is_not_silently_converted_to_gate_result(synthetic_lifecycle,monkeypatch,control):
    qualification,state=synthetic_lifecycle
    state.error=gate_error(qualification_claim())
    def interrupted(*args):raise control
    monkeypatch.setattr(policy,'_qualification_details',interrupted)
    with pytest.raises(type(control)) as caught:
        qualification.execute()
    assert caught.value is control
    record=json.loads((qualification.root/'versioned-lifecycle.json').read_bytes())
    assert record['passed'] is False
    assert 'runtime_qualification' not in record['failure']


@pytest.mark.parametrize('role',['qemu','gdb'])
@pytest.mark.parametrize('field',['version','sha256'])
def test_runtime_projection_recomputes_each_identity_field_independently(synthetic_lifecycle,role,field):
    claim=qualification_claim()
    observed=claim['tools'][role]['observed']
    observed[field]=('QEMU emulator version 11.1.3' if role=='qemu' else 'GNU gdb (GDB) 18.2') if field=='version' else 'e' * 64
    claim['tools'][role]['matches']={'version':True,'sha256':True}
    record=execute_failure(synthetic_lifecycle,gate_error(claim))
    matches=record['failure']['runtime_qualification']['tools'][role]['matches']
    assert matches=={name:name!=field for name in ('version','sha256')}


@pytest.fixture
def synthetic_main(tmp_path,monkeypatch):
    """CLI dispatch is stubbed: these cases never install, probe or run firmware."""
    state=SimpleNamespace(error=None,result={'passed':True,'measurement':'synthetic'},calls=[])
    def execute():
        if state.error is not None:raise state.error
        return state.result
    def qualification(*paths):
        state.calls.append(paths)
        return SimpleNamespace(execute=execute)
    monkeypatch.setattr(v,'Qualification',qualification)
    monkeypatch.setattr(v.subprocess,'Popen',lambda *a,**k:pytest.fail('Synthetic CLI dispatched a process'))
    def invoke():
        result=v.main(['--baseline',str(tmp_path/'baseline'),'--candidate',str(tmp_path/'candidate'),
                       '--output',str(tmp_path/'output')])
        assert len(state.calls)==1
        assert not (tmp_path/'output').exists()
        return result
    return state,invoke


def public_comparison(output):
    prefix='::notice title=Windows runtime admission rejected::'
    rows=[line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)]
    assert len(rows)==1
    return json.loads(rows[0]),rows[0]


@pytest.mark.parametrize('role',['qemu','gdb'])
@pytest.mark.parametrize('field',['version','sha256'])
def test_cli_publishes_recomputed_rejected_runtime_comparison(synthetic_main,capsys,role,field):
    state,invoke=synthetic_main
    claim=qualification_claim()
    claim['tools'][role]['observed'][field]=('QEMU emulator version 11.1.3' if role=='qemu'
        else 'GNU gdb (GDB) 18.2') if field=='version' else 'a'*64
    state.error=gate_error(claim)
    before=deepcopy(claim)
    assert invoke()==1
    output=capsys.readouterr().out
    assert output.startswith('::error title=Versioned installer qualification::'+str(state.error)+'\n')
    value,encoded=public_comparison(output)
    assert value['admission']=='rejected'
    assert encoded==json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'))
    comparison=value['comparison']
    for name,(version,digest) in policy.WINDOWS_EXECUTABLES.items():
        row=comparison['tools'][name]
        assert row['expected']=={'version':version,'sha256':digest}
        assert row['observed']==claim['tools'][name]['observed']
        assert row['matches']=={key:not (name==role and key==field) for key in ('version','sha256')}
    assert claim==before


def test_cli_all_matching_tools_still_reports_rejection_without_qualification(synthetic_main,capsys):
    state,invoke=synthetic_main
    claim=qualification_claim();claim['host_architecture']='arm64'
    state.error=gate_error(claim)
    assert invoke()==1
    value,_=public_comparison(capsys.readouterr().out)
    assert value['admission']=='rejected'
    assert value['comparison']['host_architecture']=='arm64'
    assert all(all(row['matches'].values()) for row in value['comparison']['tools'].values())
    assert 'passed' not in value


@pytest.mark.parametrize('tools',[None,[],{}, {'qemu':{'observed':[]},'gdb':None}],
                         ids=['missing','list','empty','malformed'])
def test_cli_missing_observations_remain_unknown(synthetic_main,capsys,tools):
    state,invoke=synthetic_main
    claim=qualification_claim();claim['tools']=tools
    state.error=gate_error(claim)
    assert invoke()==1
    value,_=public_comparison(capsys.readouterr().out)
    for row in value['comparison']['tools'].values():
        assert row['observed']=={'version':None,'sha256':None}
        assert row['matches']=={'version':None,'sha256':None}


@pytest.mark.parametrize('claim',[None,[],{},
    {**qualification_claim(),'schema_version':True},
    {**qualification_claim(),'profile_version':2},
    {**qualification_claim(),'required_profile':'unknown-profile'}],
    ids=['missing','list','empty','bool-schema','future-version','unknown-profile'])
def test_cli_unsupported_contract_publishes_no_comparison(synthetic_main,capsys,claim):
    state,invoke=synthetic_main;state.error=gate_error(claim)
    assert invoke()==1
    output=capsys.readouterr().out
    assert output.count('::error title=Versioned installer qualification::')==1
    assert '::notice' not in output


def test_cli_comparison_drops_private_details_and_untrusted_expected_fields(synthetic_main,capsys):
    state,invoke=synthetic_main;claim=qualification_claim()
    marker='PRIVATE-CREDENTIAL-DO-NOT-PUBLISH'
    claim.update(host_architecture=marker,environment={'TOKEN':marker},vendor_packages=marker)
    for row in claim['tools'].values():
        row.update(expected={'version':marker,'sha256':marker},matches={'version':False,'sha256':False},path=marker)
        row['observed'].update(path=marker,environment=marker)
    state.error=gate_error(claim);state.error.details['raw_vendor_output']=marker
    assert invoke()==1
    output=capsys.readouterr().out
    assert marker not in output
    value,_=public_comparison(output)
    assert value['comparison']['host_architecture']=='unknown'
    assert set(value)=={'admission','comparison'}
    assert all(all(row['matches'].values()) for row in value['comparison']['tools'].values())


@pytest.mark.parametrize('error',[RuntimeError('synthetic unrelated failure'),
    ProductError('missing_dependency','synthetic missing tool',{'qualification':qualification_claim()})],
    ids=['ordinary','other-category'])
def test_cli_unrelated_failure_has_no_runtime_notice(synthetic_main,capsys,error):
    state,invoke=synthetic_main;state.error=error
    assert invoke()==1
    assert '::notice' not in capsys.readouterr().out


def test_cli_success_is_unchanged_and_has_no_runtime_notice(synthetic_main,capsys,monkeypatch):
    state,invoke=synthetic_main
    monkeypatch.setattr(v,'_runtime_qualification_failure',lambda *a:pytest.fail('Success requested failure diagnostics'))
    assert invoke()==0
    output=capsys.readouterr().out
    assert json.loads(output)==state.result
    assert '::notice' not in output and '::error' not in output


@pytest.mark.parametrize('error',[KeyboardInterrupt('synthetic CLI cancellation'),SystemExit(31),
                                  BaseException('synthetic CLI control')],ids=['keyboard','exit','base-control'])
def test_cli_original_control_flow_is_not_an_ordinary_failure(synthetic_main,capsys,error):
    state,invoke=synthetic_main;state.error=error
    with pytest.raises(type(error)) as caught:invoke()
    assert caught.value is error
    assert capsys.readouterr().out==''


def test_cli_optional_projection_error_keeps_rejection_and_hides_error_text(synthetic_main,capsys,monkeypatch):
    state,invoke=synthetic_main;state.error=gate_error(qualification_claim())
    def failed(*args):raise OSError('PRIVATE-PROJECTION-ERROR')
    monkeypatch.setattr(v,'_runtime_qualification_failure',failed)
    assert invoke()==1
    output=capsys.readouterr().out
    assert '::error title=Versioned installer qualification::'+str(state.error) in output
    assert output.endswith('::notice title=Windows runtime admission rejected::comparison unavailable\n')
    assert 'PRIVATE-PROJECTION-ERROR' not in output


@pytest.mark.parametrize('control',[KeyboardInterrupt('projection cancellation'),SystemExit(37),
                                   BaseException('projection control')],ids=['keyboard','exit','base-control'])
def test_cli_projection_control_flow_propagates(synthetic_main,capsys,monkeypatch,control):
    state,invoke=synthetic_main;state.error=gate_error(qualification_claim())
    def interrupted(*args):raise control
    monkeypatch.setattr(v,'_runtime_qualification_failure',interrupted)
    with pytest.raises(type(control)) as caught:invoke()
    assert caught.value is control
    output=capsys.readouterr().out
    assert output.startswith('::error title=Versioned installer qualification::')
    assert '::notice' not in output


def test_cli_failure_console_uses_existing_cp1252_safe_renderer(synthetic_main,monkeypatch):
    state,invoke=synthetic_main
    state.error=ProductError('unsupported_platform','synthetic \ufffd caf\u00e9 %\nsecond line',
                             {'qualification':qualification_claim()})
    data=io.BytesIO()
    stream=io.TextIOWrapper(data,encoding='cp1252',errors='strict',newline='',write_through=True)
    with monkeypatch.context() as patch:
        patch.setattr(v.sys,'stdout',stream)
        assert invoke()==1
    output=data.getvalue().decode('cp1252')
    assert 'synthetic \\ufffd caf\u00e9 %25%0Asecond line' in output
    assert public_comparison(output)[0]['admission']=='rejected'
