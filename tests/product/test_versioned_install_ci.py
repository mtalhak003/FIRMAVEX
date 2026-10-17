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
