"""Local trust and bounded filesystem handling, not an execution sandbox.

Checks detect observable races. They neither lock hostile writers out nor provide
an atomic filesystem snapshot. Product execution requires explicit trust.
"""

from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import stat

from firmavex.product.file_state import handle_state, path_state
from .api import Request

JSON_BYTES = 64 * 1024 * 1024
PROJECT_BYTES = 1024 * 1024
EXPORT_BYTES = 128 * 1024 * 1024
EXPORT_FILES = 256
TRUST_MODES = frozenset({"trusted_example", "trusted_project"})


def checked_path(path, *, directory=False, exists=True):
    """Reject special files, symlinks, traversal spelling, and control characters."""
    path = Path(path).expanduser()
    if ".." in path.parts or any(ord(c) < 32 for c in str(path)):
        raise ValueError("Unsafe path: traversal or control characters")
    path = path.absolute()
    for candidate in reversed((path, *path.parents)):
        try:
            value = candidate.lstat()
        except FileNotFoundError:
            if exists and candidate == path:
                raise
            continue
        if stat.S_ISLNK(value.st_mode) or getattr(value,"st_file_attributes",0) & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400):
            raise ValueError("Symlink/reparse-point paths are unsupported")
        if candidate != path and not stat.S_ISDIR(value.st_mode):
            raise ValueError("Path parent is not a directory")
        if candidate == path and not (
            stat.S_ISDIR(value.st_mode) if directory else (stat.S_ISREG(value.st_mode) and value.st_nlink == 1)
        ):
            raise ValueError("Expected a regular file" if not directory else "Expected a directory")
    return path


def read_bytes(path, maximum):
    """Read a bounded regular file while checking path and handle metadata."""
    path = checked_path(path)
    before = path_state(path)
    if path.stat().st_size > maximum:
        raise ValueError("File exceeds byte limit")
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb", buffering=0) as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Expected a regular file")
        opened = handle_state(stream.fileno())
        data = bytearray()
        while chunk := stream.read(min(1024 * 1024, maximum + 1 - len(data))):
            data.extend(chunk)
            if len(data) > maximum:
                raise ValueError("File exceeds byte limit")
        finished = handle_state(stream.fileno())
        # Windows can defer write/change timestamps while handles remain open.
        # Verify the actual bounded bytes too, including same-size rewrites.
        stream.seek(0)
        offset = 0
        while chunk := stream.read(min(1024 * 1024, maximum + 1 - offset)):
            if chunk != data[offset:offset + len(chunk)]:
                raise ValueError("File changed during capture")
            offset += len(chunk)
            if offset > maximum:
                raise ValueError("File exceeds byte limit")
        if offset != len(data) or handle_state(stream.fileno()) != finished:
            raise ValueError("File changed during capture")
    if not (before == opened == finished == path_state(checked_path(path))):
        raise ValueError("File changed during capture")
    return bytes(data)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def read_json(path, maximum=JSON_BYTES):
    def nonfinite(value):
        raise ValueError("Non-finite JSON value")

    try:
        record = json.loads(read_bytes(path, maximum).decode("utf-8"),
                            object_pairs_hook=_object, parse_constant=nonfinite)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds supported limits") from exc
    pending = [(record, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 128 or nodes > 2_000_000:
            raise ValueError("JSON nesting or record count exceeds supported limits")
        if type(value) is dict:
            pending.extend((child, depth + 1) for child in value.values())
        elif type(value) is list:
            pending.extend((child, depth + 1) for child in value)
    return record


def fresh_directory(path):
    path = checked_path(path, directory=True, exists=False)
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return checked_path(path, directory=True)


def artifact_name(name):
    if (type(name) is not str or not name or name in {".", ".."}
            or "/" in name or "\\" in name or ":" in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError("Unsafe artifact name")
    return name


def _arm_config(source):
    from firmavex.product.config import ProductConfig
    source = checked_path(source)
    record = read_json(source, PROJECT_BYTES)
    # Validate the spelling before ProductConfig resolves relative image paths.
    if type(record) is not dict or type(record.get("firmware")) is not str:
        raise ValueError("Invalid ARM project")
    image = checked_path(source.parent / Path(record["firmware"]).expanduser())
    config = ProductConfig.from_dict(record, base_dir=source.parent)
    if config.firmware != image:
        raise ValueError("ARM firmware path changed")
    return config


def validate_trust(request, trust):
    if type(trust) is not str or trust not in TRUST_MODES:
        raise ValueError("Untrusted workloads are rejected: select a verified example or explicitly trust this project")
    checked_path(request.source)
    if request.profile == "cortex-m3-mps2":
        config = _arm_config(request.source)
        if trust == "trusted_example":
            from firmavex.product.example import example_configuration
            manifest = json.loads(files("firmavex.product").joinpath("resources/example/image.json").read_text())
            expected = example_configuration()
            actual = config.to_dict()
            actual["firmware"] = expected["firmware"]
            if actual != expected:
                raise ValueError("Trusted example configuration differs from the package example")
            if hashlib.sha256(read_bytes(config.firmware, request.limits.artifact_bytes)).hexdigest() != manifest["image_sha256"]:
                raise ValueError("Trusted ARM image does not match the package example")
    elif trust == "trusted_example" and request.profile == "riscv32-virt":
        from .bundled import validate_builtin_riscv
        validate_builtin_riscv(request.source)
    elif trust == "trusted_example":
        expected = files("firmavex.backends").joinpath("examples/counter.v").read_bytes()
        if read_bytes(request.source, request.limits.artifact_bytes) != expected:
            raise ValueError("Trusted HDL source does not match the package example")


def prepare_trusted_request(request, output, trust):
    """Snapshot and revalidate before dispatch; never trust a supplied build marker."""
    if request.profile == "cortex-m3-mps2":
        config = _arm_config(request.source)
        image = output / "input.elf"
        image.write_bytes(read_bytes(config.firmware, request.limits.artifact_bytes))
        source = output / "input-project.json"
        source.write_text(json.dumps(replace(config, firmware=image).to_dict(), sort_keys=True), encoding="utf-8")
    else:
        source = output / ("input.elf" if request.profile == "riscv32-virt" else "input.v")
        source.write_bytes(read_bytes(request.source, request.limits.artifact_bytes))
    snapshot = replace(request, source=source)
    validate_trust(snapshot, trust)
    return snapshot
