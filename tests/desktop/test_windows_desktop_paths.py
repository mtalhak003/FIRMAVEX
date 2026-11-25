"""Desktop filesystem contracts, with actual Win32 checks on Windows only.

The bundled ELF is inspected/imported but never executed. GUI controller records
are explicitly synthetic. Native file sharing/attributes/locking tests do not
establish QEMU/GDB compatibility or consumer-machine acceptance.
"""
from contextlib import contextmanager
from dataclasses import replace
import ctypes
import hashlib
import os
import subprocess
import sys
import tempfile
import time

import pytest
from PySide6.QtCore import QUrl

from firmavex.desktop import projects, recents, window as ui
from firmavex.desktop.projects import DesktopProject
from firmavex.desktop.workflow import confirmed_export
from firmavex.product.bundled_example import prepare_example
from firmavex.product.config import load_config
from firmavex.product.errors import ProductError
from tests.desktop.test_batch29_exports import response
from tests.desktop.test_window import view


native_windows = pytest.mark.skipif(
    sys.platform != 'win32', reason='Actual Windows file sharing, attributes and locking required')


@pytest.fixture
def bundled_project(tmp_path):
    prepared = prepare_example(tmp_path / 'bundled image source')
    assert prepared['firmware_executed'] is False
    config = load_config(prepared['config_file'])
    project = DesktopProject.create(tmp_path / 'project résumé #1 & notes', config.firmware, config)
    return project


def project_bytes(project, *, include_lock=True):
    """Inspect only this newly created temporary project, never checkout data."""
    return {str(path.relative_to(project.root)): path.read_bytes()
            for path in project.root.rglob('*')
            if path.is_file() and (include_lock or path.name != '.project.lock')}


def test_real_bundled_elf_import_and_readonly_reopen_at_unicode_windows_friendly_path(
        bundled_project):
    project = bundled_project
    before = project_bytes(project)
    reopened = DesktopProject.open(project.root)
    config = reopened.load_config()
    identity = projects.inspect_elf(config)
    assert config.firmware == project.firmware_path
    assert identity['firmware_sha256'] == hashlib.sha256(project.firmware_path.read_bytes()).hexdigest()
    assert config.input_symbols == ('product_inputs[0]', 'product_inputs[1]')
    assert config.ready_breakpoint == 'product_input_ready'
    assert config.completion_breakpoint == 'product_complete'
    assert project_bytes(project) == before


def test_open_export_folder_routes_literal_local_url_without_running_a_command(view, tmp_path, qtbot, monkeypatch):
    window, controller = view
    exported = tmp_path / 'report résumé #1 & notes'
    exported.mkdir()
    calls = []
    # Capture the actual Qt URL; do not open Explorer or any other OS application.
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda url: calls.append(QUrl(url)) or True)
    window._last_export = exported
    assert window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy, timeout=5000)
    assert len(calls) == 1
    assert calls[0].scheme() == 'file' and calls[0].isLocalFile()
    assert calls[0].query() == '' and calls[0].fragment() == ''
    assert os.path.samefile(calls[0].toLocalFile(), exported)
    assert '%23' in calls[0].toString(QUrl.ComponentFormattingOption.FullyEncoded)
    assert controller.calls == []


@pytest.mark.parametrize('kind', ['missing', 'file', 'file-parent'])
def test_invalid_export_folder_is_not_opened_and_a_valid_retry_succeeds(
        view, tmp_path, qtbot, monkeypatch, kind):
    window, controller = view
    original = tmp_path / 'original file'; original.write_bytes(b'preserve user bytes')
    selected = {'missing': tmp_path / 'missing folder', 'file': original,
                'file-parent': original / 'child'}[kind]
    calls = []
    monkeypatch.setattr(ui.QDesktopServices, 'openUrl', lambda url: calls.append(QUrl(url)) or True)
    window._last_export = selected
    assert window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy, timeout=5000)
    assert calls == []
    assert 'Next:' in window.status_label.text()
    assert original.read_bytes() == b'preserve user bytes'
    valid = tmp_path / 'valid report folder'; valid.mkdir()
    window._last_export = valid
    assert window.open_export_folder()
    qtbot.waitUntil(lambda: not window.busy, timeout=5000)
    assert len(calls) == 1 and os.path.samefile(calls[0].toLocalFile(), valid)
    assert controller.calls == []


def _kernel32():
    """Declare pointer-sized ABI explicitly; never load a fake Win32 API."""
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    api.GetFileAttributesW.restype = wintypes.DWORD
    api.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    api.SetFileAttributesW.restype = wintypes.BOOL
    return api


@contextmanager
def deny_delete_sharing(path):
    api = _kernel32()
    # GENERIC_READ; FILE_SHARE_READ|FILE_SHARE_WRITE (deliberately no DELETE);
    # OPEN_EXISTING; FILE_ATTRIBUTE_NORMAL. Other readers remain admitted.
    handle = api.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not api.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


@native_windows
@pytest.mark.parametrize('operation', ['clear', 'forget'])
def test_windows_recent_index_sharing_violation_preserves_bytes_then_retry_succeeds(tmp_path, operation):
    root = tmp_path / 'preferences résumé'; selected = tmp_path / 'project shortcut'
    recents.remember(root, selected)
    index = root / 'recent-projects.json'; original = index.read_bytes()
    def apply():
        return recents.clear(root) if operation == 'clear' else recents.forget(root, selected)
    with deny_delete_sharing(index):
        with pytest.raises(PermissionError) as error:
            apply()
        assert error.value.winerror in {5, 32}  # Access denied / sharing violation.
        assert index.read_bytes() == original and recents.load(root) == [str(selected)]
        assert list(root.glob('*.tmp')) == []
    apply()
    assert recents.load(root) == []


@native_windows
def test_windows_readonly_recent_preferences_remain_intact_until_explicit_attribute_repair(tmp_path):
    root = tmp_path / 'preferences'; selected = tmp_path / 'project shortcut'
    recents.remember(root, selected)
    index = root / 'recent-projects.json'; original = index.read_bytes()
    api = _kernel32()
    attributes = api.GetFileAttributesW(str(index))
    assert attributes != 0xFFFFFFFF, ctypes.get_last_error()
    assert api.SetFileAttributesW(str(index), attributes | 1), ctypes.get_last_error()
    try:
        with pytest.raises(PermissionError) as error:
            recents.clear(root)
        assert error.value.winerror == 5
        assert index.read_bytes() == original and recents.load(root) == [str(selected)]
        assert list(root.glob('*.tmp')) == []
    finally:
        assert api.SetFileAttributesW(str(index), attributes), ctypes.get_last_error()
    recents.clear(root)
    assert recents.load(root) == []


WINDOWS_PROJECT_WRITER_SCRIPT = '''
import msvcrt, pathlib, sys
with open(sys.argv[1], 'r+b') as stream:
    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        ready = pathlib.Path(sys.argv[2])
        pending = ready.with_name(ready.name + '.pending')
        with pending.open('x', encoding='ascii') as marker:
            marker.write('locked')
        pending.rename(ready)
        sys.stdin.buffer.readline()
    finally:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
'''


@contextmanager
def competing_windows_project_writer(project, temporary):
    """A real second interpreter holds one byte; no subprocess can wait forever."""
    ready = temporary / 'writer-ready'
    pending = ready.with_name(ready.name + '.pending')
    assert not ready.exists() and not pending.exists(), 'Expected fresh readiness markers'
    with tempfile.TemporaryFile() as diagnostics:
        process = subprocess.Popen([sys.executable, '-B', '-c', WINDOWS_PROJECT_WRITER_SCRIPT,
                                    str(project.root / '.project.lock'), str(ready)],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=diagnostics, cwd=temporary)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists():
                if process.poll() is not None:
                    diagnostics.seek(0)
                    pytest.fail('Windows writer failed before locking: ' + diagnostics.read().decode('utf-8', 'replace'))
                if time.monotonic() >= deadline:
                    pytest.fail('Windows writer did not confirm lock within 10 seconds')
                time.sleep(0.02)
            assert ready.read_text(encoding='ascii') == 'locked'
            yield
        finally:
            try:
                process.communicate(b'release\n', timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            assert process.poll() is not None


@pytest.mark.parametrize('fault', ['none', 'write', 'publish'])
def test_windows_writer_marker_publication_is_complete_or_absent(tmp_path, monkeypatch, fault):
    """Same producer script, simulated Win32 lock API; no native locking claim."""
    from types import SimpleNamespace
    from pathlib import Path
    lock = tmp_path / '.project.lock'; lock.write_bytes(b'0')
    ready = tmp_path / 'writer-ready'; pending = tmp_path / 'writer-ready.pending'
    locks = []; handles = []; waited = []
    def locking(fd, operation, count):
        assert count == 1 and os.lseek(fd, 0, os.SEEK_CUR) == 0
        locks.append(operation)
    native = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setitem(sys.modules, 'msvcrt', native)
    monkeypatch.setattr(sys, 'argv', ['synthetic writer', str(lock), str(ready)])
    def release():
        assert ready.read_bytes() == b'locked' and not pending.exists()
        waited.append(True)
        return b'release\n'
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=SimpleNamespace(readline=release)))
    original_open, original_rename = Path.open, Path.rename
    class PartialMarker:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): return self.handle.__exit__(*args)
        def write(self, text):
            assert text == 'locked'
            self.handle.write(text[:2]); self.handle.flush()
            assert pending.read_bytes() == b'lo' and not ready.exists()
            if fault == 'write': raise OSError('synthetic incomplete marker write')
            return 2 + self.handle.write(text[2:])
    def opened(path, mode='r', *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == pending and mode == 'x':
            handles.append(handle)
            return PartialMarker(handle)
        return handle
    def publish(path, target):
        assert path == pending and target == ready
        assert handles[0].closed and pending.read_bytes() == b'locked'
        assert not ready.exists() and locks == [native.LK_NBLCK]
        if fault == 'publish': raise OSError('synthetic marker publication failure')
        return original_rename(path, target)
    monkeypatch.setattr(Path, 'open', opened)
    monkeypatch.setattr(Path, 'rename', publish)
    if fault == 'none':
        exec(WINDOWS_PROJECT_WRITER_SCRIPT, {})
        assert ready.read_bytes() == b'locked' and waited == [True]
    else:
        with pytest.raises(OSError, match='synthetic'):
            exec(WINDOWS_PROJECT_WRITER_SCRIPT, {})
        assert not ready.exists() and waited == []
    assert handles[0].closed and locks == [native.LK_NBLCK, native.LK_UNLCK]
    assert lock.read_bytes() == b'0'


@pytest.mark.parametrize('name', ['writer-ready', 'writer-ready.pending'])
def test_windows_writer_rejects_stale_markers_before_process_start(tmp_path, monkeypatch, name):
    from types import SimpleNamespace
    stale = tmp_path / name; stale.write_bytes(b'preserve')
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Stale marker started child'))
    with pytest.raises(AssertionError, match='fresh readiness markers'):
        with competing_windows_project_writer(SimpleNamespace(root=tmp_path), tmp_path):
            pytest.fail('Stale marker announced ownership')
    assert stale.read_bytes() == b'preserve'


@native_windows
def test_windows_other_process_writer_blocks_save_but_not_readonly_open_and_allows_retry(
        bundled_project, tmp_path):
    project = bundled_project
    # Windows byte-range locks deny reading the lock byte from another handle.
    # Compare all project content except that live ownership primitive.
    before = project_bytes(project, include_lock=False)
    config = project.load_config()
    with competing_windows_project_writer(project, tmp_path):
        reopened = DesktopProject.open(project.root)
        assert reopened.load_config() == config
        with pytest.raises(ProductError) as error:
            project.save_config(replace(config, execution_budget=17))
        assert error.value.category == 'project_busy'
        assert project_bytes(project, include_lock=False) == before
    assert (project.root / '.project.lock').read_bytes() == b'0'
    project.save_config(replace(config, execution_budget=17))
    assert project.load_config().execution_budget == 17
    assert len(list((project.root / 'configurations').iterdir())) == 2


@native_windows
@pytest.mark.parametrize('backend', [False, True])
def test_windows_export_confirmation_accepts_case_spelling_but_not_another_directory(tmp_path, backend):
    requested = tmp_path / 'Export résumé with spaces'
    requested.mkdir()
    record = response(requested, backend)
    field = 'destination' if backend else 'output_directory'
    # Vary only a controlled ASCII segment, not an arbitrary Unicode username
    # or volume path (Unicode uppercase can expand characters such as ß).
    record[field] = str(requested.with_name('EXPORT résumé with spaces'))
    assert confirmed_export(record, requested, backend=backend) == requested
    record[field] = str(tmp_path / 'different export')
    assert confirmed_export(record, requested, backend=backend) is None
