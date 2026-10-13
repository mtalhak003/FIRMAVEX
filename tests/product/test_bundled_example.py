import base64
import hashlib
import json
from pathlib import Path
import threading

import pytest
from firmavex.product import bundled_example as module
from firmavex.product.config import load_config
from firmavex.product.errors import ProductError


def test_preparation_requires_neither_compiler_nor_guest_dispatch(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Preparation dispatched a process'))
    result = module.prepare_example(tmp_path / 'example')
    assert not result['compiler_required'] and not result['firmware_executed']
    assert not result['provenance']['locally_compiled']
    assert load_config(result['config_file']).compiler is None
    assert hashlib.sha256(Path(result['firmware_file']).read_bytes()).hexdigest() == result['provenance']['image_sha256']
    assert set(result['provenance']['sources']) == {'main.c', 'startup.c', 'linker.ld'}
    assert 'image_base64' not in result['provenance']


def test_existing_directory_is_never_overwritten(tmp_path):
    sentinel = tmp_path / 'sentinel'
    sentinel.write_text('keep')
    with pytest.raises(ProductError, match='new directory'):
        module.prepare_example(tmp_path)
    assert sentinel.read_text() == 'keep'


def test_cancelled_preparation_dispatches_nothing(tmp_path):
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt):
        module.prepare_example(tmp_path / 'example', cancel_event=event)
    assert not (tmp_path / 'example').exists()


@pytest.mark.parametrize('change', [
    {'schema_version': True}, {'license': 'unknown'}, {'sources': {}},
    {'image_sha256': '0' * 64}, {'image_base64': 'invalid#'}, {'image_base64': ''},
])
def test_bad_image_manifest_fails_before_output_creation(tmp_path, monkeypatch, change):
    resources = module.files('firmavex.product')
    original = json.loads(resources.joinpath('resources/example/image.json').read_text())
    original.update(change)
    fake = tmp_path / 'resources/example'
    fake.mkdir(parents=True)
    (fake / 'image.json').write_text(json.dumps(original))
    monkeypatch.setattr(module, 'files', lambda name: tmp_path)
    with pytest.raises(ProductError):
        module.prepare_example(tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_source_mutation_is_detected(tmp_path, monkeypatch):
    source = module.files('firmavex.product')
    fake = tmp_path / 'resources/example'; fake.mkdir(parents=True)
    for name in ['image.json', 'main.c', 'startup.c', 'linker.ld']:
        (fake / name).write_bytes(source.joinpath('resources/example/' + name).read_bytes())
    (fake / 'main.c').write_bytes(b'different')
    monkeypatch.setattr(module, 'files', lambda name: tmp_path)
    with pytest.raises(ProductError, match='source identity'):
        module.prepare_example(tmp_path / 'output')


def test_image_has_no_cloud_workspace_path(tmp_path):
    result = module.prepare_example(tmp_path / 'image')
    assert b'/workspace/' not in Path(result['firmware_file']).read_bytes()
