"""Invented ZIPs only: integrity is never publisher or execution evidence."""
import builtins
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import threading
import urllib.request
import warnings
import zipfile
import zlib

import pytest

from tools import artifact_member_integrity as audit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def packed(rows, *, compression=zipfile.ZIP_STORED):
    target = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(target, 'w', compression=compression) as archive:
            for name, data in rows:
                if isinstance(name, str):
                    entry = zipfile.ZipInfo(name)
                    # ZipInfo normalizes os.sep on Windows. These are crafted
                    # ZIP bytes, never extracted paths: retain the exact unsafe
                    # spelling so native tests actually exercise rejection.
                    entry.filename = entry.orig_filename = name
                    entry.compress_type = compression
                    archive.writestr(entry, data)
                else:
                    archive.writestr(name, data)
    return target.getvalue()


def test_zip_fixture_preserves_unsafe_backslash_under_windows_constructor_rules(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(zipfile.os, 'sep', '\\')
        assert zipfile.ZipInfo('a\\b').filename == 'a/b'
        raw = packed([('a\\b', b'crafted unsafe name')])
    # Both local and central names must contain the actual malicious spelling.
    assert raw.count(b'a\\b') == 2
    with pytest.raises(ValueError):
        audit._members(raw, None)


def raw_member_zip(data, compressed, *, advertised=None, method=zipfile.ZIP_DEFLATED):
    """Craft coherent ZIP headers without trusting zipfile's output truncation."""
    name = b'crafted.txt'
    advertised = len(data) if advertised is None else advertised
    crc = zlib.crc32(data)
    local = struct.pack('<4s5H3I2H', b'PK\x03\x04', 20, 0, method, 0, 0,
                        crc, len(compressed), advertised, len(name), 0) + name + compressed
    central = struct.pack('<4s6H3I5H2I', b'PK\x01\x02', 20, 20, 0, method, 0, 0,
                          crc, len(compressed), advertised, len(name), 0, 0, 0, 0,
                          (stat.S_IFREG | 0o600) << 16, 0) + name
    end = struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, 1, 1, len(central), len(local), 0)
    return local + central + end


def deflated(data):
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


def set_archive_bytes(supplied, raw):
    supplied['archive'].write_bytes(raw)
    supplied['value']['archive'] = {'sha256': digest(raw), 'size_bytes': len(raw)}
    supplied['save']()


@pytest.fixture
def supplied(tmp_path):
    archive = tmp_path / 'private-original.zip'
    manifest = tmp_path / 'private-selection.json'
    data = b'{"diagnostic":"PRIVATE-TOKEN-DO-NOT-PUBLISH"}'
    archive.write_bytes(packed([('private-selected.json', data), ('other.txt', b'other')]))
    value = {
        'schema_version': 1, 'kind': 'firmavex_artifact_member_manifest',
        'source': {'repository': 'mtalhak003/FIRMAVEX', 'revision': 'a' * 40,
                   'run_id': 123, 'artifact_id': 456},
        'archive': {'sha256': digest(archive.read_bytes()), 'size_bytes': archive.stat().st_size},
        'complete_inventory': False,
        'members': [{'name': 'private-selected.json', 'sha256': digest(data), 'size_bytes': len(data)}],
    }
    def save():
        manifest.write_bytes(json.dumps(value, sort_keys=True).encode())
        return digest(manifest.read_bytes())
    def replace(rows, *, compression=zipfile.ZIP_STORED):
        archive.write_bytes(packed(rows, compression=compression))
        value['archive'] = {'sha256': digest(archive.read_bytes()), 'size_bytes': archive.stat().st_size}
        return save()
    save()
    return {'archive': archive, 'manifest': manifest, 'value': value, 'save': save,
            'replace': replace, 'selected': data}


def verify(supplied, **overrides):
    args = {'expected_manifest_sha256': digest(supplied['manifest'].read_bytes())}
    args.update(overrides)
    return audit.verify(supplied['archive'], supplied['manifest'], **args)


def assert_blocked(result):
    assert result['status'] == 'blocked'
    assert result['failures']
    assert all(set(row) == {'code'} and type(row['code']) is str for row in result['failures'])
    for key in ('tools_executed', 'production_qualified', 'atomic_snapshot', 'concurrent_path_isolation'):
        assert result[key] is False


def forbid_activity(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Integrity checker attempted execution, network, scan, extraction or write')
    for name in ('run', 'Popen', 'call', 'check_call', 'check_output'):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    for name in ('write_bytes', 'write_text', 'mkdir', 'touch', 'unlink', 'replace',
                 'rename', 'glob', 'rglob', 'iterdir'):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ('walk', 'scandir', 'listdir'):
        monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(zipfile.ZipFile, 'extract', forbidden)
    monkeypatch.setattr(zipfile.ZipFile, 'extractall', forbidden)
    normal_open, normal_io, normal_os = builtins.open, io.open, os.open
    def readonly_open(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+')
        return normal_open(file, mode, *args, **kwargs)
    def readonly_io(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+')
        return normal_io(file, mode, *args, **kwargs)
    def readonly_os(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return normal_os(path, flags, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', readonly_open)
    monkeypatch.setattr(io, 'open', readonly_io)
    monkeypatch.setattr(os, 'open', readonly_os)


def test_integrity_is_deterministic_read_only_sanitized_and_not_qualification(supplied, monkeypatch):
    pin = digest(supplied['manifest'].read_bytes())
    before = {key: supplied[key].read_bytes() for key in ('archive', 'manifest')}
    forbid_activity(monkeypatch)
    first = audit.verify(supplied['archive'], supplied['manifest'], expected_manifest_sha256=pin)
    assert first == audit.verify(supplied['archive'], supplied['manifest'], expected_manifest_sha256=pin)
    assert first['status'] == 'integrity_matched'
    assert first['failures'] == [] and first['read_only'] is True
    for key in ('tools_executed', 'production_qualified', 'atomic_snapshot', 'concurrent_path_isolation'):
        assert first[key] is False
    serialized = json.dumps(first, sort_keys=True, allow_nan=False)
    for private in ('PRIVATE-TOKEN', 'private-selected', 'private-original', 'other.txt', str(supplied['archive'].parent)):
        assert private not in serialized
    for key in before:
        assert supplied[key].read_bytes() == before[key]


def test_complete_inventory_matches_all_files_and_allows_explicit_directories(supplied):
    value = supplied['value']
    value['complete_inventory'] = True
    value['members'].append({'name': 'other.txt', 'sha256': digest(b'other'), 'size_bytes': 5})
    supplied['replace']([('folder/', b''), ('private-selected.json', supplied['selected']), ('other.txt', b'other')])
    assert verify(supplied)['status'] == 'integrity_matched'


def test_empty_selected_member_and_deflated_member_are_supported(supplied):
    supplied['value']['members'] = [{'name': 'empty.txt', 'sha256': digest(b''), 'size_bytes': 0}]
    supplied['replace']([('empty.txt', b''), ('other.txt', b'hello world' * 5)], compression=zipfile.ZIP_DEFLATED)
    assert verify(supplied)['status'] == 'integrity_matched'


@pytest.mark.parametrize('extra', [struct.pack('<HHQ', 1, 8, 3), b'\x01',
    struct.pack('<HH', 10, 7) + b'bad', struct.pack('<HHHH', 10, 0, 10, 0)],
    ids=['zip64-with-low-version', 'truncated-header', 'truncated-payload', 'duplicate-field'])
def test_unsupported_or_malformed_extra_fields_are_refused(supplied, extra):
    entry = zipfile.ZipInfo('unselected.txt')
    entry.extract_version = 20
    entry.extra = extra
    supplied['replace']([('private-selected.json', supplied['selected']), (entry, b'abc')])
    assert_blocked(verify(supplied))


def test_zip64_central_size_override_with_forged_low_version_is_refused(supplied):
    raw = bytearray(packed([('private-selected.json', supplied['selected'])]))
    central = raw.index(b'PK\x01\x02')
    name_size, extra_size = struct.unpack_from('<HH', raw, central + 28)
    assert extra_size == 0
    field = struct.pack('<HHQ', 1, 8, len(supplied['selected']))
    struct.pack_into('<I', raw, central + 24, 0xffffffff)
    struct.pack_into('<H', raw, central + 30, len(field))
    raw[central + 46 + name_size:central + 46 + name_size] = field
    end = raw.rfind(b'PK\x05\x06')
    size, = struct.unpack_from('<I', raw, end + 12)
    struct.pack_into('<I', raw, end + 12, size + len(field))
    with zipfile.ZipFile(io.BytesIO(raw)) as standard:
        assert standard.infolist()[0].file_size == len(supplied['selected'])
        assert standard.infolist()[0].extract_version == 20
    supplied['archive'].write_bytes(raw)
    supplied['value']['archive'] = {'sha256': digest(raw), 'size_bytes': len(raw)}
    supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('pin', [None, True, '', 'x' * 64, 'F' * 64, '0' * 63],
                         ids=['missing', 'bool', 'empty', 'nonhex', 'upper', 'short'])
def test_invalid_manifest_pin_rejected_before_io(supplied, monkeypatch, pin):
    monkeypatch.setattr(audit, 'read_bytes', lambda *a, **k: pytest.fail('Invalid pin accessed input'))
    assert_blocked(audit.verify(supplied['archive'], supplied['manifest'], expected_manifest_sha256=pin))


def test_wrong_manifest_pin(supplied):
    assert_blocked(verify(supplied, expected_manifest_sha256='0' * 64))


@pytest.mark.parametrize('path', ['/workspace/FIRMAVEX/private', 'evidence/windows-sandbox/private',
    'EVIDENCE\\WINDOWS-SANDBOX\\private', '../private', 'C:\\private:stream', '~/.private',
    '//host/private', 'NUL.txt'], ids=['original', 'protected', 'backslash-protected', 'parent',
                                      'alternate-stream', 'home', 'unc', 'device'])
def test_unsafe_input_spelling_rejected_before_io(supplied, monkeypatch, path):
    pin = digest(supplied['manifest'].read_bytes())
    monkeypatch.setattr(audit, 'read_bytes', lambda *a, **k: pytest.fail('Unsafe path accessed input'))
    result = audit.verify(path, supplied['manifest'], expected_manifest_sha256=pin)
    assert_blocked(result)
    assert path not in json.dumps(result)


def test_same_input_path_refused(supplied):
    pin = digest(supplied['manifest'].read_bytes())
    assert_blocked(audit.verify(supplied['manifest'], supplied['manifest'], expected_manifest_sha256=pin))


@pytest.mark.parametrize('which', ['archive', 'manifest'])
def test_symlink_input_refused_without_following_target(supplied, tmp_path, which):
    path = tmp_path / f'{which}-link'
    try:
        path.symlink_to(supplied[which])
    except (OSError, NotImplementedError):
        pytest.skip('Symlink creation unavailable; no privilege requested')
    supplied[which] = path
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('which', ['archive', 'manifest'])
def test_hardlink_input_refused(supplied, tmp_path, which):
    try:
        os.link(supplied[which], tmp_path / f'{which}-alias')
    except OSError:
        pytest.skip('Hardlink creation unavailable')
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('raw', [b'not json', b'[]', b'null', b'{}', b'{"x":1,"x":2}',
    b'{"x":NaN}', b'{"x":1e999}', b'\xff'],
    ids=['text', 'list', 'null', 'empty', 'duplicate', 'nonfinite', 'overflow-float', 'encoding'])
def test_malformed_manifest_refused(supplied, raw):
    supplied['manifest'].write_bytes(raw)
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('field,value', [('schema_version', True), ('schema_version', 2),
    ('kind', 'private-kind'), ('source', []), ('archive', []), ('complete_inventory', 1),
    ('members', []), ('members', {}), ('extra-private-field', 'private-value')],
    ids=['bool-schema', 'future-schema', 'kind', 'source', 'archive', 'bool-alias', 'empty', 'dict', 'extra'])
def test_unsupported_manifest_fields_refused(supplied, field, value):
    supplied['value'][field] = value; supplied['save']()
    result = verify(supplied)
    assert_blocked(result)
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('field,value', [('repository', 'private/repository'), ('revision', 'A' * 40),
    ('revision', True), ('run_id', 0), ('run_id', True), ('artifact_id', -1),
    ('artifact_id', '456'), ('extra', 'PRIVATE')],
    ids=['repository', 'upper-revision', 'bool-revision', 'zero-run', 'bool-run', 'negative-id', 'str-id', 'extra'])
def test_source_binding_fields_are_strict_and_not_echoed(supplied, field, value):
    supplied['value']['source'][field] = value; supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('field,value', [('sha256', 'F' * 64), ('sha256', True),
    ('size_bytes', -1), ('size_bytes', True), ('extra', 'PRIVATE')],
    ids=['upper-hash', 'bool-hash', 'negative-size', 'bool-size', 'extra'])
def test_archive_identity_fields_are_strict(supplied, field, value):
    supplied['value']['archive'][field] = value; supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('field,value', [('name', ''), ('name', '../private'), ('sha256', True),
    ('sha256', 'F' * 64), ('size_bytes', -1), ('size_bytes', True), ('extra', 'PRIVATE')],
    ids=['empty-name', 'unsafe-name', 'bool-hash', 'upper-hash', 'negative-size', 'bool-size', 'extra'])
def test_member_identity_fields_are_strict(supplied, field, value):
    supplied['value']['members'][0][field] = value; supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('case', ['archive-hash', 'archive-size', 'member-hash', 'member-size',
                                 'missing-member', 'duplicate-selection', 'case-alias-selection', 'complete-extra'])
def test_pin_and_inventory_mismatches_refused(supplied, case):
    value = supplied['value']
    if case == 'archive-hash': value['archive']['sha256'] = '0' * 64
    elif case == 'archive-size': value['archive']['size_bytes'] += 1
    elif case == 'member-hash': value['members'][0]['sha256'] = '0' * 64
    elif case == 'member-size': value['members'][0]['size_bytes'] += 1
    elif case == 'missing-member': value['members'][0]['name'] = 'absent.txt'
    elif case == 'duplicate-selection': value['members'].append(deepcopy(value['members'][0]))
    elif case == 'case-alias-selection':
        row = deepcopy(value['members'][0]); row['name'] = row['name'].upper(); value['members'].append(row)
    else: value['complete_inventory'] = True
    supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a\\b', 'a//b', './a', 'a/../b',
    'a:b', 'NUL.txt', 'file.', 'file ', 'a~1', 'evidence/windows-sandbox/never-open',
    'folder/EVIDENCE/WINDOWS-SANDBOX/never-open', 'a\x7fb'],
    ids=['parent', 'absolute', 'backslash', 'empty-part', 'dot', 'nested-parent', 'ads', 'device',
         'trailing-dot', 'trailing-space', 'alias', 'protected', 'nested-protected', 'control'])
def test_unselected_unsafe_zip_paths_refused_before_decompression(supplied, monkeypatch, name):
    supplied['replace']([('private-selected.json', supplied['selected']), (name, b'PRIVATE')])
    monkeypatch.setattr(audit, '_chunks', lambda *a, **k: pytest.fail('Unsafe entries were processed'))
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('rows', [
    [('same', b'a'), ('same', b'b')], [('same', b'a'), ('SAME', b'b')],
    [('node', b'a'), ('node/child', b'b')], [('node/child', b'b'), ('NODE', b'a')],
    [('node/', b''), ('node', b'a')], [('node/', b'not empty')],
], ids=['duplicate', 'case-alias', 'file-parent', 'late-file-parent', 'file-directory', 'directory-payload'])
def test_unsafe_entry_inventory_refused(supplied, rows):
    supplied['replace']([('private-selected.json', supplied['selected']), *rows])
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'socket', 'reparse'])
def test_special_zip_entries_refused(supplied, kind):
    entry = zipfile.ZipInfo('unsafe-entry')
    entry.create_system = 3
    modes = {'symlink': stat.S_IFLNK, 'fifo': stat.S_IFIFO, 'socket': stat.S_IFSOCK}
    entry.external_attr = ((modes[kind] | 0o600) << 16) if kind != 'reparse' else ((stat.S_IFREG | 0o600) << 16) | 0x400
    supplied['replace']([('private-selected.json', supplied['selected']), (entry, b'PRIVATE')])
    assert_blocked(verify(supplied))


def test_nul_name_truncation_is_rejected(supplied):
    data = packed([('private-selected.json', supplied['selected']), ('unsafeXentry', b'data')])
    assert data.count(b'unsafeXentry') == 2
    data = data.replace(b'unsafeXentry', b'unsafe\0entry')
    supplied['archive'].write_bytes(data)
    supplied['value']['archive'] = {'sha256': digest(data), 'size_bytes': len(data)}
    supplied['save']()
    assert_blocked(verify(supplied))


def test_crc_is_checked_even_for_unselected_members(supplied):
    raw = supplied['archive'].read_bytes()
    assert raw.count(b'other') >= 1
    # Alter stored payload, retaining the original CRC in both ZIP headers.
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo('other.txt')
    offset = info.header_offset
    name_size, extra_size = struct.unpack_from('<HH', raw, offset + 26)
    payload = offset + 30 + name_size + extra_size
    changed = bytearray(raw); changed[payload] ^= 1
    supplied['archive'].write_bytes(changed)
    supplied['value']['archive'] = {'sha256': digest(changed), 'size_bytes': len(changed)}
    supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('fault', ['truncated-advertised-size', 'trailing-compressed-data',
                                 'unterminated-deflate', 'concatenated-deflate'])
def test_actual_deflate_stream_must_match_declared_size_and_end(supplied, fault):
    # Synthetic draft-regression: ZipExtFile can silently stop at a forged
    # advertised file_size. Even repinned headers/CRC must not hide extra output.
    actual = b'abcde'
    compressed = deflated(actual)
    declared = actual
    if fault == 'truncated-advertised-size': declared = b'a'
    elif fault == 'trailing-compressed-data': compressed += b'junk'
    elif fault == 'unterminated-deflate': compressed = compressed[:-1]
    else: compressed += deflated(b'extra')
    raw = raw_member_zip(declared, compressed)
    supplied['value']['members'] = [{'name': 'crafted.txt', 'sha256': digest(declared), 'size_bytes': len(declared)}]
    set_archive_bytes(supplied, raw)
    assert_blocked(verify(supplied))


def test_actual_deflate_stream_valid_at_bounded_chunk_boundary(supplied, monkeypatch):
    data = b'abcdefghij'
    supplied['value']['members'] = [{'name': 'crafted.txt', 'sha256': digest(data), 'size_bytes': len(data)}]
    set_archive_bytes(supplied, raw_member_zip(data, deflated(data)))
    monkeypatch.setattr(audit, 'CHUNK', 2)
    assert verify(supplied)['status'] == 'integrity_matched'


@pytest.mark.parametrize('fault', ['none', 'crc', 'compressed-size', 'size'],
                         ids=['valid', 'invalid-crc', 'invalid-compressed-size', 'invalid-size'])
def test_nonseekable_writer_descriptor_is_validated(supplied, fault):
    class Nonseekable(io.BytesIO):
        def seekable(self): return False
        def seek(self, *args): raise io.UnsupportedOperation('Nonseekable synthetic writer')
    stream = Nonseekable()
    data = b'bounded descriptor payload'
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('crafted.txt', data)
    raw = bytearray(stream.getvalue())
    descriptor = raw.find(b'PK\x07\x08')
    assert descriptor > 0
    if fault != 'none':
        offset = descriptor + {'crc': 4, 'compressed-size': 8, 'size': 12}[fault]
        struct.pack_into('<I', raw, offset, struct.unpack_from('<I', raw, offset)[0] ^ 1)
    supplied['value']['members'] = [{'name': 'crafted.txt', 'sha256': digest(data), 'size_bytes': len(data)}]
    set_archive_bytes(supplied, raw)
    result = verify(supplied)
    if fault == 'none': assert result['status'] == 'integrity_matched'
    else: assert_blocked(result)


@pytest.mark.parametrize('fault', ['bad-zip', 'trailing', 'prefix', 'multidisk', 'zip64-sentinel', 'encrypted', 'local-name'])
def test_malformed_or_unsupported_zip_structure_refused(supplied, fault):
    raw = bytearray(supplied['archive'].read_bytes())
    end = raw.rfind(b'PK\x05\x06')
    if fault == 'bad-zip': raw = bytearray(b'not an archive')
    elif fault == 'trailing': raw.extend(b'PRIVATE-TRAILING')
    elif fault == 'prefix': raw = bytearray(b'PRIVATE-PREFIX') + raw
    elif fault == 'multidisk': struct.pack_into('<H', raw, end + 4, 1)
    elif fault == 'zip64-sentinel': struct.pack_into('<H', raw, end + 10, 0xffff)
    elif fault == 'encrypted':
        struct.pack_into('<H', raw, 6, 1)
        central = raw.find(b'PK\x01\x02'); struct.pack_into('<H', raw, central + 8, 1)
    else: raw[30] ^= 1
    supplied['archive'].write_bytes(raw)
    supplied['value']['archive'] = {'sha256': digest(raw), 'size_bytes': len(raw)}
    supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('field,offset,format,value', [
    ('method', 8, '<H', zipfile.ZIP_DEFLATED), ('flags', 6, '<H', 8),
    ('crc', 14, '<I', 0), ('compressed-size', 18, '<I', 1),
    ('size', 22, '<I', 1), ('zip64-version', 4, '<H', 45),
], ids=['method', 'flags', 'crc', 'compressed-size', 'size', 'zip64-version'])
def test_local_header_disagreement_is_rejected(supplied, field, offset, format, value):
    raw = bytearray(supplied['archive'].read_bytes())
    struct.pack_into(format, raw, offset, value)
    supplied['archive'].write_bytes(raw)
    supplied['value']['archive'] = {'sha256': digest(raw), 'size_bytes': len(raw)}
    supplied['save']()
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('fault', ['duplicate-offset', 'overlap'])
def test_duplicate_and_overlapping_local_offsets_are_rejected(supplied, fault):
    raw = bytearray(supplied['archive'].read_bytes())
    end = raw.rfind(b'PK\x05\x06')
    first = struct.unpack_from('<I', raw, end + 16)[0]
    name_size, extra_size, comment_size = struct.unpack_from('<HHH', raw, first + 28)
    second = first + 46 + name_size + extra_size + comment_size
    if fault == 'duplicate-offset':
        struct.pack_into('<I', raw, second + 42, 0)
    else:
        # Extend the first stored member's declared extent into the second
        # local header while keeping its local and central declarations equal.
        for offset in (18, 22, first + 20, first + 24):
            size = struct.unpack_from('<I', raw, offset)[0]
            struct.pack_into('<I', raw, offset, size + 2)
    supplied['archive'].write_bytes(raw)
    supplied['value']['archive'] = {'sha256': digest(raw), 'size_bytes': len(raw)}
    supplied['save']()
    assert_blocked(verify(supplied))


def test_bounded_central_directory_is_checked_before_zipfile_allocation(supplied, monkeypatch):
    monkeypatch.setattr(audit, 'MAX_CENTRAL', 1)
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **k: pytest.fail('Central bound checked too late'))
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('name', ['caf\u00e9.txt', 'cafe\u0301.txt'], ids=['composed', 'decomposed'])
def test_unicode_member_spellings_are_explicitly_unsupported(supplied, name):
    supplied['replace']([('private-selected.json', supplied['selected']), (name, b'not published')])
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('constant,limit', [('MAX_ARCHIVE', 1), ('MAX_MEMBER', 1),
    ('MAX_TOTAL', 1), ('MAX_MEMBERS', 1), ('MAX_SELECTED', 0), ('MAX_CENTRAL', 1)],
    ids=['archive', 'member', 'total', 'entries', 'selected', 'central'])
def test_fixed_resource_bounds_are_enforced(supplied, monkeypatch, constant, limit):
    monkeypatch.setattr(audit, constant, limit)
    assert_blocked(verify(supplied))


def test_high_ratio_is_rejected_without_materializing_large_domain(supplied):
    supplied['replace']([('private-selected.json', supplied['selected']), ('ratio.txt', b'x' * 100000)],
                         compression=zipfile.ZIP_DEFLATED)
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('constant', ['MAX_ARCHIVE', 'MAX_MANIFEST', 'MAX_MEMBER',
    'MAX_TOTAL', 'MAX_MEMBERS', 'MAX_SELECTED', 'MAX_CENTRAL', 'MAX_RATIO'])
def test_resource_bounds_include_the_exact_limit(supplied, monkeypatch, constant):
    raw = supplied['archive'].read_bytes()
    end = raw.rfind(b'PK\x05\x06')
    limits = {
        'MAX_ARCHIVE': len(raw), 'MAX_MANIFEST': supplied['manifest'].stat().st_size,
        'MAX_MEMBER': len(supplied['selected']), 'MAX_TOTAL': len(supplied['selected']) + 5,
        'MAX_MEMBERS': 2, 'MAX_SELECTED': 1,
        'MAX_CENTRAL': struct.unpack_from('<I', raw, end + 12)[0], 'MAX_RATIO': 1,
    }
    monkeypatch.setattr(audit, constant, limits[constant])
    assert verify(supplied)['status'] == 'integrity_matched'


def test_oversized_manifest_is_rejected_before_json_processing(supplied, monkeypatch):
    monkeypatch.setattr(audit, 'MAX_MANIFEST', supplied['manifest'].stat().st_size - 1)
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('method', [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA], ids=['bzip2', 'lzma'])
def test_unsupported_compression_refused(supplied, method):
    supplied['replace']([('private-selected.json', supplied['selected'])], compression=method)
    assert_blocked(verify(supplied))


def test_cancellation_before_read_propagates(supplied, monkeypatch):
    pin = digest(supplied['manifest'].read_bytes())
    cancelled = threading.Event(); cancelled.set()
    monkeypatch.setattr(audit, 'read_bytes', lambda *a, **k: pytest.fail('Cancelled input read'))
    with pytest.raises(KeyboardInterrupt):
        audit.verify(supplied['archive'], supplied['manifest'], expected_manifest_sha256=pin, cancel_event=cancelled)


def test_cancellation_during_member_decompression_propagates(supplied, monkeypatch):
    cancelled = threading.Event()
    original = audit._chunks
    calls = []
    def chunks(*args, **kwargs):
        for chunk in original(*args, **kwargs):
            calls.append(len(chunk)); cancelled.set()
            yield chunk
    monkeypatch.setattr(audit, '_chunks', chunks)
    with pytest.raises(KeyboardInterrupt):
        verify(supplied, cancel_event=cancelled)
    assert calls


class SyntheticControl(BaseException):
    pass


@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, SyntheticControl], ids=['keyboard', 'exit', 'other-control'])
def test_read_control_flow_identity_propagates(supplied, monkeypatch, factory):
    control = factory('PRIVATE-CONTROL')
    def fail(*args, **kwargs): raise control
    monkeypatch.setattr(audit, 'read_bytes', fail)
    with pytest.raises(type(control)) as caught:
        verify(supplied)
    assert caught.value is control


@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, SyntheticControl], ids=['keyboard', 'exit', 'other-control'])
@pytest.mark.parametrize('stage', ['members', 'final-read'])
def test_late_control_flow_identity_propagates(supplied, monkeypatch, factory, stage):
    control = factory('PRIVATE-CONTROL')
    if stage == 'members':
        def fail(*args, **kwargs): raise control
        monkeypatch.setattr(audit, '_members', fail)
    else:
        original = audit.read_bytes
        calls = []
        def read(*args, **kwargs):
            calls.append(True)
            if len(calls) == 3: raise control
            return original(*args, **kwargs)
        monkeypatch.setattr(audit, 'read_bytes', read)
    with pytest.raises(type(control)) as caught:
        verify(supplied)
    assert caught.value is control


@pytest.mark.parametrize('factory', [OSError, ValueError, TypeError], ids=['os', 'value', 'type'])
def test_ordinary_failure_output_is_sanitized_without_partial_success(supplied, monkeypatch, factory):
    def fail(*args, **kwargs): raise factory('PRIVATE-PATH-TOKEN')
    monkeypatch.setattr(audit, '_members', fail)
    result = verify(supplied)
    assert_blocked(result)
    assert 'PRIVATE' not in json.dumps(result)
    assert 'all_member_crc_checked' not in result and 'members' not in result


@pytest.mark.parametrize('which', ['archive', 'manifest'])
def test_missing_input_has_no_partial_success(supplied, which):
    pin = digest(supplied['manifest'].read_bytes())
    supplied[which].unlink()
    result = audit.verify(supplied['archive'], supplied['manifest'], expected_manifest_sha256=pin)
    assert_blocked(result)
    assert 'members' not in result


def test_cancellation_during_final_consistency_read_propagates(supplied, monkeypatch):
    cancelled = threading.Event()
    original = audit.read_bytes
    calls = []
    def read(path, *args, **kwargs):
        calls.append(Path(path))
        if len(calls) == 3:
            cancelled.set()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(audit, 'read_bytes', read)
    with pytest.raises(KeyboardInterrupt):
        verify(supplied, cancel_event=cancelled)
    assert len(calls) == 3


@pytest.mark.parametrize('which', ['archive', 'manifest'])
@pytest.mark.parametrize('replacement', [False, True], ids=['same-size-rewrite', 'same-bytes-replacement'])
def test_final_consistency_check_rejects_changes_after_member_processing(supplied, monkeypatch, which, replacement):
    original = audit._members
    target = supplied[which]
    before = target.stat()
    initial = target.read_bytes()
    def members(*args, **kwargs):
        result = original(*args, **kwargs)
        if replacement:
            fresh = target.with_name('replacement.tmp')
            fresh.write_bytes(initial)
            fresh.replace(target)
        else:
            changed = bytearray(initial); changed[-1] ^= 1
            target.write_bytes(changed)
        # Restoring ordinary timestamps does not make changed bytes or a
        # replacement identity a consistent capture.
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        return result
    monkeypatch.setattr(audit, '_members', members)
    assert_blocked(verify(supplied))


@pytest.mark.parametrize('which', ['archive', 'manifest'])
def test_input_change_after_initial_read_is_rejected(supplied, monkeypatch, which):
    original = audit.read_bytes
    target = supplied[which]
    changed = []
    def read(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if Path(path) == target and not changed:
            changed.append(True)
            target.write_bytes(result + b' ')
        return result
    monkeypatch.setattr(audit, 'read_bytes', read)
    assert_blocked(verify(supplied))
    assert changed


@pytest.mark.parametrize('which', ['archive', 'manifest'])
def test_input_disappearance_after_initial_read_is_rejected(supplied, monkeypatch, which):
    original = audit.read_bytes
    target = supplied[which]
    vanished = []
    def read(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if Path(path) == target and not vanished:
            vanished.append(True); target.unlink()
        return result
    monkeypatch.setattr(audit, 'read_bytes', read)
    assert_blocked(verify(supplied))
    assert vanished


@pytest.mark.parametrize('success', [True, False], ids=['matched', 'blocked'])
def test_cli_exit_and_json_summary_are_sanitized(supplied, capsys, success):
    pin = digest(supplied['manifest'].read_bytes()) if success else '0' * 64
    code = audit.main(['--archive', str(supplied['archive']), '--manifest', str(supplied['manifest']),
                       '--manifest-sha256', pin])
    captured = capsys.readouterr()
    assert code == (0 if success else 2)
    report = json.loads(captured.out)
    assert report['status'] == ('integrity_matched' if success else 'blocked')
    assert 'private-' not in captured.out + captured.err
    assert str(supplied['archive'].parent) not in captured.out + captured.err


def test_invalid_cli_arguments_are_sanitized(capsys):
    assert audit.main(['--PRIVATE-UNSUPPORTED-OPTION']) == 2
    captured = capsys.readouterr()
    assert_blocked(json.loads(captured.out))
    assert 'PRIVATE' not in captured.out + captured.err
