"""Offline, bounded ZIP/member integrity only; never extraction or qualification.

The caller must independently obtain the manifest SHA-256. Source/run fields are
declarations, not authenticated origin. Stable controlled inputs are required;
observable consistency is not an atomic snapshot or hostile-path containment.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import struct
import sys
import zipfile
import zlib

from firmavex.backends.security import bounded_reads, checked_path, read_bytes
from firmavex.product.file_state import path_state
from firmavex.product.verification import check_cancel, digest
from tools.product_ci_tests import console_print
from tools.windows_runtime_preflight import _json, _lexical_path, _path_spelling, _sha

MAX_MANIFEST = 1024**2
MAX_ARCHIVE = 128 * 1024**2
MAX_MEMBER = 128 * 1024**2
MAX_TOTAL = 512 * 1024**2
MAX_MEMBERS = 1024
MAX_SELECTED = 64
MAX_CENTRAL = 1024**2
MAX_RATIO = 200
CHUNK = 64 * 1024


class IntegrityError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise IntegrityError(code)


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _name(name):
    _require(type(name) is str and 0 < len(name) <= 1024
        and not name.startswith('/') and '\\' not in name and ':' not in name
        and all(part not in {'', '.', '..'} for part in name.split('/')), 'unsafe_member_name')
    _path_spelling(name)
    # Printable ASCII avoids Unicode normalization and Windows case aliases.
    _require(all(32 <= ord(c) < 127 for c in name), 'unsafe_member_name')
    return name


def _spec(value):
    _require(type(value) is dict and set(value) == {'schema_version', 'kind', 'source',
        'archive', 'members', 'complete_inventory'}
        and type(value['schema_version']) is int and value['schema_version'] == 1
        and value['kind'] == 'firmavex_artifact_member_manifest'
        and type(value['complete_inventory']) is bool, 'invalid_manifest_schema')
    source = value['source']
    _require(type(source) is dict and set(source) == {'repository', 'revision', 'run_id', 'artifact_id'}
        and source['repository'] == 'mtalhak003/FIRMAVEX'
        and type(source['revision']) is str and re.fullmatch('[0-9a-f]{40}', source['revision'])
        and all(_integer(source[k], 1, 2**63 - 1) for k in ('run_id', 'artifact_id')),
        'invalid_source_declaration')
    archive = value['archive']
    _require(type(archive) is dict and set(archive) == {'sha256', 'size_bytes'}
        and _integer(archive['size_bytes'], 1, MAX_ARCHIVE), 'invalid_archive_identity')
    _sha(archive['sha256'])
    rows = value['members']
    _require(type(rows) is list and 1 <= len(rows) <= MAX_SELECTED, 'manifest_member_bound')
    seen = set()
    for row in rows:
        _require(type(row) is dict and set(row) == {'name', 'sha256', 'size_bytes'}
            and _integer(row['size_bytes'], 0, MAX_MEMBER), 'invalid_member_identity')
        name = _name(row['name'])
        _sha(row['sha256'])
        _require(name.casefold() not in seen, 'duplicate_manifest_member')
        seen.add(name.casefold())
    return value


def _directory(data):
    """Bound the central directory before ZipFile allocates entry objects.

    ZIP64, multipart, self-extracting and appended-data layouts are unsupported.
    They fail closed rather than inheriting zipfile's permissive offset repair.
    """
    end = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    _require(end >= 0 and end + 22 <= len(data), 'invalid_zip_directory')
    _, disk, start_disk, local_count, count, size, offset, comment = struct.unpack_from('<4s4H2IH', data, end)
    _require(disk == start_disk == 0 and local_count == count
        and 0 < count <= MAX_MEMBERS and count < 65535
        and 0 < size <= MAX_CENTRAL and 0 <= offset < end
        and offset + size == end and end + 22 + comment == len(data)
        and data[:4] == b'PK\x03\x04' and data[offset:offset + 4] == b'PK\x01\x02',
        'unsupported_zip_directory')
    return count, offset


def _extra(data):
    position, seen = 0, set()
    while position < len(data):
        _require(position + 4 <= len(data), 'malformed_zip_extra')
        field, size = struct.unpack_from('<HH', data, position)
        position += 4
        _require(field != 1 and field not in seen and position + size <= len(data),
                 'unsupported_zip_extra')
        seen.add(field)
        position += size


def _entries(archive, data):
    count, central = _directory(data)
    infos = archive.infolist()
    _require(len(infos) == count, 'archive_count_mismatch')
    names, file_names, offsets, extents, total = set(), set(), set(), [], 0
    for entry in infos:
        _extra(entry.extra)
        _require(entry.orig_filename == entry.filename, 'unsafe_member_name')
        name = _name(entry.filename[:-1] if entry.is_dir() else entry.filename)
        key = name.casefold()
        _require(key not in names, 'duplicate_archive_member')
        names.add(key)
        if not entry.is_dir():
            file_names.add(key)
        mode = stat.S_IFMT(entry.external_attr >> 16)
        _require(mode in ({0, stat.S_IFDIR} if entry.is_dir() else {0, stat.S_IFREG})
            and not (entry.external_attr & 0x400), 'nonregular_archive_member')
        _require(not entry.flag_bits & ~0x808 and entry.compress_type in
            {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, 'unsupported_archive_encoding')
        _require(0 <= entry.file_size <= MAX_MEMBER and entry.compress_size >= 0
            and entry.file_size <= MAX_RATIO * max(1, entry.compress_size), 'archive_member_bound')
        total += entry.file_size
        _require(total <= MAX_TOTAL, 'archive_byte_bound')
        _require(not entry.is_dir() or entry.file_size == entry.compress_size == 0,
                 'nonempty_archive_directory')
        _require(entry.header_offset not in offsets and 0 <= entry.header_offset < central
            and data[entry.header_offset:entry.header_offset + 4] == b'PK\x03\x04',
            'invalid_local_header')
        offsets.add(entry.header_offset)
        start = entry.header_offset
        _require(start + 30 <= central, 'invalid_local_header')
        _, version, flags, method, _, _, crc, compressed, size, name_size, extra_size = struct.unpack_from(
            '<4s5H3I2H', data, start)
        payload = start + 30 + name_size + extra_size
        _require(version < 45 and entry.extract_version < 45
            and flags == entry.flag_bits and method == entry.compress_type
            and data[start + 30:start + 30 + name_size] == entry.filename.encode('ascii')
            and payload + entry.compress_size <= central, 'inconsistent_local_header')
        _extra(data[start + 30 + name_size:payload])
        expected = (entry.CRC, entry.compress_size, entry.file_size)
        observed = (crc, compressed, size)
        _require(all(a in (0, b) for a, b in zip(observed, expected)) if flags & 8
                 else observed == expected, 'inconsistent_local_header')
        extents.append((start, payload + entry.compress_size, entry))
    _require(min(offsets) == 0, 'unsupported_zip_prefix')
    ordered = sorted(extents)
    for index, (_, end, entry) in enumerate(ordered):
        following = ordered[index + 1][0] if index + 1 < len(ordered) else central
        _require(end <= following, 'overlapping_archive_member')
        if entry.flag_bits & 8:
            _require(following - end in {12, 16}, 'invalid_data_descriptor')
            gap = data[end:following]
            descriptor = struct.pack('<III', entry.CRC, entry.compress_size, entry.file_size)
            _require(gap in (descriptor, b'PK\x07\x08' + descriptor), 'invalid_data_descriptor')
        else:
            _require(end == following, 'unsupported_local_padding')
    for name in names:
        parts = name.split('/')
        _require(all('/'.join(parts[:i]) not in file_names for i in range(1, len(parts))),
                 'conflicting_archive_member')
    return infos


def _chunks(data, entry, cancel_event):
    """Bound actual expansion and require full raw-DEFLATE consumption.

    ZipExtFile truncates decoded output at advertised file_size. That behavior
    can hide a forged smaller size and matching prefix CRC; do not use it as
    proof that the full compressed stream has the asserted identity.
    """
    name_size, extra_size = struct.unpack_from('<HH', data, entry.header_offset + 26)
    position = entry.header_offset + 30 + name_size + extra_size
    end = position + entry.compress_size
    if entry.compress_type == zipfile.ZIP_STORED:
        _require(entry.compress_size == entry.file_size, 'archive_member_size_mismatch')
        while position < end:
            check_cancel(cancel_event)
            chunk = data[position:min(end, position + CHUNK)]
            position += len(chunk)
            yield chunk
        return
    decoder = zlib.decompressobj(-15)
    while True:
        check_cancel(cancel_event)
        encoded = decoder.unconsumed_tail
        if not encoded and position < end:
            encoded = data[position:min(end, position + CHUNK)]
            position += len(encoded)
        chunk = decoder.decompress(encoded, CHUNK)
        if chunk:
            yield chunk
        if decoder.eof:
            _require(not decoder.unused_data and not decoder.unconsumed_tail and position == end,
                     'invalid_deflate_stream')
            return
        _require(encoded or chunk, 'invalid_deflate_stream')


def _members(data, cancel_event):
    # Precheck before constructing ZipFile; its central-directory parser eagerly
    # allocates records. No names or bytes ever become filesystem paths.
    _directory(data)
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = _entries(archive, data)
        for entry in entries:
            check_cancel(cancel_event)
            size, crc, checksum = 0, 0, hashlib.sha256()
            for chunk in _chunks(data, entry, cancel_event):
                check_cancel(cancel_event)
                size += len(chunk)
                _require(size <= entry.file_size and size <= MAX_MEMBER, 'archive_member_bound')
                checksum.update(chunk)
                crc = zlib.crc32(chunk, crc)
            _require(size == entry.file_size, 'archive_member_size_mismatch')
            _require(crc == entry.CRC, 'archive_crc_mismatch')
            if not entry.is_dir():
                result[entry.filename] = {'size_bytes': size, 'sha256': checksum.hexdigest()}
    check_cancel(cancel_event)
    return result


def _snapshot(path, maximum, cancel_event):
    before = path_state(checked_path(path))
    data = read_bytes(path, maximum, cancel_event=cancel_event)
    _require(before == path_state(checked_path(path)), 'input_changed')
    return data, before


def _base():
    return {'schema_version': 1, 'kind': 'firmavex_artifact_member_integrity',
        'status': 'blocked', 'read_only': True, 'tools_executed': False,
        'firmware_executed': False, 'production_qualified': False,
        'atomic_snapshot': False, 'concurrent_path_isolation': False,
        'source_binding': 'supplied_declaration_only_not_authenticated',
        'not_assessed': ['GitHub origin authenticity', 'receipt semantics', 'publisher trust',
            'vendor authenticity', 'executable ownership', 'dependency closure', 'licensing',
            'native execution', 'sandbox qualification', 'production qualification'], 'failures': []}


def verify(archive_path, manifest_path, *, expected_manifest_sha256, cancel_event=None):
    report = _base()
    code = 'invalid_expected_manifest_digest'
    try:
        pin = _sha(expected_manifest_sha256)
        code = 'unsafe_input_path'
        _require(isinstance(archive_path, (str, Path)) and isinstance(manifest_path, (str, Path)), code)
        archive_path = _lexical_path(str(archive_path), Path.cwd())
        manifest_path = _lexical_path(str(manifest_path), Path.cwd())
        _require(str(archive_path).casefold() != str(manifest_path).casefold(), 'duplicate_input_path')
        check_cancel(cancel_event)
        # Four shared reads, each including its own byte-for-byte reread. This
        # bounds initial capture and final consistency reads, including EOF probes.
        with bounded_reads(4 * (MAX_ARCHIVE + MAX_MANIFEST) + 16, calls=4, cancel_event=cancel_event):
            code = 'unreadable_or_changed_input'
            manifest_data, manifest_state = _snapshot(manifest_path, MAX_MANIFEST, cancel_event)
            _require(digest(manifest_data, cancel_event) == pin, 'manifest_digest_mismatch')
            code = 'malformed_manifest'
            spec = _spec(_json(manifest_data))
            code = 'unreadable_or_changed_input'
            data, archive_state = _snapshot(archive_path, MAX_ARCHIVE, cancel_event)
            archive_digest = digest(data, cancel_event)
            _require(len(data) == spec['archive']['size_bytes'], 'archive_size_mismatch')
            _require(archive_digest == spec['archive']['sha256'], 'archive_digest_mismatch')
            code = 'malformed_archive'
            members = _members(data, cancel_event)
            selected = {row['name']: {k: row[k] for k in ('sha256', 'size_bytes')} for row in spec['members']}
            _require(all(members.get(name) == identity for name, identity in selected.items()),
                     'member_identity_mismatch')
            _require(not spec['complete_inventory'] or set(members) == set(selected), 'inventory_mismatch')
            code = 'unreadable_or_changed_input'
            for path, maximum, state, checksum in (
                    (manifest_path, MAX_MANIFEST, manifest_state, pin),
                    (archive_path, MAX_ARCHIVE, archive_state, archive_digest)):
                final, final_state = _snapshot(path, maximum, cancel_event)
                _require(final_state == state and digest(final, cancel_event) == checksum, 'input_changed')
            check_cancel(cancel_event)
        report.update(status='integrity_matched', capture='stable_observed',
            manifest_sha256=pin, archive_sha256=archive_digest, source=spec['source'],
            member_count=len(members), selected_count=len(selected),
            complete_inventory=spec['complete_inventory'], all_member_crc_checked=True,
            members=[{'index': i, **identity} for i, identity in enumerate(selected.values())])
    except IntegrityError as error:
        report['failures'] = [{'code': str(error)}]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError,
            RecursionError, struct.error, zipfile.BadZipFile, NotImplementedError, zlib.error):
        report['failures'] = [{'code': code}]
    return report


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise IntegrityError('invalid_arguments')
    parser = Parser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--manifest-sha256', required=True)
    try:
        args = parser.parse_args(argv)
        result = verify(args.archive, args.manifest, expected_manifest_sha256=args.manifest_sha256)
    except IntegrityError:
        result = _base(); result['failures'] = [{'code': 'invalid_arguments'}]
    console_print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    print('FIRMAVEX ZIP integrity: ' + result['status'] + '; authenticity and qualification not assessed.',
          file=sys.stderr, flush=True)
    return 0 if result['status'] == 'integrity_matched' else 2


if __name__ == '__main__':
    raise SystemExit(main())
