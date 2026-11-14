"""Synthetic operator-harness checks; never native Windows qualification."""

import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from tools import windows_preflight_validation as validation


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def inputs(tmp_path):
    staging = tmp_path / 'controlled inputs with spaces'
    staging.mkdir()
    manifest = staging / 'manifest.json'
    manifest.write_text(json.dumps({'schema_version': 1, 'artifacts': {}}), encoding='utf-8')
    return staging, manifest


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def forbid_dispatch(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A manifest assessment dispatched a process or network request')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)


def test_repeatable_missing_manifest_assessment_is_read_only_and_not_qualification(inputs, tmp_path, monkeypatch):
    staging, manifest = inputs
    original = manifest.read_bytes()
    archive = validation.Archive(tmp_path / 'fresh outputs')
    forbid_dispatch(monkeypatch)
    result = validation.assess_manifest(manifest, staging, archive, 'missing',
                                        input_class='generated_synthetic')
    assert result['input_class'] == 'generated_synthetic'
    assert result['deterministic'] is True
    assert result['inputs_unchanged'] is True
    assert result['qualification'] is False
    assert result['preflight_exit_codes'] == [1, 1]
    first = load(tmp_path / 'fresh outputs' / 'assessments' / 'missing' / 'first.json')
    second = load(tmp_path / 'fresh outputs' / 'assessments' / 'missing' / 'second.json')
    assert first == second
    assert first['status'] == 'missing'
    assert first['production_qualified'] is False
    assert first['tools_executed'] is False
    assert first['concurrent_path_isolation'] is False
    assert manifest.read_bytes() == original
    assert str(staging) not in json.dumps(result)


def test_malformed_receipt_preserves_expected_blocked_classification(inputs, tmp_path, monkeypatch):
    staging, manifest = inputs
    receipt = staging / 'malformed receipt.json'
    payload = b'{ MALFORMED-PRIVATE-CONTENT'
    receipt.write_bytes(payload)
    manifest.write_text(json.dumps({'schema_version': 1, 'artifacts': {}, 'receipts': {
        'runtime_observations': {'path': receipt.name, 'sha256': sha(payload)}}}), encoding='utf-8')
    original = {path: path.read_bytes() for path in (manifest, receipt)}
    archive = validation.Archive(tmp_path / 'outputs')
    forbid_dispatch(monkeypatch)
    result = validation.assess_manifest(manifest, staging, archive, 'malformed',
                                        input_class='generated_synthetic')
    assert result['preflight_exit_codes'] == [2, 2]
    assert result['inputs_unchanged'] is True and result['deterministic'] is True
    report = load(tmp_path / 'outputs' / 'assessments' / 'malformed' / 'first.json')
    assert report['status'] == 'blocked'
    assert report['production_qualified'] is False
    assert 'MALFORMED-PRIVATE-CONTENT' not in json.dumps(report)
    assert {path: path.read_bytes() for path in original} == original


def test_ordinary_spaced_unicode_path_is_observed_without_executing_its_contents(inputs, tmp_path, monkeypatch):
    staging, manifest = inputs
    artifact = staging / 'ordinary naïve file.txt'
    data = b'Plain synthetic text, not an executable or firmware.'
    artifact.write_bytes(data)
    manifest.write_text(json.dumps({'schema_version': 1, 'artifacts': {
        'application': {'path': artifact.name, 'sha256': sha(data)}}}), encoding='utf-8')
    archive = validation.Archive(tmp_path / 'outputs')
    forbid_dispatch(monkeypatch)
    result = validation.assess_manifest(manifest, staging, archive, 'ordinary')
    report = load(tmp_path / 'outputs' / 'assessments' / 'ordinary' / 'first.json')
    assert result['preflight_exit_codes'] == [2, 2]
    assert report['artifacts']['application']['identity']['state'] == 'verified'
    assert report['artifacts']['application']['pe']['state'] == 'blocked'
    assert artifact.read_bytes() == data
    assert report['tools_executed'] is False


def test_archive_existing_output_is_never_reused_or_overwritten(tmp_path):
    output = tmp_path / 'existing'
    output.mkdir()
    sentinel = output / 'sentinel.txt'
    sentinel.write_bytes(b'USER DATA')
    with pytest.raises((validation.ValidationError, FileExistsError)):
        validation.Archive(output)
    assert sentinel.read_bytes() == b'USER DATA'
    assert set(output.iterdir()) == {sentinel}


def test_archive_file_creation_is_exclusive_and_rejects_traversal(tmp_path):
    output = tmp_path / 'new archive'
    archive = validation.Archive(output)
    archive.write('retained.txt', b'original evidence')
    with pytest.raises((validation.ValidationError, FileExistsError)):
        archive.write('retained.txt', b'changed')
    assert (output / 'retained.txt').read_bytes() == b'original evidence'
    with pytest.raises((validation.ValidationError, ValueError)):
        archive.write('../escaped.txt', b'not allowed')
    assert not (tmp_path / 'escaped.txt').exists()


@pytest.mark.parametrize('path', [
    'evidence/windows-sandbox/NEVER-TOUCH',
    '/workspace/FIRMAVEX/NEVER-TOUCH',
    r'\/server/share/NEVER-TOUCH',
    '../NEVER-TOUCH',
], ids=['protected', 'original', 'unc', 'traversal'])
def test_archive_unsafe_output_is_refused_before_filesystem_access(monkeypatch, path):
    def forbidden(*args, **kwargs):
        raise AssertionError('Forbidden output spelling reached filesystem')
    monkeypatch.setattr(Path, 'stat', forbidden)
    monkeypatch.setattr(Path, 'lstat', forbidden)
    with pytest.raises((validation.ValidationError, ValueError)):
        validation.Archive(path)


def test_snapshot_covers_explicit_receipts_and_preserves_missing_file_state(inputs):
    staging, manifest = inputs
    receipt = staging / 'license receipt.txt'
    receipt.write_bytes(b'caller-supplied opaque provenance, not authenticated')
    manifest.write_text(json.dumps({'schema_version': 1, 'artifacts': {
        'qemu': {'path': 'missing-qemu.exe'}}, 'receipts': {
        'licensing': {'path': receipt.name, 'sha256': sha(receipt.read_bytes())}}}), encoding='utf-8')
    before = validation.snapshot(manifest, staging)
    encoded = json.dumps(before)
    assert sha(manifest.read_bytes()) in encoded
    assert sha(receipt.read_bytes()) in encoded
    assert 'missing' in encoded
    assert str(staging) not in encoded
    assert 'caller-supplied opaque provenance' not in encoded
    (staging / 'missing-qemu.exe').write_bytes(b'newly appeared synthetic bytes')
    assert validation.snapshot(manifest, staging) != before


def test_snapshot_rejects_descriptor_outside_controlled_staging_before_read(inputs, tmp_path, monkeypatch):
    staging, manifest = inputs
    outside = tmp_path / 'outside receipt.txt'
    outside.write_bytes(b'not an approved input')
    manifest.write_text(json.dumps({'schema_version': 1, 'artifacts': {}, 'receipts': {
        'licensing': {'path': str(outside)}}}), encoding='utf-8')
    original = Path.open
    def controlled_open(path, *args, **kwargs):
        assert path != outside, 'Outside-staging input was opened'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', controlled_open)
    with pytest.raises(validation.ValidationError):
        validation.snapshot(manifest, staging)


@pytest.mark.parametrize('label', ['../escape', '/absolute', 'private\nlabel', '', 'x' * 33],
                         ids=['traversal', 'absolute', 'control', 'empty', 'oversized'])
def test_assessment_labels_cannot_redirect_or_inject_output(inputs, tmp_path, label):
    staging, manifest = inputs
    archive = validation.Archive(tmp_path / 'outputs')
    with pytest.raises(validation.ValidationError):
        validation.assess_manifest(manifest, staging, archive, label)


@pytest.mark.parametrize('label', ['native_verified', 'real_firmware', 'production_qualified'])
def test_input_class_cannot_claim_native_execution_or_qualification(inputs, tmp_path, label):
    staging, manifest = inputs
    archive = validation.Archive(tmp_path / 'outputs')
    with pytest.raises(validation.ValidationError):
        validation.assess_manifest(manifest, staging, archive, 'probe', input_class=label)


def test_host_context_comes_from_executing_environment_not_a_caller_label():
    context = validation.host_context()
    encoded = json.dumps(context)
    assert sys.version.split()[0] in encoded
    if sys.platform != 'win32':
        assert context.get('native_windows') is not True


def test_powershell_wrapper_static_contract_preserves_native_gates_and_argument_arrays():
    """Source invariants only: this does not parse or execute PowerShell."""
    script = Path(__file__).resolve().parents[2] / 'tools' / 'validate_windows_preflight.ps1'
    source = script.read_text(encoding='utf-8')
    assert '#requires -Version 7.0' in source
    assert '$IsWindows' in source and '$ConfirmControlledInputs.IsPresent' in source
    assert "'^[0-9a-f]{40}$'" in source
    assert 'pyvenv.cfg' in source and "'python.exe'" in source
    assert "':(exclude)evidence/**'" in source
    assert "$Arguments = @('-E', '-s', '-B', '-m', 'tools.windows_preflight_validation'" in source
    assert "'--git-executable'" in source and '$Git' in source
    assert '& $Python @Arguments' in source
    assert '$HarnessExit = $LASTEXITCODE' in source
    assert 'finally { Pop-Location }' in source
    assert 'ReparsePoint' in source and 'Get-Item -LiteralPath' in source
    for forbidden in ('Invoke-Expression', 'Start-Process', 'ExecutionPolicy',
                      'Set-Content', 'Out-File', 'Remove-Item', 'pip install',
                      'qemu-system-arm.exe', 'gdb-multiarch.exe'):
        assert forbidden not in source


def synthetic_junit(*, failures=0, errors=0, skipped=1, count=162, duplicate=False,
                    include_ntfs=True):
    """Invented host-test records only, never a retained native test artifact."""
    suites = ET.Element('testsuites')
    suite = ET.SubElement(suites, 'testsuite', tests=str(count), failures=str(failures),
                          errors=str(errors), skipped=str(skipped))
    names = [f'test_synthetic_case_{i}' for i in range(max(0, count - 4))]
    entries = [('tests.product.test_windows_runtime_preflight', name) for name in names]
    file_state_names = [
        'test_open_file_identity_agrees_with_path_and_survives_read',
        'test_missing_path_fails_instead_of_returning_identity',
        'test_native_windows_change_time_detects_same_size_write_with_restored_mtime',
        'test_windows_abi_setup_is_reused_but_each_snapshot_queries_fresh_data',
    ]
    if not include_ntfs:
        file_state_names[2] = 'test_not_the_required_ntfs_case'
    entries += [('tests.product.test_file_state', name) for name in file_state_names]
    if duplicate and len(entries) > 1:
        entries[1] = entries[0]
    for index, (classname, name) in enumerate(entries):
        case = ET.SubElement(suite, 'testcase', classname=classname, name=name, time='0.001')
        if index < failures:
            ET.SubElement(case, 'failure', message='synthetic failure')
        elif index < failures + errors:
            ET.SubElement(case, 'error', message='synthetic error')
        elif index >= len(entries) - skipped:
            ET.SubElement(case, 'skipped', message='synthetic unavailable host feature')
    return ET.tostring(suites, encoding='utf-8')


def test_junit_counts_preserve_actual_failures_errors_skips_and_required_ntfs_case():
    counts = validation.junit_counts(synthetic_junit(failures=1, errors=1, skipped=2))
    assert counts['cases'] == 162
    assert counts['passed'] == 158
    assert counts['failed'] == 1
    assert counts['errors'] == 1
    assert counts['skipped'] == 2
    assert 'required_ntfs_case' in counts


@pytest.mark.parametrize('fault', ['count', 'duplicate', 'missing-ntfs', 'malformed',
                                 'doctype', 'entity'],
                         ids=['wrong-count', 'duplicate-case', 'missing-required',
                              'malformed-xml', 'doctype', 'entity'])
def test_junit_invalid_or_incomplete_evidence_is_rejected(fault):
    if fault == 'count': raw = synthetic_junit(count=161)
    elif fault == 'duplicate': raw = synthetic_junit(duplicate=True)
    elif fault == 'missing-ntfs': raw = synthetic_junit(include_ntfs=False)
    elif fault == 'malformed': raw = b'<testsuites>PRIVATE-LOG-CONTENT'
    elif fault == 'doctype': raw = b'<!DOCTYPE suite SYSTEM "https://DO-NOT-CONNECT.invalid/x"><testsuites/>'
    else: raw = b'<!DOCTYPE suite [<!ENTITY e "do-not-expand">]><testsuites>&e;</testsuites>'
    with pytest.raises((validation.ValidationError, ValueError)):
        validation.junit_counts(raw)


def test_junit_multiple_outcomes_for_one_case_are_invalid():
    root = ET.fromstring(synthetic_junit(skipped=0))
    case = root.find('.//testcase')
    ET.SubElement(case, 'failure')
    ET.SubElement(case, 'error')
    with pytest.raises(validation.ValidationError):
        validation.junit_counts(ET.tostring(root, encoding='utf-8'))


@pytest.fixture
def operator(tmp_path, tmp_path_factory, monkeypatch):
    """Mocked native admission facts: output is test data, not Windows evidence."""
    repo = tmp_path / 'fake reviewed checkout'
    repo.mkdir()
    git_directory = tmp_path_factory.mktemp('operator trusted git')
    (git_directory / 'git.exe').write_bytes(b'Synthetic Git path fixture; never executed.\n')
    (git_directory / 'git.exe').chmod(0o700)
    head = 'a' * 40
    facts = {'head': head, 'baseline': validation.BASELINE,
             'branch': validation.BRANCH, 'pins': {'synthetic': 'b' * 40}}
    host = {'os': 'windows', 'native_windows': True, 'python': '3.12.0',
            'architecture': 'x64'}
    monkeypatch.setattr(validation, 'host_context', lambda: dict(host))
    monkeypatch.setattr(validation, 'verify_checkout', lambda *args, **kwargs: dict(facts))

    def synthetic_suite(repo, archive):
        archive.write('pytest/console.log', b'Synthetic fake test process record only.\n')
        archive.write('pytest/results.xml', synthetic_junit(skipped=0))
        return validation.junit_counts(synthetic_junit(skipped=0))

    monkeypatch.setattr(validation, '_run_pytest', synthetic_suite)
    return repo, head, git_directory / 'git.exe'


def invoke_operator(operator, output, **kwargs):
    repo, head, git_executable = operator
    return validation.run_operator(repo, head, output, controlled_inputs=True,
                                   powershell_version='7.7.0',
                                   git_executable=git_executable, **kwargs)


def test_operator_composition_seals_private_synthetic_fixture_evidence_without_dispatch(operator, tmp_path, monkeypatch):
    output = tmp_path / 'fresh operator outputs'
    forbid_dispatch(monkeypatch)
    result = invoke_operator(operator, output)
    assert result['runtime_qualified'] is False
    assert result['concurrent_path_isolation'] is False
    assert result['signature_trust'] == 'not_assessed'
    assert result['tests']['cases'] == 162
    assert result['tests']['passed'] == 162
    assert set(result['assessments']) == {'missing', 'normal_path', 'lexical_refusal', 'malformed_receipt'}
    for assessment in result['assessments'].values():
        assert assessment['input_class'] == 'generated_synthetic'
        assert assessment['qualification'] is False
    complete = load(output / 'COMPLETE.json')
    assert complete['runtime_qualified'] is False
    assert complete['result_sha256'] == sha((output / 'result.json').read_bytes())
    assert complete['inventory_sha256'] == sha((output / 'SHA256SUMS').read_bytes())
    for line in (output / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        expected, name = line.split('  ', 1)
        assert sha((output / name).read_bytes()) == expected
    assert not (output / 'FAILED.json').exists()


@pytest.mark.parametrize('failure', ['pytest', 'checkout-drift', 'write-failure'])
def test_operator_failure_preserves_partial_evidence_without_completion(operator, tmp_path, monkeypatch, failure):
    output = tmp_path / 'failed operator outputs'
    if failure == 'pytest':
        def fail(*args): raise validation.ValidationError('synthetic_regressions_failed')
        monkeypatch.setattr(validation, '_run_pytest', fail)
    elif failure == 'checkout-drift':
        original = validation.verify_checkout
        calls = 0
        def changed(*args, **kwargs):
            nonlocal calls
            calls += 1
            return {**original(*args, **kwargs), 'head': ('c' * 40 if calls > 1 else operator[1])}
        monkeypatch.setattr(validation, 'verify_checkout', changed)
    else:
        original = validation.Archive.write
        def fail_checksum(self, name, data):
            if name == 'SHA256SUMS': raise OSError('PRIVATE-OUTPUT-FAILURE /private/path')
            return original(self, name, data)
        monkeypatch.setattr(validation.Archive, 'write', fail_checksum)
    with pytest.raises((validation.ValidationError, OSError)):
        invoke_operator(operator, output)
    assert (output / 'STARTED.json').exists()
    failure_record = load(output / 'FAILED.json')
    assert failure_record['status'] == 'failed' and failure_record['runtime_qualified'] is False
    assert not (output / 'COMPLETE.json').exists()
    assert 'PRIVATE-OUTPUT-FAILURE' not in json.dumps(failure_record)
    assert '/private/path' not in json.dumps(failure_record)


@pytest.mark.parametrize('interruption_type', [KeyboardInterrupt, SystemExit],
                         ids=['keyboard-interrupt', 'system-exit'])
def test_operator_interruption_preserves_original_object_and_failure_record(operator, tmp_path, monkeypatch, interruption_type):
    output = tmp_path / 'interrupted outputs'
    original = interruption_type('original cancellation')
    def interrupt(*args): raise original
    monkeypatch.setattr(validation, '_run_pytest', interrupt)
    with pytest.raises(interruption_type) as caught:
        invoke_operator(operator, output)
    assert caught.value is original
    assert load(output / 'FAILED.json')['interrupted'] is True
    assert not (output / 'COMPLETE.json').exists()


def test_failure_record_write_does_not_mask_cancellation(operator, tmp_path, monkeypatch):
    original_error = KeyboardInterrupt('keep this original object')
    def interrupt(*args): raise original_error
    monkeypatch.setattr(validation, '_run_pytest', interrupt)
    original_json = validation.Archive.json
    def unavailable_failure_file(self, name, value):
        if name == 'FAILED.json': raise OSError('private failure output unavailable')
        return original_json(self, name, value)
    monkeypatch.setattr(validation.Archive, 'json', unavailable_failure_file)
    with pytest.raises(KeyboardInterrupt) as caught:
        invoke_operator(operator, tmp_path / 'failure during cancellation')
    assert caught.value is original_error
    assert any('could not be fully persisted' in note for note in original_error.__notes__)


def test_supplied_inputs_cannot_change_during_the_synthetic_test_phase(operator, inputs, tmp_path, monkeypatch):
    staging, manifest = inputs
    original_suite = validation._run_pytest
    def change_before_assessment(repo, archive):
        manifest.write_bytes(manifest.read_bytes() + b' ')
        return original_suite(repo, archive)
    monkeypatch.setattr(validation, '_run_pytest', change_before_assessment)
    output = tmp_path / 'input changed outputs'
    with pytest.raises(validation.ValidationError, match='input_changed'):
        invoke_operator(operator, output, manifest=manifest, staging_root=staging)
    assert load(output / 'FAILED.json')['status'] == 'failed'
    assert not (output / 'COMPLETE.json').exists()


@pytest.mark.parametrize('location', ['inside-repo', 'ancestor-repo', 'inside-staging', 'ancestor-staging'])
def test_operator_input_output_checkout_separation_precedes_archive_creation(operator, inputs, tmp_path, location):
    repo, *_ = operator
    staging, manifest = inputs
    if location == 'inside-repo': output = repo / 'outputs'
    elif location == 'ancestor-repo': output = repo.parent
    elif location == 'inside-staging': output = staging / 'outputs'
    else: output = staging.parent
    existing = output.exists()
    with pytest.raises(validation.ValidationError, match='locations_overlap'):
        invoke_operator(operator, output, manifest=manifest, staging_root=staging)
    assert output.exists() is existing


def test_native_entry_rejects_linux_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.setattr(validation, 'host_context', lambda: {'native_windows': False})
    output = tmp_path / 'not native outputs'
    with pytest.raises(validation.ValidationError, match='native_windows_required'):
        validation.run_operator(tmp_path, 'a' * 40, output, controlled_inputs=True)
    assert not output.exists()


def test_controlled_input_acknowledgment_is_required_before_any_work(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Unacknowledged run did work')
    monkeypatch.setattr(validation, 'verify_checkout', forbidden)
    with pytest.raises(validation.ValidationError, match='controlled_inputs_not_confirmed'):
        validation.run_operator(tmp_path, 'a' * 40, tmp_path / 'outputs')


def test_child_environment_disables_implicit_plugins_and_interpreter_expansion(monkeypatch):
    cleared = ['PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTEST_DEBUG', 'PYTHONPATH', 'PYTHONHOME',
               'PYTHONINSPECT', 'PYTHONSTARTUP', 'PYTHONPYCACHEPREFIX', 'GITHUB_STEP_SUMMARY']
    for name in cleared: monkeypatch.setenv(name, 'PRIVATE-HOST-VALUE')
    actual = validation._child_environment()
    assert all(name not in actual for name in cleared)
    assert actual['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    assert actual['PYTHONDONTWRITEBYTECODE'] == '1'
    assert actual['PYTHONNOUSERSITE'] == '1'
    assert all(__import__('os').environ[name] == 'PRIVATE-HOST-VALUE' for name in cleared)


@pytest.fixture
def git_facts(tmp_path, monkeypatch):
    repo = tmp_path / 'synthetic checkout facts'
    repo.mkdir()
    git_directory = tmp_path / 'validated tools'
    git_directory.mkdir()
    git_executable = git_directory / 'git.exe'
    git_executable.write_bytes(b'Synthetic Git path fixture; never executed.\n')
    git_executable.chmod(0o700)
    head = 'a' * 40
    facts = {'head': head, 'branch': validation.BRANCH, 'status': '', 'changes': '',
             'pin_drift': False, 'calls': [], 'git_executable': git_executable,
             'blob': b'# Synthetic reviewed source bytes only.\n',
             'config_keys': b'', 'index_entries': b'H README.md\0', 'toplevel': str(repo)}
    for name in set(validation.PINS) | set(validation.ADDITIONS):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(facts['blob'])
    def fake_git(selected, *args, **kwargs):
        assert selected == repo
        assert Path(kwargs['executable']) == git_executable
        facts['calls'].append(args)
        if args == ('rev-parse', '--show-toplevel'):
            return facts['toplevel']
        if args[0] == 'config':
            assert kwargs.get('raw') is True
            return facts['config_keys']
        if args[0] == 'ls-files':
            assert kwargs.get('raw') is True
            assert args[-1] == ':(exclude)evidence/**'
            return facts['index_entries']
        if args[0] == 'show':
            assert kwargs.get('raw') is True
            return facts['blob']
        if args == ('rev-parse', 'HEAD'): return facts['head']
        if args == ('branch', '--show-current'): return facts['branch']
        if args[0] == 'status':
            assert args[-1] == ':(exclude)evidence/**'
            return facts['status']
        if args[0] == 'merge-base': return ''
        if args[0] == 'diff': return facts['changes']
        if args[0] == 'rev-parse':
            return ('c' * 40 if facts['pin_drift'] and args[1].startswith(head + ':')
                    else 'b' * 40)
        raise AssertionError('Unexpected Git operation: ' + repr(args))
    monkeypatch.setattr(validation, '_git', fake_git)
    return repo, head, facts


def test_checkout_requires_reviewed_head_clean_target_branch_and_all_baseline_pins(git_facts):
    repo, head, facts = git_facts
    result = validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert result['head'] == head and result['baseline'] == validation.BASELINE
    assert result['branch'] == validation.BRANCH
    assert set(result['pins']) == set(validation.PINS)
    assert ('merge-base', '--is-ancestor', validation.BASELINE, head) in facts['calls']


@pytest.mark.parametrize('fault', ['head', 'branch', 'detached', 'dirty', 'untracked', 'source', 'pin'])
def test_checkout_drift_is_rejected_without_mutating_git(git_facts, fault):
    repo, head, facts = git_facts
    if fault == 'head': facts['head'] = 'd' * 40
    elif fault == 'branch': facts['branch'] = 'main'
    elif fault == 'detached': facts['branch'] = ''
    elif fault == 'dirty': facts['status'] = ' M tools/windows_runtime_preflight.py'
    elif fault == 'untracked': facts['status'] = '?? unrelated-user-file.txt'
    elif fault == 'source': facts['changes'] = 'firmavex/product/platform_support.py'
    else: facts['pin_drift'] = True
    with pytest.raises(validation.ValidationError):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert all(args[0] not in {'reset', 'clean', 'stash', 'checkout', 'switch', 'merge', 'pull',
                               'rebase', 'commit', 'push'} for args in facts['calls'])


@pytest.mark.parametrize('head', ['short', 'A' * 40, 'g' * 40, True, None],
                         ids=['short', 'uppercase', 'nonhex', 'bool', 'null'])
def test_expected_revision_is_exact_lowercase_before_git_reads(git_facts, head):
    repo, _, facts = git_facts
    with pytest.raises(validation.ValidationError):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert facts['calls'] == []


def test_git_failure_never_exposes_raw_git_diagnostics(tmp_path, monkeypatch):
    repo = tmp_path / 'checkout'
    repo.mkdir()
    git_executable = tmp_path / 'git.exe'
    git_executable.write_bytes(b'Synthetic Git path fixture; never executed.\n')
    git_executable.chmod(0o700)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 1, 'PRIVATE-SOURCE-PATH', 'TOKEN=PRIVATE'))
    with pytest.raises(validation.ValidationError, match='git_check_failed') as caught:
        validation._git(repo, 'rev-parse', 'HEAD', executable=git_executable)
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('fault', ['base-python', 'old-python', 'missing-pytest'])
def test_native_operator_requires_existing_supported_python_environment(operator, tmp_path, monkeypatch, fault):
    if fault in {'base-python', 'old-python'}:
        monkeypatch.setattr(validation, 'sys', SimpleNamespace(
            prefix=sys.base_prefix if fault == 'base-python' else sys.prefix,
            base_prefix=sys.base_prefix,
            version_info=(3, 10, 0) if fault == 'old-python' else sys.version_info))
    else: monkeypatch.setattr(validation.importlib.util, 'find_spec', lambda name: None)
    output = tmp_path / 'no environment outputs'
    with pytest.raises(validation.ValidationError, match='existing_python_environment_required'):
        invoke_operator(operator, output)
    assert not output.exists()


@pytest.fixture
def fake_pytest_child(tmp_path, monkeypatch):
    """No process runs: model the ownership/admission/cleanup contract."""
    from firmavex.product import windows_job
    events = []
    controls = {'wait_error': None, 'assign_error': None, 'close_error': None,
                'returncode': 0, 'calls': []}
    class Input(io.BytesIO):
        def write(self, data):
            events.append(('admitted', data))
            return super().write(data)
    class Child:
        pid = 12345
        _handle = 123
        def __init__(self):
            self.stdin = Input()
            self.returncode = controls['returncode']
            self.waits = 0
        def wait(self, timeout):
            self.waits += 1
            events.append(('wait', timeout))
            if self.waits == 1 and controls['wait_error'] is not None:
                self.returncode = None
                raise controls['wait_error']
            return self.returncode
        def poll(self): return self.returncode
        def kill(self):
            events.append(('kill',))
            self.returncode = -9
    child = Child()
    class Job:
        def __init__(self): events.append(('job-created',))
        def assign(self, handle):
            events.append(('assigned', handle))
            if controls['assign_error'] is not None: raise controls['assign_error']
        def close(self):
            events.append(('job-closed',))
            if controls['close_error'] is not None: raise controls['close_error']
    def popen(command, **kwargs):
        events.append(('popen',))
        controls['calls'].append((command, kwargs))
        kwargs['stdout'].write(b'Synthetic child log; no process executed.\n')
        report = next(value.split('=', 1)[1] for value in command if value.startswith('--junitxml='))
        Path(report).write_bytes(synthetic_junit(skipped=0))
        return child
    monkeypatch.setattr(subprocess, 'Popen', popen)
    monkeypatch.setattr(windows_job, 'WindowsJob', Job)
    monkeypatch.setattr(validation, 'os', SimpleNamespace(name='nt', environ=os.environ,
                                                        fsync=os.fsync, fspath=os.fspath))
    return child, controls, events


def test_pytest_child_is_owned_before_admission_and_fixed_selection_is_preserved(tmp_path, fake_pytest_child):
    child, controls, events = fake_pytest_child
    archive = validation.Archive(tmp_path / 'child outputs')
    counts = validation._run_pytest(tmp_path, archive)
    assert counts['passed'] == 162 and counts['cases'] == 162
    assert events.index(('assigned', child._handle)) < events.index(('admitted', b'1'))
    assert ('job-closed',) in events
    assert ('wait', 240) in events and ('wait', 10) in events
    command, kwargs = controls['calls'][0]
    assert command[0] == sys.executable
    assert all(path in command for path in validation.SELECTION)
    assert kwargs['env']['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    assert any(left == '-c' and right == str(tmp_path / 'pyproject.toml')
               for left, right in zip(command, command[1:]))
    temp_options = [item.split('=', 1)[1] for item in command if item.startswith('--basetemp=')]
    if '--basetemp' in command:
        temp_options.append(command[command.index('--basetemp') + 1])
    assert len(temp_options) == 1
    temporary = Path(temp_options[0])
    # The mocked pytest never creates its fresh basetemp. Pre-creating or
    # reusing it would permit pytest to delete pre-existing user contents.
    assert archive.root in temporary.parents and not temporary.exists()
    process_temps = {kwargs['env'][name] for name in ('TMP', 'TEMP', 'TMPDIR')}
    assert len(process_temps) == 1
    process_temp = Path(process_temps.pop())
    assert archive.root in process_temp.parents and process_temp.is_dir()
    assert process_temp != temporary
    assert '--confcutdir=' + str(tmp_path) in command
    assert kwargs['stdin'] is subprocess.PIPE
    assert child.stdin.closed


@pytest.mark.parametrize('failure', ['assignment', 'timeout', 'cancel', 'cleanup'])
def test_pytest_failures_still_close_owner_and_reap_child(tmp_path, fake_pytest_child, failure):
    child, controls, events = fake_pytest_child
    if failure == 'assignment':
        controls['assign_error'] = OSError('assignment failed')
        child.returncode = None
        expected = OSError
    elif failure == 'timeout':
        controls['wait_error'] = subprocess.TimeoutExpired('synthetic-child', 240)
        expected = subprocess.TimeoutExpired
    elif failure == 'cancel':
        controls['wait_error'] = KeyboardInterrupt('original child cancellation')
        controls['close_error'] = OSError('cleanup also failed')
        expected = KeyboardInterrupt
    else:
        controls['close_error'] = OSError('cleanup failed')
        expected = validation.ValidationError
    archive = validation.Archive(tmp_path / 'failed child outputs')
    with pytest.raises(expected) as caught:
        validation._run_pytest(tmp_path, archive)
    assert ('job-closed',) in events
    assert ('wait', 10) in events and child.stdin.closed
    if failure == 'assignment': assert ('admitted', b'1') not in events
    if failure == 'cancel': assert caught.value is controls['wait_error']


class _SyntheticAbort(BaseException):
    """Invented control-flow exception; never runtime or firmware evidence."""


@pytest.mark.parametrize('exception_type', [KeyboardInterrupt, SystemExit, _SyntheticAbort],
                         ids=['keyboard-interrupt', 'system-exit', 'custom-control-flow'])
def test_cleanup_only_control_flow_is_not_converted_into_validation_error(tmp_path, fake_pytest_child, exception_type):
    child, controls, events = fake_pytest_child
    original = exception_type('original cleanup control flow')
    controls['close_error'] = original
    archive = validation.Archive(tmp_path / 'cleanup interrupted outputs')
    with pytest.raises(exception_type) as caught:
        validation._run_pytest(tmp_path, archive)
    assert caught.value is original
    assert ('job-closed',) in events and ('wait', 10) in events
    assert child.stdin.closed


@pytest.mark.parametrize('exception_type', [KeyboardInterrupt, SystemExit, _SyntheticAbort],
                         ids=['keyboard-interrupt', 'system-exit', 'custom-control-flow'])
def test_cleanup_control_flow_takes_precedence_over_an_ordinary_child_error(tmp_path, fake_pytest_child, exception_type):
    child, controls, events = fake_pytest_child
    controls['wait_error'] = OSError('ordinary child wait failure')
    original = exception_type('cleanup requires control-flow propagation')
    controls['close_error'] = original
    archive = validation.Archive(tmp_path / 'ordinary failure then cleanup interruption')
    with pytest.raises(exception_type) as caught:
        validation._run_pytest(tmp_path, archive)
    assert caught.value is original
    assert ('job-closed',) in events and ('wait', 10) in events
    assert child.stdin.closed


@pytest.mark.parametrize('cleanup_type', [SystemExit, _SyntheticAbort],
                         ids=['system-exit', 'custom-control-flow'])
def test_existing_child_interruption_is_preserved_over_cleanup_control_flow(tmp_path, fake_pytest_child, cleanup_type):
    child, controls, events = fake_pytest_child
    original = KeyboardInterrupt('original active interruption')
    controls['wait_error'] = original
    controls['close_error'] = cleanup_type('later cleanup interruption')
    archive = validation.Archive(tmp_path / 'preserved first interruption')
    with pytest.raises(KeyboardInterrupt) as caught:
        validation._run_pytest(tmp_path, archive)
    assert caught.value is original
    assert ('wait', 10) in events and child.stdin.closed


@pytest.mark.parametrize('persistence_type', [KeyboardInterrupt, SystemExit, _SyntheticAbort],
                         ids=['keyboard-interrupt', 'system-exit', 'custom-control-flow'])
def test_failure_persistence_control_flow_promotes_over_ordinary_failure(operator, tmp_path, monkeypatch, persistence_type):
    original = persistence_type('new interruption while retaining failure')
    def ordinary_failure(*args): raise OSError('ordinary pytest failure')
    monkeypatch.setattr(validation, '_run_pytest', ordinary_failure)
    original_json = validation.Archive.json
    def interrupted_persistence(self, name, value):
        if name == 'FAILED.json': raise original
        return original_json(self, name, value)
    monkeypatch.setattr(validation.Archive, 'json', interrupted_persistence)
    output = tmp_path / 'failure retention interrupted'
    with pytest.raises(persistence_type) as caught:
        invoke_operator(operator, output)
    assert caught.value is original
    assert (output / 'STARTED.json').exists()
    assert not (output / 'COMPLETE.json').exists()


@pytest.mark.parametrize('persistence_type', [OSError, SystemExit, _SyntheticAbort],
                         ids=['ordinary-error', 'system-exit', 'custom-control-flow'])
def test_failure_persistence_preserves_existing_control_flow(operator, tmp_path, monkeypatch, persistence_type):
    original = KeyboardInterrupt('first original interruption')
    def interruption(*args): raise original
    monkeypatch.setattr(validation, '_run_pytest', interruption)
    original_json = validation.Archive.json
    def unavailable_persistence(self, name, value):
        if name == 'FAILED.json': raise persistence_type('later failure retention problem')
        return original_json(self, name, value)
    monkeypatch.setattr(validation.Archive, 'json', unavailable_persistence)
    with pytest.raises(KeyboardInterrupt) as caught:
        invoke_operator(operator, tmp_path / 'keep active interruption')
    assert caught.value is original


def test_git_uses_only_the_explicit_validated_absolute_executable(tmp_path, monkeypatch):
    repo = tmp_path / 'checkout'
    repo.mkdir()
    directory = tmp_path / 'operator chosen tools'
    directory.mkdir()
    executable = directory / 'git.exe'
    executable.write_bytes(b'Synthetic Git fixture; subprocess execution is mocked.\n')
    executable.chmod(0o700)
    calls = []
    def supplied_git_only(command, **kwargs):
        calls.append((command, kwargs))
        assert command[0] == str(executable)
        assert command[-2:] == ['rev-parse', 'HEAD']
        assert command[command.index('-C') + 1] == str(repo)
        assert '--no-optional-locks' in command and '--no-pager' in command
        settings = [right for left, right in zip(command, command[1:]) if left == '-c']
        assert 'core.fsmonitor=false' in settings
        assert 'core.hooksPath=' + str(executable) in settings
        assert kwargs.get('shell') is not True
        return subprocess.CompletedProcess(command, 0, 'a' * 40 + '\n', '')
    monkeypatch.setattr(subprocess, 'run', supplied_git_only)
    monkeypatch.setenv('PATH', str(tmp_path / 'DO-NOT-DISCOVER-ANOTHER-GIT'))
    assert validation._git(repo, 'rev-parse', 'HEAD', executable=executable) == 'a' * 40
    assert len(calls) == 1


@pytest.mark.parametrize('executable', [None, 'git', 'relative/git.exe'],
                         ids=['not-supplied', 'bare-path-search', 'relative'])
def test_git_never_falls_back_to_path_for_missing_or_relative_selection(tmp_path, monkeypatch, executable):
    def forbidden(*args, **kwargs): raise AssertionError('Unvalidated Git was dispatched')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(validation.ValidationError):
        validation._git(tmp_path, 'rev-parse', 'HEAD', executable=executable)


def test_operator_passes_the_selected_git_to_both_checkout_checks(operator, tmp_path, monkeypatch):
    seen = []
    original = validation.verify_checkout
    def selected_git_only(*args, **kwargs):
        seen.append(Path(kwargs['git_executable']))
        return original(*args, **kwargs)
    monkeypatch.setattr(validation, 'verify_checkout', selected_git_only)
    invoke_operator(operator, tmp_path / 'explicit git propagation')
    selected = operator[2]
    assert seen == [selected, selected]


def test_git_child_cannot_inherit_repository_redirection_or_configuration_helpers(tmp_path, monkeypatch):
    repo = tmp_path / 'checkout'
    repo.mkdir()
    directory = tmp_path / 'host tools'
    directory.mkdir()
    executable = directory / 'git.exe'
    executable.write_bytes(b'Synthetic Git path; never executed.\n')
    executable.chmod(0o700)
    hostile = [
        'GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
        'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_EXTERNAL_DIFF',
        'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0', 'GIT_CONFIG',
        'GIT_CONFIG_PARAMETERS', 'GIT_SSH_COMMAND', 'GIT_ASKPASS', 'GIT_TRACE',
        'git_dir', 'gIt_Work_Tree', 'git_config_global', 'GIT_NO_REPLACE_OBJECTS',
    ]
    for name in hostile:
        monkeypatch.setenv(name, 'PRIVATE-GIT-INJECTION')
    captured = []
    def safe_git_only(command, **kwargs):
        captured.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, 'a' * 40, '')
    monkeypatch.setattr(subprocess, 'run', safe_git_only)
    assert validation._git(repo, 'rev-parse', 'HEAD', executable=executable) == 'a' * 40
    command, options = captured[0]
    assert command[0] == str(executable)
    environment = options['env']
    assert 'PRIVATE-GIT-INJECTION' not in environment.values()
    assert environment['GIT_CONFIG_NOSYSTEM'] == '1'
    assert environment['GIT_CONFIG_GLOBAL'] == os.devnull
    assert environment.get('GIT_CONFIG_SYSTEM', os.devnull) == os.devnull
    assert environment['GIT_NO_REPLACE_OBJECTS'] == '1'
    assert all(name.upper() not in {item.upper() for item in environment}
               for name in hostile if name.upper() not in {'GIT_CONFIG_GLOBAL', 'GIT_NO_REPLACE_OBJECTS'})
    assert all(os.environ[name] == 'PRIVATE-GIT-INJECTION' for name in hostile)


def test_checkout_diff_disables_external_diff_and_text_conversion(git_facts):
    repo, head, facts = git_facts
    validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    commands = [args for args in facts['calls'] if args[0] == 'diff']
    assert len(commands) == 1
    assert '--no-ext-diff' in commands[0]
    assert '--no-textconv' in commands[0]


@pytest.mark.parametrize('name,allowed', [('git', False), ('git.exe', True)],
                         ids=['extensionless-refused', 'explicit-exe-accepted'])
def test_windows_git_selection_never_relies_on_implicit_executable_suffix(tmp_path, monkeypatch, name, allowed):
    repo = tmp_path / 'checkout'
    repo.mkdir()
    executable = tmp_path / name
    executable.write_bytes(b'Synthetic path-validation fixture; never executed.\n')
    executable.chmod(0o700)
    monkeypatch.setattr(validation, 'os', SimpleNamespace(name='nt', fspath=os.fspath))
    if allowed:
        assert validation._validated_git(repo, executable) == executable
    else:
        with pytest.raises(validation.ValidationError, match='unsafe_git_executable'):
            validation._validated_git(repo, executable)


def test_post_complete_fsync_failure_retains_failure_that_overrides_raw_completion_marker(operator, tmp_path, monkeypatch):
    """COMPLETE's existence is not authoritative if failure persistence follows."""
    original_open = Path.open
    original_fsync = os.fsync
    names = {}
    attempted_complete = False
    def observe_archive_open(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if mode == 'xb': names[stream.fileno()] = path.name
        return stream
    def fail_complete_sync(fd):
        nonlocal attempted_complete
        if names.get(fd) == 'COMPLETE.json':
            attempted_complete = True
            raise OSError('Synthetic final completion fsync failed')
        return original_fsync(fd)
    monkeypatch.setattr(Path, 'open', observe_archive_open)
    monkeypatch.setattr(validation.os, 'fsync', fail_complete_sync)
    output = tmp_path / 'failed final completion sync'
    with pytest.raises(OSError, match='completion fsync'):
        invoke_operator(operator, output)
    assert attempted_complete
    assert (output / 'COMPLETE.json').exists()
    failure = load(output / 'FAILED.json')
    assert failure['status'] == 'failed' and failure['runtime_qualified'] is False
    # A complete-looking marker is deliberately retained as partial evidence;
    # consumers must treat the retained FAILED marker as authoritative.
    assert load(output / 'COMPLETE.json')['runtime_qualified'] is False


@pytest.mark.parametrize('code', ['revision_mismatch', 'checkout_not_clean'],
                         ids=['wrong-head', 'dirty-checkout'])
def test_checkout_gate_precedes_supplied_input_snapshot_or_output_creation(operator, inputs, tmp_path, monkeypatch, code):
    staging, manifest = inputs
    before = manifest.read_bytes()
    def reject_checkout(*args, **kwargs):
        assert Path(kwargs['git_executable']) == operator[2]
        raise validation.ValidationError(code)
    def forbidden(*args, **kwargs):
        raise AssertionError('Supplied inputs were assessed before checkout admission')
    monkeypatch.setattr(validation, 'verify_checkout', reject_checkout)
    monkeypatch.setattr(validation, 'snapshot', forbidden)
    monkeypatch.setattr(validation.preflight, 'preflight', forbidden)
    output = tmp_path / 'unadmitted outputs'
    with pytest.raises(validation.ValidationError, match=code):
        invoke_operator(operator, output, manifest=manifest, staging_root=staging)
    assert not output.exists()
    assert manifest.read_bytes() == before


@pytest.mark.parametrize('change', ['meaningful-code', 'extra-whitespace'])
def test_reviewed_source_bytes_are_checked_even_when_git_status_and_objects_look_clean(git_facts, change):
    repo, head, facts = git_facts
    selected = repo / validation.PINS[0]
    addition = b'print("unreviewed synthetic source")\n' if change == 'meaningful-code' else b' \n'
    selected.write_bytes(facts['blob'] + addition)
    assert facts['status'] == '' and facts['pin_drift'] is False
    with pytest.raises(validation.ValidationError):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])


def test_reviewed_text_accepts_only_declared_crlf_normalization(git_facts):
    repo, head, facts = git_facts
    selected = repo / validation.PINS[0]
    selected.write_bytes(facts['blob'].replace(b'\n', b'\r\n'))
    result = validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert result['head'] == head
    assert set(result['pins']) == set(validation.PINS)
    assert result['pins'][validation.PINS[0]]['working_tree_sha256'] == sha(selected.read_bytes())
    assert result['pins'][validation.PINS[0]]['normalized_sha256'] == sha(facts['blob'])


def test_new_harness_source_bytes_cannot_hide_behind_clean_git_status(git_facts):
    repo, head, facts = git_facts
    selected = repo / 'tools/windows_preflight_validation.py'
    selected.write_bytes(facts['blob'] + b'# Unreviewed synthetic harness change.\n')
    with pytest.raises(validation.ValidationError, match='working_source_drift'):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])


def test_git_worktree_redirection_is_refused_before_status_or_source_reads(git_facts):
    repo, head, facts = git_facts
    facts['toplevel'] = str(repo.parent / 'different-worktree')
    with pytest.raises(validation.ValidationError, match='git_worktree_redirected'):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert facts['calls'] == [('rev-parse', '--show-toplevel')]


@pytest.mark.parametrize('entry', [b'h reviewed.py\0', b'S reviewed.py\0'],
                         ids=['assume-unchanged', 'skip-worktree'])
def test_index_visibility_flags_are_refused_before_status_or_source_assessment(git_facts, entry):
    repo, head, facts = git_facts
    facts['index_entries'] = entry
    with pytest.raises(validation.ValidationError):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert not any(args[0] == 'status' for args in facts['calls'])


@pytest.mark.parametrize('key', [b'filter.private.clean\0', b'include.path\0',
                               b'includeif.gitdir:private.path\0'],
                         ids=['clean-filter', 'config-include', 'conditional-include'])
def test_local_git_filter_or_include_configuration_is_not_allowed_to_trigger_status(git_facts, key):
    repo, head, facts = git_facts
    facts['config_keys'] = key
    with pytest.raises(validation.ValidationError):
        validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert not any(args[0] == 'status' for args in facts['calls'])


def test_ordinary_local_git_configuration_does_not_require_relaxing_guards(git_facts):
    repo, head, facts = git_facts
    facts['config_keys'] = b'core.repositoryformatversion\0core.bare\0'
    result = validation.verify_checkout(repo, head, git_executable=facts['git_executable'])
    assert result['head'] == head


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-16-le', 'utf-16-be'])
def test_non_utf8_xml_cannot_bypass_preparse_entity_guard(monkeypatch, encoding):
    raw = ('<?xml version="1.0"?><!DOCTYPE suite [<!ENTITY e "DO-NOT-EXPAND">]>'
           '<testsuites>&e;</testsuites>').encode(encoding)
    def forbidden(*args, **kwargs):
        raise AssertionError('Unsupported encoded XML reached entity parser')
    monkeypatch.setattr(validation.ET, 'fromstring', forbidden)
    with pytest.raises(validation.ValidationError):
        validation.junit_counts(raw)


@pytest.mark.parametrize('raw', [b'\xff<testsuites/>', b'<testsuites>\x00</testsuites>'],
                         ids=['invalid-utf8', 'embedded-nul'])
def test_invalid_xml_encoding_is_refused_before_parser(monkeypatch, raw):
    def forbidden(*args, **kwargs):
        raise AssertionError('Malformed XML bytes reached parser')
    monkeypatch.setattr(validation.ET, 'fromstring', forbidden)
    with pytest.raises(validation.ValidationError):
        validation.junit_counts(raw)
