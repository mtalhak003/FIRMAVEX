"""Workflow presentation validation without Qt or target execution."""
from copy import deepcopy

import pytest

from firmavex.backends.api import Limits
from firmavex.desktop.workflow import display_text, execution_request, result_context


@pytest.mark.parametrize('profile', ['cortex-m3-mps2', 'riscv32-virt', 'verilog-icarus'])
def test_request_preserves_profile_source_and_resource_policy(profile):
    request = execution_request(profile, ' input with spaces ', '0xffffffff, 2', 17.5, 3)
    assert request.profile == profile and str(request.source) == 'input with spaces'
    if profile == 'cortex-m3-mps2':
        assert request.limits == Limits()
    else:
        assert request.limits.timeout_seconds == 17.5
        assert request.limits.artifact_bytes == 3 * 1024 * 1024
    assert request.values == ((0xFFFFFFFF, 2) if profile == 'riscv32-virt' else ())


@pytest.mark.parametrize('values', ['', '1', '1 2 3', '-1,0', '4294967296 0', 'one two', '9' * 1000])
def test_vector_errors_are_actionable_and_do_not_echo_input(values):
    with pytest.raises(ValueError, match='exactly two uint32 inputs') as error:
        execution_request('riscv32-virt', 'input.elf', values, 10, 16)
    assert len(str(error.value)) < 150


@pytest.mark.parametrize('source', ['', '  ', 'a\x00b', 'a\nb', 'x' * 4097])
def test_invalid_paths_are_rejected_without_filesystem_access(source):
    with pytest.raises(ValueError, match='valid path'):
        execution_request('verilog-icarus', source, '', 10, 16)


def test_unresolvable_home_is_an_actionable_validation_error(monkeypatch):
    from pathlib import Path
    def unavailable_home(path):
        raise RuntimeError('No home for this user')
    monkeypatch.setattr(Path, 'expanduser', unavailable_home)
    with pytest.raises(ValueError, match='Choose an explicit input file path'):
        execution_request('verilog-icarus', '~unknown/input.v', '', 10, 16)


def test_saved_identity_comes_from_record_is_bounded_and_preserves_evidence():
    record = {'status': 'triggered', 'evidence': {'admission': {'profile': {'id': 'riscv32-virt'}}}}
    original = deepcopy(record)
    assert 'riscv32-virt' in result_context(record, '/saved/run')
    assert 'Saved run: /saved/run' in result_context(record, '/saved/run')
    assert record == original
    assert 'unknown backend' in result_context({'evidence': None}, '/saved')
    assert display_text('<tag>\x00\n' + 'x' * 10000, 20) == '<tag>  ' + 'x' * 13 + '…'
    assert len(result_context({'status': 'x' * 10000}, 'p' * 10000)) < 1250
