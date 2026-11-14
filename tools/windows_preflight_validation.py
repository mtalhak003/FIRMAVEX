"""Controlled preflight validation, not runtime execution or qualification.

The native operator entry requires Windows. Portable assessment helpers are
testable with synthetic files; they never manufacture native Windows evidence.
All outputs belong to a fresh operator-controlled archive, never to supplied
input trees. Native ACL privacy and concurrent path isolation are not qualified.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

from firmavex.backends.security import bounded_reads, checked_path, read_bytes
from firmavex.product.file_state import path_state
from tools import windows_runtime_preflight as preflight

BASELINE = '90af3e836c81bd0dc9a27dcea076f19ce7ee15e6'
BRANCH = 'product/desktop-batch11'
SELECTION = ('tests/product/test_windows_runtime_preflight.py', 'tests/product/test_file_state.py')
EXPECTED_CASES = 162
MAX_RECORD = 1024**2
MAX_LOG = 16 * 1024**2
PINS = ('tools/windows_runtime_preflight.py', 'tools/windows_candidate_closure.py',
        'firmavex/backends/security.py', 'firmavex/product/file_state.py',
        'firmavex/product/platform_support.py', 'tools/product_ci_tests.py',
        'firmavex/product/windows_job.py', 'firmavex/product/verification.py',
        'firmavex/product/errors.py', 'firmavex/backends/api.py', 'firmavex/__init__.py',
        'pyproject.toml', 'tests/conftest.py', *SELECTION)
ADDITIONS = {'tools/windows_preflight_validation.py', 'tools/validate_windows_preflight.ps1',
             'tests/product/test_windows_preflight_validation.py'}


class ValidationError(ValueError):
    """Fixed codes only; raw tool/OS diagnostics remain out of public summaries."""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _local(value):
    return preflight._lexical_path(os.fspath(value), Path.cwd())


def _under(path, root):
    return path == root or root in path.parents


def _separate(left, right):
    if _under(left, right) or _under(right, left):
        raise ValidationError('locations_overlap')


def _validated_git(repo, executable):
    if executable is None:
        raise ValidationError('explicit_git_required')
    raw = os.fspath(executable)
    selected = _local(raw)
    names = {'git.exe'} if os.name == 'nt' else {'git', 'git.exe'}
    if not Path(raw).is_absolute() or selected.name.casefold() not in names:
        raise ValidationError('unsafe_git_executable')
    if _under(selected, _local(repo)):
        raise ValidationError('unsafe_git_executable')
    return checked_path(selected)


def _git_environment():
    result = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    result.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                  GIT_CONFIG_SYSTEM=os.devnull, GIT_ATTR_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
                  GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1')
    return result


def _git(repo, *args, executable=None, raw=False):
    selected = _validated_git(repo, executable)
    try:
        result = subprocess.run([str(selected), '--no-optional-locks', '--no-pager',
                                '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + str(selected),
                                '-c', 'protocol.allow=never', '-c', 'core.attributesFile=' + os.devnull,
                                '-C', str(repo), *args], env=_git_environment(),
                                stdin=subprocess.DEVNULL, capture_output=True, text=not raw,
                                timeout=20, **({} if raw else {'errors': 'replace'}))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidationError('git_check_failed') from error
    if result.returncode or len(result.stdout if raw else result.stdout.encode('utf-8')) > MAX_RECORD:
        raise ValidationError('git_check_failed')
    return result.stdout if raw else result.stdout.strip()


def verify_checkout(repo, expected_head, *, git_executable=None):
    repo = checked_path(_local(repo), directory=True)
    if type(expected_head) is not str or not re.fullmatch('[0-9a-f]{40}', expected_head):
        raise ValidationError('invalid_expected_revision')
    def git(*args, raw=False):
        return _git(repo, *args, executable=git_executable, raw=raw)
    if _local(git('rev-parse', '--show-toplevel')) != repo:
        raise ValidationError('git_worktree_redirected')
    config = git('config', '--no-includes', '--null', '--name-only', '--list', raw=True)
    if any(key.lower().startswith((b'filter.', b'include.', b'includeif.')) for key in config.split(b'\0')):
        raise ValidationError('unsupported_local_git_configuration')
    entries = git('ls-files', '-v', '-z', '--', '.', ':(exclude)evidence/**', raw=True)
    if any(row[:2] != b'H ' for row in entries.split(b'\0') if row):
        raise ValidationError('unsupported_index_visibility_flags')
    head = git('rev-parse', 'HEAD')
    if head != expected_head:
        raise ValidationError('revision_mismatch')
    branch = git('branch', '--show-current')
    if branch != BRANCH:
        raise ValidationError('wrong_branch')
    if git('status', '--short', '--untracked-files=all', '--', '.', ':(exclude)evidence/**'):
        raise ValidationError('checkout_not_clean')
    git('merge-base', '--is-ancestor', BASELINE, head)
    changes = git('diff', '--no-ext-diff', '--no-textconv', '--name-only', BASELINE, head,
                  '--', '.', ':(exclude)evidence/**').splitlines()
    if any(name not in ADDITIONS and name != 'README.md' and not name.startswith('docs/') for name in changes):
        raise ValidationError('reviewed_baseline_drift')
    pins = {}
    for name in PINS:
        original = git('rev-parse', BASELINE + ':' + name)
        if git('rev-parse', head + ':' + name) != original:
            raise ValidationError('reviewed_baseline_drift')
        expected = git('show', '--no-ext-diff', '--no-textconv', BASELINE + ':' + name, raw=True)
        observed = read_bytes(_local(repo / name), MAX_RECORD)
        if observed.replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
            raise ValidationError('working_source_drift')
        pins[name] = {'git_blob': original, 'working_tree_sha256': _sha(observed),
                      'normalized_sha256': _sha(expected.replace(b'\r\n', b'\n'))}
    harness = {}
    for name in sorted(ADDITIONS):
        expected = git('show', '--no-ext-diff', '--no-textconv', head + ':' + name, raw=True)
        observed = read_bytes(_local(repo / name), MAX_RECORD)
        if observed.replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
            raise ValidationError('working_source_drift')
        harness[name] = _sha(observed)
    return {'head': head, 'baseline': BASELINE, 'branch': branch, 'pins': pins, 'harness_files': harness}


def host_context():
    native = sys.platform == 'win32' and os.name == 'nt'
    family = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}.get(sys.platform, 'other')
    machine = platform.machine().casefold()
    return {'os': family, 'native_windows': native, 'python': platform.python_version(),
            'architecture': {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64',
                             'aarch64': 'arm64'}.get(machine, 'other')}


class Archive:
    """Exclusive writes in a fresh owned tree. Never recursively remove anything."""
    def __init__(self, output):
        self.root = checked_path(_local(output), directory=True, exists=False)
        _separate(self.root, Path(__file__).absolute().parents[1])
        checked_path(self.root.parent, directory=True)
        self.root.mkdir(mode=0o700, exist_ok=False)
        self.files = []
        self.directories = {self.root}

    def member(self, name):
        if (type(name) is not str or not re.fullmatch('[a-zA-Z0-9_./ -]{1,180}', name)
                or any(p in {'.', '..', ''} for p in name.split('/'))):
            raise ValidationError('unsafe_archive_member')
        path = _local(self.root / name)
        if path == self.root or not _under(path, self.root):
            raise ValidationError('unsafe_archive_member')
        return path

    def destination(self, name):
        path = self.member(name)
        parents = []
        parent = path.parent
        while parent not in self.directories:
            parents.append(parent)
            parent = parent.parent
        for directory in reversed(parents):
            checked_path(directory, directory=True, exists=False)
            directory.mkdir(mode=0o700, exist_ok=False)
            self.directories.add(directory)
        checked_path(path.parent, directory=True)
        checked_path(path, exists=False)
        if path.exists():
            raise ValidationError('archive_member_exists')
        return path

    @contextmanager
    def open(self, name):
        path = self.destination(name)
        stream = path.open('xb')
        primary = None
        try:
            self.files.append(name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException as error:
            primary = error
            raise
        finally:
            try:
                stream.close()
            except BaseException as error:
                if primary is None or isinstance(primary, Exception) and not isinstance(error, Exception):
                    raise
                primary.add_note('Archive stream cleanup failed; preserve partial output.')

    def write(self, name, content):
        if type(content) is not bytes or len(content) > MAX_LOG:
            raise ValidationError('archive_record_bound')
        with self.open(name) as stream:
            stream.write(content)

    def json(self, name, value):
        self.write(name, _json_bytes(value))

    def register(self, name):
        path = self.member(name)
        read_bytes(path, MAX_LOG)
        if name not in self.files:
            self.files.append(name)

    def seal(self, result):
        self.json('result.json', result)
        summary = ('Controlled preflight validation: ' + result['status']
                   + '\nRuntime/signature qualification: NOT ASSESSED.\n'
                   + 'Concurrent path isolation is not provided.\n')
        self.write('summary.txt', summary.encode('utf-8'))
        rows = []
        for name in sorted(self.files):
            rows.append(_sha(read_bytes(self.root / name, MAX_LOG)) + '  ' + name + '\n')
        self.write('SHA256SUMS', ''.join(rows).encode('ascii'))
        self.json('COMPLETE.json', {'schema_version': 1, 'kind': 'preflight_validation_completion',
                  'result_sha256': _sha(read_bytes(self.root / 'result.json', MAX_RECORD)),
                  'inventory_sha256': _sha(read_bytes(self.root / 'SHA256SUMS', MAX_RECORD)),
                  'runtime_qualified': False, 'concurrent_path_isolation': False})


def snapshot(manifest, staging):
    """Snapshot only explicit assessed inputs, preserving absent-file states."""
    staging = checked_path(_local(staging), directory=True)
    _separate(staging, Path(__file__).absolute().parents[1])
    manifest = _local(manifest)
    if manifest == staging or not _under(manifest, staging):
        raise ValidationError('input_outside_staging')
    inventory = {}
    with bounded_reads(4 * preflight.MAX_TOTAL_BYTES + 1,
                       calls=2 * (preflight.MAX_FILES + len(preflight.RECEIPTS) + 1)):
        capture = preflight._Capture()
        raw, identity = capture.read(manifest, preflight.MAX_MANIFEST_BYTES)
        inventory['manifest'] = {'state': 'present', **identity,
                                 'state_fingerprint': _sha(repr(path_state(manifest)).encode('ascii'))}
        try:
            artifacts, companions, receipts = preflight._spec(preflight._json(raw), manifest)
        except (ValueError, TypeError, RecursionError):
            capture.finish()
            return {'scope': 'manifest_only_unassessable', 'files': inventory}
        items = [(name, row, preflight.MAX_FILE_BYTES) for name, row in artifacts.items()]
        items += [(f'companion_{i:03}', row, preflight.MAX_FILE_BYTES) for i, row in enumerate(companions, 1)]
        items += [('receipt_' + name, row, preflight.MAX_RECEIPT_BYTES) for name, row in receipts.items()]
        if any(not _under(row['path'], staging) or row['path'] == staging for _, row, _ in items):
            raise ValidationError('input_outside_staging')
        for label, descriptor, maximum in sorted(items):
            path = descriptor['path']
            try:
                _, identity = capture.read(path, maximum)
            except FileNotFoundError:
                inventory[label] = {'state': 'missing'}
            else:
                inventory[label] = {'state': 'present', **identity,
                                     'state_fingerprint': _sha(repr(path_state(path)).encode('ascii'))}
        capture.finish()
    return {'scope': 'explicit_manifest_members', 'files': inventory}


def assess_manifest(manifest, staging, archive, label, *, input_class='operator_supplied_unverified'):
    if (type(label) is not str or not re.fullmatch('[a-z][a-z0-9_-]{0,31}', label)
            or input_class not in {'generated_synthetic', 'operator_supplied_unverified'}):
        raise ValidationError('invalid_assessment_label')
    manifest, staging = _local(manifest), _local(staging)
    _separate(archive.root / 'assessments', staging)
    before = snapshot(manifest, staging)
    first = preflight.preflight(manifest)
    archive.json('assessments/' + label + '/first.json', first)
    middle = snapshot(manifest, staging)
    second = preflight.preflight(manifest)
    archive.json('assessments/' + label + '/second.json', second)
    after = snapshot(manifest, staging)
    if before != middle or before != after:
        raise ValidationError('input_changed')
    if _json_bytes(first) != _json_bytes(second):
        raise ValidationError('reports_not_deterministic')
    for report in (first, second):
        if (report.get('production_qualified') is not False
                or report.get('production_admission_evaluated') is not False
                or report.get('firmware_executed') is not False or report.get('tools_executed') is not False
                or report.get('concurrent_path_isolation') is not False):
            raise ValidationError('unexpected_approval_claim')
    archive.write('assessments/' + label + '/summary.txt', preflight.summary(first).encode('utf-8'))
    return {'input_class': input_class, 'status': first['status'], 'deterministic': True,
            'inputs_unchanged': True, 'unchanged_scope': before['scope'], 'inventory': before,
            'preflight_exit_codes': [2 if report['status'] == 'blocked' else 1 for report in (first, second)],
            'qualification': False}


def junit_counts(raw):
    if type(raw) is not bytes or len(raw) > MAX_RECORD or b'\0' in raw:
        raise ValidationError('invalid_junit')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise ValidationError('invalid_junit') from error
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValidationError('invalid_junit')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValidationError('invalid_junit') from error
    cases = root.findall('.//testcase')
    identities = [(row.get('classname'), row.get('name')) for row in cases]
    classes = {'tests.product.test_windows_runtime_preflight': 158, 'tests.product.test_file_state': 4}
    if (len(cases) != EXPECTED_CASES or len(set(identities)) != len(cases)
            or any(not a or not b or len(a) > 256 or len(b) > 1024 for a, b in identities)
            or any(sum(a == name for a, _ in identities) != count for name, count in classes.items())
            or any(sum(len(row.findall(tag)) for tag in ('failure', 'error', 'skipped')) > 1 for row in cases)):
        raise ValidationError('junit_selection_mismatch')
    failed = sum(row.find('failure') is not None for row in cases)
    errors = sum(row.find('error') is not None for row in cases)
    skipped = sum(row.find('skipped') is not None for row in cases)
    required = [row for row in cases if row.get('classname') == 'tests.product.test_file_state'
                and row.get('name') == 'test_native_windows_change_time_detects_same_size_write_with_restored_mtime']
    if len(required) != 1:
        raise ValidationError('junit_selection_mismatch')
    return {'cases': len(cases), 'passed': len(cases) - failed - errors - skipped,
            'failed': failed, 'errors': errors, 'skipped': skipped,
            'required_ntfs_case': 'skipped' if required[0].find('skipped') is not None else
                                  'failed' if required[0].find('failure') is not None or required[0].find('error') is not None else 'passed'}


def _child_environment(temporary=None):
    result = dict(os.environ)
    for name in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTHONPATH', 'PYTHONHOME',
                 'PYTHONINSPECT', 'PYTHONSTARTUP', 'PYTHONPYCACHEPREFIX', 'GITHUB_STEP_SUMMARY',
                 'PYTEST_DEBUG'):
        result.pop(name, None)
    result.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    if temporary is not None:
        result.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    return result


def _run_pytest(repo, archive):
    # Reuse the reviewed admission handshake and Windows process-tree owner.
    from tools.product_ci_tests import pytest_command
    from firmavex.product.windows_job import WindowsJob
    report = archive.destination('pytest/results.xml')
    basetemp = archive.destination('pytest/temporary-root')
    temporary = archive.destination('pytest/process-temp')
    temporary.mkdir(mode=0o700, exist_ok=False)
    archive.directories.add(temporary)
    command = pytest_command(['-q', '-ra', '-p', 'no:cacheprovider', '-c', str(repo / 'pyproject.toml'),
                              '--confcutdir=' + str(repo), '--basetemp=' + str(basetemp),
                              *SELECTION], report, bounded=False)
    process = owner = None
    primary = None
    with archive.open('pytest/console.log') as transcript:
        try:
            process = subprocess.Popen(command, cwd=repo, env=_child_environment(temporary),
                                       stdin=subprocess.PIPE, stdout=transcript, stderr=subprocess.STDOUT,
                                       **({'start_new_session': True} if os.name == 'posix' else {}))
            if os.name == 'nt':
                owner = WindowsJob()
                owner.assign(int(process._handle))
            process.stdin.write(b'1')
            process.stdin.close()
            process.wait(timeout=240)
        except BaseException as error:
            primary = error
            raise
        finally:
            cleanup = []
            if owner is not None:
                try:
                    owner.close()
                except BaseException as error:
                    cleanup.append(error)
            if process is not None:
                try:
                    if os.name == 'posix':
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    elif process.poll() is None:
                        process.kill()
                    process.wait(timeout=10)
                    process.stdin.close()
                except BaseException as error:
                    cleanup.append(error)
            if cleanup:
                controls = [error for error in cleanup if not isinstance(error, Exception)]
                if controls and (primary is None or isinstance(primary, Exception)):
                    raise controls[0]
                if primary is None:
                    raise ValidationError('pytest_cleanup_failed') from cleanup[0]
                primary.add_note('Pytest process cleanup was not verified.')
    archive.register('pytest/results.xml')
    counts = junit_counts(read_bytes(report, MAX_RECORD))
    if process.returncode or counts['failed'] or counts['errors']:
        raise ValidationError('synthetic_regressions_failed')
    return counts


def _synthetic_assessments(archive):
    results = {}
    cases = {'missing': {'schema_version': 1, 'artifacts': {}},
             'lexical_refusal': {'schema_version': 1, 'artifacts': {'qemu': {'path': 'alias./never-open.exe'}}},
             'normal_path': {'schema_version': 1, 'artifacts': {
                 'application': {'path': 'ordinary path/example.txt', 'sha256': _sha(b'synthetic text only\n')}}},
             'malformed_receipt': {'schema_version': 1, 'artifacts': {}, 'receipts': {
                 'runtime_observations': {'path': 'receipt.json', 'sha256': _sha(b'{malformed synthetic receipt')}}}}
    for name, manifest in cases.items():
        prefix = 'fixtures/' + name + '/'
        archive.json(prefix + 'manifest.json', manifest)
        if name == 'normal_path':
            archive.write(prefix + 'ordinary path/example.txt', b'synthetic text only\n')
        selected = archive.root / prefix / 'manifest.json'
        if name == 'malformed_receipt':
            archive.write(prefix + 'receipt.json', b'{malformed synthetic receipt')
        results[name] = assess_manifest(selected, archive.root / prefix, archive, name,
                                        input_class='generated_synthetic')
        expected = 'missing' if name == 'missing' else 'blocked'
        if results[name]['status'] != expected:
            raise ValidationError('synthetic_expectation_mismatch')
    return results


def run_operator(repo, expected_head, output, *, controlled_inputs=False, manifest=None,
                 staging_root=None, powershell_version=None, git_executable=None):
    if controlled_inputs is not True:
        raise ValidationError('controlled_inputs_not_confirmed')
    host = host_context()
    if not host['native_windows']:
        raise ValidationError('native_windows_required')
    if (sys.prefix == sys.base_prefix or sys.version_info < (3, 11)
            or importlib.util.find_spec('pytest') is None):
        raise ValidationError('existing_python_environment_required')
    if powershell_version is not None and not re.fullmatch(r'7\.[0-9]+(?:\.[0-9]+){0,2}', powershell_version):
        raise ValidationError('invalid_powershell_version')
    repo, output = _local(repo), _local(output)
    git_executable = _validated_git(repo, git_executable)
    if _under(git_executable, output):
        raise ValidationError('unsafe_git_executable')
    _separate(repo, output)
    _separate(_local(sys.prefix), output)
    if (manifest is None) != (staging_root is None):
        raise ValidationError('paired_manifest_staging_required')
    admitted_inventory = None
    if manifest is not None:
        staging_root, manifest = _local(staging_root), _local(manifest)
        _separate(repo, staging_root)
        _separate(output, staging_root)
        if _under(git_executable, staging_root):
            raise ValidationError('unsafe_git_executable')
    context = verify_checkout(repo, expected_head, git_executable=git_executable)
    if manifest is not None:
        admitted_inventory = snapshot(manifest, staging_root)
    archive = Archive(output)
    started = datetime.now(timezone.utc).isoformat()
    try:
        archive.json('STARTED.json', {'schema_version': 1, 'started_at_utc': started,
                     'source_revision': context['head'], 'reviewed_baseline': BASELINE,
                     'host': host, 'runtime_qualified': False, 'concurrent_path_isolation': False})
        counts = _run_pytest(repo, archive)
        assessments = _synthetic_assessments(archive)
        if manifest is not None:
            assessments['supplied'] = assess_manifest(manifest, staging_root, archive, 'supplied')
            if (assessments['supplied']['inventory'] != admitted_inventory
                    or snapshot(manifest, staging_root) != admitted_inventory):
                raise ValidationError('input_changed_after_admission')
        if verify_checkout(repo, expected_head, git_executable=git_executable) != context:
            raise ValidationError('checkout_changed')
        if host_context() != host:
            raise ValidationError('host_context_changed')
        result = {'schema_version': 1, 'kind': 'firmavex_controlled_windows_preflight_validation',
                  'status': 'completed_with_unverified_cases' if counts['skipped'] else 'completed',
                  'evidence_class': 'native_functional_preflight', 'host': host,
                  'powershell': {'version': powershell_version, 'source': 'wrapper_supplied_not_authenticated'},
                  'source': context, 'started_at_utc': started,
                  'ended_at_utc': datetime.now(timezone.utc).isoformat(), 'tests': counts,
                  'assessments': assessments, 'runtime_qualified': False,
                  'signature_trust': 'not_assessed', 'concurrent_path_isolation': False,
                  'private_logs': ['pytest/console.log', 'pytest/results.xml'],
                  'checksum_scope': 'listed_files_only_not_recursive_fixture_or_temp_inventory'}
        archive.seal(result)
        return result
    except BaseException as error:
        code = str(error) if type(error) is ValidationError and re.fullmatch('[a-z_]{1,80}', str(error)) else 'validation_interrupted_or_failed'
        try:
            archive.json('FAILED.json', {'schema_version': 1, 'status': 'failed', 'code': code,
                         'interrupted': not isinstance(error, Exception), 'runtime_qualified': False})
        except BaseException as persistence_error:
            if isinstance(error, Exception) and not isinstance(persistence_error, Exception):
                raise
            error.add_note('Failure evidence could not be fully persisted; preserve the partial output.')
        raise


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValidationError('invalid_arguments')
    parser = Parser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--controlled-inputs', action='store_true')
    parser.add_argument('--manifest')
    parser.add_argument('--staging-root')
    parser.add_argument('--powershell-version')
    parser.add_argument('--git-executable', required=True)
    try:
        args = parser.parse_args(argv)
        result = run_operator(Path(__file__).absolute().parents[1], args.expected_head, args.output,
                    controlled_inputs=args.controlled_inputs, manifest=args.manifest,
                    staging_root=args.staging_root, powershell_version=args.powershell_version,
                    git_executable=args.git_executable)
    except Exception as error:
        code = str(error) if type(error) is ValidationError and re.fullmatch('[a-z_]{1,80}', str(error)) else 'validation_blocked'
        print(json.dumps({'status': 'blocked_or_failed', 'code': code, 'native_windows_verified': False,
                          'runtime_qualified': False}, sort_keys=True))
        return 2
    print(json.dumps({'status': result['status'], 'source_revision': result['source']['head'],
                      'tests': result['tests'], 'runtime_qualified': False}, sort_keys=True))
    return 1 if result['tests']['skipped'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
