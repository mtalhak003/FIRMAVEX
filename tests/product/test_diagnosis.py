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
