"""Read-only integration against actual persisted synthetic backend records."""
import io
import json
import threading

import pytest

from firmavex.product.run_review import history, compare
from firmavex.product.worker import Worker
from firmavex.product.protocol import encode_command, decode_command, decode_event


def stored(root, status='passed', profile='verilog-icarus', **extra):
    root.mkdir()
    admission = {'attempt_id': root.name, 'profile': {'id': profile},
                 'values': [2, 1] if profile == 'riscv32-virt' else []}
    (root / 'admission.json').write_text(json.dumps(admission), encoding='utf-8')
    (root / 'result.json').write_text(json.dumps({'schema_version': 1, 'status': status,
        'evidence': {'admission': admission, 'measurement_mode': 'synthetic_test',
                     'cleanup_verified': True, **extra}}), encoding='utf-8')
    return str(root)


def archive(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('profile', ['cortex-m3-mps2', 'riscv32-virt', 'verilog-icarus'])
def test_comparison_revalidates_saved_records_and_never_changes_evidence(tmp_path, profile):
    left = stored(tmp_path / 'left', profile=profile)
    right = stored(tmp_path / 'right', status='cancelled', profile=profile)
    before = archive(tmp_path)
    result = compare(left, right)
    rows = {row['field']: row for row in result['rows']}
    assert result['read_only'] and rows['status']['comparison'] == 'changed'
    assert rows['backend']['comparison'] == 'unchanged'
    assert rows['started_at_utc']['comparison'] == 'unavailable'
    assert result['right']['state'] == 'cancelled'
    assert result['left']['evidence_reference'].endswith('result.json')
    # An externally changed result is inspected again, not served from a UI cache.
    (tmp_path / 'right/result.json').write_text('{}')
    assert compare(left, right)['right']['inspection'] == 'unavailable'
    (tmp_path / 'right/result.json').write_bytes(before['right/result.json'])
    assert archive(tmp_path) == before


def test_history_preserves_unknown_legacy_malformed_and_incomplete(tmp_path):
    valid = stored(tmp_path / 'valid')
    incomplete = stored(tmp_path / 'incomplete')
    (tmp_path / 'incomplete/result.json').unlink()
    legacy = tmp_path / 'legacy'; legacy.mkdir()
    (legacy / 'result.json').write_text('{"success":true}')
    malformed = tmp_path / 'bad'; malformed.mkdir()
    (malformed / 'result.json').write_text('not JSON')
    before = archive(tmp_path)
    result = history([valid, incomplete, str(legacy), str(malformed), str(tmp_path / 'missing')])
    assert [entry['state'] for entry in result['entries']] == ['completed', 'incomplete', 'unknown', 'unknown', 'unknown']
    assert result['entries'][1]['fields']['measurement'] is None
    assert archive(tmp_path) == before


def test_unknown_optional_metadata_does_not_invent_a_value(tmp_path):
    left = stored(tmp_path / 'left', measurement_mode=['malformed'])
    # Inspector may reject malformed optional evidence; never call it a match.
    assert all(row['comparison'] == 'unavailable' for row in compare(left, str(tmp_path / 'missing'))['rows'])


def test_cancellation_stops_before_next_inspection_without_writing(tmp_path, monkeypatch):
    from firmavex.product import run_review
    path = stored(tmp_path / 'left')
    before = archive(tmp_path)
    cancel = threading.Event()
    original = run_review.inspect_run
    def inspect(path):
        cancel.set()
        return original(path)
    monkeypatch.setattr(run_review, 'inspect_run', inspect)
    with pytest.raises(KeyboardInterrupt):
        history([path, path], cancel_event=cancel)
    assert archive(tmp_path) == before


@pytest.mark.parametrize('paths', [['a'] * 51, 'a', [''], ['x' * 4097], ['a\x00b'], ['😀' * 4096] * 2])
def test_history_input_bounds(paths):
    with pytest.raises(ValueError):
        history(paths)


@pytest.mark.parametrize('command', ['backend_history', 'backend_compare'])
def test_worker_dispatches_review_without_runtime_or_execution(tmp_path, command, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: pytest.fail('Review must not execute processes'))
    path = stored(tmp_path / 'run')
    payload = {'run_dirs': [path]} if command == 'backend_history' else {'left': path, 'right': path}
    before = archive(tmp_path)
    output = io.BytesIO()
    worker = Worker(output)
    worker.handle(decode_command(encode_command('review', command, payload)))
    worker._thread.join(timeout=5)
    assert not worker._thread.is_alive()
    result = [decode_event(line) for line in output.getvalue().splitlines()][-1]
    assert result['kind'] == 'result' and result['payload']['read_only']
    assert archive(tmp_path) == before


def test_worker_review_cancellation_is_not_reported_as_execution(tmp_path, monkeypatch):
    from firmavex.product import run_review
    def cancelled(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(run_review, 'history', cancelled)
    output = io.BytesIO()
    worker = Worker(output)
    worker.handle(decode_command(encode_command('review', 'backend_history', {'run_dirs': []})))
    worker._thread.join(timeout=5)
    event = [decode_event(line) for line in output.getvalue().splitlines()][-1]
    assert event['kind'] == 'error' and event['payload']['category'] == 'cancelled'
    assert 'Read-only review cancelled' in event['payload']['message']


def test_invalid_optional_timestamp_and_cleanup_are_unavailable():
    from firmavex.product.run_review import fields
    result = fields({'status': 'passed', 'evidence': {'cleanup_verified': 'yes',
                    'admission': {'started_at_utc': 'invalid'}}})
    assert result['started_at_utc'] is None and result['cleanup_verified'] is None
