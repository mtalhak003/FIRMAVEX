"""Offline, checksum-pinned runtime packs. Integrity is not publisher authentication.

No vendor download or firmware qualification is inferred from a successful import.
Installed generations are immutable; repairs activate a new verified generation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import sys
import uuid
import zipfile

from .errors import ProductError
from .tools import file_identity

MAX_BYTES = 2 * 1024**3
MAX_FILES = 20000
HEX = re.compile(r"[0-9a-f]{64}\Z")


def runtime_root() -> Path:
    from firmavex.desktop.projects import application_data_directory
    return application_data_directory() / "runtimes"


def host() -> dict:
    machine = platform.machine().lower()
    return {"os": {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform),
            "arch": {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)}


def fail(message):
    raise ProductError("runtime_pack_invalid", message)


def safe_name(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        fail("Runtime member has an unsafe path.")
    parts = name.split("/")
    if any(part in {"", ".", ".."} or part.endswith((".", " ")) for part in parts):
        fail("Runtime member has an unsafe path.")
    if any(part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))} for part in parts):
        fail("Runtime member uses a reserved name.")
    if PurePosixPath(name).is_absolute():
        fail("Runtime member must be relative.")
    return name


def manifest(data):
    if not isinstance(data, dict) or set(data) != {"schema_version", "id", "host", "tools", "files", "licenses", "source_offer"}:
        fail("Runtime manifest fields do not match schema 1.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        fail("Unsupported runtime manifest version.")
    if not isinstance(data["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", data["id"]):
        fail("Invalid runtime identifier.")
    if data["host"] != host():
        fail("Runtime pack OS/architecture does not match this host.")
    files = data["files"]
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        fail("Runtime file inventory is empty or too large.")
    seen = set()
    for name, digest in files.items():
        safe_name(name)
        if name.casefold() in seen or name == "runtime.json":
            fail("Duplicate or reserved runtime member.")
        seen.add(name.casefold())
        if not isinstance(digest, str) or not HEX.fullmatch(digest):
            fail("Invalid runtime file checksum.")
    tools = data["tools"]
    if not isinstance(tools, dict) or not {"qemu", "gdb"} <= set(tools) <= {"qemu", "gdb", "compiler"}:
        fail("Runtime pack needs QEMU and GDB paths.")
    if any(not isinstance(name, str) or name not in files for name in tools.values()):
        fail("Runtime tool is absent from the file inventory.")
    if not isinstance(data["licenses"], list) or not data["licenses"] or any(not isinstance(name, str) or name not in files for name in data["licenses"]):
        fail("Runtime pack needs inventoried license notices.")
    if not isinstance(data["source_offer"], str) or not data["source_offer"].strip():
        fail("Runtime pack needs corresponding-source distribution information.")
    return data


def verify(directory: Path) -> dict:
    if directory.is_symlink():
        fail("Runtime directory cannot be a symlink.")
    inventory = {}
    for path in directory.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            fail("Runtime contains a link or special file.")
        if path.is_file():
            inventory[path.relative_to(directory).as_posix()] = path
    if "runtime.json" not in inventory or inventory["runtime.json"].stat().st_size > 4 * 1024**2:
        fail("Missing or oversized runtime manifest.")
    data = manifest(json.loads(inventory["runtime.json"].read_text(encoding="utf-8")))
    if set(inventory) != set(data["files"]) | {"runtime.json"}:
        fail("Runtime file inventory does not match installation.")
    for name, expected in data["files"].items():
        if file_identity(inventory[name])["sha256"] != expected:
            fail(f"Runtime checksum mismatch: {name}")
    return data


def active_tools(root: Path | None = None) -> dict:
    root = Path(root) if root is not None else runtime_root()
    pointer = root / "active.json"
    if not pointer.exists():
        return {}
    if pointer.is_symlink():
        fail("Runtime pointer cannot be a symlink.")
    data = json.loads(pointer.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"generation", "manifest_sha256"} or not isinstance(data["generation"], str) or not re.fullmatch(r"[a-f0-9]{32}", data["generation"]):
        fail("Invalid active runtime pointer.")
    directory = root / data["generation"]
    if not isinstance(data["manifest_sha256"], str) or not HEX.fullmatch(data["manifest_sha256"]) or file_identity(directory / "runtime.json")["sha256"] != data["manifest_sha256"]:
        fail("Installed runtime manifest differs from the activated identity.")
    verified = verify(directory)
    return {name: str(directory / relative) for name, relative in verified["tools"].items()}


def install(archive: Path, expected_sha256: str, *, root: Path | None = None) -> dict:
    """Trust the separately obtained checksum, not the ZIP's own claims.

    Capability probes execute pack binaries only AFTER checksum verification.
    The user must trust the publisher before installing executable code.
    """
    if not isinstance(expected_sha256, str) or not HEX.fullmatch(expected_sha256):
        fail("Supply an independently obtained lowercase SHA-256 checksum.")
    archive = Path(archive)
    if archive.stat().st_size > MAX_BYTES or file_identity(archive)["sha256"] != expected_sha256:
        fail("Runtime archive checksum mismatch or excessive size.")
    root = Path(root) if root is not None else runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        fail("Runtime root cannot be a symlink.")
    lock = root / "install.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        fail("Another runtime installation owns the lock; do not repair while an install is active.")
    generation = uuid.uuid4().hex
    directory = root / generation
    temporary = root / f"pointer-{generation}.tmp"
    activated = False
    try:
        directory.mkdir()
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
            if not 1 <= len(members) <= MAX_FILES + 1 or sum(item.file_size for item in members) > MAX_BYTES:
                fail("Runtime archive exceeds extraction limits.")
            seen = set()
            for item in members:
                name = safe_name(item.filename)
                mode = item.external_attr >> 16
                if name.casefold() in seen or item.is_dir() or stat.S_IFMT(mode) not in {0, stat.S_IFREG} or item.flag_bits & 1:
                    fail("Runtime archive contains duplicate, encrypted, or nonregular members.")
                seen.add(name.casefold())
                destination = directory / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
                destination.chmod(0o755 if mode & 0o111 else 0o644)
        if file_identity(archive)["sha256"] != expected_sha256:
            fail("Runtime archive changed during installation.")
        data = verify(directory)
        from types import SimpleNamespace
        from .tools import discover
        selected = {key: str(directory / value) for key, value in data["tools"].items()}
        tools = discover(SimpleNamespace(**selected), _managed=False)
        # Probes may alter files: never activate a generation that no longer matches.
        if verify(directory) != data:
            fail("Runtime manifest changed during capability probes.")
        temporary.write_text(json.dumps({"generation": generation, "manifest_sha256": file_identity(directory / "runtime.json")["sha256"]}, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, root / "active.json")
        activated = True
        return {"installed": True, "generation": generation, "pack_id": data["id"],
                "archive_sha256": expected_sha256, "tools": tools.to_dict(),
                "firmware_qualification": "not_established_by_installation"}
    finally:
        original = sys.exception()
        try:
            temporary.unlink(missing_ok=True)
            if not activated:
                shutil.rmtree(directory, ignore_errors=True)
            lock.rmdir()
        except BaseException as cleanup:
            if original is None:
                raise
            original.add_note(f"Runtime installation cleanup failed: {cleanup!r}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install a trusted offline runtime pack; never execute guest firmware.")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("install")
    setup.add_argument("archive", type=Path)
    setup.add_argument("--sha256", required=True)
    sub.add_parser("verify")
    args = parser.parse_args(argv)
    try:
        result = install(args.archive, args.sha256) if args.command == "install" else {"tools": active_tools()}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ProductError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
