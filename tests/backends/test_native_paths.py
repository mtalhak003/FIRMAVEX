"""Directory identity/path checks only; real native execution remains required."""
from pathlib import Path

import pytest

from firmavex.backends import security, engine
from tests.backends.test_records_security import _hdl, _synthetic


def long_directory(tmp_path):
    path = tmp_path / ('a' * 80) / ('b' * 80) / ('c' * 80)
    path.mkdir(parents=True)
    return path


def test_short_execution_directory_is_unchanged(tmp_path):
    assert security.native_directory(tmp_path) == tmp_path


def test_long_posix_directory_does_not_use_windows_alias(tmp_path, monkeypatch):
    root = long_directory(tmp_path)
    monkeypatch.setattr(security, '_WINDOWS', False)
    monkeypatch.setattr(security, '_windows_short_directory', lambda *a: pytest.fail('No Windows API on POSIX'))
    assert security.native_directory(root) == root


def test_alias_requires_same_directory_and_short_spelling(tmp_path, monkeypatch):
    root = long_directory(tmp_path)
    alias = tmp_path / 'alias'; alias.mkdir()
    monkeypatch.setattr(security, '_WINDOWS', True)
    monkeypatch.setattr(security, '_windows_short_directory', lambda path: str(alias))
    seen = []
    monkeypatch.setattr(security.os.path, 'samefile', lambda a, b: seen.append((a, b)) or True)
    assert security.native_directory(root) == alias
    assert seen == [(root, alias)]


@pytest.mark.parametrize('failure', ['different-directory', 'not-shorter', 'relative', 'api-error'])
def test_unavailable_or_wrong_alias_fails_closed(tmp_path, monkeypatch, failure):
    root = long_directory(tmp_path)
    alias = tmp_path / 'other'; alias.mkdir()
    monkeypatch.setattr(security, '_WINDOWS', True)
    def selected(path):
        if failure == 'api-error': raise OSError('short names unavailable')
        return 'relative' if failure == 'relative' else str(root if failure == 'not-shorter' else alias)
    monkeypatch.setattr(security, '_windows_short_directory', selected)
    monkeypatch.setattr(security.os.path, 'samefile', lambda *a: False)
    with pytest.raises(ValueError, match='shorter project/data directory'):
        security.native_directory(root)


def test_alias_reparse_checks_remain_required(tmp_path, monkeypatch):
    root = long_directory(tmp_path)
    alias = tmp_path / 'unsafe'; alias.mkdir()
    monkeypatch.setattr(security, '_WINDOWS', True)
    monkeypatch.setattr(security, '_windows_short_directory', lambda path: str(alias))
    original = security.checked_path
    def checked(path, **kwargs):
        if Path(path) == alias: raise ValueError('Reparse point rejected')
        return original(path, **kwargs)
    monkeypatch.setattr(security, 'checked_path', checked)
    with pytest.raises(ValueError, match='shorter project/data directory'):
        security.native_directory(root)


def test_path_error_persists_without_dispatch_or_resource_bypass(tmp_path, monkeypatch):
    request = _hdl(tmp_path)
    _synthetic(monkeypatch, lambda *a: pytest.fail('No dispatch after path rejection'))
    def reject(path): raise ValueError('Native Windows execution path is too long')
    monkeypatch.setattr(engine, 'native_directory', reject)
    root = tmp_path / 'run'
    result = engine.execute_trusted(request, root, trust='trusted_project')
    assert result['status'] == 'infrastructure_failure'
    assert 'execution path is too long' in result['evidence']['error']
    assert engine.inspect_run(root) == result
    assert (root / 'admission.json').is_file()
