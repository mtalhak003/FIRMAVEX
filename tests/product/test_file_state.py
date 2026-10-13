"""Native path/handle consistency without firmware measurements."""
import os
import sys
import time
import pytest
from firmavex.product.file_state import path_state,handle_state


def test_open_file_identity_agrees_with_path_and_survives_read(tmp_path):
    source=tmp_path/'file with spaces';source.write_bytes(b'unchanged bytes')
    before=path_state(source)
    with source.open('rb') as handle:
        assert handle_state(handle.fileno())==before
        assert handle.read()==b'unchanged bytes'
        assert handle_state(handle.fileno())==before
    assert path_state(source)==before


def test_missing_path_fails_instead_of_returning_identity(tmp_path):
    with pytest.raises(OSError): path_state(tmp_path/'missing')


@pytest.mark.skipif(sys.platform!='win32',reason='Actual NTFS change-time semantics require native Windows')
def test_native_windows_change_time_detects_same_size_write_with_restored_mtime(tmp_path):
    source=tmp_path/'native-state';source.write_bytes(b'old')
    initial=path_state(source);stat=source.stat()
    time.sleep(.03)
    source.write_bytes(b'new')
    os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert path_state(source)!=initial
    with source.open('rb') as handle:
        assert handle_state(handle.fileno())==path_state(source)


def test_windows_abi_setup_is_reused_but_each_snapshot_queries_fresh_data(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from firmavex.product import file_state
    instances = []; queries = []
    def load(*args, **kwargs):
        instances.append(args)
        def info(handle, pointer):
            queries.append(handle)
            pointer._obj.volume = 7
            pointer._obj.index_low = handle
            pointer._obj.size_low = 12
            return 1
        def basic(handle, kind, pointer, size):
            pointer._obj.write = len(queries)
            pointer._obj.change = len(queries) + 10
            return 1
        return SimpleNamespace(GetFileInformationByHandle=info,
                               GetFileInformationByHandleEx=basic,
                               CreateFileW=lambda *a: 19, CloseHandle=lambda *a: 1)
    file_state._windows_api.cache_clear()
    monkeypatch.setattr(ctypes, 'WinDLL', load, raising=False)
    try:
        assert file_state._windows_state(19) == (7,19,12,1,11)
        assert file_state._windows_state(19) == (7,19,12,2,12)
        assert len(instances) == 1 and queries == [19,19]
    finally:
        file_state._windows_api.cache_clear()
