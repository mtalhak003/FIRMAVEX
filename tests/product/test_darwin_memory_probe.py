"""Probe parsing and safety contracts only; never native qualification evidence."""
from pathlib import Path

import pytest
from tools import darwin_memory_probe as probe


def observation(**patch):
    return {'mode': 'as', 'cap_bytes': 134217728, 'uid': 501,
            'virtual_bytes': 420_000_000_000, 'resident_bytes': 20_000_000,
            'effective_cap_bytes': 134217728, 'admitted': False, **patch}


def test_rejected_admission_is_an_observation_not_qualification():
    record = observation()
    assert probe.validate_observation(record, 'as', 134217728, 125) == record


@pytest.mark.parametrize('patch,code', [
    ({'admitted': True}, 125), ({'admitted': False}, 0),
    ({'admitted': 1}, 0), ({'cap_bytes': True}, 125),
    ({'effective_cap_bytes': 134217729}, 125),
    ({'resident_bytes': -1}, 125), ({'uid': True}, 125),
    ({'mode': 'data'}, 125),
])
def test_contradictory_or_malformed_observations_rejected(patch, code):
    with pytest.raises(ValueError):
        probe.validate_observation(observation(**patch), 'as', 134217728, code)


def test_successful_api_call_is_not_enforcement_evidence():
    record = observation(mode='footprint', enforcement_verified=False)
    assert probe.validate_observation(record, 'footprint', 134217728, 0) == record
    with pytest.raises(ValueError, match='not enforcement'):
        probe.validate_observation({**record, 'enforcement_verified': True}, 'footprint', 134217728, 0)


def test_no_cross_platform_native_claim_or_directory_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.sys, 'platform', 'linux')
    output = tmp_path / 'probe'
    with pytest.raises(RuntimeError, match='actual Darwin'):
        probe.investigate(output)
    assert not output.exists()


def test_probe_cannot_execute_a_caller_selected_workload():
    source = (Path(probe.__file__).parent / 'native/darwin_memory_probe.c').read_text()
    assert 'execl("/usr/bin/true", "true", (char *)NULL)' in source
    assert 'execv(argv' not in source
    assert 'alarm(10)' in source and 'RLIMIT_CPU' in source
    assert 'inherited.rlim_cur < effective' in source and 'inherited.rlim_max < effective' in source


def test_investigation_runs_before_original_native_checks_and_retains_both_logs():
    workflow = Path('.github/workflows/unified-desktop.yml').read_text()
    assert workflow.index('tools.darwin_memory_probe') < workflow.index('name: Native ownership, path and resource regression tests')
    assert 'tests/backends/test_process_security.py' in workflow
    assert '${{ runner.temp }}/darwin-memory-investigation' in workflow
    assert '${{ runner.temp }}/native-security-regressions.log' in workflow
    assert 'continue-on-error' not in workflow


def test_interruption_is_not_replaced_by_cleanup_errors(monkeypatch):
    from types import SimpleNamespace
    cancellation = KeyboardInterrupt('original cancellation')
    closed = []
    def interrupt(**kwargs):
        raise cancellation
    def bad_close():
        closed.append('stdout')
        raise OSError('close failed')
    process = SimpleNamespace(pid=42, communicate=interrupt, wait=lambda **kwargs: None,
                              stdout=SimpleNamespace(close=bad_close),
                              stderr=SimpleNamespace(close=lambda: closed.append('stderr')))
    monkeypatch.setattr(probe.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(probe.os, 'killpg', lambda *args: None, raising=False)
    with pytest.raises(KeyboardInterrupt) as captured:
        probe._run(['/controlled/probe'], env={})
    assert captured.value is cancellation
    assert closed == ['stdout', 'stderr']
    assert any('close failed' in note for note in cancellation.__notes__)
