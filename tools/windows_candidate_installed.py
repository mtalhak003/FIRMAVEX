"""Disposable native Windows candidate installation checks; never admission approval.

Only an explicitly bound candidate CI run may install the unsigned application.
The installed product must reject the candidate runtime through its normal gate.
"""
import base64
import os
from pathlib import Path
import sys
import threading

from firmavex.backends.api import Limits
from firmavex.backends.process import Processes
from firmavex.backends.security import checked_path
from firmavex.product.tools import file_identity
from tools import windows_candidate_product as product
from tools import windows_runtime_candidate as candidate
from tools.versioned_install_ci import windows_installer_command

APP_ID = '{7CBBAED2-EF1B-48DD-A2B0-2C7E260B6B88}_is1'
EXECUTABLES = ('FIRMAVEX.exe', 'FIRMAVEX-Desktop.exe')


def reject_registered_installation(registry=None):
    """Read only the exact application key, in both per-user/machine views."""
    if registry is None:
        import winreg as registry
    name = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + APP_ID
    for hive in (registry.HKEY_CURRENT_USER, registry.HKEY_LOCAL_MACHINE):
        for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
            try:
                key = registry.OpenKey(hive, name, 0, registry.KEY_READ | view)
            except FileNotFoundError:
                continue
            registry.CloseKey(key)
            raise ValueError('Existing registered FIRMAVEX installation; candidate must not replace it')


def identities(directory):
    root = checked_path(directory, directory=True)
    result = {}
    for name in EXECUTABLES:
        identity = file_identity(checked_path(root / name))
        result[name] = {key: identity[key] for key in ('sha256', 'size_bytes')}
    return result


def _owned_run(args, working, *, installer=False):
    args = list(map(str, args))
    if installer:
        # Reuse the tested descendant-waiting command, passing its JSON as a
        # base64 literal rather than mutating the process-global environment.
        command, env = windows_installer_command(args, dict(os.environ))
        encoded = base64.b64encode(env['FIRMAVEX_INSTALLER_WAIT'].encode('utf-8')).decode('ascii')
        marker = '$env:FIRMAVEX_INSTALLER_WAIT'
        if command[-1].count(marker) != 1:
            raise ValueError('Unexpected installer waiter contract')
        command[-1] = command[-1].replace(marker,
            "([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')))")
        args = command
    owner = Processes(threading.Event(), Limits(timeout_seconds=90, artifact_bytes=64*1024**2,
                                                log_bytes=8*1024**2))
    try:
        code, _, _ = owner.run(args, working)
    finally:
        primary = sys.exception()
        try:
            owner.close()
        except BaseException as cleanup:
            if primary is None or (isinstance(primary, Exception) and not isinstance(cleanup, Exception)):
                raise
            primary.add_note('Candidate installed process cleanup failed: ' + type(cleanup).__name__)
    if (type(code) is not int or code != 0 or not owner.cleanup
            or not all(row.get('reaped') is True and type(row.get('pid')) is int and row['pid'] > 0
                       and type(row.get('returncode')) is int and row['returncode'] == 0 for row in owner.cleanup)):
        raise ValueError('Installed candidate process failed or was not reaped')
    return {'exit_code': code, 'owned_process_cleanup': owner.cleanup}


def run_lifecycle(vendor_root, evidence_dir, installer, frozen_directory):
    context, root, evidence = candidate._environment(Path(vendor_root), Path(evidence_dir))
    reject_registered_installation()
    installer = checked_path(installer)
    frozen = checked_path(frozen_directory, directory=True)
    identity = file_identity(installer)
    installer_identity = {key: identity[key] for key in ('sha256', 'size_bytes')}
    expected = identities(frozen)
    private = checked_path(evidence / 'installed-lifecycle', directory=True, exists=False)
    if private.exists():
        raise ValueError('Candidate installed lifecycle output already exists')
    # Keep installed application payloads outside uploaded evidence roots, even
    # if uninstall fails. Never reuse or replace an existing destination.
    destination = checked_path(evidence.parent / 'candidate installed application', directory=True, exists=False)
    if destination.exists():
        raise ValueError('Candidate installation destination already exists')
    private.mkdir()
    working = private / 'owned-process-working'; working.mkdir()
    saved = private / 'external-user-data'; saved.mkdir()
    sentinel = saved / 'preserved.txt'; sentinel.write_bytes(b'candidate user-data preservation sentinel\n')
    sentinel_identity = file_identity(sentinel)['sha256']
    report = {**context, 'schema_version': 1, 'kind': 'firmavex_candidate_installed_lifecycle',
              'candidate_only': True, 'production_qualified': False, 'status': 'failed',
              'scope': 'unsigned installation and runtime rejection; no positive product execution',
              'installer': installer_identity, 'executables': expected, 'cases': [],
              'installed_bytes_match': False, 'gui_startup': False, 'same_package_reinstall': False,
              'external_data_preserved': False, 'uninstalled_executables_absent': False}
    installation_attempted = False
    def unchanged():
        if (identities(frozen) != expected
                or file_identity(installer)['sha256'] != installer_identity['sha256']
                or file_identity(sentinel)['sha256'] != sentinel_identity):
            raise ValueError('Candidate build, installer, or external user data changed')
    def run(phase, args, *, install=False):
        row = {'phase': phase, 'exit_code': None, 'owned_process_cleanup': []}
        report['cases'].append(row)
        if install:
            args = [*args, '/LOG=' + str(working / (phase + '.log'))]
        row.update(_owned_run(args, working, installer=install))
    try:
        installation_attempted = True
        install_args = [installer, '/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                        '/NOICONS', '/DIR=' + str(destination)]
        run('install', install_args, install=True)
        if identities(destination) != expected:
            raise ValueError('Installed executables differ from reviewed frozen build')
        report['installed_bytes_match'] = True
        result = product.run_product_probe(root, evidence, executable=destination / 'FIRMAVEX.exe',
                                           distribution='installed')
        if (result.get('status') != 'candidate_admission_rejection_passed'
                or type(result.get('charged_attempts')) is not int or result['charged_attempts'] != 0
                or result.get('production_qualified') is not False):
            raise ValueError('Installed product did not preserve production rejection')
        run('gui-smoke', [destination / 'FIRMAVEX-Desktop.exe', '--smoke-test'])
        report['gui_startup'] = True
        unchanged()
        run('same-package-reinstall', install_args, install=True)
        if identities(destination) != expected:
            raise ValueError('Reinstalled executables differ from reviewed frozen build')
        report['same_package_reinstall'] = True
        unchanged()
    except BaseException as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        primary = sys.exception()
        try:
            if installation_attempted:
                uninstaller = checked_path(destination / 'unins000.exe')
                run('uninstall', [uninstaller, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], install=True)
                if any((destination / name).exists() for name in (*EXECUTABLES, 'unins000.exe')):
                    raise ValueError('Installed candidate executables remain after uninstall')
                report['uninstalled_executables_absent'] = True
                reject_registered_installation()
            unchanged()
            report['external_data_preserved'] = True
            if primary is None:
                report['status'] = 'candidate_installed_lifecycle_passed'
        except BaseException as cleanup:
            report['cleanup_error_type'] = type(cleanup).__name__
            if primary is None or (isinstance(primary, Exception) and not isinstance(cleanup, Exception)):
                primary = cleanup
                raise
            primary.add_note('Candidate installation cleanup failed: ' + type(cleanup).__name__)
        finally:
            candidate._save(private / 'installation-lifecycle.json', report, primary)
    return report
