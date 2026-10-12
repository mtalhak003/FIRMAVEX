import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from firmavex.product import runtime_pack as pack
from firmavex.product.errors import ProductError


def make_pack(tmp_path, *, edits=None, extra=None):
    files = {'bin/qemu': b'qemu', 'bin/gdb': b'gdb', 'LICENSES.txt': b'GPL corresponding source supplied separately'}
    manifest = {'schema_version': 1, 'id': 'test-1', 'host': pack.host(),
                'tools': {'qemu': 'bin/qemu', 'gdb': 'bin/gdb'},
                'files': {key: hashlib.sha256(value).hexdigest() for key, value in files.items()},
                'licenses': ['LICENSES.txt'], 'source_offer': 'TEST ONLY - not a distributable runtime'}
    if edits:
        manifest.update(edits)
    archive = tmp_path / 'runtime.zip'
    with zipfile.ZipFile(archive, 'w') as target:
        target.writestr('runtime.json', json.dumps(manifest))
        for name, data in files.items():
            target.writestr(name, data)
        if extra:
            target.writestr(*extra)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


@pytest.fixture
def probes(monkeypatch):
    calls = []
    def discover(config, **kwargs):
        calls.append((config, kwargs))
        return SimpleNamespace(to_dict=lambda: {'qemu': config.qemu, 'gdb': config.gdb})
    monkeypatch.setattr('firmavex.product.tools.discover', discover)
    return calls


def test_install_verify_and_repair_keep_old_generation(tmp_path, probes):
    archive, checksum = make_pack(tmp_path)
    root = tmp_path / 'installation'
    first = pack.install(archive, checksum, root=root)
    assert first['firmware_qualification'] == 'not_established_by_installation'
    assert probes[0][1] == {'_managed': False}
    selected = pack.active_tools(root)
    assert Path(selected['qemu']).read_bytes() == b'qemu'
    Path(selected['gdb']).write_bytes(b'broken')
    with pytest.raises(ProductError, match='checksum mismatch'):
        pack.active_tools(root)
    second = pack.install(archive, checksum, root=root)
    assert first['generation'] != second['generation']
    assert (root / first['generation']).exists()
    assert Path(pack.active_tools(root)['gdb']).read_bytes() == b'gdb'


def test_wrong_archive_checksum_never_executes(tmp_path, probes):
    archive, _ = make_pack(tmp_path)
    with pytest.raises(ProductError, match='checksum mismatch'):
        pack.install(archive, '0' * 64, root=tmp_path / 'installed')
    assert not probes


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'a\\b', 'C:/x', 'a/../b', 'CON', 'x/NUL.txt', 'a//b', 'a.', 'a '])
def test_unsafe_member_rejected_before_probe(tmp_path, probes, name):
    archive, digest = make_pack(tmp_path, extra=(name, b'data'))
    with pytest.raises(ProductError):
        pack.install(archive, digest, root=tmp_path / 'installed')
    assert not probes
    assert not (tmp_path / 'outside').exists()


@pytest.mark.parametrize('edits', [
    {'schema_version': True}, {'host': {'os': 'wrong', 'arch': 'wrong'}},
    {'files': {}}, {'licenses': []}, {'source_offer': ''},
    {'tools': {'qemu': 'missing', 'gdb': 'bin/gdb'}},
    {'id': '../evil'}, {'unexpected': 'field'},
])
def test_invalid_manifest_rejected(tmp_path, probes, edits):
    archive, digest = make_pack(tmp_path, edits=edits)
    with pytest.raises(ProductError):
        pack.install(archive, digest, root=tmp_path / 'installed')
    assert not probes


def test_probe_failure_preserves_activation(tmp_path, probes, monkeypatch):
    archive, digest = make_pack(tmp_path)
    root = tmp_path / 'installed'
    pack.install(archive, digest, root=root)
    before = (root / 'active.json').read_bytes()
    def failed(*args, **kwargs):
        raise ProductError('unsupported_runtime', 'missing Python')
    monkeypatch.setattr('firmavex.product.tools.discover', failed)
    with pytest.raises(ProductError, match='missing Python'):
        pack.install(archive, digest, root=root)
    assert (root / 'active.json').read_bytes() == before
    assert not (root / 'install.lock').exists()
    assert len(list(root.iterdir())) == 2


def test_active_inventory_extra_file_fails(tmp_path, probes):
    archive, digest = make_pack(tmp_path)
    root = tmp_path / 'installed'
    result = pack.install(archive, digest, root=root)
    (root / result['generation'] / 'extra').write_text('not inventoried')
    with pytest.raises(ProductError, match='inventory'):
        pack.active_tools(root)


def test_install_lock_does_not_get_stolen(tmp_path, probes):
    archive, digest = make_pack(tmp_path)
    root = tmp_path / 'installed'
    (root / 'install.lock').mkdir(parents=True)
    with pytest.raises(ProductError, match='lock'):
        pack.install(archive, digest, root=root)
    assert not probes
    assert (root / 'install.lock').exists()


def test_empty_installation_is_not_readiness(tmp_path):
    assert pack.active_tools(tmp_path) == {}


def test_frozen_worker_arguments(monkeypatch):
    from firmavex.product.supervisor import Supervisor
    import sys
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    assert Supervisor().worker_argv == [sys.executable, '--firmavex-worker']
    assert Supervisor(['explicit']).worker_argv == ['explicit']


def test_bootstrap_worker_does_not_import_desktop(monkeypatch):
    from firmavex.desktop.bootstrap import main
    monkeypatch.setattr('firmavex.product.worker.main', lambda: 7)
    assert main(['--firmavex-worker']) == 7


def test_bootstrap_cli_routes_arguments(monkeypatch):
    from firmavex.desktop.bootstrap import main
    calls = []
    monkeypatch.setattr('firmavex.product.cli.main', lambda args: calls.append(args) or 3)
    assert main(['--firmavex-cli', 'doctor']) == 3
    assert calls == [['doctor']]


def test_probe_mutation_cannot_activate(tmp_path, monkeypatch):
    archive, digest = make_pack(tmp_path)
    def mutate(config, **kwargs):
        Path(config.gdb).write_bytes(b'changed during probe')
        return SimpleNamespace(to_dict=lambda: {})
    monkeypatch.setattr('firmavex.product.tools.discover', mutate)
    root = tmp_path / 'installed'
    with pytest.raises(ProductError, match='checksum mismatch'):
        pack.install(archive, digest, root=root)
    assert not (root / 'active.json').exists()


def test_duplicate_case_names_rejected(tmp_path, probes):
    archive, digest = make_pack(tmp_path, extra=('BIN/GDB', b'gdb'))
    with pytest.raises(ProductError):
        pack.install(archive, digest, root=tmp_path / 'installed')
    assert not probes


def test_zip_symlink_rejected(tmp_path, probes):
    archive, _ = make_pack(tmp_path)
    info = zipfile.ZipInfo('link')
    info.create_system = 3
    info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(archive, 'a') as target:
        target.writestr(info, 'bin/gdb')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ProductError):
        pack.install(archive, digest, root=tmp_path / 'installed')
    assert not probes



def test_manifest_rewrite_cannot_reauthorize_changed_bytes(tmp_path, probes):
    archive, digest = make_pack(tmp_path)
    root = tmp_path / 'installed'
    installed = pack.install(archive, digest, root=root)
    directory = root / installed['generation']
    (directory / 'bin/gdb').write_bytes(b'changed')
    data = json.loads((directory / 'runtime.json').read_text())
    data['files']['bin/gdb'] = hashlib.sha256(b'changed').hexdigest()
    (directory / 'runtime.json').write_text(json.dumps(data))
    with pytest.raises(ProductError, match='activated identity'):
        pack.active_tools(root)


def test_interruption_does_not_activate_or_leave_install_lock(tmp_path, monkeypatch):
    archive, digest = make_pack(tmp_path)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt('original interruption')
    monkeypatch.setattr('firmavex.product.tools.discover', interrupt)
    root = tmp_path / 'installed'
    with pytest.raises(KeyboardInterrupt, match='original interruption'):
        pack.install(archive, digest, root=root)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('licenses', [None, False, [False], [{}], [[]]])
def test_malformed_licenses_fail_structured(tmp_path, probes, licenses):
    archive, digest = make_pack(tmp_path, edits={'licenses': licenses})
    with pytest.raises(ProductError, match='license'):
        pack.install(archive, digest, root=tmp_path / 'installed')
    assert not probes


def test_probe_cannot_rewrite_inventory_to_hide_mutation(tmp_path, monkeypatch):
    archive, digest = make_pack(tmp_path)
    def mutate(config, **kwargs):
        directory = Path(config.gdb).parents[1]
        Path(config.gdb).write_bytes(b'changed')
        data = json.loads((directory / 'runtime.json').read_text())
        data['files']['bin/gdb'] = hashlib.sha256(b'changed').hexdigest()
        (directory / 'runtime.json').write_text(json.dumps(data))
        return SimpleNamespace(to_dict=lambda: {})
    monkeypatch.setattr('firmavex.product.tools.discover', mutate)
    root = tmp_path / 'installed'
    with pytest.raises(ProductError, match='manifest changed'):
        pack.install(archive, digest, root=root)
    assert not (root / 'active.json').exists()
