"""Invented archive consistency evidence only; no native or runtime execution."""

import builtins
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import xml.etree.ElementTree as ET

import pytest

from tools import windows_preflight_archive as verifier
from tools import windows_preflight_validation as writer


REVISION = 'c5f3b879fa2043fd2aedd6ccaf61fb3f87e088a8'
STAMP = '2026-11-15T00:00:00+00:00'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('utf-8')


def load(root, name):
    return json.loads((root / name).read_bytes())


def junit(skipped=False):
    root = ET.Element('testsuites')
    suite = ET.SubElement(root, 'testsuite', tests='162', failures='0', errors='0',
                          skipped='1' if skipped else '0')
    for index in range(158):
        ET.SubElement(suite, 'testcase', classname='tests.product.test_windows_runtime_preflight',
                      name=f'test_invented_preflight_{index:03}')
    for index in range(4):
        name = ('test_native_windows_change_time_detects_same_size_write_with_restored_mtime'
                if index == 0 else f'test_invented_file_state_{index}')
        case = ET.SubElement(suite, 'testcase', classname='tests.product.test_file_state', name=name)
        if index == 0 and skipped:
            ET.SubElement(case, 'skipped', message='Synthetic skip, not native execution')
    return ET.tostring(root, encoding='utf-8')


def build_archive(root, *, skipped=False):
    archive = writer.Archive(root)
    host = {'os': 'linux', 'native_windows': False, 'python': '3.12.0', 'architecture': 'x64'}
    source = {'head': REVISION, 'baseline': writer.BASELINE, 'branch': writer.BRANCH,
              'pins': {name: {'git_blob': '1' * 40, 'working_tree_sha256': '2' * 64,
                              'normalized_sha256': '3' * 64} for name in writer.PINS},
              'harness_files': {name: '4' * 64 for name in writer.ADDITIONS}}
    archive.json('STARTED.json', {'schema_version': 1, 'started_at_utc': STAMP,
                 'source_revision': REVISION, 'reviewed_baseline': writer.BASELINE, 'host': host,
                 'runtime_qualified': False, 'concurrent_path_isolation': False})
    archive.write('pytest/console.log', b'Invented synthetic test log; not actual test execution.\n')
    xml = junit(skipped)
    archive.write('pytest/results.xml', xml)
    assessments = writer._synthetic_assessments(archive)
    result = {'schema_version': 1, 'kind': 'firmavex_controlled_windows_preflight_validation',
              'status': 'completed_with_unverified_cases' if skipped else 'completed',
              'evidence_class': 'portable_synthetic_validation', 'host': host,
              'native_windows_verified': False, 'checkout_verified': False, 'working_tree_dirty': True,
              'powershell': {'version': None, 'source': 'wrapper_supplied_not_authenticated'},
              'source': source, 'started_at_utc': STAMP, 'ended_at_utc': STAMP,
              'tests': writer.junit_counts(xml), 'assessments': assessments,
              'runtime_qualified': False, 'signature_trust': 'not_assessed',
              'concurrent_path_isolation': False,
              'private_logs': ['pytest/console.log', 'pytest/results.xml'],
              'checksum_scope': 'listed_files_only_not_recursive_fixture_or_temp_inventory'}
    archive.seal(result)
    return root


@pytest.fixture
def archive(tmp_path):
    return build_archive(tmp_path / 'synthetic archive with spaces')


def reseal(root):
    """Deliberately update invented checksums to test deeper consistency checks."""
    names = [line[66:] for line in (root / 'SHA256SUMS').read_text('ascii').splitlines()]
    rows = ''.join(sha((root / name).read_bytes()) + '  ' + name + '\n' for name in names)
    (root / 'SHA256SUMS').write_text(rows, encoding='ascii')
    complete = load(root, 'COMPLETE.json')
    complete['result_sha256'] = sha((root / 'result.json').read_bytes())
    complete['inventory_sha256'] = sha((root / 'SHA256SUMS').read_bytes())
    (root / 'COMPLETE.json').write_bytes(json_bytes(complete))


def change_json(root, name, mutate, *, seal=True):
    record = load(root, name)
    mutate(record)
    (root / name).write_bytes(json_bytes(record))
    if seal:
        reseal(root)


def failed_marker(root, **changes):
    record = {'schema_version': 1, 'status': 'failed', 'code': 'validation_interrupted_or_failed',
              'interrupted': True, 'runtime_qualified': False}
    record.update(changes)
    (root / 'FAILED.json').write_bytes(json_bytes(record))


def assert_rejected(report):
    assert report['integrity']['state'] in {'missing', 'mismatch', 'blocked'}, report
    assert report['evidence']['native_execution'] == 'not_assessed'


def test_valid_invented_archive_is_consistent_but_not_authenticated_or_native(archive):
    report = verifier.verify_archive(archive)
    assert report['integrity']['state'] == 'verified', report
    assert report['workflow'] == 'completed'
    assert report['tests'] == writer.junit_counts(junit())
    assert report['evidence']['declared_class'] == 'portable_synthetic_validation'
    assert report['evidence']['native_execution'] == 'not_assessed'
    assert report['evidence']['supplied_inputs'] == 'not_assessed'
    assert report['evidence']['source_authenticity'] == 'not_assessed'
    assert report['coverage']['listed_files'] > 20


def test_verification_never_writes_executes_or_accesses_network_and_is_repeatable(archive, monkeypatch):
    before = {str(path.relative_to(archive)): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in archive.rglob('*') if path.is_file()}
    original_open = Path.open
    original_builtin_open = builtins.open
    original_os_open = os.open
    def read_only_open(path, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+')
        return original_open(path, mode, *args, **kwargs)
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline verification attempted execution, network, or writing')
    def read_only_builtin(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+')
        return original_builtin_open(file, mode, *args, **kwargs)
    def read_only_os_open(file, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return original_os_open(file, flags, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', read_only_open)
    monkeypatch.setattr(builtins, 'open', read_only_builtin)
    monkeypatch.setattr(os, 'open', read_only_os_open)
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    one = verifier.verify_archive(archive)
    two = verifier.verify_archive(archive)
    assert one == two and one['integrity']['state'] == 'verified'
    after = {str(path.relative_to(archive)): (path.read_bytes(), path.stat().st_mtime_ns)
             for path in archive.rglob('*') if path.is_file()}
    assert before == after


def test_failed_marker_overrides_complete_even_when_other_checksums_match(archive):
    failed_marker(archive)
    report = verifier.verify_archive(archive)
    assert report['workflow'] == 'failed'
    assert verifier.main(['--archive', str(archive)]) != 0


def test_failed_partial_archive_remains_failed(tmp_path):
    root = tmp_path / 'partial failure'
    root.mkdir()
    failed_marker(root)
    report = verifier.verify_archive(root)
    assert report['workflow'] == 'failed'
    assert report['integrity']['state'] != 'verified'


def test_malformed_failed_marker_still_prevents_success(archive):
    (archive / 'FAILED.json').write_bytes(b'{broken')
    report = verifier.verify_archive(archive)
    assert report['workflow'] == 'failed'
    assert_rejected(report)


def test_interrupted_archive_without_completion_stays_incomplete(archive):
    (archive / 'COMPLETE.json').unlink()
    report = verifier.verify_archive(archive)
    assert report['workflow'] == 'incomplete'
    assert_rejected(report)


def test_missing_checksums_are_not_a_pass(archive):
    (archive / 'SHA256SUMS').unlink()
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('name', ['STARTED.json', 'result.json', 'pytest/results.xml',
                                 'assessments/missing/first.json'], ids=['start', 'result', 'junit', 'assessment'])
def test_truncated_listed_files_fail_integrity(archive, name):
    path = archive / name
    path.write_bytes(path.read_bytes()[:7])
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('mutation', ['wrong_digest', 'duplicate', 'case_alias', 'traversal', 'backslash',
                                    'absolute', 'ads', 'single_space', 'no_newline'],
                         ids=['digest', 'duplicate', 'alias', 'parent', 'backslash', 'absolute', 'ads', 'separator', 'newline'])
def test_ambiguous_or_unsafe_checksum_entries_are_rejected(archive, mutation):
    path = archive / 'SHA256SUMS'
    rows = path.read_text('ascii').splitlines(keepends=True)
    digest, name = rows[0][:64], rows[0][66:-1]
    if mutation == 'wrong_digest':
        rows[0] = '0' * 64 + '  ' + name + '\n'
    elif mutation == 'duplicate':
        rows.append(rows[0])
    elif mutation == 'case_alias':
        rows.append(digest + '  ' + name.upper() + '\n')
    elif mutation == 'traversal':
        rows[0] = digest + '  ../NEVER-READ\n'
    elif mutation == 'backslash':
        rows[0] = digest + '  pytest\\results.xml\n'
    elif mutation == 'absolute':
        rows[0] = digest + '  /NEVER-READ\n'
    elif mutation == 'ads':
        rows[0] = digest + '  result.json:stream\n'
    elif mutation == 'single_space':
        rows[0] = digest + ' ' + name + '\n'
    else:
        rows[-1] = rows[-1].rstrip('\n')
    path.write_text(''.join(rows), encoding='ascii')
    # Avoid testing just the checksum-of-inventory mismatch.
    complete = load(archive, 'COMPLETE.json')
    complete['inventory_sha256'] = sha(path.read_bytes())
    (archive / 'COMPLETE.json').write_bytes(json_bytes(complete))
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('payload', [b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}',
                                   b'{bad', b'[]', b'\xff', b'\0{}'],
                         ids=['duplicate', 'nonfinite', 'malformed', 'array', 'utf8', 'nul'])
def test_malformed_completion_metadata_is_rejected(archive, payload):
    (archive / 'COMPLETE.json').write_bytes(payload)
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize(('name', 'key', 'value'), [
    ('COMPLETE.json', 'schema_version', True),
    ('COMPLETE.json', 'kind', 'different_writer'),
    ('COMPLETE.json', 'runtime_qualified', True),
    ('COMPLETE.json', 'concurrent_path_isolation', True),
    ('COMPLETE.json', 'result_sha256', 'a' * 64),
    ('result.json', 'status', 'success'),
    ('result.json', 'runtime_qualified', True),
    ('result.json', 'signature_trust', 'verified'),
    ('result.json', 'checksum_scope', 'recursive_all_files'),
    ('result.json', 'evidence_class', 'fully_qualified_windows'),
], ids=['boolschema', 'wrongkind', 'runtime', 'isolation', 'resultdigest', 'status', 'result_runtime', 'trust', 'scope', 'class'])
def test_invalid_metadata_states_fail_closed(archive, name, key, value):
    change_json(archive, name, lambda row: row.__setitem__(key, value), seal=name != 'COMPLETE.json')
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('key', ['source_revision', 'reviewed_baseline', 'started_at_utc'],
                         ids=['revision', 'baseline', 'starttime'])
def test_start_and_result_context_must_agree(archive, key):
    change_json(archive, 'STARTED.json', lambda row: row.__setitem__(key, 'different'))
    assert_rejected(verifier.verify_archive(archive))


def test_junit_and_result_counts_must_agree_even_with_recomputed_hashes(archive):
    change_json(archive, 'result.json', lambda row: row['tests'].__setitem__('passed', 161))
    assert_rejected(verifier.verify_archive(archive))


def test_skips_are_preserved_as_unverified_not_converted_to_native_success(tmp_path):
    root = build_archive(tmp_path / 'skipped', skipped=True)
    report = verifier.verify_archive(root)
    assert report['integrity']['state'] == 'verified', report
    assert report['workflow'] == 'completed_with_unverified_cases'
    assert report['tests']['skipped'] == 1
    assert report['tests']['required_ntfs_case'] == 'skipped'
    assert verifier.main(['--archive', str(root)]) == 1


@pytest.mark.parametrize('payload', [b'<!DOCTYPE x [<!ENTITY secret "hidden">]><testsuites/>',
                                   b'\xff\xfe<\x00!\x00D\x00O\x00C\x00T\x00Y\x00P\x00E\x00',
                                   b'<testsuites><testcase>'], ids=['entity', 'utf16', 'truncated'])
def test_malformed_or_entity_xml_is_rejected(archive, payload):
    (archive / 'pytest/results.xml').write_bytes(payload)
    reseal(archive)
    assert_rejected(verifier.verify_archive(archive))


def test_changed_input_fixture_is_detected_even_if_all_file_checksums_are_updated(archive):
    (archive / 'fixtures/normal_path/ordinary path/example.txt').write_bytes(b'modified synthetic input\n')
    reseal(archive)
    assert_rejected(verifier.verify_archive(archive))


def test_inventory_digest_must_match_retained_fixture(archive):
    def mutate(row):
        row['assessments']['missing']['inventory']['files']['manifest']['sha256'] = 'a' * 64
    change_json(archive, 'result.json', mutate)
    assert_rejected(verifier.verify_archive(archive))


def test_repeated_assessment_records_must_agree(archive):
    change_json(archive, 'assessments/missing/second.json', lambda row: row.__setitem__('status', 'blocked'))
    assert_rejected(verifier.verify_archive(archive))


def test_false_input_immutability_claim_is_rejected(archive):
    change_json(archive, 'result.json', lambda row: row['assessments']['missing'].__setitem__('inputs_unchanged', False))
    assert_rejected(verifier.verify_archive(archive))


def test_native_label_with_non_windows_host_is_inconsistent(archive):
    change_json(archive, 'result.json', lambda row: row.__setitem__('evidence_class', 'native_functional_preflight'))
    assert_rejected(verifier.verify_archive(archive))


def test_matching_native_claims_still_do_not_authenticate_native_execution(archive):
    result = load(archive, 'result.json')
    result['evidence_class'] = 'native_functional_preflight'
    result['host'].update(os='windows', native_windows=True)
    result['powershell']['version'] = '7.5.0'
    for key in ('native_windows_verified', 'checkout_verified', 'working_tree_dirty'):
        result.pop(key)
    (archive / 'result.json').write_bytes(json_bytes(result))
    change_json(archive, 'STARTED.json', lambda row: row['host'].update(os='windows', native_windows=True))
    report = verifier.verify_archive(archive)
    assert report['integrity']['state'] == 'verified', report
    assert report['evidence']['declared_class'] == 'native_functional_preflight'
    assert report['evidence']['native_execution'] == 'not_assessed'


def test_missing_optional_supplied_assessment_remains_not_assessed(archive):
    report = verifier.verify_archive(archive)
    assert report['evidence']['supplied_inputs'] == 'not_assessed'
    assert report['integrity']['state'] == 'verified'


def test_unexpected_file_fails_without_leaking_its_name_or_contents(archive):
    secret = 'PRIVATE-CUSTOMER-SECRET'
    (archive / (secret + '.txt')).write_bytes(secret.encode())
    report = verifier.verify_archive(archive)
    assert_rejected(report)
    assert secret not in json.dumps(report)
    assert str(archive) not in json.dumps(report)


def test_explicit_temporary_trees_are_not_recursed_or_misrepresented(archive, monkeypatch):
    temporary = archive / 'pytest/temporary-root'
    temporary.mkdir()
    (temporary / 'UNASSESSED-PRIVATE').write_bytes(b'not integrity covered')
    original = os.scandir
    def scan(path):
        assert Path(path) != temporary, 'Uncovered temporary tree was enumerated'
        return original(path)
    monkeypatch.setattr(os, 'scandir', scan)
    report = verifier.verify_archive(archive)
    assert report['integrity']['state'] == 'verified', report
    assert report['coverage']['excluded_temporary_trees'] == 1
    assert 'UNASSESSED-PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('raw', ['../never-open', '/workspace/FIRMAVEX/never-open',
                               'evidence/windows-sandbox/never-open', r'\\server\share\never-open',
                               'ordinary./never-open', 'CON/never-open'],
                         ids=['traversal', 'original', 'protected', 'unc', 'alias', 'device'])
def test_unsafe_archive_argument_is_refused_before_filesystem_access(raw, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Unsafe argument reached filesystem')
    monkeypatch.setattr(Path, 'stat', forbidden)
    monkeypatch.setattr(Path, 'lstat', forbidden)
    monkeypatch.setattr(os, 'scandir', forbidden)
    assert_rejected(verifier.verify_archive(raw))


def test_linked_archive_member_is_rejected_without_reading_target(archive, tmp_path, monkeypatch):
    target = tmp_path / 'outside-private-file'
    target.write_bytes(b'private outside bytes')
    member = archive / 'summary.txt'
    member.unlink()
    try:
        member.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('Local filesystem cannot create synthetic symlinks')
    original = verifier.read_bytes
    def bounded(path, maximum, **kwargs):
        assert Path(path) != target
        return original(path, maximum, **kwargs)
    monkeypatch.setattr(verifier, 'read_bytes', bounded)
    assert_rejected(verifier.verify_archive(archive))


def test_parent_symlink_is_rejected(tmp_path, archive):
    linked = tmp_path / 'linked-root'
    try:
        linked.symlink_to(archive, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Local filesystem cannot create synthetic symlinks')
    assert_rejected(verifier.verify_archive(linked))


def test_hardlinked_archive_member_is_rejected(archive, tmp_path):
    try:
        os.link(archive / 'summary.txt', tmp_path / 'same-file-hardlink')
    except (OSError, NotImplementedError):
        pytest.skip('Local filesystem cannot create synthetic hardlinks')
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('control', [KeyboardInterrupt('private'), SystemExit(19), BaseException('private')],
                         ids=['keyboard', 'exit', 'base'])
def test_control_flow_exceptions_propagate_without_becoming_report(archive, monkeypatch, control):
    def interrupt(*args, **kwargs):
        raise control
    monkeypatch.setattr(verifier, 'read_bytes', interrupt)
    with pytest.raises(type(control)) as caught:
        verifier.verify_archive(archive)
    assert caught.value is control


def test_observable_mid_capture_change_is_rejected(archive, monkeypatch):
    original = verifier.read_bytes
    changed = False
    def change(path, maximum, **kwargs):
        nonlocal changed
        data = original(path, maximum, **kwargs)
        if not changed:
            changed = True
            (archive / 'summary.txt').write_bytes(b'changed during observation')
        return data
    monkeypatch.setattr(verifier, 'read_bytes', change)
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize(('name', 'limit'), [('MAX_FILES', 1), ('MAX_FILE_BYTES', 8), ('MAX_TOTAL_BYTES', 16)],
                         ids=['filecount', 'filebytes', 'aggregate'])
def test_resource_bounds_fail_closed(archive, monkeypatch, name, limit):
    monkeypatch.setattr(verifier, name, limit)
    assert_rejected(verifier.verify_archive(archive))


def test_private_log_content_never_reaches_machine_or_human_report(archive, capsys):
    marker = r'C:\Users\PRIVATE-PERSON\PRIVATE-ACCESS-TOKEN'
    (archive / 'pytest/console.log').write_bytes(marker.encode())
    reseal(archive)
    assert verifier.main(['--archive', str(archive)]) == 0
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err
    assert str(archive) not in captured.out + captured.err
    report = json.loads(captured.out)
    assert report['integrity']['state'] == 'verified'
    assert captured.err.strip()


def test_checksum_inventory_cannot_silently_drop_a_retained_member(archive):
    path = archive / 'SHA256SUMS'
    rows = path.read_text('ascii').splitlines(keepends=True)
    path.write_text(''.join(row for row in rows if not row.endswith('  summary.txt\n')), encoding='ascii')
    change_json(archive, 'COMPLETE.json', lambda row: row.__setitem__('inventory_sha256', sha(path.read_bytes())), seal=False)
    assert_rejected(verifier.verify_archive(archive))


def test_checksum_inventory_cannot_claim_its_own_hash_or_completion(archive):
    path = archive / 'SHA256SUMS'
    path.write_text(path.read_text('ascii') + '0' * 64 + '  COMPLETE.json\n', encoding='ascii')
    change_json(archive, 'COMPLETE.json', lambda row: row.__setitem__('inventory_sha256', sha(path.read_bytes())), seal=False)
    assert_rejected(verifier.verify_archive(archive))


def test_failed_marker_precedence_survives_corrupt_completion(archive):
    failed_marker(archive)
    (archive / 'COMPLETE.json').write_bytes(b'not json')
    report = verifier.verify_archive(archive)
    assert report['workflow'] == 'failed'
    assert_rejected(report)


def test_result_test_counts_reject_bool_integer_alias(archive):
    change_json(archive, 'result.json', lambda row: row['tests'].__setitem__('errors', False))
    assert_rejected(verifier.verify_archive(archive))


def test_linked_temporary_tree_root_is_rejected_without_scanning_target(archive, tmp_path, monkeypatch):
    outside = tmp_path / 'outside scratch'
    outside.mkdir()
    (outside / 'never-enumerate').write_bytes(b'private')
    link = archive / 'pytest/process-temp'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Local filesystem cannot create synthetic symlinks')
    original = os.scandir
    def scan(path):
        assert Path(path) not in {outside, link}, 'Linked temporary tree was enumerated'
        return original(path)
    monkeypatch.setattr(os, 'scandir', scan)
    assert_rejected(verifier.verify_archive(archive))


def test_json_nesting_bound_is_enforced(archive):
    payload = ('[' * 100 + '0' + ']' * 100).encode()
    (archive / 'COMPLETE.json').write_bytes(payload)
    assert_rejected(verifier.verify_archive(archive))


def update_repeated_report(root, case, record):
    for name in ('first.json', 'second.json'):
        (root / 'assessments' / case / name).write_bytes(json_bytes(record))
    (root / 'assessments' / case / 'summary.txt').write_bytes(writer.preflight.summary(record).encode('utf-8'))
    reseal(root)


def test_changed_fixed_fixture_is_rejected_even_with_coherent_regenerated_assessments(archive):
    fixture = archive / 'fixtures/normal_path'
    payload = b'Internally consistent, but not the fixed Batch 35 demonstration input.\n'
    (fixture / 'ordinary path/example.txt').write_bytes(payload)
    manifest = load(fixture, 'manifest.json')
    manifest['artifacts']['application']['sha256'] = sha(payload)
    (fixture / 'manifest.json').write_bytes(json_bytes(manifest))
    report = writer.preflight.preflight(fixture / 'manifest.json')
    update_repeated_report(archive, 'normal_path', report)
    inventory = writer.snapshot(fixture / 'manifest.json', fixture)
    change_json(archive, 'result.json',
                lambda row: row['assessments']['normal_path'].__setitem__('inventory', inventory))
    assert_rejected(verifier.verify_archive(archive))


def test_assessment_counts_reject_bool_integer_alias(archive):
    report = load(archive, 'assessments/missing/first.json')
    zero = next(key for key, count in report['counts'].items() if count == 0)
    report['counts'][zero] = False
    update_repeated_report(archive, 'missing', report)
    assert_rejected(verifier.verify_archive(archive))


def test_assessment_unknown_state_cannot_be_hidden_by_recomputed_counts(archive):
    report = load(archive, 'assessments/missing/first.json')
    report['checks']['native_capabilities']['state'] = 'unexpected_new_state'
    report = writer.preflight._finish_report({key: value for key, value in report.items()
                                            if key not in {'counts', 'status'}})
    update_repeated_report(archive, 'missing', report)
    assert_rejected(verifier.verify_archive(archive))


def test_changed_entry_set_during_verification_is_rejected(archive, monkeypatch):
    original = verifier.read_bytes
    changed = False
    def change(path, maximum, **kwargs):
        nonlocal changed
        data = original(path, maximum, **kwargs)
        if not changed:
            changed = True
            (archive / 'new-private-entry.txt').write_bytes(b'new during verification')
        return data
    monkeypatch.setattr(verifier, 'read_bytes', change)
    assert_rejected(verifier.verify_archive(archive))


def test_changed_completion_metadata_during_final_reread_is_rejected(archive, monkeypatch):
    original = verifier.read_bytes
    first_reads = 0
    def change(path, maximum, **kwargs):
        nonlocal first_reads
        data = original(path, maximum, **kwargs)
        if Path(path).name == 'COMPLETE.json':
            first_reads += 1
            if first_reads == 1:
                value = json.loads(data)
                value['result_sha256'] = 'b' * 64
                Path(path).write_bytes(json_bytes(value))
        return data
    monkeypatch.setattr(verifier, 'read_bytes', change)
    assert_rejected(verifier.verify_archive(archive))


def add_supplied_assessment(archive, tmp_path, *, present=False):
    staging = tmp_path / 'private supplied inputs'
    staging.mkdir()
    manifest = staging / 'manifest.json'
    if present:
        (staging / 'not-retained.exe').write_bytes(b'Invented tiny text file, not executable firmware.')
    manifest.write_bytes(json_bytes({'schema_version': 1, 'artifacts': {'qemu': {'path': 'not-retained.exe'}}}))
    generated = writer.Archive(tmp_path / 'synthetic supplied report generation')
    assessment = writer.assess_manifest(manifest, staging, generated, 'supplied',
                                        input_class='operator_supplied_unverified')
    destination = archive / 'assessments/supplied'
    destination.mkdir()
    checksum_names = [line[66:] for line in (archive / 'SHA256SUMS').read_text('ascii').splitlines()]
    for name in ('first.json', 'second.json', 'summary.txt'):
        relative = 'assessments/supplied/' + name
        (archive / relative).write_bytes((generated.root / relative).read_bytes())
        checksum_names.append(relative)
    result = load(archive, 'result.json')
    result['assessments']['supplied'] = assessment
    (archive / 'result.json').write_bytes(json_bytes(result))
    (archive / 'SHA256SUMS').write_text(''.join('0' * 64 + '  ' + name + '\n'
                                             for name in sorted(checksum_names)), encoding='ascii')
    reseal(archive)
    return staging, manifest


def test_optional_supplied_inventory_is_not_mistaken_for_original_file_verification(archive, tmp_path, monkeypatch):
    staging, manifest = add_supplied_assessment(archive, tmp_path)
    original = verifier.read_bytes
    def no_external_read(path, maximum, **kwargs):
        assert staging not in Path(path).parents and Path(path) != manifest
        return original(path, maximum, **kwargs)
    monkeypatch.setattr(verifier, 'read_bytes', no_external_read)
    report = verifier.verify_archive(archive)
    assert report['integrity']['state'] == 'verified', report
    assert report['evidence']['supplied_inputs'] == 'not_assessed'
    assert not (archive / 'not-retained.exe').exists()
    assert str(staging) not in json.dumps(report)


def test_complete_marker_cannot_cover_failing_test_outcomes(archive):
    xml = ET.fromstring((archive / 'pytest/results.xml').read_bytes())
    suite = xml.find('testsuite')
    suite.set('failures', '1')
    ET.SubElement(suite.find('testcase'), 'failure', message='invented failure')
    payload = ET.tostring(xml, encoding='utf-8')
    (archive / 'pytest/results.xml').write_bytes(payload)
    change_json(archive, 'result.json', lambda row: row.__setitem__('tests', writer.junit_counts(payload)))
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('control', [KeyboardInterrupt('private'), SystemExit(23), BaseException('private')],
                         ids=['keyboard', 'exit', 'base'])
def test_cli_preserves_control_flow_without_emitting_fake_result(monkeypatch, capsys, control):
    def interrupt(*args, **kwargs):
        raise control
    monkeypatch.setattr(verifier, 'verify_archive', interrupt)
    with pytest.raises(type(control)) as caught:
        verifier.main(['--archive', 'synthetic-argument-only'])
    assert caught.value is control
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize(('size', 'accepted'), [(17 * 1024**2, True), (64 * 1024**2, True),
                                              (64 * 1024**2 + 1, False)], ids=['17mib', '64mib', 'over64mib'])
def test_supplied_recorded_identity_uses_input_limit_not_archive_member_limit(archive, tmp_path, size, accepted):
    # These are invented declarations, not claims that a large file was read here.
    add_supplied_assessment(archive, tmp_path, present=True)
    report = load(archive, 'assessments/supplied/first.json')
    report['artifacts']['qemu']['file']['size_bytes'] = size
    update_repeated_report(archive, 'supplied', report)
    change_json(archive, 'result.json', lambda row: row['assessments']['supplied']['inventory']['files']['qemu'].__setitem__('size_bytes', size))
    result = verifier.verify_archive(archive)
    if accepted:
        assert result['integrity']['state'] == 'verified', result
        assert result['evidence']['supplied_inputs'] == 'not_assessed'
    else:
        assert_rejected(result)


def test_supplied_inventory_digest_contradicting_recorded_report_is_rejected(archive, tmp_path):
    add_supplied_assessment(archive, tmp_path, present=True)
    change_json(archive, 'result.json', lambda row: row['assessments']['supplied']['inventory']['files']['qemu'].__setitem__('sha256', 'f' * 64))
    assert_rejected(verifier.verify_archive(archive))


def test_finite_syntax_with_infinite_json_exponent_is_rejected(archive):
    (archive / 'COMPLETE.json').write_bytes(b'{"schema_version":1,"oversized_number":1e9999999}')
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize(('key', 'value'), [('tests', '161'), ('failures', '1'), ('errors', '1'), ('skipped', '1')],
                         ids=['tests', 'failures', 'errors', 'skipped'])
def test_junit_declared_counts_cannot_contradict_cases(archive, key, value):
    xml = ET.fromstring((archive / 'pytest/results.xml').read_bytes())
    xml.find('testsuite').set(key, value)
    (archive / 'pytest/results.xml').write_bytes(ET.tostring(xml, encoding='utf-8'))
    reseal(archive)
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize(('field', 'value'), [('source', []), ('host', []),
                                            ('source', {'head': []}), ('host', {'os': []})],
                         ids=['sourcelist', 'hostlist', 'sourcefield', 'hostfield'])
def test_malformed_source_and_host_containers_fail_as_sanitized_reports(archive, field, value):
    change_json(archive, 'result.json', lambda row: row.__setitem__(field, value))
    assert_rejected(verifier.verify_archive(archive))


def test_failed_partial_archive_retains_junit_failure_accounting_without_result(tmp_path):
    root = tmp_path / 'partial invented failure'
    root.mkdir()
    (root / 'pytest').mkdir()
    xml = ET.fromstring(junit())
    suite = xml.find('testsuite')
    suite.set('failures', '1')
    ET.SubElement(suite.find('testcase'), 'failure', message='invented failed synthetic assertion')
    (root / 'pytest/results.xml').write_bytes(ET.tostring(xml, encoding='utf-8'))
    failed_marker(root, interrupted=False, code='synthetic_regressions_failed')
    report = verifier.verify_archive(root)
    assert report['workflow'] == 'failed'
    assert report['tests']['cases'] == 162
    assert report['tests']['failed'] == 1
    assert report['tests']['passed'] == 161
    assert report['integrity']['state'] != 'verified'
    assert report['evidence']['native_execution'] == 'not_assessed'


def test_checksum_failure_does_not_override_failed_workflow_or_junit_observations(archive):
    failed_marker(archive)
    (archive / 'summary.txt').write_bytes(b'modified despite failed workflow')
    report = verifier.verify_archive(archive)
    assert report['workflow'] == 'failed'
    assert report['integrity']['state'] == 'mismatch'
    assert report['tests']['cases'] == 162
    assert report['tests']['passed'] == 162
    assert report['evidence']['native_execution'] == 'not_assessed'


@pytest.mark.parametrize('name', ['pytest/results.xml', 'pytest/console.log', 'summary.txt'])
def test_required_member_cannot_be_removed_even_with_recomputed_inventory(archive, name):
    (archive / name).unlink()
    inventory = archive / 'SHA256SUMS'
    rows = inventory.read_text('ascii').splitlines(keepends=True)
    inventory.write_text(''.join(row for row in rows if not row.endswith('  ' + name + '\n')), encoding='ascii')
    change_json(archive, 'COMPLETE.json',
                lambda row: row.__setitem__('inventory_sha256', sha(inventory.read_bytes())), seal=False)
    report = verifier.verify_archive(archive)
    assert_rejected(report)
    assert report['workflow'] != 'completed'


def test_fixed_fixture_schema_rejects_boolean_integer_alias(archive):
    change_json(archive, 'fixtures/missing/manifest.json', lambda row: row.__setitem__('schema_version', True))
    fixture = archive / 'fixtures/missing/manifest.json'
    inventory = load(archive, 'result.json')['assessments']['missing']['inventory']
    inventory['files']['manifest']['sha256'] = sha(fixture.read_bytes())
    inventory['files']['manifest']['size_bytes'] = fixture.stat().st_size
    change_json(archive, 'result.json', lambda row: row['assessments']['missing'].__setitem__('inventory', inventory))
    assert_rejected(verifier.verify_archive(archive))


def test_directory_checks_do_not_use_file_only_windows_handle_reader(archive, monkeypatch):
    original = verifier.path_state
    def files_only(path, *args, **kwargs):
        assert not Path(path).is_dir(), 'File-only Windows handle reader received a directory'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(verifier, 'path_state', files_only)
    report = verifier.verify_archive(archive)
    assert report['integrity']['state'] == 'verified'
    assert report['native_windows_verified'] is False


def test_supplied_present_report_requires_corresponding_inventory_entry(archive, tmp_path):
    add_supplied_assessment(archive, tmp_path, present=True)
    change_json(archive, 'result.json',
                lambda row: row['assessments']['supplied']['inventory']['files'].pop('qemu'))
    assert_rejected(verifier.verify_archive(archive))


def invented_identity():
    return {'state': 'present', 'sha256': 'c' * 64, 'size_bytes': 1,
            'state_fingerprint': 'd' * 64}


def test_supplied_file_not_found_cannot_have_present_inventory_identity(archive, tmp_path):
    add_supplied_assessment(archive, tmp_path, present=False)
    change_json(archive, 'result.json',
                lambda row: row['assessments']['supplied']['inventory']['files'].__setitem__('qemu', invented_identity()))
    assert_rejected(verifier.verify_archive(archive))


def test_unsupplied_role_cannot_have_invented_inventory_identity(archive, tmp_path):
    add_supplied_assessment(archive, tmp_path, present=False)
    change_json(archive, 'result.json',
                lambda row: row['assessments']['supplied']['inventory']['files'].__setitem__('gdb', invented_identity()))
    assert_rejected(verifier.verify_archive(archive))


def test_repeated_reports_require_exact_types_not_python_bool_integer_equality(archive):
    second = load(archive, 'assessments/missing/second.json')
    zero = next(key for key, count in second['counts'].items() if count == 0)
    second['counts'][zero] = False
    (archive / 'assessments/missing/second.json').write_bytes(json_bytes(second))
    reseal(archive)
    assert_rejected(verifier.verify_archive(archive))


def test_started_host_bool_integer_alias_cannot_match_result_host(archive):
    change_json(archive, 'STARTED.json', lambda row: row['host'].__setitem__('native_windows', 0))
    assert_rejected(verifier.verify_archive(archive))


def test_recorded_python_must_satisfy_writer_minimum_version(archive):
    change_json(archive, 'result.json', lambda row: row['host'].__setitem__('python', '3.10.14'))
    change_json(archive, 'STARTED.json', lambda row: row['host'].__setitem__('python', '3.10.14'))
    assert_rejected(verifier.verify_archive(archive))


def test_inventory_cannot_add_unreported_supplied_companion(archive, tmp_path):
    add_supplied_assessment(archive, tmp_path, present=True)
    fabricated = {'state': 'present', 'sha256': 'f' * 64, 'size_bytes': 1, 'state_fingerprint': 'a' * 64}
    change_json(archive, 'result.json', lambda row: row['assessments']['supplied']['inventory']['files'].__setitem__('companion_001', fabricated))
    assert_rejected(verifier.verify_archive(archive))


@pytest.mark.parametrize('change', ['unknown_artifact', 'missing_role', 'unknown_receipt', 'missing_receipt'],
                         ids=['unknown-artifact', 'missing-role', 'unknown-receipt', 'missing-receipt'])
def test_per_input_report_structure_matches_writer_contract(archive, tmp_path, change):
    add_supplied_assessment(archive, tmp_path, present=True)
    record = load(archive, 'assessments/supplied/first.json')
    if change == 'unknown_artifact':
        record['artifacts']['invented'] = {'file': {}}
    elif change == 'missing_role':
        record['artifacts'].pop('gdb')
    elif change == 'unknown_receipt':
        record['receipts']['invented'] = {'file': {}}
    else:
        record['receipts'].pop('licensing')
    record = writer.preflight._finish_report({key: value for key, value in record.items()
                                            if key not in {'status', 'counts'}})
    update_repeated_report(archive, 'supplied', record)
    assert_rejected(verifier.verify_archive(archive))


def test_recorded_input_inventory_cannot_exceed_writer_aggregate_limit(archive, tmp_path):
    add_supplied_assessment(archive, tmp_path, present=True)
    record = load(archive, 'result.json')
    inventory = record['assessments']['supplied']['inventory']['files']
    for index in range(3):
        inventory[f'companion_{index + 1:03}'] = {
            'state': 'present', 'sha256': 'd' * 64,
            'size_bytes': writer.preflight.MAX_FILE_BYTES, 'state_fingerprint': 'e' * 64}
    (archive / 'result.json').write_bytes(json_bytes(record))
    reseal(archive)
    result = verifier.verify_archive(archive)
    assert_rejected(result)
    assert result['integrity']['code'] == 'input_inventory_bound'
