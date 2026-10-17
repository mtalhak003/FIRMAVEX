import json
from pathlib import Path
import pytest
from tools import versioned_install_ci as v


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
