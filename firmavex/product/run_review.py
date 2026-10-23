"""Bounded read-only saved-run review; never dispatch or repair a workload."""
from pathlib import Path
from datetime import datetime
import json
import math

from firmavex.backends.api import profiles
from firmavex.backends.engine import inspect_run, STATUSES
from firmavex.backends.security import checked_path, EXPORT_BYTES
from firmavex.product.errors import ProductError


def _path(value):
    if type(value) is not str or not value or len(value) > 4096 or any(not c.isprintable() for c in value):
        raise ValueError('Invalid saved-run path')
    return value


def _cancel(event):
    if event is not None and event.is_set():
        raise KeyboardInterrupt('Read-only review cancelled')


def _metadata(value):
    """Only small complete JSON values participate in identity comparisons."""
    if type(value) in (dict, list, str) and not value:
        return None
    pending = [(value, 0)]
    nodes, size = 0, 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 5 or nodes > 128:
            return None
        if type(item) is str:
            size += len(item)
            if len(item) > 4096 or size > 16384:
                return None
        elif item is None or type(item) in (bool, int) or (type(item) is float and math.isfinite(item)):
            pass
        elif type(item) in (dict, list) and len(item) <= 32:
            if type(item) is dict:
                if any(type(k) is not str or len(k) > 100 for k in item):
                    return None
                size += sum(len(k) for k in item)
            children = item.values() if type(item) is dict else item
            pending.extend((child, depth + 1) for child in children)
        else:
            return None
        if size > 16384:
            return None
    return value


def comparison_fields(record):
    from .diagnosis import classification
    evidence = record.get('evidence', {})
    admission = evidence.get('admission', {})
    admission = admission if type(admission) is dict else {}
    legacy = evidence.get('legacy_result', {})
    legacy = legacy if type(legacy) is dict else {}
    result = {
        'project_configuration': admission.get('configuration'),
        'declared_source_path': admission.get('source'),
        'input_identity': evidence.get('firmware', evidence.get('source')),
        'execution_environment': admission.get('profile'),
        'execution_limits': admission.get('limits'),
        'tool_runtime_identity': evidence.get('tools'),
        'replay_metadata': legacy.get('reproduction', admission.get('reproduction_of')),
        'failure_classification': classification(record.get('status', legacy.get('outcome'))),
    }
    if result['failure_classification'] == 'unavailable':
        result['failure_classification'] = None
    if result['input_identity'] is None:
        result['input_identity'] = legacy.get('firmware_sha256')
    identity = result['input_identity']
    if type(identity) is dict:
        result['input_identity'] = identity.get('sha256', identity.get('firmware_sha256'))
    identity = result['input_identity']
    if type(identity) is not str or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
        result['input_identity'] = None
    return {key: _metadata(value) for key, value in result.items()}


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
        **comparison_fields(record),
        'backend': profile if type(profile) is str and profile in profiles else None,
        'status': status if type(status) is str and (status in STATUSES or status == 'incomplete') else None,
        'measurement': mode if type(mode) is str and mode in {'real_firmware', 'real_simulation', 'synthetic_test', 'unverified', 'unverified_runtime_observation'} else None,
        'cleanup_verified': evidence.get('cleanup_verified') if type(evidence.get('cleanup_verified')) is bool else None,
        'started_at_utc': started,
        'input_values': admission.get('values') if type(admission.get('values')) is list and len(admission['values']) <= 2 and all(type(v) is int and 0 <= v <= 0xFFFFFFFF for v in admission['values']) else None,
    }


def outcome_category(entry):
    """Recorded classifications only; absence is never a passing outcome."""
    data = entry.get('fields')
    status = data.get('status') if type(data) is dict else None
    if entry.get('inspection') != 'validated' or type(status) is not str or status == 'incomplete':
        return 'unknown'
    if status in {'triggered', 'configured_failure_observed', 'reproduced_in_emulator'}:
        return 'observed_failure'
    if status in {'passed', 'not_discovered', 'no_failure_within_budget', 'domain_exhausted'}:
        return 'no_failure'
    if status == 'cancelled':
        return 'cancelled'
    return 'failed' if status in {'invalid_input', 'invalid_output', 'infrastructure_failure', 'reproduction_inconsistent'} else 'unknown'


def _integrity(state, scope, count=0):
    return {'state': state, 'scope': scope, 'artifacts_checked': count}


def _legacy(path, *, cancel_event=None):
    from firmavex.backends.process import inspect_artifacts
    from firmavex.product.services import inspect_run as inspect_arm
    from firmavex.product.config import ProductConfig
    # Reuse the existing ARM export preflight before its hash/SQLite inspector.
    inspect_artifacts(path, EXPORT_BYTES, cancel_event=cancel_event)
    inspected = inspect_arm(path, cancel_event=cancel_event) if cancel_event is not None else inspect_arm(path)
    metadata = inspected['metadata']
    ProductConfig.from_dict(metadata['configuration'])
    result = inspected['result']
    supported = type(result) is dict and result.get('kind') == 'firmavex_product_result'
    outcome = result.get('outcome') if supported else None
    known = {'configured_failure_observed', 'no_failure_within_budget', 'domain_exhausted',
             'reproduced_in_emulator', 'reproduction_inconsistent', 'infrastructure_failure', 'invalid_output', 'cancelled'}
    values = {key: None for key in fields({'evidence': {}})}
    values['backend'] = 'cortex-m3-mps2'
    values['status'] = outcome if type(outcome) is str and outcome in known else 'incomplete' if result is None else None
    if supported and result.get('measurement_mode') in {'real_firmware', 'synthetic_test'}:
        values['measurement'] = result['measurement_mode']
    # Do not infer cleanup from an overall outcome or evidence-completeness flag.
    values.update(comparison_fields({'status': outcome, 'evidence': {
        'admission': {'configuration': metadata.get('configuration')},
        'firmware': metadata.get('firmware'), 'tools': metadata.get('tools'),
        'legacy_result': result}}))
    artifacts = inspected['artifact_verification']
    integrity = (_integrity('verified', 'Registered ARM artifact SHA-256/size checks passed; not authenticity or execution verification.', len(artifacts))
                 if artifacts else _integrity('unavailable', 'No registered artifacts were available for hash verification.'))
    return {'run_dir': path, 'archive_format': 'standalone_arm', 'inspection': 'validated',
            'state': inspected['state'], 'fields': values, 'integrity': integrity,
            'evidence_reference': str(Path(path) / 'run.sqlite3')}


def _review(path, *, cancel_event=None):
    legacy = False
    try:
        root = checked_path(path, directory=True)
        legacy = (root / 'run.sqlite3').exists() or (root / 'run.sqlite3').is_symlink()
        if legacy:
            if (root / 'admission.json').exists() or (root / 'admission.json').is_symlink():
                raise ValueError('Ambiguous archive format')
            return _legacy(path, cancel_event=cancel_event)
        record = inspect_run(path)
        values = fields(record)
        status = values['status']
        state = ('completed' if status in {'passed', 'triggered', 'not_discovered'} else
                 'incomplete' if status == 'incomplete' else
                 'cancelled' if status == 'cancelled' else 'failed' if status in STATUSES else 'unknown')
        integrity = _integrity('unavailable', 'No listed artifacts were hash-checked; record inspection is not artifact verification.')
        if record['evidence'].get('artifacts'):
            from firmavex.backends.report import _saved_artifacts
            try:
                artifacts = _saved_artifacts(root, record, cancel_event=cancel_event) if cancel_event is not None else _saved_artifacts(root, record)
                if inspect_run(path) != record:
                    raise ValueError('Record changed during verification')
                integrity = _integrity('verified', 'Listed backend artifact SHA-256/size checks passed; not authenticity, ARM receipt or execution verification.', len(artifacts))
            except (OSError, ValueError, RuntimeError):
                integrity = _integrity('unverified', 'Listed artifact verification failed or was rejected by existing limits.')
        return {'run_dir': path, 'archive_format': 'shared_backend', 'integrity': integrity,
                'inspection': 'validated', 'state': state, 'fields': values,
                'evidence_reference': str(Path(path) / ('admission.json' if status == 'incomplete' else 'result.json'))}
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ProductError):
        # Missing, legacy and malformed records are not evidence of an outcome.
        return {'run_dir': path, 'inspection': 'unavailable', 'state': 'unknown',
                'fields': {}, 'evidence_reference': None,
                'integrity': _integrity('unverified' if legacy else 'unavailable',
                                        'ARM archive verification failed or format unsupported.' if legacy else 'No integrity checks completed.')}


def history(run_dirs, *, cancel_event=None):
    if type(run_dirs) is not list or len(run_dirs) > 50:
        raise ValueError('Select at most 50 saved runs for summary inspection')
    paths = [_path(value) for value in run_dirs]
    if sum(len(json.dumps(path)) for path in paths) > 65536:
        raise ValueError('Run paths exceed the review byte budget; select fewer runs')
    entries = []
    for path in paths:
        _cancel(cancel_event)
        entries.append(_review(path, cancel_event=cancel_event))
    _cancel(cancel_event)
    return {'entries': entries, 'read_only': True,
            'scope': 'Saved metadata inspection with explicitly scoped artifact checks; not execution verification. Refresh to inspect changed files.'}


def compare(left, right, *, cancel_event=None):
    paths = [_path(left), _path(right)]
    entries = history(paths, cancel_event=cancel_event)['entries']
    rows = []
    backend_specific = {'input_identity', 'execution_environment', 'execution_limits',
                        'replay_metadata', 'project_configuration', 'input_values'}
    same_backend = entries[0]['fields'].get('backend') == entries[1]['fields'].get('backend')
    for name in sorted(fields({'evidence': {}})):
        a, b = (entry['fields'].get(name) for entry in entries)
        if a is None or b is None:
            state = 'unavailable'
        elif name in backend_specific and not same_backend:
            state = 'not comparable'
        else:
            state = 'same' if a == b else 'different'
        rows.append({'field': name, 'left': a, 'right': b, 'comparison': state})
    from .diagnosis import replay_explanation
    return {'replay_explanations': [replay_explanation(entry['fields'].get('backend')) for entry in entries], 'left': entries[0], 'right': entries[1], 'rows': rows, 'read_only': True,
            'scope': 'Sequential read-only review; no replay or atomic snapshot. Integrity states apply only to the named checks, not authenticity or execution validity. Evidence references alone prove no integrity.'}
