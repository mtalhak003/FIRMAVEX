"""Candidate harness tests; synthetic fixtures are not Windows qualification."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

from tools import windows_runtime_candidate as candidate
from firmavex.product.tools import Toolchain

HEAD = 'a' * 40


def environment():
    return {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'mtalhak003/FIRMAVEX',
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_WORKFLOW_REF': candidate.WORKFLOW,
            'GITHUB_SHA': HEAD, 'FIRMAVEX_CANDIDATE_REVISION': HEAD, 'GITHUB_RUN_ID': '123'}


@pytest.mark.parametrize('key,value', [
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_REPOSITORY', 'other/repository'),
    ('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_WORKFLOW_REF', 'other'),
    ('GITHUB_SHA', 'b' * 40), ('FIRMAVEX_CANDIDATE_REVISION', ''), ('GITHUB_RUN_ID', 'bad'),
])
def test_candidate_context_fails_closed(key, value):
    env = environment(); env[key] = value
    with pytest.raises(ValueError): candidate.context(env, 'win32', 'AMD64', HEAD)


@pytest.mark.parametrize('system,machine', [('linux', 'x86_64'), ('win32', 'ARM64'), ('darwin', 'arm64')])
def test_non_native_or_other_architectures_cannot_be_labeled_windows(system, machine):
    with pytest.raises(ValueError): candidate.context(environment(), system, machine, HEAD)


def test_explicit_context_is_bound_to_commit_and_run():
    record = candidate.context(environment(), 'win32', 'AMD64', HEAD)
    assert record == {'source_revision': HEAD, 'run_id': '123',
                      'host': {'os': 'Windows', 'architecture': 'x86_64'}}


@pytest.fixture
def candidate_runner_paths(tmp_path, monkeypatch):
    """Synthetic host context; use the real environment/path validation."""
    temporary = tmp_path / 'runner temp'; temporary.mkdir()
    root = temporary / 'vendor'; root.mkdir()
    for key, value in {**environment(), 'RUNNER_TEMP': str(temporary)}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(candidate, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(candidate, 'platform', SimpleNamespace(machine=lambda: 'AMD64'))
    def revision(command, **kwargs):
        assert command == ['git', 'rev-parse', 'HEAD']
        assert kwargs == {'text': True, 'timeout': 10}
        return HEAD + '\n'
    monkeypatch.setattr(candidate.subprocess, 'check_output', revision)
    return temporary, root, temporary / 'source-probe'


@pytest.mark.parametrize('layout', ['existing', 'new', 'new-nested'])
def test_environment_validates_output_as_directory_without_creating_or_overwriting(candidate_runner_paths, layout):
    temporary, root, output = candidate_runner_paths
    if layout == 'existing':
        output.mkdir(); (output / 'sentinel').write_bytes(b'preserve')
    elif layout == 'new-nested':
        output = temporary / 'new-parent' / 'source-probe'
    record, selected_root, selected_output = candidate._environment(root, output)
    assert record['source_revision'] == HEAD and record['run_id'] == '123'
    assert selected_root == root and selected_output == output
    if layout == 'existing':
        assert [path.name for path in output.iterdir()] == ['sentinel']
        assert (output / 'sentinel').read_bytes() == b'preserve'
    else:
        assert not output.exists()
        if layout == 'new-nested': assert not output.parent.exists()


@pytest.mark.parametrize('kind', ['file', 'file-parent', 'traversal', 'control', 'outside-runner', 'inside-vendor'])
def test_environment_rejects_unsafe_output_paths(candidate_runner_paths, kind):
    temporary, root, output = candidate_runner_paths
    if kind == 'file': output.write_bytes(b'preserve')
    elif kind == 'file-parent':
        output.write_bytes(b'preserve'); output = output / 'child'
    elif kind == 'traversal': output = temporary / 'unused' / '..' / 'source-probe'
    elif kind == 'control': output = temporary / 'bad\nname'
    elif kind == 'outside-runner': output = temporary.parent / 'outside'
    else: output = root / 'source-probe'
    with pytest.raises(ValueError): candidate._environment(root, output)
    if kind in {'file', 'file-parent'}:
        assert (temporary / 'source-probe').read_bytes() == b'preserve'


@pytest.mark.parametrize('kind', ['symlink', 'dangling', 'symlink-parent'])
def test_environment_rejects_output_symlinks_and_linked_parents(candidate_runner_paths, kind):
    temporary, root, output = candidate_runner_paths
    target = temporary / 'other'
    if kind != 'dangling': target.mkdir()
    try: output.symlink_to(target, target_is_directory=True)
    except OSError: pytest.skip('Host cannot create directory symlinks')
    selected = output / 'child' if kind == 'symlink-parent' else output
    with pytest.raises(ValueError, match='Symlink/reparse'):
        candidate._environment(root, selected)


@pytest.mark.parametrize('parent', [False, True])
def test_environment_rejects_windows_output_reparse_metadata(candidate_runner_paths, monkeypatch, parent):
    _, root, output = candidate_runner_paths
    output.mkdir()
    original = Path.lstat
    def metadata(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path == output:
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith('st_')}
            fields['st_file_attributes'] = 0x400
            return SimpleNamespace(**fields)
        return value
    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(ValueError, match='Symlink/reparse'):
        candidate._environment(root, output / 'child' if parent else output)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='POSIX special-file regression')
def test_environment_rejects_special_output_file(candidate_runner_paths):
    _, root, output = candidate_runner_paths
    os.mkfifo(output)
    with pytest.raises(ValueError): candidate._environment(root, output)


def test_preflight_still_rejects_existing_output_without_overwrite(candidate_runner_paths):
    temporary, root, output = candidate_runner_paths
    output.mkdir(); (output / 'sentinel').write_bytes(b'preserve')
    with pytest.raises(FileExistsError, match='Candidate output must be new'):
        candidate.preflight(root, temporary / 'not-read-packages', temporary / 'not-read-policy', output)
    assert [path.name for path in output.iterdir()] == ['sentinel']
    assert (output / 'sentinel').read_bytes() == b'preserve'


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    root = tmp_path / 'vendor'
    identities, pins = {}, {}
    for name, filename in [('qemu', 'qemu-system-arm.exe'), ('gdb', 'gdb-multiarch.exe')]:
        path = root / 'bin' / filename; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('synthetic fixture: ' + name).encode())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pins[name] = candidate.CANDIDATE[name][0], digest
        identities[name] = {'version': pins[name][0], 'sha256': digest, 'size_bytes': path.stat().st_size}
    license = root / 'share/licenses/fixture/COPYING'
    license.parent.mkdir(parents=True); license.write_text('synthetic license fixture')
    tools = Toolchain(str(root / 'bin/qemu-system-arm.exe'), str(root / 'bin/gdb-multiarch.exe'), identities=identities)
    monkeypatch.setattr(candidate, 'CANDIDATE', pins)
    return root, tools


@pytest.mark.parametrize('name,field', [('qemu', 'version'), ('qemu', 'sha256'), ('gdb', 'version'), ('gdb', 'sha256')])
def test_candidate_pin_rejects_each_changed_field(vendor, name, field):
    root, tools = vendor
    tools.identities[name][field] = 'changed'
    with pytest.raises(ValueError): candidate.verify_tools(tools, root)


def test_candidate_checks_real_bytes_and_declared_prefix(vendor, tmp_path):
    root, tools = vendor
    candidate.verify_tools(tools, root)
    Path(tools.qemu).write_bytes(b'changed after discovery')
    with pytest.raises(ValueError): candidate.verify_tools(tools, root)
    with pytest.raises(ValueError): candidate.verify_tools(tools, tmp_path)


@pytest.mark.parametrize('policy', ['', 'PackageOptional PackageTrustedOnly',
    'PackageRequired PackageTrustAll', 'PackageRequired PackageTrustedOnly DatabaseTrustAll'])
def test_signatures_cannot_be_optional_or_trust_all(policy):
    with pytest.raises(ValueError): candidate.signature_policy(policy)


def test_required_trusted_publisher_signatures_and_exact_packages():
    assert candidate.signature_policy('PackageRequired\nPackageTrustedOnly\nDatabaseOptional\nDatabaseTrustedOnly')
    data = '\n'.join(f'{name} {version}' for name, version in candidate.PACKAGES.items())
    assert candidate.package_inventory(data) == candidate.PACKAGES
    for changed in [data.replace('11.1.3-1', '11.1.4-1'), data+'\n'+data, data+'\nsecret https://user:password@host', 'x' * (1024**2+1)]:
        with pytest.raises(ValueError): candidate.package_inventory(changed)


def test_pacman_inventory_accepts_case_sensitive_dependency_names():
    # Publisher QEMU dependencies include SDL2 and SDL2_image, not lowercase names.
    dependencies = {'mingw-w64-ucrt-x86_64-SDL2': '2.32.10-1',
                    'mingw-w64-ucrt-x86_64-SDL2_image': '2.8.8-1',
                    'Uppercase': '1:2.0-1', 'uppercase': '3.0-1'}
    expected = {**candidate.PACKAGES, **dependencies}
    data = '\r\n'.join(f'{name} {version}' for name, version in expected.items()) + '\r\n'
    assert candidate.package_inventory(data) == expected


@pytest.mark.parametrize('row', [
    '', 'only-name', 'three fields here', '.hidden 1.0-1', '-option 1.0-1',
    'mingw-w64-ucrt-x86_64-SDL2/other 1.0-1', 'SDL2:other 1.0-1',
    'SDL2;command 1.0-1', 'SDL\u00e9 1.0-1', 'SDL2 https://user:password@host',
    'SDL2 1.0-1;command', 'SDL2 ' + '1' * 129, 'A' * 161 + ' 1.0-1',
])
def test_pacman_inventory_still_rejects_malformed_rows(row):
    data = '\n'.join(f'{name} {version}' for name, version in candidate.PACKAGES.items())
    with pytest.raises(ValueError, match='Invalid or duplicate'):
        candidate.package_inventory(data + '\n' + row + '\n')


def test_pacman_inventory_rejects_exact_uppercase_duplicates():
    data = '\n'.join(f'{name} {version}' for name, version in candidate.PACKAGES.items())
    for version in ('2.32.10-1', '2.32.11-1'):
        with pytest.raises(ValueError, match='Invalid or duplicate'):
            candidate.package_inventory(data + '\nmingw-w64-ucrt-x86_64-SDL2 2.32.10-1'
                                        + '\nmingw-w64-ucrt-x86_64-SDL2 ' + version)


def test_pacman_inventory_retains_name_length_and_entry_count_bounds():
    data = '\n'.join(f'{name} {version}' for name, version in candidate.PACKAGES.items())
    maximum_name = 'A' * 160
    data += '\n' + maximum_name + ' 1.0-1'
    data += ''.join(f'\nDependency{i} 1.0-1' for i in range(4093))
    record = candidate.package_inventory(data)
    assert len(record) == 4096 and record[maximum_name] == '1.0-1'
    with pytest.raises(ValueError, match='Invalid or duplicate'):
        candidate.package_inventory(data + '\nOneMore 1.0-1')


@pytest.mark.parametrize('repo_policy,global_policy,repo_exit,global_exit,allowed,inherit', [
    ('', 'PackageRequired PackageTrustedOnly', 0, 0, True, True),
    (' \t\r\n', 'PackageRequired\nPackageTrustedOnly\nDatabaseRequired\nDatabaseTrustedOnly', 0, 0, True, True),
    ('PackageRequired PackageTrustedOnly', '', 0, 0, True, False),
    ('PackageOptional PackageTrustedOnly', 'PackageRequired PackageTrustedOnly', 0, 0, False, False),
    ('PackageRequired PackageTrustAll', 'PackageRequired PackageTrustedOnly', 0, 0, False, False),
    ('PackageNever', 'PackageRequired PackageTrustedOnly', 0, 0, False, False),
    ('PackageRequired', 'PackageRequired PackageTrustedOnly', 0, 0, False, False),
    ('PackageRequired PackageTrustedOnly PackageOptional', '', 0, 0, False, False),
    ('', 'PackageRequired PackageTrustedOnly', 1, 0, False, False),
    ('PackageRequired PackageTrustedOnly', '', 1, 0, False, False),
    ('', 'PackageRequired PackageTrustedOnly', 0, 1, False, True),
    ('', '', 0, 0, False, True),
    ('', 'PackageOptional PackageTrustedOnly', 0, 0, False, True),
    ('', 'PackageRequired PackageTrustAll', 0, 0, False, True),
    ('', 'PackageNever', 0, 0, False, True),
    ('', 'PackageRequired', 0, 0, False, True),
])
def test_workflow_signature_preflight_enforces_effective_policy(
        tmp_path, repo_policy, global_policy, repo_exit, global_exit, allowed, inherit):
    """Run the exact acquisition shell block; package commands are synthetic stubs."""
    bash = shutil.which('bash')
    if bash is None:
        pytest.skip('Bash required for workflow shell regression; no native qualification implied')
    workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/windows-runtime-candidate.yml').read_text()
    step = workflow.split('      - name: Acquire one fully upgraded signed vendor package set\n', 1)[1]
    script = textwrap.dedent(step.split('        run: |\n', 1)[1].split('\n      - ', 1)[0])
    archive = tmp_path / 'candidate root' / 'acquisition'
    archive.mkdir(parents=True)
    stubs = '''
pacman-conf() {
  if [[ "$*" == '--repo ucrt64 SigLevel' ]]; then
    printf '%s' "$TEST_REPO_POLICY"
    return "$TEST_REPO_EXIT"
  elif [[ "$*" == 'SigLevel' ]]; then
    printf 'queried\n' >> global-query.txt
    printf '%s' "$TEST_GLOBAL_POLICY"
    return "$TEST_GLOBAL_EXIT"
  fi
  return 99
}
cygpath() { printf '%s\n' "$2"; }
pacman() { printf '%s\n' "$*" >> pacman-calls.txt; }
'''
    result = subprocess.run([bash, '--noprofile', '--norc', '-c', stubs + script],
        cwd=tmp_path, env={**os.environ, 'FIRMAVEX_CANDIDATE_ROOT': 'candidate root',
            'TEST_REPO_POLICY': repo_policy, 'TEST_GLOBAL_POLICY': global_policy,
            'TEST_REPO_EXIT': str(repo_exit), 'TEST_GLOBAL_EXIT': str(global_exit)},
        capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is allowed, result.stderr
    assert (tmp_path / 'global-query.txt').exists() is inherit
    calls = tmp_path / 'pacman-calls.txt'
    if allowed:
        assert calls.read_text().splitlines() == [
            '-Syu --needed --noconfirm mingw-w64-ucrt-x86_64-qemu mingw-w64-ucrt-x86_64-gdb-multiarch mingw-w64-ucrt-x86_64-arm-none-eabi-gcc', '-Q', '-Qi']
        assert (archive / 'package-info.txt').is_file()
        candidate.signature_policy((archive / 'signature-policy.txt').read_text())
        assert (archive / 'repository-signature-policy.txt').read_text().split() == repo_policy.split()
    else:
        assert not calls.exists(), 'Rejected policy must never install packages'


def test_vendor_inventory_includes_dependencies_not_only_executables(vendor):
    root, _ = vendor
    (root / 'bin/dependency.dll').write_bytes(b'dependency')
    rows = candidate.inventory(root)
    assert 'bin/dependency.dll' in rows and 'share/licenses/fixture/COPYING' in rows
    assert all(set(value) == {'sha256', 'size_bytes'} for value in rows.values())


@pytest.mark.parametrize('boundary', ['MAX_FILES', 'MAX_BYTES'])
def test_administrative_inventory_has_hard_bounds(vendor, monkeypatch, boundary):
    root, _ = vendor
    monkeypatch.setattr(candidate, boundary, 1)
    with pytest.raises(ValueError): candidate.inventory(root)


def test_inventory_rejects_links_before_reading_target(vendor, tmp_path):
    root, _ = vendor
    outside = tmp_path / 'outside'; outside.write_text('do not capture')
    try: (root / 'alias').symlink_to(outside)
    except OSError: pytest.skip('Host cannot create symlinks')
    with pytest.raises(ValueError): candidate.inventory(root)


def test_inventory_records_complete_vendor_hardlink_groups(vendor):
    from firmavex.backends.security import checked_path
    root, _ = vendor
    original = root / 'bin/gcc.exe'; original.write_bytes(b'trusted compiler fixture')
    aliases = [original, root / 'bin/cc.exe', root / 'bin/target-gcc.exe']
    for path in aliases[1:]: os.link(original, path)
    with pytest.raises(ValueError, match='Expected a regular file'):
        checked_path(original)  # Shared product validation remains unchanged.
    rows = candidate.inventory(root)
    for path in aliases:
        assert rows[path.relative_to(root).as_posix()] == {
            'sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
            'size_bytes': original.stat().st_size, 'link_count': 3,
            'hardlink_group': 'bin/cc.exe'}
    assert rows == candidate.inventory(root)


def test_inventory_rejects_hardlink_with_alias_outside_vendor_prefix(vendor, tmp_path, monkeypatch):
    root, _ = vendor
    source = root / 'bin/compiler.exe'; source.write_bytes(b'fixture')
    os.link(source, tmp_path / 'outside.exe')
    def forbidden(*args): pytest.fail('Incomplete hardlink group must not be read')
    monkeypatch.setattr(candidate, '_hardlink_identity', forbidden)
    with pytest.raises(candidate.VendorInventoryError) as raised:
        candidate.inventory(root)
    assert raised.value.details == {'reason': 'incomplete_or_changed_hardlink_group',
        'relative_path': 'bin/compiler.exe', 'file_type': stat.S_IFREG,
        'link_count': 2, 'reparse_point': False}


def test_inventory_rejects_file_growth_between_budget_check_and_hash(vendor, monkeypatch):
    root, _ = vendor
    source = root / 'bin/growing.dll'; source.write_bytes(b'fixture')
    original = candidate.file_identity
    def changed(path):
        if path == source: path.write_bytes(b'larger fixture')
        return original(path)
    monkeypatch.setattr(candidate, 'file_identity', changed)
    with pytest.raises(candidate.VendorInventoryError) as raised:
        candidate.inventory(root)
    assert raised.value.details['reason'] == 'file_size_changed'


@pytest.mark.parametrize('hardlink', [False, True])
def test_inventory_rejects_windows_reparse_metadata_before_read(vendor, monkeypatch, hardlink):
    root, _ = vendor
    source = root / 'bin/unsafe.exe'; source.write_bytes(b'must not read')
    if hardlink: os.link(source, root / 'bin/alias.exe')
    original = Path.lstat
    def metadata(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path == source:
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith('st_')}
            fields['st_file_attributes'] = 0x400
            return SimpleNamespace(**fields)
        return value
    monkeypatch.setattr(Path, 'lstat', metadata)
    with pytest.raises(candidate.VendorInventoryError) as raised:
        candidate.inventory(root)
    assert raised.value.details['relative_path'] == 'bin/unsafe.exe'
    assert raised.value.details['reparse_point'] is True


@pytest.mark.parametrize('directory', [False, True])
def test_inventory_rejects_vendor_symlinks_including_directory_links(vendor, tmp_path, directory):
    root, _ = vendor
    outside = tmp_path / 'outside'
    if directory: outside.mkdir()
    else: outside.write_bytes(b'outside fixture')
    path = root / 'bin/unsafe-link'
    try: path.symlink_to(outside, target_is_directory=directory)
    except OSError: pytest.skip('Host cannot create symlinks')
    with pytest.raises(candidate.VendorInventoryError) as raised:
        candidate.inventory(root)
    assert raised.value.details['relative_path'] == 'bin/unsafe-link'
    assert raised.value.details['file_type'] == stat.S_IFLNK


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='POSIX special-file regression')
def test_inventory_rejects_special_files_without_opening(vendor):
    root, _ = vendor
    os.mkfifo(root / 'bin/pipe')
    with pytest.raises(candidate.VendorInventoryError) as raised:
        candidate.inventory(root)
    assert raised.value.details['file_type'] == stat.S_IFIFO


@pytest.mark.parametrize('change', ['outside-alias', 'content', 'replacement'])
def test_inventory_rejects_hardlink_changes_before_hash(vendor, tmp_path, monkeypatch, change):
    root, _ = vendor
    source = root / 'bin/compiler.exe'; source.write_bytes(b'fixture')
    os.link(source, root / 'bin/alias.exe')
    original = candidate._hardlink_identity
    def changed(path, expected, links):
        if change == 'outside-alias': os.link(path, tmp_path / 'unexpected.exe')
        elif change == 'content': path.write_bytes(b'changed')
        else:
            path.unlink()
            path.write_bytes(b'fixture')
        return original(path, expected, links)
    monkeypatch.setattr(candidate, '_hardlink_identity', changed)
    with pytest.raises(candidate.VendorInventoryError) as raised:
        candidate.inventory(root)
    assert raised.value.details['reason'] == 'hardlink_changed'


def test_hardlink_hash_rejects_wrong_opened_object_before_reading(vendor, tmp_path, monkeypatch):
    root, _ = vendor
    source = root / 'bin/compiler.exe'; source.write_bytes(b'fixture')
    os.link(source, root / 'bin/alias.exe')
    outside = tmp_path / 'outside.exe'; outside.write_bytes(b'do not read')
    expected = candidate.path_state(source)
    original = os.open
    def substituted(path, *args, **kwargs):
        return original(outside if Path(path) == source else path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', substituted)
    def unexpected_read(*args): pytest.fail('Wrong opened object must not be hashed')
    monkeypatch.setattr(candidate.hashlib, 'sha256', lambda: SimpleNamespace(update=unexpected_read))
    with pytest.raises(ValueError, match='Opened hardlink identity changed'):
        candidate._hardlink_identity(source, expected, 2)


@pytest.mark.parametrize('change', ['content', 'outside-alias'])
def test_hardlink_hash_rejects_changes_during_read(vendor, tmp_path, monkeypatch, change):
    root, _ = vendor
    source = root / 'bin/compiler.exe'; source.write_bytes(b'fixture')
    os.link(source, root / 'bin/alias.exe')
    original = candidate.handle_state
    calls = 0
    def changed(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change == 'content': source.write_bytes(b'changed')
            else: os.link(source, tmp_path / 'unexpected.exe')
        return original(fd)
    monkeypatch.setattr(candidate, 'handle_state', changed)
    with pytest.raises(candidate.VendorInventoryError): candidate.inventory(root)


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_hardlink_hash_preserves_control_flow(vendor, monkeypatch, control):
    root, _ = vendor
    source = root / 'bin/compiler.exe'; source.write_bytes(b'fixture')
    os.link(source, root / 'bin/alias.exe')
    def interrupted(*args): raise control('original cancellation')
    monkeypatch.setattr(candidate, 'handle_state', interrupted)
    with pytest.raises(control, match='original cancellation'): candidate.inventory(root)


@pytest.mark.parametrize('phase', ['preflight', 'source'])
def test_inventory_failure_diagnostics_are_retained(vendor, tmp_path, monkeypatch, phase):
    root, tools = vendor
    output = tmp_path / 'failed-inventory'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n, v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123'}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    monkeypatch.setattr(candidate, 'production_rejection', lambda *a: {'synthetic_test': True})
    if phase == 'source': candidate.preflight(root, packages, policy, output)
    source = root / 'bin/alias.exe'; source.write_bytes(b'fixture')
    os.link(source, tmp_path / 'private-outside-name.exe')
    with pytest.raises(candidate.VendorInventoryError):
        if phase == 'preflight': candidate.preflight(root, packages, policy, output)
        else: candidate.source_probe(root, output)
    report = json.loads((output / 'candidate-report.json').read_text())
    assert report['status'] == ('candidate_preflight_failed' if phase == 'preflight' else 'candidate_source_probe_failed')
    assert report['production_qualified'] is False
    details = report['inventory_failure']
    assert details['relative_path'] == 'bin/alias.exe' and details['link_count'] == 2
    assert str(tmp_path) not in json.dumps(details) and 'private-outside-name' not in json.dumps(details)
    assert report['cases'] == []


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_record_write_failure_cannot_replace_control_flow(tmp_path, monkeypatch, control):
    primary = control('original')
    def denied(*args): raise OSError('write failed')
    monkeypatch.setattr(candidate, '_atomic_json', denied)
    candidate._save(tmp_path / 'unused', {}, primary)
    assert primary.__notes__ == ['Candidate evidence persistence failed']
    with pytest.raises(OSError): candidate._save(tmp_path / 'unused', {})


@pytest.mark.parametrize('bound', ['MAX_RECORD', 'MAX_OUTPUT_BYTES'])
def test_record_byte_bounds_include_writer_newline(tmp_path, monkeypatch, bound):
    path = tmp_path / 'record.json'
    record = {'value': 'bounded'}
    size = len(json.dumps(record, sort_keys=True).encode('utf-8')) + len(os.linesep)
    monkeypatch.setattr(candidate, bound, size)
    assert candidate._save(path, record)
    assert path.stat().st_size == size
    original = path.read_bytes()
    monkeypatch.setattr(candidate, bound, size - 1)
    with pytest.raises(ValueError): candidate._save(path, record)
    assert path.read_bytes() == original


def test_production_gate_still_rejects_candidate_and_is_not_patched(monkeypatch):
    from firmavex.product import platform_support as support
    monkeypatch.setattr(support, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(support, 'platform', SimpleNamespace(machine=lambda: 'AMD64'))
    tools = SimpleNamespace(identities={name: {'version': v, 'sha256': h} for name, (v,h) in candidate.CANDIDATE.items()})
    assert support.windows_profile(tools, machine='AMD64') is None
    assert candidate.production_rejection(tools)['required_profile'] == 'msys2-ucrt64-qemu11.1.2-gdb18.1-v1'
    assert support.windows_profile(tools, machine='AMD64') is None


def test_candidate_preflight_is_not_a_qualification_and_never_overwrites(vendor, tmp_path, monkeypatch):
    root, tools = vendor
    output = tmp_path / 'probe'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n,v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly DatabaseOptional DatabaseTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123', 'host': {'os':'synthetic_test'}}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    monkeypatch.setattr(candidate, 'production_rejection', lambda *a: {'synthetic_test': True})
    record = candidate.preflight(root, packages, policy, output)
    assert record['candidate_only'] and record['production_qualified'] is False
    assert record['status'] == 'candidate_preflight_only' and record['pending']
    before = {p.name:p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError): candidate.preflight(root, packages, policy, output)
    assert {p.name:p.read_bytes() for p in output.iterdir()} == before


def test_failed_preflight_retains_observed_identities_without_running_firmware(vendor, tmp_path, monkeypatch):
    root, tools = vendor
    output = tmp_path / 'failed-probe'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n,v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123'}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    tools.identities['qemu']['version'] = 'QEMU emulator version 11.1.4'
    with pytest.raises(ValueError): candidate.preflight(root, packages, policy, output)
    record = json.loads((output / 'candidate-report.json').read_text())
    assert record['status'] == 'candidate_preflight_failed' and record['production_qualified'] is False
    assert record['tools']['qemu']['version'] == 'QEMU emulator version 11.1.4'
    assert record['cases'] == [] and not list(output.glob('candidate-receipt-*'))


@pytest.mark.parametrize('fault', [None, 'cancel-receipt', 'cleanup'], ids=['normal', 'persistence-failure', 'cleanup-failure'])
def test_synthetic_executor_orchestration_accounts_for_every_attempt(vendor, tmp_path, monkeypatch, fault):
    """Mock runtime contract only; these fixtures never qualify Windows."""
    from firmavex.product import runtime
    from src.firmavex.evaluation.evaluator import Observation
    from src.firmavex.evaluation.api import ExecutionSignature
    root, tools = vendor
    output = tmp_path / 'source-probe'
    packages = tmp_path / 'packages.txt'
    packages.write_text('\n'.join(f'{n} {v}' for n,v in candidate.PACKAGES.items()))
    policy = tmp_path / 'policy.txt'; policy.write_text('PackageRequired PackageTrustedOnly')
    monkeypatch.setattr(candidate, '_environment', lambda *a: ({'source_revision': HEAD, 'run_id': '123', 'host': {'os':'synthetic_test'}}, root, output))
    monkeypatch.setattr(candidate, 'candidate_tools', lambda *a: tools)
    monkeypatch.setattr(candidate, 'production_rejection', lambda *a: {'synthetic_test': True})
    candidate.preflight(root, packages, policy, output)
    original_save = candidate._atomic_json
    def write(path, record):
        if fault == 'cancel-receipt' and path.name == 'candidate-receipt-19.json':
            raise OSError('synthetic retention failure')
        original_save(path, record)
    monkeypatch.setattr(candidate, '_atomic_json', write)
    class FakeExecutor:
        sequence = 0
        def __init__(self, config, tools, cancel, callback):
            self.config, self.cancel, self.callback = config, cancel, callback
            self.last_evidence = None
        def execute(self, values):
            FakeExecutor.sequence += 1
            if self.callback: self.callback({'stage':'injected'})
            incomplete = self.config.completion_breakpoint == 'Default_Handler'
            value = 0x13579bdf if self.config.failure_symbol == 'initialized_data' else int(values == (2,1))
            self.last_evidence = {
                'synthetic_fixture': True, 'attempt_id': str(FakeExecutor.sequence), 'inputs': list(values),
                'observed_value': value, 'cleanup_verified': True,
                'cleanup': {'processes':[{'reaped': True}]},
                # Deliberately simulated dependency contract, not measured evidence.
                'measurement_mode':'real_firmware', 'guest_dispatched':True,
                'input_injected':True, 'completion_reached':not incomplete,
            }
            if incomplete:
                self.last_evidence['error_category'] = 'cancelled' if self.cancel.is_set() else 'timeout'
                if fault == 'cleanup' and self.cancel.is_set(): self.last_evidence['cleanup_verified'] = False
                if self.cancel.is_set(): raise KeyboardInterrupt('synthetic expected cancellation')
                return SimpleNamespace(observation=Observation(False))
            return SimpleNamespace(observation=Observation(True, value == self.config.failure_value,
                                       execution_signature=ExecutionSignature('a'*64, False)))
    monkeypatch.setattr(runtime, 'FirmwareExecutor', FakeExecutor)
    if fault is not None:
        with pytest.raises(RuntimeError): candidate.source_probe(root, output)
        report = json.loads((output / 'candidate-report.json').read_text())
        assert report['status'] == 'candidate_source_probe_failed' and report['production_qualified'] is False
        return
    report = candidate.source_probe(root, output)
    assert report['production_qualified'] is False and len(report['cases']) == 8
    assert sum(case['accounting']['attempted_executions'] for case in report['cases']) == 19
    assert sum(case['accounting']['infrastructure_failures'] for case in report['cases']) == 2
    assert len(list(output.glob('candidate-receipt-*.json'))) == 19
    for path in output.glob('candidate-receipt-*.json'):
        record = json.loads(path.read_text())
        assert record['candidate_only'] and record['production_qualified'] is False
        assert record['runtime']['synthetic_fixture']
    with pytest.raises(ValueError): candidate.source_probe(root, output)  # Never silently rerun a consumed probe.


def test_candidate_workflow_is_manual_pinned_separate_and_never_approves():
    repo = Path(__file__).resolve().parents[2]
    workflow = (repo / '.github/workflows/windows-runtime-candidate.yml').read_text()
    assert 'workflow_dispatch:' in workflow and '\n  push:' not in workflow and '\n  pull_request:' not in workflow
    assert 'expected_revision' in workflow and 'contents: read' in workflow
    assert 'PackageRequired' in workflow and 'PackageTrustedOnly' in workflow and 'pacman -Syu' in workflow
    assert 'pacman-conf --repo ucrt64 SigLevel' in workflow
    assert 'Windows-UNQUALIFIED-runtime-candidate-' in workflow and '!/evidence/' in workflow
    assert 'FIRMAVEX_QUALIFY_BACKENDS' not in workflow
    assert 'tools.windows_runtime_candidate' not in (repo / 'packaging/desktop.spec').read_text()
    assert 'tools/windows_runtime_candidate.py' not in (repo / 'MANIFEST.in').read_text()
    for name in ('windows_candidate_evidence', 'windows_candidate_packages', 'windows_candidate_product',
                 'windows_candidate_installed', 'windows_candidate_artifact', 'windows_candidate_closure'):
        assert 'tools.' + name not in (repo / 'packaging/desktop.spec').read_text()
        assert 'tools/' + name + '.py' not in (repo / 'MANIFEST.in').read_text()


def test_candidate_python_commands_use_setup_interpreter_and_module_launcher():
    repo = Path(__file__).resolve().parents[2]
    workflow = (repo / '.github/workflows/windows-runtime-candidate.yml').read_text()
    assert not re.search(r'\bpython(?:\.exe)?\s+(?:-m|tools/)', workflow)
    prefix = '& "${{ steps.python.outputs.python-path }}" -m '
    commands = [line.strip()[len(prefix):] for line in workflow.splitlines()
                if line.strip().startswith(prefix)]
    assert [command.split()[0] for command in commands] == [
        'pip', 'pip', 'tools.check_build_inputs', 'tools.windows_runtime_candidate',
        'tools.product_ci_tests', 'tools.product_ci_tests', 'tools.product_ci_tests',
        'tools.product_ci_tests', 'tools.product_ci_tests', 'PyInstaller', 'tools.product_ci_tests',
        'tools.product_ci_tests']
    assert 'tools/product_ci_tests.py' not in workflow
    assert "(Join-Path $prefix 'bin') >> $env:GITHUB_PATH" in workflow


def test_candidate_installer_checks_keep_existing_setup_and_explicit_scope():
    repo = Path(__file__).resolve().parents[2]
    workflow = (repo / '.github/workflows/windows-runtime-candidate.yml').read_text()
    assert 'ISCC.exe" packaging/windows.iss' in workflow
    assert 'FIRMAVEX_REQUIRE_CANDIDATE_INSTALLED: "1"' in workflow
    assert 'tests/product/test_windows_candidate_installed.py -k native_windows_candidate_installed' in workflow
    assert 'FIRMAVEX_CANDIDATE_FROZEN_DIR: ${{ github.workspace }}/dist/FIRMAVEX' in workflow
    assert 'timeout-minutes: 35' in workflow  # No unmeasured timeout increase.
    assert 'pacman -Qi > "$output/package-info.txt"' in workflow
    upload = workflow.split('Retain candidate evidence only', 1)[1]
    assert '/dist/' not in upload and 'installer' not in upload.lower()


@pytest.mark.parametrize('failure', [False, True], ids=['pass', 'preserve-failure'])
def test_candidate_module_launcher_without_site_imports_keeps_interpreter_and_status(tmp_path, failure):
    """Real host launcher/pytest; no guest execution or native Windows claim."""
    repo = Path(__file__).resolve().parents[2]
    archive = tmp_path / 'diagnostics'
    probe = tmp_path / 'test_candidate_import_probe.py'
    probe.write_text('import sys\nfrom firmavex.product.windows_job import WindowsJob\n'
                     'def test_interpreter_and_import():\n'
                     f' assert sys.executable == {sys.executable!r}\n'
                     f' assert {not failure!r}, "expected probe failure"\n', encoding='utf-8')
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', FIRMAVEX_CI_DIAGNOSTICS=str(archive))
    for key in ('PYTHONPATH', 'PYTHONSAFEPATH', 'GITHUB_STEP_SUMMARY'):
        env.pop(key, None)
    # An unrelated Python earlier on PATH must not affect this launcher or child.
    vendor = tmp_path / 'vendor-bin'; vendor.mkdir()
    for name in ('python', 'python.exe'):
        path = vendor / name
        path.write_text('#!/bin/sh\nexit 99\n', encoding='utf-8'); path.chmod(0o700)
    env['PATH'] = str(vendor) + os.pathsep + env.get('PATH', '')
    direct = subprocess.run([sys.executable, '-S', 'tools/product_ci_tests.py', '-q', str(probe)],
                            cwd=repo, env=env, capture_output=True, text=True, timeout=30)
    assert direct.returncode != 0 and "No module named 'firmavex'" in direct.stderr
    assert not list(archive.glob('firmavex-ci-*/pytest.xml'))
    module = subprocess.run([sys.executable, '-S', '-m', 'tools.product_ci_tests',
                             '--ci-watchdog', '-q', str(probe), '--firmavex-test-timeout=10'],
                            cwd=repo, env=env, capture_output=True, text=True, timeout=30)
    assert module.returncode == int(failure), module.stdout + module.stderr
    assert ('1 failed' if failure else '1 passed') in module.stdout
    assert 'FIRMAVEX TEST START' in module.stdout
    reports = list(archive.glob('firmavex-ci-*/pytest.xml'))
    assert len(reports) == 1
    assert reports[0].with_name('launcher-state.log').read_text().strip() == f'completed: pytest status={int(failure)}'


def _native_required():
    if os.environ.get('FIRMAVEX_RUN_WINDOWS_CANDIDATE') != '1':
        pytest.skip('Explicit dispatch-only native Windows candidate workflow required')
    if sys.platform != 'win32': pytest.fail('Candidate mode cannot qualify Windows on another OS')


def test_native_windows_candidate_source_probe():
    _native_required()
    root = Path(os.environ['FIRMAVEX_CANDIDATE_ROOT'])
    result = candidate.source_probe(Path(os.environ['FIRMAVEX_CANDIDATE_VENDOR']), root / 'source-probe')
    assert result['status'] == 'candidate_source_probe_passed'
    assert result['production_qualified'] is False and len(result['cases']) == 8


def test_native_windows_candidate_memory_resource_bound(tmp_path):
    _native_required()
    import threading
    from firmavex.backends.api import Limits
    from firmavex.backends.process import Processes
    owner = Processes(threading.Event(), Limits(memory_bytes=128 * 1024**2, timeout_seconds=10))
    try:
        code, out, err = owner.run([sys.executable, '-c',
            "data=bytearray(256*1024*1024);print('UNEXPECTED_ALLOCATION_SUCCESS')"], tmp_path)
    finally:
        owner.close()
    assert code != 0 and 'MemoryError' in err and 'UNEXPECTED_ALLOCATION_SUCCESS' not in out
    assert all(row['reaped'] for row in owner.cleanup)
    candidate._save(Path(os.environ['FIRMAVEX_CANDIDATE_ROOT']) / 'source-probe/candidate-resource.json', {
        'candidate_only': True, 'production_qualified': False, 'firmware_executed': False,
        'scope': 'native host allocation denial, not aggregate QEMU memory qualification',
        'requested_limit_bytes': 128*1024**2, 'allocation_bytes': 256*1024**2,
        'exit_code': code, 'cleanup': owner.cleanup})
