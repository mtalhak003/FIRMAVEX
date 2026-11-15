"""Read-only, offline consistency verifier for Batch 35 directory archives.

Checksums and mutually agreeing records do not authenticate their source. No
archive contents execute. Stable developer-controlled local trees are required;
observable race detection is not an atomic snapshot or hostile-path isolation.
"""
import argparse
from datetime import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from firmavex.backends.security import bounded_reads, checked_path, read_bytes
from firmavex.product.file_state import path_state
from tools import windows_preflight_validation as writer
from tools import windows_runtime_preflight as preflight

MAX_FILES = 128
MAX_ENTRIES = 256
MAX_FILE_BYTES = 16 * 1024**2
MAX_TOTAL_BYTES = 32 * 1024**2
MAX_JSON_BYTES = 1024**2
CASES = ('missing', 'lexical_refusal', 'normal_path', 'malformed_receipt')
EXCLUDED = frozenset({'pytest/process-temp', 'pytest/temporary-root'})
FIXTURES = {
    'missing': {'manifest': 'manifest.json'},
    'lexical_refusal': {'manifest': 'manifest.json'},
    'normal_path': {'manifest': 'manifest.json', 'application': 'ordinary path/example.txt'},
    'malformed_receipt': {'manifest': 'manifest.json', 'receipt_runtime_observations': 'receipt.json'},
}
ROOT_FILES = {'STARTED.json', 'result.json', 'summary.txt', 'SHA256SUMS', 'COMPLETE.json', 'FAILED.json',
              'pytest/console.log', 'pytest/results.xml'}
FIXTURE_FILES = {f'fixtures/{case}/{name}' for case, items in FIXTURES.items() for name in items.values()}
ASSESSMENT_FILES = {f'assessments/{case}/{name}' for case in (*CASES, 'supplied')
                    for name in ('first.json', 'second.json', 'summary.txt')}
ALLOWED_FILES = ROOT_FILES | FIXTURE_FILES | ASSESSMENT_FILES
ALLOWED_DIRS = set(EXCLUDED)
for _name in ALLOWED_FILES | set(EXCLUDED):
    ALLOWED_DIRS.update('/'.join(_name.split('/')[:i]) for i in range(1, len(_name.split('/'))))


class ArchiveError(ValueError):
    def __init__(self, code, state='blocked'):
        super().__init__(code)
        self.code, self.state = code, state


def require(value, code, state='mismatch'):
    if not value:
        raise ArchiveError(code, state)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _digest(value, width=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(width) + '}', value) is not None


def _integer(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _fields(value, names):
    require(type(value) is dict and set(value) == set(names), 'invalid_metadata')


def _schema(value):
    require(type(value) is dict and type(value.get('schema_version')) is int
            and value['schema_version'] == 1, 'unsupported_schema')


def _false(value, names):
    require(all(value.get(name) is False for name in names), 'contradictory_security_claim')


def _relative(name):
    require(type(name) is str and 0 < len(name) <= 180 and '\\' not in name
            and not name.startswith('/') and ':' not in name
            and all(part not in {'', '.', '..'} for part in name.split('/')),
            'unsafe_member', 'blocked')
    preflight._path_spelling(name)
    return name


def _directory_state(path):
    # The shared Windows file-handle reader does not open directory handles.
    # Use stat for directories and recheck entry sets; this is observable
    # consistency only, never Windows change-time or concurrent isolation proof.
    value = path.lstat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _scan(root):
    """Bound enumeration, whitelist before descent, never enumerate scratch trees."""
    admitted, excluded = {}, set()
    total = 0
    def visit(directory, prefix=''):
        nonlocal total
        checked_path(directory, directory=True)
        before = _directory_state(directory)
        names = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                total += 1
                require(total <= MAX_ENTRIES, 'entry_count_bound', 'blocked')
                _relative(entry.name)
                name = _relative(prefix + entry.name)
                require(entry.name.casefold() not in names, 'ambiguous_member', 'blocked')
                names.add(entry.name.casefold())
                require(name in ALLOWED_FILES or name in ALLOWED_DIRS, 'unsupported_layout', 'blocked')
                path = preflight._lexical_path(str(root / name), Path.cwd())
                is_directory = name in ALLOWED_DIRS
                checked_path(path, directory=is_directory)
                state = _directory_state(path) if is_directory else path_state(path)
                admitted[name] = ('directory' if is_directory else 'file', state)
                if name in EXCLUDED:
                    excluded.add(name)
                elif is_directory:
                    visit(path, name + '/')
        require(before == _directory_state(checked_path(directory, directory=True)), 'capture_changed', 'blocked')
    root_state = _directory_state(root)
    visit(root)
    require(root_state == _directory_state(checked_path(root, directory=True)), 'capture_changed', 'blocked')
    files = [name for name, (kind, _) in admitted.items() if kind == 'file']
    require(len(files) <= MAX_FILES, 'file_count_bound', 'blocked')
    return admitted, excluded, root_state


def _json(data):
    require(len(data) <= MAX_JSON_BYTES and b'\0' not in data, 'json_bound', 'blocked')
    try:
        value = preflight._json(data.decode('utf-8'))
        # json.loads also accepts overflowing decimal exponents as infinity.
        pending = [value]
        while pending:
            node = pending.pop()
            if type(node) is float:
                require(math.isfinite(node), 'nonfinite_json')
            elif type(node) is dict:
                pending.extend(node.values())
            elif type(node) is list:
                pending.extend(node)
        return value
    except (ValueError, UnicodeError, RecursionError, TypeError) as error:
        raise ArchiveError('malformed_json') from error


def _inventory(data):
    require(len(data) <= MAX_JSON_BYTES, 'checksum_bound', 'blocked')
    try:
        text = data.decode('ascii')
    except UnicodeError as error:
        raise ArchiveError('malformed_checksums') from error
    require(text.endswith('\n') and 0 < len(text.splitlines()) <= MAX_FILES, 'malformed_checksums')
    result, folded = {}, set()
    for line in text.splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        require(match is not None, 'malformed_checksums')
        digest, name = match.groups()
        _relative(name)
        require(name in ALLOWED_FILES and name not in {'SHA256SUMS', 'COMPLETE.json', 'FAILED.json'},
                'unsupported_checksum_member')
        require(name.casefold() not in folded, 'duplicate_checksum_member')
        folded.add(name.casefold())
        result[name] = digest
    require(list(result) == sorted(result), 'unordered_checksums')
    return result


def _junit(data):
    require(len(data) <= MAX_JSON_BYTES and b'\0' not in data, 'junit_bound', 'blocked')
    try:
        text = data.decode('utf-8')
        require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(), 'unsafe_xml', 'blocked')
        depth = elements = 0
        root = None
        for event, node in ET.iterparse(io.StringIO(text), events=('start', 'end')):
            if event == 'start':
                if root is None:
                    root = node
                depth += 1
                elements += 1
                require(depth <= 16 and elements <= 4096 and len(node.attrib) <= 32,
                        'xml_complexity_bound', 'blocked')
            else:
                depth -= 1
        require(root is not None and root.tag in {'testsuites', 'testsuite'}, 'invalid_junit')
        suites = [root] if root.tag == 'testsuite' else list(root)
        require(bool(suites) and all(row.tag == 'testsuite' for row in suites), 'invalid_junit')
        direct_cases = []
        for suite in suites:
            cases = suite.findall('testcase')
            direct_cases.extend(cases)
            require(len(suite.findall('.//testcase')) == len(cases), 'invalid_junit')
            for tag in ('failure', 'error', 'skipped'):
                require(all(len(case.findall('.//' + tag)) == len(case.findall(tag)) for case in cases),
                        'invalid_junit')
            counts = {'tests': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
                      'errors': sum(c.find('error') is not None for c in cases),
                      'skipped': sum(c.find('skipped') is not None for c in cases)}
            for key, count in counts.items():
                require(suite.get(key) == str(count), 'junit_declared_count_mismatch')
        require(len(root.findall('.//testcase')) == len(direct_cases), 'invalid_junit')
        counts = writer.junit_counts(data)
        if root.tag == 'testsuites':
            for attr, key in (('tests', 'cases'), ('failures', 'failed'), ('errors', 'errors'), ('skipped', 'skipped')):
                require(root.get(attr) is None or root.get(attr) == str(counts[key]), 'junit_declared_count_mismatch')
        return counts
    except (UnicodeError, ET.ParseError, writer.ValidationError) as error:
        raise ArchiveError('invalid_junit') from error


def _timestamp(value):
    require(type(value) is str and len(value) <= 40, 'invalid_timestamp')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ArchiveError('invalid_timestamp') from error
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'invalid_timestamp')
    return parsed


def _source(value):
    _fields(value, {'head', 'baseline', 'branch', 'pins', 'harness_files'})
    require(_digest(value['head'], 40) and value['baseline'] == writer.BASELINE
            and value['branch'] == writer.BRANCH, 'source_metadata_mismatch')
    _fields(value['pins'], writer.PINS)
    _fields(value['harness_files'], writer.ADDITIONS)
    for pin in value['pins'].values():
        _fields(pin, {'git_blob', 'working_tree_sha256', 'normalized_sha256'})
        require(_digest(pin['git_blob'], 40) and _digest(pin['working_tree_sha256'])
                and _digest(pin['normalized_sha256']), 'invalid_source_identity')
    require(all(_digest(digest) for digest in value['harness_files'].values()), 'invalid_source_identity')


def _host(host, classification):
    _fields(host, {'os', 'native_windows', 'python', 'architecture'})
    require(host['os'] in {'windows', 'linux', 'macos', 'other'}
            and type(host['native_windows']) is bool
            and host['architecture'] in {'x64', 'arm64', 'other'}
            and type(host['python']) is str and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', host['python']),
            'invalid_host_metadata')
    require((host['os'] == 'windows') == host['native_windows'], 'host_metadata_mismatch')
    require(tuple(int(part) for part in host['python'].split('.')) >= (3, 11, 0), 'unsupported_python_metadata')
    require((classification == 'native_functional_preflight') == host['native_windows'], 'evidence_class_mismatch')


def _recorded_inventory(value):
    _fields(value, {'scope', 'files'})
    require(value['scope'] in {'explicit_manifest_members', 'manifest_only_unassessable'}
            and type(value['files']) is dict and 1 <= len(value['files']) <= 80,
            'invalid_input_inventory')
    require('manifest' in value['files'], 'invalid_input_inventory')
    for label, record in value['files'].items():
        require(type(label) is str and (label in {'manifest', *preflight.ROLES}
                or re.fullmatch(r'companion_[0-9]{3}', label)
                or label in {'receipt_' + name for name in preflight.RECEIPTS}), 'invalid_input_inventory')
        require(type(record) is dict, 'invalid_input_inventory')
        if record.get('state') == 'missing':
            _fields(record, {'state'})
        else:
            _fields(record, {'state', 'sha256', 'size_bytes', 'state_fingerprint'})
            maximum = (preflight.MAX_MANIFEST_BYTES if label == 'manifest' else
                       preflight.MAX_RECEIPT_BYTES if label.startswith('receipt_') else preflight.MAX_FILE_BYTES)
            require(record['state'] == 'present' and _digest(record['sha256'])
                    and _integer(record['size_bytes'], maximum) and _digest(record['state_fingerprint']),
                    'invalid_input_inventory')
    require(value['files']['manifest'].get('state') == 'present', 'invalid_input_inventory')
    require(sum(record.get('size_bytes', 0) for record in value['files'].values()) <= preflight.MAX_TOTAL_BYTES
            and sum(label != 'manifest' and not label.startswith('receipt_') for label in value['files'])
            <= preflight.MAX_FILES, 'input_inventory_bound')
    if value['scope'] == 'manifest_only_unassessable':
        require(set(value['files']) == {'manifest'}, 'invalid_input_inventory')


def _assessment(case, assessment, data):
    _fields(assessment, {'input_class', 'status', 'deterministic', 'inputs_unchanged', 'unchanged_scope',
                         'inventory', 'preflight_exit_codes', 'qualification'})
    require(assessment['input_class'] == ('operator_supplied_unverified' if case == 'supplied' else 'generated_synthetic')
            and assessment['deterministic'] is True and assessment['inputs_unchanged'] is True
            and assessment['qualification'] is False, 'invalid_assessment_metadata')
    first = _json(data[f'assessments/{case}/first.json'])
    second = _json(data[f'assessments/{case}/second.json'])
    require(writer._json_bytes(first) == writer._json_bytes(second), 'assessment_not_deterministic')
    _schema(first)
    require(first.get('kind') == 'firmavex_windows_runtime_preflight' and first.get('read_only') is True
            and first.get('atomic_snapshot') is False, 'invalid_assessment_report')
    _false(first, ('production_qualified', 'production_admission_evaluated', 'firmware_executed',
                   'tools_executed', 'concurrent_path_isolation'))
    base = preflight._base()
    _fields(first, {*base, 'counts', 'status'})
    require(writer._json_bytes(first['profile']) == writer._json_bytes(base['profile']) and type(first['checks']) is dict
            and all(first['checks'].get(key) == value for key, value in base['checks'].items()),
            'invalid_assessment_report')
    require(all(type(first[key]) is dict for key in ('artifacts', 'receipts', 'required_dlls', 'counts')),
            'invalid_assessment_report')
    full_report = bool(first['artifacts'] or first['receipts'])
    if full_report:
        require(set(preflight.ROLES) <= set(first['artifacts'])
                and set(first['receipts']) == set(preflight.RECEIPTS), 'invalid_assessment_report')
        companions = set(first['artifacts']) - set(preflight.ROLES)
        require(len(companions) <= preflight.MAX_FILES and companions == {
            f'companion_{index:03}' for index in range(1, len(companions) + 1)}, 'invalid_assessment_report')
    _fields(first['counts'], preflight.STATES)
    require(all(type(count) is int and count >= 0 for count in first['counts'].values()),
            'invalid_assessment_counts')
    pending = [first]
    while pending:
        node = pending.pop()
        if type(node) is dict:
            if 'state' in node:
                require(type(node['state']) is str and node['state'] in preflight.STATES, 'invalid_evidence_state')
            pending.extend(node.values())
        elif type(node) is list:
            pending.extend(node)
    # Recompute all five state counts and diagnostic precedence without accessing inputs.
    expected = preflight._finish_report({key: value for key, value in first.items() if key not in {'counts', 'status'}})
    require(first == expected, 'assessment_state_mismatch')
    require(first['status'] == assessment['status'] and first['status'] in preflight.STATES,
            'assessment_state_mismatch')
    require(assessment['preflight_exit_codes'] == [2 if first['status'] == 'blocked' else 1] * 2
            and all(type(code) is int for code in assessment['preflight_exit_codes']), 'assessment_exit_mismatch')
    require(data[f'assessments/{case}/summary.txt'] == preflight.summary(first).encode('utf-8'),
            'assessment_summary_mismatch')
    inventory = assessment['inventory']
    _recorded_inventory(inventory)
    require(assessment['unchanged_scope'] == inventory['scope'], 'inventory_scope_mismatch')
    # A reported identity must not disappear from the declared input inventory.
    observations = {'manifest': first['checks'].get('manifest', {})}
    for label, item in first['artifacts'].items():
        require(type(item) is dict and type(item.get('file')) is dict, 'invalid_assessment_report')
        observations[label] = item['file']
    for label, item in first['receipts'].items():
        require(type(item) is dict and type(item.get('file')) is dict, 'invalid_assessment_report')
        observations['receipt_' + label] = item['file']
    for label, observed in observations.items():
        record = inventory['files'].get(label)
        if 'sha256' in observed or 'size_bytes' in observed:
            require(type(record) is dict and record.get('state') == 'present'
                    and observed.get('sha256') == record.get('sha256')
                    and type(observed.get('size_bytes')) is int
                    and observed['size_bytes'] == record.get('size_bytes'), 'assessment_input_identity_mismatch')
        elif observed.get('state') == 'missing':
            if observed.get('code') == 'file_not_found':
                require(record == {'state': 'missing'}, 'assessment_input_presence_mismatch')
            elif observed.get('code') == 'file_not_supplied':
                require(record is None, 'assessment_input_presence_mismatch')
    if full_report:
        expected_labels = {'manifest'} | {
            label for label, observed in observations.items()
            if label != 'manifest' and observed.get('code') != 'file_not_supplied'}
        require(set(inventory['files']) == expected_labels, 'assessment_inventory_members_mismatch')
    if case != 'supplied':
        expected_status = 'missing' if case == 'missing' else 'blocked'
        require(first['status'] == expected_status, 'fixture_expectation_mismatch')
        require(set(inventory['files']) == set(FIXTURES[case]), 'fixture_inventory_mismatch')
        for label, name in FIXTURES[case].items():
            content = data[f'fixtures/{case}/{name}']
            record = inventory['files'][label]
            require(record.get('state') == 'present' and record['sha256'] == _sha(content)
                    and record['size_bytes'] == len(content), 'input_digest_mismatch')


def _fixture_contract(data):
    """The writer emits four fixed inert examples, not arbitrary new test inputs."""
    text = b'synthetic text only\n'
    receipt = b'{malformed synthetic receipt'
    expected = {
        'missing': {'schema_version': 1, 'artifacts': {}},
        'lexical_refusal': {'schema_version': 1, 'artifacts': {'qemu': {'path': 'alias./never-open.exe'}}},
        'normal_path': {'schema_version': 1, 'artifacts': {'application': {
            'path': 'ordinary path/example.txt', 'sha256': _sha(text)}}},
        'malformed_receipt': {'schema_version': 1, 'artifacts': {}, 'receipts': {
            'runtime_observations': {'path': 'receipt.json', 'sha256': _sha(receipt)}}},
    }
    for case, manifest in expected.items():
        observed = _json(data[f'fixtures/{case}/manifest.json'])
        _schema(observed)
        require(observed == manifest, 'fixture_definition_mismatch')
    require(data['fixtures/normal_path/ordinary path/example.txt'] == text
            and data['fixtures/malformed_receipt/receipt.json'] == receipt, 'fixture_definition_mismatch')


def _complete(data, report):
    require((ROOT_FILES - {'FAILED.json'}) <= set(data), 'required_member_missing', 'missing')
    result, start, complete = (_json(data[name]) for name in ('result.json', 'STARTED.json', 'COMPLETE.json'))
    for record in (result, start, complete):
        _schema(record)
        _false(record, ('runtime_qualified', 'concurrent_path_isolation'))
    _fields(complete, {'schema_version', 'kind', 'result_sha256', 'inventory_sha256',
                       'runtime_qualified', 'concurrent_path_isolation'})
    require(complete['kind'] == 'preflight_validation_completion'
            and complete['result_sha256'] == _sha(data['result.json'])
            and complete['inventory_sha256'] == _sha(data['SHA256SUMS']), 'completion_digest_mismatch')
    classification = result.get('evidence_class')
    require(classification in {'native_functional_preflight', 'portable_synthetic_validation'}, 'unsupported_evidence_class')
    fields = {'schema_version', 'kind', 'status', 'evidence_class', 'host', 'powershell', 'source',
              'started_at_utc', 'ended_at_utc', 'tests', 'assessments', 'runtime_qualified', 'signature_trust',
              'concurrent_path_isolation', 'private_logs', 'checksum_scope'}
    if classification == 'portable_synthetic_validation':
        fields |= {'native_windows_verified', 'checkout_verified', 'working_tree_dirty'}
        require(result.get('native_windows_verified') is False and result.get('checkout_verified') is False
                and result.get('working_tree_dirty') is True, 'synthetic_evidence_mismatch')
    _fields(result, fields)
    require(result['kind'] == 'firmavex_controlled_windows_preflight_validation'
            and result['signature_trust'] == 'not_assessed'
            and result['private_logs'] == ['pytest/console.log', 'pytest/results.xml']
            and result['checksum_scope'] == 'listed_files_only_not_recursive_fixture_or_temp_inventory',
            'invalid_result_metadata')
    _host(result['host'], classification)
    _source(result['source'])
    _fields(result['powershell'], {'version', 'source'})
    require(result['powershell']['source'] == 'wrapper_supplied_not_authenticated'
            and (result['powershell']['version'] is None or type(result['powershell']['version']) is str
                 and re.fullmatch(r'7\.[0-9]+(?:\.[0-9]+){0,2}', result['powershell']['version'])),
            'invalid_powershell_metadata')
    _fields(start, {'schema_version', 'started_at_utc', 'source_revision', 'reviewed_baseline', 'host',
                    'runtime_qualified', 'concurrent_path_isolation'})
    require(start['source_revision'] == result['source']['head'] and start['reviewed_baseline'] == writer.BASELINE
            and writer._json_bytes(start['host']) == writer._json_bytes(result['host'])
            and start['started_at_utc'] == result['started_at_utc'],
            'start_result_mismatch')
    require(_timestamp(result['started_at_utc']) <= _timestamp(result['ended_at_utc']), 'timestamp_order_mismatch')
    counts = _junit(data['pytest/results.xml'])
    report['tests'] = counts
    require(type(result['tests']) is dict and result['tests'] == counts
            and all(type(result['tests'].get(key)) is int for key in ('cases', 'passed', 'failed', 'errors', 'skipped')),
            'test_accounting_mismatch')
    require(not counts['failed'] and not counts['errors'], 'completed_failed_tests')
    status = 'completed_with_unverified_cases' if counts['skipped'] else 'completed'
    require(result['status'] == status, 'result_status_mismatch')
    require(type(result['assessments']) is dict and set(result['assessments']) in (set(CASES), {*CASES, 'supplied'}),
            'assessment_selection_mismatch')
    expected = ROOT_FILES - {'SHA256SUMS', 'COMPLETE.json', 'FAILED.json'} | FIXTURE_FILES
    expected |= {f'assessments/{case}/{name}' for case in result['assessments']
                 for name in ('first.json', 'second.json', 'summary.txt')}
    actual = set(data) - {'SHA256SUMS', 'COMPLETE.json', 'FAILED.json'}
    require(actual == expected, 'checksum_coverage_mismatch')
    _fixture_contract(data)
    for case, assessment in result['assessments'].items():
        _assessment(case, assessment, data)
    expected_summary = ('Controlled preflight validation: ' + status
                        + '\nRuntime/signature qualification: NOT ASSESSED.\nConcurrent path isolation is not provided.\n')
    require(data['summary.txt'] == expected_summary.encode('utf-8'), 'result_summary_mismatch')
    report['evidence']['declared_class'] = classification
    report['source_revision'] = result['source']['head']
    if report['workflow'] != 'failed':
        report['workflow'] = status


def _base():
    return {'schema_version': 1, 'kind': 'firmavex_preflight_archive_verification',
            'integrity': {'state': 'missing', 'code': 'incomplete_archive'}, 'workflow': 'not_assessed',
            'tests': None, 'source_revision': None,
            'coverage': {'listed_files': 0, 'assessed_files': 0, 'excluded_temporary_trees': 0},
            'evidence': {'declared_class': 'not_assessed', 'native_execution': 'not_assessed',
                         'supplied_inputs': 'not_assessed', 'source_authenticity': 'not_assessed',
                         'historical_input_immutability': 'not_assessed', 'signature_trust': 'not_assessed'},
            'findings': [], 'read_only': True, 'atomic_snapshot': False,
            'native_windows_verified': False, 'runtime_qualified': False, 'concurrent_path_isolation': False}


def _verify(root, report):
    root = checked_path(preflight._lexical_path(os.fspath(root), Path.cwd()), directory=True)
    admitted, excluded, root_state = _scan(root)
    names = {name for name, (kind, _) in admitted.items() if kind == 'file'}
    report['workflow'] = 'failed' if 'FAILED.json' in names else 'incomplete'
    report['coverage']['excluded_temporary_trees'] = len(excluded)
    report['coverage']['assessed_files'] = len(names)
    data = {}
    total = 0
    with bounded_reads(4 * MAX_TOTAL_BYTES + 1, calls=2 * MAX_FILES):
        for name in sorted(names):
            maximum = MAX_JSON_BYTES if name.endswith(('.json', '.xml')) or name == 'SHA256SUMS' else MAX_FILE_BYTES
            size = admitted[name][1][2]
            require(size <= maximum and total + size <= MAX_TOTAL_BYTES, 'archive_byte_bound', 'blocked')
            content = read_bytes(root / name, min(maximum, MAX_TOTAL_BYTES - total))
            total += len(content)
            require(total <= MAX_TOTAL_BYTES, 'archive_byte_bound', 'blocked')
            require(path_state(checked_path(root / name)) == admitted[name][1], 'capture_changed', 'blocked')
            data[name] = content
        if 'FAILED.json' in data:
            failed = _json(data['FAILED.json'])
            _fields(failed, {'schema_version', 'status', 'code', 'interrupted', 'runtime_qualified'})
            _schema(failed)
            require(failed['status'] == 'failed' and failed['runtime_qualified'] is False
                    and type(failed['interrupted']) is bool and type(failed['code']) is str
                    and re.fullmatch('[a-z_]{1,80}', failed['code']), 'invalid_failure_metadata')
            report['findings'].append('failure_marker_present')
        if 'pytest/results.xml' in data:
            # Keep recorded outcomes separate from sealing/completion, including failed runs.
            report['tests'] = _junit(data['pytest/results.xml'])
        if 'SHA256SUMS' in data:
            inventory = _inventory(data['SHA256SUMS'])
            report['coverage']['listed_files'] = len(inventory)
            for name, digest in inventory.items():
                require(name in data, 'listed_file_missing', 'missing')
                require(_sha(data[name]) == digest, 'checksum_mismatch')
            require(set(inventory) == names - {'SHA256SUMS', 'COMPLETE.json', 'FAILED.json'},
                    'checksum_coverage_mismatch')
            if {'STARTED.json', 'result.json', 'COMPLETE.json'} <= names:
                _complete(data, report)
                report['integrity'] = {'state': 'verified', 'code': 'declared_integrity_consistent'}
        # Confirm earlier bytes/identities and the observed supported entry set after parsing.
        for name, content in data.items():
            require(read_bytes(root / name, MAX_FILE_BYTES) == content
                    and path_state(checked_path(root / name)) == admitted[name][1], 'capture_changed', 'blocked')
        require(_scan(root) == (admitted, excluded, root_state), 'capture_changed', 'blocked')
    if excluded:
        report['findings'].append('temporary_contents_not_assessed')
    report['findings'].append('source_authenticity_not_assessed')


def verify_archive(directory):
    """Return sanitized evidence states; control-flow exceptions propagate."""
    report = _base()
    try:
        _verify(directory, report)
    except ArchiveError as error:
        report['integrity'] = {'state': error.state, 'code': error.code}
    except FileNotFoundError:
        report['integrity'] = {'state': 'missing', 'code': 'archive_or_member_missing'}
    except (OSError, ValueError, TypeError, RecursionError, OverflowError, KeyError, AttributeError):
        report['integrity'] = {'state': 'blocked', 'code': 'unsafe_malformed_or_inconsistent_archive'}
    return report


def summary(report):
    return ('Batch 35 archive: integrity=' + report['integrity']['state'] + '; workflow=' + report['workflow']
            + '\nNative execution, authenticity, supplied originals and signing trust: NOT ASSESSED.\n'
            + 'Listed-file consistency only; temporary contents excluded; no atomic snapshot or path isolation.\n')


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ArchiveError('invalid_arguments')
    parser = Parser(description=__doc__)
    parser.add_argument('--archive', required=True)
    try:
        args = parser.parse_args(argv)
    except ArchiveError as error:
        report = _base()
        report['integrity'] = {'state': 'blocked', 'code': error.code}
    else:
        report = verify_archive(args.archive)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    print(summary(report), file=sys.stderr, end='')
    if report['integrity']['state'] in {'blocked', 'mismatch'}:
        return 2
    return 0 if report['integrity']['state'] == 'verified' and report['workflow'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
