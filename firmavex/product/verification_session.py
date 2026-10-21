"""Session observations and bounded reports; metadata checks never reverify bytes."""
from datetime import datetime, timezone
import json
import sys
from pathlib import Path, PurePosixPath

from firmavex.backends.security import checked_path, fresh_directory
from .file_state import path_state
from .verification import check_cancel

LIMITATION = ('Saved hash observations only. Metadata checks do not rehash contents, '
              'prove authenticity or execution, or provide an atomic snapshot. '
              'Unchanged metadata is not proof of unchanged bytes.')


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, limit=600):
    if type(value) is not str:
        return 'unavailable'
    return ''.join(c if c.isprintable() else ' ' for c in value[:limit])


def relative(name):
    if (type(name) is not str or not name or len(name) > 4096 or '\\' in name
            or ':' in name or any(not c.isprintable() for c in name)
            or PurePosixPath(name).is_absolute() or any(p in {'', '.', '..'} for p in name.split('/'))):
        raise ValueError('Unsupported observation path')
    return name


def observe(root, names, *, cancel_event=None):
    """Bounded, metadata-only observation of validated archive-relative paths."""
    if len(names) > 260 or sum(len(n) if type(n) is str else 4097 for n in names) > 65536:
        return None
    observations = []
    for name in names:
        check_cancel(cancel_event)
        try:
            state = list(path_state(checked_path(root / relative(name))))
        except (OSError, ValueError):
            state = None
        observations.append({'name': name if type(name) is str and len(name) <= 4096 else '', 'state': state})
    return observations


def validate(session):
    if type(session) is not dict or len(json.dumps(session, ensure_ascii=True)) > 750000:
        raise ValueError('Invalid or oversized verification session')
    provenance = session.get('provenance')
    if type(provenance) is not dict or type(provenance.get('archive')) is not str:
        raise ValueError('Verification session has no archive provenance')
    source = provenance['archive']
    if not source or len(source) > 4096 or any(not c.isprintable() for c in source):
        raise ValueError('Invalid verification archive')
    rows = session.get('items')
    if type(rows) is not list or len(rows) > 256 or any(type(r) is not dict for r in rows):
        raise ValueError('Invalid verification rows')
    root = Path(source)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('Verification archive must have an absolute non-traversing path')
    return root


def freshness(session, *, cancel_event=None):
    root = validate(session)
    baseline = session.get('observations')
    status = 'unknown'
    if (session['provenance'].get('platform') == sys.platform and
            type(baseline) is list and 0 < len(baseline) <= 260):
        current = []
        for row in baseline:
            check_cancel(cancel_event)
            if type(row) is not dict or type(row.get('name')) is not str:
                break
            # Invalid/unavailable observations never become a freshness claim.
            observation = observe(root, [row['name']])
            current.append(observation[0] if observation else {'state': None})
        if len(current) == len(baseline):
            def valid(state):
                return type(state) is list and len(state) == 5 and all(type(v) is int for v in state)
            changed = any(valid(a.get('state')) and b.get('state') is not None and a['state'] != b['state']
                          for a, b in zip(baseline, current))
            status = 'stale' if changed else ('no_observed_metadata_changes' if all(
                valid(a.get('state')) and b.get('state') == a['state']
                for a, b in zip(baseline, current)) else 'unknown')
    return {'state': status, 'checked_at': now(), 'limitation': LIMITATION}


def review(session, *, output_dir=None, cancel_event=None):
    root = validate(session)
    check_cancel(cancel_event)
    result = {'freshness': freshness(session, cancel_event=cancel_event)}
    if output_dir is None:
        return result
    # Validate before resolving so symlinks remain forbidden. Resolve spelling
    # aliases (notably Windows short names) before testing archive overlap.
    root = checked_path(checked_path(root, directory=True, exists=False).resolve(), directory=True, exists=False)
    destination = checked_path(checked_path(output_dir, directory=True, exists=False).resolve(),
                               directory=True, exists=False)
    # Reject overlap in either direction before creating anything.
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError('Verification reports must be outside original evidence storage')
    provenance = session['provenance']
    lines = ['FIRMAVEX verification observations', LIMITATION,
             'Display-limited paths and values; not a complete archive inventory.']
    for key in ('started_at', 'finished_at', 'archive', 'scope', 'completion'):
        lines.append(key + ': ' + text(provenance.get(key)))
    lines.append('Partial results: ' + ('yes' if provenance.get('partial') is True else 'no or unavailable'))
    lines += ['status: ' + text(session.get('status'), 80),
              'diagnostic: ' + text(session.get('diagnostic')),
              'Freshness observation: ' + result['freshness']['state'],
              'Metadata checked at: ' + result['freshness']['checked_at'],
              'Per-artifact observations (display names may be truncated):']
    for index, row in enumerate(session['items'], 1):
        lines.append(str(index) + '. ' + text(row.get('name'), 160) + ' | ' + text(row.get('state'), 80))
    data = ('\n'.join(lines) + '\n').encode('utf-8', errors='replace')
    if len(data) > 262144:
        raise ValueError('Verification report exceeds export limit')
    check_cancel(cancel_event)
    destination = fresh_directory(destination)
    # Exclusive creation; never overwrite a file or a saved archive.
    with (destination / 'verification.txt').open('xb') as stream:
        stream.write(data)
    result['report'] = str(destination / 'verification.txt')
    return result
