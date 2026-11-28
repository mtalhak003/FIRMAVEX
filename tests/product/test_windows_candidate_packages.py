"""Synthetic package fixtures, not MSYS2 publisher or Windows qualification."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest

from tools import windows_candidate_packages as packages

SIGNER = 'A' * 40


def pkg(name, version='1.0-1', **extra):
    return {'name': name, 'version': version, 'architecture': 'any', 'licenses': ['MIT'],
            'depends': [], 'provides': [], 'conflicts': [], **extra}


def roots(*extra):
    return [pkg(n, v) for n, v in packages.PACKAGES.items()] + list(extra)


def valid_status(signer=SIGNER, trust='TRUST_FULLY', algorithm='8'):
    return f'[GNUPG:] VALIDSIG {signer} 2026-01-01 1767225600 0 4 0 1 {algorithm} 00 {signer}\n[GNUPG:] {trust} 0 pgp\n'


def test_metadata_uses_actual_fields_and_retains_license_declarations():
    record = packages.metadata('pkgname = SDL2\npkgver = 1:2.32.10-1\narch = x86_64\n'
                               'license = Zlib\ndepend = libc>=2.0\nprovides = sdl=2.0\n')
    assert record['name'] == 'SDL2' and record['version'] == '1:2.32.10-1'
    assert record['depends'] == ['libc>=2.0'] and record['licenses'] == ['Zlib']
    assert len(record['metadata_sha256']) == 64


@pytest.mark.parametrize('text', [
    '', 'pkgname = x\npkgname = x\npkgver = 1\narch = any\nlicense = MIT',
    'pkgname = x\npkgver = 1\narch = aarch64\nlicense = MIT',
    'pkgname = x\npkgver = 1\narch = any',
    'pkgname = ../x\npkgver = 1\narch = any\nlicense = MIT',
    'pkgname = x\npkgver = 1\narch = any\nlicense = MIT\nprovides = x>=1',
    'x' * 65537,
])
def test_metadata_rejects_malformed_or_unavailable_identity(text):
    with pytest.raises(ValueError): packages.metadata(text)


@pytest.mark.parametrize('status', [
    '', valid_status('B' * 40), valid_status(trust='TRUST_UNDEFINED'),
    valid_status(algorithm='2'), valid_status() + '[GNUPG:] BADSIG bad\n',
    valid_status() + '[GNUPG:] REVKEYSIG bad\n',
    valid_status() + '[GNUPG:] EXPKEYSIG bad\n', valid_status() * 2,
])
def test_cryptographic_status_requires_allowlist_trust_strong_hash_and_no_errors(status):
    with pytest.raises(ValueError): packages.signature_status(status, [SIGNER])


def test_valid_status_retains_fingerprint_without_arbitrary_output():
    assert packages.signature_status('arbitrary diagnostic\n' + valid_status(), [SIGNER]) == {
        'signing_fingerprint': SIGNER, 'primary_fingerprint': SIGNER,
        'hash_algorithm': '8', 'trust': 'full_or_ultimate'}


def test_dependency_closure_resolves_versions_and_versioned_virtual_provides():
    qemu, gdb = roots()
    qemu['depends'] = ['SDL2>=2', 'virtual=3']
    result = packages.closure([qemu, gdb, pkg('SDL2', '2'), pkg('provider', provides=['virtual=3'])],
                              lambda a, b: (int(a) > int(b)) - (int(a) < int(b)))
    assert result[qemu['name']] == {'SDL2>=2': ['SDL2'], 'virtual=3': ['provider']}


@pytest.mark.parametrize('case', ['missing', 'old', 'unversioned-provide', 'conflict', 'duplicate', 'wrong-root'])
def test_dependency_closure_rejects_incomplete_or_incompatible_set(case):
    qemu, gdb = roots()
    qemu['depends'] = ['needed>=2']
    extra = []
    if case == 'old': extra = [pkg('needed', '1')]
    if case == 'unversioned-provide': extra = [pkg('provider', provides=['needed'])]
    if case == 'conflict':
        qemu['depends'] = []; qemu['conflicts'] = ['other']; extra = [pkg('other')]
    if case == 'duplicate': qemu['depends'] = []; extra = [qemu.copy()]
    if case == 'wrong-root': qemu['depends'] = []; qemu['version'] = '11.1.4-1'
    with pytest.raises(ValueError): packages.closure([qemu, gdb] + extra, lambda a, b: int(a) - int(b))


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    directory = tmp_path / 'packages'; directory.mkdir()
    keyring = tmp_path / 'trusted-keyring'; keyring.mkdir()
    (keyring / 'pubring.gpg').write_bytes(b'synthetic public keyring')
    (keyring / 'trustdb.gpg').write_bytes(b'synthetic trust database')
    tools, hashes = {}, {}
    for name in ('gpg', 'bsdtar', 'vercmp'):
        tools[name] = tmp_path / (name + '.exe')
        tools[name].write_bytes(('synthetic verifier: ' + name).encode())
        hashes[name] = hashlib.sha256(tools[name].read_bytes()).hexdigest()
    rows, metadata = [], {}
    for name, version in packages.PACKAGES.items():
        filename = name + '-' + version + '-any.pkg.tar.zst'
        path = directory / filename; path.write_bytes(('synthetic archive ' + name).encode())
        signature = directory / (filename + '.sig'); signature.write_bytes(b'synthetic detached signature')
        rows.append({'archive': filename, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'signature_sha256': hashlib.sha256(signature.read_bytes()).hexdigest()})
        metadata[str(path)] = f'pkgname = {name}\npkgver = {version}\narch = any\nlicense = MIT\n'
    manifest = tmp_path / 'manifest.json'; manifest.write_text(json.dumps({'schema_version': 1, 'packages': rows}))
    calls = []
    def run(argv, cwd, deadline, **kwargs):
        calls.append(argv)
        if argv[0] == str(tools['gpg']): return valid_status()
        if argv[0] == str(tools['bsdtar']): return metadata[argv[2]]
        if argv[0] == str(tools['vercmp']): return '0\n'
        pytest.fail('Unexpected verifier command')
    monkeypatch.setattr(packages, '_run', run)
    def verify(**kwargs):
        return packages.verify(directory, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(),
                               keyring, [SIGNER], trusted_tool_sha256=hashes, **tools, **kwargs)
    return directory, manifest, keyring, tools, hashes, calls, metadata, verify


def test_complete_synthetic_bundle_is_candidate_only_and_does_not_change_inputs(bundle):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    before = {p: p.read_bytes() for p in directory.iterdir()}
    record = verify()
    assert record['candidate_only'] is True and record['production_qualified'] is False
    assert record['status'] == 'verified_listed_package_closure'
    assert record['installed_or_executed_firmware'] is False
    assert {p: p.read_bytes() for p in directory.iterdir()} == before
    assert len(record['packages']) == 2 and record['verification_tool_sha256'] == hashes
    for command in calls:
        if command[0] == str(tools['gpg']):
            assert '--no-auto-key-retrieve' in command and '--no-auto-key-import' in command
            assert '--no-options' in command and '--no-autostart' in command
            assert str(keyring) not in command  # Uses a bounded public-only copy.
        else: assert command[1] == '-xOf'


@pytest.mark.parametrize('fault', ['archive', 'signature', 'missing-signature', 'keyring', 'tool', 'duplicate', 'traversal', 'json-duplicate'])
def test_bundle_rejects_missing_tampered_or_unsafe_inputs_before_approval(bundle, fault):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    spec = json.loads(manifest.read_text())
    first = spec['packages'][0]
    if fault == 'archive': (directory / first['archive']).write_bytes(b'changed')
    elif fault == 'signature': (directory / (first['archive'] + '.sig')).write_bytes(b'changed')
    elif fault == 'missing-signature': (directory / (first['archive'] + '.sig')).unlink()
    elif fault == 'keyring': (keyring / 'trustdb.gpg').unlink()
    elif fault == 'tool': tools['gpg'].write_bytes(b'changed')
    elif fault == 'duplicate': spec['packages'].append(first.copy())
    elif fault == 'traversal': first['archive'] = '../outside.pkg.tar.zst'
    else:
        manifest.write_text('{"schema_version":1,"schema_version":1,"packages":[]}')
    if fault not in {'json-duplicate'}: manifest.write_text(json.dumps(spec))
    with pytest.raises((ValueError, FileNotFoundError)): verify()


def test_signature_failure_prevents_metadata_parser_execution(bundle, monkeypatch):
    *_, verify = bundle
    def rejected(argv, cwd, deadline, **kwargs):
        assert '--verify' in argv
        return '[GNUPG:] BADSIG bad\n'
    monkeypatch.setattr(packages, '_run', rejected)
    with pytest.raises(ValueError, match='signature'): verify()


def test_changed_archive_during_read_is_rejected(bundle, monkeypatch):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    def changing(argv, cwd, deadline, **kwargs):
        if argv[0] == str(tools['gpg']): return valid_status()
        path = Path(argv[2]); text = metadata[str(path)]; path.write_bytes(b'changed during verification')
        return text
    monkeypatch.setattr(packages, '_run', changing)
    with pytest.raises(ValueError, match='changed'): verify()


@pytest.mark.parametrize('boundary', ['archive', 'signature', 'aggregate'])
def test_input_byte_bounds_are_enforced_before_archive_hashing(bundle, monkeypatch, boundary):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    row = json.loads(manifest.read_text())['packages'][0]
    if boundary == 'aggregate': monkeypatch.setattr(packages, 'MAX_BYTES', 1)
    else:
        path = directory / (row['archive'] + ('.sig' if boundary == 'signature' else ''))
        # Sparse temporary fixture: no large payload is read or allocated.
        with path.open('wb') as stream:
            stream.truncate(65537 if boundary == 'signature' else 512 * 1024**2 + 1)
    original = packages._identity
    def guarded(path, *args, **kwargs):
        if path.parent == directory: pytest.fail('Oversized package input must not be hashed')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(packages, '_identity', guarded)
    with pytest.raises(ValueError, match='byte bound'): verify()
    assert calls == []


def test_identity_hash_checks_size_before_reading_and_detects_growth(tmp_path):
    path = tmp_path / 'fixture'; path.write_bytes(b'small fixture')
    with pytest.raises(ValueError, match='size bound'): packages._identity(path, 1)
    with pytest.raises(ValueError, match='size bound'): packages._identity(path, 1024, 1)
    assert packages._identity(path, 1024)['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('fault', ['manifest', 'earlier-archive', 'earlier-signature',
                                 'source-keyring', 'new-keyring-file'])
def test_later_package_cannot_mask_changed_earlier_input(bundle, monkeypatch, fault):
    # All package bytes, signatures and verifier output here are invented.
    # This tests capture integrity, not real publisher authentication.
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    rows = json.loads(manifest.read_text())['packages']
    first = directory / rows[0]['archive']
    second = directory / rows[1]['archive']
    original = packages._run
    changed = []
    def changing(argv, cwd, deadline, **kwargs):
        result = original(argv, cwd, deadline, **kwargs)
        if argv[0] == str(tools['bsdtar']) and argv[2] == str(second) and not changed:
            changed.append(True)
            if fault == 'manifest': manifest.write_bytes(b'{"unrelated":"changed"}')
            elif fault == 'earlier-archive': first.write_bytes(b'changed after package verification')
            elif fault == 'earlier-signature': Path(str(first) + '.sig').write_bytes(b'changed signature')
            elif fault == 'source-keyring': (keyring / 'trustdb.gpg').write_bytes(b'changed trust input')
            else: (keyring / 'pubring.kbx').write_bytes(b'appeared after initial capture')
        return result
    monkeypatch.setattr(packages, '_run', changing)
    with pytest.raises(ValueError):
        verify()
    assert changed == [True]


def change_during_second_package(bundle, monkeypatch, action):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    rows = json.loads(manifest.read_text())['packages']
    second = directory / rows[1]['archive']
    original = packages._run
    changes = []
    def run(argv, cwd, deadline, **kwargs):
        result = original(argv, cwd, deadline, **kwargs)
        if argv[0] == str(tools['bsdtar']) and argv[2] == str(second) and not changes:
            changes.append(True)
            action()
        return result
    monkeypatch.setattr(packages, '_run', run)
    return changes


@pytest.mark.parametrize('selected', ['manifest', 'archive', 'signature', 'keyring'])
@pytest.mark.parametrize('mutation', ['same-size', 'same-bytes-replacement', 'remove'])
def test_final_capture_detects_late_content_identity_or_existence_changes(bundle, monkeypatch,
                                                                         selected, mutation):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    row = json.loads(manifest.read_text())['packages'][0]
    archive = directory / row['archive']
    target = {'manifest': manifest, 'archive': archive, 'signature': Path(str(archive) + '.sig'),
              'keyring': keyring / 'trustdb.gpg'}[selected]
    before = target.stat()
    content = target.read_bytes()
    def change():
        if mutation == 'remove':
            target.unlink()
            return
        if mutation == 'same-bytes-replacement':
            replacement = target.with_name('replacement.tmp')
            replacement.write_bytes(content)
            replacement.replace(target)
        else:
            value = bytearray(content); value[-1] ^= 1
            target.write_bytes(value)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    changes = change_during_second_package(bundle, monkeypatch, change)
    with pytest.raises((OSError, ValueError)):
        verify()
    assert changes == [True]


def test_success_retains_lock_schema_and_all_source_inputs(bundle, monkeypatch):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    sources = [manifest, *directory.iterdir(), *keyring.iterdir(), *tools.values()]
    before = {path: path.read_bytes() for path in sources}
    def forbidden(*args, **kwargs):
        pytest.fail('Synthetic package verification attempted a real process or network request')
    import socket
    import urllib.request
    monkeypatch.setattr(packages, 'Processes', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    record = verify()
    assert set(record) == {'schema_version', 'kind', 'candidate_only', 'production_qualified',
        'status', 'manifest_sha256', 'trusted_keyring_sha256', 'allowed_signers',
        'verification_tool_sha256', 'packages', 'runtime_dependencies', 'atomic_snapshot',
        'installed_or_executed_firmware', 'limitations'}
    assert record['status'] == 'verified_listed_package_closure'
    assert record['production_qualified'] is False and record['atomic_snapshot'] is False
    assert record['installed_or_executed_firmware'] is False
    assert record['manifest_sha256'] == hashlib.sha256(before[manifest]).hexdigest()
    assert all(path.read_bytes() == data for path, data in before.items())
    assert str(directory) not in json.dumps(record) and str(keyring) not in json.dumps(record)


def test_cancelled_verification_does_not_dispatch_a_verifier(bundle):
    *_, calls, metadata, verify = bundle
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt):
        verify(cancel_event=event)
    assert calls == []


@pytest.mark.parametrize('field', ['bundle', 'manifest', 'keyring', 'gpg', 'bsdtar', 'vercmp'])
@pytest.mark.parametrize('unsafe', ['/workspace/FIRMAVEX/private', 'evidence/windows-sandbox/private',
    'EVIDENCE\\WINDOWS-SANDBOX\\private', '../private'],
    ids=['original-checkout', 'protected', 'protected-backslashes', 'parent'])
def test_all_supplied_path_exclusions_precede_input_access(bundle, monkeypatch, field, unsafe):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
    selected = {'bundle': directory, 'manifest': manifest, 'keyring': keyring, **tools}
    selected[field] = unsafe
    def forbidden(*args, **kwargs):
        pytest.fail('Lexically refused verification input accessed the filesystem')
    for name in ('checked_path', 'read_bytes', '_identity', 'path_state'):
        monkeypatch.setattr(packages, name, forbidden)
    with pytest.raises(ValueError):
        packages.verify(selected['bundle'], selected['manifest'], pin, selected['keyring'], [SIGNER],
                        gpg=selected['gpg'], bsdtar=selected['bsdtar'], vercmp=selected['vercmp'],
                        trusted_tool_sha256=hashes)
    assert calls == []


def test_expired_identity_deadline_precedes_filesystem_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('Expired hash deadline accessed input')
    monkeypatch.setattr(packages, 'checked_path', forbidden)
    with pytest.raises(TimeoutError):
        packages._identity(tmp_path / 'never-created', 1024, deadline=0)


def test_expired_subprocess_deadline_precedes_process_ownership(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail('Expired deadline created a process owner')
    monkeypatch.setattr(packages, 'Processes', forbidden)
    with pytest.raises(TimeoutError):
        packages._run(['synthetic-no-process'], tmp_path, 0)


def test_late_deadline_expiration_prevents_capture_success(bundle, monkeypatch):
    *_, verify = bundle
    original = packages._Capture.finish
    expired = []
    def finish(capture):
        expired.append(True); capture.deadline = 0
        return original(capture)
    monkeypatch.setattr(packages._Capture, 'finish', finish)
    with pytest.raises(TimeoutError):
        verify()
    assert expired == [True]


def test_cancellation_during_later_package_prevents_lock_result(bundle, monkeypatch):
    *_, verify = bundle
    event = threading.Event()
    changed = change_during_second_package(bundle, monkeypatch, event.set)
    with pytest.raises(KeyboardInterrupt):
        verify(cancel_event=event)
    assert changed == [True]


def test_cancellation_during_final_capture_prevents_lock_result(bundle, monkeypatch):
    *_, verify = bundle
    event = threading.Event()
    original = packages._Capture.finish
    finished = []
    def finish(capture):
        finished.append(True); event.set()
        return original(capture)
    monkeypatch.setattr(packages._Capture, 'finish', finish)
    with pytest.raises(KeyboardInterrupt):
        verify(cancel_event=event)
    assert finished == [True]


def test_identity_cancellation_during_hashing_propagates(tmp_path, monkeypatch):
    path = tmp_path / 'hash-input'; path.write_bytes(b'bounded synthetic bytes')
    event = threading.Event()
    original = packages.hashlib.sha256
    updates = []
    class Hash:
        def __init__(self): self.value = original()
        def update(self, value):
            updates.append(True); self.value.update(value); event.set()
        def hexdigest(self): return self.value.hexdigest()
    monkeypatch.setattr(packages.hashlib, 'sha256', Hash)
    with pytest.raises(KeyboardInterrupt):
        packages._identity(path, 1024, cancel_event=event)
    assert updates == [True]


class SyntheticControl(BaseException):
    """Invented cancellation behavior, never runtime or publisher evidence."""


@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, SyntheticControl],
                         ids=['keyboard', 'exit', 'other-control'])
def test_identity_hash_control_flow_keeps_original_object(tmp_path, monkeypatch, factory):
    path = tmp_path / 'hash-input'; path.write_bytes(b'synthetic bytes')
    control = factory('PRIVATE-CONTROL')
    original = packages.hashlib.sha256
    class Hash:
        def __init__(self): self.value = original()
        def update(self, value): raise control
        def hexdigest(self): return self.value.hexdigest()
    monkeypatch.setattr(packages.hashlib, 'sha256', Hash)
    with pytest.raises(type(control)) as caught:
        packages._identity(path, 1024)
    assert caught.value is control


@pytest.mark.parametrize('cancel_during_run', [False, True], ids=['normal', 'cancelled'])
def test_reviewed_subprocess_receives_caller_event_and_cleanup(tmp_path, monkeypatch, cancel_during_run):
    event = threading.Event(); owners = []
    class Owner:
        def __init__(self, selected, limits):
            assert selected is event
            assert limits.memory_bytes == 1024**3 and limits.log_bytes == 131072
            self.closed = False; owners.append(self)
        def run(self, argv, cwd):
            assert argv == ['synthetic-no-process'] and cwd == tmp_path
            if cancel_during_run: event.set()
            return 0, 'synthetic verifier output', ''
        def close(self): self.closed = True
    monkeypatch.setattr(packages, 'Processes', Owner)
    if cancel_during_run:
        with pytest.raises(KeyboardInterrupt):
            packages._run(['synthetic-no-process'], tmp_path, packages.time.monotonic() + 5,
                          cancel_event=event)
    else:
        assert packages._run(['synthetic-no-process'], tmp_path, packages.time.monotonic() + 5,
                             cancel_event=event) == 'synthetic verifier output'
    assert len(owners) == 1 and owners[0].closed is True


@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, SyntheticControl],
                         ids=['keyboard', 'exit', 'other-control'])
@pytest.mark.parametrize('secondary_factory', [OSError, KeyboardInterrupt, SystemExit, SyntheticControl],
                         ids=['os-cleanup', 'keyboard-cleanup', 'exit-cleanup', 'other-cleanup'])
def test_original_subprocess_control_is_preserved_during_cleanup(tmp_path, monkeypatch,
                                                               factory, secondary_factory):
    control = factory('PRIVATE-PRIMARY'); secondary = secondary_factory('PRIVATE-SECONDARY')
    closed = []
    class Owner:
        def __init__(self, event, limits): pass
        def run(self, argv, cwd): raise control
        def close(self): closed.append(True); raise secondary
    monkeypatch.setattr(packages, 'Processes', Owner)
    with pytest.raises(type(control)) as caught:
        packages._run(['synthetic-no-process'], tmp_path, packages.time.monotonic() + 5)
    assert caught.value is control and closed == [True]


@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, SyntheticControl],
                         ids=['keyboard', 'exit', 'other-control'])
@pytest.mark.parametrize('secondary_factory', [OSError, KeyboardInterrupt, SystemExit, SyntheticControl],
                         ids=['os-cleanup', 'keyboard-cleanup', 'exit-cleanup', 'other-cleanup'])
def test_original_verification_control_is_preserved_during_temporary_cleanup(bundle, monkeypatch,
                                                                          factory, secondary_factory):
    *_, verify = bundle
    control = factory('PRIVATE-PRIMARY'); secondary = secondary_factory('PRIVATE-SECONDARY')
    original = packages.tempfile.TemporaryDirectory
    cleaned = []
    class Temporary:
        def __init__(self, *args, **kwargs):
            self.actual = original(*args, **kwargs)
            self.name = self.actual.name
        def cleanup(self):
            self.actual.cleanup(); cleaned.append(True)
            raise secondary
    def interrupted(*args, **kwargs): raise control
    monkeypatch.setattr(packages.tempfile, 'TemporaryDirectory', Temporary)
    monkeypatch.setattr(packages, '_run', interrupted)
    with pytest.raises(type(control)) as caught:
        verify()
    assert caught.value is control and cleaned == [True]


def package_cli_arguments(bundle):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    command = ['--bundle', str(directory), '--manifest', str(manifest),
        '--expected-manifest-sha256', hashlib.sha256(manifest.read_bytes()).hexdigest(),
        '--keyring', str(keyring), '--signer', SIGNER]
    for name in tools:
        command += ['--' + name, str(tools[name]), '--' + name + '-sha256', hashes[name]]
    return command


def test_cli_does_not_publish_failure_diagnostics_or_private_paths(bundle, monkeypatch, capsys):
    def rejected(*args, **kwargs): raise ValueError('PRIVATE-PATH-TOKEN-CREDENTIAL')
    monkeypatch.setattr(packages, 'verify', rejected)
    assert packages.main(package_cli_arguments(bundle)) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {'candidate_only': True, 'production_qualified': False,
                                      'status': 'rejected', 'error_type': 'ValueError'}
    assert 'PRIVATE' not in captured.out + captured.err


@pytest.mark.parametrize('factory', [KeyboardInterrupt, SystemExit, SyntheticControl],
                         ids=['keyboard', 'exit', 'other-control'])
def test_cli_does_not_convert_control_flow_to_ordinary_failure(bundle, monkeypatch, capsys, factory):
    control = factory('PRIVATE-CONTROL')
    def interrupted(*args, **kwargs): raise control
    monkeypatch.setattr(packages, 'verify', interrupted)
    with pytest.raises(type(control)) as caught:
        packages.main(package_cli_arguments(bundle))
    assert caught.value is control and capsys.readouterr().out == ''


def test_cli_rejection_is_nonzero_and_does_not_publish_private_paths(bundle):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    command = [sys.executable, '-m', 'tools.windows_candidate_packages', '--bundle', str(directory),
        '--manifest', str(manifest), '--expected-manifest-sha256', '0' * 64,
        '--keyring', str(keyring), '--signer', SIGNER]
    for name in tools:
        command += ['--' + name, str(tools[name]), '--' + name + '-sha256', hashes[name]]
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {'candidate_only': True, 'production_qualified': False,
                                       'status': 'rejected', 'error_type': 'ValueError'}
    assert str(directory) not in result.stdout + result.stderr


@pytest.mark.skipif(not (shutil.which('gpg') and shutil.which('gpgconf')), reason='GnuPG fixture tools unavailable')
def test_actual_gnupg_fixture_status_is_accepted_and_unknown_signer_rejected(tmp_path):
    """Local synthetic key; never MSYS2 publisher or native Windows evidence."""
    gpg, gpgconf = shutil.which('gpg'), shutil.which('gpgconf')
    home = tmp_path / 'ephemeral-keys'; home.mkdir(mode=0o700)
    def command(*args):
        return subprocess.run([gpg, '--homedir', str(home), '--batch', *args],
                              capture_output=True, text=True, timeout=20, check=True)
    try:
        command('--pinentry-mode', 'loopback', '--passphrase', '', '--quick-generate-key',
                'Synthetic FIRMAVEX fixture <fixture@example.invalid>', 'ed25519', 'sign', '0')
        listing = command('--with-colons', '--list-keys').stdout
        fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
        data = tmp_path / 'fixture'; data.write_bytes(b'synthetic package fixture')
        signature = tmp_path / 'fixture.sig'
        command('--pinentry-mode', 'loopback', '--passphrase', '', '--detach-sign', '--output', str(signature), str(data))
        status = command('--no-options', '--no-auto-key-retrieve', '--no-auto-key-import', '--no-autostart',
                         '--no-auto-check-trustdb', '--status-fd', '1', '--verify', str(signature), str(data)).stdout
        assert packages.signature_status(status, [fingerprint])['signing_fingerprint'] == fingerprint
        with pytest.raises(ValueError): packages.signature_status(status, ['B' * 40])
    finally:
        subprocess.run([gpgconf, '--homedir', str(home), '--kill', 'all'], timeout=10, check=True,
                       capture_output=True, text=True)
