"""Diagnostic review never executes or changes retained evidence."""
import copy
import threading

import pytest

from firmavex.product.diagnosis import (diagnosis, inspect_artifact, FILE_LIMIT,
                                       SIGNAL_LIMIT, TEXT_LIMIT)
from firmavex.product.run_review import compare
from tests.product.test_run_review import stored, archive


@pytest.mark.parametrize('backend', ['cortex-m3-mps2', 'riscv32-virt', 'verilog-icarus'])
@pytest.mark.parametrize('status,category', [('triggered', 'firmware/test failure'),
    ('infrastructure_failure', 'tool or infrastructure failure'), ('cancelled', 'cancellation')])
def test_diagnosis_recorded_classification_and_immutability(backend, status, category):
    record = {'status': status, 'evidence': {'admission': {'profile': {'id': backend},
        'attempt_id': 'attempt-1'}, 'stderr': 'bad\x1b\x00output', 'observation': {'triggered': True}}}
    before = copy.deepcopy(record)
    result = diagnosis(record)
    assert category in result and 'attempt-1' in result
    assert 'Execution stage: unavailable' in result
    assert 'Expected behavior: unavailable' in result
    assert '\x1b' not in result and '\x00' not in result
    assert record == before
    assert ('QEMU/GDB' in result) == (backend != 'verilog-icarus')


@pytest.mark.parametrize('record', [None, {}, {'status': []}, {'evidence': []}])
def test_missing_malformed_diagnosis(record):
    assert 'Failure category: unavailable' in diagnosis(record)


def test_log_bounds_missing_unsupported_and_cancellation(tmp_path):
    path = tmp_path / 'retained.log'
    path.write_bytes(b'a\x00\x1b' * TEXT_LIMIT)
    before = path.read_bytes()
    result = inspect_artifact(path)
    assert len(result) < TEXT_LIMIT + 100 and 'truncated' in result
    assert '\x00' not in result and '\x1b' not in result
    assert path.read_bytes() == before
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt):
        inspect_artifact(path, cancel_event=event)
    assert 'unavailable' in inspect_artifact(tmp_path / 'missing.log')
    assert 'Unsupported' in inspect_artifact(tmp_path / 'program.vvp')
    path.write_bytes(b'a' * (FILE_LIMIT + 1))
    assert 'unavailable' in inspect_artifact(path)


def test_vcd_metadata_multiline_and_immutable(tmp_path):
    path = tmp_path / 'trace.vcd'
    data = '$timescale\n 1 ns\n$end\n$var wire 1 ! ready $end\n$enddefinitions $end\n#0\n0!\n#42\n1!\n'
    path.write_text(data)
    result = inspect_artifact(path)
    assert 'Timescale: 1 ns' in result and 'ready' in result
    assert 'Duration in timestamp units: 42' in result
    assert path.read_text() == data


@pytest.mark.parametrize('data,expected', [('nonsense', 'Malformed'),
    ('$enddefinitions $end\n#abc', 'Malformed'),
    ('$enddefinitions $end\n#4\n#2', 'Malformed'),
    ('$var wire $end\n$enddefinitions $end', 'Malformed'),
    ('$var wire 1 ! signal $end\n' * (SIGNAL_LIMIT + 1) + '$enddefinitions $end', 'signal limit'),
    ('$enddefinitions $end\n' + '\n' * 20001, 'line limit')])
def test_vcd_rejects_malformed_and_bounded(tmp_path, data, expected):
    path = tmp_path / 'trace.vcd'; path.write_text(data)
    assert expected in inspect_artifact(path)


def test_symlink_not_read(tmp_path):
    path = tmp_path / 'trace.log'
    path.symlink_to(tmp_path / 'missing')
    assert 'unsafe' in inspect_artifact(path)


def test_comparison_identity_environment_and_missing_fields(tmp_path):
    left = stored(tmp_path / 'left', tools={'compiler': {'version': '1'}}, source={'sha256': 'a' * 64})
    right = stored(tmp_path / 'right', tools={'compiler': {'version': '2'}}, source={'sha256': 'a' * 64})
    before = archive(tmp_path)
    result = compare(left, right)
    rows = {r['field']: r for r in result['rows']}
    assert rows['input_identity']['comparison'] == 'same'
    assert rows['tool_runtime_identity']['comparison'] == 'different'
    assert rows['project_configuration']['comparison'] == 'unavailable'
    assert rows['replay_metadata']['comparison'] == 'unavailable'
    assert 'not authenticity' in result['scope']
    assert archive(tmp_path) == before
    other = stored(tmp_path / 'other', profile='riscv32-virt', firmware={'sha256': 'a' * 64})
    rows = {r['field']: r for r in compare(left, other)['rows']}
    assert rows['input_identity']['comparison'] == 'not comparable'


@pytest.mark.parametrize('value', [{}, [], 'a' * 4097, {'a': {'b': {'c': {'d': {'e': {'f': 1}}}}}},
    {'tools': ['x'] * 33}, {'tools': [['x'] * 32] * 32}])
def test_excessive_or_missing_comparison_metadata_unavailable(value):
    from firmavex.product.run_review import comparison_fields
    result = comparison_fields({'evidence': {'tools': value}})
    assert result['tool_runtime_identity'] is None


def test_inline_log_and_observation_display_bounded():
    record = {'status': 'invalid_output', 'evidence': {'stderr': '\x00' * 100000,
        'stdout': 'x' * 100000, 'observation': {str(i): 'x' * 100000 for i in range(100)}}}
    result = diagnosis(record)
    assert len(result) < 4000 and '\x00' not in result and 'truncated' in result


def test_configuration_optional_nulls_and_finite_timeouts_remain_comparable():
    from firmavex.product.run_review import comparison_fields
    config = {'firmware': 'firmware.elf', 'seed': None, 'timeout_seconds': 10.0,
              'input_symbols': ['a', 'b']}
    result = comparison_fields({'evidence': {'admission': {'configuration': config}}})
    assert result['project_configuration'] == config


def test_failure_cause_remains_visible_in_bounded_excerpt():
    from firmavex.product.provenance import declaration, execution_context
    with execution_context(configuration_revision='a' * 64, configuration_created_at='2026-10-24T00:00:00+00:00',
        input_sha256='b' * 64, test_set_id='c' * 32, test_set_revision='d' * 64, entry_id='e' * 32,
        regression_run_id='f' * 32, rerun_of='0' * 32):
        provenance = declaration('riscv32-virt')
    record = {'status': 'infrastructure_failure', 'evidence': {'admission': {'attempt_id': '1' * 32,
        'profile': {'id': 'riscv32-virt'}, 'execution_provenance': provenance},
        'error': 'NotADirectoryError: [WinError 267] The directory name is invalid'}}
    assert 'WinError 267' in diagnosis(record)[:1024]


def rv_failure_record(*, status='infrastructure_failure', stage='debugger_observation',
                      category='timeout', tool='gdb', return_code=None):
    """Invented metadata exercises display contracts, not real firmware execution."""
    return {'status': status, 'evidence': {
        'backend': 'riscv32-virt', 'measurement_mode': 'synthetic_test',
        'admission': {'profile': {'id': 'riscv32-virt'}, 'attempt_id': 'synthetic-rv-attempt'},
        'failure_diagnostic': {'schema_version': 1, 'backend': 'riscv32-virt',
            'stage': stage, 'category': category, 'tool': tool, 'return_code': return_code}}}


@pytest.mark.parametrize('stage,category,tool,code,phase,cause', [
    ('tool_probe', 'timeout', 'qemu', None, 'Runtime version probe', 'Timeout'),
    ('qemu_startup', 'timeout', 'qemu', None, 'QEMU startup', 'Timeout'),
    ('debugger_observation', 'timeout', 'gdb', None, 'Debugger observation', 'Timeout'),
    ('tool_probe', 'tool_exit', 'gdb', 7, 'Runtime version probe', 'Tool process exited'),
    ('qemu_startup', 'tool_exit', 'qemu', 0, 'QEMU startup', 'Tool process exited'),
    ('debugger_observation', 'tool_exit', 'gdb', -9, 'Debugger observation', 'Tool process exited'),
    ('completion_validation', 'invalid_observation', 'gdb', None,
     'Completion validation', 'Invalid completion observation'),
    ('identity_validation', 'identity_changed', None, None,
     'Identity validation', 'Retained input or runtime identity changed'),
    ('identity_validation', 'identity_changed', 'qemu', None,
     'Identity validation', 'Retained input or runtime identity changed'),
    ('debugger_observation', 'infrastructure_error', 'gdb', None,
     'Debugger observation', 'Infrastructure error; specific cause not established'),
], ids=['probe-timeout', 'startup-timeout', 'observation-timeout', 'probe-exit',
        'startup-clean-exit', 'debugger-signal', 'invalid-completion', 'image-changed',
        'tool-changed', 'unknown-infrastructure'])
def test_rv_failure_detail_uses_supported_structured_phase_and_cause(
        stage, category, tool, code, phase, cause):
    record = rv_failure_record(stage=stage, category=category, tool=tool, return_code=code)
    before = copy.deepcopy(record)
    shown = diagnosis(record)
    assert 'RV32 execution diagnostic' in shown
    assert 'Recorded phase: ' + phase in shown
    assert 'Recorded cause: ' + cause in shown
    assert 'Recorded tool: ' + (tool or 'unavailable') in shown
    assert 'Recorded exit code: ' + (str(code) if code is not None else 'unavailable') in shown
    assert 'Failure category: tool or infrastructure failure' in shown
    assert 'Build outcome: not assessed' in shown
    assert 'Assertion cause: not established' in shown
    assert record == before


def test_rv_cancellation_detail_preserves_the_recorded_cancellation_category():
    record = rv_failure_record(status='cancelled', category='cancelled')
    before = copy.deepcopy(record)
    shown = diagnosis(record)
    assert 'Failure category: cancellation' in shown
    assert 'Recorded cause: Cancellation' in shown
    assert record == before


@pytest.mark.parametrize('status', ['passed', 'triggered'])
def test_rv_completed_observation_does_not_become_a_pipeline_failure_or_assertion(status):
    record = rv_failure_record(status=status)
    record['evidence'].pop('failure_diagnostic')
    record['evidence'].update(completion_observed=True, observation={'triggered': status == 'triggered'})
    before = copy.deepcopy(record)
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert 'Recorded cause: Timeout' not in shown
    assert 'Build outcome: not assessed' in shown
    assert 'Assertion cause: not established' in shown
    assert ('Failure category: no failure recorded' if status == 'passed'
            else 'Failure category: firmware/test failure') in shown
    assert record == before


@pytest.mark.parametrize('diagnostic', [
    None, [], 'TimeoutError', {},
    {'schema_version': 1},
    {'schema_version': True, 'backend': 'riscv32-virt', 'stage': 'debugger_observation',
     'category': 'timeout', 'tool': 'gdb', 'return_code': None},
    {'schema_version': 2, 'backend': 'riscv32-virt', 'stage': 'debugger_observation',
     'category': 'timeout', 'tool': 'gdb', 'return_code': None},
], ids=['none', 'list', 'string', 'empty', 'partial', 'bool-version', 'future-version'])
def test_rv_absent_or_unsupported_detail_is_unavailable(diagnostic):
    record = rv_failure_record()
    record['evidence']['failure_diagnostic'] = diagnostic
    before = copy.deepcopy(record)
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert 'Recorded cause: Timeout' not in shown
    assert record == before


@pytest.mark.parametrize('field,value', [
    ('backend', 'cortex-m3-mps2'), ('backend', []),
    ('stage', 'unknown'), ('stage', []), ('category', 'assertion_failure'), ('category', []),
    ('tool', 'unknown-tool'), ('tool', []), ('return_code', True),
    ('return_code', '1'), ('return_code', 2**32), ('return_code', -(2**31) - 1),
], ids=['wrong-backend', 'backend-list', 'unknown-stage', 'stage-list', 'unsupported-cause',
        'cause-list', 'unknown-tool', 'tool-list', 'bool-code', 'string-code', 'large-code', 'small-code'])
def test_rv_malformed_detail_values_do_not_drive_a_classification(field, value):
    record = rv_failure_record()
    record['evidence']['failure_diagnostic'][field] = value
    shown = diagnosis(record)
    assert 'Recorded cause: Timeout' not in shown
    assert 'Recorded cause: unavailable' in shown


@pytest.mark.parametrize('changes', [
    {'stage': 'qemu_startup', 'tool': 'gdb'},
    {'stage': 'debugger_observation', 'tool': 'qemu'},
    {'stage': 'tool_probe', 'tool': None},
    {'stage': 'identity_validation', 'category': 'tool_exit', 'return_code': 2},
    {'stage': 'qemu_startup', 'category': 'invalid_observation', 'tool': 'qemu'},
    {'stage': 'debugger_observation', 'category': 'identity_changed'},
    {'category': 'timeout', 'return_code': 7},
    {'category': 'tool_exit', 'return_code': None},
    {'category': 'tool_exit', 'return_code': 0},
], ids=['startup-gdb', 'observation-qemu', 'probe-no-tool', 'identity-exit',
        'startup-invalid-completion', 'observation-identity-change', 'timeout-code',
        'exit-without-code', 'debugger-zero-exit'])
def test_rv_contradictory_phase_cause_and_tool_remain_unavailable(changes):
    record = rv_failure_record()
    record['evidence']['failure_diagnostic'].update(changes)
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert 'Recorded phase: unavailable' in shown


@pytest.mark.parametrize('status,category', [('passed', 'timeout'), ('triggered', 'timeout'),
    ('cancelled', 'timeout'), ('infrastructure_failure', 'cancelled'), ('invalid_input', 'timeout')],
    ids=['passed', 'triggered', 'cancelled-timeout', 'infrastructure-cancelled', 'input-timeout'])
def test_rv_detail_must_agree_with_the_recorded_terminal_outcome(status, category):
    record = rv_failure_record(status=status, category=category)
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert 'Recorded cause: Timeout' not in shown
    assert 'Recorded cause: Cancellation' not in shown


@pytest.mark.parametrize('identity', ['cortex-m3-mps2', 'verilog-icarus', [], None],
                         ids=['arm', 'hdl', 'malformed', 'missing-value'])
def test_rv_conflicting_admission_identity_cannot_borrow_other_backend_detail(identity):
    record = rv_failure_record()
    record['evidence']['admission']['profile']['id'] = identity
    shown = diagnosis(record)
    assert 'Recorded cause: Timeout' not in shown


def test_rv_diagnostic_without_outer_backend_context_cannot_supply_its_own_identity():
    record = rv_failure_record()
    record['evidence'].pop('backend')
    record['evidence'].pop('admission')
    assert 'Recorded cause: Timeout' not in diagnosis(record)


def test_rv_legacy_error_text_is_not_parsed_as_timeout_or_assertion():
    record = rv_failure_record()
    record['evidence'].pop('failure_diagnostic')
    record['evidence']['error'] = 'TimeoutError: assert failed; infrastructure prose is not structured evidence'
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert 'Recorded cause: Timeout' not in shown
    assert 'Assertion cause: not established' in shown
    assert 'Retained error:' in shown


def test_rv_detail_display_is_bounded_sanitized_and_never_executes_or_reads(monkeypatch):
    import socket
    import subprocess
    from firmavex.product import diagnosis as diagnostic_module
    record = rv_failure_record()
    record['evidence']['failure_diagnostic']['category'] = 'PRIVATE-CONTROL\x1b\x00' * 10000
    before = copy.deepcopy(record)
    def forbidden(*args, **kwargs):
        raise AssertionError('Read-only diagnosis attempted I/O or execution')
    monkeypatch.setattr(diagnostic_module, 'read_bytes', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert 'PRIVATE-CONTROL' not in shown and '\x1b' not in shown and '\x00' not in shown
    assert len(shown) < 3500
    assert record == before


def test_rv_detail_rejects_extra_arbitrary_metadata_instead_of_displaying_it():
    record = rv_failure_record()
    record['evidence']['failure_diagnostic']['private_path'] = '/private/never-read-or-display'
    shown = diagnosis(record)
    assert 'Recorded cause: unavailable' in shown
    assert '/private/never-read-or-display' not in shown
