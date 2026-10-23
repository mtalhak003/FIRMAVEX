"""Local trust and bounded filesystem handling, not an execution sandbox.

Checks detect observable races. They neither lock hostile writers out nor provide
an atomic filesystem snapshot. Product execution requires explicit trust.
"""

from contextlib import contextmanager
from contextvars import ContextVar
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


_read_budget = ContextVar('firmavex_read_budget', default=None)


@contextmanager
def bounded_reads(maximum, *, calls=1024, cancel_event=None):
    """Optional aggregate byte/read budget, including consistency rereads."""
    if type(maximum) is not int or maximum <= 0 or type(calls) is not int or calls <= 0:
        raise ValueError('Invalid aggregate read budget')
    if _read_budget.get() is not None:
        raise ValueError('Nested read budgets are unsupported')
    budget = {'remaining': maximum, 'consumed': 0, 'calls': 0}
    token = _read_budget.set((budget, calls, cancel_event))
    try:
        yield budget
    finally:
        _read_budget.reset(token)


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


# Leave space for the fixed native input/script/artifact basenames. Python can
# retain evidence at longer paths, but CreateProcessW's cwd cannot use them.
_NATIVE_DIRECTORY_UNITS = 240
_WINDOWS = os.name == 'nt'


def _windows_short_directory(path):
    import ctypes
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetShortPathNameW
    api.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    api.restype = ctypes.c_uint32
    size = api(str(path), None, 0)
    if not 0 < size <= 32768:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(size)
    count = api(str(path), buffer, size)
    if not 0 < count < size:
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def native_directory(path):
    """Use an existing same-directory Windows alias; never create a link/copy.

    Native tools receive this spelling before their paths are constructed. All
    evidence remains in the original owned directory. Unsupported volumes fail
    closed with guidance; they do not receive weaker process admission.
    """
    path = checked_path(path, directory=True)
    units = lambda value: len(str(value).encode('utf-16-le')) // 2
    if not _WINDOWS or units(path) <= _NATIVE_DIRECTORY_UNITS:
        return path
    message = ('Native Windows execution path is too long. Use a shorter project/data directory; '
               'this volume must provide a short path to the same directory.')
    try:
        alias = Path(_windows_short_directory(path))
        if not alias.is_absolute():
            raise ValueError(message)
        alias = checked_path(alias, directory=True)
        if units(alias) > _NATIVE_DIRECTORY_UNITS or not os.path.samefile(path, alias):
            raise ValueError(message)
        # Reject any observable link/reparse-point substitution in either spelling.
        checked_path(path, directory=True)
        checked_path(alias, directory=True)
        return alias
    except (OSError, ValueError) as error:
        raise ValueError(message) from error


def read_bytes(path, maximum, *, cancel_event=None):
    """Read a bounded regular file while checking path and handle metadata."""
    budget_context = _read_budget.get()
    budget = budget_context[0] if budget_context else None
    if budget is not None:
        if cancel_event is None:
            cancel_event = budget_context[2]
        budget['calls'] += 1
        if budget['calls'] > budget_context[1]:
            raise ValueError('Aggregate read count exceeded')
        maximum = min(maximum, budget['remaining'] // 2)

    def read(stream, count):
        if budget is None:
            return stream.read(count)
        if budget['remaining'] <= 0:
            raise ValueError('Aggregate read byte limit exceeded')
        chunk = stream.read(min(count, budget['remaining']))
        budget['remaining'] -= len(chunk)
        budget['consumed'] += len(chunk)
        return chunk

    path = checked_path(path)
    from firmavex.product.verification import check_cancel
    check_cancel(cancel_event)
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
        while chunk := read(stream, min(1024 * 1024, maximum + 1 - len(data))):
            check_cancel(cancel_event)
            data.extend(chunk)
            if len(data) > maximum:
                raise ValueError("File exceeds byte limit")
        finished = handle_state(stream.fileno())
        # Windows can defer write/change timestamps while handles remain open.
        # Verify the actual bounded bytes too, including same-size rewrites.
        stream.seek(0)
        offset = 0
        while chunk := read(stream, min(1024 * 1024, maximum + 1 - offset)):
            check_cancel(cancel_event)
            if chunk != data[offset:offset + len(chunk)]:
                raise ValueError("File changed during capture")
            offset += len(chunk)
            if offset > maximum:
                raise ValueError("File exceeds byte limit")
        if offset != len(data) or handle_state(stream.fileno()) != finished:
            raise ValueError("File changed during capture")
    if not (before == opened == finished == path_state(checked_path(path))):
        raise ValueError("File changed during capture")
    check_cancel(cancel_event)
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
