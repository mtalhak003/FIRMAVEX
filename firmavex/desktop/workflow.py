"""Pure presentation helpers; file validation and execution remain in the worker."""
from pathlib import Path

from firmavex.backends.api import Limits, Request


def display_text(value, limit=500):
    text = str(value)
    visible = ''.join(c if c.isprintable() else ' ' for c in text[:limit])
    return visible + ('…' if len(text) > limit else '')


def execution_request(profile, source, values, timeout, artifact_mib):
    source = source.strip()
    if not source or len(source) > 4096 or any(not c.isprintable() for c in source):
        raise ValueError('Choose a compatible input file with a valid path (up to 4096 characters).')
    vector = ()
    if profile == 'riscv32-virt':
        if len(values) > 128:
            raise ValueError('Enter exactly two uint32 inputs, each from 0 to 4294967295.')
        tokens = values.replace(',', ' ').split()
        try:
            if len(tokens) != 2:
                raise ValueError()
            vector = tuple(int(t, 16 if t.lower().startswith('0x') else 10) for t in tokens)
            if any(not 0 <= v <= 0xFFFFFFFF for v in vector):
                raise ValueError()
        except ValueError:
            raise ValueError('Enter exactly two uint32 inputs (decimal or 0x hex), each from 0 to 4294967295.') from None
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
