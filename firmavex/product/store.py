"""Owned, append-only product run archives.

Inspection is read-only. Recovery is an explicit administrative operation and
marks an unfinished archive interrupted; it does not resume a strategy or
invent missing evaluator accounting. The database is transactional, but the
database and artifact directory are not one atomic filesystem snapshot.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
from typing import Any

from .errors import ProductError
from .file_state import path_state, handle_state


_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "interrupted"})
_STATES = _TERMINAL_STATES | {"created", "running"}
_RESERVED_NAMES = frozenset({"run.sqlite3", ".writer.lock"})
_SQLITE_BUSY_SECONDS = 5.0


def _error(message: str, exc: BaseException | None = None) -> ProductError:
    details = {"underlying_error": str(exc)} if exc is not None else None
    return ProductError("persistence_error", message, details)


def _validate_json(value: Any) -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise _error("JSON values must be finite")
        return
    if type(value) is list:
        for item in value:
            _validate_json(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise _error("JSON object keys must be strings")
            _validate_json(item)
        return
    raise _error("Archive values must be ordinary JSON-compatible records")


def _encode(value: dict) -> str:
    if type(value) is not dict:
        raise _error("Archive record must be an ordinary dictionary")
    try:
        _validate_json(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (RecursionError, ValueError, TypeError) as exc:
        raise _error("Archive record cannot be serialized", exc) from exc


def _decode(text: str) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON value: {value}")

    def unique_keys(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    try:
        value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_keys)
        _encode(value)
        return value
    except (ValueError, TypeError, RecursionError) as exc:
        raise _error("Archive contains a malformed JSON record", exc) from exc


def _validate_attempt(record: dict) -> None:
    _encode(record)
    vector = record.get("input")
    if type(vector) is not list or not vector or any(type(v) is not int for v in vector):
        raise _error("Attempt must retain a nonempty exact-integer input vector")


def _validate_result(result: dict) -> str:
    _encode(result)
    state = result.get("state")
    if type(state) is not str or state not in _TERMINAL_STATES:
        raise _error("Final result must declare a terminal state")
    if "success" in result:
        success = result["success"]
        if type(success) is not bool:
            raise _error("Final result success must be an exact boolean")
        if success != (state == "completed"):
            raise _error("Final result success contradicts its terminal state")
    if result.get("aborted") is True and state == "completed":
        raise _error("An aborted run cannot be recorded as completed")
    for key in ("attempted_executions", "successful_executions", "infrastructure_failures"):
        if key in result and (type(result[key]) is not int or result[key] < 0):
            raise _error(f"Final result {key} must be a nonnegative exact integer")
    attempted = result.get("attempted_executions")
    successful = result.get("successful_executions")
    failures = result.get("infrastructure_failures")
    if attempted is not None:
        for count in (successful, failures):
            if count is not None and count > attempted:
                raise _error("Final result execution counts are inconsistent")
        if successful is not None and failures is not None and successful + failures > attempted:
            raise _error("Final result execution counts exceed admitted attempts")
    return state


def _read_consistent(source: Path) -> bytes:
    before = source.stat()
    initial = path_state(source, before)
    if not stat.S_ISREG(before.st_mode):
        raise _error("Artifact source must be a regular file")
    with source.open("rb") as handle:
        opened = handle_state(handle.fileno())
        content = handle.read()
        after_read = handle_state(handle.fileno())
    after = source.stat()
    if len(content) != before.st_size or any(
        info != initial for info in (opened, after_read, path_state(source, after))
    ):
        raise _error("Artifact source changed during capture")
    return content


class _WriterLock:
    """Single live writer, with OS release on process exit."""

    def __init__(self, path: Path, *, create: bool) -> None:
        self.file = None
        try:
            if path.is_symlink():
                raise OSError("Writer lock must not be a symbolic link")
            self.file = path.open("x+b" if create else "r+b")
            if create:
                self.file.write(b"0")
                self.file.flush()
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError) as exc:
            if self.file is not None:
                self.file.close()
            raise _error("Run archive has another writer or cannot be owned", exc) from exc

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None


class RunStore:
    """Create a new writable run or inspect an existing run without writes.

    ``create=True`` requires a nonexistent root. Methods that append records
    require ownership. ``recover_interrupted`` is the only public operation
    that opens an existing archive for writing. Closing an unfinished writer
    does not silently turn it into a completed result.
    """

    def __init__(self, root: Path, create: bool = False) -> None:
        self.root = Path(root).absolute()
        self._connection: sqlite3.Connection | None = None
        self._lock: _WriterLock | None = None
        self._writable = create
        try:
            if self.root.is_symlink():
                raise _error("Run root must not be a symbolic link")
            if create:
                self.root.mkdir(parents=True, exist_ok=False)
                self._lock = _WriterLock(self.root / ".writer.lock", create=True)
                self._connection = sqlite3.connect(self.root / "run.sqlite3", timeout=_SQLITE_BUSY_SECONDS, isolation_level=None)
                self._connection.execute("PRAGMA synchronous=FULL")
                self._create_schema()
            else:
                self._open_readonly()
                self.snapshot()
        except BaseException as exc:
            self._close_preserving(exc)
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot open run archive", exc) from exc

    def _open_readonly(self) -> None:
        path = self.root / "run.sqlite3"
        if path.is_symlink() or not path.is_file():
            raise _error("Run database is missing or is a symbolic link")
        self._connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=_SQLITE_BUSY_SECONDS, isolation_level=None)
        self._connection.execute("PRAGMA query_only=ON")

    def _create_schema(self) -> None:
        assert self._connection is not None
        self._connection.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE run (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL CHECK (schema_version = 1),
                state TEXT NOT NULL,
                metadata TEXT,
                result TEXT
            );
            CREATE TABLE events (
                sequence INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE attempts (
                sequence INTEGER PRIMARY KEY,
                record TEXT NOT NULL
            );
            CREATE TABLE artifacts (
                name TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL
            );
            INSERT INTO run VALUES (1, 1, 'created', NULL, NULL);
            COMMIT;
        """)

    def __enter__(self) -> RunStore:
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        self._close_preserving(exception)

    def _close_preserving(self, original: BaseException | None) -> None:
        try:
            self.close()
        except BaseException as cleanup_error:
            if original is not None and not isinstance(original, Exception):
                if hasattr(original, "add_note"):
                    original.add_note(f"Archive cleanup failed: {cleanup_error}")
                return
            raise

    def close(self) -> None:
        try:
            if self._connection is not None:
                self._connection.close()
        finally:
            self._connection = None
            if self._lock is not None:
                self._lock.close()
                self._lock = None

    def _db(self, *, writing: bool = False) -> sqlite3.Connection:
        if self._connection is None:
            raise _error("Run archive is closed")
        if writing and not self._writable:
            raise _error("Inspection is read-only; explicit ownership is required")
        return self._connection

    def _mutate(self, action: Any) -> Any:
        db = self._db(writing=True)
        try:
            db.execute("BEGIN IMMEDIATE")
            result = action(db)
            db.execute("COMMIT")
            return result
        except BaseException as exc:
            self._rollback(db, exc)
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot persist run record", exc) from exc

    @staticmethod
    def _rollback(db: sqlite3.Connection, original: BaseException) -> None:
        try:
            if db.in_transaction:
                db.execute("ROLLBACK")
        except BaseException as rollback_error:
            if not isinstance(original, Exception):
                if hasattr(original, "add_note"):
                    original.add_note(f"Archive rollback failed: {rollback_error}")
                return
            raise _error("Archive transaction rollback failed", rollback_error) from original

    @staticmethod
    def _require_running(db: sqlite3.Connection) -> None:
        row = db.execute("SELECT state FROM run WHERE id=1").fetchone()
        if row is None or row[0] != "running":
            raise _error("Run is not active")

    def initialize(self, metadata: dict) -> None:
        encoded = _encode(metadata)

        def action(db: sqlite3.Connection) -> None:
            state = db.execute("SELECT state FROM run WHERE id=1").fetchone()
            if state is None or state[0] != "created":
                raise _error("Run metadata can only be initialized once")
            db.execute("UPDATE run SET metadata=?, state='running' WHERE id=1", (encoded,))

        self._mutate(action)

    def append_event(self, kind: str, payload: dict) -> int:
        if type(kind) is not str or not kind or len(kind) > 128:
            raise _error("Event kind must be a nonempty string of at most 128 characters")
        encoded = _encode(payload)

        def action(db: sqlite3.Connection) -> int:
            self._require_running(db)
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM events").fetchone()[0]
            db.execute("INSERT INTO events VALUES (?, ?, ?)", (sequence, kind, encoded))
            return sequence

        return self._mutate(action)

    def record_attempt(self, record: dict) -> int:
        _validate_attempt(record)
        encoded = _encode(record)

        def action(db: sqlite3.Connection) -> int:
            self._require_running(db)
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM attempts").fetchone()[0]
            db.execute("INSERT INTO attempts VALUES (?, ?)", (sequence, encoded))
            return sequence

        return self._mutate(action)

    def finish(self, result: dict) -> None:
        state = _validate_result(result)
        encoded = _encode(result)

        def action(db: sqlite3.Connection) -> None:
            self._require_running(db)
            db.execute("UPDATE run SET state=?, result=? WHERE id=1", (state, encoded))

        self._mutate(action)

    def snapshot(self) -> dict:
        db = self._db()
        try:
            db.execute("BEGIN")
            check = db.execute("PRAGMA quick_check").fetchone()
            if check != ("ok",):
                raise _error("Run database integrity check failed")
            rows = db.execute("SELECT schema_version, state, metadata, result FROM run").fetchall()
            if len(rows) != 1:
                raise _error("Run database must contain exactly one run")
            schema, state, metadata, result = rows[0]
            if schema != 1 or state not in _STATES:
                raise _error("Unsupported or invalid run archive state")
            metadata = _decode(metadata) if metadata is not None else None
            result = _decode(result) if result is not None else None
            if state == "created" and (metadata is not None or result is not None):
                raise _error("Created run has contradictory metadata or result")
            if state != "created" and metadata is None:
                raise _error("Initialized run lacks metadata")
            if state in _TERMINAL_STATES:
                if result is None or _validate_result(result) != state:
                    raise _error("Terminal state and result disagree")
            elif result is not None:
                raise _error("Unfinished run contains a final result")
            events = []
            for expected, (sequence, kind, payload) in enumerate(
                db.execute("SELECT sequence, kind, payload FROM events ORDER BY sequence"), start=1
            ):
                if sequence != expected or type(kind) is not str or not kind or len(kind) > 128:
                    raise _error("Run contains malformed or noncontiguous events")
                events.append({"sequence": sequence, "kind": kind, "payload": _decode(payload)})
            attempts = []
            for expected, (sequence, record) in enumerate(
                db.execute("SELECT sequence, record FROM attempts ORDER BY sequence"), start=1
            ):
                decoded = _decode(record)
                _validate_attempt(decoded)
                if sequence != expected:
                    raise _error("Run contains noncontiguous attempts")
                attempts.append({"sequence": sequence, "record": decoded})
            if state == "created" and (events or attempts):
                raise _error("Uninitialized run contains execution records")
            db.execute("COMMIT")
            return {"schema_version": 1, "metadata": metadata, "events": events,
                    "attempts": attempts, "result": result, "state": state}
        except BaseException as exc:
            self._rollback(db, exc)
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot inspect run archive", exc) from exc

    @classmethod
    def recover_interrupted(cls, root: Path) -> dict:
        """Explicitly mark an unfinished run interrupted under exclusive ownership.

        Completed/terminal results are never rewritten. Unknown accounting is
        retained as unknown; attempt records are not reconstructed as counters.
        This does not resume firmware or a strategy.
        """
        store = cls(root)
        primary = None
        try:
            store.close()
            path = store.root / "run.sqlite3"
            store._lock = _WriterLock(store.root / ".writer.lock", create=False)
            store._writable = True
            store._connection = sqlite3.connect(path, timeout=_SQLITE_BUSY_SECONDS, isolation_level=None)
            store._connection.execute("PRAGMA synchronous=FULL")
            snapshot = store.snapshot()
            if snapshot["state"] in _TERMINAL_STATES:
                return snapshot
            if snapshot["state"] == "created":
                store.initialize({"recovery": "unfinished_before_initialization"})
            store.append_event("recovery", {"previous_state": snapshot["state"],
                                            "accounting_status": "unknown"})
            store.finish({"state": "interrupted", "success": False,
                          "accounting_status": "unknown",
                          "reason": "Previous writer ended before a terminal result was persisted"})
            return store.snapshot()
        except BaseException as exc:
            primary = exc
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot recover interrupted run", exc) from exc
        finally:
            store._close_preserving(primary)

    def _artifact_path(self, name: str) -> Path:
        if type(name) is not str or not name or "\\" in name:
            raise _error("Artifact path must be a nonempty portable relative path")
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or not relative.parts
                or ":" in name or relative.as_posix() != name):
            raise _error("Artifact path must remain inside the run archive")
        if relative.parts[0] in _RESERVED_NAMES or relative.parts[0].startswith("run.sqlite3-"):
            raise _error("Artifact path conflicts with archive metadata")
        path = self.root.joinpath(*relative.parts)
        for item in (path, *path.parents):
            if item == self.root.parent:
                break
            if item.is_symlink():
                raise _error("Artifact paths must not traverse symbolic links")
        return path

    def _write_artifact(self, name: str, content: bytes) -> dict:
        db = self._db(writing=True)
        state = db.execute("SELECT state FROM run WHERE id=1").fetchone()
        if state is None or state[0] not in {"created", "running"}:
            raise _error("Artifacts can only be added before a run is terminal")
        path = self._artifact_path(name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            identity = {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}

            def action(db: sqlite3.Connection) -> None:
                row = db.execute("SELECT state FROM run WHERE id=1").fetchone()
                if row is None or row[0] not in {"created", "running"}:
                    raise _error("Artifacts can only be added before a run is terminal")
                db.execute("INSERT INTO artifacts VALUES (?, ?, ?)",
                           (name, identity["sha256"], identity["size_bytes"]))

            self._mutate(action)
            return identity
        except BaseException as exc:
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot persist immutable artifact", exc) from exc

    def write_json(self, relative_path: str, value: dict) -> dict:
        """Exclusively create a canonical JSON artifact; never overwrite."""
        return self._write_artifact(relative_path, (_encode(value) + "\n").encode("utf-8"))

    def write_text(self, relative_path: str, text: str) -> dict:
        """Exclusively create a UTF-8 report artifact; never overwrite."""
        if type(text) is not str:
            raise _error("Text artifact must be an ordinary string")
        try:
            content = text.encode("utf-8")
        except UnicodeError as exc:
            raise _error("Text artifact is not valid UTF-8", exc) from exc
        return self._write_artifact(relative_path, content)

    def add_artifact(self, relative_path: str, source: Path) -> dict:
        """Copy an actual file after observable identity/metadata consistency checks."""
        try:
            content = _read_consistent(Path(source))
            return self._write_artifact(relative_path, content)
        except BaseException as exc:
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot capture artifact source", exc) from exc

    def verify_artifacts(self, *, cancel_event=None, event_callback=None) -> dict:
        """Verify registered identities and reject unregistered files, read-only.

        The check observes filesystem consistency, not an atomic snapshot.
        An interrupted artifact/database write is rejected rather than treated
        as a complete authoritative inventory.
        """
        from .verification import check_cancel, digest
        report = event_callback or (lambda *args, **kwargs: None)
        try:
            result = {}
            inventory = self._db().execute(
                "SELECT name, sha256, size_bytes FROM artifacts ORDER BY name"
            )
            # The explicit desktop path is preflight-bounded; legacy default
            # readers retain their established streaming inventory behavior.
            if event_callback is not None:
                inventory = inventory.fetchmany(257)
                if len(inventory) > 256:
                    raise _error('Desktop verification artifact count limit exceeded')
                report('inventory', names=[item[0] for item in inventory])
            for index, (name, expected, size) in enumerate(inventory):
                check_cancel(cancel_event)
                report('artifact', index=index, state='checking')
                if type(size) is not int or size < 0 or type(expected) is not str or len(expected) != 64:
                    report('artifact', index=index, state='unavailable_metadata')
                    raise _error("Artifact manifest contains malformed identities")
                try:
                    path = self._artifact_path(name)
                except ProductError:
                    report('artifact', index=index, state='unavailable_metadata')
                    raise
                if not path.is_file():
                    report('artifact', index=index, state='missing_artifact')
                    raise _error(f"Artifact is missing or is not a regular file: {name}")
                if cancel_event is not None:
                    from firmavex.backends.security import read_bytes, EXPORT_BYTES
                    data = read_bytes(path, EXPORT_BYTES, cancel_event=cancel_event)
                else:
                    data = _read_consistent(path)
                if len(data) != size or digest(data, cancel_event) != expected:
                    report('artifact', index=index, state='hash_mismatch')
                    raise _error(f"Artifact identity mismatch: {name}")
                result[name] = {"sha256": expected, "size_bytes": size}
                report('artifact', index=index, state='hash_match')
            report('checking_archive_inventory')
            own_files = {"run.sqlite3", ".writer.lock", "run.sqlite3-journal",
                         "run.sqlite3-wal", "run.sqlite3-shm"}
            for path in self.root.rglob("*"):
                check_cancel(cancel_event)
                name = path.relative_to(self.root).as_posix()
                if path.is_symlink():
                    raise _error(f"Unexpected symbolic link in archive: {name}")
                if not path.is_dir() and name not in result and name not in own_files:
                    raise _error(f"Unregistered artifact in archive: {name}")
            return result
        except BaseException as exc:
            if isinstance(exc, ProductError) or not isinstance(exc, Exception):
                raise
            raise _error("Cannot verify archive artifacts", exc) from exc
