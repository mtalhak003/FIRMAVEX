"""Offline collected-file inventory. Attribution hints never establish legal clearance.

Inspects regular files and internal links without executing binaries. Embedded
PyInstaller archives and installer payloads require separate extraction/audit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from .release import _identity
from .release_bundle import canonical

MAX_FILES = 50000
MAX_TOTAL = 8 * 1024**3


def _entries(root):
    entries = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if Path(target).is_absolute() or not path.resolve(strict=True).is_relative_to(root):
                    raise ValueError('External or broken application link: ' + relative)
                entries[relative] = ('link', target)
            elif stat.S_ISREG(info.st_mode):
                entries[relative] = ('file',)
            elif not stat.S_ISDIR(info.st_mode):
                raise ValueError('Unsupported application entry: ' + relative)
            if len(entries) > MAX_FILES:
                raise ValueError('Application inventory file limit exceeded')
    return dict(sorted(entries.items()))


def _classification(path):
    with path.open('rb') as stream:
        magic = stream.read(8)
    if magic.startswith(b'\x7fELF'): return 'ELF'
    if magic.startswith(b'MZ'): return 'PE_candidate'
    if magic[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe'): return 'MachO_candidate'
    if path.suffix.lower() in ('.zip', '.pyz'): return 'embedded_archive_unexpanded'
    return 'data_or_unrecognized'


def _hint(name):
    """Path-based hints explicitly remain unverified, never ownership assertions."""
    lower = name.lower()
    for tokens, component in ((('pyside6', 'shiboken6', 'qt6', 'libqt6'), 'Qt/PySide6'),
                              (('libpython', 'python3', 'python.dll', 'base_library.zip'), 'CPython'),
                              (('firmavex',), 'FIRMAVEX/PyInstaller composite')):
        if any(token in lower for token in tokens): return component
    return None


def capture(directory, installers=()):
    supplied = Path(directory)
    if supplied.is_symlink() or not supplied.is_dir():
        raise ValueError('Select a real application directory')
    root = supplied.resolve(strict=True)
    before = _entries(root)
    records, total = [], 0
    for name, entry in before.items():
        path = root / name
        if entry[0] == 'link':
            record = {'path': name, 'type': 'symlink', 'target': entry[1]}
        else:
            identity = _identity(path)
            total += identity['size_bytes']
            if total > MAX_TOTAL: raise ValueError('Application inventory total limit exceeded')
            record = {'path': name, 'type': 'file', **identity,
                      'format': _classification(path), 'component_hint': _hint(name),
                      'ownership': 'unverified', 'license_concluded': 'NOASSERTION',
                      'corresponding_source': 'not_verified'}
        records.append(record)
    # Verify all bytes and link identities again, including directory membership.
    if _entries(root) != before:
        raise ValueError('Application entries changed during inventory')
    for record in records:
        if record['type'] == 'file' and _identity(root / record['path']) != {
                k: record[k] for k in ('sha256', 'size_bytes')}:
            raise ValueError('Application file changed during inventory')
    if _entries(root) != before:
        raise ValueError('Application entries changed during inventory')
    artifacts = {}
    for artifact in installers:
        name = Path(artifact).name
        if name.casefold() in {key.casefold() for key in artifacts}:
            raise ValueError('Duplicate installer name')
        artifacts[name] = {**_identity(artifact), 'payload_inventory': 'not_extracted_not_verified'}
    return {'schema_version': 1, 'kind': 'firmavex_collected_file_inventory',
            'files': records, 'installers': artifacts,
            'counts': {'entries': len(records), 'regular_bytes': total,
                       'unverified_ownership_files': sum(r['type'] == 'file' for r in records)},
            'coverage': 'all_observed_collected_entries; embedded archives and installer payloads not expanded',
            'consistency': {'status': 'stable_observed', 'atomic': False},
            'release_approved': False,
            'blockers': ['File ownership and license conclusions require component audit',
                         'Corresponding-source and replacement-rights review incomplete',
                         'Embedded archives and installer payload correspondence unverified']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--installer', action='append', type=Path, default=[])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.resolve().is_relative_to(args.directory.resolve()):
            raise ValueError('Inventory output must be outside application directory')
        data = canonical(capture(args.directory, args.installer))
        with args.output.open('xb') as stream: stream.write(data)
        print(json.dumps({'inventory_sha256': hashlib.sha256(data).hexdigest(), 'release_approved': False}))
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
