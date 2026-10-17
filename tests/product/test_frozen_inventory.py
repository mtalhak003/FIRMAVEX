import json
from pathlib import Path
import pytest
from firmavex.product import frozen_inventory as inventory


def test_actual_files_and_explicit_unknowns(tmp_path):
    app = tmp_path / 'app'; app.mkdir()
    (app / 'libpython.so').write_bytes(b'\x7fELFtest')
    (app / 'unknown.dat').write_bytes(b'hello')
    (app / 'base_library.zip').write_bytes(b'PK')
    result = inventory.capture(app)
    assert result == inventory.capture(app)
    assert result['counts']['entries'] == 3
    assert result['counts']['regular_bytes'] == 15
    assert result['release_approved'] is False
    assert result['consistency']['atomic'] is False
    files = {v['path']: v for v in result['files']}
    assert files['libpython.so']['format'] == 'ELF'
    assert files['libpython.so']['component_hint'] == 'CPython'
    assert files['unknown.dat']['component_hint'] is None
    assert files['base_library.zip']['format'] == 'embedded_archive_unexpanded'
    assert all(v['ownership'] == 'unverified' for v in files.values())


def test_installer_is_not_claimed_extracted(tmp_path):
    app = tmp_path / 'app'; app.mkdir()
    installer = tmp_path / 'setup.exe'; installer.write_bytes(b'MZexample')
    result = inventory.capture(app, [installer])
    assert result['installers']['setup.exe']['payload_inventory'] == 'not_extracted_not_verified'
    with pytest.raises(ValueError, match='Duplicate'): inventory.capture(app, [installer, installer])


def test_mid_capture_change_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'item'; source.write_bytes(b'a')
    original = inventory._classification
    def mutate(path):
        result = original(path); path.write_bytes(b'b'); return result
    monkeypatch.setattr(inventory, '_classification', mutate)
    with pytest.raises(ValueError, match='changed'): inventory.capture(tmp_path)


def test_new_entry_rejected(tmp_path, monkeypatch):
    (tmp_path / 'item').write_bytes(b'a')
    original = inventory._classification
    def mutate(path):
        (tmp_path / 'new').write_bytes(b'new'); return original(path)
    monkeypatch.setattr(inventory, '_classification', mutate)
    with pytest.raises(ValueError, match='changed'): inventory.capture(tmp_path)


def test_links(tmp_path):
    app = tmp_path / 'app'; app.mkdir()
    (app / 'file').write_bytes(b'x')
    try: (app / 'alias').symlink_to('file')
    except OSError: pytest.skip('Host does not admit test symlinks')
    assert inventory.capture(app)['files'][0] == {'path': 'alias', 'type': 'symlink', 'target': 'file'}
    (app / 'alias').unlink(); (app / 'alias').symlink_to('../outside')
    (tmp_path / 'outside').write_bytes(b'x')
    with pytest.raises(ValueError, match='External'): inventory.capture(app)


def test_cli_never_overwrites(tmp_path):
    app=tmp_path/'app'; app.mkdir()
    output=tmp_path/'out.json'
    args=[str(app),'--output',str(output)]
    assert inventory.main(args)==0
    before=output.read_bytes()
    assert inventory.main(args)==1
    assert output.read_bytes()==before
    assert json.loads(before)['release_approved'] is False


def test_output_cannot_change_application(tmp_path):
    assert inventory.main([str(tmp_path),'--output',str(tmp_path/'inventory.json')])==1
    assert list(tmp_path.iterdir())==[]


def test_special_files_rejected(tmp_path):
    import os
    if not hasattr(os,'mkfifo'):pytest.skip('POSIX FIFO test')
    os.mkfifo(tmp_path/'pipe')
    with pytest.raises(ValueError,match='Unsupported'):inventory.capture(tmp_path)


def test_limits_fail_closed(tmp_path,monkeypatch):
    (tmp_path/'one').write_bytes(b'one')
    monkeypatch.setattr(inventory,'MAX_FILES',0)
    with pytest.raises(ValueError,match='file limit'):inventory.capture(tmp_path)
    monkeypatch.setattr(inventory,'MAX_FILES',10)
    monkeypatch.setattr(inventory,'MAX_TOTAL',1)
    with pytest.raises(ValueError,match='total limit'):inventory.capture(tmp_path)
