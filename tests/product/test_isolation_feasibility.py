"""Fixed real namespace probes are not firmware or hostile-workload qualification."""
import json
import platform
import shutil
import threading
from dataclasses import replace
import pytest
from tools import isolation_feasibility as probe


def test_missing_mechanism_never_dispatches(monkeypatch):
    monkeypatch.setattr(probe.shutil, 'which', lambda name: None)
    monkeypatch.setattr(probe, 'Processes', lambda *a: pytest.fail('unexpected dispatch'))
    result = probe.assess()
    assert result['status'] == 'blocked'
    assert result['untrusted_execution_authorized'] is False
    assert result['sandbox_qualification'] == 'not_established'


def test_assessment_output_never_overwrites_existing_file(tmp_path, monkeypatch):
    path = tmp_path/'evidence.json'; path.write_text('keep')
    monkeypatch.setattr(probe, 'assess', lambda: {'status': 'blocked'})
    with pytest.raises(FileExistsError): probe.main(['--output', str(path)])
    assert path.read_text() == 'keep'


@pytest.fixture
def mechanism():
    if platform.system() != 'Linux' or not shutil.which('bwrap'):
        pytest.skip('Real Linux namespace diagnostic requires Bubblewrap')


def test_real_namespace_boundaries_or_explicit_host_blocker(mechanism):
    result = probe.assess()
    assert result['untrusted_execution_authorized'] is False
    assert result['aggregate_cgroup_quotas'] == 'not_validated'
    assert result['sandbox_qualification'] == 'not_established'
    assert not result['owned_marker_processes_remaining']
    if result['status'] == 'mechanism_checks_passed_not_qualified':
        assert len(result['checks']) == 12 and all(result['checks'].values())
        assert result['limits']['address_space'] == [536870912, 536870912]
        assert result['limits']['file_size'] == [1048576, 1048576]
    else:
        assert result['status'] == 'blocked' and result['diagnostics']
    assert all(row['reaped'] for row in result['cleanup'])


@pytest.fixture
def admitted_mechanism(mechanism):
    result = probe.assess()
    if result['status'] == 'blocked':
        pytest.skip('Namespace admission unavailable: ' + result['diagnostics'])
    assert result['status'] == 'mechanism_checks_passed_not_qualified'


def test_real_timeout_reaps_namespace_processes(admitted_mechanism, monkeypatch):
    monkeypatch.setattr(probe, 'GUEST', 'import time;time.sleep(30)')
    limits = probe.Limits
    monkeypatch.setattr(probe, 'Limits', lambda **kwargs: replace(limits(**kwargs), timeout_seconds=.3))
    result = probe.assess()
    assert result['status'] == 'assessment_failed' and 'TimeoutError' in result['diagnostics']
    assert result['checks']['namespace_descendants_absent'] is True
    assert all(row['reaped'] for row in result['cleanup'])
    assert result['untrusted_execution_authorized'] is False


def test_cancelled_assessment_does_not_admit_guest(mechanism):
    event = threading.Event(); event.set()
    result = probe.assess(cancel=event)
    assert result['status'] == 'cancelled' and 'Cancelled' in result['diagnostics']
    assert result['cleanup'] == []
    assert not result['owned_marker_processes_remaining']


def test_interruption_preserved_when_final_inspection_fails(mechanism, monkeypatch):
    class Interrupted(probe.Processes):
        def run(self, *args, **kwargs): raise KeyboardInterrupt('original cancellation')
    monkeypatch.setattr(probe, 'Processes', Interrupted)
    def denied(token): raise OSError('inspection unavailable')
    monkeypatch.setattr(probe, 'remaining_owned', denied)
    with pytest.raises(KeyboardInterrupt, match='original cancellation') as caught:
        probe.assess()
    assert any('inspection' in note for note in caught.value.__notes__)


def test_final_inspection_failure_cannot_report_verified_cleanup(mechanism, monkeypatch):
    def denied(token): raise OSError('inspection unavailable')
    monkeypatch.setattr(probe, 'remaining_owned', denied)
    result = probe.assess()
    assert result['status'] == 'cleanup_verification_failed'
    assert result['checks']['namespace_descendants_absent'] is False
    assert 'inspection unavailable' in result['process_inspection_errors'][0]
    assert result['untrusted_execution_authorized'] is False


def test_missing_boundary_results_fail_closed(mechanism, monkeypatch):
    class Incomplete(probe.Processes):
        def run(self, *args, **kwargs): return 0, '{"checks":{"input_readable":true}}', ''
    monkeypatch.setattr(probe, 'Processes', Incomplete)
    result = probe.assess()
    assert result['status'] == 'assessment_failed'
    assert 'Missing fixed boundary' in result['diagnostics']
    assert result['untrusted_execution_authorized'] is False


def test_guest_output_cannot_promote_security_policy(mechanism, monkeypatch):
    class Contradictory(probe.Processes):
        def run(self, *args, **kwargs):
            result = {'checks': dict.fromkeys(probe.REQUIRED_CHECKS, True),
                      'limits': {'address_space': [536870912, 536870912], 'cpu': [9, 9], 'file_size': [1048576, 1048576]},
                      'guest_pid': 2, 'untrusted_execution_authorized': True}
            return 0, json.dumps(result), ''
    monkeypatch.setattr(probe, 'Processes', Contradictory)
    result = probe.assess()
    assert result['status'] == 'assessment_failed'
    assert result['untrusted_execution_authorized'] is False
    assert result['sandbox_qualification'] == 'not_established'


@pytest.mark.parametrize('status,expected', [('blocked', 0), ('mechanism_checks_passed_not_qualified', 0),
                                           ('boundary_check_failed', 1), ('cleanup_failed', 1),
                                           ('cleanup_verification_failed', 1), ('assessment_failed', 1),
                                           ('cancelled', 1)])
def test_cli_retains_failures_and_returns_nonzero(tmp_path, monkeypatch, status, expected):
    record = {'status': status, 'untrusted_execution_authorized': False}
    monkeypatch.setattr(probe, 'assess', lambda: record)
    path = tmp_path/'assessment.json'
    assert probe.main(['--output', str(path)]) == expected
    assert json.loads(path.read_text()) == record
