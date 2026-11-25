"""Read-only supplied lifecycle receipt/inventory consistency, never qualification.

Exit 0 means pinned records are internally consistent, including a rejected
runtime. Exit 2 means the assessment is blocked. No original ZIP, executable,
publisher signature, dependency closure or installation is verified here.
"""
import argparse
import json
from pathlib import Path
import re
import sys

from firmavex.backends.security import bounded_reads
from firmavex.product.errors import ProductError
from firmavex.product.verification import check_cancel
from tools.product_ci_tests import console_print
from tools.versioned_install_ci import _runtime_qualification_failure
from tools.windows_runtime_candidate import parse_package_inventory
from tools.windows_runtime_preflight import _Capture, _json, _lexical_path, _sha

MAX_INPUT = 1024**2
PACKAGES = ('mingw-w64-ucrt-x86_64-qemu', 'mingw-w64-ucrt-x86_64-qemu-common',
            'mingw-w64-ucrt-x86_64-gdb', 'mingw-w64-ucrt-x86_64-gdb-multiarch')
ROOTS = (PACKAGES[0], PACKAGES[3])
_VERSION = re.compile(r'(?:(?P<epoch>[0-9]{1,6}):)?(?P<upstream>[0-9]{1,6}(?:\.[0-9]{1,6}){0,3})-[0-9]{1,6}(?:\.[0-9]{1,6})?')


class _Invalid(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise _Invalid(code)


def _base():
    return {'schema_version': 1, 'kind': 'firmavex_windows_runtime_inventory',
            'status': 'blocked', 'read_only': True, 'firmware_executed': False,
            'tools_executed': False, 'production_admission_evaluated': False,
            'production_qualified': False, 'atomic_snapshot': False,
            'concurrent_path_isolation': False,
            'scope': 'supplied pinned receipt/inventory consistency only',
            'checks': {name: 'not_assessed' for name in
                ('source_revision_authenticity', 'original_archive_authenticity', 'vendor_binary_authenticity',
                 'publisher_trust', 'package_ownership', 'dependency_closure',
                 'licensing', 'native_runtime_capability', 'production_qualification')},
            'failures': []}


def _comparison(receipt, revision):
    _require(type(receipt) is dict and type(receipt.get('schema_version')) is int
        and receipt['schema_version'] == 1
        and receipt.get('kind') == 'firmavex_versioned_installer_qualification'
        and type(receipt.get('candidate_git_revision')) is str
        and receipt['candidate_git_revision'] == revision
        and receipt.get('platform') == 'win32'
        and receipt.get('measurement') == 'real_hosted_ci_not_physical_consumer'
        and receipt.get('passed') is False and type(receipt.get('phases')) is list
        and receipt['phases'] == [], 'unsupported_lifecycle_receipt')
    failure = receipt.get('failure')
    _require(type(failure) is dict and failure.get('type') == 'ProductError'
        and type(failure.get('diagnostic')) is str, 'unsupported_lifecycle_failure')
    value = failure.get('runtime_qualification')
    comparison = _runtime_qualification_failure(ProductError('unsupported_platform',
        'Supplied rejection receipt', {'qualification': value}))
    _require(comparison is not None, 'unsupported_qualification_contract')
    # Python equality aliases bool/int; enforce exact match-field record types.
    _require(type(value.get('tools')) is dict, 'contradictory_comparison')
    for role in ('qemu', 'gdb'):
        row = value['tools'].get(role)
        _require(type(row) is dict and type(row.get('matches')) is dict
            and set(row['matches']) == {'version', 'sha256'}
            and all(item is None or type(item) is bool for item in row['matches'].values()),
            'contradictory_comparison')
    _require(value == comparison, 'contradictory_comparison')
    _require(not (comparison['host_architecture'] == 'x86_64'
        and all(all(row['matches'].values()) for row in comparison['tools'].values())),
        'contradictory_admission_rejection')
    return comparison


def _packages(inventory, comparison):
    _require(all(name in inventory for name in ROOTS), 'missing_inventory_roots')
    result = {}
    for name in PACKAGES:
        version = inventory.get(name)
        match = _VERSION.fullmatch(version) if version is not None else None
        role = 'qemu' if 'qemu' in name else 'gdb'
        reported = comparison['tools'][role]['observed']['version']
        upstream = match['upstream'] if match else None
        prefix = 'QEMU emulator version ' if role == 'qemu' else 'GNU gdb (GDB) '
        result[name] = {'declaration_scope': 'supplied_inventory_only_not_ownership',
            'state': 'missing' if version is None else 'recorded' if match else 'not_assessed',
            'declared_version': version if match else None,
            'upstream_version': upstream,
            'reported_upstream_agrees': (reported == prefix + upstream
                if upstream is not None and reported is not None else None)}
    return result


def assess(receipt_path, inventory_path, *, expected_revision,
           expected_receipt_sha256, expected_inventory_sha256, cancel_event=None):
    report = _base()
    code = 'invalid_expected_identity'
    try:
        _require(type(expected_revision) is str
            and re.fullmatch('[0-9a-f]{40}', expected_revision) is not None,
            'invalid_expected_identity')
        receipt_pin, inventory_pin = _sha(expected_receipt_sha256), _sha(expected_inventory_sha256)
        code = 'unsafe_input_path'
        _require(isinstance(receipt_path, (str, Path)) and isinstance(inventory_path, (str, Path)), code)
        receipt_path = _lexical_path(str(receipt_path), Path.cwd())
        inventory_path = _lexical_path(str(inventory_path), Path.cwd())
        _require(str(receipt_path).casefold() != str(inventory_path).casefold(), 'duplicate_input_path')
        check_cancel(cancel_event)
        code = 'unreadable_or_changed_input'
        with bounded_reads(8 * MAX_INPUT + 16, calls=4, cancel_event=cancel_event):
            capture = _Capture()
            receipt_bytes, receipt_identity = capture.read(receipt_path, MAX_INPUT)
            inventory_bytes, inventory_identity = capture.read(inventory_path, MAX_INPUT)
            _require(receipt_identity['sha256'] == receipt_pin, 'receipt_digest_mismatch')
            _require(inventory_identity['sha256'] == inventory_pin, 'inventory_digest_mismatch')
            check_cancel(cancel_event)
            code = 'malformed_lifecycle_receipt'
            comparison = _comparison(_json(receipt_bytes), expected_revision)
            code = 'malformed_package_inventory'
            inventory = parse_package_inventory(inventory_bytes.decode('utf-8'))
            packages = _packages(inventory, comparison)
            check_cancel(cancel_event)
            code = 'unreadable_or_changed_input'
            capture.finish()
            check_cancel(cancel_event)
        report.update(status='consistent_records', source_revision=expected_revision,
            inputs={'receipt': receipt_identity, 'inventory': inventory_identity},
            recorded_admission='rejected', recorded_installer_transitions=0,
            transition_scope='no installer transition recorded; not proof of zero tool subprocesses',
            comparison=comparison, package_count=len(inventory), packages=packages,
            capture={'status': 'stable_observed', 'atomic': False})
    except _Invalid as error:
        report['failures'] = [{'code': str(error)}]
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        report['failures'] = [{'code': code}]
    return report


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise _Invalid('invalid_arguments')
    parser = Parser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--inventory', required=True, type=Path)
    for field in ('revision', 'receipt-sha256', 'inventory-sha256'):
        parser.add_argument('--' + field, required=True)
    try:
        args = parser.parse_args(argv)
        report = assess(args.receipt, args.inventory, expected_revision=args.revision,
            expected_receipt_sha256=args.receipt_sha256,
            expected_inventory_sha256=args.inventory_sha256)
    except _Invalid:
        report = _base(); report['failures'] = [{'code': 'invalid_arguments'}]
    console_print(json.dumps(report, sort_keys=True, ensure_ascii=True, allow_nan=False))
    print('FIRMAVEX supplied runtime inventory: ' + report['status']
          + '; qualification not assessed.', file=sys.stderr, flush=True)
    return 0 if report['status'] == 'consistent_records' else 2


if __name__ == '__main__':
    raise SystemExit(main())
