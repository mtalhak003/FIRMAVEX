"""Synthetic package fixtures, not MSYS2 publisher or Windows qualification."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

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
    def run(argv, cwd, deadline):
        calls.append(argv)
        if argv[0] == str(tools['gpg']): return valid_status()
        if argv[0] == str(tools['bsdtar']): return metadata[argv[2]]
        if argv[0] == str(tools['vercmp']): return '0\n'
        pytest.fail('Unexpected verifier command')
    monkeypatch.setattr(packages, '_run', run)
    def verify():
        return packages.verify(directory, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(),
                               keyring, [SIGNER], trusted_tool_sha256=hashes, **tools)
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
    def rejected(argv, cwd, deadline):
        assert '--verify' in argv
        return '[GNUPG:] BADSIG bad\n'
    monkeypatch.setattr(packages, '_run', rejected)
    with pytest.raises(ValueError, match='signature'): verify()


def test_changed_archive_during_read_is_rejected(bundle, monkeypatch):
    directory, manifest, keyring, tools, hashes, calls, metadata, verify = bundle
    def changing(argv, cwd, deadline):
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
    def guarded(path, *args):
        if path.parent == directory: pytest.fail('Oversized package input must not be hashed')
        return original(path, *args)
    monkeypatch.setattr(packages, '_identity', guarded)
    with pytest.raises(ValueError, match='byte bound'): verify()
    assert calls == []


def test_identity_hash_checks_size_before_reading_and_detects_growth(tmp_path):
    path = tmp_path / 'fixture'; path.write_bytes(b'small fixture')
    with pytest.raises(ValueError, match='size bound'): packages._identity(path, 1)
    with pytest.raises(ValueError, match='size bound'): packages._identity(path, 1024, 1)
    assert packages._identity(path, 1024)['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


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
