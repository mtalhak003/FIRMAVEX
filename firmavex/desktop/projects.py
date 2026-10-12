"""Qt-free, user-owned desktop projects; no firmware execution on import.

Imported images and saved configuration records are immutable. Observable
identity checks detect inconsistent reads; they do not lock external files or
provide an atomic filesystem snapshot.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import sysconfig
import uuid

from firmavex.product.config import ProductConfig
from firmavex.product.errors import ProductError
from firmavex.product.file_state import path_state, handle_state
from firmavex.product.firmware import MAX_IMAGE_BYTES, inspect_elf


MARKER = "desktop-project.json"
SCHEMA_VERSION = 1
_RECORD = re.compile(r"([0-9]{6})-([a-f0-9]{64})\.json\Z")
_KIND = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


def application_data_directory() -> Path:
    """Return the platform's per-user FIRMAVEX directory, without creating it."""
    if sys.platform == "win32":
        parent = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        parent = Path.home() / "Library" / "Application Support"
    else:
        value = os.environ.get("XDG_DATA_HOME")
        parent = Path(value) if value and Path(value).is_absolute() else Path.home() / ".local" / "share"
    return parent / "FIRMAVEX"


def _fail(message: str, category: str = "desktop_project_error") -> None:
    raise ProductError(category, message)


def _safe_root(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_symlink():
        _fail("Project directories must not be symbolic links.")
    resolved = path.resolve()
    protected = {Path(__file__).resolve().parents[2], Path(sys.prefix).resolve()}
    protected.update(Path(value).resolve() for key in ("purelib", "platlib")
                     if (value := sysconfig.get_path(key)))
    for directory in protected:
        if resolved == directory or directory in resolved.parents or resolved in directory.parents:
            _fail("Projects must be outside the installed application and source checkout.")
    return resolved


def _regular(path: Path) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError as exc:
        _fail(f"Cannot access project file {path.name}: {exc}")
    if not stat.S_ISREG(value.st_mode):
        _fail(f"Project file {path.name} must be a regular file, not a link.")
    return value


def _read(path: Path, *, maximum: int = 1024 * 1024) -> bytes:
    before = _regular(path)
    initial = path_state(path, before)
    if not 0 < before.st_size <= maximum:
        _fail(f"Project file {path.name} has an invalid size.")
    try:
        with path.open("rb") as stream:
            opened = handle_state(stream.fileno())
            data = stream.read(maximum + 1)
            finished = handle_state(stream.fileno())
        after = _regular(path)
    except OSError as exc:
        _fail(f"Cannot read project file {path.name}: {exc}")
    if len(data) > maximum or not (initial == opened == finished == path_state(path, after)):
        _fail(f"Project file {path.name} changed while being read.", "artifact_changed")
    return data


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _object(data: bytes) -> dict:
    try:
        result = json.loads(data, object_pairs_hook=_pairs,
                            parse_constant=lambda value: _fail(f"Non-finite JSON value: {value}."))
    except (ValueError, UnicodeError) as exc:
        _fail(f"Invalid project JSON: {exc}")
    if type(result) is not dict:
        _fail("Project metadata must be a JSON object.")
    return result


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exclusive_write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


@contextmanager
def _write_lock(root: Path):
    lock = root / ".project.lock"
    _regular(lock)
    with lock.open("r+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ProductError("project_busy", "Another process is saving this project.") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ProductError("project_busy", "Another process is saving this project.") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class DesktopProject:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", _safe_root(self.root))

    @property
    def config_path(self) -> Path:
        return self.root / "project.json"

    @property
    def firmware_path(self) -> Path:
        return self.root / "firmware.elf"

    @classmethod
    def create(cls, root: str | Path, firmware: str | Path,
               config: ProductConfig) -> "DesktopProject":
        root = _safe_root(root)
        source = Path(firmware).expanduser().absolute()
        _regular(source)
        if type(config) is not ProductConfig or source.resolve() != config.firmware:
            _fail("The configuration must describe the firmware selected for import.")
        validated = inspect_elf(config)
        try:
            root.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ProductError("desktop_project_error", "Choose a new, nonexistent project directory.") from exc
        project = cls(root)
        # Only this newly created directory is cleaned if import fails.
        try:
            before = _regular(source)
            initial = path_state(source, before)
            digest = hashlib.sha256()
            total = 0
            with source.open("rb") as incoming, project.firmware_path.open("xb") as outgoing:
                opened = handle_state(incoming.fileno())
                while chunk := incoming.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        _fail("Firmware grew beyond the import limit.", "artifact_changed")
                    outgoing.write(chunk)
                    digest.update(chunk)
                finished = handle_state(incoming.fileno())
                outgoing.flush()
                os.fsync(outgoing.fileno())
            after = _regular(source)
            if (not (initial == opened == finished == path_state(source, after)) or digest.hexdigest() != validated["firmware_sha256"]):
                _fail("Firmware changed during import.", "artifact_changed")
            imported = replace(config, firmware=project.firmware_path)
            imported_identity = inspect_elf(imported)
            if imported_identity["firmware_sha256"] != digest.hexdigest():
                _fail("Imported firmware identity does not match its source.", "artifact_changed")
            (root / "configurations").mkdir()
            (root / "runs").mkdir()
            _exclusive_write(root / ".project.lock", b"0")
            _exclusive_write(root / MARKER, _encoded({
                "kind": "firmavex_desktop_project", "schema_version": SCHEMA_VERSION,
                "project_id": uuid.uuid4().hex,
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "firmware": {"file": "firmware.elf", "sha256": digest.hexdigest(),
                             "size_bytes": total},
                "source_firmware": str(source.resolve()),
                "consistency": {"atomic": False, "status": "stable_observed"},
            }))
            project.save_config(imported)
        except BaseException as exc:
            try:
                shutil.rmtree(root)
            except BaseException as cleanup:
                exc.add_note(f"New-project cleanup also failed: {cleanup}")
            raise
        return project

    @classmethod
    def open(cls, root: str | Path) -> "DesktopProject":
        project = cls(_safe_root(root))
        project.load_config()
        return project

    def _identity(self) -> dict:
        if self.root.is_symlink() or not self.root.is_dir():
            _fail("Project directory is missing or is a symbolic link.")
        marker = _object(_read(self.root / MARKER))
        firmware = marker.get("firmware")
        if (marker.get("kind") != "firmavex_desktop_project"
                or type(marker.get("schema_version")) is not int
                or marker["schema_version"] != SCHEMA_VERSION
                or type(firmware) is not dict
                or firmware.get("file") != "firmware.elf"
                or type(firmware.get("sha256")) is not str
                or re.fullmatch(r"[a-f0-9]{64}", firmware["sha256"]) is None
                or type(firmware.get("size_bytes")) is not int):
            _fail("Unsupported or inconsistent desktop-project marker.")
        data = _read(self.firmware_path, maximum=MAX_IMAGE_BYTES)
        if len(data) != firmware["size_bytes"] or hashlib.sha256(data).hexdigest() != firmware["sha256"]:
            _fail("Imported firmware changed; create a new project to import another image.", "artifact_changed")
        for name in ("configurations", "runs"):
            directory = self.root / name
            if directory.is_symlink() or not directory.is_dir():
                _fail(f"Project directory {name} is missing or is a symbolic link.")
        return marker

    def _history(self) -> list[tuple[Path, int, str, bytes]]:
        records = []
        numbers = set()
        for path in (self.root / "configurations").iterdir():
            match = _RECORD.fullmatch(path.name)
            if match is None:
                _fail("Unexpected file in immutable configuration history.")
            data = _read(path)
            if hashlib.sha256(data).hexdigest() != match[2]:
                _fail("An immutable configuration record changed.", "artifact_changed")
            number = int(match[1])
            if number == 0 or number in numbers:
                _fail("Configuration history contains an invalid or repeated version.")
            numbers.add(number)
            records.append((path, number, match[2], data))
        return records

    def load_config(self) -> ProductConfig:
        self._identity()
        active = _read(self.config_path)
        value = _object(active)
        if value.get("firmware") != "firmware.elf":
            _fail("The active configuration must use the project's imported firmware.")
        digest = hashlib.sha256(active).hexdigest()
        if not any(saved_digest == digest and saved == active
                   for _, _, saved_digest, saved in self._history()):
            _fail("The active configuration has no matching immutable saved record.")
        config = ProductConfig.from_dict(value, base_dir=self.root)
        result = inspect_elf(config)
        if result["firmware_sha256"] != self._identity()["firmware"]["sha256"]:
            _fail("Firmware changed during project validation.", "artifact_changed")
        return config

    def save_config(self, config: ProductConfig) -> Path:
        if type(config) is not ProductConfig or config.firmware != self.firmware_path.resolve():
            _fail("Saved configurations must use the project's imported firmware.")
        with _write_lock(self.root):
            marker = self._identity()
            identity = inspect_elf(config)
            if identity["firmware_sha256"] != marker["firmware"]["sha256"]:
                _fail("Firmware changed while saving configuration.", "artifact_changed")
            value = config.to_dict()
            value["firmware"] = "firmware.elf"
            data = _encoded(value)
            existing = [number for _, number, _, _ in self._history()]
            number = max(existing, default=0) + 1
            if number > 999999:
                _fail("Configuration history is full.")
            record = self.root / "configurations" / f"{number:06d}-{hashlib.sha256(data).hexdigest()}.json"
            _exclusive_write(record, data)
            temporary = self.root / f".project-{uuid.uuid4().hex}.tmp"
            try:
                _exclusive_write(temporary, data)
                if self.config_path.exists() or self.config_path.is_symlink():
                    _regular(self.config_path)
                self._identity()
                os.replace(temporary, self.config_path)
                _sync_directory(self.root)
            finally:
                temporary.unlink(missing_ok=True)
            return record

    def new_run_directory(self, kind: str = "run") -> Path:
        """Return a fresh nonexistent run destination; the engine creates it."""
        if type(kind) is not str or _KIND.fullmatch(kind) is None:
            _fail("Run directory kind must be a short lowercase identifier.")
        self.load_config()
        return self.root / "runs" / f"{kind}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex}"

    def command_config(self, saved_record: Path) -> Path:
        """Freeze one saved version for dispatch, independent of active edits."""
        with _write_lock(self.root):
            self._identity()
            record = Path(saved_record)
            match = _RECORD.fullmatch(record.name)
            if record.parent != self.root / "configurations" or match is None:
                _fail("A command must reference this project's immutable configuration history.")
            data = _read(record)
            if hashlib.sha256(data).hexdigest() != match[2]:
                _fail("Saved configuration changed before command admission.", "artifact_changed")
            config = ProductConfig.from_dict(_object(data), base_dir=self.root)
            if config.firmware != self.firmware_path.resolve():
                _fail("Command configuration must use the imported project image.")
            directory = self.root / "commands"
            directory.mkdir(exist_ok=True)
            if directory.is_symlink() or not directory.is_dir():
                _fail("Command configuration directory must be owned and cannot be a link.")
            destination = directory / f"{uuid.uuid4().hex}.json"
            _exclusive_write(destination, _encoded(config.to_dict()))
            return destination
