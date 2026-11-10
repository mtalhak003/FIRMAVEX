"""Pure presentation helpers; file validation and execution remain in the worker."""
from pathlib import Path
import os
import re

from firmavex.backends.api import Limits, Request
from firmavex.backends.security import EXPORT_FILES


def confirmed_export(record, requested, *, backend=False):
    """Return a worker-confirmed requested destination, without filesystem I/O.

    This validates presentation fields, not file contents or execution evidence.
    The export service remains responsible for writing and hashing the files.
    """
    if type(record) is not dict or requested is None:
        return None
    if (record.get('status') != 'exported' if backend else record.get('success') is not True):
        return None
    destination = record.get('destination' if backend else 'output_directory')
    files = record.get('files')
    required = {'REPORT.md', 'result.json'} if backend else {'report.md', 'evidence.json'}
    if (type(destination) is not str or not destination or len(destination) > 4096
            or not destination.isprintable() or type(files) is not dict
            or not required <= files.keys() or not 2 <= len(files) <= EXPORT_FILES):
        return None
    for value in files.values():
        digest = value if backend else value.get('sha256') if type(value) is dict else None
        if type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None:
            return None
        if not backend and (type(value.get('size_bytes')) is not int or value['size_bytes'] < 0):
            return None
    try:
        selected, reported = Path(requested).absolute(), Path(destination)
        if not reported.is_absolute() or '..' in reported.parts:
            return None
        if os.path.normcase(os.path.normpath(str(selected))) != os.path.normcase(os.path.normpath(str(reported))):
            return None
    except (TypeError, ValueError, RuntimeError):
        return None
    return selected


def display_text(value, limit=500):
    text = str(value)
    visible = ''.join(c if c.isprintable() else ' ' for c in text[:limit])
    return visible + ('…' if len(text) > limit else '')


def input_vector(values):
    """One bounded decimal/hex RV32 input contract for execution and test sets."""
    message = 'Enter exactly two uint32 inputs (decimal or 0x hex), each from 0 to 4294967295.'
    if type(values) is not str or len(values) > 128:
        raise ValueError(message)
    tokens = values.replace(',', ' ').split()
    try:
        if len(tokens) != 2:
            raise ValueError()
        vector = tuple(int(token, 16 if token.lower().startswith('0x') else 10) for token in tokens)
        if any(not 0 <= value <= 0xFFFFFFFF for value in vector):
            raise ValueError()
    except ValueError:
        raise ValueError(message) from None
    return vector


def execution_request(profile, source, values, timeout, artifact_mib):
    source = source.strip()
    if not source or len(source) > 4096 or any(not c.isprintable() for c in source):
        raise ValueError('Choose a compatible input file with a valid path (up to 4096 characters).')
    vector = input_vector(values) if profile == 'riscv32-virt' else ()
    limits = Limits() if profile == 'cortex-m3-mps2' else Limits(
        timeout, artifact_bytes=artifact_mib * 1024 * 1024)
    try:
        path = Path(source).expanduser()
    except RuntimeError:
        raise ValueError('Cannot resolve this home directory. Choose an explicit input file path.') from None
    return Request(profile, path, vector, limits)


def result_context(record, run):
    evidence = record.get('evidence', {})
    evidence = evidence if type(evidence) is dict else {}
    admission = evidence.get('admission', {})
    admission = admission if type(admission) is dict else {}
    profile = admission.get('profile', {})
    profile = profile.get('id') if type(profile) is dict else None
    profile = profile or evidence.get('backend') or 'unknown backend'
    return f"Displayed result: {display_text(profile, 80)} · {display_text(record.get('status', 'unknown'), 80)}\nSaved run: {display_text(run, 1024)}"
