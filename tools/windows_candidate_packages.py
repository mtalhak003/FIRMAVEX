"""Offline candidate package-set verifier. Never installs or approves a runtime.

The manifest digest, public keyring and signer allowlist must be obtained through
an independent trusted channel, never from the package payload. Only listed
archives are read. Legal/source obligations and dynamic DLL closure are separate.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import tempfile
import threading
import time

from firmavex.backends.api import Limits
from firmavex.backends.process import Processes
from firmavex.backends.security import checked_path, read_bytes
from firmavex.product.file_state import handle_state, path_state
from tools.windows_runtime_candidate import PACKAGES

MAX_PACKAGES = 1024
MAX_BYTES = 8 * 1024**3
_NAME = r'[A-Za-z0-9][A-Za-z0-9+_.@-]{0,159}'
_VERSION = r'[0-9][A-Za-z0-9.+_:~-]{0,127}'


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def _digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected lowercase SHA-256')
    return value


def _name(value):
    if type(value) is not str or not re.fullmatch(_NAME, value):
        raise ValueError('Invalid package name')
    return value


def _identity(path, maximum, expected_size=None):
    """Bound bytes before and during hashing; reject observable file changes."""
    path = checked_path(path)
    before = path.stat()
    if (not 0 < before.st_size <= maximum
            or expected_size is not None and before.st_size != expected_size):
        raise ValueError('Verification input size bound or identity changed')
    initial = path_state(path, before)
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        if handle_state(stream.fileno()) != initial:
            raise ValueError('Verification input changed before hashing')
        while chunk := stream.read(min(1024**2, before.st_size + 1 - size)):
            size += len(chunk)
            if size > before.st_size:
                raise ValueError('Verification input grew during hashing')
            digest.update(chunk)
        if size != before.st_size or handle_state(stream.fileno()) != initial:
            raise ValueError('Verification input changed during hashing')
    checked_path(path)
    if path_state(path) != initial:
        raise ValueError('Verification input changed after hashing')
    return {'path': str(path), 'sha256': digest.hexdigest(), 'size_bytes': size}


def _constraint(value):
    match = re.fullmatch(f'({_NAME})(?:(>=|<=|=|>|<)({_VERSION}))?', value)
    if match is None:
        raise ValueError('Unsupported package dependency expression')
    return match.groups()


def metadata(text):
    """Parse actual signed .PKGINFO, not caller-supplied package descriptions."""
    if len(text.encode('utf-8')) > 65536:
        raise ValueError('Package metadata exceeds bound')
    rows = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition(' = ')
        if not separator or not re.fullmatch('[a-z][a-z0-9_]{0,39}', key) or not value:
            raise ValueError('Invalid package metadata record')
        rows.setdefault(key, []).append(value)
    for key in ('pkgname', 'pkgver', 'arch'):
        if len(rows.get(key, [])) != 1:
            raise ValueError('Missing or duplicate package identity')
    name, version, arch = (rows[k][0] for k in ('pkgname', 'pkgver', 'arch'))
    _name(name)
    if not re.fullmatch(_VERSION, version) or arch not in {'any', 'x86_64'}:
        raise ValueError('Unsupported package version or architecture')
    licenses = rows.get('license', [])
    if not licenses or any(not re.fullmatch(r'[A-Za-z0-9 ._:+()/\-]{1,160}', value) for value in licenses):
        raise ValueError('Missing or unsupported license declaration')
    depends, provides, conflicts = (rows.get(k, []) for k in ('depend', 'provides', 'conflict'))
    for value in depends + provides + conflicts:
        _constraint(value)
    if any(_constraint(value)[1] not in {None, '='} for value in provides):
        raise ValueError('Unsupported versioned provide')
    return {'name': name, 'version': version, 'architecture': arch,
            'licenses': licenses, 'depends': depends, 'provides': provides,
            'conflicts': conflicts, 'metadata_sha256': hashlib.sha256(text.encode()).hexdigest()}


def signature_status(text, allowed):
    rows = [line[len('[GNUPG:] '):].split() for line in text.splitlines() if line.startswith('[GNUPG:] ')]
    rejected = {'BADSIG', 'ERRSIG', 'REVKEYSIG', 'EXPKEYSIG', 'EXPSIG', 'NO_PUBKEY',
                'NODATA', 'FAILURE', 'ERROR', 'KEYEXPIRED', 'SIGEXPIRED', 'KEYREVOKED'}
    if any(row and row[0] in rejected for row in rows):
        raise ValueError('Publisher signature failed')
    valid = [row for row in rows if row and row[0] == 'VALIDSIG']
    if len(valid) != 1 or len(valid[0]) not in {10, 11}:
        raise ValueError('Exactly one valid publisher signature required')
    row = valid[0]
    signing, primary = row[1], row[10] if len(row) == 11 else row[1]
    if (not re.fullmatch('[A-F0-9]{40}|[A-F0-9]{64}', signing)
            or not re.fullmatch('[A-F0-9]{40}|[A-F0-9]{64}', primary)
            or not ({signing, primary} & set(allowed)) or row[8] not in {'8', '9', '10'}
            or not any(r and r[0] in {'TRUST_FULLY', 'TRUST_ULTIMATE'} for r in rows)):
        raise ValueError('Trusted allowlisted publisher signature required')
    return {'signing_fingerprint': signing, 'primary_fingerprint': primary,
            'hash_algorithm': row[8], 'trust': 'full_or_ultimate'}


def closure(packages, compare):
    """Resolve mandatory runtime dependencies and conflicts using native vercmp."""
    by_name = {}
    capabilities = {}
    for package in packages:
        name = package['name']
        if name in by_name:
            raise ValueError('Duplicate package identity')
        by_name[name] = package
        capabilities.setdefault(name, []).append((name, package['version']))
        for expression in package['provides']:
            virtual, _, version = _constraint(expression)
            capabilities.setdefault(virtual, []).append((name, version))
    if any(by_name.get(name, {}).get('version') != version for name, version in PACKAGES.items()):
        raise ValueError('Candidate root package pins missing or changed')
    def matches(expression):
        name, operator, expected = _constraint(expression)
        found = []
        for provider, version in capabilities.get(name, []):
            if operator is None:
                found.append(provider)
            elif version is not None:
                result = compare(version, expected)
                if {'=': result == 0, '>': result > 0, '<': result < 0,
                    '>=': result >= 0, '<=': result <= 0}[operator]:
                    found.append(provider)
        return sorted(set(found))
    resolved = {}
    for name, package in sorted(by_name.items()):
        rows = {}
        for dependency in package['depends']:
            providers = matches(dependency)
            if not providers:
                raise ValueError('Incomplete package dependency closure')
            rows[dependency] = providers
        if any(any(provider != name for provider in matches(value)) for value in package['conflicts']):
            raise ValueError('Conflicting package set')
        resolved[name] = rows
    return resolved


def _run(argv, cwd, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Package-set verification deadline exceeded')
    owner = Processes(threading.Event(), Limits(timeout_seconds=min(60, remaining),
        memory_bytes=1024**3, log_bytes=131072, artifact_bytes=1048576))
    primary = None
    try:
        code, stdout, _ = owner.run(argv, cwd)
        if code:
            raise ValueError('External package verification command failed')
        return stdout
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            owner.close()
        except BaseException as cleanup:
            if primary is None or (isinstance(primary, Exception) and not isinstance(cleanup, Exception)):
                raise
            primary.add_note('Package verifier process cleanup failed')


def verify(bundle, manifest, expected_manifest_sha256, keyring, signers, *, gpg, bsdtar, vercmp,
           trusted_tool_sha256):
    """Return a new verified lock record; do not write, install, download or approve."""
    bundle, keyring = checked_path(bundle, directory=True), checked_path(keyring, directory=True)
    if bundle == keyring or bundle in keyring.parents:
        raise ValueError('Trusted keyring must be independent of the package payload')
    signers = list(signers)
    if not signers or len(signers) > 64 or any(not re.fullmatch('[A-F0-9]{40}|[A-F0-9]{64}', s) for s in signers):
        raise ValueError('Independent publisher fingerprint allowlist required')
    data = read_bytes(manifest, 1024**2)
    if hashlib.sha256(data).hexdigest() != _digest(expected_manifest_sha256):
        raise ValueError('Manifest digest mismatch')
    specification = json.loads(data, object_pairs_hook=_object)
    if (type(specification) is not dict or set(specification) != {'schema_version', 'packages'}
            or type(specification['schema_version']) is not int or specification['schema_version'] != 1
            or type(specification['packages']) is not list or not 1 <= len(specification['packages']) <= MAX_PACKAGES):
        raise ValueError('Unsupported package-set manifest')
    tools = {name: checked_path(path) for name, path in {'gpg': gpg, 'bsdtar': bsdtar, 'vercmp': vercmp}.items()}
    if type(trusted_tool_sha256) is not dict or set(trusted_tool_sha256) != set(tools):
        raise ValueError('Independent verification-tool hashes required')
    tool_records = {name: _identity(path, 512 * 1024**2) for name, path in tools.items()}
    identities = {name: value['sha256'] for name, value in tool_records.items()}
    if any(identities[name] != _digest(trusted_tool_sha256[name]) for name in tools):
        raise ValueError('Verification-tool digest mismatch')
    seen, size, records = set(), 0, []
    deadline = time.monotonic() + 600
    with tempfile.TemporaryDirectory(prefix='firmavex-candidate-package-check-') as temporary:
        temporary = Path(temporary)
        home = temporary / 'keys'; home.mkdir(mode=0o700)
        work = temporary / 'work'; work.mkdir()
        trusted = {}
        for name in ('pubring.gpg', 'pubring.kbx', 'trustdb.gpg'):
            source = keyring / name
            if not source.exists():
                continue
            content = read_bytes(source, 32 * 1024**2)
            trusted[name] = hashlib.sha256(content).hexdigest()
            (home / name).write_bytes(content)
        if 'trustdb.gpg' not in trusted or not ({'pubring.gpg', 'pubring.kbx'} & trusted.keys()):
            raise ValueError('Independent public keyring and trust database required')
        for row in specification['packages']:
            if type(row) is not dict or set(row) != {'archive', 'sha256', 'signature_sha256'}:
                raise ValueError('Invalid package manifest entry')
            name = row['archive']
            if (type(name) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]{0,239}\.pkg\.tar\.(?:zst|xz|gz)', name)
                    or name.casefold() in seen):
                raise ValueError('Unsafe or duplicate archive name')
            seen.add(name.casefold())
            archive, signature = checked_path(bundle / name), checked_path(bundle / (name + '.sig'))
            archive_size, signature_size = archive.stat().st_size, signature.stat().st_size
            size += archive_size + signature_size
            if not (0 < archive_size <= 512 * 1024**2 and 0 < signature_size <= 65536 and size <= MAX_BYTES):
                raise ValueError('Package archive/signature byte bound exceeded')
            before = _identity(archive, 512 * 1024**2, archive_size)
            sig_before = _identity(signature, 65536, signature_size)
            if before['sha256'] != _digest(row['sha256']) or sig_before['sha256'] != _digest(row['signature_sha256']):
                raise ValueError('Package archive/signature bound or digest mismatch')
            status = _run([str(tools['gpg']), '--batch', '--no-options', '--no-autostart',
                '--no-auto-key-retrieve', '--no-auto-key-import', '--no-auto-check-trustdb',
                '--homedir', str(home), '--status-fd', '1', '--verify', str(signature), str(archive)], work, deadline)
            signer = signature_status(status, signers)
            if before != _identity(archive, 512 * 1024**2, archive_size):
                raise ValueError('Package changed after signature verification')
            text = _run([str(tools['bsdtar']), '-xOf', str(archive), '.PKGINFO'], work, deadline)
            package = metadata(text)
            if before != _identity(archive, 512 * 1024**2, archive_size) or sig_before != _identity(signature, 65536, signature_size):
                raise ValueError('Package or signature changed during verification')
            records.append({**package, **row, 'signature': signer})
        comparisons = {}
        def compare(a, b):
            if (a, b) not in comparisons:
                answer = _run([str(tools['vercmp']), a, b], work, deadline).strip()
                if not re.fullmatch('-?[0-9]{1,10}', answer):
                    raise ValueError('Invalid native version-comparison result')
                comparisons[a, b] = int(answer)
            return comparisons[a, b]
        dependencies = closure(records, compare)
    for name, path in tools.items():
        if _identity(path, 512 * 1024**2, tool_records[name]['size_bytes'])['sha256'] != identities[name]:
            raise ValueError('Verification tool changed')
    return {'schema_version': 1, 'kind': 'firmavex_candidate_package_lock',
        'candidate_only': True, 'production_qualified': False, 'status': 'verified_listed_package_closure',
        'manifest_sha256': expected_manifest_sha256, 'trusted_keyring_sha256': trusted,
        'allowed_signers': sorted(set(signers)), 'verification_tool_sha256': identities,
        'packages': sorted(records, key=lambda p: p['name']), 'runtime_dependencies': dependencies,
        'atomic_snapshot': False, 'installed_or_executed_firmware': False,
        'limitations': ['Listed signed archives and mandatory metadata dependencies only; no installation performed.',
            'Archive-to-installed QEMU/GDB executable binding and native installation remain unproven until approved native verification.',
            'Optional/build/check dependencies and dynamic system DLL resolution are not established.',
            'License declarations are inventoried; corresponding source and redistribution clearance require review.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'manifest', 'keyring', 'gpg', 'bsdtar', 'vercmp'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('gpg', 'bsdtar', 'vercmp'):
        parser.add_argument('--' + name + '-sha256', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--signer', action='append', required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.bundle, args.manifest, args.expected_manifest_sha256, args.keyring,
                        args.signer, gpg=args.gpg, bsdtar=args.bsdtar, vercmp=args.vercmp,
                        trusted_tool_sha256={name: getattr(args, name + '_sha256') for name in ('gpg', 'bsdtar', 'vercmp')})
    except Exception as error:
        # API callers retain exceptions; the CLI never publishes raw package/tool output.
        print(json.dumps({'candidate_only': True, 'production_qualified': False,
                          'status': 'rejected', 'error_type': type(error).__name__}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
