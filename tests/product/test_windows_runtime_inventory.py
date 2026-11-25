"""Invented supplied records only; no real Windows, binary or original evidence."""
import builtins
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import urllib.request

import pytest

from firmavex.product import platform_support as policy
from tools import windows_runtime_inventory as audit
from tools import windows_runtime_preflight as preflight

REVISION = 'a' * 40


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def supplied(tmp_path):
    comparison = policy._qualification_details({
        'qemu': {'version': 'QEMU emulator version 11.1.3', 'sha256': '1' * 64},
        'gdb': {'version': 'GNU gdb (GDB) 18.1', 'sha256': '2' * 64}}, 'AMD64')
    value = {'schema_version': 1, 'kind': 'firmavex_versioned_installer_qualification',
        'candidate_git_revision': REVISION, 'platform': 'win32',
        'measurement': 'real_hosted_ci_not_physical_consumer', 'passed': False, 'phases': [],
        'failure': {'type': 'ProductError', 'diagnostic': 'PRIVATE-UNPUBLISHED-DIAGNOSTIC',
                    'runtime_qualification': comparison}}
    packages = {audit.PACKAGES[0]: '11.1.3-2', audit.PACKAGES[1]: '11.1.3-2',
                audit.PACKAGES[2]: '18.1-4', audit.PACKAGES[3]: '18.1-4',
                'UnpublishedPrivatePackage': '1.0-1'}
    paths = {'receipt': tmp_path/'private-receipt.json', 'inventory': tmp_path/'private-packages.txt'}
    def save():
        paths['receipt'].write_bytes(json.dumps(value, sort_keys=True).encode())
        paths['inventory'].write_bytes('\n'.join(f'{n} {v}' for n, v in packages.items()).encode())
    save()
    return {'value': value, 'packages': packages, 'paths': paths, 'save': save}


def arguments(supplied):
    p = supplied['paths']
    return {'expected_revision': REVISION,
            'expected_receipt_sha256': digest(p['receipt'].read_bytes()),
            'expected_inventory_sha256': digest(p['inventory'].read_bytes())}


def assess(supplied, **overrides):
    pins = arguments(supplied); pins.update(overrides)
    return audit.assess(supplied['paths']['receipt'], supplied['paths']['inventory'], **pins)


def forbid_activity(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Assessment attempted execution, network, directory scan or write')
    for name in ('run', 'Popen', 'call', 'check_call', 'check_output'):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    for name in ('write_bytes', 'write_text', 'mkdir', 'touch', 'unlink', 'replace', 'rename', 'glob', 'rglob', 'iterdir'):
        monkeypatch.setattr(Path, name, forbidden)
    for name in ('walk', 'scandir', 'listdir'):
        monkeypatch.setattr(os, name, forbidden)
    original = (builtins.open, io.open, os.open)
    def readonly_open(file, mode='r', *args, **kwargs):
        assert not any(c in mode for c in 'wax+')
        return original[0](file, mode, *args, **kwargs)
    def readonly_io(file, mode='r', *args, **kwargs):
        assert not any(c in mode for c in 'wax+')
        return original[1](file, mode, *args, **kwargs)
    def readonly_os(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return original[2](path, flags, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', readonly_open)
    monkeypatch.setattr(io, 'open', readonly_io)
    monkeypatch.setattr(os, 'open', readonly_os)


def test_consistent_rejection_is_deterministic_read_only_and_never_qualification(supplied, monkeypatch):
    pins = arguments(supplied)
    before = {name: p.read_bytes() for name, p in supplied['paths'].items()}
    forbid_activity(monkeypatch)
    first = audit.assess(supplied['paths']['receipt'], supplied['paths']['inventory'], **pins)
    assert first == audit.assess(supplied['paths']['receipt'], supplied['paths']['inventory'], **pins)
    assert first['status'] == 'consistent_records' and first['recorded_admission'] == 'rejected'
    assert first['recorded_installer_transitions'] == 0
    assert 'not proof of zero tool subprocesses' in first['transition_scope']
    assert first['capture'] == {'status': 'stable_observed', 'atomic': False}
    assert first['package_count'] == 5
    assert set(first['packages']) == set(audit.PACKAGES)
    assert all(row['reported_upstream_agrees'] is True for row in first['packages'].values())
    assert all(value == 'not_assessed' for value in first['checks'].values())
    assert first['checks']['source_revision_authenticity'] == 'not_assessed'
    for flag in ('production_qualified', 'production_admission_evaluated', 'firmware_executed',
                 'tools_executed', 'atomic_snapshot', 'concurrent_path_isolation'):
        assert first[flag] is False
    serialized = json.dumps(first)
    assert 'PRIVATE' not in serialized and 'UnpublishedPrivatePackage' not in serialized
    assert str(supplied['paths']['receipt'].parent) not in serialized
    assert 'private-receipt' not in serialized and 'private-packages' not in serialized
    for name, p in supplied['paths'].items():
        assert p.read_bytes() == before[name]


@pytest.mark.parametrize('field,value', [('expected_revision', True), ('expected_revision', 'A'*40),
    ('expected_revision', 'a'*39), ('expected_receipt_sha256', True),
    ('expected_inventory_sha256', 'F'*64), ('expected_inventory_sha256', 'private')],
    ids=['bool-revision', 'upper-revision', 'short-revision', 'bool-digest', 'upper-digest', 'private-digest'])
def test_bad_pins_are_rejected_before_input_io(supplied, monkeypatch, field, value):
    pins = arguments(supplied); pins[field] = value
    monkeypatch.setattr(audit._Capture, 'read', lambda *a: pytest.fail('Invalid pin read input'))
    result = audit.assess(*supplied['paths'].values(), **pins)
    assert result['status'] == 'blocked'
    assert result['failures'] == [{'code': 'invalid_expected_identity'}]
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('path', ['/workspace/FIRMAVEX/private', 'evidence/windows-sandbox/private',
    'EVIDENCE\\WINDOWS-SANDBOX\\private', '../private', 'C:\\private:stream', '~/.private',
    '//host/private', 'NUL.txt'], ids=['original', 'protected', 'backslash-protected', 'parent',
                                      'alternate-stream', 'home', 'unc', 'device'])
def test_lexical_refusals_precede_any_input_access(supplied, monkeypatch, path):
    pins = arguments(supplied)
    monkeypatch.setattr(audit._Capture, 'read', lambda *a: pytest.fail('Forbidden path accessed'))
    result = audit.assess(path, supplied['paths']['inventory'], **pins)
    assert result['status'] == 'blocked' and result['failures'] == [{'code': 'unsafe_input_path'}]
    assert path not in json.dumps(result)


def test_duplicate_paths_are_rejected_before_io(supplied, monkeypatch):
    pins = arguments(supplied); path = supplied['paths']['receipt']
    monkeypatch.setattr(audit._Capture, 'read', lambda *a: pytest.fail('Duplicate path read'))
    result = audit.assess(path, str(path).upper(), **pins)
    assert result['failures'] == [{'code': 'duplicate_input_path'}]


@pytest.mark.parametrize('which', ['receipt', 'inventory'])
def test_supplied_digest_mismatch_blocks(supplied, which):
    result = assess(supplied, **{f'expected_{which}_sha256': '0'*64})
    assert result['failures'] == [{'code': f'{which}_digest_mismatch'}]


@pytest.mark.parametrize('field,value', [('schema_version', True), ('schema_version', 2),
    ('kind', 'other'), ('candidate_git_revision', 'b'*40), ('passed', 0), ('passed', True),
    ('platform', 'linux'), ('measurement', 'synthetic'), ('phases', [1]), ('phases', {})],
    ids=['bool-schema', 'future-schema', 'kind', 'revision', 'int-passed', 'passed',
         'platform', 'measurement', 'transition', 'wrong-phases'])
def test_unsupported_receipt_fields_block(supplied, field, value):
    supplied['value'][field] = value; supplied['save']()
    assert assess(supplied)['failures'] == [{'code': 'unsupported_lifecycle_receipt'}]


@pytest.mark.parametrize('mutation', ['type', 'profile', 'expected', 'matches', 'bool-alias', 'malformed'])
def test_contradictory_or_unsupported_qualification_blocks(supplied, mutation):
    value = supplied['value']; q = value['failure']['runtime_qualification']
    if mutation == 'type': value['failure']['type'] = 'RuntimeError'
    elif mutation == 'profile': q['required_profile'] = 'other'
    elif mutation == 'expected': q['tools']['gdb']['expected']['sha256'] = '0'*64
    elif mutation == 'matches': q['tools']['qemu']['matches']['version'] = True
    elif mutation == 'bool-alias': q['tools']['gdb']['matches']['version'] = 1
    else: q['tools']['qemu']['observed']['sha256'] = []
    supplied['save']()
    result = assess(supplied)
    assert result['status'] == 'blocked' and len(result['failures']) == 1


def test_fully_matching_x64_cannot_explain_a_failed_admission(supplied):
    q = policy._qualification_details({k: {'version': v, 'sha256': h}
        for k, (v, h) in policy.WINDOWS_EXECUTABLES.items()}, 'AMD64')
    supplied['value']['failure']['runtime_qualification'] = q; supplied['save']()
    assert assess(supplied)['failures'] == [{'code': 'contradictory_admission_rejection'}]
    q['host_architecture'] = 'arm64'; supplied['save']()
    assert assess(supplied)['status'] == 'consistent_records'


@pytest.mark.parametrize('roles', [('qemu',), ('gdb',), ('qemu', 'gdb')],
                         ids=['missing-qemu-identities', 'missing-gdb-identities', 'missing-both-identities'])
def test_missing_recorded_identities_stay_unknown_and_never_become_matches(supplied, roles):
    claim = supplied['value']['failure']['runtime_qualification']
    for role in roles:
        claim['tools'][role]['observed'] = {'version': None, 'sha256': None}
        claim['tools'][role]['matches'] = {'version': None, 'sha256': None}
    supplied['save']()
    result = assess(supplied)
    assert result['status'] == 'consistent_records'
    assert result['recorded_admission'] == 'rejected' and result['production_qualified'] is False
    for role in roles:
        row = result['comparison']['tools'][role]
        assert row['observed'] == row['matches'] == {'version': None, 'sha256': None}
        for name, package in result['packages'].items():
            if ('qemu' in name) is (role == 'qemu'):
                assert package['reported_upstream_agrees'] is None


@pytest.mark.parametrize('version,upstream', [('11.1.3-2', '11.1.3'), ('1:11.1.3-2', '11.1.3'),
                                          ('11.1.3-2.1', '11.1.3')])
def test_numeric_package_release_and_epoch_are_declarations_only(supplied, version, upstream):
    supplied['packages'][audit.PACKAGES[0]] = version; supplied['save']()
    result = assess(supplied); row = result['packages'][audit.PACKAGES[0]]
    assert result['status'] == 'consistent_records'
    assert row['declared_version'] == version and row['upstream_version'] == upstream
    assert row['reported_upstream_agrees'] is True
    assert row['declaration_scope'].endswith('not_ownership')


def test_disagreement_or_private_version_never_invents_ownership(supplied):
    supplied['packages'][audit.PACKAGES[0]] = '11.1.2-1'
    supplied['packages'][audit.PACKAGES[1]] = '1PRIVATE-PACKAGE-DETAIL'
    supplied['save'](); result = assess(supplied)
    assert result['status'] == 'consistent_records'
    assert result['packages'][audit.PACKAGES[0]]['reported_upstream_agrees'] is False
    assert result['packages'][audit.PACKAGES[1]]['state'] == 'not_assessed'
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('root', audit.ROOTS)
def test_required_workflow_roots_cannot_be_missing(supplied, root):
    del supplied['packages'][root]; supplied['save']()
    assert assess(supplied)['failures'] == [{'code': 'missing_inventory_roots'}]


@pytest.mark.parametrize('data', [b'{}', b'{"schema_version":1,"schema_version":1}',
                                b'{"private":NaN}', b'\xff'],
                         ids=['empty-object', 'duplicate', 'nonfinite', 'invalid-utf8'])
def test_malformed_receipts_never_leak_input(supplied, data):
    supplied['paths']['receipt'].write_bytes(data)
    result = assess(supplied)
    assert result['status'] == 'blocked' and 'private' not in json.dumps(result)


@pytest.mark.parametrize('data', [b'', b'only-one-field', b'name 1\nname 2', b'\xff',
                                b'\n'.join(f'Dep{i} 1.0-1'.encode() for i in range(4097))],
                         ids=['empty', 'malformed', 'duplicate', 'invalid-utf8', 'count-bound'])
def test_malformed_inventory_blocks(supplied, data):
    supplied['paths']['inventory'].write_bytes(data)
    assert assess(supplied)['status'] == 'blocked'


@pytest.mark.parametrize('which', ['receipt', 'inventory'])
def test_oversized_or_missing_input_blocks(supplied, which):
    supplied['paths'][which].write_bytes(b'x'*(audit.MAX_INPUT+1))
    assert assess(supplied)['failures'] == [{'code': 'unreadable_or_changed_input'}]
    pins = arguments(supplied); supplied['paths'][which].unlink()
    assert audit.assess(*supplied['paths'].values(), **pins)['status'] == 'blocked'


def test_both_inputs_at_byte_boundary_fit_total_budget(supplied):
    receipt = supplied['paths']['receipt']; inventory = supplied['paths']['inventory']
    content = receipt.read_bytes(); receipt.write_bytes(content+b' '*(audit.MAX_INPUT-len(content)))
    content = inventory.read_bytes(); split = content.index(b' ')
    inventory.write_bytes(content[:split]+b' '*(audit.MAX_INPUT-len(content))+content[split:])
    assert len(receipt.read_bytes()) == len(inventory.read_bytes()) == audit.MAX_INPUT
    result = assess(supplied)
    assert result['status'] == 'consistent_records'
    assert all(row['size_bytes'] == audit.MAX_INPUT for row in result['inputs'].values())


@pytest.mark.parametrize('which', ['receipt', 'inventory'])
def test_mid_processing_input_change_is_rejected(supplied, monkeypatch, which):
    original = audit._packages
    def change(*args):
        path = supplied['paths'][which]; data = path.read_bytes()
        path.write_bytes(data.replace(b'11.1.3', b'11.1.4', 1))
        return original(*args)
    monkeypatch.setattr(audit, '_packages', change)
    assert assess(supplied)['failures'] == [{'code': 'unreadable_or_changed_input'}]


def test_symlink_input_is_rejected_without_reading_target(supplied, monkeypatch, tmp_path):
    link = tmp_path/'link.json'
    try: link.symlink_to(supplied['paths']['receipt'])
    except OSError: pytest.skip('Host does not permit test symlinks')
    pins = arguments(supplied)
    monkeypatch.setattr(preflight, 'read_bytes', lambda *a, **k: pytest.fail('Symlink target read'))
    assert audit.assess(link, supplied['paths']['inventory'], **pins)['status'] == 'blocked'


def test_pre_cancelled_assessment_does_not_read_inputs(supplied, monkeypatch):
    pins = arguments(supplied); cancel = threading.Event(); cancel.set()
    monkeypatch.setattr(audit._Capture, 'read', lambda *a: pytest.fail('Cancelled input read'))
    with pytest.raises(KeyboardInterrupt, match='cancelled'):
        audit.assess(*supplied['paths'].values(), **pins, cancel_event=cancel)


@pytest.mark.parametrize('stage', ['parse', 'finish'])
@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, BaseException],
                         ids=['keyboard', 'exit', 'base-control'])
def test_control_flow_propagates_without_ordinary_blocked_result(supplied, monkeypatch, stage, factory):
    error = factory('synthetic control')
    def interrupted(*args, **kwargs): raise error
    if stage == 'parse': monkeypatch.setattr(audit, '_json', interrupted)
    else: monkeypatch.setattr(audit._Capture, 'finish', interrupted)
    with pytest.raises(type(error)) as caught:
        assess(supplied)
    assert caught.value is error


def test_cancellation_after_processing_remains_control_flow(supplied, monkeypatch):
    cancel = threading.Event(); original = audit._packages
    def stop(*args):
        result = original(*args); cancel.set(); return result
    monkeypatch.setattr(audit, '_packages', stop)
    with pytest.raises(KeyboardInterrupt): assess(supplied, cancel_event=cancel)


def test_cli_reports_json_and_fixed_summary_without_private_paths(supplied, capsys):
    pins = arguments(supplied)
    args = ['--receipt', str(supplied['paths']['receipt']), '--inventory', str(supplied['paths']['inventory']),
            '--revision', REVISION, '--receipt-sha256', pins['expected_receipt_sha256'],
            '--inventory-sha256', pins['expected_inventory_sha256']]
    assert audit.main(args) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)['status'] == 'consistent_records'
    assert output.err == 'FIRMAVEX supplied runtime inventory: consistent_records; qualification not assessed.\n'
    assert audit.main(['--private-missing-argument']) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)['failures'] == [{'code': 'invalid_arguments'}]
    assert 'private' not in output.out+output.err


def test_cli_cp1252_stream_has_no_encoding_fallback_or_data_loss(supplied, monkeypatch, capsys):
    pins = arguments(supplied); data = io.BytesIO()
    stream = io.TextIOWrapper(data, encoding='cp1252', errors='strict', newline='', write_through=True)
    args = ['--receipt', str(supplied['paths']['receipt']), '--inventory', str(supplied['paths']['inventory']),
            '--revision', REVISION, '--receipt-sha256', pins['expected_receipt_sha256'],
            '--inventory-sha256', pins['expected_inventory_sha256']]
    with monkeypatch.context() as patch:
        patch.setattr(audit.sys, 'stdout', stream)
        assert audit.main(args) == 0
    assert json.loads(data.getvalue().decode('cp1252'))['recorded_admission'] == 'rejected'
