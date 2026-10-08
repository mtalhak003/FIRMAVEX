"""Opt-in administrator provenance sidecars, separate from official records.

Snapshots record evidence, not an attestation that sources produced an image or
that the captured environment remained unchanged during execution. Keep source,
ELF, patch, and original result files separately. Nothing here builds firmware,
dispatches a strategy, changes accounting, or writes a manifest automatically.
"""

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.results import CampaignResult


TOOLS = ("arm-none-eabi-gcc", "qemu-system-arm", "arm-none-eabi-gdb")
PROBE_TIMEOUT_SECONDS = 5


class ProvenanceConsistencyError(ValueError):
    """An observed change prevents a coherent best-effort provenance snapshot."""


def _stat_identity(metadata: os.stat_result) -> dict:
    # atime is deliberately excluded: reading evidence may update it.
    return {name: getattr(metadata, "st_" + name) for name in (
        "dev", "ino", "mode", "size", "mtime_ns", "ctime_ns",
    )}


def _artifact_identity(requested: Path) -> dict:
    resolved = requested.resolve(strict=True)
    requested_stat = requested.lstat()
    resolved_stat = resolved.stat()
    if not stat.S_ISREG(resolved_stat.st_mode):
        raise ValueError(f"Provenance artifact is not a readable file: {resolved}")
    return {
        "requested_path": str(requested), "resolved_path": str(resolved),
        "requested_stat": _stat_identity(requested_stat),
        "resolved_stat": _stat_identity(resolved_stat),
    }


def _assert_artifact_identity(artifact: dict) -> None:
    try:
        current = _artifact_identity(Path(artifact["requested_path"]))
    except (OSError, ValueError) as exc:
        raise ProvenanceConsistencyError(f"Artifact changed during capture: {artifact['requested_path']}: {exc}") from exc
    if current != artifact["identity"]:
        raise ProvenanceConsistencyError(f"Artifact changed during capture: {artifact['requested_path']}")


def describe_artifact(path: str | Path) -> dict:
    """Hash bytes with descriptor/path identity checks; never return contents.

    Changes observed during hashing, including digest processing, fail closed.
    Equal endpoint observations are best-effort evidence, not an atomic capture
    or protection against adversarial changes and restoration between checks.
    """
    requested = Path(path).absolute()
    try:
        identity = _artifact_identity(requested)
    except OSError as exc:
        raise ValueError(f"Provenance artifact is not a readable file: {requested}: {exc}") from exc
    artifact = Path(identity["resolved_path"])
    try:
        digest = hashlib.sha256()
        size = 0
        with artifact.open("rb") as stream:
            descriptor_before = _stat_identity(os.fstat(stream.fileno()))
            if descriptor_before != identity["resolved_stat"]:
                raise ProvenanceConsistencyError(f"Artifact changed before hashing: {requested}")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
            encoded_digest = digest.hexdigest()
            descriptor_after = _stat_identity(os.fstat(stream.fileno()))
            record = {
                "path": str(artifact), "requested_path": str(requested),
                "size_bytes": size, "sha256": encoded_digest, "identity": identity,
                "consistency": {"status": "stable_observed", "atomic": False},
            }
            _assert_artifact_identity(record)
            descriptor_final = _stat_identity(os.fstat(stream.fileno()))
            if (
                descriptor_before != descriptor_after or descriptor_before != descriptor_final
                or size != descriptor_before["size"]
            ):
                raise ProvenanceConsistencyError(f"Artifact changed during hashing: {requested}")
    except OSError as exc:
        raise ProvenanceConsistencyError(f"Unable to capture stable artifact {requested}: {exc}") from exc
    return record


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True, timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Unable to capture Git provenance: {exc}") from exc
    if completed.returncode != 0:
        diagnostic = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"Unable to capture Git provenance: {diagnostic}")
    return completed.stdout


def _tool_version(name: str) -> dict:
    executable = shutil.which(name)
    if executable is None:
        return {"status": "unavailable", "executable": None, "version": None,
                "error": f"{name} was not found on PATH."}
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "executable": executable, "version": None,
                "error": f"Unable to query {name}: {exc}"}
    version = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 or not version:
        return {"status": "error", "executable": executable, "version": None,
                "error": f"{name} --version returned {completed.returncode}: {completed.stderr.strip()}",
                "return_code": completed.returncode}
    return {"status": "ok", "executable": executable, "version": version, "error": None}


def _repository_root(repository: str | Path) -> Path:
    requested = Path(repository).resolve()
    return Path(os.fsdecode(_git(requested, "rev-parse", "--show-toplevel")).strip()).resolve()


def _git_state(root: Path) -> tuple[bytes, ...]:
    state = (
        _git(root, "rev-parse", "HEAD"),
        _git(root, "status", "--short", "--untracked-files=all"),
        _git(root, "diff", "--binary", "HEAD"),
        _git(root, "diff", "--cached", "--binary", "HEAD"),
        _git(root, "ls-files", "--others", "--exclude-standard", "-z"),
    )
    if not state[1].strip() and any(state[index] for index in (2, 3, 4)):
        raise ProvenanceConsistencyError("Git capture reported clean status with nonempty diff or untracked files.")
    return state


def _git_snapshot(root: Path) -> dict:
    before = _git_state(root)
    artifacts = [
        {"repository_path": os.fsdecode(name), **describe_artifact(root / os.fsdecode(name))}
        for name in before[4].split(b"\0") if name
    ]
    after = _git_state(root)
    if before != after:
        raise ProvenanceConsistencyError("Git state changed during provenance capture.")
    for artifact in artifacts:
        _assert_artifact_identity(artifact)
    return {
        "revision": before[0].decode().strip(),
        "status_short": before[1].decode(errors="replace").rstrip("\n"),
        "dirty": bool(before[1].strip()),
        "tracked_diff_sha256": hashlib.sha256(before[2]).hexdigest(),
        "index_diff_sha256": hashlib.sha256(before[3]).hexdigest(),
        "untracked_files": artifacts,
    }


def capture_environment(repository: str | Path) -> dict:
    """Capture real Git/tool/host evidence without reading environment values.

    Tool probe failures are explicit metadata. Git failures fail closed, because
    a missing revision must not be mistaken for a known clean source state.
    Untracked nonignored files are hashed; ignored build/cache files are omitted.
    Matching Git snapshots bracket probes and hashing. Observed changes abort
    capture without retries; matching endpoints do not imply an atomic snapshot.
    """
    root = _repository_root(repository)
    before = _git_snapshot(root)
    try:
        affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    except OSError:
        affinity = None
    try:
        release = platform.freedesktop_os_release()
        os_release = {key: release[key] for key in ("NAME", "ID", "VERSION_ID", "PRETTY_NAME") if key in release}
    except OSError:
        os_release = None
    captured = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repository": str(root),
        "git": before,
        "tools": {name: _tool_version(name) for name in TOOLS},
        "python": {"version": sys.version, "implementation": platform.python_implementation(),
                   "executable": sys.executable},
        "host": {"system": platform.system(), "release": platform.release(),
                 "platform": platform.platform(), "os_release": os_release,
                 "version": platform.version(), "machine": platform.machine(),
                 "processor": platform.processor(), "cpu_count": os.cpu_count(),
                 "cpu_affinity": affinity},
    }
    if _git_snapshot(root) != before:
        raise ProvenanceConsistencyError("Git state or untracked contents changed during environment capture.")
    captured["consistency"] = {"status": "stable_observed", "atomic": False}
    return captured


def _timestamp(value: str, name: str) -> datetime:
    if type(value) is not str:
        raise ValueError(f"{name} must be a timezone-aware UTC timestamp string.")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware UTC timestamp string.") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC timestamp string.")
    return timestamp


def _json_copy(value):
    """Accept JSON data only; avoid coercing keys or embedding arbitrary objects."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Build metadata keys must be strings.")
        return {key: _json_copy(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_json_copy(item) for item in value]
    if type(value) not in (str, int, float, bool, type(None)):
        raise ValueError("Build metadata must contain only JSON-compatible values.")
    try:
        json.dumps(value, allow_nan=False)
    except ValueError as exc:
        raise ValueError("Build metadata must contain only finite JSON values.") from exc
    return value


def _coverage(values: Mapping, identifiers: tuple[str, ...], name: str) -> None:
    if not isinstance(values, Mapping) or set(values) != set(identifiers):
        raise ValueError(f"{name} must cover exactly the protocol benchmark IDs.")


def capture_campaign_manifest(
    protocol: EvaluationProtocol, *, repository: str | Path, preset_name: str,
    firmware_images: Mapping, source_inputs: Mapping, build_metadata: Mapping,
    started_at_utc: str, ended_at_utc: str | None = None,
    campaign_result: CampaignResult | None = None,
) -> dict:
    """Return a fresh administrative sidecar for the exact retained protocol.

    ``preset_name`` and per-benchmark ``build_metadata`` are administrator
    declarations, not verified claims. Sources/support files and ELF images
    are supplied explicitly; this API never inspects private registry state.
    Start/end timestamps must describe the actual campaign, not capture time.
    Optional completed outcomes retain the official serialization unchanged.
    An interrupted campaign can have no completed result in this sidecar.
    Git state, the retained plan, and supplied artifact identities/hashes are
    bracketed across capture; an observed change fails closed without retries.
    This is best-effort consistency evidence, not an atomic snapshot.
    """
    if type(protocol) is not EvaluationProtocol:
        raise ValueError("Provenance requires the canonical EvaluationProtocol.")
    if type(preset_name) is not str or not preset_name.strip():
        raise ValueError("Provenance requires a nonempty administrator-declared preset name.")
    started = _timestamp(started_at_utc, "started_at_utc")
    ended = _timestamp(ended_at_utc, "ended_at_utc") if ended_at_utc is not None else None
    if ended is not None and ended < started:
        raise ValueError("Campaign end must not precede its start.")
    identifiers = protocol.benchmark_ids
    for name, values in (("firmware_images", firmware_images), ("source_inputs", source_inputs),
                         ("build_metadata", build_metadata)):
        _coverage(values, identifiers, name)
    root = _repository_root(repository)
    git_before = _git_snapshot(root)
    plan = protocol.plan_to_dict()
    artifacts = []
    for identifier in identifiers:
        inputs = source_inputs[identifier]
        if type(inputs) not in (tuple, list) or not inputs:
            raise ValueError("Each benchmark requires a nonempty source/support file sequence.")
        if type(build_metadata[identifier]) is not dict or not build_metadata[identifier]:
            raise ValueError("Each benchmark requires explicitly declared build metadata.")
        artifacts.append({
            "benchmark_id": identifier,
            "firmware_image": describe_artifact(firmware_images[identifier]),
            "source_inputs": [describe_artifact(path) for path in inputs],
            "build": {"verification": "administrator_supplied_not_verified",
                      "metadata": _json_copy(build_metadata[identifier])},
        })
    outcome = None
    if campaign_result is not None:
        if type(campaign_result) is not CampaignResult:
            raise ValueError("Completed outcomes require a canonical CampaignResult.")
        if campaign_result.protocol.plan_to_dict() != plan:
            raise ValueError("Campaign outcome plan differs from the captured protocol.")
        # Revalidate identity and exact ordered declarations without recounting
        # executions or manufacturing an outcome for an incomplete campaign.
        CampaignResult(protocol, campaign_result.records)
        if ended is None:
            raise ValueError("Completed campaign provenance requires an end timestamp.")
        outcome = campaign_result.to_dict()
    environment = capture_environment(root)
    all_artifacts = [
        artifact for benchmark in artifacts
        for artifact in [benchmark["firmware_image"], *benchmark["source_inputs"]]
    ]
    for artifact in all_artifacts:
        if describe_artifact(artifact["requested_path"]) != artifact:
            raise ProvenanceConsistencyError(f"Artifact changed across manifest capture: {artifact['requested_path']}")
    git_after = _git_snapshot(root)
    if git_before != environment["git"] or git_before != git_after:
        raise ProvenanceConsistencyError("Git state changed across manifest capture.")
    for artifact in all_artifacts:
        _assert_artifact_identity(artifact)
    if protocol.plan_to_dict() != plan:
        raise ProvenanceConsistencyError("Protocol plan changed across manifest capture.")
    return {
        "schema_version": 1,
        "kind": "administrator_campaign_provenance_v1",
        "preset": {"name": preset_name, "verification": "administrator_declared_not_verified"},
        "plan": plan,
        "started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": ended.isoformat().replace("+00:00", "Z") if ended else None,
        "environment": environment,
        "benchmarks": artifacts,
        "official_campaign_result": outcome,
        "consistency": {"status": "stable_observed", "atomic": False},
    }


def manifest_to_json(manifest: dict) -> str:
    """Stable JSON formatting for a captured sidecar, without persistence."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
