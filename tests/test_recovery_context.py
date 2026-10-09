"""Recovery evidence tests; temporary byte fixtures are not firmware runs."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from src.firmavex.protocols import provenance, recovery_context
from src.firmavex.protocols.journal import fingerprint
from src.firmavex.protocols.protocol import EvaluationProtocol


ID = "b-" + "3" * 32


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                          text=True, check=True, timeout=5).stdout.strip()


@pytest.fixture
def captured(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "source.c"
    source.write_bytes(b"administrative context test source")
    image = tmp_path / "firmware.elf"
    image.write_bytes(b"administrative context test image, not executable ARM")
    git(repository, "init", "--quiet")
    git(repository, "add", "source.c")
    git(repository, "-c", "user.name=Recovery Test", "-c", "user.email=recovery@example.test",
        "commit", "--quiet", "-m", "test fixture")
    monkeypatch.setattr(provenance, "_tool_version", lambda name: {
        "status": "unavailable", "executable": None, "version": None, "error": f"{name} unavailable in test",
    })
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(), strategies=("enumerative",))
    kwargs = dict(repository=repository, preset_name="administrative_test",
                  firmware_images={ID: image}, source_inputs={ID: [source]},
                  build_metadata={ID: {"argv": ["fixture", "-O0"], "note": "not a firmware build"}},
                  started_at_utc="2026-10-08T00:00:00Z")
    manifest = provenance.capture_campaign_manifest(protocol, **kwargs)
    return protocol, kwargs, manifest


def test_context_projection_keeps_stable_actual_evidence_and_no_quality_upgrade(captured):
    protocol, kwargs, manifest = captured
    context = recovery_context.context_from_manifest(manifest)
    recovery_context.validate_context(context, protocol)
    assert context["schema_version"] == 1 and context["kind"] == "firmavex_recovery_context"
    assert context["plan_sha256"] == fingerprint(protocol.plan_to_dict())
    assert context["consistency"] == {"status": "stable_observed", "atomic": False}
    assert context["environment"]["git"]["revision"] == git(kwargs["repository"], "rev-parse", "HEAD")
    assert not context["environment"]["git"]["dirty"]
    image = context["benchmarks"][0]["firmware_image"]
    assert image == {
        "path": str(kwargs["firmware_images"][ID]), "requested_path": str(kwargs["firmware_images"][ID]),
        "size_bytes": kwargs["firmware_images"][ID].stat().st_size,
        "sha256": hashlib.sha256(kwargs["firmware_images"][ID].read_bytes()).hexdigest(),
    }
    assert context["preset"]["verification"] == "administrator_declared_not_verified"
    assert context["benchmarks"][0]["build"]["verification"] == "administrator_supplied_not_verified"
    assert all(tool["status"] == "unavailable" for tool in context["environment"]["tools"].values())
    serialized = json.dumps(context)
    assert "captured_at_utc" not in serialized and "started_at_utc" not in serialized
    assert "mtime_ns" not in serialized and "ctime_ns" not in serialized and '"identity"' not in serialized
    assert "real_firmware" not in serialized


def test_capture_helper_delegates_actual_capture_once_and_is_not_a_preset_label(captured, monkeypatch):
    protocol, kwargs, manifest = captured
    capture = Mock(wraps=recovery_context.capture_campaign_manifest)
    monkeypatch.setattr(recovery_context, "capture_campaign_manifest", capture)
    context = recovery_context.capture_recovery_context(protocol, **kwargs)
    capture.assert_called_once_with(protocol, **kwargs)
    assert context == recovery_context.context_from_manifest(manifest)


def test_recapture_ignores_timestamps_and_stat_only_changes(captured):
    protocol, kwargs, before = captured
    path = kwargs["firmware_images"][ID]
    metadata = path.stat()
    os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1000000))
    kwargs = {**kwargs, "started_at_utc": "2026-10-09T00:00:00Z"}
    after = provenance.capture_campaign_manifest(protocol, **kwargs)
    assert before["benchmarks"][0]["firmware_image"]["identity"] != after["benchmarks"][0]["firmware_image"]["identity"]
    assert recovery_context.context_from_manifest(before) == recovery_context.context_from_manifest(after)


@pytest.mark.parametrize("change", ["git_revision", "tracked_bytes", "untracked_bytes", "image_bytes", "source_bytes", "build_flags", "preset", "tool_version", "host", "python"])
def test_recapture_exposes_compatibility_changes_without_comparing_only_labels(captured, monkeypatch, change):
    protocol, kwargs, before = captured
    if change == "git_revision":
        git(kwargs["repository"], "-c", "user.name=Recovery Test", "-c", "user.email=recovery@example.test",
            "commit", "--quiet", "--allow-empty", "-m", "changed revision")
    elif change == "tracked_bytes":
        kwargs["source_inputs"][ID][0].write_bytes(b"changed tracked content")
    elif change == "untracked_bytes":
        (kwargs["repository"] / "new.txt").write_bytes(b"new administrative input")
    elif change == "image_bytes":
        kwargs["firmware_images"][ID].write_bytes(b"changed image bytes")
    elif change == "source_bytes":
        source = Path(kwargs["repository"]).parent / "external source.c"
        source.write_bytes(b"external support")
        kwargs = {**kwargs, "source_inputs": {ID: [*kwargs["source_inputs"][ID], source]}}
    elif change == "build_flags":
        kwargs = {**kwargs, "build_metadata": {ID: {"argv": ["fixture", "-O1"]}}}
    elif change == "preset":
        kwargs = {**kwargs, "preset_name": "different_declaration"}
    elif change == "tool_version":
        monkeypatch.setattr(provenance, "_tool_version", lambda name: {
            "status": "ok", "executable": "/unit/tools/" + name, "version": "unit fake 1", "error": None,
        })
    elif change == "host":
        monkeypatch.setattr(provenance.platform, "release", lambda: "changed unit host")
    else:
        monkeypatch.setattr(provenance.platform, "python_implementation", lambda: "ChangedUnitPython")
    after = provenance.capture_campaign_manifest(protocol, **kwargs)
    assert recovery_context.context_from_manifest(before) != recovery_context.context_from_manifest(after)


def test_untracked_context_retains_byte_and_relative_path_identity(captured):
    protocol, kwargs, _ = captured
    path = kwargs["repository"] / "untracked.txt"
    path.write_bytes(b"context untracked bytes")
    context = recovery_context.capture_recovery_context(protocol, **kwargs)
    artifact, = context["environment"]["git"]["untracked_files"]
    assert artifact == {
        "repository_path": "untracked.txt", "path": str(path), "requested_path": str(path),
        "size_bytes": 23, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    assert context["environment"]["git"]["dirty"]


def test_projection_is_a_detached_json_copy(captured):
    _, _, manifest = captured
    before = deepcopy(manifest)
    context = recovery_context.context_from_manifest(manifest)
    context["benchmarks"][0]["build"]["metadata"]["argv"].append("changed")
    context["environment"]["tools"]["arm-none-eabi-gcc"]["error"] = "changed"
    assert manifest == before


@pytest.mark.parametrize("change", ["version_bool", "wrong_kind", "plan_digest", "atomic_true", "atomic_zero", "unstable", "extra", "digest_upper", "size_bool", "preset_upgrade", "build_upgrade", "empty_sources", "duplicate_benchmark", "missing_benchmark", "tools_missing", "tool_label_only", "clean_diff", "clean_index", "dirty_flag", "untracked_escape", "host_nan"])
def test_malformed_or_contradictory_context_is_rejected(captured, change):
    protocol, _, manifest = captured
    context = recovery_context.context_from_manifest(manifest)
    if change == "version_bool":
        context["schema_version"] = True
    elif change == "wrong_kind":
        context["kind"] = "other"
    elif change == "plan_digest":
        context["plan_sha256"] = "0" * 64
    elif change == "atomic_true":
        context["consistency"]["atomic"] = True
    elif change == "atomic_zero":
        context["consistency"]["atomic"] = 0
    elif change == "unstable":
        context["consistency"]["status"] = "assumed"
    elif change == "extra":
        context["arbitrary"] = "not permitted"
    elif change == "digest_upper":
        context["benchmarks"][0]["firmware_image"]["sha256"] = "A" * 64
    elif change == "size_bool":
        context["benchmarks"][0]["firmware_image"]["size_bytes"] = True
    elif change == "preset_upgrade":
        context["preset"]["verification"] = "verified"
    elif change == "build_upgrade":
        context["benchmarks"][0]["build"]["verification"] = "verified"
    elif change == "empty_sources":
        context["benchmarks"][0]["source_inputs"] = []
    elif change == "duplicate_benchmark":
        context["benchmarks"].append(deepcopy(context["benchmarks"][0]))
    elif change == "missing_benchmark":
        context["benchmarks"] = []
    elif change == "tools_missing":
        del context["environment"]["tools"]["arm-none-eabi-gcc"]
    elif change == "tool_label_only":
        context["environment"]["tools"]["arm-none-eabi-gcc"] = {"status": "ok", "executable": None, "version": None, "error": None}
    elif change == "clean_diff":
        context["environment"]["git"]["tracked_diff_sha256"] = "1" * 64
    elif change == "clean_index":
        context["environment"]["git"]["index_diff_sha256"] = "1" * 64
    elif change == "dirty_flag":
        context["environment"]["git"]["dirty"] = True
    elif change == "untracked_escape":
        artifact = deepcopy(context["benchmarks"][0]["firmware_image"])
        artifact["repository_path"] = "../firmware.elf"
        context["environment"]["git"].update(dirty=True, status_short="?? ../firmware.elf", untracked_files=[artifact])
    else:
        context["benchmarks"][0]["build"]["metadata"]["unsafe"] = float("nan")
    with pytest.raises(ValueError):
        recovery_context.validate_context(context, protocol)


@pytest.mark.parametrize("location", ["manifest", "environment", "artifact"])
def test_projection_requires_stable_non_atomic_capture_evidence(captured, location):
    _, _, manifest = captured
    manifest = deepcopy(manifest)
    target = manifest if location == "manifest" else manifest["environment"] if location == "environment" else manifest["benchmarks"][0]["firmware_image"]
    target["consistency"]["atomic"] = True
    with pytest.raises(ValueError, match="non-atomic"):
        recovery_context.context_from_manifest(manifest)


@pytest.mark.parametrize("change", ["missing_identity", "mismatched_path", "mismatched_size", "extra_fields"])
def test_projection_rejects_inconsistent_raw_artifact_evidence(captured, change):
    _, _, manifest = captured
    manifest = deepcopy(manifest)
    image = manifest["benchmarks"][0]["firmware_image"]
    if change == "missing_identity":
        del image["identity"]
    elif change == "mismatched_path":
        image["identity"]["resolved_path"] = "/different/image.elf"
    elif change == "mismatched_size":
        image["identity"]["resolved_stat"]["size"] += 1
    else:
        image["unexpected"] = "not captured"
    with pytest.raises(ValueError):
        recovery_context.context_from_manifest(manifest)


def test_context_rejects_a_different_budget_or_seed_schedule(captured):
    protocol, _, manifest = captured
    context = recovery_context.context_from_manifest(manifest)
    different = EvaluationProtocol((ID,), 3, "development", random_seeds=(), strategies=("enumerative",))
    with pytest.raises(ValueError, match="frozen experiment plan"):
        recovery_context.validate_context(context, different)
    different = EvaluationProtocol((ID,), 2, "development", random_seeds=(4,), strategies=("random",))
    with pytest.raises(ValueError, match="frozen experiment plan"):
        recovery_context.validate_context(context, different)


def test_context_rejects_subclass_protocol(captured):
    _, _, manifest = captured
    class DerivedProtocol(EvaluationProtocol):
        pass
    protocol = DerivedProtocol((ID,), 2, "development", random_seeds=(), strategies=("enumerative",))
    with pytest.raises(ValueError, match="canonical"):
        recovery_context.validate_context(recovery_context.context_from_manifest(manifest), protocol)
