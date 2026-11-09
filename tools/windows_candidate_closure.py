"""Read-only candidate PE import-graph audit; never a full DLL or package proof.

Only ordinary PE32+ x64 imports are supported. Delay imports fail closed. Dynamic
LoadLibrary calls, API-set mapping, forwarded exports, loader search-policy and
publisher/package ownership are not authenticated by this tool. The manifest
digest must be independently obtained. No executable is launched or extracted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from firmavex.backends.security import checked_path, read_bytes

MAX_FILE = 128 * 1024**2
MAX_TOTAL = 2 * 1024**3
MAX_FILES = 4096
MAX_EDGES = 65536
_FILE = r'[A-Za-z0-9][A-Za-z0-9_.+\-]{0,158}\.(?:exe|dll)'


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest field')
        result[key] = value
    return result


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected lowercase SHA-256')
    return value


def imports(data):
    """Return sorted ordinary import DLL names from bounded PE32+ x64 bytes."""
    if type(data) is not bytes or not 64 <= len(data) <= MAX_FILE or data[:2] != b'MZ':
        raise ValueError('Expected bounded PE bytes')
    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        if type(offset) is not int or offset < 0 or offset + size > len(data):
            raise ValueError('Truncated PE record')
        return struct.unpack_from(fmt, data, offset)
    pe, = unpack('<I', 60)
    if pe < 64 or pe > 1024**2 or data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    machine, count, _, _, _, optional_size, _ = unpack('<HHIIIHH', pe + 4)
    optional = pe + 24
    magic, = unpack('<H', optional)
    if machine != 0x8664 or magic != 0x20b or not 1 <= count <= 96 or optional_size < 128:
        raise ValueError('Only bounded x64 PE32+ is supported')
    directories, = unpack('<I', optional + 108)
    if not 2 <= directories <= 16 or optional_size < 112 + directories * 8:
        raise ValueError('Invalid PE directories')
    if directories > 13 and any(unpack('<II', optional + 112 + 13 * 8)):
        raise ValueError('Delay-import closure is unsupported')
    headers, = unpack('<I', optional + 60)
    section_table = optional + optional_size
    if headers < section_table + 40*count or headers > len(data):
        raise ValueError('Invalid PE header bounds')
    sections = []
    for index in range(count):
        size, address, raw_size, raw = unpack('<IIII', section_table + index*40 + 8)
        end = address + max(size, raw_size)
        if (address < headers or end > 2**32 or (raw_size and (raw < headers or raw + raw_size > len(data)))
                or any(address < b and end > a for a, b, _, _ in sections)):
            raise ValueError('Invalid or overlapping PE sections')
        sections.append((address, end, raw_size, raw))
    def offset(rva, size):
        if not 0 < rva < 2**32 or rva + size > 2**32:
            raise ValueError('Invalid PE RVA')
        if rva < headers and rva + size <= headers:
            return rva
        for start, _, raw_size, raw in sections:
            if start <= rva and rva + size <= start + raw_size:
                return raw + rva - start
        raise ValueError('PE RVA has no complete file mapping')
    address, size = unpack('<II', optional + 120)
    if address == size == 0:
        return []
    if not address or not 20 <= size <= 65536:
        raise ValueError('Invalid import directory')
    found = set()
    for position in range(0, min(size, 20 * 513) - 19, 20):
        descriptor = unpack('<IIIII', offset(address + position, 20))
        if not any(descriptor):
            return sorted(found)
        if len(found) >= 512:
            raise ValueError('Import count exceeds bound')
        name_rva = descriptor[3]
        raw_name = bytearray()
        for index in range(164):
            value = data[offset(name_rva + index, 1)]
            if value == 0:
                break
            raw_name.append(value)
        else:
            raise ValueError('Unterminated import name')
        name = raw_name.decode('ascii')
        if not re.fullmatch(_FILE, name, re.I) or not name.lower().endswith('.dll'):
            raise ValueError('Unsupported import DLL name')
        found.add(name.lower())
    raise ValueError('Import directory lacks bounded terminator')


def _table(value):
    if type(value) is not dict or len(value) > MAX_FILES:
        raise ValueError('Invalid file inventory')
    result = {}
    for name, identity in value.items():
        if (type(name) is not str or not re.fullmatch(_FILE, name, re.I)
                or name.lower() in result or type(identity) is not dict
                or set(identity) != {'sha256', 'size_bytes'}
                or type(identity['size_bytes']) is not int or not 1 <= identity['size_bytes'] <= MAX_FILE):
            raise ValueError('Invalid, unsafe or duplicate file identity')
        _sha(identity['sha256'])
        result[name.lower()] = (name, identity)
    return result


def _available(directory):
    files = {}
    for index, path in enumerate(checked_path(directory, directory=True).iterdir()):
        if index >= MAX_FILES:
            raise ValueError('Directory entry bound exceeded')
        if path.name.lower().endswith(('.exe', '.dll')):
            key = path.name.lower()
            if key in files:
                raise ValueError('Case-insensitive filesystem collision')
            files[key] = path
    return files


def audit(vendor_bin, system_directory, manifest, expected_manifest_sha256):
    """Check actual listed bytes and their import graph, without approval claims."""
    vendor_bin = checked_path(vendor_bin, directory=True)
    system_directory = checked_path(system_directory, directory=True)
    if vendor_bin == system_directory or vendor_bin in system_directory.parents or system_directory in vendor_bin.parents:
        raise ValueError('Distinct independent vendor and system directories required')
    raw = read_bytes(manifest, 2 * 1024**2)
    if hashlib.sha256(raw).hexdigest() != _sha(expected_manifest_sha256):
        raise ValueError('Manifest digest mismatch')
    spec = json.loads(raw, object_pairs_hook=_object)
    if (type(spec) is not dict or set(spec) != {'schema_version', 'roots', 'vendor', 'system'}
            or type(spec['schema_version']) is not int or spec['schema_version'] != 1
            or type(spec['roots']) is not list or not 1 <= len(spec['roots']) <= 16):
        raise ValueError('Unsupported import-graph manifest')
    vendor, system = _table(spec['vendor']), _table(spec['system'])
    if len(vendor) + len(system) > MAX_FILES or vendor.keys() & system.keys():
        raise ValueError('Oversized or ambiguous search inventory')
    roots = spec['roots']
    if (any(type(name) is not str or name != name.lower() or name not in vendor for name in roots)
            or len(set(roots)) != len(roots)):
        raise ValueError('Explicit unique lowercase vendor roots required')
    # Directory names, not PATH, establish the finite supported resolution policy.
    available = {}
    for label, directory in (('vendor', vendor_bin), ('system', system_directory)):
        available[label] = _available(directory)
    pending, graph, identities, total, edges = list(reversed(roots)), {}, {}, 0, 0
    while pending:
        name = pending.pop()
        if name in graph:
            continue
        if len(graph) >= MAX_FILES:
            raise ValueError('Reachable import graph exceeds bound')
        label, table, directory = ('vendor', vendor, vendor_bin) if name in vendor else ('system', system, system_directory)
        if name not in table:
            raise ValueError('Unresolved DLL or API-set mapping')
        if name in available['vendor'] and name in available['system']:
            raise ValueError('Ambiguous vendor/system DLL selection')
        declared, expected = table[name]
        selected = available[label].get(name)
        if selected is None or selected.name != declared:
            raise ValueError('Manifest and actual filename differ')
        total += expected['size_bytes']
        if total > MAX_TOTAL:
            raise ValueError('Reachable byte bound exceeded')
        data = read_bytes(checked_path(selected), MAX_FILE)
        if len(data) != expected['size_bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Observed file identity differs from immutable manifest')
        graph[name] = imports(data)
        edges += len(graph[name])
        if edges > MAX_EDGES:
            raise ValueError('Import edge count exceeds bound')
        identities[name] = {'origin': label, **expected}
        pending.extend(reversed(graph[name]))
    # Detect observable changes to all measured files across the audit interval.
    for name, identity in identities.items():
        table, directory = (vendor, vendor_bin) if identity['origin'] == 'vendor' else (system, system_directory)
        data = read_bytes(directory / table[name][0], MAX_FILE)
        if len(data) != identity['size_bytes'] or hashlib.sha256(data).hexdigest() != identity['sha256']:
            raise ValueError('Measured file changed during audit')
    if read_bytes(manifest, 2 * 1024**2) != raw:
        raise ValueError('Manifest changed during audit')
    if _available(vendor_bin) != available['vendor'] or _available(system_directory) != available['system']:
        raise ValueError('Executable directory inventory changed during audit')
    return {'schema_version': 1, 'kind': 'firmavex_candidate_static_pe_import_graph',
        'candidate_only': True, 'production_qualified': False, 'status': 'verified_static_import_graph',
        'manifest_sha256': expected_manifest_sha256, 'roots': roots,
        'files': dict(sorted(identities.items())), 'imports': dict(sorted(graph.items())),
        'atomic_snapshot': False, 'firmware_executed': False, 'package_ownership_authenticated': False,
        'complete_dynamic_dll_closure_verified': False,
        'limitations': ['Ordinary PE32+ x64 imports under the explicit finite resolution policy only.',
            'Dynamic loads, forwarded exports, API-set resolution and actual Windows loader search remain unproven.',
            'Manifest pins do not authenticate package ownership, publisher signatures, license evidence or build origin.',
            'Use authentic signed-package verification and separately approved native loaded-module/ownership audits.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('vendor-bin', 'system-directory', 'manifest'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--expected-manifest-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.vendor_bin, args.system_directory, args.manifest, args.expected_manifest_sha256)
    except Exception as error:
        print(json.dumps({'candidate_only': True, 'production_qualified': False,
                          'status': 'rejected', 'error_type': type(error).__name__}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
