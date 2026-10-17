"""Preview sidecars never establish authenticity, legal clearance or qualification."""
import hashlib
import json
import subprocess
from pathlib import Path
import pytest
from firmavex.product import release, release_bundle as bundle


@pytest.fixture
def build(tmp_path):
    repo = tmp_path/'source'; repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-q', '--allow-empty', '-m', 'Synthetic build source'], check=True)
    artifact = tmp_path/'candidate.deb'; artifact.write_bytes(b'synthetic installer; never executed')
    return repo, artifact


def test_bundle_round_trip_and_deterministic_inventory(build, tmp_path):
    repo, artifact = build
    first = bundle.capture([artifact], repo=repo)
    assert first == bundle.capture([artifact], repo=repo)
    doc = json.loads(first['build-environment.spdx.json'])
    assert doc['spdxVersion'] == 'SPDX-2.3'
    assert doc['packages'] and len(doc['packages']) == len(doc['documentDescribes'])
    assert all(p['licenseConcluded'] == 'NOASSERTION' and p['filesAnalyzed'] is False for p in doc['packages'])
    assert all('installed_build_environment_not_proven_bundled' in p['comment'] for p in doc['packages'])
    out = tmp_path/'bundle'
    bundle.create([artifact], repo=repo, output=out)
    result = bundle.verify(out, tmp_path)
    assert result['verified_artifacts'] == 1 and result['verified_sidecars'] == 4
    assert result['release_approved'] is False
    assert result['authenticity'] == 'not_established_by_checksums'
    assert set(p.name for p in out.iterdir()) == set(bundle.SIDECARS) | {'bundle-index.json'}
    with pytest.raises(FileExistsError): bundle.create([artifact], repo=repo, output=out)


@pytest.mark.parametrize('name', [*bundle.SIDECARS, 'bundle-index.json'])
def test_every_sidecar_tamper_is_rejected(build, tmp_path, name):
    repo, artifact = build; out = tmp_path/'bundle'
    bundle.create([artifact], repo=repo, output=out)
    (out/name).write_bytes(b'{}')
    with pytest.raises(ValueError): bundle.verify(out, tmp_path)


def test_actual_installer_tamper_is_rejected(build, tmp_path):
    repo, artifact = build; out = tmp_path/'bundle'
    bundle.create([artifact], repo=repo, output=out)
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError, match='artifact verification'): bundle.verify(out, tmp_path)


def test_inventory_race_rejects_without_creating_output(build, tmp_path, monkeypatch):
    repo, artifact = build
    monkeypatch.setattr(bundle, 'inventory', lambda: next(calls))
    # Preserve meaningful SPDX package identifiers while simulating metadata drift.
    calls = iter([[{'SPDXID': 'SPDXRef-one'}], [{'SPDXID': 'SPDXRef-two'}]])
    with pytest.raises(ValueError, match='environment or Git state changed'):
        bundle.create([artifact], repo=repo, output=tmp_path/'not-created')
    assert not (tmp_path/'not-created').exists()


def test_git_race_during_inventory_rejected(build, tmp_path, monkeypatch):
    repo, artifact = build
    original = bundle.inventory
    def changed():
        result = original()
        (repo/'new-untracked').write_text('observable source change')
        return result
    monkeypatch.setattr(bundle, 'inventory', changed)
    with pytest.raises(ValueError, match='Git state changed'): bundle.capture([artifact], repo=repo)


def test_checksums_cannot_contradict_manifest_even_with_updated_index(build, tmp_path):
    repo, artifact = build; out = tmp_path/'bundle'
    bundle.create([artifact], repo=repo, output=out)
    path = out/'SHA256SUMS'; path.write_text('misleading checksum list\n')
    index = json.loads((out/'bundle-index.json').read_text())
    index['files']['SHA256SUMS'] = release._identity(path)
    (out/'bundle-index.json').write_bytes(bundle.canonical(index))
    with pytest.raises(ValueError, match='contradicts'): bundle.verify(out, tmp_path)


def test_bundle_cli_and_original_manifest_contract(build, tmp_path):
    repo, artifact = build; out = tmp_path/'bundle'
    original = release.capture([artifact], repo=repo)
    assert release.main(['bundle-create', '--repo', str(repo), '--artifact', str(artifact), '--output', str(out)]) == 0
    assert release.main(['bundle-verify', '--bundle', str(out), '--artifact-dir', str(tmp_path)]) == 0
    assert json.loads((out/'release-manifest.json').read_text()) == original
    assert release.main(['bundle-verify', '--bundle', str(tmp_path/'absent'), '--artifact-dir', str(tmp_path)]) == 1


def test_duplicate_distribution_inventory_rejected(monkeypatch):
    class Distribution:
        metadata = {'Name': 'Example', 'License': 'synthetic license'}
        version = '1'; files = []
    first, second = Distribution(), Distribution()
    second.version = '2'
    monkeypatch.setattr(bundle.metadata, 'distributions', lambda: [first, second])
    with pytest.raises(ValueError, match='Conflicting'): bundle.inventory()
    second.version = '1'
    assert len(bundle.inventory()) == 1


@pytest.mark.parametrize('field,value', [('schema_version', True), ('files', {'../escape': {}}),
                                        ('authenticity', 'signed'), ('kind', 'approved')])
def test_unsupported_index_metadata_rejected(build, tmp_path, field, value):
    repo, artifact = build; out = tmp_path/'bundle'
    bundle.create([artifact], repo=repo, output=out)
    index = json.loads((out/'bundle-index.json').read_text()); index[field] = value
    (out/'bundle-index.json').write_bytes(bundle.canonical(index))
    with pytest.raises(ValueError): bundle.verify(out, tmp_path)


def test_installed_notice_hardlinks_are_read_only_and_hashed(tmp_path):
    import os
    path = tmp_path/'LICENSE'; path.write_bytes(b'actual test license bytes')
    alias = tmp_path/'alias'; os.link(path, alias)
    assert bundle.notice_identity(path) == {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes': path.stat().st_size}
    assert alias.read_bytes() == path.read_bytes()


def test_installed_notice_observable_race_rejected(tmp_path, monkeypatch):
    path = tmp_path/'LICENSE'; path.write_bytes(b'original')
    original = bundle.handle_state
    def changed(fd):
        result = original(fd); path.write_bytes(b'modified'); return result
    monkeypatch.setattr(bundle, 'handle_state', changed)
    with pytest.raises(ValueError, match='changed'): bundle.notice_identity(path)


def test_existing_official_manifest_unchanged_without_opt_in(build, tmp_path):
    repo, artifact = build; out = tmp_path/'legacy'
    assert release.main(['create', '--repo', str(repo), '--artifact', str(artifact), '--output', str(out)]) == 0
    assert set(p.name for p in out.iterdir()) == {'release-manifest.json', 'SHA256SUMS'}
    assert release.verify(out/'release-manifest.json', tmp_path)['verified_artifacts'] == 1


@pytest.mark.parametrize('document,value', [('release-review.json', []),
                                            ('release-review.json', {'release_approved': True}),
                                            ('build-environment.spdx.json', {})])
def test_reindexed_unsupported_sidecar_claims_rejected(build, tmp_path, document, value):
    repo, artifact = build; out = tmp_path/'bundle'
    bundle.create([artifact], repo=repo, output=out)
    path = out/document; path.write_bytes(bundle.canonical(value))
    index = json.loads((out/'bundle-index.json').read_text())
    index['files'][document] = release._identity(path)
    (out/'bundle-index.json').write_bytes(bundle.canonical(index))
    with pytest.raises(ValueError): bundle.verify(out, tmp_path)


def test_frozen_application_cannot_reconstruct_build_environment(build, tmp_path, monkeypatch):
    repo, artifact = build
    monkeypatch.setattr(bundle.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(bundle, 'inventory', lambda: pytest.fail('must not invent build environment'))
    with pytest.raises(ValueError, match='original build Python environment'):
        bundle.create([artifact], repo=repo, output=tmp_path/'absent')
    assert not (tmp_path/'absent').exists()
