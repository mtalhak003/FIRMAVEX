"""Real static fixtures and synthetic dispatch seams; never hardware evidence."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import threading

import pytest

from firmavex.backends.api import Request, request_to_dict
from firmavex.backends.bundled import catalog
from firmavex.product import workspace
from firmavex.product.errors import ProductError


def image(tmp_path, profile='verilog-icarus'):
    source = tmp_path / 'custom input'
    if profile == 'riscv32-virt':
        source.write_bytes(catalog()[1])
    else:
        source.write_text('module testbench; initial begin $display("FIRMAVEX_TEST_RESULT=PASS"); $finish; end endmodule', encoding='ascii')
    return Request(profile, source, (2, 1) if profile == 'riscv32-virt' else ())


def contents(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('profile', ['riscv32-virt', 'verilog-icarus'])
def test_save_reopen_preflight_and_missing_original_never_execute(tmp_path, monkeypatch, profile):
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('unexpected process execution'))
    request = image(tmp_path, profile)
    preflight = workspace.preflight(request_to_dict(request))
    assert preflight['execution_performed'] is False and 'runtime' in preflight['limitation']
    saved = workspace.save(tmp_path / 'configs', 'My custom input', request_to_dict(request))
    root = Path(saved['configuration'])
    before = contents(root)
    request.source.write_bytes(b'changed external build')
    opened = workspace.open_configuration(root)
    assert opened['input_sha256'] == preflight['source_sha256']
    request.source.unlink()
    assert workspace.open_configuration(root) == opened
    assert contents(root) == before
    assert workspace.listing(tmp_path / 'configs')['entries'][0]['identity'] == root.name
    assert opened['request']['source'] == str(root / 'input')


def test_revision_preserves_old_input_configuration_and_legacy_runs(tmp_path):
    request = image(tmp_path)
    first = workspace.save(tmp_path / 'configs', 'test', request_to_dict(request))
    root = Path(first['configuration'])
    (root / 'runs' / 'legacy').mkdir(parents=True)
    (root / 'runs' / 'legacy' / 'result.json').write_bytes(b'legacy evidence remains opaque')
    before = contents(root)
    request.source.write_bytes(request.source.read_bytes().replace(b'PASS', b'FAIL'))
    second = workspace.save(tmp_path / 'configs', 'test revision', request_to_dict(request), parent=root)
    assert second['parent'] == first['identity'] and second['identity'] != first['identity']
    assert contents(root) == before
    assert second['input_sha256'] != first['input_sha256']
    assert not (Path(second['configuration']) / 'runs').exists()
    (root / 'input').write_bytes(b'tampered imported snapshot')
    with pytest.raises(ValueError, match='changed'):
        workspace.open_configuration(root)
    with pytest.raises(ValueError, match='changed'):
        workspace.save(tmp_path / 'configs', 'not a repair', request_to_dict(request), parent=root)


def test_malformed_records_and_incompatible_inputs_fail_closed(tmp_path):
    request = image(tmp_path)
    root = tmp_path / 'configs'
    root.mkdir()
    (root / 'legacy').mkdir()
    (root / 'legacy' / 'configuration.json').write_bytes(b'{}')
    assert workspace.listing(root)['entries'] == []
    with pytest.raises(ValueError):
        workspace.open_configuration(root / 'legacy')
    request.source.write_text('module testbench; initial $system("bad"); endmodule')
    with pytest.raises(ValueError, match='Unsupported simulator'):
        workspace.preflight(request_to_dict(request))
    with pytest.raises(ValueError):
        workspace.save(root, 'bad', request_to_dict(request))
    assert list(root.iterdir()) == [root / 'legacy']
    request.source.unlink()
    with pytest.raises(FileNotFoundError):
        workspace.preflight(request_to_dict(request))


def test_saved_identity_and_configuration_edits_are_detected(tmp_path):
    saved = workspace.save(tmp_path / 'configs', 'test', request_to_dict(image(tmp_path)))
    path = Path(saved['configuration']) / 'configuration.json'
    record = json.loads(path.read_text())
    record['request']['limits']['timeout_seconds'] += 1
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='identity changed'):
        workspace.open_configuration(path.parent)
    assert workspace.listing(path.parent.parent)['entries'] == []


def test_cancellation_does_not_publish_a_configuration(tmp_path):
    request = image(tmp_path)
    event = threading.Event()
    event.set()
    with pytest.raises(KeyboardInterrupt):
        workspace.save(tmp_path / 'configs', 'cancelled', request_to_dict(request), cancel_event=event)
    assert not (tmp_path / 'configs').exists()


def test_dispatch_freezes_verified_bytes_and_preserves_consent(tmp_path, monkeypatch):
    from firmavex.product import backend_services
    request = image(tmp_path)
    saved = workspace.save(tmp_path / 'configs', 'test', request_to_dict(request))
    root = Path(saved['configuration'])
    with pytest.raises(ProductError, match='Untrusted'):
        workspace.execute_saved(root, root / 'runs' / 'untrusted', trust='untrusted')
    assert not (root / 'runs').exists()
    with pytest.raises(ValueError, match='own runs'):
        workspace.execute_saved(root, tmp_path / 'outside', trust='trusted_project')
    original = (root / 'input').read_bytes()
    def synthetic(record, output, *, trust, **kwargs):
        assert trust == 'trusted_project'
        (root / 'input').write_bytes(b'changed after verified capture')
        temporary = Path(record['source'])
        assert temporary.read_bytes() == original
        assert temporary.parent != root
        return {'status': 'synthetic_test', 'temporary': str(temporary)}
    monkeypatch.setattr(backend_services, 'execute', synthetic)
    result = workspace.execute_saved(root, root / 'runs' / 'synthetic', trust='trusted_project')
    assert not Path(result['temporary']).exists()


def test_arm_handoff_preserves_exact_config_and_rejects_mutation(tmp_path):
    from firmavex.product.services import prepare_example_project
    from firmavex.product.config import load_config
    from firmavex.desktop.projects import DesktopProject
    prepared = prepare_example_project(tmp_path / 'builtin')
    config = load_config(prepared['config_file'])
    project = DesktopProject.create(tmp_path / 'project', config.firmware, config)
    selected = replace(project.load_config(), execution_budget=7)
    context = workspace.arm_context(project, selected)
    # Another explicit save must not change the context being returned to.
    project.save_config(replace(selected, execution_budget=11))
    before = contents(project.root)
    returned, exact = workspace.arm_selection(context['source'], context)
    assert returned.root == project.root and exact == selected
    assert contents(project.root) == before
    assert workspace.preflight(request_to_dict(Request('cortex-m3-mps2', Path(context['source']))))['execution_performed'] is False
    Path(context['source']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        workspace.arm_selection(context['source'], context)


def test_arm_selected_execution_pins_firmware_and_config(tmp_path, monkeypatch):
    from firmavex.product.services import prepare_example_project
    from firmavex.product.config import load_config
    from firmavex.desktop.projects import DesktopProject
    from firmavex.product import backend_services
    prepared = prepare_example_project(tmp_path / 'builtin')
    config = load_config(prepared['config_file'])
    project = DesktopProject.create(tmp_path / 'project', config.firmware, config)
    context = workspace.arm_context(project, project.load_config())
    request = request_to_dict(Request('cortex-m3-mps2', Path(context['source'])))
    def synthetic(record, output, **kwargs):
        selected = load_config(record['source'])
        assert selected.firmware.parent == Path(record['source']).parent
        assert hashlib.sha256(selected.firmware.read_bytes()).hexdigest() == context['firmware_sha256']
        return {'status': 'synthetic_test'}
    monkeypatch.setattr(backend_services, 'execute', synthetic)
    assert workspace.execute_selected(request, tmp_path / 'out', context['sha256'],
        trust='trusted_project', expected_firmware=context['firmware_sha256'])['status'] == 'synthetic_test'
    project.firmware_path.write_bytes(b'new build without explicit import')
    with pytest.raises(ValueError, match='firmware changed'):
        workspace.execute_selected(request, tmp_path / 'out', context['sha256'],
            trust='trusted_project', expected_firmware=context['firmware_sha256'])


def test_real_supervised_static_configuration_workflow(tmp_path):
    from firmavex.product.supervisor import Supervisor
    request = request_to_dict(image(tmp_path))
    preflight = Supervisor().execute('backend_preflight', {'request': request})
    assert preflight['execution_performed'] is False
    saved = Supervisor().execute('backend_configurations', {'action': 'save', 'root': str(tmp_path / 'configs'),
        'name': 'Worker custom fixture', 'request': request})
    opened = Supervisor().execute('backend_configurations', {'action': 'open', 'configuration': saved['configuration']})
    assert opened['identity'] == saved['identity']
    assert not (Path(saved['configuration']) / 'runs').exists()


def test_cancel_after_input_write_cleans_only_new_configuration(tmp_path, monkeypatch):
    request = image(tmp_path)
    first = workspace.save(tmp_path / 'configs', 'old', request_to_dict(request))
    old = contents(Path(first['configuration']))
    event = threading.Event()
    original = workspace._write
    def write_then_cancel(path, data, cancel_event):
        original(path, data, cancel_event)
        if path.name == 'input':
            event.set()
    monkeypatch.setattr(workspace, '_write', write_then_cancel)
    with pytest.raises(KeyboardInterrupt):
        workspace.save(tmp_path / 'configs', 'cancelled', request_to_dict(request), cancel_event=event)
    assert contents(Path(first['configuration'])) == old
    assert len(list((tmp_path / 'configs').iterdir())) == 1


def test_preflight_respects_selected_snapshot_identity(tmp_path):
    request = image(tmp_path)
    saved = workspace.save(tmp_path / 'configs', 'test', request_to_dict(request))
    selected = saved['request']
    assert workspace.preflight(selected, configuration=saved['configuration'])['runtime_behavior'] == 'unverified'
    (Path(saved['configuration']) / 'input').write_bytes(request.source.read_bytes().replace(b'PASS', b'FAIL'))
    with pytest.raises(ValueError, match='changed'):
        workspace.preflight(selected, configuration=saved['configuration'])
