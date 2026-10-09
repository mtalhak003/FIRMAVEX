"""Stable administrative evidence for experiment-boundary recovery.

This projection is intentionally stricter than a portable research artifact:
absolute paths, selected tool versions and host information must match on
recovery. Volatile capture timestamps and filesystem stat fields are omitted.
Capture still uses Step 18B's observed-consistency checks; the projection is
neither an atomic snapshot nor an attestation of supplied build metadata.
"""

import hashlib
import json
from pathlib import Path

from src.firmavex.protocols.journal import fingerprint
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.provenance import TOOLS, capture_campaign_manifest


_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_CONSISTENCY = {"status": "stable_observed", "atomic": False}
_STAT_KEYS = {"dev", "ino", "mode", "size", "mtime_ns", "ctime_ns"}


def _keys(value, expected, name):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(f"{name} has an invalid recovery context shape.")


def _string(value, name, *, empty=False):
    if type(value) is not str or (not empty and not value.strip()):
        raise ValueError(f"{name} must be a string{' (possibly empty)' if empty else ' with a value'}.")


def _digest(value, name, *, git=False):
    lengths = (40, 64) if git else (64,)
    if type(value) is not str or len(value) not in lengths or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be a lowercase hexadecimal digest.")


def _json_copy(value):
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Recovery metadata keys must be strings.")
        return {key: _json_copy(item) for key, item in value.items()}
    if type(value) is list:
        return [_json_copy(item) for item in value]
    if type(value) not in (str, int, float, bool, type(None)):
        raise ValueError("Recovery metadata must contain exact JSON values.")
    try:
        json.dumps(value, allow_nan=False)
    except ValueError as exc:
        raise ValueError("Recovery metadata must contain finite JSON values.") from exc
    return value


def _consistency(value, name):
    _keys(value, _CONSISTENCY, name)
    if value["status"] != "stable_observed" or type(value["atomic"]) is not bool or value["atomic"]:
        raise ValueError(f"{name} requires stable observed, non-atomic capture evidence.")


def _artifact(value, name):
    _keys(value, ("path", "requested_path", "size_bytes", "sha256"), name)
    for field in ("path", "requested_path"):
        _string(value[field], f"{name}.{field}")
        if not Path(value[field]).is_absolute():
            raise ValueError(f"{name}.{field} must retain the captured absolute path.")
    if type(value["size_bytes"]) is not int or value["size_bytes"] < 0:
        raise ValueError(f"{name}.size_bytes must be a nonnegative integer.")
    _digest(value["sha256"], f"{name}.sha256")


def _project_artifact(value, name):
    _keys(value, ("path", "requested_path", "size_bytes", "sha256", "identity", "consistency"), name)
    _consistency(value["consistency"], f"{name}.consistency")
    identity = value["identity"]
    _keys(identity, ("requested_path", "resolved_path", "requested_stat", "resolved_stat"), f"{name}.identity")
    if identity["requested_path"] != value["requested_path"] or identity["resolved_path"] != value["path"]:
        raise ValueError(f"{name} path and captured identity disagree.")
    for field in ("requested_stat", "resolved_stat"):
        _keys(identity[field], _STAT_KEYS, f"{name}.identity.{field}")
        if any(type(item) is not int for item in identity[field].values()):
            raise ValueError(f"{name} stat metadata must contain exact integers.")
    if identity["resolved_stat"]["size"] != value["size_bytes"]:
        raise ValueError(f"{name} size and captured identity disagree.")
    projected = {key: value[key] for key in ("path", "requested_path", "size_bytes", "sha256")}
    _artifact(projected, name)
    return projected


def _environment(value):
    _keys(value, ("repository", "git", "tools", "python", "host"), "environment")
    _string(value["repository"], "environment.repository")
    if not Path(value["repository"]).is_absolute():
        raise ValueError("Recovery repository must retain its captured absolute path.")
    git = value["git"]
    _keys(git, ("revision", "dirty", "status_short", "tracked_diff_sha256", "index_diff_sha256", "untracked_files"), "environment.git")
    _digest(git["revision"], "environment.git.revision", git=True)
    _string(git["status_short"], "environment.git.status_short", empty=True)
    if type(git["dirty"]) is not bool or git["dirty"] != bool(git["status_short"].strip()):
        raise ValueError("Recovery Git dirty flag contradicts captured status.")
    for field in ("tracked_diff_sha256", "index_diff_sha256"):
        _digest(git[field], f"environment.git.{field}")
    if type(git["untracked_files"]) is not list:
        raise ValueError("Recovery untracked identities must be an ordered list.")
    paths = []
    for item in git["untracked_files"]:
        _keys(item, ("repository_path", "path", "requested_path", "size_bytes", "sha256"), "untracked artifact")
        _artifact({key: item[key] for key in ("path", "requested_path", "size_bytes", "sha256")}, "untracked artifact")
        _string(item["repository_path"], "untracked repository path")
        if Path(item["repository_path"]).is_absolute() or ".." in Path(item["repository_path"]).parts:
            raise ValueError("Untracked repository paths must remain relative to the captured repository.")
        if str(Path(value["repository"]) / item["repository_path"]) != item["requested_path"]:
            raise ValueError("Untracked requested path contradicts its repository-relative identity.")
        paths.append(item["repository_path"])
    if len(set(paths)) != len(paths):
        raise ValueError("Recovery untracked identities contain duplicate paths.")
    if not git["dirty"] and (paths or git["tracked_diff_sha256"] != _EMPTY_SHA256 or git["index_diff_sha256"] != _EMPTY_SHA256):
        raise ValueError("Clean recovery Git evidence contradicts recorded changes.")
    tools = value["tools"]
    _keys(tools, TOOLS, "environment.tools")
    for name, tool in tools.items():
        required = {"status", "executable", "version", "error"}
        if type(tool) is not dict or set(tool) not in (required, required | {"return_code"}):
            raise ValueError(f"Invalid {name} tool evidence.")
        if tool["status"] not in ("ok", "error", "unavailable") or type(tool["status"]) is not str:
            raise ValueError(f"Unsupported {name} tool status.")
        if "return_code" in tool and type(tool["return_code"]) is not int:
            raise ValueError(f"Invalid {name} return code.")
        if tool["status"] == "ok":
            _string(tool["executable"], f"{name} executable")
            _string(tool["version"], f"{name} version")
            if tool["error"] is not None or "return_code" in tool:
                raise ValueError(f"Successful {name} evidence contradicts its error state.")
        else:
            _string(tool["error"], f"{name} error")
            if tool["version"] is not None:
                raise ValueError(f"Failed {name} evidence must not contain a successful version.")
            if tool["status"] == "unavailable":
                if tool["executable"] is not None or "return_code" in tool:
                    raise ValueError(f"Unavailable {name} evidence contradicts an executable.")
            else:
                _string(tool["executable"], f"{name} executable")
    _keys(value["python"], ("version", "implementation", "executable"), "environment.python")
    for field, item in value["python"].items():
        _string(item, f"environment.python.{field}")
    host = value["host"]
    _keys(host, ("system", "release", "platform", "os_release", "version", "machine", "processor", "cpu_count", "cpu_affinity"), "environment.host")
    for field in ("system", "release", "platform", "version", "machine", "processor"):
        _string(host[field], f"environment.host.{field}", empty=True)
    if host["os_release"] is not None:
        if type(host["os_release"]) is not dict or not set(host["os_release"]).issubset({"NAME", "ID", "VERSION_ID", "PRETTY_NAME"}):
            raise ValueError("Invalid selected operating-system release evidence.")
        for item in host["os_release"].values():
            _string(item, "operating-system release value", empty=True)
    if host["cpu_count"] is not None and (type(host["cpu_count"]) is not int or host["cpu_count"] < 1):
        raise ValueError("Host CPU count must be a positive integer or unavailable.")
    affinity = host["cpu_affinity"]
    if affinity is not None and (type(affinity) is not list or any(type(cpu) is not int or cpu < 0 for cpu in affinity) or affinity != sorted(set(affinity))):
        raise ValueError("Host CPU affinity must be sorted unique CPU indices or unavailable.")


def _validate(context, plan):
    _keys(context, ("schema_version", "kind", "plan_sha256", "consistency", "preset", "environment", "benchmarks"), "recovery context")
    if type(context["schema_version"]) is not int or context["schema_version"] != 1 or context["kind"] != "firmavex_recovery_context":
        raise ValueError("Unsupported recovery context schema.")
    _digest(context["plan_sha256"], "recovery plan digest")
    if context["plan_sha256"] != fingerprint(plan):
        raise ValueError("Recovery context does not match the frozen experiment plan.")
    _consistency(context["consistency"], "recovery context consistency")
    _keys(context["preset"], ("name", "verification"), "preset")
    _string(context["preset"]["name"], "preset name")
    if context["preset"]["verification"] != "administrator_declared_not_verified":
        raise ValueError("Recovery must preserve the declared preset's unverified status.")
    _environment(context["environment"])
    identifiers = plan["protocol"]["benchmark_ids"]
    if type(context["benchmarks"]) is not list or [item.get("benchmark_id") if type(item) is dict else None for item in context["benchmarks"]] != identifiers:
        raise ValueError("Recovery artifacts must cover the frozen ordered benchmark IDs exactly once.")
    for item in context["benchmarks"]:
        _keys(item, ("benchmark_id", "firmware_image", "source_inputs", "build"), "benchmark evidence")
        _artifact(item["firmware_image"], "firmware image")
        if type(item["source_inputs"]) is not list or not item["source_inputs"]:
            raise ValueError("Recovery requires a nonempty source/support identity sequence.")
        for artifact in item["source_inputs"]:
            _artifact(artifact, "source input")
        _keys(item["build"], ("verification", "metadata"), "build evidence")
        if item["build"]["verification"] != "administrator_supplied_not_verified" or type(item["build"]["metadata"]) is not dict or not item["build"]["metadata"]:
            raise ValueError("Recovery requires explicitly supplied, unverified build metadata.")
        _json_copy(item["build"]["metadata"])
    _json_copy(context)


def context_from_manifest(manifest: dict) -> dict:
    """Project a successful Step 18B capture, retaining evidence quality labels.

    A caller-created dictionary is not independently verified by this function;
    use ``capture_recovery_context`` for a fresh capture on every runner call.
    Administrator-supplied source/build relationships remain unverified.
    """
    _keys(manifest, ("schema_version", "kind", "preset", "plan", "started_at_utc", "ended_at_utc", "environment", "benchmarks", "official_campaign_result", "consistency"), "campaign manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["kind"] != "administrator_campaign_provenance_v1":
        raise ValueError("Recovery requires a Step 18B administrator campaign manifest.")
    _consistency(manifest["consistency"], "manifest consistency")
    raw = manifest["environment"]
    _keys(raw, ("captured_at_utc", "repository", "git", "tools", "python", "host", "consistency"), "captured environment")
    _consistency(raw["consistency"], "environment consistency")
    git = _json_copy(raw["git"])
    if type(git.get("untracked_files")) is not list:
        raise ValueError("Captured untracked identities must be an ordered list.")
    projected = []
    for item in git["untracked_files"]:
        if type(item) is not dict or "repository_path" not in item:
            raise ValueError("Captured untracked identity requires its repository-relative path.")
        projected.append({"repository_path": item["repository_path"], **_project_artifact({key: value for key, value in item.items() if key != "repository_path"}, "untracked artifact")})
    git["untracked_files"] = projected
    environment = {key: _json_copy(raw[key]) for key in ("repository", "tools", "python", "host")}
    environment["git"] = git
    if type(manifest["benchmarks"]) is not list:
        raise ValueError("Captured benchmark evidence must be an ordered list.")
    benchmarks = []
    for item in manifest["benchmarks"]:
        _keys(item, ("benchmark_id", "firmware_image", "source_inputs", "build"), "captured benchmark evidence")
        if type(item["source_inputs"]) is not list:
            raise ValueError("Captured source inputs must be an ordered list.")
        benchmarks.append({
            "benchmark_id": item["benchmark_id"],
            "firmware_image": _project_artifact(item["firmware_image"], "firmware image"),
            "source_inputs": [_project_artifact(artifact, "source input") for artifact in item["source_inputs"]],
            "build": _json_copy(item["build"]),
        })
    context = {
        "schema_version": 1, "kind": "firmavex_recovery_context",
        "plan_sha256": fingerprint(manifest["plan"]), "consistency": dict(_CONSISTENCY),
        "preset": _json_copy(manifest["preset"]), "environment": environment,
        "benchmarks": benchmarks,
    }
    _validate(context, manifest["plan"])
    return context


def capture_recovery_context(protocol: EvaluationProtocol, **manifest_kwargs) -> dict:
    """Recapture actual Git/file/tool evidence via unchanged Step 18B helpers."""
    context = context_from_manifest(capture_campaign_manifest(protocol, **manifest_kwargs))
    validate_context(context, protocol)
    return context


def validate_context(context: dict, protocol: EvaluationProtocol) -> None:
    """Validate exact administrative record shapes against a canonical plan."""
    if type(protocol) is not EvaluationProtocol:
        raise ValueError("Recovery context requires the canonical EvaluationProtocol.")
    _validate(context, protocol.plan_to_dict())
