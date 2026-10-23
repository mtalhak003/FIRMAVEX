"""Bounded regression dashboard, hash observations and portable text reports.

No workload dispatch. Summaries, identities and hash matches are recorded claims,
not execution authenticity. Verification never edits original evidence.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json

from firmavex.backends.security import (bounded_reads, checked_path, read_bytes,
                                       fresh_directory, EXPORT_BYTES)
from firmavex.backends.engine import inspect_run
from firmavex.backends.process import inspect_artifacts
from . import regression, verification, workspace
from .verification_session import now, report_destination
from .diagnosis import diagnosis, text
from .run_review import comparison_fields
from .provenance import recorded
from .verification import check_cancel

READ_BYTES = 256 * 1024 * 1024
ARTIFACTS = 256
REPORT_BYTES = 256 * 1024
SCOPE = ('Bounded sequential recorded-metadata and artifact-hash observations; not an atomic snapshot, '
         'authentic execution, hardware validation or complete reproducibility. Export contains no binary artifacts.')
STATES = ('verified', 'changed', 'missing', 'unavailable', 'unverified')


def dashboard(root, *, directory=None, cancel_event=None):
    """Metadata-only listing: bounded revision/session scans, never dispatch."""
    with bounded_reads(128 * 1024 * 1024, cancel_event=cancel_event):
        sets = regression.listing(root, cancel_event=cancel_event)
        sessions, configurations = [], []
        scanned = 0
        directories = [directory] if directory is not None else [entry['directory'] for entry in sets['entries']]
        for candidate_directory in directories:
            check_cancel(cancel_event)
            try:
                selected, manifest = regression._manifest(candidate_directory)
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                if directory is not None:
                    raise
                continue
            entries = manifest['entries']
            if type(entries) is not list or len(entries) > regression.MAX_ENTRIES:
                continue
            for entry in entries:
                if type(entry) is not dict or len(configurations) >= 64:
                    continue
                identity = entry.get('configuration_revision')
                try:
                    regression._identity(identity)
                    configurations.append({'entry_id': regression._identity(entry.get('id'), 32),
                        'name': text(entry.get('name'), 80), 'revision': identity, 'set_revision': selected.name,
                        'input_sha256': text(entry.get('input_sha256'), 64)})
                except ValueError:
                    continue
            runs = checked_path(selected / 'runs', directory=True, exists=False)
            if runs.exists():
                for candidate in runs.iterdir():
                    check_cancel(cancel_event)
                    if scanned >= 200:
                        break
                    scanned += 1
                    try:
                        result = regression.inspect(candidate, cancel_event=cancel_event)
                        if result['set_id'] != manifest['set_id'] or result['revision'] != selected.name:
                            continue
                        sessions.append({key: result[key] for key in ('directory', 'run_id', 'set_id',
                            'revision', 'name', 'created_at', 'state', 'counts')})
                    except (OSError, ValueError, TypeError, KeyError, RecursionError):
                        continue
            if scanned >= 200:
                break
        check_cancel(cancel_event)
        sessions.sort(key=lambda value: datetime.fromisoformat(value['created_at']), reverse=True)
        return {'sets': sets['entries'], 'configurations': configurations, 'sessions': sessions[:50],
                'session_candidates': scanned, 'session_limit': 50, 'candidate_limit': 200,
                'read_only': True, 'scope': 'Metadata only from at most 200 revision folders, 64 configuration pins and 200 session candidates. Open revalidates the selection. No execution or artifact verification.'}


def compare(left, right, *, cancel_event=None):
    with bounded_reads(2 * 1024 * 1024, cancel_event=cancel_event):
        return _compare(left, right, cancel_event=cancel_event)


def _compare(left, right, *, cancel_event=None):
    a, b = regression.inspect(left, cancel_event=cancel_event), regression.inspect(right, cancel_event=cancel_event)
    result = regression.compare_records(a, b)
    result['revision_comparison'] = ('not comparable' if a['set_id'] != b['set_id'] else
                                     'same' if a['revision'] == b['revision'] else 'changed')
    if a['set_id'] != b['set_id']:
        for row in result['rows']:
            row['comparison'] = 'not comparable'
    else:
        for row in result['rows']:
            row['comparison'] = 'missing' if row['left'] is None else 'changed' if row['comparison'] == 'different' else row['comparison']
    previous = {entry['id']: entry for entry in a['entries']}
    current = {entry['id']: entry for entry in b['entries']}
    for row in result['rows']:
        old, new = previous.get(row['id']), current.get(row['id'])
        if row['comparison'] == 'same' and old is not None and old['category'] != new['category']:
            row['comparison'] = 'changed'
        row['definition'] = ('not comparable' if a['set_id'] != b['set_id'] else 'missing' if old is None else
                             'same' if all(old[k] == new[k] for k in ('backend', 'configuration_revision', 'input_sha256', 'values')) else 'changed')
    for identity in result['removed']:
        result['rows'].append({'id': identity, 'left': previous[identity]['status'], 'right': None,
                              'comparison': 'missing' if a['set_id'] == b['set_id'] else 'not comparable',
                              'definition': 'missing' if a['set_id'] == b['set_id'] else 'not comparable'})
    result['left'] = {k: a[k] for k in ('run_id', 'set_id', 'revision', 'state', 'counts')}
    result['right'] = {k: b[k] for k in ('run_id', 'set_id', 'revision', 'state', 'counts')}
    result['scope'] = SCOPE
    return result



def _state(items):
    if not items:
        return 'unavailable'
    for state in ('changed', 'missing', 'unverified', 'unavailable'):
        if state in items:
            return state
    return 'verified'


def _association(summary, entry, record):
    admission = record['evidence']['admission']
    provenance = recorded(admission)
    if provenance is None:
        return 'unavailable'
    identity = record['evidence'].get('firmware' if entry['backend'] == 'riscv32-virt' else 'source')
    if type(identity) is not dict or type(identity.get('sha256')) is not str:
        return 'unavailable'
    expected = {'test_set_id': summary['set_id'], 'test_set_revision': summary['revision'],
                'regression_run_id': summary['run_id'], 'entry_id': entry['id'],
                'configuration_revision': entry['configuration_revision'], 'input_sha256': entry['input_sha256']}
    expected_category = regression.category(record['status'])
    allowed_categories = {expected_category}
    if record['evidence'].get('cleanup_verified') is not True:
        allowed_categories.add('infrastructure_error')
    if (identity['sha256'] != entry['input_sha256'] or entry['category'] not in allowed_categories
            or any(provenance.get(k) != v for k, v in expected.items())
            or admission['profile']['id'] != entry['backend'] or admission['values'] != entry['values']
            or record['status'] != entry['status']):
        return 'changed'
    return 'same'


def review(directory, *, verify_evidence=False, previous_run=None, cancel_event=None, event_callback=None):
    """Capture supported metadata; explicit verification retains partial results."""
    root = checked_path(directory, directory=True)
    callback = event_callback or (lambda event: None)
    with bounded_reads(READ_BYTES, cancel_event=cancel_event) as budget:
        summary = regression.inspect(root, cancel_event=cancel_event)
        snapshot = read_bytes(root / 'regression.json', regression.SUMMARY_BYTES, cancel_event=cancel_event)
        consistent = workspace._json(snapshot) == {k: v for k, v in summary.items() if k not in {'directory', 'read_only'}}
        rows = [{**entry, 'diagnostic': text(entry['diagnostic'], 4096), 'state': 'unverified' if entry['evidence'] else 'unavailable',
                 'association': 'unavailable', 'artifacts': [], 'metadata': None} for entry in summary['entries']]
        cancelled, limited, boundary_rejected, inventory_count = False, False, False, 0
        started = now()
        if verify_evidence:
            try:
                # Reuse the existing regular-file/link/count/aggregate-size boundary scan.
                inspect_artifacts(root, EXPORT_BYTES, cancel_event=cancel_event)
            except (KeyboardInterrupt, SystemExit):
                cancelled = True
            except (OSError, ValueError, RuntimeError):
                boundary_rejected = True
        for index, row in enumerate(rows):
            if cancelled or limited or boundary_rejected:
                break
            try:
                check_cancel(cancel_event)
                if not row['evidence']:
                    continue
                target = checked_path(root / row['evidence'], directory=True)
                record = inspect_run(target)
                row['association'] = _association(summary, row, record)
                metadata = comparison_fields(record)
                row['metadata'] = {k: v if len(json.dumps(v)) <= 2048 else None for k, v in metadata.items()}
                row['diagnostic'] = text(diagnosis(record), 4096)
                if verify_evidence:
                    def progress(event):
                        nonlocal inventory_count, limited
                        if event.get('phase') == 'inventory':
                            count = len(event.get('items', []))
                            if inventory_count + count > ARTIFACTS:
                                limited = True
                                raise ValueError('Aggregate artifact inventory limit exceeded')
                            inventory_count += count
                        callback({'type': 'regression_verification', 'entry_id': row['id'],
                                  'index': index, 'phase': event.get('phase'), 'completed_entries': index,
                                  'total_entries': len(rows)})
                    verified = verification.verify(str(target), cancel_event=cancel_event,
                                                     event_callback=progress, include_input=True)
                    mapping = {'hash_match': 'verified', 'hash_mismatch': 'changed', 'missing_artifact': 'missing',
                               'unavailable_metadata': 'unavailable'}
                    row['artifacts'] = [{'name': item['name'], 'state': mapping.get(item['state'], 'unverified'),
                                         'observation': item['state']} for item in verified['items']]
                    row['verification_status'] = verified['status']
                    row['state'] = _state([item['state'] for item in row['artifacts']])
                    if verified['status'] != 'verified' and row['state'] == 'verified':
                        row['state'] = 'unverified'
                    if row['association'] != 'same':
                        row['state'] = 'changed' if row['association'] == 'changed' else 'unverified'
                    # Check the record used for association/diagnosis too, without inferring an atomic snapshot.
                    if inspect_run(target) != record:
                        row['association'], row['state'] = 'changed', 'changed'
                    if verified['status'] == 'cancelled':
                        cancelled = True
            except FileNotFoundError:
                row['state'] = 'missing'
            except (KeyboardInterrupt, SystemExit):
                cancelled = True
            except (OSError, ValueError, RuntimeError, TypeError, KeyError, RecursionError):
                row['state'] = 'unverified'
            callback({'type': 'regression_verification', 'entry_id': row['id'], 'index': index,
                      'phase': row['state'], 'completed_entries': index + 1, 'total_entries': len(rows)})
        snapshot_state = 'unavailable'
        if not cancelled:
            try:
                snapshot_state = 'same' if read_bytes(root / 'regression.json', regression.SUMMARY_BYTES,
                                                     cancel_event=cancel_event) == snapshot else 'changed'
            except (OSError, ValueError, RuntimeError):
                snapshot_state = 'unavailable'
            except (KeyboardInterrupt, SystemExit):
                cancelled = True
        if not consistent:
            snapshot_state = 'changed'
        status = 'cancelled' if cancelled else _state([row['state'] for row in rows]) if verify_evidence else 'unverified'
        if verify_evidence and (limited or boundary_rejected or snapshot_state != 'same') and status == 'verified':
            status = 'unverified'
        comparison = None
        if previous_run and not cancelled:
            # Compare bounded snapshots in this existing read budget, without nesting it.
            try:
                comparison = _compare(previous_run, str(root), cancel_event=cancel_event)
            except (KeyboardInterrupt, SystemExit):
                cancelled, status = True, 'cancelled'
            except (OSError, ValueError, RuntimeError, TypeError, KeyError):
                comparison = {'rows': [], 'status': 'unavailable', 'scope': 'Previous comparison metadata unavailable; no outcome equivalence inferred.'}
        result = {'kind': 'firmavex_regression_review', 'schema_version': 1,
                'directory': str(root), 'summary': summary, 'entries': rows, 'status': status,
                'counts': {state: sum(row['state'] == state for row in rows) for state in STATES},
                'verification_requested': verify_evidence, 'summary_observation': snapshot_state,
                'summary_sha256': hashlib.sha256(snapshot).hexdigest(), 'started_at': started, 'finished_at': now(),
                'budget': {**budget, 'artifact_inventory': inventory_count}, 'limit_reached': limited, 'boundary_rejected': boundary_rejected,
                'comparison': comparison, 'read_only': True, 'scope': SCOPE}
        if len(workspace._encoded(result)) > 750000:
            raise ValueError('Regression review exceeds presentation limit')
        return result


def export(directory, output_dir, *, previous_run=None, cancel_event=None, event_callback=None):
    """Fresh verification and sanitized text only; never overwrite source evidence."""
    root = checked_path(directory, directory=True)
    protected = [root]
    if previous_run:
        protected.append(checked_path(previous_run, directory=True, exists=False))
    if root.parent.name == 'runs':
        protected.append(root.parent.parent)
        # Protect referenced configuration stores when the original manifest is available.
        try:
            _, manifest = regression._manifest(root.parent.parent)
            for entry in manifest['entries'][:regression.MAX_ENTRIES]:
                if type(entry) is dict and type(entry.get('configuration')) is str:
                    protected.append(Path(entry['configuration']))
        except (OSError, ValueError, TypeError, KeyError):
            pass
    destination = report_destination(output_dir, protected)
    result = review(root, verify_evidence=True, previous_run=previous_run,
                    cancel_event=cancel_event, event_callback=event_callback)
    check_cancel(cancel_event)
    summary = result['summary']
    lines = ['FIRMAVEX regression report', SCOPE, 'Exported at: ' + now(),
             'Source session reference: ' + text(str(root), 4096),
             'Metadata fields with null are unavailable or exceed display limits.']
    if previous_run:
        lines.append('Previous session reference: ' + text(str(previous_run), 4096))
    for key in ('name', 'set_id', 'revision', 'run_id', 'created_at', 'state', 'rerun_of'):
        lines.append(key + ': ' + text(summary.get(key), 200))
    lines += ['Recorded outcome counts: ' + json.dumps(summary['counts'], sort_keys=True),
              'Verification status: ' + result['status'], 'Verification entry counts: ' + json.dumps(result['counts'], sort_keys=True),
              'Summary observation: ' + result['summary_observation'], 'Verification started: ' + result['started_at'],
              'Verification finished: ' + result['finished_at']]
    for row in result['entries']:
        lines.append('\nEntry ' + row['id'] + ': ' + text(row['name'], 80))
        for key in ('configuration_revision', 'input_sha256', 'backend', 'status', 'category', 'evidence', 'state', 'association'):
            lines.append(key + ': ' + text(row.get(key), 200))
        lines.append('Metadata and provenance: ' + text(json.dumps(row['metadata'], ensure_ascii=False, sort_keys=True), 4096))
        lines.append('Failure diagnosis:\n' + text(row['diagnostic'], 4096))
        for artifact in row['artifacts']:
            lines.append('Artifact: ' + text(artifact['name'], 160) + ' | ' + artifact['state'])
    if result['comparison']:
        lines.append('\nComparison:\n' + text(json.dumps(result['comparison'], ensure_ascii=False, sort_keys=True), 16384))
    data = ('\n'.join(lines) + '\n').encode('utf-8')
    if len(data) > REPORT_BYTES:
        raise ValueError('Regression report exceeds byte limit')
    check_cancel(cancel_event)
    destination = fresh_directory(destination)
    try:
        workspace._write(destination / 'regression.txt', data, cancel_event)
    except BaseException:
        (destination / 'regression.txt').unlink(missing_ok=True)
        destination.rmdir()
        raise
    return {'report': str(destination / 'regression.txt'), 'verification_status': result['status'],
            'counts': result['counts'], 'read_only_source': True, 'scope': SCOPE}
