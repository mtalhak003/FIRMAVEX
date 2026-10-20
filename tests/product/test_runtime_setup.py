"""Synthetic administrative tests; actual installation is qualified in native CI."""
import hashlib
import io
from pathlib import Path
import threading
import zipfile

import pytest
from firmavex.product import runtime_setup as setup
from firmavex.product.errors import ProductError


class Response(io.BytesIO):
    def geturl(self): return 'https://release-assets.githubusercontent.com/asset'


def test_download_uses_pinned_digest(tmp_path, monkeypatch):
    payload = b'synthetic-vendor-bootstrap'
    monkeypatch.setitem(setup.BOOTSTRAP, 'sha256', hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(setup.urllib.request, 'urlopen', lambda *a, **k: Response(payload))
    events = []
    setup._download(tmp_path / 'bootstrap', None, events.append)
    assert (tmp_path / 'bootstrap').read_bytes() == payload
    assert all(row['firmware_executed'] is False for row in events)


def test_bad_download_never_executes(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.urllib.request, 'urlopen', lambda *a, **k: Response(b'changed'))
    with pytest.raises(ProductError, match='checksum'):
        setup._download(tmp_path / 'bootstrap', None, None)


def test_unexpected_redirect_is_rejected(tmp_path, monkeypatch):
    class Bad(Response):
        def geturl(self): return 'http://untrusted.invalid/payload'
    monkeypatch.setattr(setup.urllib.request, 'urlopen', lambda *a, **k: Bad(b'x'))
    with pytest.raises(ProductError, match='unexpected'):
        setup._download(tmp_path / 'bootstrap', None, None)


def test_download_cancellation_is_not_swallowed(tmp_path, monkeypatch):
    event = threading.Event(); event.set()
    monkeypatch.setattr(setup.urllib.request, 'urlopen', lambda *a, **k: Response(b'x'))
    with pytest.raises(KeyboardInterrupt):
        setup._download(tmp_path / 'bootstrap', event, None)


@pytest.mark.parametrize('host', [{'os':'linux','arch':'x86_64'}, {'os':'macos','arch':'arm64'}, {'os':'windows','arch':'arm64'}])
def test_unsupported_provider_makes_no_installation(tmp_path, monkeypatch, host):
    monkeypatch.setattr(setup, 'host', lambda: host)
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=tmp_path / 'new')
    assert caught.value.category == 'runtime_provider_unavailable'
    assert not (tmp_path / 'new').exists()


def test_local_snapshot_retains_licenses_and_package_records(tmp_path):
    root = tmp_path / 'vendor'
    (root / 'bin').mkdir(parents=True)
    (root / 'bin/qemu-system-arm.exe').write_bytes(b'synthetic qemu')
    (root / 'bin/gdb-multiarch.exe').write_bytes(b'synthetic gdb')
    (root / 'bin/qemu-system-x86_64.exe').write_bytes(b'unrelated machine')
    (root / 'bin/dependency.dll').write_bytes(b'preserved shared library')
    (root / 'include').mkdir()
    (root / 'include/developer.h').write_bytes(b'not used by execution')
    (root / 'lib').mkdir()
    (root / 'lib/required.dll').write_bytes(b'needed runtime library')
    (root / 'lib/unused.a').write_bytes(b'link-time only')
    license = root / 'share/licenses/gdb/COPYING'; license.parent.mkdir(parents=True)
    license.write_text('synthetic test license')
    archive = tmp_path / 'runtime.zip'
    digest = setup.snapshot_runtime(root, archive, packages='synthetic-package 1.0')
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as contents:
        assert 'share/licenses/gdb/COPYING' in contents.namelist()
        assert 'FIRMAVEX-VENDOR-PACKAGES.json' in contents.namelist()
        assert 'bin/qemu-system-x86_64.exe' not in contents.namelist()
        assert 'bin/dependency.dll' in contents.namelist()
        assert 'bin/qemu-system-arm.exe' in contents.namelist()
        assert 'include/developer.h' not in contents.namelist()
        assert 'lib/unused.a' not in contents.namelist()
        assert 'lib/required.dll' in contents.namelist()
        assert all(not row.is_dir() for row in contents.infolist())


def test_snapshot_refuses_missing_licenses(tmp_path):
    directory = tmp_path / 'vendor'; directory.mkdir()
    (directory / 'file').write_bytes(b'x')
    with pytest.raises(ProductError, match='license'):
        setup.snapshot_runtime(directory, tmp_path / 'runtime.zip', packages='')


def test_snapshot_cancel_preserves_control_exception(tmp_path):
    directory = tmp_path / 'vendor'; directory.mkdir()
    (directory / 'file').write_bytes(b'x')
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt):
        setup.snapshot_runtime(directory, tmp_path / 'runtime.zip', packages='', cancel=event)


def test_provider_failure_keeps_existing_selection_and_cleans_temporary(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'host', lambda: {'os':'windows','arch':'x86_64'})
    root = tmp_path / 'runtime'; root.mkdir()
    (root / 'active.json').write_bytes(b'existing selection')
    def failed(*args): raise ProductError('runtime_download_failed', 'synthetic network failure')
    monkeypatch.setattr(setup, '_download', failed)
    with pytest.raises(ProductError, match='network'):
        setup.install_vendor_runtime(root=root)
    assert (root / 'active.json').read_bytes() == b'existing selection'
    assert sorted(p.name for p in root.iterdir()) == ['active.json']


def test_provider_preserves_interruption_when_cleanup_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'host', lambda: {'os':'windows','arch':'x86_64'})
    def interrupt(*args): raise KeyboardInterrupt('original cancellation')
    def denied(*args, **kwargs): raise OSError('synthetic cleanup failure')
    monkeypatch.setattr(setup, '_download', interrupt)
    monkeypatch.setattr(setup.shutil, 'rmtree', denied)
    with pytest.raises(KeyboardInterrupt, match='original cancellation') as caught:
        setup.install_vendor_runtime(root=tmp_path / 'runtime')
    assert any('cleanup' in note for note in caught.value.__notes__)


def test_private_cleanup_retries_read_only_files_only_inside_owned_tree(tmp_path, monkeypatch):
    import stat
    work = tmp_path / 'owned'; work.mkdir()
    file = work / 'read-only'; file.write_bytes(b'temporary'); file.chmod(0o444)
    calls = []
    def remove(root, *, onerror):
        def unlink(name):
            calls.append(name)
            assert Path(name).stat().st_mode & stat.S_IWRITE
            Path(name).unlink()
        onerror(unlink, str(file), (PermissionError, PermissionError('read-only'), None))
    monkeypatch.setattr(setup.shutil, 'rmtree', remove)
    setup._remove_private_tree(work)
    assert calls == [str(file)] and not file.exists()


def test_private_cleanup_never_changes_file_outside_owned_tree(tmp_path, monkeypatch):
    work = tmp_path / 'owned'; work.mkdir()
    outside = tmp_path / 'user-data'; outside.write_bytes(b'keep'); outside.chmod(0o444)
    def remove(root, *, onerror):
        onerror(lambda name: pytest.fail('modified outside file'), str(outside),
                (PermissionError, PermissionError('outside'), None))
    monkeypatch.setattr(setup.shutil, 'rmtree', remove)
    with pytest.raises(PermissionError): setup._remove_private_tree(work)
    assert outside.read_bytes() == b'keep'


@pytest.mark.parametrize('error,category', [
    (setup.urllib.error.URLError('https://user:secret@proxy.invalid'), 'runtime_download_failed'),
    (PermissionError(13, 'secret user path'), 'runtime_setup_io_failed'),
    (RuntimeError('token=secret'), 'runtime_setup_failed'),
])
def test_setup_failure_has_safe_shareable_diagnostic(tmp_path, monkeypatch, error, category):
    import json
    monkeypatch.setattr(setup, 'host', lambda: {'os': 'windows', 'arch': 'x86_64'})
    def failed(*args):
        raise error
    monkeypatch.setattr(setup, '_download', failed)
    root = tmp_path / 'runtimes'
    root.mkdir()
    (root / 'active.json').write_text('previous')
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=root)
    assert caught.value.category == category
    record = Path(caught.value.details['diagnostic_file'])
    data = json.loads(record.read_text())
    assert data['stage'] == 'download'
    assert data['exception_type'] == type(error).__name__
    assert data['traceback'][-1]['function'] == 'failed'
    assert data['firmware_executed'] is False
    assert 'secret' not in record.read_text() + str(caught.value.to_dict())
    assert (root / 'active.json').read_text() == 'previous'
    assert sorted(p.name for p in root.iterdir()) == ['active.json']


def test_diagnostic_write_failure_preserves_classification(tmp_path, monkeypatch):
    def failed(**kwargs):
        raise setup.urllib.error.HTTPError('https://private.invalid', 403, 'secret', {}, None)
    def denied(*args):
        raise PermissionError('secret')
    monkeypatch.setattr(setup, '_install_vendor_runtime', failed)
    monkeypatch.setattr(setup, '_write_diagnostic', denied)
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=tmp_path / 'runtimes')
    assert caught.value.category == 'runtime_download_failed'
    assert caught.value.details['diagnostic_write_failed'] is True
    assert 'secret' not in str(caught.value.to_dict())


def test_http_status_is_saved_without_url_or_headers(tmp_path, monkeypatch):
    import json
    def failed(**kwargs):
        kwargs['event_callback']({'stage': 'download'})
        raise setup.urllib.error.HTTPError('https://user:secret@example.invalid', 403,
                                           'secret', {'Authorization': 'secret'}, None)
    monkeypatch.setattr(setup, '_install_vendor_runtime', failed)
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=tmp_path / 'runtimes')
    text = Path(caught.value.details['diagnostic_file']).read_text()
    assert json.loads(text)['http_status'] == 403
    assert 'secret' not in text


@pytest.mark.parametrize('linked_component', ['application', 'installation-diagnostics'])
def test_diagnostic_rejects_linked_directory(tmp_path, linked_component):
    outside = tmp_path / 'outside'; outside.mkdir()
    application = tmp_path / 'application'
    if linked_component == 'application':
        link = application
    else:
        application.mkdir()
        link = application / linked_component
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks is unavailable on this host')
    with pytest.raises(OSError, match='Linked'):
        setup._write_diagnostic(application / 'runtimes', {})
    assert list(outside.iterdir()) == []


def test_diagnostic_rejects_traversal(tmp_path):
    with pytest.raises(OSError, match='Unsafe'):
        setup._write_diagnostic(tmp_path / '..' / 'runtimes', {})


def test_diagnostic_exclusive_creation_preserves_existing_file(tmp_path, monkeypatch):
    directory = tmp_path / 'installation-diagnostics'; directory.mkdir()
    existing = directory / 'runtime-setup-collision.json'
    existing.write_text('keep')
    # Exercise the writer with an existing candidate filename. The real mkstemp
    # retries collisions; its exclusive flag must never be replaced by rename.
    def collide(**kwargs):
        descriptor = __import__('os').open(existing, __import__('os').O_CREAT |
                                          __import__('os').O_EXCL | __import__('os').O_WRONLY, 0o600)
        return descriptor, str(existing)
    monkeypatch.setattr(setup.tempfile, 'mkstemp', collide)
    with pytest.raises(FileExistsError):
        setup._write_diagnostic(tmp_path / 'runtimes', {})
    assert existing.read_text() == 'keep'


def test_early_storage_failure_still_saves_diagnostic(tmp_path, monkeypatch):
    import json
    root = tmp_path / 'runtimes'
    root.write_text('not a directory')
    monkeypatch.setattr(setup, 'host', lambda: {'os': 'windows', 'arch': 'x86_64'})
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=root)
    record = json.loads(Path(caught.value.details['diagnostic_file']).read_text())
    assert record['stage'] == 'initialization'
    assert record['category'] == 'runtime_setup_io_failed'
    assert root.read_text() == 'not a directory'


def test_cleanup_progress_does_not_mask_failure_stage(tmp_path, monkeypatch):
    def failed(**kwargs):
        callback = kwargs['event_callback']
        callback({'stage': 'signed runtime package installation'})
        callback({'stage': 'private vendor agent cleanup'})
        raise ProductError('runtime_vendor_install_failed', 'Package installation failed.', {'return_code': 7})
    monkeypatch.setattr(setup, '_install_vendor_runtime', failed)
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=tmp_path / 'runtimes')
    assert caught.value.details['stage'] == 'signed runtime package installation'


def test_diagnostic_rejects_windows_reparse_attribute(tmp_path, monkeypatch):
    from types import SimpleNamespace
    application = tmp_path / 'application'; application.mkdir()
    original = Path.lstat
    def metadata(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == application:
            return SimpleNamespace(st_mode=result.st_mode,
                                   st_file_attributes=setup.stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return result
    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(OSError, match='Linked'):
        setup._write_diagnostic(application / 'runtimes', {})
    assert not (application / 'installation-diagnostics').exists()


def test_signed_package_failure_saves_safe_output_and_log_before_cleanup(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(setup, 'host', lambda: {'os': 'windows', 'arch': 'x86_64'})
    monkeypatch.setattr(setup, '_download', lambda *args: None)
    root = tmp_path / 'User with spaces' / 'runtimes'
    root.mkdir(parents=True)
    (root / 'active.json').write_text('previous')
    calls = []

    def run(command, *, stage, callback, **kwargs):
        calls.append(stage)
        callback({'stage': stage})
        if stage == 'signed runtime package installation':
            msys = next(root.glob('vendor-setup-*')) / 'msys64'
            log = msys / 'var/log/pacman.log'
            log.parent.mkdir(parents=True)
            log.write_text('[ALPM] permission denied: C:\\Users\\Alice\\secret\n'
                           '[ALPM] token=private-token\n')
            raise ProductError('runtime_vendor_install_failed', 'Package installation failed.', {
                'return_code': 23,
                'stdout': 'Authorization: Bearer secret-bearer\n' +
                          'error: failed to commit transaction (invalid or corrupted package)\n',
                'stderr': "error: failed retrieving file 'mingw-w64-ucrt-x86_64-qemu' from "
                          'https://user:password@mirror.invalid/private?token=secret-query : '
                          'The requested URL returned error: 503\n',
            })
        return ''

    monkeypatch.setattr(setup, '_run', run)
    monkeypatch.setattr(setup, 'snapshot_runtime', lambda *a, **k: pytest.fail('snapshot after failure'))
    monkeypatch.setattr(setup, 'install', lambda *a, **k: pytest.fail('activation after failure'))
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=root)
    text = Path(caught.value.details['diagnostic_file']).read_text()
    record = json.loads(text)
    assert record['return_code'] == 23
    assert caught.value.details['return_code'] == 23
    assert record['stage'] == 'signed runtime package installation'
    vendor = record['vendor_diagnostics']
    assert vendor['stdout'] == ['failed to commit transaction; invalid or corrupted package']
    assert vendor['stderr'] == ['failed retrieving file; mingw-w64-ucrt-x86_64-qemu; HTTP 503']
    assert vendor['pacman_log'] == ['permission denied']
    for secret in ('Alice', 'secret', 'password', 'mirror.invalid', 'private-token', 'Authorization'):
        assert secret not in text + str(caught.value.to_dict())
    assert calls[-1] == 'signed runtime package installation'
    assert (root / 'active.json').read_text() == 'previous'
    assert list(root.iterdir()) == [root / 'active.json']


def test_vendor_projection_omits_unknown_secrets_and_bounds_output():
    raw = ('ghp_unlabelledsecret /home/alice/private C:\\Users\\Alice\\private '
           'https://user:password@host/?token=secret \x1b[31m\n'
           'error: target not found: unlabelledsecret\n')
    assert setup._vendor_diagnostic(raw) == ['target not found']
    assert setup._vendor_diagnostic('unknown secret text') == []
    assert setup._vendor_diagnostic(None) == []
    rows = setup._vendor_diagnostic('\n'.join(setup._VENDOR_ERRORS))
    assert len(rows) == 16
    assert setup._vendor_diagnostic('target not found\n' + 'x' * 32768) == []


def test_run_preserves_actual_vendor_exit_code_and_cleans_process(monkeypatch):
    from types import SimpleNamespace
    from firmavex.product import runtime
    process = SimpleNamespace(returncode=37, poll=lambda: 37)
    output = SimpleNamespace(thread=SimpleNamespace(join=lambda **kwargs: None),
                             text=lambda: 'error: target not found: secret')
    monkeypatch.setattr(runtime, '_spawn', lambda *a, **k: (process, output, output))
    cleaned = []
    def cleanup(children, original):
        cleaned.append(original)
        return {'success': True}
    monkeypatch.setattr(runtime, '_cleanup', cleanup)
    with pytest.raises(ProductError) as caught:
        setup._run(['pacman'], cancel=None, callback=None,
                   stage='signed runtime package installation')
    assert caught.value.details['return_code'] == 37
    assert caught.value.details['stderr'] == output.text()
    assert cleaned == [caught.value]


def test_pacman_log_tail_is_bounded_and_missing_log_is_optional(tmp_path):
    assert setup._pacman_log_tail(tmp_path) == ''
    log = tmp_path / 'var/log/pacman.log'
    log.parent.mkdir(parents=True)
    log.write_bytes(b'old secret\n' + b'x' * 40000 + b'\nerror: permission denied\n')
    text = setup._pacman_log_tail(tmp_path)
    assert len(text) == 32768
    assert 'old secret' not in text
    assert setup._vendor_diagnostic(text) == ['permission denied']


def test_pacman_log_rejects_linked_directory(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'pacman.log').write_text('error: permission denied')
    (tmp_path / 'var').mkdir()
    try:
        (tmp_path / 'var/log').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks is unavailable on this host')
    assert setup._pacman_log_tail(tmp_path) == ''


def test_package_diagnostic_write_failure_keeps_exit_code_and_failure(tmp_path, monkeypatch):
    def failed(**kwargs):
        kwargs['event_callback']({'stage': 'signed runtime package installation'})
        raise ProductError('runtime_vendor_install_failed', 'Package installation failed.',
                           {'return_code': 41, 'stderr': 'permission denied: secret'})
    def denied(*args):
        raise PermissionError('private storage path')
    monkeypatch.setattr(setup, '_install_vendor_runtime', failed)
    monkeypatch.setattr(setup, '_write_diagnostic', denied)
    with pytest.raises(ProductError) as caught:
        setup.install_vendor_runtime(root=tmp_path / 'runtimes')
    assert caught.value.category == 'runtime_vendor_install_failed'
    assert caught.value.details['return_code'] == 41
    assert caught.value.details['diagnostic_write_failed'] is True
    assert 'secret' not in str(caught.value.to_dict())
    assert 'private storage path' not in str(caught.value.to_dict())


def test_windows_workflow_collects_only_diagnostic_json_with_spaces(tmp_path):
    import glob
    workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/desktop-beta.yml').read_text()
    block = workflow.split('      - name: Retain sanitized installation diagnostics\n', 1)[1].split('      - uses:', 1)[0]
    assert 'if: failure()' in block
    assert 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02' in block
    pattern = block.split('          path: ', 1)[1].splitlines()[0]
    assert pattern == '${{ runner.temp }}/FIRMAVEX user with spaces/FIRMAVEX/installation-diagnostics/runtime-setup-*.json'
    directory = tmp_path / 'FIRMAVEX user with spaces/FIRMAVEX/installation-diagnostics'
    directory.mkdir(parents=True)
    diagnostic = setup._write_diagnostic(directory.parent / 'runtimes', {'return_code': 23})
    (directory / 'vendor-raw.log').write_text('secret')
    (directory.parent / 'bootstrap.exe').write_bytes(b'private')
    assert glob.glob(pattern.replace('${{ runner.temp }}', str(tmp_path))) == [str(diagnostic)]
