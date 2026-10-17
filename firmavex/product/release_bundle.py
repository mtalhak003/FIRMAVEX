"""Offline preview sidecars: integrity and build-environment inventory, not approval."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
import os
import stat
from pathlib import Path
import re
import subprocess
import sys

from firmavex.backends.security import checked_path, fresh_directory, read_json
from . import release
from .file_state import path_state, handle_state

SIDECARS = ('release-manifest.json', 'SHA256SUMS', 'build-environment.spdx.json',
            'release-review.json')


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def notice_identity(path):
    """Read-only installed notices may be hardlinked by package managers."""
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected a regular installed notice')
    path = path.resolve(strict=True)
    before = path_state(path)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = handle_state(stream.fileno())
        data = stream.read(4 * 1024**2 + 1)
        if len(data) > 4 * 1024**2:
            raise ValueError('License file exceeds inventory limit')
        stream.seek(0)
        if stream.read(4 * 1024**2 + 1) != data or handle_state(stream.fileno()) != opened:
            raise ValueError('Installed notice changed during capture')
    if opened != before or path_state(path) != before:
        raise ValueError('Installed notice changed during capture')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}


def inventory():
    """All installed Python distributions; not a claim about bundled native libraries."""
    views = {}
    for dist in metadata.distributions():
        name, version = dist.metadata['Name'], dist.version
        if not name or not version:
            raise ValueError('Distribution lacks name/version')
        normalized = re.sub(r'[-_.]+', '-', name).lower()
        declared = dist.metadata.get('License-Expression') or dist.metadata.get('License')
        if normalized in views and (views[normalized]['version'] != version or views[normalized]['license'] != declared):
            raise ValueError('Conflicting Python distribution: ' + normalized)
        view = views.setdefault(normalized, {'version': version, 'license': declared, 'notices': {}})
        for member in sorted(dist.files or [], key=str):
            spelling = str(member).replace('\\', '/')
            if '.dist-info/' not in spelling:
                continue
            leaf = Path(spelling).name.lower()
            if '/licenses/' not in spelling and not leaf.startswith(('license', 'copying', 'notice')):
                continue
            if Path(spelling).is_absolute() or '..' in Path(spelling).parts:
                raise ValueError('Unsafe distribution license path')
            notice = {'path': spelling, **notice_identity(dist.locate_file(member))}
            if spelling in view['notices'] and view['notices'][spelling] != notice:
                raise ValueError('Conflicting license file identity')
            view['notices'][spelling] = notice
    packages = []
    for name, view in sorted(views.items()):
        key = hashlib.sha256((name + '\0' + view['version']).encode()).hexdigest()
        packages.append({'SPDXID': 'SPDXRef-Package-' + key, 'name': name,
                         'versionInfo': view['version'], 'downloadLocation': 'NOASSERTION',
                         'filesAnalyzed': False, 'licenseConcluded': 'NOASSERTION',
                         'licenseDeclared': 'NOASSERTION', 'copyrightText': 'NOASSERTION',
                         'comment': json.dumps({
                             'scope': 'installed_build_environment_not_proven_bundled',
                             'declared_license_metadata': view['license'],
                             'license_files': sorted(view['notices'].values(), key=lambda n: n['path']),
                             'legal_clearance': 'not_established'}, sort_keys=True)})
    if not packages or len(packages) > 4096:
        raise ValueError('Unsupported build environment inventory size')
    return sorted(packages, key=lambda item: item['SPDXID'])


def capture(artifacts, *, repo):
    if getattr(sys, 'frozen', False):
        raise ValueError('Build-environment inventory requires the original build Python environment; frozen applications can verify bundles, not reconstruct build provenance')
    manifest = release.capture(artifacts, repo=repo)
    initial = release._git(repo)
    if initial[0] != manifest['git_revision'] or bool(initial[1]) != manifest['dirty'] or initial[2] != manifest['tracked_diff_sha256']:
        raise ValueError('Git state changed before bundle inventory')
    epoch = int(subprocess.check_output(
        ['git', '-C', str(repo), 'show', '-s', '--format=%ct', manifest['git_revision']], timeout=10))
    packages = inventory()
    stamp = datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    identifier = hashlib.sha256(canonical({'revision': manifest['git_revision'],
                                         'artifacts': manifest['artifacts'], 'packages': packages})).hexdigest()
    document = {'spdxVersion': 'SPDX-2.3', 'dataLicense': 'CC0-1.0',
                'SPDXID': 'SPDXRef-DOCUMENT', 'name': 'FIRMAVEX preview build environment',
                'documentNamespace': 'https://firmavex.invalid/spdx/' + identifier,
                'creationInfo': {'creators': ['Tool: FIRMAVEX preview inventory'], 'created': stamp,
                                 'comment': 'Timestamp is source commit time, not measured build time.'},
                'documentDescribes': [item['SPDXID'] for item in packages],
                'packages': packages, 'relationships': [],
                'comment': 'Build-environment Python SBOM only. Native libraries, OS packages and runtime packs require separate inventories. No legal clearance, signing, reproducibility or security qualification is implied.'}
    review = {'schema_version': 1, 'kind': 'firmavex_release_review', 'channel': 'preview',
              'release_approved': False, 'signing': 'not_verified', 'notarization': 'not_verified',
              'native_dependency_audit': 'required', 'corresponding_source_archive': 'required',
              'sbom_scope': 'installed_python_build_environment_only',
              'runtime_distribution': 'not_bundled; direct vendor installation is separate',
              'reproducible_build': 'not_established', 'consumer_machine_validation': 'not_established',
              'hostile_workloads': 'rejected', 'macos': 'desktop_preview_only',
              'source_timestamp': stamp, 'source_timestamp_basis': 'actual_git_commit_time'}
    if inventory() != packages or release._git(repo) != initial:
        raise ValueError('Build environment or Git state changed during inventory')
    for artifact in artifacts:
        if release._identity(artifact) != manifest['artifacts'][Path(artifact).name]:
            raise ValueError('Release artifact changed during bundle capture')
    return {'release-manifest.json': canonical(manifest),
            'SHA256SUMS': ''.join(v['sha256'] + '  ' + k + '\n' for k, v in sorted(manifest['artifacts'].items())).encode(),
            'build-environment.spdx.json': canonical(document), 'release-review.json': canonical(review)}


def create(artifacts, *, repo, output):
    contents = capture(artifacts, repo=repo)
    directory = fresh_directory(output)
    identities = {}
    for name, data in contents.items():
        with (directory / name).open('xb') as stream:
            stream.write(data)
        identities[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
    index = {'schema_version': 1, 'kind': 'firmavex_preview_bundle', 'files': identities,
             'authenticity': 'not_established_by_checksums'}
    with (directory / 'bundle-index.json').open('xb') as stream:
        stream.write(canonical(index))
    return {'bundle': str(directory), 'sidecars': len(contents), 'release_approved': False}


def verify(directory, artifact_dir):
    directory = checked_path(directory, directory=True)
    index_path = directory / 'bundle-index.json'
    index_identity = release._identity(index_path)
    index = read_json(index_path, 1024**2)
    if (type(index) is not dict or set(index) != {'schema_version', 'kind', 'files', 'authenticity'}
            or type(index['schema_version']) is not int or index['schema_version'] != 1
            or index['kind'] != 'firmavex_preview_bundle'
            or index['authenticity'] != 'not_established_by_checksums'
            or type(index['files']) is not dict or set(index['files']) != set(SIDECARS)):
        raise ValueError('Unsupported preview bundle index')
    for name, expected in index['files'].items():
        if (type(expected) is not dict or set(expected) != {'sha256', 'size_bytes'}
                or type(expected['size_bytes']) is not int or not 0 <= expected['size_bytes'] <= 64 * 1024**2
                or type(expected['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', expected['sha256'])
                or release._identity(directory / name) != expected):
            raise ValueError('Bundle sidecar verification failed: ' + name)
    result = release.verify(directory / 'release-manifest.json', artifact_dir)
    manifest = read_json(directory / 'release-manifest.json')
    expected_sums = ''.join(v['sha256'] + '  ' + k + '\n' for k, v in sorted(manifest['artifacts'].items())).encode()
    from firmavex.backends.security import read_bytes
    if read_bytes(directory / 'SHA256SUMS', 1024**2) != expected_sums:
        raise ValueError('Checksum list contradicts manifest')
    # The index covers the exact generated documents. It does not authenticate
    # them or accept a caller-supplied promotion to signed/approved release.
    review = read_json(directory / 'release-review.json')
    if (type(review) is not dict or type(review.get('schema_version')) is not int
            or review.get('schema_version') != 1 or review.get('kind') != 'firmavex_release_review'
            or review.get('channel') != 'preview' or review.get('native_dependency_audit') != 'required'
            or review.get('corresponding_source_archive') != 'required'
            or review.get('sbom_scope') != 'installed_python_build_environment_only'
            or review.get('release_approved') is not False or review.get('signing') != 'not_verified'
            or review.get('notarization') != 'not_verified' or review.get('hostile_workloads') != 'rejected'):
        raise ValueError('Unsupported release approval claim')
    document = read_json(directory / 'build-environment.spdx.json')
    if (type(document) is not dict or document.get('spdxVersion') != 'SPDX-2.3'
            or document.get('dataLicense') != 'CC0-1.0'
            or document.get('SPDXID') != 'SPDXRef-DOCUMENT'
            or type(document.get('packages')) is not list or not 1 <= len(document['packages']) <= 4096):
        raise ValueError('Unsupported build-environment SPDX document')
    packages = document['packages']
    ids = []
    for package in packages:
        if (type(package) is not dict or type(package.get('name')) is not str
                or type(package.get('versionInfo')) is not str
                or package.get('licenseConcluded') != 'NOASSERTION'
                or package.get('licenseDeclared') != 'NOASSERTION'
                or package.get('filesAnalyzed') is not False):
            raise ValueError('Unsupported SPDX package claim')
        identifier = 'SPDXRef-Package-' + hashlib.sha256((package['name'] + '\0' + package['versionInfo']).encode()).hexdigest()
        if package.get('SPDXID') != identifier or identifier in ids:
            raise ValueError('Invalid SPDX package identity')
        ids.append(identifier)
    identity = hashlib.sha256(canonical({'revision': manifest['git_revision'],
                                        'artifacts': manifest['artifacts'], 'packages': packages})).hexdigest()
    if (document.get('documentDescribes') != ids
            or document.get('documentNamespace') != 'https://firmavex.invalid/spdx/' + identity):
        raise ValueError('SPDX document identity contradicts release inventory')
    if release._identity(index_path) != index_identity or any(
            release._identity(directory / name) != expected for name, expected in index['files'].items()):
        raise ValueError('Bundle changed during verification')
    return {**result, 'verified_sidecars': len(SIDECARS), 'release_approved': False,
            'sbom_scope': 'installed_python_build_environment_only'}
