"""Real filesystem alias checks for native acceptance assertions only."""
import ctypes
import os
import sys
from pathlib import Path

import pytest

from tests.desktop.path_identity import assert_same_path


def test_directory_alias_and_same_bytes_in_unrelated_files(tmp_path):
    directory = tmp_path / 'original'; directory.mkdir()
    first = directory / 'firmware.elf'; first.write_bytes(b'fixture')
    second = tmp_path / 'firmware.elf'; second.write_bytes(first.read_bytes())
    assert_same_path(first, first)
    with pytest.raises(AssertionError):
        assert_same_path(first, second)
    with pytest.raises(AssertionError):
        assert_same_path(directory, tmp_path)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX directory alias; Windows 8.3 exercised separately')
def test_posix_directory_alias_preserves_artifact_identity(tmp_path):
    original = tmp_path / 'original'; original.mkdir()
    (original / 'firmware.elf').write_bytes(b'fixture')
    alias = tmp_path / 'alias'; alias.symlink_to(original, target_is_directory=True)
    assert_same_path(alias, original)
    assert_same_path(alias / 'firmware.elf', original / 'firmware.elf')
    assert (alias / 'firmware.elf').read_bytes() == b'fixture'


@pytest.mark.parametrize('bad', ['missing', 'not-a-directory/child', 'nul\x00path'])
def test_missing_or_malformed_path_never_matches(tmp_path, bad):
    existing = tmp_path / 'not-a-directory'; existing.write_bytes(b'fixture')
    for actual, expected in [(tmp_path / bad, existing), (existing, tmp_path / bad)]:
        with pytest.raises((OSError, ValueError)):
            assert_same_path(actual, expected)


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows short-path API')
def test_windows_short_alias_preserves_artifact_identity(tmp_path):
    original = tmp_path / 'long directory name for identity'; original.mkdir()
    (original / 'firmware.elf').write_bytes(b'fixture')
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    api.GetShortPathNameW.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    count = api.GetShortPathNameW(str(original), buffer, len(buffer))
    assert 0 < count < len(buffer), ctypes.get_last_error()
    alias = Path(buffer.value)
    if alias == original:
        pytest.skip('Volume does not provide an alternate short path')
    assert_same_path(alias, original)
    assert_same_path(alias / 'firmware.elf', original / 'firmware.elf')
    other = tmp_path / 'other'; other.mkdir()
    with pytest.raises(AssertionError):
        assert_same_path(alias, other)


@pytest.mark.skipif(sys.platform != 'darwin', reason='Actual macOS /var alias')
def test_macos_var_alias():
    assert_same_path(Path('/var'), Path('/private/var'))
