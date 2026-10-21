"""Explicit, bounded artifact checks with partial results; never execute evidence."""
import hashlib
import threading
import sys


def check_cancel(event):
    if event is not None and event.is_set():
        raise KeyboardInterrupt('Evidence verification cancelled')


def digest(data, cancel_event=None):
    if cancel_event is None:
        return hashlib.sha256(data).hexdigest()
    result = hashlib.sha256()
    for offset in range(0, len(data), 1024 * 1024):
        check_cancel(cancel_event)
        result.update(memoryview(data)[offset:offset + 1024 * 1024])
    check_cancel(cancel_event)
    return result.hexdigest()


def verify(run_dir, *, cancel_event=None, event_callback=None):
    from firmavex.backends.security import checked_path, EXPORT_BYTES, EXPORT_FILES
    from firmavex.backends.engine import inspect_run
    from firmavex.product.errors import ProductError
    from .run_review import _path

    cancel = cancel_event if cancel_event is not None else threading.Event()
    callback = event_callback or (lambda event: None)
    from .verification_session import now, observe
    started = now()
    root = None
    observations = None
    scope = 'Unavailable archive scope'
    rows = []
    active = None

    def report(phase, **data):
        nonlocal active, rows, observations
        if phase == 'inventory':
            names = data['names']
            if len(names) > EXPORT_FILES:
                raise ValueError('Verification inventory exceeds desktop limits')
            metadata = ['run.sqlite3', 'result.json'] if scope == 'Registered ARM artifacts' else ['admission.json', 'result.json']
            observations = observe(root, metadata + names, cancel_event=cancel)
            rows = [{'name': ''.join(c if c.isprintable() else ' ' for c in (name[:160] if type(name) is str else '[invalid metadata]')),
                     'state': 'pending'} for name in names]
        elif phase == 'artifact':
            active = data['index']
            rows[active]['state'] = data['state']
        event = {'type': 'verification_progress', 'phase': phase,
                 'completed': sum(row['state'] not in {'pending', 'checking'} for row in rows),
                 'total': len(rows) if rows else None}
        if phase == 'inventory':
            event['items'] = [dict(row) for row in rows]
        elif phase == 'artifact':
            event.update(index=active, item=dict(rows[active]))
        callback(event)

    status, diagnostic = 'unavailable', 'No supported artifact inventory was verified.'
    try:
        report('inspecting_archive')
        check_cancel(cancel)
        root = checked_path(_path(run_dir), directory=True)
        if (root / 'run.sqlite3').exists() or (root / 'run.sqlite3').is_symlink():
            scope = 'Registered ARM artifacts'
            from firmavex.backends.process import inspect_artifacts
            from .store import RunStore
            if (root / 'admission.json').exists() or (root / 'admission.json').is_symlink():
                raise ValueError('Ambiguous archive format')
            report('checking_archive_boundaries')
            inspect_artifacts(root, EXPORT_BYTES, cancel_event=cancel)
            with RunStore(root) as store:
                report('reading_manifest')
                before = store.snapshot()
                store.verify_artifacts(cancel_event=cancel, event_callback=report)
                check_cancel(cancel)
                report('checking_archive_record')
                if store.snapshot() != before:
                    raise ValueError('Archive metadata changed during verification')
            diagnostic = 'Registered ARM artifact hashes and inventory checked; not receipt/accounting, authenticity or execution verification.'
        else:
            scope = 'Listed backend artifacts'
            from firmavex.backends.report import _saved_artifacts
            before = inspect_run(root)
            _saved_artifacts(root, before, cancel_event=cancel, event_callback=report)
            check_cancel(cancel)
            report('checking_archive_record')
            if inspect_run(root) != before:
                raise ValueError('Record changed during verification')
            diagnostic = 'Listed backend artifact hashes checked; not nested ARM receipts, authenticity or execution verification.'
        check_cancel(cancel)
        status = 'verified' if rows and all(row['state'] == 'hash_match' for row in rows) else 'unavailable'
        if not rows:
            diagnostic = 'No registered/listed artifact inventory was available for hash checking. No integrity claim.'
    except (KeyboardInterrupt, SystemExit):
        status, diagnostic = 'cancelled', 'Verification cancelled. Completed hash checks retained; unchecked work is not verified.'
        if active is not None and rows[active]['state'] == 'checking':
            rows[active]['state'] = 'cancelled'
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, ProductError) as error:
        status, diagnostic = 'failed', 'Verification failed or was rejected by existing archive/file limits. No overall integrity claim.'
        if active is not None and rows[active]['state'] == 'checking':
            rows[active]['state'] = 'missing_artifact' if isinstance(error, FileNotFoundError) else 'read_error'
    for row in rows:
        if row['state'] == 'pending':
            row['state'] = 'not_checked'
    result = {'status': status, 'success': status == 'verified', 'read_only': True,
              'items': rows, 'completed': sum(row['state'] not in {'pending', 'checking', 'cancelled', 'not_checked'} for row in rows),
              'matched': sum(row['state'] == 'hash_match' for row in rows),
              'total': len(rows) if rows else None, 'diagnostic': diagnostic}
    result['provenance'] = {'started_at': started, 'finished_at': now(),
                            'archive': str(root) if root is not None else str(run_dir)[:4096],
                            'scope': scope, 'platform': sys.platform, 'completion': ('completed' if status in {'verified', 'unavailable'} else status),
                            'partial': any(row['state'] == 'hash_match' for row in rows) and status != 'verified'}
    result['observations'] = observations
    result['freshness'] = {'state': 'unknown', 'limitation': 'Saved observations; use Check for changes for a metadata-only observation.'}
    callback({'type': 'verification_progress', 'phase': status, **result})
    return result
