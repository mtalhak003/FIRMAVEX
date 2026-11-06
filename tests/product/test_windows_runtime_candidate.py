"""Candidate harness tests; synthetic fixtures are not Windows qualification."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tools import windows_runtime_candidate as candidate
from firmavex.product.tools import Toolchain

HEAD = 'a' * 40


def environment():
    return {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'mtalhak003/FIRMAVEX',
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_WORKFLOW_REF': candidate.WORKFLOW,
            'GITHUB_SHA': HEAD, 'FIRMAVEX_CANDIDATE_REVISION': HEAD, 'GITHUB_RUN_ID': '123'}


@pytest.mark.parametrize('key,value', [
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_REPOSITORY', 'other/repository'),
    ('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_WORKFLOW_REF', 'other'),
    ('GITHUB_SHA', 'b' * 40), ('FIRMAVEX_CANDIDATE_REVISION', ''), ('GITHUB_RUN_ID', 'bad'),
])
def test_candidate_context_fails_closed(key, value):
    env = environment(); env[key] = value
    with pytest.raises(ValueError): candidate.context(env, 'win32', 'AMD64', HEAD)


@pytest.mark.parametrize('system,machine', [('linux', 'x86_64'), ('win32', 'ARM64'), ('darwin', 'arm64')])
def test_non_native_or_other_architectures_cannot_be_labeled_windows(system, machine):
    with pytest.raises(ValueError): candidate.context(environment(), system, machine, HEAD)


def test_explicit_context_is_bound_to_commit_and_run():
    record = candidate.context(environment(), 'win32', 'AMD64', HEAD)
    assert record == {'source_revision': HEAD, 'run_id': '123',
                      'host': {'os': 'Windows', 'architecture': 'x86_64'}}


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    root = tmp_path / 'vendor'
    identities, pins = {}, {}
    for name, filename in [('qemu', 'qemu-system-arm.exe'), ('gdb', 'gdb-multiarch.exe')]:
        path = root / 'bin' / filename; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('synthetic fixture: ' + name).encode())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pins[name] = candidate.CANDIDATE[name][0], digest
        identities[name] = {'version': pins[name][0], 'sha256': digest, 'size_bytes': path.stat().st_size}
    license = root / 'share/licenses/fixture/COPYING'
    license.parent.mkdir(parents=True); license.write_text('synthetic license fixture')
    tools = Toolchain(str(root / 'bin/qemu-system-arm.exe'), str(root / 'bin/gdb-multiarch.exe'), identities=identities)
    monkeypatch.setattr(candidate, 'CANDIDATE', pins)
    return root, tools


@pytest.mark.parametrize('name,field', [('qemu', 'version'), ('qemu', 'sha256'), ('gdb', 'version'), ('gdb', 'sha256')])
def test_candidate_pin_rejects_each_changed_field(vendor, name, field):
    root, tools = vendor
    tools.identities[name][field] = 'changed'
    with pytest.raises(ValueError): candidate.verify_tools(tools, root)


def test_candidate_checks_real_bytes_and_declared_prefix(vendor, tmp_path):
    root, tools = vendor
    candidate.verify_tools(tools, root)
    Path(tools.qemu).write_bytes(b'changed after discovery')
    with pytest.raises(ValueError): candidate.verify_tools(tools, root)
    with pytest.raises(ValueError): candidate.verify_tools(tools, tmp_path)


@pytest.mark.parametrize('policy', ['', 'PackageOptional PackageTrustedOnly',
    'PackageRequired PackageTrustAll', 'PackageRequired PackageTrustedOnly DatabaseTrustAll'])
def test_signatures_cannot_be_optional_or_trust_all(policy):
    with pytest.raises(ValueError): candidate.signature_policy(policy)


def test_required_trusted_publisher_signatures_and_exact_packages():
    assert candidate.signature_policy('PackageRequired\nPackageTrustedOnly\nDatabaseOptional\nDatabaseTrustedOnly')
    data = '\n'.join(f'{name} {version}' for name, version in candidate.PACKAGES.items())
    assert candidate.package_inventory(data) == candidate.PACKAGES
    for changed in [data.replace('11.1.3-1', '11.1.4-1'), data+'\n'+data, data+'\nsecret https://user:password@host', 'x' * (1024**2+1)]:
        with pytest.raises(ValueError): candidate.package_inventory(changed)


def test_vendor_inventory_includes_dependencies_not_only_executables(vendor):
    root, _ = vendor
    (root / 'bin/dependency.dll').write_bytes(b'dependency')
    rows = candidate.inventory(root)
    assert 'bin/dependency.dll' in rows and 'share/licenses/fixture/COPYING' in rows
    assert all(set(value) == {'sha256', 'size_bytes'} for value in rows.values())


@pytest.mark.parametrize('boundary', ['MAX_FILES', 'MAX_BYTES'])
def test_administrative_inventory_has_hard_bounds(vendor, monkeypatch, boundary):
    root, _ = vendor
    monkeypatch.setattr(candidate, boundary, 1)
    with pytest.raises(ValueError): candidate.inventory(root)


def test_inventory_rejects_links_before_reading_target(vendor, tmp_path):
    root, _ = vendor
    outside = tmp_path / 'outside'; outside.write_text('do not capture')
    try: (root / 'alias').symlink_to(outside)
    except OSError: pytest.skip('Host cannot create symlinks')
    with pytest.raises(ValueError): candidate.inventory(root)


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_record_write_failure_cannot_replace_control_flow(tmp_path, monkeypatch, control):
    primary = control('original')
    def denied(*args): raise OSError('write failed')
    monkeypatch.setattr(candidate, '_atomic_json', denied)
    candidate._save(tmp_path / 'unused', {}, primary)
    assert primary.__notes__ == ['Candidate evidence persistence failed']
    with pytest.raises(OSError): candidate._save(tmp_path / 'unused', {})


@pytest.mark.parametrize('bound', ['MAX_RECORD', 'MAX_OUTPUT_BYTES'])
def test_record_byte_bounds_include_writer_newline(tmp_path, monkeypatch, bound):
    path = tmp_path / 'record.json'
    record = {'value': 'bounded'}
    size = len(json.dumps(record, sort_keys=True).encode('utf-8')) + len(os.linesep)
    monkeypatch.setattr(candidate, bound, size)
    assert candidate._save(path, record)
    assert path.stat().st_size == size
    original = path.read_bytes()
    monkeypatch.setattr(candidate, bound, size - 1)
    with pytest.raises(ValueError): candidate._save(path, record)
    assert path.read_bytes() == original


def test_production_gate_still_rejects_candidate_and_is_not_patched(monkeypatch):
    from firmavex.product import platform_support as support
    monkeypatch.setattr(support, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(support, 'platform', SimpleNamespace(machine=lambda: 'AMD64'))
    tools = SimpleNamespace(identities={name: {'version': v, 'sha256': h} for name, (v,h) in candidate.CANDIDATE.items()})
    assert support.windows_profile(tools, machine='AMD64') is None
    assert candidate.production_rejection(tools)['required_profile'] == 'msys2-ucrt64-qemu11.1.2-gdb18.1-v1'
    assert support.windows_profile(tools, machine='AMD64') is None


def test_candidate_preflight_is_not_a_qualification_and_never_overwrites(vendor, tmp_path, monkeypatch):
    root, tools = vendor
    output = tmp_path / 'probe'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n,v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly DatabaseOptional DatabaseTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123', 'host': {'os':'synthetic_test'}}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    monkeypatch.setattr(candidate, 'production_rejection', lambda *a: {'synthetic_test': True})
    record = candidate.preflight(root, packages, policy, output)
    assert record['candidate_only'] and record['production_qualified'] is False
    assert record['status'] == 'candidate_preflight_only' and record['pending']
    before = {p.name:p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError): candidate.preflight(root, packages, policy, output)
    assert {p.name:p.read_bytes() for p in output.iterdir()} == before


def test_failed_preflight_retains_observed_identities_without_running_firmware(vendor, tmp_path, monkeypatch):
    root, tools = vendor
    output = tmp_path / 'failed-probe'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n,v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123'}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    tools.identities['qemu']['version'] = 'QEMU emulator version 11.1.4'
    with pytest.raises(ValueError): candidate.preflight(root, packages, policy, output)
    record = json.loads((output / 'candidate-report.json').read_text())
    assert record['status'] == 'candidate_preflight_failed' and record['production_qualified'] is False
    assert record['tools']['qemu']['version'] == 'QEMU emulator version 11.1.4'
    assert record['cases'] == [] and not list(output.glob('candidate-receipt-*'))


@pytest.mark.parametrize('fault', [None, 'cancel-receipt', 'cleanup'], ids=['normal', 'persistence-failure', 'cleanup-failure'])
def test_synthetic_executor_orchestration_accounts_for_every_attempt(vendor, tmp_path, monkeypatch, fault):
    """Mock runtime contract only; these fixtures never qualify Windows."""
    from firmavex.product import runtime
    from src.firmavex.evaluation.evaluator import Observation
    from src.firmavex.evaluation.api import ExecutionSignature
    root, tools = vendor
    output = tmp_path / 'source-probe'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n,v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123', 'host': {'os':'synthetic_test'}}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    monkeypatch.setattr(candidate, 'production_rejection', lambda *a: {'synthetic_test': True})
    candidate.preflight(root, packages, policy, output)
    original_save = candidate._atomic_json
    def write(path, record):
        if fault == 'cancel-receipt' and path.name == 'candidate-receipt-19.json':
            raise OSError('synthetic retention failure')
        original_save(path, record)
    monkeypatch.setattr(candidate, '_atomic_json', write)
    class FakeExecutor:
        sequence = 0
        def __init__(self, config, tools, cancel, callback):
            self.config, self.cancel, self.callback = config, cancel, callback
            self.last_evidence = None
        def execute(self, values):
            FakeExecutor.sequence += 1
            if self.callback: self.callback({'stage':'injected'})
            incomplete = self.config.completion_breakpoint == 'Default_Handler'
            value = 0x13579bdf if self.config.failure_symbol == 'initialized_data' else int(values == (2,1))
            self.last_evidence = {
                'synthetic_fixture': True, 'attempt_id': str(FakeExecutor.sequence), 'inputs': list(values),
                'observed_value': value, 'cleanup_verified': True,
                'cleanup': {'processes':[{'reaped': True}]},
                # Deliberately simulated dependency contract, not measured evidence.
                'measurement_mode':'real_firmware', 'guest_dispatched':True,
                'input_injected':True, 'completion_reached':not incomplete,
            }
            if incomplete:
                self.last_evidence['error_category'] = 'cancelled' if self.cancel.is_set() else 'timeout'
                if fault == 'cleanup' and self.cancel.is_set(): self.last_evidence['cleanup_verified'] = False
                if self.cancel.is_set(): raise KeyboardInterrupt('synthetic expected cancellation')
                return SimpleNamespace(observation=Observation(False))
            return SimpleNamespace(observation=Observation(True, value == self.config.failure_value,
                                       execution_signature=ExecutionSignature('a'*64, False)))
    monkeypatch.setattr(runtime, 'FirmwareExecutor', FakeExecutor)
    if fault is not None:
        with pytest.raises(RuntimeError): candidate.source_probe(root, output)
        report = json.loads((output / 'candidate-report.json').read_text())
        assert report['status'] == 'candidate_source_probe_failed' and report['production_qualified'] is False
        return
    report = candidate.source_probe(root, output)
    assert report['production_qualified'] is False and len(report['cases']) == 8
    assert sum(case['accounting']['attempted_executions'] for case in report['cases']) == 19
    assert sum(case['accounting']['infrastructure_failures'] for case in report['cases']) == 2
    assert len(list(output.glob('candidate-receipt-*.json'))) == 19
    for path in output.glob('candidate-receipt-*.json'):
        record = json.loads(path.read_text())
        assert record['candidate_only'] and record['production_qualified'] is False
        assert record['runtime']['synthetic_fixture']
    with pytest.raises(ValueError): candidate.source_probe(root, output)  # Never silently rerun a consumed probe.


def test_candidate_workflow_is_manual_pinned_separate_and_never_approves():
    repo = Path(__file__).resolve().parents[2]
    workflow = (repo / '.github/workflows/windows-runtime-candidate.yml').read_text()
    assert 'workflow_dispatch:' in workflow and '\n  push:' not in workflow and '\n  pull_request:' not in workflow
    assert 'expected_revision' in workflow and 'contents: read' in workflow
    assert 'PackageRequired' in workflow and 'PackageTrustedOnly' in workflow and 'pacman -Syu' in workflow
    assert 'pacman-conf --repo ucrt64 SigLevel' in workflow
    assert 'Windows-UNQUALIFIED-runtime-candidate-' in workflow and '!/evidence/' in workflow
    assert 'FIRMAVEX_QUALIFY_BACKENDS' not in workflow
    assert 'tools.windows_runtime_candidate' not in (repo / 'packaging/desktop.spec').read_text()
    assert 'tools/windows_runtime_candidate.py' not in (repo / 'MANIFEST.in').read_text()


def _native_required():
    if os.environ.get('FIRMAVEX_RUN_WINDOWS_CANDIDATE') != '1':
        pytest.skip('Explicit dispatch-only native Windows candidate workflow required')
    if sys.platform != 'win32': pytest.fail('Candidate mode cannot qualify Windows on another OS')


def test_native_windows_candidate_source_probe():
    _native_required()
    root = Path(os.environ['FIRMAVEX_CANDIDATE_ROOT'])
    result = candidate.source_probe(Path(os.environ['FIRMAVEX_CANDIDATE_VENDOR']), root / 'source-probe')
    assert result['status'] == 'candidate_source_probe_passed'
    assert result['production_qualified'] is False and len(result['cases']) == 8


def test_native_windows_candidate_memory_resource_bound(tmp_path):
    _native_required()
    import threading
    from firmavex.backends.api import Limits
    from firmavex.backends.process import Processes
    owner = Processes(threading.Event(), Limits(memory_bytes=128 * 1024**2, timeout_seconds=10))
    try:
        code, out, err = owner.run([sys.executable, '-c',
            "data=bytearray(256*1024*1024);print('UNEXPECTED_ALLOCATION_SUCCESS')"], tmp_path)
    finally:
        owner.close()
    assert code != 0 and 'MemoryError' in err and 'UNEXPECTED_ALLOCATION_SUCCESS' not in out
    assert all(row['reaped'] for row in owner.cleanup)
    candidate._save(Path(os.environ['FIRMAVEX_CANDIDATE_ROOT']) / 'source-probe/candidate-resource.json', {
        'candidate_only': True, 'production_qualified': False, 'firmware_executed': False,
        'scope': 'native host allocation denial, not aggregate QEMU memory qualification',
        'requested_limit_bytes': 128*1024**2, 'allocation_bytes': 256*1024**2,
        'exit_code': code, 'cleanup': owner.cleanup})
