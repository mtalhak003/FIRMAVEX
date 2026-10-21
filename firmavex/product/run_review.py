"""Bounded read-only saved-run review; never dispatch or repair a workload."""
from pathlib import Path
from datetime import datetime
import json

from firmavex.backends.api import profiles
from firmavex.backends.engine import inspect_run, STATUSES


def _path(value):
    if type(value) is not str or not value or len(value) > 4096 or any(not c.isprintable() for c in value):
        raise ValueError('Invalid saved-run path')
    return value


def _cancel(event):
    if event is not None and event.is_set():
        raise KeyboardInterrupt('Read-only review cancelled')


def fields(record):
    evidence = record.get('evidence', {})
    admission = evidence.get('admission', {})
    admission = admission if type(admission) is dict else {}
    profile = admission.get('profile', {})
    profile = profile.get('id') if type(profile) is dict else None
    status = record.get('status')
    mode = evidence.get('measurement_mode')
    started = admission.get('started_at_utc')
    try:
        if type(started) is not str or len(started) > 80 or datetime.fromisoformat(started).tzinfo is None:
            started = None
    except ValueError:
        started = None
    return {
        'backend': profile if type(profile) is str and profile in profiles else None,
        'status': status if type(status) is str and (status in STATUSES or status == 'incomplete') else None,
        'measurement': mode if type(mode) is str and mode in {'real_firmware', 'real_simulation', 'synthetic_test', 'unverified', 'unverified_runtime_observation'} else None,
        'cleanup_verified': evidence.get('cleanup_verified') if type(evidence.get('cleanup_verified')) is bool else None,
        'started_at_utc': started,
        'input_values': admission.get('values') if type(admission.get('values')) is list and len(admission['values']) <= 2 and all(type(v) is int and 0 <= v <= 0xFFFFFFFF for v in admission['values']) else None,
    }


def _review(path):
    try:
        record = inspect_run(path)
        values = fields(record)
        status = values['status']
        state = ('completed' if status in {'passed', 'triggered', 'not_discovered'} else
                 'incomplete' if status == 'incomplete' else
                 'cancelled' if status == 'cancelled' else 'failed' if status in STATUSES else 'unknown')
        return {'run_dir': path, 'inspection': 'validated', 'state': state, 'fields': values,
                'evidence_reference': str(Path(path) / ('admission.json' if status == 'incomplete' else 'result.json'))}
    except (OSError, ValueError, TypeError):
        # Missing, legacy and malformed records are not evidence of an outcome.
        return {'run_dir': path, 'inspection': 'unavailable', 'state': 'unknown',
                'fields': {}, 'evidence_reference': None}


def history(run_dirs, *, cancel_event=None):
    if type(run_dirs) is not list or len(run_dirs) > 50:
        raise ValueError('Select at most 50 saved runs for summary inspection')
    paths = [_path(value) for value in run_dirs]
    if sum(len(json.dumps(path)) for path in paths) > 65536:
        raise ValueError('Run paths exceed the review byte budget; select fewer runs')
    entries = []
    for path in paths:
        _cancel(cancel_event)
        entries.append(_review(path))
    _cancel(cancel_event)
    return {'entries': entries, 'read_only': True,
            'scope': 'Saved metadata inspection; not execution verification. Refresh to inspect changed files.'}


def compare(left, right, *, cancel_event=None):
    paths = [_path(left), _path(right)]
    entries = history(paths, cancel_event=cancel_event)['entries']
    rows = []
    for name in ('backend', 'status', 'measurement', 'cleanup_verified', 'started_at_utc', 'input_values'):
        a, b = (entry['fields'].get(name) for entry in entries)
        rows.append({'field': name, 'left': a, 'right': b,
                     'comparison': 'unavailable' if a is None or b is None else 'unchanged' if a == b else 'changed'})
    return {'left': entries[0], 'right': entries[1], 'rows': rows, 'read_only': True,
            'scope': 'Sequential saved metadata inspection only; no replay, artifact validation or atomic snapshot. Evidence references are not content hashes.'}
