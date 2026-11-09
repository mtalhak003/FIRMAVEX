"""Synthetic PE metadata only; no native or publisher qualification evidence."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from tools import windows_candidate_closure as closure


def pe(*names, delay=False):
    """Invented non-executable PE header/section fixture, not actual firmware."""
    data = bytearray(2048)
    data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', data, 68, 0x8664, 1, 0, 0, 0, 240, 0)
    optional = 88
    struct.pack_into('<H', data, optional, 0x20b)
    struct.pack_into('<I', data, optional + 60, 512)
    struct.pack_into('<I', data, optional + 108, 16)
    struct.pack_into('<IIII', data, optional + 240 + 8, 1536, 4096, 1536, 512)
    if delay: struct.pack_into('<II', data, optional + 112 + 13*8, 4096, 32)
    if names:
        struct.pack_into('<II', data, optional + 120, 4096, 20*(len(names)+1))
        offset = 512 + 20*(len(names)+1)
        for index, name in enumerate(names):
            encoded = name.encode() + b'\0'
            struct.pack_into('<IIIII', data, 512 + index*20, 0, 0, 0, 4096 + offset - 512, 0)
            data[offset:offset+len(encoded)] = encoded
            offset += len(encoded)
    return bytes(data)


def test_parser_preserves_actual_import_names_as_deterministic_casefolded_set():
    assert closure.imports(pe('KERNEL32.dll', 'libstdc++-6.dll', 'kernel32.DLL')) == [
        'kernel32.dll', 'libstdc++-6.dll']
    assert closure.imports(pe()) == []


def test_empty_bss_raw_extent_is_supported():
    data = bytearray(pe())
    struct.pack_into('<H', data, 70, 2)
    struct.pack_into('<IIII', data, 88+240+40+8, 4096, 8192, 0, 0)
    assert closure.imports(bytes(data)) == []


@pytest.mark.parametrize('fault', ['dos', 'pe', 'offset', 'machine', 'magic', 'sections', 'optional',
    'directories', 'headers', 'raw', 'rva', 'size', 'delay', 'name', 'unterminated', 'descriptor'])
def test_parser_rejects_unsupported_or_malformed_headers(fault):
    data = bytearray(pe('safe.dll'))
    if fault == 'dos': data[0] = 0
    elif fault == 'pe': data[64] = 0
    elif fault == 'offset': struct.pack_into('<I', data, 60, 2**32-1)
    elif fault == 'machine': struct.pack_into('<H', data, 68, 0x14c)
    elif fault == 'magic': struct.pack_into('<H', data, 88, 0x10b)
    elif fault == 'sections': struct.pack_into('<H', data, 70, 97)
    elif fault == 'optional': struct.pack_into('<H', data, 84, 112)
    elif fault == 'directories': struct.pack_into('<I', data, 88+108, 17)
    elif fault == 'headers': struct.pack_into('<I', data, 88+60, 64)
    elif fault == 'raw': struct.pack_into('<I', data, 88+240+20, 2**32-1)
    elif fault == 'rva': struct.pack_into('<I', data, 88+120, 2**32-1)
    elif fault == 'size': struct.pack_into('<I', data, 88+124, 19)
    elif fault == 'delay': data = bytearray(pe(delay=True))
    elif fault == 'name': data = bytearray(pe('../bad.dll'))
    elif fault == 'unterminated': data[552:716] = b'x'*164
    elif fault == 'descriptor': struct.pack_into('<I', data, 88+124, 20)
    with pytest.raises((ValueError, UnicodeError)): closure.imports(bytes(data))


@pytest.fixture
def fixture(tmp_path):
    vendor = tmp_path/'vendor'; vendor.mkdir()
    system = tmp_path/'system'; system.mkdir()
    files = {'app.exe': pe('helper.dll', 'kernel32.dll'), 'helper.dll': pe('kernel32.dll')}
    systems = {'kernel32.dll': pe()}
    def table(directory, entries):
        result = {}
        for name, content in entries.items():
            (directory/name).write_bytes(content)
            result[name] = {'sha256': hashlib.sha256(content).hexdigest(), 'size_bytes': len(content)}
        return result
    manifest = tmp_path/'manifest.json'
    spec = {'schema_version': 1, 'roots': ['app.exe'], 'vendor': table(vendor, files), 'system': table(system, systems)}
    def save():
        manifest.write_text(json.dumps(spec, sort_keys=True))
        return hashlib.sha256(manifest.read_bytes()).hexdigest()
    return vendor, system, manifest, spec, save


def execute(fixture):
    vendor, system, manifest, _, save = fixture
    return closure.audit(vendor, system, manifest, save())


def test_audit_reads_actual_files_is_deterministic_read_only_and_keeps_limits_explicit(fixture):
    vendor, system, manifest, spec, save = fixture
    digest = save(); before = {p:p.read_bytes() for root in (vendor, system) for p in root.iterdir()}
    result = closure.audit(vendor, system, manifest, digest)
    assert result == closure.audit(vendor, system, manifest, digest)
    assert result['status'] == 'verified_static_import_graph'
    assert result['imports'] == {'app.exe': ['helper.dll', 'kernel32.dll'],
                                 'helper.dll': ['kernel32.dll'], 'kernel32.dll': []}
    assert result['production_qualified'] is False and result['candidate_only'] is True
    assert result['package_ownership_authenticated'] is False
    assert result['complete_dynamic_dll_closure_verified'] is False
    assert result['atomic_snapshot'] is False and result['firmware_executed'] is False
    assert {p:p.read_bytes() for root in (vendor, system) for p in root.iterdir()} == before
    assert all(str(vendor) not in json.dumps(value) for value in result.values())


@pytest.mark.parametrize('fault', ['digest', 'missing-file', 'unlisted-dll', 'changed', 'bad-size', 'bool-size',
    'schema', 'root', 'duplicate-root', 'duplicate-name', 'ambiguous', 'traversal', 'unsafe-extension', 'delay'])
def test_audit_rejects_missing_ambiguous_unsafe_or_changed_inputs(fixture, fault):
    vendor, system, manifest, spec, save = fixture
    if fault == 'missing-file': (vendor/'helper.dll').unlink()
    elif fault == 'unlisted-dll': del spec['vendor']['helper.dll']
    elif fault == 'changed': (vendor/'helper.dll').write_bytes(b'changed')
    elif fault == 'bad-size': spec['vendor']['app.exe']['size_bytes'] = 1
    elif fault == 'bool-size': spec['vendor']['app.exe']['size_bytes'] = True
    elif fault == 'schema': spec['schema_version'] = True
    elif fault == 'root': spec['roots'] = ['missing.exe']
    elif fault == 'duplicate-root': spec['roots'] = ['app.exe', 'app.exe']
    elif fault == 'duplicate-name': spec['vendor']['APP.EXE'] = spec['vendor']['app.exe']
    elif fault == 'ambiguous': spec['system']['helper.dll'] = spec['vendor']['helper.dll']
    elif fault == 'traversal': spec['vendor']['../bad.dll'] = spec['vendor']['helper.dll']
    elif fault == 'unsafe-extension': spec['vendor']['script.py'] = spec['vendor']['helper.dll']
    elif fault == 'delay':
        content = pe(delay=True); (vendor/'helper.dll').write_bytes(content)
        spec['vendor']['helper.dll'] = {'sha256':hashlib.sha256(content).hexdigest(),'size_bytes':len(content)}
    digest = save()
    if fault == 'digest': digest = '0'*64
    with pytest.raises((ValueError, FileNotFoundError)):
        closure.audit(vendor, system, manifest, digest)


def test_actual_unlisted_vendor_shadow_of_system_dll_is_rejected(fixture):
    vendor, _, _, _, _ = fixture
    (vendor/'kernel32.dll').write_bytes(pe())
    with pytest.raises(ValueError, match='Ambiguous'): execute(fixture)


@pytest.mark.parametrize('boundary', ['MAX_FILE', 'MAX_TOTAL', 'MAX_FILES', 'MAX_EDGES'])
def test_resource_boundaries_fail_closed(fixture, monkeypatch, boundary):
    monkeypatch.setattr(closure, boundary, 1)
    with pytest.raises(ValueError): execute(fixture)


def test_observable_file_change_during_audit_is_rejected(fixture, monkeypatch):
    vendor, _, _, _, _ = fixture
    original = closure.imports
    def changed(data):
        result = original(data)
        (vendor/'app.exe').write_bytes(b'changed during processing')
        return result
    monkeypatch.setattr(closure, 'imports', changed)
    with pytest.raises(ValueError, match='changed during audit'): execute(fixture)


def test_manifest_change_during_audit_is_rejected(fixture, monkeypatch):
    _, _, manifest, _, _ = fixture
    original = closure.imports
    def changed(data):
        manifest.write_text('{}')
        return original(data)
    monkeypatch.setattr(closure, 'imports', changed)
    with pytest.raises(ValueError, match='Manifest changed'): execute(fixture)


def test_observable_directory_change_during_audit_is_rejected(fixture, monkeypatch):
    vendor, _, _, _, _ = fixture
    original = closure.imports
    def changed(data):
        (vendor/'new.dll').write_bytes(pe())
        return original(data)
    monkeypatch.setattr(closure, 'imports', changed)
    with pytest.raises(ValueError, match='directory inventory changed'): execute(fixture)


@pytest.mark.skipif(os.name == 'nt', reason='Symlink construction privileges are platform-specific')
def test_unsafe_linked_dll_is_rejected(fixture):
    vendor, _, _, _, _ = fixture
    dll = vendor/'helper.dll'; other = vendor/'payload'; dll.rename(other); dll.symlink_to(other)
    with pytest.raises(ValueError, match='Symlink'): execute(fixture)


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_control_flow_is_not_converted_to_success_or_ordinary_error(fixture, monkeypatch, control):
    def interrupt(*args): raise control('original interruption')
    monkeypatch.setattr(closure, 'imports', interrupt)
    with pytest.raises(control, match='original interruption'): execute(fixture)


def test_cli_rejection_is_nonzero_and_omits_private_paths(fixture):
    vendor, system, manifest, _, save = fixture; save()
    result = subprocess.run([sys.executable, '-m', 'tools.windows_candidate_closure',
        '--vendor-bin', str(vendor), '--system-directory', str(system), '--manifest', str(manifest),
        '--expected-manifest-sha256', '0'*64], cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {'candidate_only':True, 'production_qualified':False,
                                         'status':'rejected', 'error_type':'ValueError'}
    assert str(vendor) not in result.stdout + result.stderr
