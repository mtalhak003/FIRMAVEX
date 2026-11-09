"""Synthetic lifecycle regressions do not establish native installer support."""
import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import windows_candidate_installed as installed


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    vendor = tmp_path / 'vendor'; vendor.mkdir()
    evidence = tmp_path / 'source-probe'; evidence.mkdir()
    frozen = tmp_path / 'frozen'; frozen.mkdir()
    for name in installed.EXECUTABLES:
        (frozen / name).write_bytes(('synthetic not executable ' + name).encode())
    installer = tmp_path / 'installer.exe'; installer.write_bytes(b'synthetic installer not executed')
    context = {'source_revision': 'a'*40, 'run_id': '123', 'host': {'os': 'synthetic_test'}}
    monkeypatch.setattr(installed.candidate, '_environment', lambda *args: (context, vendor, evidence))
    monkeypatch.setattr(installed, 'reject_registered_installation', lambda: None)
    monkeypatch.setattr(installed.product, 'run_product_probe', lambda *args, **kwargs: {
        'status': 'candidate_admission_rejection_passed', 'charged_attempts': 0, 'production_qualified': False})
    destination = evidence.parent / 'candidate installed application'
    calls = []
    def run(args, working, *, installer=False):
        calls.append((list(map(str, args)), working, installer))
        if any(str(arg).startswith('/DIR=') for arg in args):
            destination.mkdir(exist_ok=True)
            for name in installed.EXECUTABLES:
                (destination / name).write_bytes((frozen / name).read_bytes())
            (destination / 'unins000.exe').write_bytes(b'synthetic uninstaller')
        elif Path(args[0]).name == 'unins000.exe':
            for name in (*installed.EXECUTABLES, 'unins000.exe'):
                (destination / name).unlink()
        return {'exit_code': 0, 'owned_process_cleanup': [{'pid': 123, 'returncode': 0, 'reaped': True}]}
    monkeypatch.setattr(installed, '_owned_run', run)
    return SimpleNamespace(vendor=vendor, evidence=evidence, frozen=frozen, installer=installer,
                           destination=destination, calls=calls, run=run)


def execute(fixture):
    return installed.run_lifecycle(fixture.vendor, fixture.evidence, fixture.installer, fixture.frozen)


def retained(fixture):
    return json.loads((fixture.evidence / 'installed-lifecycle/installation-lifecycle.json').read_text())


def test_synthetic_lifecycle_checks_installed_bytes_rejection_startup_and_removal(lifecycle):
    report = execute(lifecycle)
    assert report['status'] == 'candidate_installed_lifecycle_passed'
    assert report['candidate_only'] is True and report['production_qualified'] is False
    assert report['host'] == {'os': 'synthetic_test'}
    assert [row['phase'] for row in report['cases']] == ['install', 'gui-smoke', 'same-package-reinstall', 'uninstall']
    assert all(report[key] is True for key in ('installed_bytes_match', 'gui_startup', 'same_package_reinstall',
                                              'external_data_preserved', 'uninstalled_executables_absent'))
    assert report == retained(lifecycle)
    assert not (lifecycle.destination / 'FIRMAVEX.exe').exists()
    assert (lifecycle.evidence / 'installed-lifecycle/external-user-data/preserved.txt').exists()
    assert '/NOICONS' in lifecycle.calls[0][0]
    assert lifecycle.calls[1][0][-1] == '--smoke-test'
    assert all(working.name == 'owned-process-working' for _, working, _ in lifecycle.calls)
    for args, working, installer in lifecycle.calls:
        if installer:
            assert sum(arg.startswith('/LOG=') for arg in args) == 1
            log = Path(next(arg[5:] for arg in args if arg.startswith('/LOG=')))
            assert log.parent == working


def test_native_context_checked_before_registry_or_directory_mutation(lifecycle, monkeypatch):
    def reject(*args): raise ValueError('native context required')
    monkeypatch.setattr(installed.candidate, '_environment', reject)
    monkeypatch.setattr(installed, 'reject_registered_installation', lambda: pytest.fail('No registry access yet'))
    with pytest.raises(ValueError, match='native context'): execute(lifecycle)
    assert not (lifecycle.evidence / 'installed-lifecycle').exists()


def test_registered_installation_stops_before_install_or_mutation(lifecycle, monkeypatch):
    def reject(): raise ValueError('Existing installation')
    monkeypatch.setattr(installed, 'reject_registered_installation', reject)
    with pytest.raises(ValueError, match='Existing'): execute(lifecycle)
    assert lifecycle.calls == [] and not (lifecycle.evidence / 'installed-lifecycle').exists()


def test_existing_lifecycle_directory_is_preserved(lifecycle):
    private = lifecycle.evidence / 'installed-lifecycle'; private.mkdir()
    saved = private / 'keep'; saved.write_bytes(b'unchanged')
    with pytest.raises(ValueError, match='already exists'): execute(lifecycle)
    assert saved.read_bytes() == b'unchanged' and not lifecycle.calls


def test_existing_installation_destination_is_never_reused(lifecycle):
    lifecycle.destination.mkdir()
    saved = lifecycle.destination / 'keep'; saved.write_bytes(b'unchanged')
    with pytest.raises(ValueError, match='destination already exists'): execute(lifecycle)
    assert saved.read_bytes() == b'unchanged' and not lifecycle.calls
    assert not (lifecycle.evidence / 'installed-lifecycle').exists()


@pytest.mark.parametrize('name', installed.EXECUTABLES)
def test_installed_executable_mismatch_fails_and_uninstalls(lifecycle, monkeypatch, name):
    def changed(args, working, **kwargs):
        result = lifecycle.run(args, working, **kwargs)
        if any(str(arg).startswith('/DIR=') for arg in args):
            (lifecycle.destination / name).write_bytes(b'different installed executable')
        return result
    monkeypatch.setattr(installed, '_owned_run', changed)
    with pytest.raises(ValueError, match='differ'): execute(lifecycle)
    report = retained(lifecycle)
    assert report['status'] == 'failed' and report['uninstalled_executables_absent'] is True
    assert report['gui_startup'] is False


@pytest.mark.parametrize('change', [{'status': 'unexpected'}, {'charged_attempts': 1},
                                  {'charged_attempts': False}, {'production_qualified': True}])
def test_unexpected_product_outcome_cannot_pass_lifecycle(lifecycle, monkeypatch, change):
    result = {'status': 'candidate_admission_rejection_passed', 'charged_attempts': 0,
              'production_qualified': False, **change}
    monkeypatch.setattr(installed.product, 'run_product_probe', lambda *args, **kwargs: result)
    with pytest.raises(ValueError, match='preserve production rejection'): execute(lifecycle)
    assert retained(lifecycle)['status'] == 'failed'
    assert retained(lifecycle)['uninstalled_executables_absent'] is True


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize('cleanup_failure', [False, True])
def test_interruption_is_preserved_and_report_never_passes(lifecycle, monkeypatch, control, cleanup_failure):
    def interrupt(*args, **kwargs): raise control('original candidate interruption')
    monkeypatch.setattr(installed.product, 'run_product_probe', interrupt)
    def run(args, working, **kwargs):
        if cleanup_failure and Path(args[0]).name == 'unins000.exe': raise OSError('uninstall fixture')
        return lifecycle.run(args, working, **kwargs)
    monkeypatch.setattr(installed, '_owned_run', run)
    with pytest.raises(control, match='original candidate interruption') as found: execute(lifecycle)
    report = retained(lifecycle)
    assert report['status'] == 'failed' and report['error_type'] == control.__name__
    if cleanup_failure:
        assert report['cleanup_error_type'] == 'OSError'
        assert 'cleanup failed' in ' '.join(found.value.__notes__)
    else:
        assert report['uninstalled_executables_absent'] is True


@pytest.mark.parametrize('fault', ['uninstall', 'remaining', 'sentinel', 'installer', 'frozen'])
def test_final_verification_failures_cannot_report_success(lifecycle, monkeypatch, fault):
    def run(args, working, **kwargs):
        if Path(args[0]).name == 'unins000.exe':
            if fault == 'uninstall': raise OSError('uninstall fixture')
            if fault == 'remaining': return {'exit_code': 0, 'owned_process_cleanup': []}
        result = lifecycle.run(args, working, **kwargs)
        if Path(args[0]).name == 'FIRMAVEX-Desktop.exe':
            target = {'sentinel': lifecycle.evidence / 'installed-lifecycle/external-user-data/preserved.txt',
                      'installer': lifecycle.installer, 'frozen': lifecycle.frozen / 'FIRMAVEX.exe'}.get(fault)
            if target: target.write_bytes(b'observable changed bytes')
        return result
    monkeypatch.setattr(installed, '_owned_run', run)
    with pytest.raises((OSError, ValueError)): execute(lifecycle)
    assert retained(lifecycle)['status'] == 'failed'


@pytest.mark.parametrize('symlink_target', ['installer', 'frozen'])
def test_unsafe_input_paths_rejected_before_installation(lifecycle, symlink_target):
    if os.name == 'nt': pytest.skip('Symlink construction permission is platform-specific')
    original = getattr(lifecycle, symlink_target)
    linked = original.with_name(original.name + '-link'); linked.symlink_to(original, target_is_directory=original.is_dir())
    setattr(lifecycle, symlink_target, linked)
    with pytest.raises(ValueError, match='Symlink'): execute(lifecycle)
    assert not lifecycle.calls


@pytest.mark.parametrize('present', [None, (1, 32), (1, 64), (2, 32), (2, 64)])
def test_only_exact_application_registry_keys_are_checked(present):
    calls = []; closed = []
    def open_key(hive, name, reserved, access):
        calls.append((hive, name, reserved, access))
        if (hive, access & 96) == present: return 'found'
        raise FileNotFoundError
    registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=1,
        KEY_WOW64_32KEY=32, KEY_WOW64_64KEY=64, OpenKey=open_key, CloseKey=closed.append)
    if present is None: installed.reject_registered_installation(registry)
    else:
        with pytest.raises(ValueError, match='Existing registered'): installed.reject_registered_installation(registry)
    assert all(name == 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + installed.APP_ID
               and reserved == 0 for _, name, reserved, _ in calls)
    assert closed == ([] if present is None else ['found'])


def test_registry_access_denial_fails_closed():
    def denied(*args): raise PermissionError('fixture denial')
    registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_READ=1,
        KEY_WOW64_32KEY=32, KEY_WOW64_64KEY=64, OpenKey=denied)
    with pytest.raises(PermissionError): installed.reject_registered_installation(registry)


def test_installer_waiter_uses_data_literal_without_environment_mutation(tmp_path, monkeypatch):
    import os
    original = dict(os.environ)
    payload = json.dumps({'executable': 'installer with spaces.exe', 'command_line': '/literal=$data'})
    monkeypatch.setattr(installed, 'windows_installer_command', lambda *args: (
        ['pwsh', '-Command', '$invocation=ConvertFrom-Json $env:FIRMAVEX_INSTALLER_WAIT'],
        {'FIRMAVEX_INSTALLER_WAIT': payload}))
    observed = []
    class Owner:
        def __init__(self, cancel, limits): self.cleanup = []
        def run(self, args, cwd): observed.extend(args); return 0, '', ''
        def close(self): self.cleanup = [{'pid': 123, 'returncode': 0, 'reaped': True}]
    monkeypatch.setattr(installed, 'Processes', Owner)
    installed._owned_run(['installer', '/literal=$data'], tmp_path, installer=True)
    assert dict(os.environ) == original
    script = observed[-1]
    assert '$env:FIRMAVEX_INSTALLER_WAIT' not in script and '/literal=$data' not in script
    assert base64.b64encode(payload.encode()).decode() in script


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_owned_process_cleanup_preserves_original_interruption(tmp_path, monkeypatch, control):
    class Owner:
        def __init__(self, *args): pass
        def run(self, *args): raise control('original interrupted process')
        def close(self): raise OSError('cleanup fixture')
    monkeypatch.setattr(installed, 'Processes', Owner)
    with pytest.raises(control, match='original interrupted process') as found:
        installed._owned_run(['fixture'], tmp_path)
    assert found.value.__notes__ == ['Candidate installed process cleanup failed: OSError']


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_interrupted_initial_install_without_uninstaller_retains_failed_report(lifecycle, monkeypatch, control):
    def interrupt(args, working, **kwargs):
        lifecycle.destination.mkdir()
        (lifecycle.destination / 'partial-payload').write_bytes(b'partial synthetic install')
        raise control('original interrupted initial installation')
    monkeypatch.setattr(installed, '_owned_run', interrupt)
    with pytest.raises(control, match='original interrupted initial installation') as found:
        execute(lifecycle)
    report = retained(lifecycle)
    assert report['status'] == 'failed' and report['error_type'] == control.__name__
    assert report['cleanup_error_type'] == 'FileNotFoundError'
    assert report['uninstalled_executables_absent'] is False
    assert report['external_data_preserved'] is False  # Final verification did not complete.
    assert [row['phase'] for row in report['cases']] == ['install']
    assert 'cleanup failed' in ' '.join(found.value.__notes__)
    assert (lifecycle.destination / 'partial-payload').read_bytes() == b'partial synthetic install'


@pytest.mark.parametrize('fault', ['exit', 'bool', 'no-cleanup', 'not-reaped'])
def test_owned_process_bad_exit_or_cleanup_is_rejected(tmp_path, monkeypatch, fault):
    class Owner:
        def __init__(self, *args): self.cleanup = []
        def run(self, *args): return (1 if fault == 'exit' else False if fault == 'bool' else 0), '', ''
        def close(self):
            if fault != 'no-cleanup': self.cleanup = [{'pid': 123, 'returncode': 0, 'reaped': fault != 'not-reaped'}]
    monkeypatch.setattr(installed, 'Processes', Owner)
    with pytest.raises(ValueError, match='failed or was not reaped'):
        installed._owned_run(['fixture'], tmp_path)


def test_native_windows_candidate_installed_lifecycle():
    if os.environ.get('FIRMAVEX_RUN_WINDOWS_CANDIDATE') != '1':
        pytest.skip('Explicit native Windows candidate workflow required')
    if os.sys.platform != 'win32': pytest.fail('Installed lifecycle requires native Windows')
    required = ('FIRMAVEX_CANDIDATE_INSTALLER', 'FIRMAVEX_CANDIDATE_FROZEN_DIR')
    if not all(os.environ.get(name) for name in required):
        if os.environ.get('FIRMAVEX_REQUIRE_CANDIDATE_INSTALLED') == '1':
            pytest.fail('Required installed candidate inputs missing')
        pytest.skip('Installed candidate inputs not requested')
    report = installed.run_lifecycle(Path(os.environ['FIRMAVEX_CANDIDATE_VENDOR']),
        Path(os.environ['FIRMAVEX_CANDIDATE_ROOT']) / 'source-probe',
        Path(os.environ['FIRMAVEX_CANDIDATE_INSTALLER']), Path(os.environ['FIRMAVEX_CANDIDATE_FROZEN_DIR']))
    assert report['status'] == 'candidate_installed_lifecycle_passed'
    assert report['production_qualified'] is False
