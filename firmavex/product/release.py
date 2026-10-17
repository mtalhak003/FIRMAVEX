"""Offline preview-release identity sidecars, not signing or qualification."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
from firmavex import __version__
import subprocess

from firmavex.backends.security import (
    checked_path,
    fresh_directory,
    read_json,
    artifact_name,
)
from .file_state import handle_state, path_state

MAX_ARTIFACT = 2 * 1024**3


def _identity(path):
    path = checked_path(path)
    before = path_state(path)
    if path.stat().st_size > MAX_ARTIFACT:
        raise ValueError("Release artifact exceeds size limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb", buffering=0) as stream:
        opened = handle_state(stream.fileno())
        hashes, states = [], [opened]
        for _ in range(2):
            stream.seek(0)
            digest, count = hashlib.sha256(), 0
            while chunk := stream.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_ARTIFACT:
                    raise ValueError("Release artifact exceeds size limit")
                digest.update(chunk)
            hashes.append((digest.hexdigest(), count))
            states.append(handle_state(stream.fileno()))
        finished = handle_state(stream.fileno())
    if hashes[0] != hashes[1] or not (
        all(state == before for state in states)
        and finished == before == path_state(checked_path(path))
    ):
        raise ValueError("Release artifact changed during capture")
    return {"sha256": hashes[0][0], "size_bytes": hashes[0][1]}


def _git(repo):
    values = tuple(
        subprocess.check_output(["git", "-C", str(repo), *args], timeout=10)
        for args in (
            ["rev-parse", "HEAD"],
            ["status", "--porcelain=v1", "--untracked-files=all"],
            ["diff", "--binary", "HEAD", "--"],
        )
    )
    return (
        values[0].decode().strip(),
        values[1].decode().strip(),
        hashlib.sha256(values[2]).hexdigest(),
    )


def capture(artifacts, *, repo):
    if not 1 <= len(artifacts) <= 64:
        raise ValueError("Select 1–64 explicit release artifacts")
    paths = [checked_path(path) for path in artifacts]
    names = [artifact_name(path.name) for path in paths]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Duplicate/case-colliding release artifact names")
    initial = _git(repo)
    identities = {path.name: _identity(path) for path in sorted(paths)}
    if sum(value["size_bytes"] for value in identities.values()) > 8 * 1024**3:
        raise ValueError("Release artifact total exceeds limit")
    dependencies = {}
    for name in ("PyInstaller", "PySide6", "shiboken6", "pyelftools"):
        try:
            dist = importlib.metadata.distribution(name)
            dependencies[name] = {
                "version": dist.version,
                "declared_license": dist.metadata.get("License-Expression")
                or dist.metadata.get("License")
                or "not declared",
            }
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = {"version": None, "declared_license": "not installed"}
    if (
        any(_identity(path) != identities[path.name] for path in paths)
        or _git(repo) != initial
    ):
        raise ValueError("Release files or Git state changed during capture")
    return {
        "schema_version": 1,
        "kind": "firmavex_preview_release",
        "channel": "preview",
        "git_revision": initial[0],
        "dirty": bool(initial[1]),
        "tracked_diff_sha256": initial[2],
        "application_version": __version__,
        "host": {
            "system": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "dependencies": dependencies,
        "artifacts": identities,
        "signing": "not_verified",
        "notarization": "not_verified",
        "qualification": "not_established_by_manifest",
        "redistribution": "dependency metadata is not legal clearance; runtimes are not bundled by this tool",
        "consistency": {"status": "stable_observed", "atomic": False},
    }


def verify(manifest, directory):
    record = read_json(manifest, 1024 * 1024)
    if (
        type(record) is not dict
        or type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
        or record.get("kind") != "firmavex_preview_release"
        or record.get("channel") != "preview"
    ):
        raise ValueError("Unsupported release manifest")
    required = {
        "schema_version",
        "kind",
        "channel",
        "git_revision",
        "dirty",
        "tracked_diff_sha256",
        "application_version",
        "host",
        "dependencies",
        "artifacts",
        "signing",
        "notarization",
        "qualification",
        "redistribution",
        "consistency",
    }

    def hex_digest(value, sizes):
        return (
            type(value) is str
            and len(value) in sizes
            and all(c in "0123456789abcdef" for c in value)
        )

    if (
        set(record) != required
        or type(record["dirty"]) is not bool
        or not hex_digest(record["git_revision"], {40, 64})
        or not hex_digest(record["tracked_diff_sha256"], {64})
    ):
        raise ValueError("Invalid release metadata")
    if (
        record["signing"] != "not_verified"
        or record["notarization"] != "not_verified"
        or record["qualification"] != "not_established_by_manifest"
    ):
        raise ValueError(
            "Release verification cannot establish signing or qualification claims"
        )
    if (
        type(record["application_version"]) is not str
        or not 1 <= len(record["application_version"]) <= 128
    ):
        raise ValueError("Invalid application version")
    host = record["host"]
    if (
        type(host) is not dict
        or set(host) != {"system", "architecture", "python"}
        or any(type(v) is not str or not 1 <= len(v) <= 256 for v in host.values())
    ):
        raise ValueError("Invalid release host metadata")
    dependencies = record["dependencies"]
    if type(dependencies) is not dict or set(dependencies) != {
        "PyInstaller",
        "PySide6",
        "shiboken6",
        "pyelftools",
    }:
        raise ValueError("Invalid dependency inventory")
    for item in dependencies.values():
        if (
            type(item) is not dict
            or set(item) != {"version", "declared_license"}
            or (
                item["version"] is not None
                and (
                    type(item["version"]) is not str
                    or not 1 <= len(item["version"]) <= 128
                )
            )
            or type(item["declared_license"]) is not str
            or not 1 <= len(item["declared_license"]) <= 65536
        ):
            raise ValueError("Invalid dependency metadata")
    consistency = record["consistency"]
    if (
        type(consistency) is not dict
        or set(consistency) != {"status", "atomic"}
        or consistency["status"] != "stable_observed"
        or consistency["atomic"] is not False
    ):
        raise ValueError("Unsupported release consistency claim")
    artifacts = record.get("artifacts")
    if type(artifacts) is not dict or not 1 <= len(artifacts) <= 64:
        raise ValueError("Invalid artifact inventory")
    root = checked_path(directory, directory=True)
    seen = set()
    for name, expected in artifacts.items():
        artifact_name(name)
        if name.casefold() in seen:
            raise ValueError("Artifact names collide")
        seen.add(name.casefold())
        if (
            type(expected) is not dict
            or set(expected) != {"sha256", "size_bytes"}
            or type(expected["size_bytes"]) is not int
            or not 0 <= expected["size_bytes"] <= MAX_ARTIFACT
            or type(expected["sha256"]) is not str
            or len(expected["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in expected["sha256"])
        ):
            raise ValueError("Invalid artifact identity")
    if sum(value["size_bytes"] for value in artifacts.values()) > 8 * 1024**3:
        raise ValueError("Release artifact total exceeds limit")
    for name, expected in artifacts.items():
        if _identity(root / name) != expected:
            raise ValueError("Release artifact verification failed: " + name)
    return {
        "verification": "passed",
        "verified_artifacts": len(artifacts),
        "authenticity": "not_established_by_checksums",
        "qualification": "not_established_by_verification",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--artifact", type=Path, action="append", required=True)
    create.add_argument("--repo", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--artifact-dir", type=Path, required=True)
    bundle = sub.add_parser("bundle-create", help="Create preview manifest, SBOM and review sidecars")
    bundle.add_argument("--artifact", type=Path, action="append", required=True)
    bundle.add_argument("--repo", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    bundle_check = sub.add_parser("bundle-verify", help="Verify preview bundle and named artifacts")
    bundle_check.add_argument("--bundle", type=Path, required=True)
    bundle_check.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"bundle-create", "bundle-verify"}:
            from . import release_bundle
            if args.command == "bundle-create":
                result = release_bundle.create(args.artifact, repo=args.repo, output=args.output)
            else:
                result = release_bundle.verify(args.bundle, args.artifact_dir)
        elif args.command == "verify":
            result = verify(args.manifest, args.artifact_dir)
        else:
            result = capture(args.artifact, repo=args.repo)
            output = fresh_directory(args.output)
            (output / "release-manifest.json").write_text(
                json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            (output / "SHA256SUMS").write_text(
                "".join(
                    value["sha256"] + "  " + name + "\n"
                    for name, value in sorted(result["artifacts"].items())
                ),
                encoding="utf-8",
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
