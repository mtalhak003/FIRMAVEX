"""Preview identities are file integrity, never release qualification/signing."""

import hashlib
import json
from pathlib import Path
import pytest
from firmavex.product import release


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    artifact = tmp_path / "application.deb"
    artifact.write_bytes(b"not a real installer: unit test")
    monkeypatch.setattr(release, "_git", lambda repo: ("a" * 40, "", "b" * 64))
    return artifact


def test_capture_and_verify_are_deterministic_and_truthful(prepared, tmp_path):
    record = release.capture([prepared], repo=tmp_path)
    assert record == release.capture([prepared], repo=tmp_path)
    assert record["consistency"]["atomic"] is False
    assert record["channel"] == "preview" and record["signing"] == "not_verified"
    assert (
        record["artifacts"][prepared.name]["sha256"]
        == hashlib.sha256(prepared.read_bytes()).hexdigest()
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(record))
    assert (
        release.verify(path, tmp_path)["authenticity"] == "not_established_by_checksums"
    )
    prepared.write_bytes(b"changed")
    with pytest.raises(ValueError, match="verification failed"):
        release.verify(path, tmp_path)


def test_git_change_during_capture_rejected(prepared, tmp_path, monkeypatch):
    states = iter([("a" * 40, "", "b" * 64), ("a" * 40, " M file", "c" * 64)])
    monkeypatch.setattr(release, "_git", lambda repo: next(states))
    with pytest.raises(ValueError, match="Git state changed"):
        release.capture([prepared], repo=tmp_path)


def test_observable_content_race_rejected_even_with_deferred_metadata(
    prepared, monkeypatch
):
    state = release.path_state(prepared)
    calls = 0

    def change(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            prepared.write_bytes(b"x" * len(prepared.read_bytes()))
        return state

    # Change after both reads remains detectable by stable path state on ordinary
    # files; this test specifically changes at the handle-state capture boundary.
    monkeypatch.setattr(release, "handle_state", change)
    monkeypatch.setattr(release, "path_state", lambda *args: state)
    with pytest.raises(ValueError, match="changed"):
        release._identity(prepared)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "A\\file", "x:y"])
def test_untrusted_manifest_names_rejected(prepared, tmp_path, name):
    record = release.capture([prepared], repo=tmp_path)
    record["artifacts"] = {name: next(iter(record["artifacts"].values()))}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(record))
    with pytest.raises((ValueError, OSError)):
        release.verify(manifest, tmp_path)


def test_case_collisions_and_missing_artifacts(prepared, tmp_path):
    other = tmp_path / "APPLICATION.deb"
    other.write_bytes(b"other")
    with pytest.raises(ValueError, match="colliding"):
        release.capture([prepared, other], repo=tmp_path)


def test_cli_writes_only_fresh_output(prepared, tmp_path):
    output = tmp_path / "sidecars"
    assert (
        release.main(
            [
                "create",
                "--artifact",
                str(prepared),
                "--repo",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (output / "SHA256SUMS").is_file()
    assert (
        release.main(
            [
                "verify",
                "--manifest",
                str(output / "release-manifest.json"),
                "--artifact-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert (
        release.main(
            [
                "create",
                "--artifact",
                str(prepared),
                "--repo",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    "patch", [{"schema_version": True}, {"channel": "qualified"}, {"kind": "future"}]
)
def test_manifest_cannot_claim_release_qualification(prepared, tmp_path, patch):
    record = {**release.capture([prepared], repo=tmp_path), **patch}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Unsupported"):
        release.verify(path, tmp_path)


@pytest.mark.parametrize(
    "patch",
    [
        {"dirty": 0},
        {"git_revision": "not a revision"},
        {"tracked_diff_sha256": "A" * 64},
        {"signing": "signed"},
        {"consistency": {"status": "stable_observed", "atomic": True}},
        {"unexpected": "field"},
    ],
)
def test_release_metadata_is_strict_and_never_upgrades_claims(
    prepared, tmp_path, patch
):
    record = {**release.capture([prepared], repo=tmp_path), **patch}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        release.verify(manifest, tmp_path)
