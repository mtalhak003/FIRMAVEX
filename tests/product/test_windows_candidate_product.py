"""Candidate product probes: synthetic records are not native qualification."""
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from firmavex.backends.api import Limits
from firmavex.backends.process import Processes
from firmavex.product.errors import ProductError
from firmavex.product.platform_support import WINDOWS_PROFILE_ID
from tools import windows_candidate_product as product


def rejection():
    return {'category': 'unsupported_platform', 'message': 'fixture rejection', 'details': {
        'required_profile': WINDOWS_PROFILE_ID, 'qualification': {'host_architecture': 'x86_64',
            'tools': {name: {'observed': {'version': version, 'sha256': digest}}
                      for name, (version, digest) in product.candidate.CANDIDATE.items()}}}}


def test_rejection_requires_exact_candidate_observations():
    result = product.rejection_details(rejection())
    assert result['category'] == 'unsupported_platform' and result['required_profile'] == WINDOWS_PROFILE_ID


@pytest.mark.parametrize('change', ['success', 'cleanup', 'profile', 'architecture', 'missing', 'tools', 'tool-record', 'qemu', 'gdb'])
def test_rejection_cannot_mask_unexpected_error_or_identity(change):
    record = rejection()
    if change == 'success': record['category'] = 'success'
    elif change == 'cleanup': record['details']['supervisor_cleanup_error'] = 'failed'
    elif change == 'profile': record['details']['required_profile'] = 'other'
    elif change == 'architecture': record['details']['qualification']['host_architecture'] = 'arm64'
    elif change == 'missing': record['details'].pop('qualification')
    elif change == 'tools': record['details']['qualification']['tools'] = []
    elif change == 'tool-record': record['details']['qualification']['tools']['qemu'] = []
    else: record['details']['qualification']['tools'][change]['observed']['sha256'] = '0'*64
    with pytest.raises(ValueError): product.rejection_details(record)


@pytest.mark.parametrize('distribution,executable', [('other', None), ('frozen', None), ('source', 'fake.exe')])
def test_invalid_distribution_stops_before_context_or_execution(monkeypatch, distribution, executable):
    monkeypatch.setattr(product, 'prepared_context', lambda *a: pytest.fail('Must reject arguments first'))
    with pytest.raises(ValueError): product.run_product_probe('unused', 'unused', distribution=distribution, executable=executable)


def test_real_host_cli_missing_configuration_fails_without_guest_and_reaps_worker(tmp_path, monkeypatch):
    """Actual CLI/worker error path; no fake runtime or Windows label supplied."""
    # The owned cwd must stay private: Processes audits all files under it.
    # Explicitly bind the launcher, CLI and worker imports to this approved source.
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[2]))
    owner = Processes(threading.Event(), Limits(timeout_seconds=20))
    try:
        code, out, err = owner.run([sys.executable, '-m', 'firmavex.product.cli', 'run',
                                   str(tmp_path/'missing-config.json'), '--output-dir', str(tmp_path/'never-run')], tmp_path)
    finally:
        owner.close()
    assert code == 1, out + err
    record = json.loads(out)
    assert record['success'] is False
    assert record['error']['category'] not in {'worker_failure', 'worker_interrupted', 'worker_timeout'}
    assert not (tmp_path/'never-run').exists()
    assert owner.cleanup and all(row['reaped'] for row in owner.cleanup)


@pytest.mark.parametrize('admitted', [False, True])
def test_synthetic_product_orchestration_keeps_candidate_labels_and_rejection_only(tmp_path, monkeypatch, admitted):
    vendor = tmp_path/'vendor'; vendor.mkdir()
    evidence = tmp_path/'evidence'; evidence.mkdir()
    context = {'source_revision': 'a'*40, 'run_id': '123', 'host': {'os': 'synthetic_test'}}
    monkeypatch.setattr(product, 'prepared_context', lambda *a: (context, vendor, evidence, SimpleNamespace()))
    def project(directory, tools):
        path = directory/'project.json'; path.write_text('{}'); return path
    monkeypatch.setattr(product, 'prepare_project', project)
    class Supervisor:
        def __init__(self, argv): assert argv is None
        def execute(self, command, payload, *, timeout, event_callback):
            assert command == 'run' and timeout == 60
            if admitted: return {'synthetic_test': True}
            event_callback({'kind':'accepted'}); event_callback({'kind':'error'})
            record = rejection()
            raise ProductError(record['category'], record['message'], record['details'])
    monkeypatch.setattr(product, 'Supervisor', Supervisor)
    monkeypatch.setattr(product, 'run_cli', lambda *a: {'path': 'CLI', 'synthetic_test': True})
    if admitted:
        with pytest.raises(ValueError, match='Unqualified runtime was admitted'):
            product.run_product_probe(vendor, evidence)
        result = json.loads((evidence/'product-source/product-admission.json').read_text())
        assert result['status'] == 'failed' and result['production_qualified'] is False
        assert result['charged_attempts'] is None and result['firmware_execution'] == 'unknown_not_verified'
        return
    result = product.run_product_probe(vendor, evidence)
    assert result['status'] == 'candidate_admission_rejection_passed'
    assert result['production_qualified'] is False and result['candidate_only'] is True
    assert result['installation_verified'] is False and result['charged_attempts'] == 0
    assert result['executable_origin'] == 'running_interpreter'
    assert result['firmware_execution'] == 'not_admitted' and len(result['cases']) == 2
    assert (evidence/'product-source/product-admission.json').is_file()


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_cli_cleanup_failure_preserves_original_control_flow(tmp_path, monkeypatch, control):
    class Owner:
        def __init__(self, *args): pass
        def run(self, *args): raise control('original interruption')
        def close(self): raise OSError('cleanup fixture')
    monkeypatch.setattr(product, 'Processes', Owner)
    with pytest.raises(control, match='original interruption') as raised:
        product.run_cli(['unused'], tmp_path/'config', tmp_path/'unused', tmp_path)
    assert raised.value.__notes__ == ['Candidate CLI cleanup failed: OSError']


def test_native_windows_candidate_product_entrypoint_rejection():
    if os.environ.get('FIRMAVEX_RUN_WINDOWS_CANDIDATE') != '1':
        pytest.skip('Explicit native Windows candidate workflow required')
    if sys.platform != 'win32': pytest.fail('Native Windows candidate checks cannot run on another OS')
    result = product.run_product_probe(Path(os.environ['FIRMAVEX_CANDIDATE_VENDOR']),
        Path(os.environ['FIRMAVEX_CANDIDATE_ROOT'])/'source-probe')
    assert result['status'] == 'candidate_admission_rejection_passed'
    assert result['production_qualified'] is False and result['charged_attempts'] == 0


def test_native_windows_candidate_frozen_product_rejection():
    if os.environ.get('FIRMAVEX_RUN_WINDOWS_CANDIDATE') != '1':
        pytest.skip('Explicit native Windows candidate workflow required')
    if sys.platform != 'win32': pytest.fail('Frozen candidate checks require native Windows')
    binary = os.environ.get('FIRMAVEX_CANDIDATE_FROZEN')
    if not binary:
        if os.environ.get('FIRMAVEX_REQUIRE_CANDIDATE_FROZEN') == '1':
            pytest.fail('Requested frozen candidate executable is missing')
        pytest.skip('Frozen candidate executable not requested')
    result = product.run_product_probe(Path(os.environ['FIRMAVEX_CANDIDATE_VENDOR']),
        Path(os.environ['FIRMAVEX_CANDIDATE_ROOT'])/'source-probe',
        executable=Path(binary), distribution='frozen')
    assert result['status'] == 'candidate_admission_rejection_passed'
    assert result['production_qualified'] is False and result['installation_verified'] is False
