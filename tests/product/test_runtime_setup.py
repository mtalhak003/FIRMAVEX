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
    license = root / 'share/licenses/gdb/COPYING'; license.parent.mkdir(parents=True)
    license.write_text('synthetic test license')
    archive = tmp_path / 'runtime.zip'
    digest = setup.snapshot_runtime(root, archive, packages='synthetic-package 1.0')
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as contents:
        assert 'share/licenses/gdb/COPYING' in contents.namelist()
        assert 'FIRMAVEX-VENDOR-PACKAGES.json' in contents.namelist()
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
    def denied(*args): raise OSError('synthetic cleanup failure')
    monkeypatch.setattr(setup, '_download', interrupt)
    monkeypatch.setattr(setup.shutil, 'rmtree', denied)
    with pytest.raises(KeyboardInterrupt, match='original cancellation') as caught:
        setup.install_vendor_runtime(root=tmp_path / 'runtime')
    assert any('cleanup' in note for note in caught.value.__notes__)
