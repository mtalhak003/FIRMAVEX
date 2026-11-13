"""Read explicitly supplied files only; never execute, install, sign or qualify.

JSON is written to stdout and a sanitized summary to stderr. Exit 1 means the
report retains missing/mismatching/unassessed evidence; 2 means assessment was
blocked. Neither a hash match nor a supplied receipt authenticates a publisher.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

from firmavex.backends.security import bounded_reads, checked_path, read_bytes
from firmavex.product.file_state import path_state
from firmavex.product.platform_support import (
    WINDOWS_EXECUTABLES, WINDOWS_PROFILE_ID, WINDOWS_PROFILE_VERSION,
)
from tools.windows_candidate_closure import imports

MAX_FILE_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 128 * 1024**2
MAX_FILES = 64
MAX_MANIFEST_BYTES = 1024**2
MAX_RECEIPT_BYTES = 1024**2
MAX_IMPORTS = 4096
ROLES = ('qemu', 'gdb', 'application', 'worker', 'installer', 'uninstaller')
RECEIPTS = ('runtime_observations', 'package_manifest', 'publisher_authentication',
            'dependency_closure', 'licensing', 'authenticode')
STATES = ('verified', 'missing', 'mismatch', 'blocked', 'not_assessed')
PYTHON_MARKER = 'FIRMAVEX_GDB_CAPABILITY_V1=' + hashlib.sha256(b'probe').hexdigest()
_CODES = frozenset({'invalid_digest', 'duplicate_json_field', 'nonfinite_json',
    'json_complexity_bound', 'unsafe_path', 'forbidden_path', 'forbidden_original_checkout',
    'aggregate_byte_bound', 'capture_changed', 'capture_changed_or_read_blocked', 'invalid_file_descriptor',
    'invalid_manifest_schema', 'artifact_count_bound', 'duplicate_input_path',
    'invalid_companion_inventory', 'static_import_count_bound', 'invalid_observation_receipt',
    'malformed_pe', 'unsupported_pe_architecture', 'malformed_certificate_table', 'invalid_arguments'})


class _Blocked(ValueError):
    """Only fixed diagnostic codes may reach the report."""


def _check(state, code, **fields):
    return {'state': state, 'code': code, **fields}


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise _Blocked('invalid_digest')
    return value


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _Blocked('duplicate_json_field')
            result[key] = value
        return result
    def nonfinite(_):
        raise _Blocked('nonfinite_json')
    value = json.loads(data, object_pairs_hook=pairs, parse_constant=nonfinite)
    pending, count = [(value, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 12 or count > 8192:
            raise _Blocked('json_complexity_bound')
        if type(node) is dict:
            pending.extend((v, depth + 1) for v in node.values())
        elif type(node) is list:
            pending.extend((v, depth + 1) for v in node)
    return value


def _lexical_path(value, base):
    # No resolve(), stat(), expanduser(), directory scan or PATH search here.
    if (type(value) is not str or not 1 <= len(value) <= 4096
            or value.startswith(('~', '\\\\', '//'))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise _Blocked('unsafe_path')
    parts = re.split(r'[\\/]+', value.casefold())
    devices = {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)),
               *(f'lpt{i}' for i in range(1, 10))}
    if any(p and (p.endswith((' ', '.')) or '~' in p or p.split('.')[0] in devices)
           for p in parts):
        raise _Blocked('unsafe_path')
    if '..' in parts or any(a == 'evidence' and b == 'windows-sandbox'
                            for a, b in zip(parts, parts[1:])):
        raise _Blocked('forbidden_path')
    # Reject device paths, ADS and foreign drive spellings, not just traversal.
    if ':' in value and not (os.name == 'nt' and re.match(r'^[A-Za-z]:[\\/]', value)
                             and value.count(':') == 1):
        raise _Blocked('unsafe_path')
    path = Path(value)
    path = path if path.is_absolute() else base / path
    spelling = str(path.absolute()).replace('\\', '/').casefold()
    if spelling == '/workspace/firmavex' or spelling.startswith('/workspace/firmavex/'):
        raise _Blocked('forbidden_original_checkout')
    tokens = spelling.split('/')
    if any(a == 'evidence' and b == 'windows-sandbox' for a, b in zip(tokens, tokens[1:])):
        raise _Blocked('forbidden_path')
    return path.absolute()


class _Capture:
    def __init__(self):
        self.files, self.missing, self.total = [], [], 0

    def read(self, path, maximum):
        try:
            checked_path(path)
        except FileNotFoundError:
            self.missing.append(path)
            raise
        try:
            size = path.stat().st_size
        except FileNotFoundError as error:
            raise _Blocked('capture_changed') from error
        if size > min(maximum, MAX_TOTAL_BYTES - self.total):
            raise ValueError('Input byte bound exceeded')
        # Once existence was observed, disappearance is an inconsistent capture,
        # including FileNotFoundError raised inside the shared reader's checks.
        try:
            data = read_bytes(path, min(maximum, MAX_TOTAL_BYTES - self.total))
            state = path_state(checked_path(path))
        except (FileNotFoundError, ValueError) as error:
            raise _Blocked('capture_changed_or_read_blocked') from error
        self.total += len(data)
        if self.total > MAX_TOTAL_BYTES:
            raise _Blocked('aggregate_byte_bound')
        digest = hashlib.sha256(data).hexdigest()
        self.files.append((path, digest, state))
        return data, {'sha256': digest, 'size_bytes': len(data)}

    def finish(self):
        # Recheck earlier inputs after all processing, not just within each read.
        for path, digest, state in self.files:
            data = read_bytes(path, MAX_FILE_BYTES)
            if (hashlib.sha256(data).hexdigest() != digest
                    or path_state(checked_path(path)) != state):
                raise _Blocked('capture_changed')
        for path in self.missing:
            try:
                checked_path(path)
            except FileNotFoundError:
                continue
            raise _Blocked('capture_changed')


def _descriptor(value, base, *, runtime=False):
    if (type(value) is not dict or 'path' not in value
            or not value.keys() <= ({'path'} if runtime else {'path', 'sha256'})):
        raise _Blocked('invalid_file_descriptor')
    if 'sha256' in value:
        _sha(value['sha256'])
    return {'path': _lexical_path(value['path'], base), 'sha256': value.get('sha256')}


def _spec(value, manifest):
    if (type(value) is not dict or not {'schema_version', 'artifacts'} <= value.keys()
            or not value.keys() <= {'schema_version', 'artifacts', 'companions', 'receipts'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['artifacts']) is not dict or not value['artifacts'].keys() <= set(ROLES)
            or type(value.get('companions', [])) is not list
            or type(value.get('receipts', {})) is not dict
            or not value.get('receipts', {}).keys() <= set(RECEIPTS)):
        raise _Blocked('invalid_manifest_schema')
    if len(value['artifacts']) + len(value.get('companions', [])) > MAX_FILES:
        raise _Blocked('artifact_count_bound')
    artifacts = {name: _descriptor(item, manifest.parent, runtime=name in WINDOWS_EXECUTABLES)
                 for name, item in value['artifacts'].items()}
    companions = [_descriptor(item, manifest.parent) for item in value.get('companions', [])]
    receipts = {name: _descriptor(item, manifest.parent) for name, item in value.get('receipts', {}).items()}
    paths = [manifest, *(d['path'] for d in artifacts.values()),
             *(d['path'] for d in companions), *(d['path'] for d in receipts.values())]
    if len({str(p).casefold() for p in paths}) != len(paths):
        raise _Blocked('duplicate_input_path')
    names = [d['path'].name.casefold() for d in companions]
    if (len(set(names)) != len(names)
            or any(not re.fullmatch(r'[a-z0-9][a-z0-9_.+\-]{0,158}\.dll', n) for n in names)):
        raise _Blocked('invalid_companion_inventory')
    return artifacts, companions, receipts


def _read(capture, descriptor, maximum):
    if descriptor is None:
        return None, _check('missing', 'file_not_supplied')
    try:
        data, identity = capture.read(descriptor['path'], maximum)
        return data, _check('verified', 'bounded_regular_file_read', **identity)
    except FileNotFoundError:
        return None, _check('missing', 'file_not_found')
    except _Blocked:
        raise
    except (OSError, ValueError):
        return None, _check('blocked', 'file_unsafe_unreadable_or_changed')


def _identity(file, expected):
    if file['state'] != 'verified':
        return _check(file['state'], file['code'])
    if expected is None:
        return _check('missing', 'expected_digest_not_supplied')
    return _check('verified' if file['sha256'] == expected else 'mismatch',
                  'digest_comparison_only', expected_sha256=expected)


def _pe(data):
    """Bounded PE/header and WIN_CERTIFICATE geometry only, not Authenticode."""
    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise _Blocked('malformed_pe')
        return struct.unpack_from(fmt, data, offset)
    if len(data) < 64 or data[:2] != b'MZ':
        raise _Blocked('malformed_pe')
    pe, = unpack('<I', 60)
    if not 64 <= pe <= 1024**2 or data[pe:pe + 4] != b'PE\0\0':
        raise _Blocked('malformed_pe')
    machine, = unpack('<H', pe + 4)
    size, = unpack('<H', pe + 20)
    sections, = unpack('<H', pe + 6)
    optional = pe + 24
    magic, = unpack('<H', optional)
    if (machine, magic) not in {(0x8664, 0x20b), (0x14c, 0x10b)}:
        raise _Blocked('unsupported_pe_architecture')
    base = 112 if magic == 0x20b else 96
    if size < base or optional + size > len(data):
        raise _Blocked('malformed_pe')
    count, = unpack('<I', optional + base - 4)
    if count > 16 or base + count * 8 > size:
        raise _Blocked('malformed_pe')
    headers, = unpack('<I', optional + 60)
    table = optional + size
    if not 1 <= sections <= 96 or not table + sections * 40 <= headers <= len(data):
        raise _Blocked('malformed_pe')
    payload_end = headers
    for index in range(sections):
        raw_size, raw = unpack('<II', table + index * 40 + 16)
        if raw_size and (raw < headers or raw + raw_size > len(data)):
            raise _Blocked('malformed_pe')
        payload_end = max(payload_end, raw + raw_size if raw_size else headers)
    geometry = _check('verified', 'pe_header_structure_only', architecture='x64' if magic == 0x20b else 'x86')
    if count <= 4:
        return geometry, _check('missing', 'certificate_table_absent')
    offset, length = unpack('<II', optional + base + 4 * 8)
    if offset == length == 0:
        return geometry, _check('missing', 'certificate_table_absent')
    if (not offset or length < 8 or length > 4 * 1024**2 or offset % 8
            or offset < payload_end or offset + length > len(data)):
        raise _Blocked('malformed_certificate_table')
    end, entries = offset + length, 0
    while offset < end:
        if offset + 8 > end or entries >= 256:
            raise _Blocked('malformed_certificate_table')
        size, revision, kind = unpack('<IHH', offset)
        if size <= 8 or offset + size > end or revision != 0x200 or kind != 2:
            raise _Blocked('malformed_certificate_table')
        offset += (size + 7) // 8 * 8
        entries += 1
    if offset != end:
        raise _Blocked('malformed_certificate_table')
    return geometry, _check('verified', 'certificate_table_structure_only', entries=entries)


def _artifact(capture, descriptor, role):
    data, file = _read(capture, descriptor, MAX_FILE_BYTES)
    expected = WINDOWS_EXECUTABLES[role][1] if role in WINDOWS_EXECUTABLES else (descriptor or {}).get('sha256')
    result = {'file': file, 'identity': _identity(file, expected)}
    if role in WINDOWS_EXECUTABLES:
        version = WINDOWS_EXECUTABLES[role][0]
        result['version'] = _check('verified' if result['identity']['state'] == 'verified' else 'not_assessed',
                                   'profile_digest_association_only', expected=version)
    if data is None:
        result['signing'] = _check(file['state'], file['code'])
        return result, []
    try:
        result['pe'], result['certificate_table'] = _pe(data)
        result['signing'] = (_check('not_assessed', 'authenticode_trust_not_verified')
                             if result['certificate_table']['state'] == 'verified'
                             else _check('missing', 'certificate_table_absent'))
    except ValueError:
        result['pe'] = _check('blocked', 'pe_or_certificate_structure_unsupported')
        result['signing'] = _check('blocked', 'signature_cannot_be_assessed')
    dlls = []
    if role in ('qemu', 'gdb', 'companion'):
        try:
            dlls = imports(data)
            result['imports'] = _check('verified', 'ordinary_x64_imports_only', dlls=dlls)
        except (ValueError, UnicodeError, struct.error):
            result['imports'] = _check('blocked', 'static_imports_unsupported')
    return result, dlls


def _runtime_observations(data, artifacts):
    """Cross-check supplied observations; never reclassify them as native proof."""
    value = _json(data)
    if (type(value) is not dict or set(value) != {'schema_version', 'tools'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['tools']) is not dict or not value['tools'].keys() <= {'qemu', 'gdb'}):
        raise _Blocked('invalid_observation_receipt')
    checks = {}
    for name in ('qemu', 'gdb'):
        row = value['tools'].get(name)
        if row is None:
            checks[name] = _check('missing', 'tool_observation_not_supplied')
            continue
        fields = {'sha256', 'version', 'mps2_an385'} if name == 'qemu' else {'sha256', 'version', 'arm', 'python_hashlib_marker'}
        if type(row) is not dict or 'sha256' not in row or not row.keys() <= fields:
            raise _Blocked('invalid_observation_receipt')
        digest = _sha(row['sha256'])
        file = artifacts[name]['file']
        if file['state'] != 'verified':
            checks[name] = _check('blocked', 'observation_subject_unavailable')
            continue
        if digest != file['sha256']:
            checks[name] = _check('mismatch', 'observation_subject_digest_mismatch')
            continue
        checks[name] = _check('verified', 'receipt_subject_binding_only')
        for field in sorted(fields - {'sha256'}):
            if field not in row:
                checks[name + '_' + field] = _check('missing', 'observation_field_not_supplied')
                continue
            observed = row[field]
            if field == 'version':
                pattern = (r'QEMU emulator version [0-9]{1,6}(?:\.[0-9]{1,6}){1,3}' if name == 'qemu'
                           else r'GNU gdb \(GDB\) [0-9]{1,6}(?:\.[0-9]{1,6}){1,3}')
                if type(observed) is not str or len(observed) > 128 or not re.fullmatch(pattern, observed):
                    raise _Blocked('invalid_observation_receipt')
                matches = observed == WINDOWS_EXECUTABLES[name][0]
                detail = {'reported': observed, 'expected': WINDOWS_EXECUTABLES[name][0]}
            elif field == 'python_hashlib_marker':
                if type(observed) is not str or len(observed) > 128:
                    raise _Blocked('invalid_observation_receipt')
                matches, detail = observed == PYTHON_MARKER, {}
            else:
                if type(observed) is not bool:
                    raise _Blocked('invalid_observation_receipt')
                matches, detail = observed is True, {}
            checks[name + '_' + field] = _check('verified' if matches else 'mismatch',
                                               'receipt_consistency_only', **detail)
    return {'scope': 'caller_supplied_receipt_consistency_only', 'checks': checks}


def _base():
    return {'schema_version': 1, 'kind': 'firmavex_windows_runtime_preflight',
            'profile': {'id': WINDOWS_PROFILE_ID, 'version': WINDOWS_PROFILE_VERSION, 'architecture': 'x64'},
            'read_only': True, 'firmware_executed': False, 'tools_executed': False,
            'production_admission_evaluated': False, 'production_qualified': False,
            'atomic_snapshot': False, 'artifacts': {}, 'receipts': {}, 'required_dlls': {},
            'checks': {name: _check('not_assessed', code) for name, code in (
                ('native_capabilities', 'no_runtime_tools_executed'),
                ('publisher_trust', 'publisher_authentication_not_verified'),
                ('dynamic_dll_closure', 'native_loader_not_observed'),
                ('license_completeness', 'legal_review_not_performed'),
                ('authenticode_trust', 'native_signature_trust_not_verified'),
                ('application_signing_coverage', 'explicit_files_not_complete_inventory'),
                ('qualification', 'preflight_never_qualifies'))}}


def _finish_report(report):
    counts = Counter()
    def visit(node):
        if type(node) is dict:
            if node.get('state') in STATES:
                counts[node['state']] += 1
            for item in node.values():
                visit(item)
        elif type(node) is list:
            for item in node:
                visit(item)
    visit(report)
    report['counts'] = {state: counts[state] for state in STATES}
    report['status'] = next((s for s in ('blocked', 'mismatch', 'missing', 'not_assessed') if counts[s]), 'not_assessed')
    return report


def preflight(manifest_path, *, expected_manifest_sha256=None):
    """Return sanitized static evidence states, including on unsafe/missing input."""
    report = _base()
    manifest_read = False
    try:
        manifest = _lexical_path(os.fspath(manifest_path), Path.cwd())
        # One spare byte permits the final EOF probe at the inclusive byte cap.
        with bounded_reads(4 * MAX_TOTAL_BYTES + 1, calls=2 * (MAX_FILES + len(RECEIPTS) + 1)):
            capture = _Capture()
            raw, identity = capture.read(manifest, MAX_MANIFEST_BYTES)
            manifest_read = True
            if expected_manifest_sha256 is not None and identity['sha256'] != _sha(expected_manifest_sha256):
                report['checks']['manifest'] = _check('mismatch', 'manifest_digest_mismatch')
                return _finish_report(report)
            spec = _spec(_json(raw), manifest)
            report['checks']['manifest'] = _check(
                'verified' if expected_manifest_sha256 is not None else 'not_assessed',
                'manifest_integrity_only' if expected_manifest_sha256 is not None else 'manifest_digest_unpinned', **identity)
            descriptors, companions, receipts = spec
            references = {}
            for name in ROLES:
                report['artifacts'][name], dlls = _artifact(capture, descriptors.get(name), name)
                for dll in dlls:
                    references.setdefault(dll, []).append(name)
            names = {}
            for index, descriptor in enumerate(companions, 1):
                name = f'companion_{index:03}'
                report['artifacts'][name], dlls = _artifact(capture, descriptor, 'companion')
                names[descriptor['path'].name.casefold()] = name
                for dll in dlls:
                    references.setdefault(dll, []).append(name)
            if sum(map(len, references.values())) > MAX_IMPORTS:
                raise _Blocked('static_import_count_bound')
            report['checks']['companion_inventory'] = _check(
                'verified' if companions else 'missing', 'declared_companions_only', count=len(companions))
            for dll, owners in sorted(references.items()):
                selected = names.get(dll)
                identity = _check('missing', 'import_not_explicitly_supplied')
                if selected:
                    row = report['artifacts'][selected]
                    identity = next((row[key] for key in ('file', 'pe', 'imports', 'identity')
                                     if row.get(key, {}).get('state') != 'verified'),
                                    _check('verified', 'explicit_companion_static_checks_only'))
                report['required_dlls'][dll] = {**identity, 'required_by': owners, 'artifact': selected}
            for name in RECEIPTS:
                descriptor = receipts.get(name)
                data, file = _read(capture, descriptor, MAX_RECEIPT_BYTES)
                integrity = _identity(file, (descriptor or {}).get('sha256'))
                report['receipts'][name] = {'file': file, 'integrity': integrity}
                if integrity['state'] != 'verified':
                    report['checks'][name] = integrity.copy()
                elif name == 'runtime_observations':
                    report['receipts'][name].update(_runtime_observations(data, report['artifacts']))
                    report['checks'][name] = _check('not_assessed', 'supplied_observations_not_independently_verified')
                else:
                    report['checks'][name] = _check('not_assessed', 'receipt_integrity_only_not_authentication')
            capture.finish()
            file_checks = [v['file'] for v in (*report['artifacts'].values(), *report['receipts'].values())]
            blocked = any(v['state'] == 'blocked' for v in file_checks)
            report['checks']['capture'] = _check('blocked' if blocked else 'verified',
                                                'partial_capture' if blocked else 'stable_observed_not_atomic')
    except FileNotFoundError:
        report = _base()
        report['checks']['capture'] = _check('blocked' if manifest_read else 'missing',
                                            'capture_changed' if manifest_read else 'manifest_not_found')
    except _Blocked as error:
        report = _base()
        code = error.args[0] if error.args and error.args[0] in _CODES else 'input_blocked'
        report['checks']['capture'] = _check('blocked', code)
    except (OSError, ValueError, TypeError, RecursionError, struct.error):
        # Never echo exception text, input paths, raw receipt data or environments.
        report = _base()
        report['checks']['capture'] = _check('blocked', 'unsafe_malformed_oversized_or_inconsistent_input')
    return _finish_report(report)


def summary(report):
    counts = ', '.join(f'{state}={report["counts"][state]}' for state in STATES)
    return ('Windows runtime preflight: ' + report['status'] + '\n' + counts
            + '\nNo tools or firmware executed. Runtime/signing qualification: NOT ASSESSED.\n')


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise _Blocked('invalid_arguments')
    parser = Parser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--expected-manifest-sha256')
    try:
        args = parser.parse_args(argv)
    except _Blocked:
        report = _base()
        report['checks']['capture'] = _check('blocked', 'invalid_arguments')
        report = _finish_report(report)
    else:
        report = preflight(args.manifest, expected_manifest_sha256=args.expected_manifest_sha256)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    print(summary(report), file=sys.stderr, end='')
    return 2 if report['status'] == 'blocked' else 1


if __name__ == '__main__':
    raise SystemExit(main())
