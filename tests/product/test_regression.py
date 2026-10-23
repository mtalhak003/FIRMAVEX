"""Synthetic dispatch seams, bounded manifests and immutable earlier evidence."""
from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import threading
from uuid import uuid4

import pytest

from firmavex.backends.api import request_to_dict
from firmavex.product import regression, workspace
from firmavex.product.provenance import declaration
from tests.product.test_workspace import image, contents


def setup_set(tmp_path, count=3, profile='verilog-icarus'):
    request = image(tmp_path, profile)
    config = workspace.save(tmp_path / 'configs', 'build', request_to_dict(request))
    entries = [{'id': uuid4().hex, 'name': 'test ' + str(i), 'configuration': config['configuration'],
                'values': [i, 0] if profile == 'riscv32-virt' else []} for i in range(count)]
    saved = regression.save(tmp_path / 'sets', 'My set', entries)
    return config, entries, saved


def output(saved, name='run'):
    return Path(saved['directory']) / 'runs' / name


def fake_executor(monkeypatch, statuses=('passed', 'triggered', 'passed'), cancel=None, cleanup=True):
    seen = []
    def execute(request, directory, data, **kwargs):
        from firmavex.backends.engine import _write
        from firmavex.backends.security import fresh_directory
        root = fresh_directory(directory)
        status = statuses[len(seen)]
        seen.append((request, data, declaration(request.profile)))
        record = {'schema_version': 1, 'status': status, 'evidence': {'measurement_mode': 'synthetic_test',
                  'cleanup_verified': cleanup, 'admission': {'profile': {'id': request.profile},
                  'attempt_id': root.name, 'values': list(request.values),
                  'execution_provenance': seen[-1][2]}}}
        _write(root / 'result.json', record)
        if cancel:
            cancel.set()
        return record
    monkeypatch.setattr(workspace, 'execute_captured', execute)
    return seen


def test_create_open_and_edit_revisions_without_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Must not execute'))
    config, entries, first = setup_set(tmp_path)
    before = contents(Path(first['directory']))
    reopened = regression.open_set(first['directory'])
    assert reopened['entries'] == first['entries'] and not reopened['execution_performed']
    assert reopened['entries'][0]['configuration_revision'] == config['identity']
    assert workspace.open_configuration(config['configuration'])['created_at'] == config['created_at']
    entries[1]['name'] = 'edited'
    entries.reverse()
    second = regression.save(tmp_path / 'sets', 'Revised', entries, parent=first['directory'])
    assert second['set_id'] == first['set_id'] and second['parent'] == first['revision']
    assert second['revision'] != first['revision'] and second['created_at']
    assert [e['id'] for e in second['entries']] == [e['id'] for e in entries]
    assert contents(Path(first['directory'])) == before


@pytest.mark.parametrize('mutation', ['empty', 'oversize', 'duplicate', 'bad_id', 'bad_values', 'extra', 'bad_name', 'bad_path'])
def test_invalid_entries_rejected_before_publishing(tmp_path, mutation):
    _, entries, _ = setup_set(tmp_path)
    if mutation == 'empty': entries = []
    if mutation == 'oversize': entries *= 6
    if mutation == 'duplicate': entries[1]['id'] = entries[0]['id']
    if mutation == 'bad_id': entries[0]['id'] = '../escape'
    if mutation == 'bad_values': entries[0]['values'] = [True, -1]
    if mutation == 'extra': entries[0]['extra'] = True
    if mutation == 'bad_name': entries[0]['name'] = 'bad\x1b'
    if mutation == 'bad_path': entries[0]['configuration'] = '../escape'
    with pytest.raises((ValueError, OSError)):
        regression.save(tmp_path / 'invalid', 'set', entries)
    assert not (tmp_path / 'invalid').exists()


def test_configuration_revision_changes_are_explicit_and_prior_evidence_preserved(tmp_path):
    config, entries, first = setup_set(tmp_path)
    old = Path(config['configuration'])
    (old / 'runs' / 'old').mkdir(parents=True)
    (old / 'runs' / 'old' / 'result.json').write_text('old opaque evidence')
    before = contents(old)
    request = image(tmp_path)
    request.source.write_text(request.source.read_text().replace('PASS', 'FAIL'))
    revised = workspace.save(tmp_path / 'configs', 'new build', request_to_dict(request), parent=old)
    entries[0]['configuration'] = revised['configuration']
    second = regression.save(tmp_path / 'sets', 'set', entries, parent=first['directory'])
    assert second['entries'][0]['id'] == first['entries'][0]['id']
    assert second['entries'][0]['configuration_revision'] != first['entries'][0]['configuration_revision']
    assert second['entries'][0]['input_sha256'] != first['entries'][0]['input_sha256']
    assert contents(old) == before


def test_execution_order_counts_provenance_and_rerun_immutability(tmp_path, monkeypatch):
    config, entries, saved = setup_set(tmp_path)
    seen = fake_executor(monkeypatch)
    first = regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert [p['entry_id'] for _, _, p in seen] == [e['id'] for e in entries]
    assert first['counts'] == dict(passed=2, failed=1, cancelled=0, infrastructure_error=0, not_run=0, unavailable=0)
    assert first['state'] == 'completed'
    assert seen[0][2]['configuration_revision'] == config['identity']
    assert seen[0][2]['test_set_revision'] == saved['revision']
    assert regression.inspect(output(saved))['counts'] == first['counts']
    before = contents(output(saved))
    fake_executor(monkeypatch, statuses=('passed', 'passed', 'passed'))
    second = regression.execute(saved['directory'], output(saved, 'second'), trust='trusted_project', previous_run=output(saved))
    assert second['rerun_of'] == first['run_id']
    rows = regression.compare(output(saved), output(saved, 'second'))['rows']
    assert [r['comparison'] for r in rows] == ['same', 'different', 'same']
    assert contents(output(saved)) == before
    assert 'entry_id' not in declaration('verilog-icarus')  # Context never leaks.


@pytest.mark.parametrize('status', ['infrastructure_failure', 'invalid_input', 'invalid_output', 'cancelled'])
def test_stop_on_infrastructure_or_cancellation_and_preserve_not_run(tmp_path, monkeypatch, status):
    _, _, saved = setup_set(tmp_path)
    seen = fake_executor(monkeypatch, statuses=(status,))
    result = regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert len(seen) == 1 and result['counts']['not_run'] == 2
    assert result['state'] == ('cancelled' if status == 'cancelled' else 'stopped')


def test_missing_cleanup_stops_following_entries(tmp_path, monkeypatch):
    _, _, saved = setup_set(tmp_path)
    seen = fake_executor(monkeypatch, cleanup=False)
    result = regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert len(seen) == 1 and result['state'] == 'stopped'
    assert result['counts']['infrastructure_error'] == 1


def test_cancel_between_entries_preserves_completed_outcome(tmp_path, monkeypatch):
    _, _, saved = setup_set(tmp_path)
    event = threading.Event()
    seen = fake_executor(monkeypatch, cancel=event)
    result = regression.execute(saved['directory'], output(saved), trust='trusted_project', cancel_event=event)
    assert len(seen) == 1 and result['counts']['passed'] == 1 and result['counts']['not_run'] == 2
    assert result['state'] == 'cancelled'


@pytest.mark.parametrize('exception', [KeyboardInterrupt, RuntimeError])
def test_exception_retains_partial_summary(tmp_path, monkeypatch, exception):
    _, _, saved = setup_set(tmp_path)
    def interrupted(*a, **k): raise exception()
    monkeypatch.setattr(workspace, 'execute_captured', interrupted)
    result = regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert result['counts']['not_run'] == 2
    assert regression.inspect(output(saved))['entries'][0]['category'] != 'passed'


def test_all_entries_validated_before_any_execution(tmp_path, monkeypatch):
    config, _, saved = setup_set(tmp_path)
    Path(config['configuration'], 'input').write_bytes(b'corrupted input')
    monkeypatch.setattr(workspace, 'execute_captured', lambda *a, **k: pytest.fail('No execution allowed'))
    with pytest.raises(ValueError, match='changed'):
        regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert not output(saved).exists()


def test_cancel_before_execution_and_existing_outputs_rejected(tmp_path, monkeypatch):
    _, _, saved = setup_set(tmp_path)
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt):
        regression.execute(saved['directory'], output(saved), trust='trusted_project', cancel_event=event)
    assert not output(saved).exists()
    fake_executor(monkeypatch)
    regression.execute(saved['directory'], output(saved), trust='trusted_project')
    before = contents(output(saved))
    with pytest.raises((ValueError, FileExistsError)):
        regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert contents(output(saved)) == before


@pytest.mark.parametrize('trust', [None, 'trusted_example', 'untrusted', []])
def test_explicit_all_project_trust_required(tmp_path, trust):
    _, _, saved = setup_set(tmp_path)
    with pytest.raises(ValueError, match='trust'):
        regression.execute(saved['directory'], output(saved), trust=trust)
    assert not output(saved).exists()


def test_worker_storage_operation_never_executes(tmp_path, monkeypatch):
    from firmavex.product.worker import Worker
    from firmavex.product.protocol import decode_command, encode_command, decode_event
    _, _, saved = setup_set(tmp_path)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('No execution'))
    stream = io.BytesIO(); worker = Worker(stream)
    worker.handle(decode_command(encode_command('testset', 'backend_regression', {'action': 'open', 'directory': saved['directory']})))
    worker._thread.join(timeout=5)
    events = [decode_event(line) for line in stream.getvalue().splitlines()]
    assert events[-1]['kind'] == 'result' and events[-1]['payload']['execution_performed'] is False


def test_malformed_oversized_and_changed_manifests(tmp_path):
    _, _, saved = setup_set(tmp_path)
    path = Path(saved['directory']) / 'testset.json'
    for data in (b'not json', b'x' * (regression.MANIFEST_BYTES + 1), b'{}'):
        path.write_bytes(data)
        with pytest.raises(ValueError): regression.open_set(path.parent)


def test_comparison_incompatible_revisions_and_missing_legacy(tmp_path, monkeypatch):
    _, entries, saved = setup_set(tmp_path)
    fake_executor(monkeypatch)
    regression.execute(saved['directory'], output(saved), trust='trusted_project')
    other_config = workspace.save(tmp_path / 'configs', 'different revision', request_to_dict(image(tmp_path)))
    entries[0]['configuration'] = other_config['configuration']
    revised = regression.save(tmp_path / 'sets', 'revised', entries, parent=saved['directory'])
    fake_executor(monkeypatch)
    regression.execute(revised['directory'], output(revised), trust='trusted_project')
    assert regression.compare(output(saved), output(revised))['rows'][0]['comparison'] == 'not comparable'
    legacy = tmp_path / 'legacy'; legacy.mkdir()
    (legacy / 'regression.json').write_text('{}')
    with pytest.raises(ValueError): regression.inspect(legacy)
    from firmavex.product.run_review import comparison_fields
    assert comparison_fields({'evidence': {}})['execution_provenance'] is None


def test_listing_is_bounded_read_only_and_open_is_explicit(tmp_path, monkeypatch):
    _, _, saved = setup_set(tmp_path)
    before = contents(tmp_path / 'sets')
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Listing must not execute'))
    result = regression.listing(tmp_path / 'sets')
    assert result['entries'][0]['name'] == 'My set' and result['limit'] == 200
    assert result['entries'][0]['revision'] == saved['revision']
    assert not result['execution_performed'] and contents(tmp_path / 'sets') == before
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt): regression.listing(tmp_path / 'sets', cancel_event=event)


def test_aggregate_input_budget_rejected_before_dispatch(tmp_path, monkeypatch):
    _, _, saved = setup_set(tmp_path)
    monkeypatch.setattr(regression, 'TOTAL_INPUT_BYTES', 1)
    with pytest.raises(ValueError, match='aggregate'):
        regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert not output(saved).exists()


def test_invalid_last_entry_prevents_first_dispatch(tmp_path, monkeypatch):
    _, entries, first = setup_set(tmp_path)
    config = workspace.save(tmp_path / 'configs', 'last', request_to_dict(image(tmp_path)))
    entries[-1]['configuration'] = config['configuration']
    saved = regression.save(tmp_path / 'sets', 'set', entries, parent=first['directory'])
    Path(config['configuration'], 'input').write_bytes(b'bad last input')
    monkeypatch.setattr(workspace, 'execute_captured', lambda *a, **k: pytest.fail('First entry must not execute'))
    with pytest.raises(ValueError): regression.execute(saved['directory'], output(saved), trust='trusted_project')
    assert not output(saved).exists()


def test_inputs_frozen_before_first_execution(tmp_path, monkeypatch):
    config, _, saved = setup_set(tmp_path)
    original = Path(config['configuration'], 'input').read_bytes()
    seen = fake_executor(monkeypatch)
    def progress(event):
        if event.get('stage') == 'finished':
            Path(config['configuration'], 'input').write_bytes(b'changed after preflight')
    result = regression.execute(saved['directory'], output(saved), trust='trusted_project', event_callback=progress)
    assert result['state'] == 'completed'
    assert all(data == original for _, data, _ in seen)


def test_unfinished_entry_is_unavailable_not_not_run(tmp_path, monkeypatch):
    _, _, saved = setup_set(tmp_path)
    seen = []
    def abort(event):
        if event.get('stage') == 'starting':
            seen.append(regression.inspect(output(saved)))
            raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        regression.execute(saved['directory'], output(saved), trust='trusted_project', event_callback=abort)
    assert seen[0]['entries'][0]['category'] == 'unavailable'
    partial = regression.inspect(output(saved))
    assert partial['state'] == 'cancelled' and partial['counts']['unavailable'] == 1
    assert partial['counts']['not_run'] == 2


def test_environment_diagnostics_and_old_missing_provenance():
    from firmavex.product.provenance import execution_context
    from firmavex.product.run_review import comparison_fields
    from firmavex.product.diagnosis import diagnosis
    with execution_context(configuration_revision='a' * 64, entry_id='b' * 32):
        provenance = declaration('riscv32-virt')
    record = {'status': 'triggered', 'evidence': {'admission': {'profile': {'id': 'riscv32-virt'},
              'execution_provenance': provenance}, 'observation': {'observed_value': 1}}}
    fields = comparison_fields(record)
    assert fields['configuration_revision'] == 'a' * 64
    assert fields['environment_assumptions']['host_os']
    shown = diagnosis(record)
    assert 'Configuration revision: ' + 'a' * 64 in shown
    assert 'observed_value=1' in shown
    assert comparison_fields({'evidence': {}})['environment_assumptions'] is None
    assert 'configuration_revision' not in declaration('riscv32-virt')


@pytest.mark.parametrize('fields', [{'bad': 'x'}, {'entry_id': None}, {'entry_id': '\x00'}, {'entry_id': 'x' * 4097}])
def test_invalid_provenance_rejected(fields):
    from firmavex.product.provenance import execution_context
    with pytest.raises(ValueError):
        with execution_context(**fields): pytest.fail('Invalid provenance accepted')


def test_summary_missing_and_malformed_are_unavailable(tmp_path):
    for data in ('{}', '{bad', 'x' * (regression.SUMMARY_BYTES + 1)):
        directory = tmp_path / uuid4().hex; directory.mkdir()
        (directory / 'regression.json').write_text(data)
        with pytest.raises(ValueError): regression.inspect(directory)


@pytest.mark.parametrize('change', [{'schema_version': 2}, {'schema_version': True}, {'host_os': []}, {'backend': 'unknown'}])
def test_unknown_or_malformed_optional_provenance_is_unavailable(change):
    from firmavex.product.run_review import comparison_fields
    provenance = {**declaration('verilog-icarus'), **change}
    record = {'evidence': {'admission': {'profile': {'id': 'verilog-icarus'}, 'execution_provenance': provenance}}}
    assert comparison_fields(record)['execution_provenance'] is None
    assert comparison_fields(record)['environment_assumptions'] is None
