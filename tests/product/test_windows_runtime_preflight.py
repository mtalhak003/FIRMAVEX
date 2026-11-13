"""Synthetic file/receipt checks; never native runtime or signing qualification."""

import builtins
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import random
import socket
import struct
import subprocess
from types import SimpleNamespace
import urllib.request

import pytest

from tools import windows_runtime_preflight as preflight


def digest(data):
    return hashlib.sha256(data).hexdigest()


def synthetic_pe(*imports, certificate=False, architecture='x64'):
    """Invented PE metadata with no executable guest or host program."""
    data = bytearray(2048)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    optional_size = 240 if architecture == 'x64' else 224
    directory_base = 112 if architecture == 'x64' else 96
    struct.pack_into('<HHIIIHH', data, 68,
                     0x8664 if architecture == 'x64' else 0x14c,
                     1, 0, 0, 0, optional_size, 0)
    optional = 88
    struct.pack_into('<H', data, optional, 0x20b if architecture == 'x64' else 0x10b)
    struct.pack_into('<I', data, optional + 60, 512)
    struct.pack_into('<I', data, optional + directory_base - 4, 16)
    struct.pack_into('<IIII', data, optional + optional_size + 8, 1536, 4096, 1536, 512)
    if imports:
        struct.pack_into('<II', data, optional + directory_base + 8,
                         4096, 20 * (len(imports) + 1))
        offset = 512 + 20 * (len(imports) + 1)
        for index, name in enumerate(imports):
            encoded = name.encode('ascii') + b'\0'
            struct.pack_into('<IIIII', data, 512 + index * 20,
                             0, 0, 0, 4096 + offset - 512, 0)
            data[offset:offset + len(encoded)] = encoded
            offset += len(encoded)
    if certificate:
        struct.pack_into('<II', data, optional + directory_base + 4 * 8, len(data), 16)
        data.extend(struct.pack('<IHH', 16, 0x200, 2) + b'FAKECERT')
    return bytes(data)


@pytest.fixture
def sample(tmp_path):
    qemu = tmp_path / 'private-qemu.exe'
    gdb = tmp_path / 'private-gdb.exe'
    qemu.write_bytes(synthetic_pe('helper.dll'))
    gdb.write_bytes(synthetic_pe())
    spec = {'schema_version': 1,
            'artifacts': {'qemu': {'path': str(qemu)}, 'gdb': {'path': str(gdb)}}}
    manifest = tmp_path / 'private-manifest.json'

    def save():
        manifest.write_text(json.dumps(spec, sort_keys=True))
        return manifest

    return {'qemu': qemu, 'gdb': gdb, 'spec': spec, 'manifest': manifest,
            'save': save, 'root': tmp_path}


def run(sample):
    return preflight.preflight(sample['save']())


def receipt(sample, name, value):
    path = sample['root'] / (name + '.json')
    path.write_text(json.dumps(value, sort_keys=True))
    sample['spec'].setdefault('receipts', {})[name] = {
        'path': str(path), 'sha256': digest(path.read_bytes())}
    return path


def observations(sample):
    return {'schema_version': 1, 'tools': {
        'qemu': {'sha256': digest(sample['qemu'].read_bytes()),
                 'version': 'QEMU emulator version 11.1.2', 'mps2_an385': True},
        'gdb': {'sha256': digest(sample['gdb'].read_bytes()),
                'version': 'GNU gdb (GDB) 18.1', 'arm': True,
                'python_hashlib_marker': 'FIRMAVEX_GDB_CAPABILITY_V1=' + digest(b'probe')}}}


def all_nodes(value):
    yield value
    if type(value) is dict:
        for child in value.values():
            yield from all_nodes(child)
    elif type(value) is list:
        for child in value:
            yield from all_nodes(child)


def forbid_activity(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Read-only preflight attempted execution, network or a write')

    for name in ('run', 'Popen', 'call', 'check_call', 'check_output'):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    for name in ('write_bytes', 'write_text', 'touch', 'mkdir', 'unlink', 'rename', 'replace'):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ('iterdir', 'glob', 'rglob'):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ('scandir', 'walk', 'listdir'):
        monkeypatch.setattr(os, name, forbidden)
    original_open = builtins.open
    original_io_open = io.open
    original_os_open = os.open

    def only_read_open(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+'), mode
        return original_open(file, mode, *args, **kwargs)

    def only_read_os_open(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return original_os_open(path, flags, *args, **kwargs)

    def only_read_io_open(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+'), mode
        return original_io_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', only_read_open)
    monkeypatch.setattr(io, 'open', only_read_io_open)
    monkeypatch.setattr(os, 'open', only_read_os_open)


def assert_inert(report):
    assert report['read_only'] is True
    for key in ('firmware_executed', 'tools_executed', 'production_admission_evaluated',
                'production_qualified', 'atomic_snapshot', 'concurrent_path_isolation'):
        assert report[key] is False
    for name in ('native_capabilities', 'publisher_trust', 'dynamic_dll_closure',
                 'license_completeness', 'authenticode_trust', 'application_signing_coverage',
                 'qualification', 'access_containment'):
        assert report['checks'][name]['state'] == 'not_assessed'
    assert report['checks']['access_containment']['code'] == 'concurrent_path_redirection_not_prevented'
    counts = {state: 0 for state in preflight.STATES}
    for node in all_nodes(report):
        if type(node) is dict and node.get('state') in counts:
            counts[node['state']] += 1
    assert report['counts'] == counts


def test_reads_actual_bytes_without_execution_network_writes_or_path_disclosure(sample, monkeypatch):
    manifest = sample['save']()
    expected = {path: path.read_bytes() for path in (manifest, sample['qemu'], sample['gdb'])}
    forbid_activity(monkeypatch)
    first = preflight.preflight(manifest)
    assert first == preflight.preflight(manifest)
    assert_inert(first)
    assert first['artifacts']['qemu']['file']['sha256'] == digest(expected[sample['qemu']])
    assert first['artifacts']['gdb']['file']['sha256'] == digest(expected[sample['gdb']])
    assert first['checks']['capture'] == {'state': 'verified', 'code': 'stable_observed_not_atomic'}
    assert first['checks']['manifest']['state'] == 'not_assessed'
    serialized = json.dumps(first)
    assert str(sample['root']) not in serialized
    assert 'private-qemu.exe' not in serialized and 'private-gdb.exe' not in serialized
    assert {path: path.read_bytes() for path in expected} == expected


def test_synthetic_runtime_mismatches_fixed_production_pins_and_is_never_admitted(sample):
    report = run(sample)
    assert_inert(report)
    assert report['status'] == 'mismatch'
    for role in ('qemu', 'gdb'):
        assert report['artifacts'][role]['identity']['state'] == 'mismatch'
        assert report['artifacts'][role]['version']['state'] == 'not_assessed'
    assert report['required_dlls']['helper.dll']['state'] == 'missing'


def test_expected_application_digest_is_comparison_only_and_preserves_signing_gap(sample):
    app = sample['root'] / 'sensitive-app.exe'
    data = synthetic_pe(certificate=True)
    app.write_bytes(data)
    sample['spec']['artifacts']['application'] = {'path': str(app), 'sha256': digest(data)}
    report = run(sample)
    record = report['artifacts']['application']
    assert record['identity']['state'] == 'verified'
    assert record['pe'] == {'state': 'verified', 'code': 'pe_header_structure_only', 'architecture': 'x64'}
    assert record['certificate_table'] == {'state': 'verified', 'code': 'certificate_table_structure_only', 'entries': 1}
    assert record['signing'] == {'state': 'not_assessed', 'code': 'authenticode_trust_not_verified'}
    assert_inert(report)


@pytest.mark.parametrize('role', ['installer', 'uninstaller'])
def test_pe32_x86_installer_signing_metadata_is_supported_without_trust_approval(sample, role):
    path = sample['root'] / (role + '.exe')
    data = synthetic_pe(certificate=True, architecture='x86')
    path.write_bytes(data)
    sample['spec']['artifacts'][role] = {'path': str(path), 'sha256': digest(data)}
    report = run(sample)
    record = report['artifacts'][role]
    assert record['identity']['state'] == 'verified'
    assert record['pe'] == {'state': 'verified', 'code': 'pe_header_structure_only', 'architecture': 'x86'}
    assert record['certificate_table']['state'] == 'verified'
    assert record['signing'] == {'state': 'not_assessed', 'code': 'authenticode_trust_not_verified'}
    assert_inert(report)


@pytest.mark.parametrize('role', ['qemu', 'gdb'])
def test_pe32_runtime_does_not_become_a_supported_x64_profile(sample, role):
    sample[role].write_bytes(synthetic_pe(architecture='x86'))
    report = run(sample)
    record = report['artifacts'][role]
    assert record['pe']['architecture'] == 'x86'
    assert record['imports']['state'] == 'blocked'
    assert record['identity']['state'] == 'mismatch'
    assert record['version']['state'] == 'not_assessed'
    assert report['status'] == 'blocked'
    assert_inert(report)


@pytest.mark.parametrize('role', ['application', 'worker', 'installer', 'uninstaller'])
def test_each_application_signing_role_is_independent_and_missing_by_default(sample, role):
    assert run(sample)['artifacts'][role]['file']['state'] == 'missing'
    artifact = sample['root'] / (role + '.exe')
    artifact.write_bytes(synthetic_pe())
    sample['spec']['artifacts'][role] = {'path': str(artifact), 'sha256': '0' * 64}
    record = run(sample)['artifacts'][role]
    assert record['file']['state'] == 'verified'
    assert record['identity']['state'] == 'mismatch'
    assert record['signing']['state'] == 'missing'


def test_companions_are_explicit_bound_identities_not_complete_loader_closure(sample):
    companion = sample['root'] / 'helper.dll'
    companion.write_bytes(synthetic_pe('KERNEL32.dll'))
    sample['spec']['companions'] = [{'path': str(companion), 'sha256': digest(companion.read_bytes())}]
    report = run(sample)
    assert report['required_dlls']['helper.dll']['state'] == 'verified'
    assert report['required_dlls']['helper.dll']['artifact'] == 'companion_001'
    assert report['required_dlls']['kernel32.dll']['state'] == 'missing'
    assert report['artifacts']['companion_001']['signing']['state'] == 'missing'
    assert report['checks']['dynamic_dll_closure']['state'] == 'not_assessed'
    assert str(companion) not in json.dumps(report)


def test_relative_descriptors_resolve_against_manifest_without_path_search(sample, monkeypatch):
    sample['spec']['artifacts'] = {name: {'path': path.name}
                                   for name, path in [('qemu', sample['qemu']), ('gdb', sample['gdb'])]}
    monkeypatch.setenv('PATH', str(sample['root'] / 'DO-NOT-SEARCH'))
    report = run(sample)
    assert report['artifacts']['qemu']['file']['sha256'] == digest(sample['qemu'].read_bytes())


@pytest.mark.parametrize('role', ['qemu', 'gdb'])
def test_runtime_descriptor_cannot_override_production_digest(sample, role):
    sample['spec']['artifacts'][role]['sha256'] = digest(sample[role].read_bytes())
    report = run(sample)
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {}


def test_manifest_digest_pin_is_optional_integrity_not_authentication(sample, monkeypatch):
    manifest = sample['save']()
    expected = digest(manifest.read_bytes())
    report = preflight.preflight(manifest, expected_manifest_sha256=expected)
    assert report['checks']['manifest']['state'] == 'verified'
    assert report['checks']['manifest']['code'] == 'manifest_integrity_only'
    assert_inert(report)
    original = preflight.read_bytes
    def manifest_only(path, maximum):
        assert Path(path) == manifest, 'mismatch must not inspect artifact files'
        return original(path, maximum)
    monkeypatch.setattr(preflight, 'read_bytes', manifest_only)
    report = preflight.preflight(manifest, expected_manifest_sha256='0' * 64)
    assert report['checks']['manifest']['state'] == 'mismatch'
    assert report['artifacts'] == {}


@pytest.mark.parametrize('value', [True, 12, 'ABCDEF' * 10, 'a' * 63, 'g' * 64],
                         ids=['bool', 'integer', 'uppercase', 'short', 'nonhex'])
def test_invalid_expected_manifest_digest_is_sanitized_blocked(sample, value):
    report = preflight.preflight(sample['save'](), expected_manifest_sha256=value)
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {}


@pytest.mark.parametrize('fault', ['schema-bool', 'schema-future', 'unknown-root', 'unknown-role',
    'artifact-list', 'descriptor-list', 'unknown-field', 'path-bool', 'receipt-name', 'companions-dict'])
def test_manifest_schema_and_exact_types_fail_closed(sample, fault):
    spec = sample['spec']
    if fault == 'schema-bool': spec['schema_version'] = True
    elif fault == 'schema-future': spec['schema_version'] = 2
    elif fault == 'unknown-root': spec['secret'] = 'PRIVATE-CREDENTIAL'
    elif fault == 'unknown-role': spec['artifacts']['arbitrary'] = {'path': '/not/inspected'}
    elif fault == 'artifact-list': spec['artifacts'] = []
    elif fault == 'descriptor-list': spec['artifacts']['qemu'] = []
    elif fault == 'unknown-field': spec['artifacts']['qemu']['command'] = 'MUST-NOT-RUN'
    elif fault == 'path-bool': spec['artifacts']['qemu']['path'] = True
    elif fault == 'receipt-name': spec['receipts'] = {'unknown': {'path': '/not/inspected'}}
    elif fault == 'companions-dict': spec['companions'] = {}
    report = run(sample)
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {}
    assert 'PRIVATE-CREDENTIAL' not in json.dumps(report)


@pytest.mark.parametrize(('payload', 'code'), [
    (b'{', 'unsafe_malformed_oversized_or_inconsistent_input'),
    (b'{"schema_version":1,"schema_version":1,"artifacts":{}}', 'duplicate_json_field'),
    (b'{"schema_version":NaN,"artifacts":{}}', 'nonfinite_json'),
    (b'[' * 20 + b'0' + b']' * 20, 'json_complexity_bound'),
    (b'\xff', 'unsafe_malformed_oversized_or_inconsistent_input')],
    ids=['truncated', 'duplicate', 'nonfinite', 'depth', 'encoding'])
def test_malformed_manifest_is_fixed_code_without_echoing_input(sample, payload, code):
    sample['manifest'].write_bytes(payload)
    report = preflight.preflight(sample['manifest'])
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == code


@pytest.mark.parametrize('value', [
    '/workspace/FIRMAVEX/evidence-not-read.bin',
    'evidence/windows-sandbox/NEVER-READ.bin',
    'EVIDENCE/WINDOWS-SANDBOX/NEVER-READ.bin',
    r'evidence\windows-sandbox\NEVER-READ.bin',
    'evidence/./windows-sandbox/NEVER-READ.bin',
    '../escape.exe', '~/.credentials', '//host/share/file.exe',
    r'C:\private\file.exe:stream', 'control\nname.exe',
], ids=['original', 'protected', 'protected-case', 'protected-windows', 'protected-dot',
        'parent', 'tilde', 'unc', 'ads', 'control'])
def test_unsafe_artifact_path_is_rejected_before_any_artifact_access(sample, monkeypatch, value):
    sample['spec']['artifacts']['qemu']['path'] = value
    manifest = sample['save']()
    original = preflight.read_bytes
    calls = []
    def manifest_only(path, maximum):
        calls.append(path)
        assert Path(path) == manifest, 'unsafe descriptor must not reach filesystem helpers'
        return original(path, maximum)
    monkeypatch.setattr(preflight, 'read_bytes', manifest_only)
    report = preflight.preflight(manifest)
    assert report['status'] == 'blocked'
    assert calls == [manifest]
    assert 'NEVER-READ' not in json.dumps(report)


def test_protected_manifest_path_is_refused_before_any_filesystem_operation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Protected path reached filesystem')
    monkeypatch.setattr(preflight, 'read_bytes', forbidden)
    monkeypatch.setattr(Path, 'lstat', forbidden)
    monkeypatch.setattr(Path, 'stat', forbidden)
    report = preflight.preflight('evidence/windows-sandbox/DO-NOT-ACCESS.json')
    assert report['status'] == 'blocked'
    assert 'DO-NOT-ACCESS' not in json.dumps(report)


@pytest.mark.parametrize('value', [
    'evidence./windows-sandbox/NEVER-READ.bin',
    'evidence /windows-sandbox/NEVER-READ.bin',
    'evidence/windows-sandbox./NEVER-READ.bin',
    'evidence/windows-sandbox /NEVER-READ.bin',
    'EVIDEN~1/WINDOW~1/NEVER-READ.bin',
    'NUL.exe', 'subdir/CON', 'COM1.dll',
], ids=['parent-dot', 'parent-space', 'child-dot', 'child-space', 'short-alias',
        'device-nul', 'device-con', 'device-com'])
def test_windows_alias_spellings_are_rejected_before_any_read(monkeypatch, value):
    def forbidden(*args, **kwargs): raise AssertionError('Alias reached filesystem')
    monkeypatch.setattr(preflight, 'read_bytes', forbidden)
    report = preflight.preflight(value)
    assert report['status'] == 'blocked'
    assert 'NEVER-READ' not in json.dumps(report)


@pytest.mark.parametrize('fault', ['same-path', 'case-path', 'bad-companion-name', 'companion-case'])
def test_duplicate_and_unsafe_companion_declarations_are_blocked(sample, fault):
    if fault == 'same-path': sample['spec']['artifacts']['gdb']['path'] = str(sample['qemu'])
    elif fault == 'case-path': sample['spec']['artifacts']['gdb']['path'] = str(sample['qemu']).upper()
    elif fault == 'bad-companion-name': sample['spec']['companions'] = [{'path': 'not-a-dll.exe'}]
    else: sample['spec']['companions'] = [{'path': 'helper.dll'}, {'path': 'other/HELPER.DLL'}]
    assert run(sample)['status'] == 'blocked'


def test_missing_manifest_and_missing_artifact_are_distinguished(sample):
    report = preflight.preflight(sample['root'] / 'missing.json')
    assert report['status'] == 'missing'
    assert report['checks']['capture']['code'] == 'manifest_not_found'
    sample['spec']['artifacts']['qemu']['path'] = str(sample['root'] / 'missing.exe')
    report = run(sample)
    assert report['artifacts']['qemu']['file'] == {'state': 'missing', 'code': 'file_not_found'}
    assert report['artifacts']['gdb']['file']['state'] == 'verified'


def test_os_error_details_never_escape_report(sample, monkeypatch):
    manifest = sample['save']()
    original = preflight.read_bytes
    def fail(path, maximum):
        if Path(path) == sample['qemu']:
            raise PermissionError('Bearer SECRET-TOKEN at /home/private/account')
        return original(path, maximum)
    monkeypatch.setattr(preflight, 'read_bytes', fail)
    report = preflight.preflight(manifest)
    assert report['artifacts']['qemu']['file']['state'] == 'blocked'
    assert report['checks']['capture']['state'] == 'blocked'
    assert all(secret not in json.dumps(report) for secret in ('SECRET-TOKEN', '/home/private', str(sample['root'])))


@pytest.mark.parametrize('kind', ['symlink', 'parent-symlink', 'hardlink', 'directory', 'fifo'])
def test_unsafe_filesystem_entries_fail_closed(sample, kind):
    target = sample['root'] / 'unsafe.exe'
    if kind in {'symlink', 'parent-symlink'}:
        try:
            if kind == 'symlink': target.symlink_to(sample['qemu'])
            else:
                link = sample['root'] / 'linked'
                link.symlink_to(sample['root'], target_is_directory=True)
                target = link / sample['qemu'].name
        except OSError:
            pytest.skip('Host cannot create the required filesystem symlink')
    elif kind == 'hardlink': os.link(sample['qemu'], target)
    elif kind == 'directory': target.mkdir()
    else:
        if not hasattr(os, 'mkfifo'):
            pytest.skip('Native FIFO creation is unavailable on this host')
        os.mkfifo(target)
    sample['spec']['artifacts']['qemu']['path'] = str(target)
    record = run(sample)['artifacts']['qemu']
    assert record['file']['state'] == 'blocked'
    assert record['signing']['state'] == 'blocked'


@pytest.mark.parametrize('location', ['file', 'parent'])
def test_reparse_point_attribute_simulation_is_rejected_without_native_execution(sample, monkeypatch, location):
    vendor = sample['root'] / 'vendor'
    vendor.mkdir()
    selected = vendor / 'qemu.exe'
    selected.write_bytes(synthetic_pe())
    sample['spec']['artifacts']['qemu']['path'] = str(selected)
    manifest = sample['save']()
    target = selected if location == 'file' else vendor
    original = Path.lstat

    class ReparseInfo:
        def __init__(self, value):
            self.value = value
            self.st_file_attributes = getattr(value, 'st_file_attributes', 0) | 0x400
        def __getattr__(self, name):
            return getattr(self.value, name)

    def simulated_lstat(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        return ReparseInfo(value) if path == target else value

    monkeypatch.setattr(Path, 'lstat', simulated_lstat)
    report = preflight.preflight(manifest)
    assert report['artifacts']['qemu']['file']['state'] == 'blocked'
    assert report['status'] == 'blocked'
    assert_inert(report)


def test_complete_supplied_runtime_observations_are_only_receipt_consistency(sample):
    receipt(sample, 'runtime_observations', observations(sample))
    report = run(sample)
    record = report['receipts']['runtime_observations']
    assert record['integrity']['state'] == 'verified'
    assert record['scope'] == 'caller_supplied_receipt_consistency_only'
    assert all(row['state'] == 'verified' for row in record['checks'].values())
    assert report['checks']['runtime_observations']['state'] == 'not_assessed'
    assert report['checks']['native_capabilities']['state'] == 'not_assessed'
    assert report['artifacts']['qemu']['identity']['state'] == 'mismatch'
    assert_inert(report)


@pytest.mark.parametrize('field', ['qemu-version', 'qemu-machine', 'gdb-version', 'gdb-arm', 'gdb-python'])
def test_negative_observation_fields_are_comparisons_never_guest_execution(sample, field):
    value = observations(sample)
    name, attribute = {'qemu-version': ('qemu', 'version'), 'qemu-machine': ('qemu', 'mps2_an385'),
        'gdb-version': ('gdb', 'version'), 'gdb-arm': ('gdb', 'arm'),
        'gdb-python': ('gdb', 'python_hashlib_marker')}[field]
    value['tools'][name][attribute] = ('QEMU emulator version 11.1.3' if name == 'qemu'
        else 'GNU gdb (GDB) 16.3') if attribute == 'version' else ('wrong-marker' if attribute == 'python_hashlib_marker' else False)
    receipt(sample, 'runtime_observations', value)
    report = run(sample)
    checks = report['receipts']['runtime_observations']['checks']
    assert checks[name + '_' + attribute]['state'] == 'mismatch'
    assert_inert(report)


@pytest.mark.parametrize('fault', ['subject', 'bool-arm', 'bad-version', 'extra-secret', 'schema-bool'])
def test_observation_receipt_binding_types_and_data_hygiene(sample, fault):
    value = observations(sample)
    if fault == 'subject': value['tools']['gdb']['sha256'] = '0' * 64
    elif fault == 'bool-arm': value['tools']['gdb']['arm'] = 1
    elif fault == 'bad-version': value['tools']['gdb']['version'] = 'GNU gdb (GDB) 18.1\nPRIVATE-SECRET'
    elif fault == 'extra-secret': value['tools']['gdb']['password'] = 'PRIVATE-SECRET'
    else: value['schema_version'] = True
    receipt(sample, 'runtime_observations', value)
    report = run(sample)
    if fault == 'subject':
        assert report['receipts']['runtime_observations']['checks']['gdb']['state'] == 'mismatch'
    else:
        assert report['status'] == 'blocked'
    assert 'PRIVATE-SECRET' not in json.dumps(report)


@pytest.mark.parametrize('name', preflight.RECEIPTS)
def test_evidence_categories_are_missing_until_explicitly_supplied_and_never_self_authenticating(sample, name):
    assert run(sample)['receipts'][name]['file']['state'] == 'missing'
    value = observations(sample) if name == 'runtime_observations' else {
        'trusted': True, 'production_qualified': True, 'secret': 'DO-NOT-PUBLISH'}
    receipt(sample, name, value)
    report = run(sample)
    assert report['receipts'][name]['integrity']['state'] == 'verified'
    assert report['checks'][name]['state'] == 'not_assessed'
    assert 'DO-NOT-PUBLISH' not in json.dumps(report)
    assert_inert(report)


def test_unpinned_or_mismatching_receipt_does_not_supply_capability_checks(sample):
    path = receipt(sample, 'runtime_observations', observations(sample))
    descriptor = sample['spec']['receipts']['runtime_observations']
    del descriptor['sha256']
    report = run(sample)
    assert report['receipts']['runtime_observations']['integrity']['state'] == 'missing'
    assert 'checks' not in report['receipts']['runtime_observations']
    descriptor['sha256'] = '0' * 64
    report = run(sample)
    assert report['receipts']['runtime_observations']['integrity']['state'] == 'mismatch'
    assert 'checks' not in report['receipts']['runtime_observations']
    assert path.read_bytes()


@pytest.mark.parametrize('timing', ['after-first-read', 'after-later-file', 'new-missing-file'])
def test_changes_across_capture_interval_fail_closed(sample, monkeypatch, timing):
    if timing == 'new-missing-file':
        missing = sample['root'] / 'later.exe'
        sample['spec']['artifacts']['qemu']['path'] = str(missing)
    manifest = sample['save']()
    original = preflight.read_bytes
    changed = False
    def racing_read(path, maximum):
        nonlocal changed
        data = original(path, maximum)
        path = Path(path)
        if not changed and ((timing == 'after-first-read' and path == sample['qemu'])
                or (timing in {'after-later-file', 'new-missing-file'} and path == sample['gdb'])):
            changed = True
            if timing == 'new-missing-file': missing.write_bytes(synthetic_pe())
            else: sample['qemu'].write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        return data
    monkeypatch.setattr(preflight, 'read_bytes', racing_read)
    report = preflight.preflight(manifest)
    assert changed
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {}


@pytest.mark.parametrize('deleted', ['qemu', 'manifest'])
def test_disappearing_measured_input_is_blocked_not_misreported_as_missing_manifest(sample, monkeypatch, deleted):
    manifest = sample['save']()
    original = preflight.read_bytes
    removed = False
    def racing_read(path, maximum):
        nonlocal removed
        data = original(path, maximum)
        if Path(path) == sample['gdb'] and not removed:
            removed = True
            sample[deleted].unlink()
        return data
    monkeypatch.setattr(preflight, 'read_bytes', racing_read)
    report = preflight.preflight(manifest)
    assert removed
    assert report['status'] == 'blocked'
    assert report['checks']['capture'] == {'state': 'blocked', 'code': 'capture_changed'}
    assert report['artifacts'] == {}


@pytest.mark.parametrize('deleted', ['manifest', 'qemu'])
def test_file_not_found_after_successful_read_is_capture_failure_not_initial_absence(sample, monkeypatch, deleted):
    manifest = sample['save']()
    target = sample[deleted]
    original = preflight.read_bytes
    removed = False
    def racing_read(path, maximum):
        nonlocal removed
        data = original(path, maximum)
        if Path(path) == target and not removed:
            removed = True
            target.unlink()
            raise FileNotFoundError('PRIVATE read-time disappearance')
        return data
    monkeypatch.setattr(preflight, 'read_bytes', racing_read)
    report = preflight.preflight(manifest)
    assert removed
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['state'] == 'blocked'
    assert report['checks']['capture']['code'] != 'manifest_not_found'
    assert report['artifacts'] == {}
    assert 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('limit', ['MAX_FILE_BYTES', 'MAX_MANIFEST_BYTES', 'MAX_TOTAL_BYTES', 'MAX_FILES', 'MAX_IMPORTS'])
def test_resource_bounds_fail_closed(sample, monkeypatch, limit):
    monkeypatch.setattr(preflight, limit, 1)
    if limit == 'MAX_IMPORTS':
        sample['qemu'].write_bytes(synthetic_pe('one.dll', 'two.dll'))
    report = run(sample)
    assert report['status'] == 'blocked'


def test_exact_aggregate_byte_boundary_can_be_captured(sample, monkeypatch):
    manifest = sample['save']()
    total = sum(path.stat().st_size for path in (manifest, sample['qemu'], sample['gdb']))
    monkeypatch.setattr(preflight, 'MAX_TOTAL_BYTES', total)
    report = preflight.preflight(manifest)
    assert report['checks']['capture']['state'] == 'verified'
    assert report['artifacts']['qemu']['file']['state'] == 'verified'
    monkeypatch.setattr(preflight, 'MAX_TOTAL_BYTES', total - 1)
    report = preflight.preflight(manifest)
    assert report['status'] == 'blocked'


def test_exact_file_manifest_and_inventory_bounds_are_inclusive(sample, monkeypatch):
    manifest = sample['save']()
    monkeypatch.setattr(preflight, 'MAX_FILE_BYTES', len(sample['qemu'].read_bytes()))
    monkeypatch.setattr(preflight, 'MAX_MANIFEST_BYTES', manifest.stat().st_size)
    monkeypatch.setattr(preflight, 'MAX_FILES', 2)
    report = preflight.preflight(manifest)
    assert report['checks']['capture']['state'] == 'verified'
    assert report['artifacts']['qemu']['file']['state'] == 'verified'
    sample['spec']['companions'] = [{'path': 'helper.dll'}]
    monkeypatch.setattr(preflight, 'MAX_MANIFEST_BYTES', 1024**2)
    report = run(sample)
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == 'artifact_count_bound'


def test_runtime_receipt_size_and_import_count_exact_boundaries(sample, monkeypatch):
    path = receipt(sample, 'runtime_observations', observations(sample))
    monkeypatch.setattr(preflight, 'MAX_RECEIPT_BYTES', path.stat().st_size)
    monkeypatch.setattr(preflight, 'MAX_IMPORTS', 1)
    report = run(sample)
    assert report['receipts']['runtime_observations']['file']['state'] == 'verified'
    assert report['artifacts']['qemu']['imports']['state'] == 'verified'
    monkeypatch.setattr(preflight, 'MAX_RECEIPT_BYTES', path.stat().st_size - 1)
    assert run(sample)['receipts']['runtime_observations']['file']['state'] == 'blocked'


@pytest.mark.parametrize('fault', ['overlap', 'unaligned', 'oversize', 'revision', 'type', 'length'])
def test_certificate_table_geometry_failures_never_become_signing_evidence(sample, fault):
    data = bytearray(synthetic_pe(certificate=True))
    if fault == 'overlap': struct.pack_into('<I', data, 88 + 112 + 4 * 8, 512)
    elif fault == 'unaligned': struct.pack_into('<I', data, 88 + 112 + 4 * 8, 2049)
    elif fault == 'oversize': struct.pack_into('<I', data, 88 + 112 + 4 * 8 + 4, 2**32 - 1)
    elif fault == 'revision': struct.pack_into('<H', data, 2048 + 4, 0x100)
    elif fault == 'type': struct.pack_into('<H', data, 2048 + 6, 1)
    else: struct.pack_into('<I', data, 2048, 8)
    sample['qemu'].write_bytes(data)
    report = run(sample)
    assert report['artifacts']['qemu']['pe']['state'] == 'blocked'
    assert report['artifacts']['qemu']['signing']['state'] == 'blocked'
    assert_inert(report)


def test_geometrically_valid_certificate_inside_mapped_raw_section_is_rejected(sample):
    data = bytearray(synthetic_pe(certificate=True))
    data[1024:1040] = data[2048:2064]
    struct.pack_into('<II', data, 88 + 112 + 4 * 8, 1024, 16)
    sample['qemu'].write_bytes(data)
    report = run(sample)
    assert report['artifacts']['qemu']['pe']['state'] == 'blocked'
    assert report['artifacts']['qemu']['signing']['state'] == 'blocked'
    # The same valid certificate is structurally accepted when its bytes are
    # outside the mapped raw section; presence still establishes no trust.
    struct.pack_into('<I', data, 88 + 240 + 16, 512)
    sample['qemu'].write_bytes(data)
    report = run(sample)
    assert report['artifacts']['qemu']['pe']['state'] == 'verified'
    assert report['artifacts']['qemu']['certificate_table']['state'] == 'verified'
    assert report['artifacts']['qemu']['signing']['state'] == 'not_assessed'
    assert_inert(report)


def test_required_companion_row_preserves_structural_failure_despite_matching_digest(sample):
    companion = sample['root'] / 'helper.dll'
    companion.write_bytes(b'not a PE, despite matching its caller-provided digest')
    sample['spec']['companions'] = [{'path': str(companion), 'sha256': digest(companion.read_bytes())}]
    report = run(sample)
    assert report['artifacts']['companion_001']['identity']['state'] == 'verified'
    assert report['required_dlls']['helper.dll']['state'] == 'blocked'


@pytest.mark.parametrize('exception_type', [KeyboardInterrupt, SystemExit],
                         ids=['keyboard-interrupt', 'system-exit'])
def test_control_flow_interruption_is_not_converted_to_a_report(sample, monkeypatch, exception_type):
    manifest = sample['save']()
    interruption = exception_type('cancelled')
    def interrupt(*args, **kwargs): raise interruption
    monkeypatch.setattr(preflight, 'read_bytes', interrupt)
    with pytest.raises(exception_type, match='cancelled') as caught:
        preflight.preflight(manifest)
    assert caught.value is interruption


def test_cli_writes_only_sanitized_json_and_human_summary(sample, capsys):
    manifest = sample['save']()
    assert preflight.main(['--manifest', str(manifest)]) == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['status'] == 'mismatch'
    assert output.err == preflight.summary(report)
    assert str(sample['root']) not in output.out + output.err
    assert 'No tools or firmware executed' in output.err
    assert preflight.main(['--manifest', 'evidence/windows-sandbox/NEVER-OPEN.json']) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)['status'] == 'blocked'
    assert 'NEVER-OPEN' not in output.out + output.err


@pytest.mark.parametrize('args', [[], ['--manifest'], ['--manifest', 'NO-READ', '--SECRET-CREDENTIAL']],
                         ids=['missing-manifest', 'missing-value', 'unknown-option'])
def test_cli_usage_errors_have_safe_json_without_echoing_arguments_or_program_path(capsys, args):
    assert preflight.main(args) == 2
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == 'invalid_arguments'
    assert all(secret not in output.out + output.err for secret in ('SECRET-CREDENTIAL', 'NO-READ'))
    assert output.err == preflight.summary(report)


def test_production_profile_remains_exact_original_constants():
    from firmavex.product import platform_support
    assert platform_support.WINDOWS_PROFILE_ID == 'msys2-ucrt64-qemu11.1.2-gdb18.1-v1'
    assert platform_support.WINDOWS_EXECUTABLES == {
        'qemu': ('QEMU emulator version 11.1.2', '1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244'),
        'gdb': ('GNU gdb (GDB) 18.1', 'f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236')}


@pytest.mark.parametrize('tool', ['qemu', 'gdb'])
def test_present_null_observation_tool_is_malformed_not_missing(sample, tool):
    value = observations(sample)
    value['tools'][tool] = None
    receipt(sample, 'runtime_observations', value)
    report = run(sample)
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == 'invalid_observation_receipt'
    assert report['artifacts'] == {}


@pytest.mark.parametrize('subject', ['missing-artifact', 'stale-digest'])
@pytest.mark.parametrize(('tool', 'field', 'bad_value'), [
    ('qemu', 'mps2_an385', 1),
    ('gdb', 'arm', 1),
    ('qemu', 'version', None),
    ('gdb', 'version', {'private': 'DO-NOT-PUBLISH'}),
    ('gdb', 'python_hashlib_marker', []),
    ('gdb', 'unknown', 'DO-NOT-PUBLISH'),
], ids=['machine-bool', 'arm-bool', 'null-version', 'object-version',
        'marker-list', 'unknown-field'])
def test_observation_schema_is_validated_before_subject_binding(sample, subject, tool, field, bad_value):
    value = observations(sample)
    value['tools'][tool][field] = bad_value
    if subject == 'missing-artifact':
        del sample['spec']['artifacts'][tool]
    else:
        value['tools'][tool]['sha256'] = '0' * 64
    receipt(sample, 'runtime_observations', value)
    report = run(sample)
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == 'invalid_observation_receipt'
    assert report['artifacts'] == {}
    assert 'DO-NOT-PUBLISH' not in json.dumps(report)


@pytest.mark.parametrize('tool', ['qemu', 'gdb'])
def test_truly_absent_observation_tool_remains_missing(sample, tool):
    value = observations(sample)
    del value['tools'][tool]
    receipt(sample, 'runtime_observations', value)
    report = run(sample)
    assert report['receipts']['runtime_observations']['checks'][tool] == {
        'state': 'missing', 'code': 'tool_observation_not_supplied'}
    assert report['checks']['capture']['state'] == 'verified'


@pytest.mark.parametrize('value', [r'\/server/share/file.json', r'/\server/share/file.json'],
                         ids=['backslash-forward-unc', 'forward-backslash-unc'])
def test_mixed_separator_unc_manifest_is_refused_before_filesystem_or_network(monkeypatch, value):
    def forbidden(*args, **kwargs):
        raise AssertionError('UNC manifest reached filesystem or network')
    monkeypatch.setattr(preflight, 'checked_path', forbidden)
    monkeypatch.setattr(preflight, 'read_bytes', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    report = preflight.preflight(value)
    assert report['status'] == 'blocked'
    assert 'server' not in json.dumps(report)


@pytest.mark.parametrize('value', [r'\/server/share/file.exe', r'/\server/share/file.exe'],
                         ids=['backslash-forward-unc', 'forward-backslash-unc'])
def test_mixed_separator_unc_descriptor_is_refused_before_artifact_access(sample, monkeypatch, value):
    sample['spec']['artifacts']['qemu']['path'] = value
    manifest = sample['save']()
    original = preflight.checked_path
    def manifest_only(path, *args, **kwargs):
        assert Path(path) == manifest, 'UNC artifact reached filesystem'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(preflight, 'checked_path', manifest_only)
    report = preflight.preflight(manifest)
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {}
    assert 'server' not in json.dumps(report)


class _AbsoluteWindowsPath(PureWindowsPath):
    """Lexical-only Windows path model; never sent to filesystem helpers."""
    def absolute(self):
        return self


@pytest.mark.parametrize('base', [
    r'\\server\share\admin',
    r'C:\EVIDEN~1\WINDOW~1',
    r'C:\evidence.\windows-sandbox',
    r'C:\evidence \windows-sandbox',
    r'C:\evidence\windows-sandbox.',
], ids=['unc-base', 'short-name-base', 'parent-dot-base', 'parent-space-base',
        'protected-child-dot-base'])
def test_relative_path_cannot_inherit_unsafe_windows_base(monkeypatch, base):
    def forbidden(*args, **kwargs):
        raise AssertionError('Lexical-only test reached filesystem')
    monkeypatch.setattr(preflight, 'checked_path', forbidden)
    monkeypatch.setattr(preflight, 'read_bytes', forbidden)
    monkeypatch.setattr(preflight, 'os', SimpleNamespace(name='nt'))
    with pytest.raises(ValueError):
        preflight._lexical_path('manifest.json', _AbsoluteWindowsPath(base))


def test_relative_path_under_ordinary_windows_drive_base_remains_lexically_supported(monkeypatch):
    monkeypatch.setattr(preflight, 'os', SimpleNamespace(name='nt'))
    base = _AbsoluteWindowsPath(r'C:\FIRMAVEX-admin')
    result = preflight._lexical_path('manifest.json', base)
    assert str(result).replace('\\', '/') == 'C:/FIRMAVEX-admin/manifest.json'


def test_bounded_deterministic_pe_mutations_do_not_escape_parser_or_claim_trust():
    original = synthetic_pe(certificate=True)
    rng = random.Random(3401)
    cases = [original[:n] for n in range(0, len(original) + 1, 17)]
    fields = [60, 68, 70, 84, 88, 148, 196, 232, 236, 344, 348, 2048, 2052, 2054]
    for index in range(2500):
        data = bytearray(original)
        for _ in range(1 + index % 3):
            offset = rng.choice(fields)
            struct.pack_into('<I', data, offset, rng.choice([
                0, 1, 7, 8, 9, 16, 96, 512, 2048, 0xffffffff, rng.randrange(2**32)]))
        cases.append(bytes(data))
    accepted = rejected = 0
    for data in cases:
        try:
            header, table = preflight._pe(data)
        except ValueError:
            rejected += 1
        else:
            accepted += 1
            assert header['state'] == 'verified'
            assert table['state'] in {'verified', 'missing'}
            assert set(header) == {'state', 'code', 'architecture'}
            assert set(table) <= {'state', 'code', 'entries'}
    assert len(cases) == 2622
    assert accepted > 0 and rejected > 0


def test_runtime_receipt_change_during_processing_rejects_entire_capture(sample, monkeypatch):
    path = receipt(sample, 'runtime_observations', observations(sample))
    original = preflight._runtime_observations
    changed = False
    def mutate_receipt(data, artifacts):
        nonlocal changed
        result = original(data, artifacts)
        path.write_bytes(data + b' ')
        changed = True
        return result
    monkeypatch.setattr(preflight, '_runtime_observations', mutate_receipt)
    report = run(sample)
    assert changed
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == 'capture_changed'
    assert report['artifacts'] == {} and report['receipts'] == {}


def test_initially_missing_receipt_appearing_during_later_receipt_read_is_blocked(sample, monkeypatch):
    missing = sample['root'] / 'missing-package-receipt.json'
    sample['spec']['receipts'] = {'package_manifest': {'path': str(missing), 'sha256': '0' * 64}}
    later = receipt(sample, 'publisher_authentication', {'declared': 'opaque-evidence'})
    original = preflight.read_bytes
    appeared = False
    def create_missing(path, maximum):
        nonlocal appeared
        data = original(path, maximum)
        if Path(path) == later and not appeared:
            missing.write_bytes(b'appeared during capture')
            appeared = True
        return data
    monkeypatch.setattr(preflight, 'read_bytes', create_missing)
    report = run(sample)
    assert appeared
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['code'] == 'capture_changed'
    assert report['artifacts'] == {} and report['receipts'] == {}


def test_integrity_pinned_malformed_runtime_receipt_json_is_blocked_without_echo(sample):
    data = b'{"schema_version":1,"tools":{"gdb": PRIVATE-RECEIPT-SECRET'
    path = sample['root'] / 'malformed-runtime-observations.json'
    path.write_bytes(data)
    sample['spec']['receipts'] = {'runtime_observations': {'path': str(path), 'sha256': digest(data)}}
    report = run(sample)
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {} and report['receipts'] == {}
    assert 'PRIVATE-RECEIPT-SECRET' not in json.dumps(report)
    assert str(path) not in json.dumps(report)


def test_opaque_provenance_bytes_prove_only_integrity_and_are_not_parsed_or_published(sample):
    data = b'\xff{not-json; PRIVATE-PUBLISHER-SECRET}'
    path = sample['root'] / 'opaque-publisher-evidence.bin'
    path.write_bytes(data)
    sample['spec']['receipts'] = {'publisher_authentication': {'path': str(path), 'sha256': digest(data)}}
    report = run(sample)
    row = report['receipts']['publisher_authentication']
    assert row['file']['state'] == 'verified' and row['integrity']['state'] == 'verified'
    assert report['checks']['publisher_authentication'] == {
        'state': 'not_assessed', 'code': 'receipt_integrity_only_not_authentication'}
    assert report['checks']['publisher_trust']['state'] == 'not_assessed'
    assert report['checks']['capture']['state'] == 'verified'
    assert 'PRIVATE-PUBLISHER-SECRET' not in json.dumps(report)
    assert str(path) not in json.dumps(report)
    assert_inert(report)


def test_protected_receipt_path_is_rejected_before_any_artifact_access(sample, monkeypatch):
    sample['spec']['receipts'] = {'licensing': {'path': 'evidence/windows-sandbox/NEVER-READ.json'}}
    manifest = sample['save']()
    original = preflight.checked_path
    calls = []
    def manifest_only(path, *args, **kwargs):
        calls.append(Path(path))
        assert Path(path) == manifest, 'Protected receipt reached filesystem'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(preflight, 'checked_path', manifest_only)
    report = preflight.preflight(manifest)
    assert calls and set(calls) == {manifest}
    assert report['status'] == 'blocked'
    assert report['artifacts'] == {} and report['receipts'] == {}
    assert 'NEVER-READ' not in json.dumps(report)


def test_real_oversized_runtime_receipt_is_blocked_before_json_processing(sample, monkeypatch):
    data = b'x' * (1024**2 + 1)
    path = sample['root'] / 'oversized-runtime-observations.json'
    path.write_bytes(data)
    sample['spec']['receipts'] = {'runtime_observations': {'path': str(path), 'sha256': digest(data)}}
    def forbidden(*args, **kwargs):
        raise AssertionError('Oversized runtime observations reached parser')
    monkeypatch.setattr(preflight, '_runtime_observations', forbidden)
    report = run(sample)
    assert path.stat().st_size == preflight.MAX_RECEIPT_BYTES + 1
    assert report['status'] == 'blocked'
    assert report['receipts']['runtime_observations']['file']['state'] == 'blocked'
    assert 'oversized-runtime-observations.json' not in json.dumps(report)


@pytest.mark.parametrize('value', ['COM\u00b9.exe', 'LPT\u00b2.txt', 'COM1 .exe',
                                  'NUL .dll', 'CONIN$', 'CONOUT$.txt'],
                         ids=['superscript-com', 'superscript-lpt', 'spaced-com',
                              'spaced-nul', 'console-input', 'console-output'])
def test_additional_windows_reserved_names_are_refused_before_filesystem_access(monkeypatch, value):
    assert PureWindowsPath(value).is_reserved(), 'Fixture must model a Windows reserved name'
    def forbidden(*args, **kwargs):
        raise AssertionError('Reserved device spelling reached filesystem')
    monkeypatch.setattr(preflight, 'checked_path', forbidden)
    monkeypatch.setattr(preflight, 'read_bytes', forbidden)
    report = preflight.preflight(value)
    assert report['status'] == 'blocked'
    assert value not in json.dumps(report)


@pytest.mark.parametrize('value', ['COM0.exe', 'COM10.exe'])
def test_ordinary_nonreserved_device_like_names_remain_lexically_supported(value):
    assert not PureWindowsPath(value).is_reserved()
    base = Path.cwd() / 'ordinary-preflight-base'
    assert preflight._lexical_path(value, base) == base / value


def test_concurrent_parent_swap_is_rejected_without_claiming_access_containment(tmp_path, monkeypatch):
    """Characterize final rejection only; hostile-writer containment is unresolved."""
    from firmavex.backends import security

    selected_parent = tmp_path / 'selected-parent'
    selected_parent.mkdir()
    alternate_parent = tmp_path / 'alternate-parent'
    alternate_parent.mkdir()
    selected = selected_parent / 'synthetic.exe'
    selected.write_bytes(synthetic_pe('declared.dll'))
    (alternate_parent / selected.name).write_bytes(synthetic_pe('alternate.dll'))
    probe = tmp_path / 'symlink-capability-probe'
    try:
        probe.symlink_to(alternate_parent, target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create the required temporary directory symlink')
    probe.unlink()
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'schema_version': 1,
                                    'artifacts': {'qemu': {'path': str(selected)}}}))
    original_state = security.path_state
    swapped = False

    def swap_parent_before_open(path, *args, **kwargs):
        nonlocal swapped
        if Path(path) == selected and not swapped:
            swapped = True
            selected_parent.rename(tmp_path / 'retained-original-parent')
            selected_parent.symlink_to(alternate_parent, target_is_directory=True)
        return original_state(path, *args, **kwargs)

    monkeypatch.setattr(security, 'path_state', swap_parent_before_open)
    report = preflight.preflight(manifest)
    assert swapped
    assert report['status'] == 'blocked'
    assert report['checks']['capture']['state'] == 'blocked'
    assert report['artifacts'] == {} and report['receipts'] == {}
    assert report['checks']['access_containment'] == {
        'state': 'not_assessed', 'code': 'concurrent_path_redirection_not_prevented'}
    assert report['production_qualified'] is False
    # A blocked final report does not assert that no redirected access occurred.
    assert str(tmp_path) not in json.dumps(report)
