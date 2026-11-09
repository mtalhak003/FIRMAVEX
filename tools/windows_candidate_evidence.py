"""Read-only, bounded internal-consistency review of a Windows candidate ZIP.

No extraction, execution, repair, network access or profile approval occurs here.
The caller must obtain the ZIP digest, source revision and run ID independently.
Matching records cannot authenticate guest execution or replace review of the CI
runner, publisher signatures, corresponding source or redistribution obligations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
from importlib.resources import files
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET
import zipfile
import zlib

from firmavex.backends.security import read_bytes
from firmavex.product.platform_support import WINDOWS_EXECUTABLES, WINDOWS_PROFILE_ID, WINDOWS_PROFILE_VERSION
from tools.windows_runtime_candidate import CANDIDATE, MAX_BYTES, MAX_FILES, package_inventory, signature_policy

MAX_ARCHIVE = 128 * 1024**2
MAX_MEMBER = 32 * 1024**2
MAX_MEMBERS = 1024
REQUIRED_TESTS = {
    'test_actual_arm_firmware_input_after_startup': 4,
    'test_actual_bundled_mps2_startup_and_behavior': 4,
    'test_actual_missing_completion_is_failure_despite_trigger': 1,
    'test_actual_cancellation_charged_and_aborted': 1,
    'test_native_windows_candidate_source_probe': 1,
    'test_native_windows_candidate_memory_resource_bound': 1,
    'test_original_windows_handle_proves_termination_independently_of_exit_code': 2,
    'test_native_windows_job_owns_and_terminates_python_descendant': 2,
    'test_native_windows_supervisor_reaps_python_descendant_after_worker_death': 1,
}
REQUIRED_MODULES = {name: ('tests.product.test_runtime' if name.startswith('test_actual_')
    else 'tests.product.test_windows_runtime_candidate' if name.startswith('test_native_windows_candidate_')
    else 'tests.product.test_supervisor' if name.startswith('test_native_windows_supervisor_')
    else 'tests.product.test_windows_job') for name in REQUIRED_TESTS}
PRODUCT_PATHS = {
    'source-probe/product-source/product-admission.json': ('source', 'test_native_windows_candidate_product_entrypoint_rejection'),
    'source-probe/product-gui/gui-admission.json': ('gui', 'test_native_windows_candidate_gui_rejection'),
    'source-probe/product-frozen/product-admission.json': ('frozen', 'test_native_windows_candidate_frozen_product_rejection'),
}


class EvidenceError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise EvidenceError(code)


def _sha(value):
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _integer(value, minimum=0, maximum=2**63-1):
    return type(value) is int and minimum <= value <= maximum


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _relative(name):
    require(type(name) is str and 0 < len(name) <= 1024 and '\\' not in name
            and ':' not in name and all(ord(c) >= 32 for c in name), 'unsafe_member_name')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in {'', '.', '..'} for part in name.split('/')),
            'unsafe_member_name')
    return name


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_field')
            result[key] = value
        return result
    def constant(_):
        raise EvidenceError('nonfinite_json')
    require(len(data) <= MAX_MEMBER, 'json_bound')
    result = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    pending = [(result, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop(); nodes += 1
        require(depth <= 64 and nodes <= 500000, 'json_complexity_bound')
        if type(value) is float:
            require(math.isfinite(value), 'nonfinite_json')
        if type(value) is dict: pending.extend((v, depth + 1) for v in value.values())
        elif type(value) is list: pending.extend((v, depth + 1) for v in value)
    return result


def _members(data):
    result, names, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_MEMBERS, 'archive_entry_bound')
        for entry in infos:
            name = _relative(entry.filename[:-1] if entry.is_dir() else entry.filename)
            require(name.casefold() not in names, 'duplicate_archive_member')
            names.add(name.casefold())
            require(name.split('/')[0] in {'acquisition', 'source-probe', 'test-diagnostics'}, 'unexpected_archive_root')
            mode = stat.S_IFMT(entry.external_attr >> 16)
            require(mode in ({0, stat.S_IFDIR} if entry.is_dir() else {0, stat.S_IFREG}), 'nonregular_archive_member')
            require(not entry.flag_bits & 1 and entry.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
                    'unsupported_archive_encoding')
            require(0 <= entry.file_size <= MAX_MEMBER, 'archive_member_bound')
            total += entry.file_size
            require(total <= MAX_ARCHIVE, 'archive_byte_bound')
            if entry.is_dir():
                require(entry.file_size == 0, 'nonempty_archive_directory')
                continue
            # Read through EOF to check CRC, without trusting ZIP metadata alone.
            chunks, size = [], 0
            with archive.open(entry) as stream:
                while chunk := stream.read(1024**2):
                    size += len(chunk)
                    require(size <= entry.file_size and size <= MAX_MEMBER, 'archive_member_bound')
                    chunks.append(chunk)
            require(size == entry.file_size, 'archive_member_size_mismatch')
            result[name] = b''.join(chunks)
    return result


def _envelope(value):
    require(type(value) is dict and value.get('candidate_only') is True
            and value.get('production_qualified') is False, 'candidate_label_mismatch')


def _bundled_image_identity():
    """Bind to this reviewed checkout's trusted bundled image, not ZIP metadata."""
    with files('firmavex.product').joinpath('resources/example/image.json').open('rb') as stream:
        data = stream.read(2 * 1024**2 + 1)
    require(len(data) <= 2 * 1024**2, 'approved_image_manifest_bound')
    manifest = _json(data)
    require(type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1
            and manifest.get('kind') == 'firmavex_product_example_image' and _sha(manifest.get('image_sha256')),
            'approved_image_manifest_invalid')
    return {'image_sha256': manifest['image_sha256'], 'manifest_sha256': hashlib.sha256(data).hexdigest()}


def _tools(value):
    require(type(value) is dict, 'tool_identity_missing')
    for name, (version, digest) in CANDIDATE.items():
        identity = value[name]
        require(identity.get('version') == version and identity.get('sha256') == digest
                and _integer(identity.get('size_bytes'), 1, 512 * 1024**2), 'candidate_identity_mismatch')


def _inventory(value, tools):
    require(type(value) is dict and 0 < len(value) <= MAX_FILES, 'vendor_inventory_bound')
    groups, total = {}, 0
    for name, row in value.items():
        _relative(name)
        require(type(row) is dict and set(row) in ({'sha256', 'size_bytes'},
                {'sha256', 'size_bytes', 'hardlink_group', 'link_count'}), 'vendor_inventory_record')
        require(_sha(row['sha256']) and _integer(row['size_bytes'], 0, 512 * 1024**2), 'vendor_inventory_record')
        total += row['size_bytes']; require(total <= MAX_BYTES, 'vendor_inventory_bound')
        if 'hardlink_group' in row:
            group = _relative(row['hardlink_group'])
            require(_integer(row['link_count'], 2, MAX_FILES), 'hardlink_inventory_record')
            groups.setdefault(group, []).append((name, row))
    for group, aliases in groups.items():
        require(group == min(name for name, _ in aliases), 'hardlink_inventory_record')
        require(all(row['link_count'] == len(aliases) and row['sha256'] == aliases[0][1]['sha256']
                    and row['size_bytes'] == aliases[0][1]['size_bytes'] for _, row in aliases), 'hardlink_inventory_record')
    require(any(name.startswith('share/licenses/') for name in value), 'license_inventory_missing')
    for name, filename in [('qemu', 'qemu-system-arm.exe'), ('gdb', 'gdb-multiarch.exe')]:
        row = value['bin/' + filename]
        require(row['sha256'] == tools[name]['sha256'] and row['size_bytes'] == tools[name]['size_bytes'],
                'vendor_tool_identity_mismatch')


def _cleanup(value, *, runtime=False):
    require(type(value) is dict and value.get('success') is True and value.get('errors') == [], 'cleanup_not_verified')
    rows = value.get('processes')
    require(type(rows) is list and len(rows) == 2, 'cleanup_not_verified')
    require({row.get('name') for row in rows} == {'qemu', 'gdb'}, 'cleanup_not_verified')
    for row in rows:
        require(row.get('reaped') is True and _integer(row.get('pid'), 1) and type(row.get('return_code')) is int,
                'cleanup_not_verified')
        if runtime:
            native = row.get('windows_identity', {})
            require(native.get('terminated') is True and type(native.get('wait_status')) is int
                    and native.get('wait_status') == 0
                    and _integer(native.get('creation_time'), 1), 'windows_cleanup_not_verified')


def _receipt_plan():
    result = []
    for values, failure in [([2, 1], 1), ([2, 0], 0)]:
        for symbol, expected in [('product_failure', failure), ('initialized_data', 0x13579bdf)]:
            result.append((f'{symbol}-{values[0]}-{values[1]}', values, expected, symbol == 'initialized_data' or bool(failure), None))
    result.extend(('enumerative-search', list(divmod(i, 4)), int(i == 9), i == 9, None) for i in range(10))
    result.extend(('reproduction', [2, 1], 1, True, None) for _ in range(3))
    result.extend([(name, [2, 1], None, False, error) for name, error in [('timeout', 'timeout'), ('cancel', 'cancelled')]])
    return result


def _receipts(members, report, image_sha, image_size):
    names = {name for name in members if re.fullmatch(r'source-probe/candidate-receipt-.*\.json', name)}
    expected_names = {f'source-probe/candidate-receipt-{i:02}.json' for i in range(1, 20)}
    require(names == expected_names, 'receipt_inventory_mismatch')
    attempts = set()
    for i, (case, inputs, observed, triggered, fault) in enumerate(_receipt_plan(), 1):
        value = _json(members[f'source-probe/candidate-receipt-{i:02}.json']); _envelope(value)
        require(value.get('case') == case, 'receipt_order_mismatch')
        runtime = value['runtime']
        require(type(runtime.get('schema_version')) is int and runtime.get('schema_version') == 1
                and runtime.get('backend') == 'qemu-mps2-an385-gdb', 'runtime_schema_mismatch')
        attempt = runtime.get('attempt_id')
        require(type(attempt) is str and re.fullmatch(r'[0-9a-f]{32}', attempt) and attempt not in attempts,
                'attempt_identity_mismatch')
        attempts.add(attempt)
        require(runtime.get('inputs') == inputs and all(type(v) is int for v in runtime['inputs']), 'input_mismatch')
        _tools(runtime['tools']['identities'])
        for name in CANDIDATE:
            require(runtime['tools']['identities'][name]['size_bytes'] == report['tools'][name]['size_bytes'], 'tool_size_mismatch')
        firmware = runtime['firmware']
        require(firmware.get('sha256') == image_sha and firmware.get('size_bytes') == image_size, 'firmware_identity_mismatch')
        require(runtime['firmware_validation'].get('firmware_sha256') == image_sha
                and runtime['firmware_validation']['elf'].get('target') == 'mps2-an385', 'firmware_identity_mismatch')
        require(runtime.get('cleanup_verified') is True and runtime.get('guest_dispatched') is True
                and runtime.get('input_injected') is True, 'execution_evidence_incomplete')
        _cleanup(runtime['cleanup'], runtime=True)
        require(_number(runtime.get('duration_seconds')), 'invalid_duration')
        if fault:
            require(runtime.get('error_category') == fault and runtime.get('completion_reached') is False
                    and runtime.get('measurement_mode') == 'unverified_runtime_observation'
                    and runtime.get('classification') == ('interrupted' if fault == 'cancelled' else 'infrastructure_failure'),
                    'fault_classification_mismatch')
        else:
            require(runtime.get('measurement_mode') == 'real_firmware' and runtime.get('completion_reached') is True,
                    'execution_evidence_incomplete')
            require('error' not in runtime and 'error_category' not in runtime
                    and runtime.get('classification') == ('configured_failure_observed' if triggered
                                                         else 'completed_without_configured_failure'),
                    'success_classification_mismatch')
            observation = runtime['observation']
            require(type(runtime.get('observed_value')) is int and runtime['observed_value'] == observed
                    and type(observation.get('observed_value')) is int
                    and runtime.get('failure_condition_observed') is triggered
                    and observation.get('observed_value') == observed and observation.get('triggered') is triggered,
                    'observation_mismatch')
            require(all(observation.get(key) is True for key in ('success', 'ready_reached', 'completion_reached'))
                    and observation.get('inputs_read_back') == dict(zip(['product_inputs[0]', 'product_inputs[1]'], inputs))
                    and all(type(v) is int for v in observation['inputs_read_back'].values()),
                    'observation_mismatch')


def _accounting(cases):
    expected = [
        ('product_failure-(2, 1)', 1, 1, 1, False, 1), ('initialized_data-(2, 1)', 1, 1, 1, False, 1),
        ('product_failure-(2, 0)', 1, 1, 0, False, None), ('initialized_data-(2, 0)', 1, 1, 1, False, 1),
        ('enumerative-search', 10, 16, 1, False, 10), ('reproduction', 3, 3, 3, False, 1),
        ('timeout', 1, 2, 0, True, None), ('cancel', 1, 2, 0, True, None)]
    require(type(cases) is list and len(cases) == len(expected), 'case_accounting_mismatch')
    for row, (name, count, budget, triggers, aborted, first) in zip(cases, expected):
        require(row.get('name') == name, 'case_accounting_mismatch')
        actual = row['accounting']
        fields = {'attempted_executions': count, 'execution_budget': budget,
                  'successful_executions': 0 if aborted else count, 'infrastructure_failures': int(aborted),
                  'failure_triggering_executions': triggers, 'budget_remaining': budget-count}
        require(all(type(actual.get(key)) is int and actual[key] == value for key, value in fields.items()),
                'case_accounting_mismatch')
        require(actual.get('aborted') is aborted and actual.get('failure_found') is bool(triggers)
                and actual.get('budget_exhausted') is (budget == count)
                and actual.get('first_failure_execution') == first
                and (first is None or type(actual.get('first_failure_execution')) is int), 'case_accounting_mismatch')
        require(actual.get('time_to_first_failure_seconds') is None if first is None
                else _number(actual.get('time_to_first_failure_seconds')), 'case_accounting_mismatch')


def _product_rejection(value):
    require(type(value) is dict and value.get('category') == 'unsupported_platform'
            and value.get('required_profile') == WINDOWS_PROFILE_ID, 'product_rejection_mismatch')
    qualification = value['qualification']
    require(type(qualification) is dict and type(qualification.get('schema_version')) is int
            and qualification['schema_version'] == 1 and qualification.get('required_profile') == WINDOWS_PROFILE_ID
            and type(qualification.get('profile_version')) is int
            and qualification['profile_version'] == WINDOWS_PROFILE_VERSION
            and qualification.get('host_architecture') == 'x86_64', 'product_rejection_mismatch')
    for name, (version, digest) in CANDIDATE.items():
        item = qualification['tools'][name]
        expected = dict(zip(('version', 'sha256'), WINDOWS_EXECUTABLES[name]))
        observed = {'version': version, 'sha256': digest}
        require(item.get('expected') == expected and item.get('observed') == observed
                and item.get('matches') == {key: observed[key] == expected[key] for key in expected}
                and all(type(v) is bool for v in item['matches'].values()), 'product_rejection_mismatch')


def _product_records(members, revision, run_id, required):
    terminal = {name for name in members if name.startswith('source-probe/product-')
                and name.rsplit('/', 1)[-1] in {'product-admission.json', 'gui-admission.json'}}
    present = terminal & PRODUCT_PATHS.keys()
    unreviewed = terminal - PRODUCT_PATHS.keys()
    if required:
        require(present == PRODUCT_PATHS.keys() and not unreviewed, 'required_product_records_missing_or_unsupported')
    tests = {}
    for name in sorted(present):
        value = _json(members[name]); _envelope(value)
        distribution, test = PRODUCT_PATHS[name]
        require(type(value.get('schema_version')) is int and value['schema_version'] == 1
                and value.get('source_revision') == revision and value.get('run_id') == run_id
                and value.get('host') == {'os': 'Windows', 'architecture': 'x86_64'}
                and value.get('firmware_execution') == 'not_admitted'
                and type(value.get('charged_attempts')) is int and value['charged_attempts'] == 0
                and 'error_type' not in value, 'product_report_binding_or_outcome_mismatch')
        if distribution == 'gui':
            require(value.get('kind') == 'firmavex_candidate_gui_admission'
                    and value.get('status') == 'candidate_gui_admission_rejection_passed'
                    and value.get('worker_idle_after_cleanup') is True, 'gui_rejection_not_verified')
            _product_rejection(value['rejection'])
            tests[test] = 'tests.desktop.test_windows_candidate_rejection'
            continue
        require(value.get('kind') == 'firmavex_candidate_product_admission'
                and value.get('status') == 'candidate_admission_rejection_passed'
                and value.get('distribution') == distribution and value.get('installation_verified') is False
                and value.get('executable_origin') == ('running_interpreter' if distribution == 'source'
                    else 'caller_supplied_not_independently_verified'), 'product_rejection_not_verified')
        executable = value['executable']
        require(_sha(executable.get('sha256')) and _integer(executable.get('size_bytes'), 1, 512 * 1024**2),
                'product_executable_identity_missing')
        cases = value['cases']
        require(type(cases) is list and len(cases) == 2
                and [row.get('path') for row in cases] == ['supervised_worker', 'CLI'], 'product_case_inventory_mismatch')
        require(cases[0].get('event_kinds') == ['accepted', 'error'], 'product_admission_events_mismatch')
        for row in cases: _product_rejection(row['rejection'])
        cleanup = cases[1]['owned_process_cleanup']
        require(type(cleanup) is list and cleanup and all(row.get('reaped') is True
                and _integer(row.get('pid'), 1) and type(row.get('returncode')) is int
                and row['returncode'] == 1 for row in cleanup), 'product_cleanup_not_verified')
        tests[test] = 'tests.product.test_windows_candidate_product'
    return {'scope': 'admission rejection only; no positive execution or installation verification',
            'required': required, 'complete': present == PRODUCT_PATHS.keys() and not unreviewed,
            'reviewed_paths': sorted(present), 'unreviewed_paths': sorted(unreviewed)}, tests


def _junit(members, product_tests=None):
    product_tests = product_tests or {}
    required = {**REQUIRED_TESTS, **{name: 1 for name in product_tests}}
    modules = {**REQUIRED_MODULES, **product_tests}
    names = [name for name in members if name.startswith('test-diagnostics/') and name.endswith('/pytest.xml')]
    require(3 <= len(names) <= MAX_MEMBERS, 'junit_selection_inventory_mismatch')
    totals, passes = Counter(), Counter()
    for name in sorted(names):
        data = members[name]
        require(len(data) <= 8 * 1024**2, 'unsafe_junit')
        text = data.decode('utf-8-sig')
        require('\x00' not in text and '<!DOCTYPE' not in text and '<!ENTITY' not in text, 'unsafe_junit')
        root = ET.fromstring(text)
        require(root.tag in {'testsuite', 'testsuites'}, 'invalid_junit')
        cases = list(root.iter('testcase'))
        require(0 < len(cases) <= 10000, 'invalid_junit')
        identities, selection_passes = set(), Counter()
        for case in cases:
            identity = case.get('classname', ''), case.get('name', '')
            require(all(identity) and identity not in identities, 'duplicate_junit_case')
            identities.add(identity)
            status = 'failed' if case.find('failure') is not None else 'errors' if case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
            totals[status] += 1
            test_name = identity[1].split('[', 1)[0]
            if status == 'passed' and (test_name not in required or identity[0] == modules[test_name]):
                selection_passes[test_name] += 1
        for suite in root.iter('testsuite'):
            direct = list(suite.findall('testcase'))
            if not direct: continue
            counts = {'tests': len(direct), 'failures': sum(c.find('failure') is not None for c in direct),
                      'errors': sum(c.find('error') is not None for c in direct),
                      'skipped': sum(c.find('skipped') is not None for c in direct)}
            require(all(suite.get(key) == str(value) for key, value in counts.items()), 'junit_summary_mismatch')
        for test, count in selection_passes.items(): passes[test] = max(passes[test], count)
    require(totals['failed'] == totals['errors'] == 0, 'junit_failures')
    require(all(passes[name] >= count for name, count in required.items()), 'critical_native_tests_missing_or_skipped')
    return {**{key: totals[key] for key in ('passed', 'failed', 'errors', 'skipped')}, 'selections': len(names),
            'required_cases_passed': {name: passes[name] for name in required}}


def verify_archive(path, *, expected_sha256, expected_revision, expected_run_id, require_product_paths=False):
    """Return a safe report; control-flow exceptions propagate normally."""
    result = {'schema_version': 1, 'kind': 'firmavex_windows_candidate_archive_validation',
              'candidate_only': True, 'production_qualified': False, 'validation': 'failed',
              'scope': 'internal consistency of a caller-bound archive; no execution or publisher authentication',
              'additional_product_records_reviewed': False,
              'not_proven': ['native execution authenticity', 'publisher signature and license review',
                             'complete immutable dependency closure', 'product GUI/frozen/installed qualification'],
              'failures': []}
    try:
        require(type(require_product_paths) is bool and _sha(expected_sha256) and type(expected_revision) is str
                and re.fullmatch(r'[0-9a-f]{40}', expected_revision)
                and type(expected_run_id) is str and re.fullmatch(r'[1-9][0-9]{0,19}', expected_run_id), 'invalid_expected_identity')
        data = read_bytes(path, MAX_ARCHIVE)
        actual = hashlib.sha256(data).hexdigest(); result['archive_sha256'] = actual
        require(actual == expected_sha256, 'archive_digest_mismatch')
        members = _members(data)
        report = _json(members['source-probe/candidate-report.json']); _envelope(report)
        require(type(report.get('schema_version')) is int and report.get('schema_version') == 1
                and report.get('kind') == 'firmavex_windows_runtime_candidate'
                and report.get('status') == 'candidate_source_probe_passed', 'candidate_report_not_complete')
        require(report.get('source_revision') == expected_revision and report.get('run_id') == expected_run_id
                and report.get('host') == {'os': 'Windows', 'architecture': 'x86_64'}, 'source_or_run_binding_mismatch')
        require(report['candidate_expected'] == {name: {'version': version, 'sha256': digest}
                                                 for name, (version, digest) in CANDIDATE.items()},
                'candidate_identity_mismatch')
        _tools(report['tools'])
        rejection = report['production_rejection']
        require(type(rejection) is dict and type(rejection.get('profile_version')) is int
                and rejection['profile_version'] == WINDOWS_PROFILE_VERSION, 'production_rejection_missing')
        _product_rejection({'category': 'unsupported_platform', **rejection})
        packages = package_inventory(members['acquisition/packages.txt'].decode('ascii'))
        require(packages == report['packages'], 'package_inventory_mismatch')
        policy = signature_policy(members['acquisition/signature-policy.txt'].decode('ascii'))
        require(policy == report['signature_policy'], 'signature_policy_mismatch')
        vendor = members['source-probe/vendor-files.json']
        require(hashlib.sha256(vendor).hexdigest() == report['vendor_inventory_sha256'], 'vendor_inventory_digest_mismatch')
        _inventory(_json(vendor), report['tools'])
        image = members['source-probe/example/example.elf']; image_sha = hashlib.sha256(image).hexdigest()
        approved = _bundled_image_identity()
        result['approved_bundled_image'] = approved
        provenance = _json(members['source-probe/example/image-provenance.json'])
        require(0 < len(image) <= 1024**2 and image[:4] == b'\x7fELF' and image_sha == approved['image_sha256']
                and provenance.get('image_sha256') == image_sha
                and provenance.get('origin') == 'bundled_verified_image' and provenance.get('locally_compiled') is False,
                'firmware_identity_mismatch')
        _receipts(members, report, image_sha, len(image)); _accounting(report['cases'])
        resource = _json(members['source-probe/candidate-resource.json']); _envelope(resource)
        require(resource.get('firmware_executed') is False and resource.get('requested_limit_bytes') == 128*1024**2
                and resource.get('allocation_bytes') == 256*1024**2 and type(resource.get('exit_code')) is int
                and resource['exit_code'] != 0, 'resource_evidence_mismatch')
        require(type(resource.get('cleanup')) is list and resource['cleanup']
                and all(row.get('reaped') is True and type(row.get('returncode')) is int for row in resource['cleanup']),
                'resource_cleanup_not_verified')
        product, product_tests = _product_records(members, expected_revision, expected_run_id, require_product_paths)
        result['junit'] = _junit(members, product_tests)
        result['product_admission'] = product
        result['additional_product_records_reviewed'] = bool(product['reviewed_paths']) and not product['unreviewed_paths']
        result.update(validation='passed', source_revision=expected_revision, run_id=expected_run_id,
                      attempt_receipts=19, successful_observations=17, infrastructure_failures=2,
                      vendor_inventory_sha256=report['vendor_inventory_sha256'])
    except EvidenceError as error:
        result['failures'] = [{'code': error.code}]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError,
            zipfile.BadZipFile, ET.ParseError, zlib.error, EOFError):
        result['failures'] = [{'code': 'malformed_or_unreadable_evidence'}]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--require-product-paths', action='store_true',
                        help='Require source, GUI and frozen rejection reports and their passing native tests; never approves execution.')
    args = parser.parse_args(argv)
    result = verify_archive(args.archive, expected_sha256=args.sha256, expected_revision=args.revision,
                            expected_run_id=args.run_id, require_product_paths=args.require_product_paths)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['validation'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
