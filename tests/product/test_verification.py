"""Synthetic persisted evidence checks; never native execution qualification."""
import hashlib
import io
import json
import sys
import threading

import pytest

from firmavex.product.verification import verify, digest
from firmavex.product.store import RunStore
from firmavex.product.errors import ProductError


def saved(root, *, large=False):
    root.mkdir()
    items = []
    for name, data in [('a.bin', b'first'), ('b.bin', b'x' * (3 * 1024 * 1024) if large else b'second'), ('c.bin', b'last')]:
        (root / name).write_bytes(data)
        items.append({'name': name, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    admission = {'attempt_id': 'synthetic', 'profile': {'id': 'verilog-icarus'}, 'values': []}
    (root / 'admission.json').write_text(json.dumps(admission), encoding='utf-8')
    (root / 'result.json').write_text(json.dumps({'schema_version': 1, 'status': 'passed',
        'evidence': {'admission': admission, 'measurement_mode': 'synthetic_test', 'artifacts': items}}), encoding='utf-8')
    return str(root)


def archive(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_progress_and_results_only_claim_checks_actually_finished(tmp_path):
    path = saved(tmp_path / 'run')
    before = archive(tmp_path)
    events = []
    result = verify(path, event_callback=events.append)
    assert result['status'] == 'verified' and result['success']
    assert result['completed'] == result['matched'] == result['total'] == 3
    assert [row['state'] for row in result['items']] == ['hash_match'] * 3
    assert events[0]['total'] is None and events[0]['phase'] == 'inspecting_archive'
    assert [e['completed'] for e in events if e['phase'] == 'artifact'] == [0, 1, 1, 2, 2, 3]
    assert archive(tmp_path) == before


@pytest.mark.parametrize('pass_number', [1, 2])
def test_cancel_during_capture_or_recapture_retains_completed_rows(tmp_path, monkeypatch, pass_number):
    from firmavex.backends import security
    path = saved(tmp_path / 'run', large=True)
    before = archive(tmp_path)
    cancel = threading.Event()
    original = security.os.fdopen
    class Reader:
        def __init__(self, stream): self.stream, self.second = stream, False
        def __enter__(self): self.stream.__enter__(); return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def __getattr__(self, name): return getattr(self.stream, name)
        def seek(self, *args): self.second = True; return self.stream.seek(*args)
        def read(self, count):
            data = self.stream.read(count)
            if len(data) == 1024 * 1024 and self.second == (pass_number == 2):
                cancel.set()
            return data
    monkeypatch.setattr(security.os, 'fdopen', lambda *a, **kw: Reader(original(*a, **kw)))
    result = verify(path, cancel_event=cancel)
    assert result['status'] == 'cancelled' and not result['success']
    assert [row['state'] for row in result['items']] == ['hash_match', 'cancelled', 'not_checked']
    assert result['completed'] == result['matched'] == 1 and result['total'] == 3
    assert archive(tmp_path) == before


def test_cancel_during_digest_never_returns_partial_hash():
    class Cancel:
        calls = 0
        def is_set(self):
            self.calls += 1
            return self.calls == 2
    with pytest.raises(KeyboardInterrupt):
        digest(b'x' * (3 * 1024 * 1024), Cancel())


@pytest.mark.parametrize('failure,state', [('missing', 'missing_artifact'), ('mismatch', 'hash_mismatch'),
                                         ('metadata', 'unavailable_metadata'), ('read', 'read_error')])
def test_failures_preserve_matches_and_do_not_skip_required_checks(tmp_path, monkeypatch, failure, state):
    from firmavex.backends import report
    path = saved(tmp_path / 'run')
    if failure == 'missing': (tmp_path / 'run/b.bin').unlink()
    if failure == 'mismatch': (tmp_path / 'run/b.bin').write_bytes(b'tampered')
    if failure == 'metadata':
        record_path = tmp_path / 'run/result.json'
        record = json.loads(record_path.read_text())
        record['evidence']['artifacts'][1]['sha256'] = 'invalid'
        record_path.write_text(json.dumps(record), encoding='utf-8')
    if failure == 'read':
        original = report.read_bytes
        def read(path, *a, **kw):
            if path.name == 'b.bin': raise PermissionError('private environment detail')
            return original(path, *a, **kw)
        monkeypatch.setattr(report, 'read_bytes', read)
    before = archive(tmp_path)
    result = verify(path)
    assert result['status'] == 'failed' and not result['success']
    assert [row['state'] for row in result['items']] == ['hash_match', state, 'not_checked']
    assert 'private environment detail' not in json.dumps(result)
    assert archive(tmp_path) == before


def test_empty_or_malformed_inventory_never_becomes_verified(tmp_path):
    path = saved(tmp_path / 'run')
    record_path = tmp_path / 'run/result.json'
    record = json.loads(record_path.read_text())
    record['evidence']['artifacts'] = []
    record_path.write_text(json.dumps(record))
    assert verify(path)['status'] == 'unavailable'
    record['evidence']['artifacts'] = [None]
    record_path.write_text(json.dumps(record))
    result = verify(path)
    assert not result['success'] and result['items'][0]['state'] == 'unavailable_metadata'


def test_arm_registered_artifacts_verify_readonly_and_cancel_between_files(tmp_path):
    root = tmp_path / 'arm'
    with RunStore(root, create=True) as store:
        store.initialize({'application': 'firmavex-desktop', 'measurement_mode': 'synthetic_test'})
        for name in ('a.txt', 'b.txt', 'c.txt'):
            store.write_text(name, 'synthetic retained bytes')
    before = archive(root)
    assert verify(str(root))['status'] == 'verified'
    cancel = threading.Event()
    def stop(event):
        if event.get('phase') == 'artifact' and event.get('item', {}).get('state') == 'hash_match': cancel.set()
    result = verify(str(root), cancel_event=cancel, event_callback=stop)
    assert result['status'] == 'cancelled' and result['matched'] == 1
    assert [row['state'] for row in result['items']] == ['hash_match', 'not_checked', 'not_checked']
    assert archive(root) == before
    (root / 'a.txt').write_bytes(b'tampered')
    failed = verify(str(root))
    assert failed['status'] == 'failed' and failed['items'][0]['state'] == 'hash_mismatch'
    with RunStore(root) as store:
        with pytest.raises(ProductError, match='identity mismatch'):
            store.verify_artifacts()  # Existing default enforcement remains strict.
    (root / 'a.txt').write_bytes(before['a.txt'])
    (root / 'b.txt').unlink()
    assert verify(str(root))['items'][1]['state'] == 'missing_artifact'
    (root / 'b.txt').write_bytes(before['b.txt'])
    assert archive(root) == before


def test_progress_inventory_cap_fails_closed_instead_of_truncating(monkeypatch):
    class Cursor:
        def fetchmany(self, size): return [(str(i), 'a' * 64, 0) for i in range(257)]
    class Db:
        def execute(self, query): return Cursor()
    store = RunStore.__new__(RunStore)
    monkeypatch.setattr(store, '_db', lambda: Db())
    with pytest.raises(ProductError, match='count limit exceeded'):
        store.verify_artifacts(event_callback=lambda *a, **kw: None)


def test_worker_transport_streams_progress_without_dispatch(tmp_path, monkeypatch):
    from firmavex.product.worker import Worker
    from firmavex.product.protocol import encode_command, decode_command, decode_event
    import subprocess
    path = saved(tmp_path / 'run')
    before = archive(tmp_path)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: pytest.fail('Evidence must never execute'))
    output = io.BytesIO()
    worker = Worker(output)
    worker.handle(decode_command(encode_command('verify', 'backend_verify', {'run_dir': path})))
    worker._thread.join(timeout=5)
    assert not worker._thread.is_alive()
    events = [decode_event(line) for line in output.getvalue().splitlines()]
    assert any(e['kind'] == 'progress' for e in events)
    assert events[-1]['kind'] == 'result' and events[-1]['payload']['status'] == 'verified'
    assert archive(tmp_path) == before


def test_worker_cancel_channel_stops_hashing_with_partial_result(tmp_path, monkeypatch):
    from firmavex.product import verification
    from firmavex.product.worker import Worker
    from firmavex.product.protocol import encode_command, decode_command, decode_event
    path = saved(tmp_path / 'run', large=True)
    before = archive(tmp_path)
    hashing, release = threading.Event(), threading.Event()
    original = verification.digest
    def paused(data, cancel_event=None):
        if len(data) > 1024 * 1024:
            hashing.set()
            assert release.wait(5), 'Cancellation test did not release the hash phase'
        return original(data, cancel_event)
    monkeypatch.setattr(verification, 'digest', paused)
    output = io.BytesIO()
    worker = Worker(output)
    worker.handle(decode_command(encode_command('verify', 'backend_verify', {'run_dir': path})))
    try:
        assert hashing.wait(5), 'Worker did not reach the hash phase'
        worker.handle(decode_command(encode_command('stop', 'cancel', {'job_request_id': 'verify'})))
    finally:
        release.set()
        worker._thread.join(timeout=5)
    assert not worker._thread.is_alive()
    events = [decode_event(line) for line in output.getvalue().splitlines()]
    result = events[-1]['payload']
    assert result['status'] == 'cancelled' and not result['success']
    assert [r['state'] for r in result['items']] == ['hash_match', 'cancelled', 'not_checked']
    assert archive(tmp_path) == before


def test_session_provenance_freshness_and_read_only_report(tmp_path, monkeypatch):
    from datetime import datetime
    from firmavex.product.verification_session import review
    path = saved(tmp_path / 'run')
    before = archive(tmp_path / 'run')
    session = verify(path)
    provenance = session['provenance']
    assert datetime.fromisoformat(provenance['started_at']) <= datetime.fromisoformat(provenance['finished_at'])
    assert provenance['archive'] == path
    assert provenance['scope'] == 'Listed backend artifacts'
    assert provenance['completion'] == 'completed' and not provenance['partial']
    assert session['freshness']['state'] == 'unknown'
    # Metadata-only review must not read/rehash artifact contents.
    monkeypatch.setattr('firmavex.product.verification.digest', lambda *a: pytest.fail('unexpected rehash'))
    result = review(session, output_dir=str(tmp_path / 'report'))
    assert result['freshness']['state'] == 'no_observed_metadata_changes'
    report = (tmp_path / 'report' / 'verification.txt').read_text(encoding='utf-8')
    assert 'authenticity' in report and path in report and 'hash_match' in report
    assert 'unchanged bytes' in report
    assert archive(tmp_path / 'run') == before
    (tmp_path / 'run' / 'a.bin').write_bytes(b'changed data')
    assert review(session)['freshness']['state'] == 'stale'
    assert session['items'][0]['state'] == 'hash_match'  # historical observation retained
    with pytest.raises(FileExistsError):
        review(session, output_dir=str(tmp_path / 'report'))


def test_unknown_freshness_and_export_rejections(tmp_path):
    from firmavex.product.verification_session import review
    session = verify(saved(tmp_path / 'run'))
    (tmp_path / 'run' / 'a.bin').unlink()
    assert review(session)['freshness']['state'] == 'unknown'
    session['observations'] = None
    assert review(session)['freshness']['state'] == 'unknown'
    before = archive(tmp_path / 'run')
    with pytest.raises(ValueError, match='outside original'):
        review(session, output_dir=str(tmp_path / 'run' / 'report'))
    assert archive(tmp_path / 'run') == before
    for value in ({}, {'provenance': {}, 'items': []}, dict(session, items=[None]),
                  dict(session, observations=[{'name': '../outside', 'state': [1]*5}])):
        if value.get('observations') == [{'name': '../outside', 'state': [1]*5}]:
            assert review(value)['freshness']['state'] == 'unknown'
        else:
            with pytest.raises(ValueError):
                review(value)


def test_cancelled_session_report_is_bounded_and_never_overwrites_evidence(tmp_path):
    from firmavex.product.verification_session import review
    path = saved(tmp_path / 'run')
    cancel = threading.Event()
    def stop(event):
        if event.get('phase') == 'artifact' and event.get('completed') == 1:
            cancel.set()
    session = verify(path, cancel_event=cancel, event_callback=stop)
    assert session['provenance']['completion'] == 'cancelled'
    assert session['provenance']['partial']
    assert [r['state'] for r in session['items']] == ['hash_match', 'not_checked', 'not_checked']
    before = archive(tmp_path / 'run')
    with pytest.raises(KeyboardInterrupt):
        review(session, output_dir=str(tmp_path / 'cancelled'), cancel_event=cancel)
    assert not (tmp_path / 'cancelled').exists()
    session['items'] = [{'name': '<script>\n' + '長' * 160, 'state': 'hash_match\r\nforged'}] * 256
    session['diagnostic'] = 'x' * 1000
    result = review(session, output_dir=str(tmp_path / 'report'))
    data = (tmp_path / 'report' / 'verification.txt').read_bytes()
    assert len(data) <= 262144 and b'\r' not in data and b'\nforged' not in data
    assert b'completion: cancelled' in data and b'not proof' in data
    assert archive(tmp_path / 'run') == before


def test_real_supervised_session_review_export_and_portable_freshness(tmp_path):
    from firmavex.product.supervisor import Supervisor
    from firmavex.product.verification_session import review
    path = saved(tmp_path / 'run')
    before = archive(tmp_path / 'run')
    session = Supervisor().execute('backend_verify', {'run_dir': path})
    result = Supervisor().execute('backend_verification_review', {
        'session': session, 'output_dir': str(tmp_path / 'report')})
    assert result['freshness']['state'] == 'no_observed_metadata_changes'
    assert (tmp_path / 'report' / 'verification.txt').is_file()
    assert archive(tmp_path / 'run') == before
    session['provenance']['platform'] = 'different-platform'
    assert review(session)['freshness']['state'] == 'unknown'


def test_legacy_arm_report_scope_and_malformed_freshness_are_unknown(tmp_path):
    from firmavex.product.verification_session import review
    root = tmp_path / 'legacy-arm'
    with RunStore(root, create=True) as store:
        store.initialize({'application': 'firmavex-desktop', 'measurement_mode': 'synthetic_test'})
        store.write_text('a.txt', 'retained legacy artifact')
    before = archive(root)
    session = verify(str(root))
    assert session['provenance']['scope'] == 'Registered ARM artifacts'
    assert session['status'] == 'verified'
    # This legacy archive has no result.json; missing freshness data is unknown.
    assert review(session)['freshness']['state'] == 'unknown'
    session['observations'] = [{'name': 'a.txt', 'state': [True]}, {'name': 'run.sqlite3', 'state': None}]
    assert review(session)['freshness']['state'] == 'unknown'
    review(session, output_dir=str(tmp_path / 'legacy report'))
    assert archive(root) == before


def test_report_rejects_symlink_destination_and_traversing_archive(tmp_path):
    from firmavex.product.verification_session import review
    session = verify(saved(tmp_path / 'run'))
    before = archive(tmp_path / 'run')
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(tmp_path / 'run', target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create directory symlinks')
    with pytest.raises(ValueError, match='Symlink/reparse'):
        review(session, output_dir=str(alias / 'report'))
    session['provenance']['archive'] = str(tmp_path / 'run' / '..' / 'run')
    with pytest.raises(ValueError, match='non-traversing'):
        review(session, output_dir=str(tmp_path / 'report'))
    assert archive(tmp_path / 'run') == before


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows short-path aliases')
def test_report_rejects_windows_short_name_archive_overlap(tmp_path):
    import ctypes
    from pathlib import Path
    from firmavex.product.verification_session import review
    root = tmp_path / 'long archive directory name'
    session = verify(saved(root))
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    api.GetShortPathNameW.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    count = api.GetShortPathNameW(str(root), buffer, len(buffer))
    if not count or count >= len(buffer) or Path(buffer.value) == root:
        pytest.skip('Volume does not provide an alternate short path')
    before = archive(root)
    with pytest.raises(ValueError, match='outside original'):
        review(session, output_dir=str(Path(buffer.value) / 'report'))
    assert archive(root) == before
