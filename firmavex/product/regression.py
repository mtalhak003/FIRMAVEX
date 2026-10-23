"""Explicit bounded test sets over immutable RV32/single-file HDL configurations.

Manifests and previous evidence are never rewritten. Only a newly owned run's
summary advances; backend admission, limits, trust and cleanup remain mandatory.
"""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import uuid

from firmavex.backends.security import checked_path, read_bytes, fresh_directory
from firmavex.backends.engine import _write
from . import workspace
from .verification import check_cancel
from .provenance import execution_context
from .diagnosis import diagnosis

MAX_ENTRIES = 16
MANIFEST_BYTES = 32768
TOTAL_INPUT_BYTES = 64 * 1024 * 1024
SUMMARY_BYTES = 128 * 1024
CATEGORIES = ('passed', 'failed', 'cancelled', 'infrastructure_error', 'not_run', 'unavailable')


def _name(value):
    if type(value) is not str or not 1 <= len(value.strip()) <= 80 or not value.isprintable():
        raise ValueError('Use a printable name of 1–80 characters')
    return value.strip()


def _identity(value, length=64):
    if type(value) is not str or len(value) != length or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid revision or entry identity')
    return value


def _timestamp(value):
    if type(value) is not str or len(value) > 80 or datetime.fromisoformat(value).tzinfo is None:
        raise ValueError('Invalid revision timestamp')
    return value


def _path(value):
    if type(value) is not str or not 1 <= len(value) <= 4096 or not value.isprintable():
        raise ValueError('Invalid configuration path')
    return checked_path(value, directory=True)


def _entries(entries, cancel_event=None, *, pinned=False, capture=False):
    if type(entries) is not list or not 1 <= len(entries) <= MAX_ENTRIES:
        raise ValueError('Select 1–16 explicit test entries')
    result, captured, identities, total = [], [], set(), 0
    required = {'id', 'name', 'configuration', 'values'}
    pins = {'configuration_revision', 'input_sha256'} if pinned else set()
    for entry in entries:
        check_cancel(cancel_event)
        if type(entry) is not dict or set(entry) != required | pins:
            raise ValueError('Invalid test entry fields')
        identity = _identity(entry['id'], 32)
        if identity in identities:
            raise ValueError('Duplicate test entry identity')
        identities.add(identity)
        directory, manifest, request = workspace._manifest(_path(entry['configuration']))
        if pinned and (entry['configuration_revision'] != directory.name or entry['input_sha256'] != manifest['input_sha256']):
            raise ValueError('Test entry configuration/input identity changed')
        values = entry['values']
        if type(values) is not list or len(values) > 2:
            raise ValueError('Test input values must be a list')
        _timestamp(manifest['saved_at'])
        request = replace(request, values=tuple(values))  # Reuse exact Request validation.
        # Bound aggregate capture before reading the next input.
        if (directory / 'input').stat().st_size > TOTAL_INPUT_BYTES - total:
            raise ValueError('Test set exceeds aggregate input limit')
        _, data, digest = workspace._capture(request, cancel_event, manifest['input_sha256'])
        total += len(data)
        if total > TOTAL_INPUT_BYTES:
            raise ValueError('Test set exceeds aggregate input limit')
        workspace._check(request, data)
        result.append({'id': identity, 'name': _name(entry['name']), 'configuration': str(directory),
                       'configuration_revision': directory.name, 'input_sha256': digest, 'values': values})
        if capture:
            captured.append((request, data, manifest['saved_at']))
    check_cancel(cancel_event)
    return result, captured


def _manifest(directory):
    directory = _path(str(directory))
    identity = _identity(directory.name)
    data = read_bytes(directory / 'testset.json', MANIFEST_BYTES)
    if hashlib.sha256(data).hexdigest() != identity:
        raise ValueError('Test-set revision changed')
    value = workspace._json(data)
    if (type(value) is not dict or set(value) != {'kind', 'schema_version', 'set_id', 'name', 'created_at', 'parent', 'entries'}
            or value['kind'] != 'firmavex_regression_set' or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise ValueError('Unsupported test-set manifest')
    _identity(value['set_id'], 32)
    _name(value['name']); _timestamp(value['created_at'])
    if value['parent'] is not None:
        _identity(value['parent'])
    return directory, value


def open_set(directory, *, cancel_event=None):
    directory, value = _manifest(directory)
    entries, _ = _entries(value['entries'], cancel_event, pinned=True)
    return {**value, 'entries': entries, 'directory': str(directory), 'revision': directory.name,
            'execution_performed': False}


def save(root, name, entries, *, parent=None, cancel_event=None):
    name = _name(name)
    previous = open_set(parent, cancel_event=cancel_event) if parent is not None else None
    entries, _ = _entries(entries, cancel_event)
    value = {'kind': 'firmavex_regression_set', 'schema_version': 1,
             'set_id': previous['set_id'] if previous else uuid.uuid4().hex,
             'name': name, 'created_at': datetime.now(timezone.utc).isoformat(),
             'parent': previous['revision'] if previous else None, 'entries': entries}
    data = workspace._encoded(value)
    if len(data) > MANIFEST_BYTES:
        raise ValueError('Test-set metadata exceeds byte limit')
    root = checked_path(root, directory=True, exists=False)
    check_cancel(cancel_event)
    root.mkdir(parents=True, exist_ok=True)
    directory = fresh_directory(root / hashlib.sha256(data).hexdigest())
    try:
        workspace._write(directory / 'testset.json', data, cancel_event)
    except BaseException:
        (directory / 'testset.json').unlink(missing_ok=True)
        directory.rmdir()
        raise
    return {**value, 'directory': str(directory), 'revision': directory.name, 'execution_performed': False}


def listing(root, *, cancel_event=None):
    root = checked_path(root, directory=True, exists=False)
    entries = []
    if root.exists():
        for index, path in enumerate(root.iterdir()):
            check_cancel(cancel_event)
            if index >= 200:
                break
            try:
                directory, value = _manifest(path)
                entries.append({'directory': str(directory), 'name': value['name'],
                                'revision': directory.name, 'created_at': value['created_at']})
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                continue
    check_cancel(cancel_event)
    return {'entries': entries, 'limit': 200, 'execution_performed': False}


def category(status):
    return {'passed': 'passed', 'triggered': 'failed', 'cancelled': 'cancelled',
            'invalid_input': 'infrastructure_error', 'invalid_output': 'infrastructure_error',
            'infrastructure_failure': 'infrastructure_error'}.get(status, 'infrastructure_error')


def _counts(entries):
    return {name: sum(entry['category'] == name for entry in entries) for name in CATEGORIES}


def _publish(root, result):
    result['counts'] = _counts(result['entries'])
    if len(workspace._encoded(result)) > SUMMARY_BYTES:
        raise ValueError('Regression summary exceeds byte limit')
    _write(root / 'regression.json', result)


def inspect(directory, *, cancel_event=None):
    """Validate summary structure; references alone do not verify backend evidence."""
    root = _path(str(directory))
    result = workspace._json(read_bytes(root / 'regression.json', SUMMARY_BYTES, cancel_event=cancel_event))
    fields = {'kind', 'schema_version', 'run_id', 'set_id', 'revision', 'name', 'created_at', 'state',
              'rerun_of', 'entries', 'counts', 'scope'}
    if (type(result) is not dict or set(result) != fields or result['kind'] != 'firmavex_regression_run'
            or type(result['schema_version']) is not int or result['schema_version'] != 1
            or result['state'] not in ('running', 'completed', 'cancelled', 'stopped')):
        raise ValueError('Unsupported regression result')
    _identity(result['run_id'], 32); _identity(result['set_id'], 32); _identity(result['revision'])
    _name(result['name']); _timestamp(result['created_at'])
    if result['rerun_of'] is not None:
        _identity(result['rerun_of'], 32)
    entries = result['entries']
    if type(entries) is not list or not 1 <= len(entries) <= MAX_ENTRIES:
        raise ValueError('Invalid regression result entries')
    ids = set()
    for entry in entries:
        check_cancel(cancel_event)
        if (type(entry) is not dict or set(entry) != {'id', 'name', 'configuration_revision', 'input_sha256', 'values',
                'backend', 'status', 'category', 'evidence', 'diagnostic'}):
            raise ValueError('Invalid regression result entry')
        _identity(entry['id'], 32); _identity(entry['configuration_revision']); _identity(entry['input_sha256'])
        _name(entry['name'])
        if entry['id'] in ids or entry['backend'] not in ('riscv32-virt', 'verilog-icarus'):
            raise ValueError('Invalid regression entry identity/backend')
        ids.add(entry['id'])
        values = entry['values']
        if (type(values) is not list or len(values) != (2 if entry['backend'] == 'riscv32-virt' else 0)
                or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in values)):
            raise ValueError('Invalid regression entry values')
        if (type(entry['category']) is not str or entry['category'] not in CATEGORIES
                or type(entry['status']) is not str or len(entry['status']) > 80
                or type(entry['diagnostic']) is not str or len(entry['diagnostic']) > 4096):
            raise ValueError('Invalid regression entry outcome')
        statuses = {'passed', 'triggered', 'cancelled', 'invalid_input', 'invalid_output', 'infrastructure_failure', 'running', 'not_run'}
        if entry['status'] not in statuses:
            raise ValueError('Unsupported regression entry outcome')
        if entry['status'] in {'not_run', 'running'} and entry['category'] != ('not_run' if entry['status'] == 'not_run' else 'unavailable'):
            raise ValueError('Contradictory partial regression outcome')
        if entry['evidence'] is not None and entry['evidence'] != 'entries/' + entry['id']:
            raise ValueError('Invalid evidence reference')
    counts = result['counts']
    if type(counts) is not dict or set(counts) != set(CATEGORIES) or any(type(v) is not int or not 0 <= v <= MAX_ENTRIES for v in counts.values()):
        raise ValueError('Invalid regression counts')
    if result['counts'] != _counts(entries) or type(result['scope']) is not str or len(result['scope']) > 500:
        raise ValueError('Invalid regression summary counts/scope')
    return {**result, 'directory': str(root), 'read_only': True}


def compare(left, right, *, cancel_event=None):
    a, b = inspect(left, cancel_event=cancel_event), inspect(right, cancel_event=cancel_event)
    old = {e['id']: e for e in a['entries']}
    rows = []
    for entry in b['entries']:
        previous = old.get(entry['id'])
        state = 'unavailable' if previous is None else 'not comparable'
        if a['set_id'] == b['set_id'] and previous is not None:
            keys = ('configuration_revision', 'input_sha256', 'values', 'backend')
            if all(previous[k] == entry[k] for k in keys):
                state = ('unavailable' if any(c in ('not_run', 'unavailable') for c in (previous['category'], entry['category'])) else
                         'same' if previous['status'] == entry['status'] else 'different')
        rows.append({'id': entry['id'], 'comparison': state, 'left': previous['status'] if previous else None,
                     'right': entry['status']})
    return {'rows': rows, 'read_only': True, 'scope': 'Recorded outcomes matched by set/entry/configuration/input identities. Hashes are not execution authenticity; removed entries are listed separately.',
            'removed': [entry['id'] for entry in a['entries'] if entry['id'] not in {e['id'] for e in b['entries']}]}


def execute(directory, output_dir, *, trust, previous_run=None, cancel_event=None, event_callback=None):
    if type(trust) is not str or trust != 'trusted_project':
        raise ValueError('Explicit trust in all selected inputs and runtime tools is required')
    directory, value = _manifest(directory)
    # Freeze and preflight every input before admitting the first execution.
    entries, captured = _entries(value['entries'], cancel_event, pinned=True, capture=True)
    previous = inspect(previous_run, cancel_event=cancel_event) if previous_run else None
    if previous is not None and previous['set_id'] != value['set_id']:
        raise ValueError('Rerun parent belongs to a different test set')
    root = checked_path(output_dir, directory=True, exists=False)
    if root.parent != directory / 'runs':
        raise ValueError('Test-set runs must use the selected revision runs folder')
    check_cancel(cancel_event)
    root = fresh_directory(root)
    result = {'kind': 'firmavex_regression_run', 'schema_version': 1, 'run_id': uuid.uuid4().hex,
              'set_id': value['set_id'], 'revision': directory.name, 'name': value['name'],
              'created_at': datetime.now(timezone.utc).isoformat(), 'state': 'running',
              'rerun_of': previous['run_id'] if previous else None,
              'entries': [{**{k: entry[k] for k in ('id', 'name', 'configuration_revision', 'input_sha256', 'values')},
                           'backend': request.profile, 'status': 'not_run', 'category': 'not_run',
                           'evidence': None, 'diagnostic': ''} for entry, (request, _, _) in zip(entries, captured)],
              'scope': 'Sequential explicit software executions; retained summaries and hashes do not prove authentic execution or hardware validation.'}
    _publish(root, result)
    callback = event_callback or (lambda event: None)
    try:
        for row, (request, data, created_at) in zip(result['entries'], captured):
            if cancel_event is not None and cancel_event.is_set():
                result['state'] = 'cancelled'
                break
            target = root / 'entries' / row['id']
            row['status'] = 'running'
            row['category'] = 'unavailable'
            row['evidence'] = 'entries/' + row['id']
            _publish(root, result)
            callback({'type': 'regression_entry', 'entry_id': row['id'], 'stage': 'starting'})
            fields = dict(configuration_revision=row['configuration_revision'], configuration_created_at=created_at,
                          input_sha256=row['input_sha256'], test_set_id=value['set_id'], test_set_revision=directory.name,
                          entry_id=row['id'], regression_run_id=result['run_id'])
            if previous:
                fields['rerun_of'] = previous['run_id']
            try:
                with execution_context(**fields):
                    record = workspace.execute_captured(request, target, data, trust=trust,
                                 cancel_event=cancel_event, event_callback=callback)
                row['status'] = record['status']
                row['category'] = category(record['status'])
                row['diagnostic'] = diagnosis(record)[:1024]
                if record.get('evidence', {}).get('cleanup_verified') is not True:
                    row['category'] = 'infrastructure_error'
                    row['diagnostic'] = 'Cleanup was not verified; no further entries dispatched. ' + row['diagnostic'][:950]
            except (KeyboardInterrupt, SystemExit):
                row.update(status='cancelled', category='cancelled', diagnostic='Execution interrupted; inspect retained partial evidence.')
            except Exception:
                # Never turn an exception into a firmware verdict or retry it.
                row.update(status='infrastructure_failure', category='infrastructure_error',
                           diagnostic='Entry could not complete; inspect retained evidence and runtime admission.')
            if row['category'] == 'cancelled' or (cancel_event is not None and cancel_event.is_set()):
                result['state'] = 'cancelled'
            elif row['category'] == 'infrastructure_error':
                # Cleanup/admission may be uncertain: do not dispatch another target.
                result['state'] = 'stopped'
            _publish(root, result)
            callback({'type': 'regression_entry', 'entry_id': row['id'], 'stage': 'finished', 'category': row['category']})
            if result['state'] != 'running':
                break
        if result['state'] == 'running':
            result['state'] = 'completed'
    except (KeyboardInterrupt, SystemExit):
        result['state'] = 'cancelled'
        raise
    except Exception:
        result['state'] = 'stopped'
        raise
    finally:
        _publish(root, result)
    return {**result, 'directory': str(root)}


def operation(payload, *, cancel_event=None, event_callback=None):
    action = payload.get('action')
    fields = {'list': ({'action', 'root'}, set()), 'save': ({'action', 'root', 'name', 'entries'}, {'parent'}),
              'open': ({'action', 'directory'}, set()), 'inspect': ({'action', 'directory'}, set()),
              'compare': ({'action', 'left', 'right'}, set()),
              'execute': ({'action', 'directory', 'output_dir', 'trust'}, {'previous_run'})}
    if type(action) is not str or action not in fields:
        raise ValueError('Invalid regression operation')
    required, optional = fields[action]
    if not required <= payload.keys() or not payload.keys() <= required | optional:
        raise ValueError('Invalid regression operation fields')
    args = {k: v for k, v in payload.items() if k != 'action'}
    if action == 'execute':
        return execute(**args, cancel_event=cancel_event, event_callback=event_callback)
    return {'list': listing, 'save': save, 'open': open_set, 'inspect': inspect, 'compare': compare}[action](**args, cancel_event=cancel_event)
