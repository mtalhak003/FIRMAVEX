"""Fresh-run persistence and dispatch, never automatic retries or resumes.

``execute`` preserves the Batch 5 trusted-caller API. Desktop/worker entry points
use ``execute_trusted`` and must make trust explicit. Neither API is a sandbox.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import uuid
from .api import Request, Result, profiles
from .process import Cancelled
from .security import JSON_BYTES, checked_path, fresh_directory, read_json
from firmavex.product.file_state import path_state

STATUSES = frozenset({"passed", "triggered", "not_discovered", "invalid_input",
                      "invalid_output", "infrastructure_failure", "cancelled"})


def _write(path, record):
    """Atomic bounded JSON replacement in an already owned directory."""
    path = Path(path)
    data = json.dumps(record, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    if len(data) > JSON_BYTES:
        raise ValueError("JSON record exceeds byte limit")
    checked_path(path.parent, directory=True)
    if path.exists() or path.is_symlink():
        checked_path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    primary = None
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException as exc:
            if primary is not None and not (isinstance(primary, Exception) and not isinstance(exc, Exception)):
                primary.add_note("Temporary record cleanup failed: " + str(exc))
            else:
                raise


def _lock(stream, acquire=True, nonblocking=False):
    if os.name == "posix":
        import fcntl
        mode = fcntl.LOCK_EX if acquire else fcntl.LOCK_UN
        fcntl.flock(stream, mode | (fcntl.LOCK_NB if nonblocking else 0))
    else:
        import msvcrt
        stream.seek(0)
        mode = (msvcrt.LK_NBLCK if nonblocking else msvcrt.LK_LOCK) if acquire else msvcrt.LK_UNLCK
        msvcrt.locking(stream.fileno(), mode, 1)


class _Ownership:
    """OS-held ownership survives no process: stale files are never stale locks."""
    def __init__(self, output, attempt_id):
        # Lock a separate byte. Windows byte-range locks prevent reads of that
        # byte, so locking the JSON itself would block inspection of its owner.
        _write(output / "attempt.owner", {"schema_version": 1, "attempt_id": attempt_id,
                                          "pid": os.getpid()})
        self.path = output / "attempt.lock"
        self.stream = self.path.open("x+b")
        try:
            self.stream.write(b"1")
            self.stream.flush()
            os.fsync(self.stream.fileno())
            _lock(self.stream)
        except BaseException as exc:
            try:
                self.stream.close()
            except BaseException as cleanup:
                if isinstance(exc, Exception) and not isinstance(cleanup, Exception):
                    raise
                exc.add_note("Ownership construction cleanup failed: " + str(cleanup))
            raise

    def close(self):
        try:
            _lock(self.stream, acquire=False)
        finally:
            self.stream.close()


def _lifecycle(output, admission):
    owner_path = output / "attempt.owner"
    if not owner_path.exists() and not owner_path.is_symlink():
        return "unknown; legacy admission has no live ownership evidence"
    owner = read_json(owner_path, 4096)
    if (type(owner) is not dict or type(owner.get("schema_version")) is not int
            or owner["schema_version"] != 1
            or owner.get("attempt_id") != admission.get("attempt_id")
            or type(owner.get("pid")) is not int):
        raise ValueError("Invalid attempt ownership record")
    lock_path = output / "attempt.lock"
    if not lock_path.exists() and not lock_path.is_symlink():
        return "unknown; ownership lock is absent"
    lock_path = checked_path(lock_path)
    if lock_path.stat().st_size != 1:
        raise ValueError("Invalid attempt ownership lock")
    # Locking changes no bytes and works with a read-only file handle, so an
    # administrator can inspect a read-only saved archive.
    with lock_path.open("rb") as stream:
        try:
            _lock(stream, nonblocking=True)
        except (BlockingIOError, PermissionError):
            return "running; attempt ownership is held"
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) in {33, 36}:
                return "running; attempt ownership is held"
            raise
        else:
            _lock(stream, acquire=False)
            return "interrupted; ownership released without a final record"


def _validate_result(record):
    if (type(record) is not dict or set(record) != {"schema_version", "status", "evidence"}
            or type(record.get("schema_version")) is not int or record["schema_version"] != 1
            or type(record.get("status")) is not str or record["status"] not in STATUSES
            or type(record.get("evidence")) is not dict):
        raise ValueError("Invalid backend result record")
    evidence = record["evidence"]
    if "cleanup_verified" in evidence and type(evidence["cleanup_verified"]) is not bool:
        raise ValueError("Invalid cleanup evidence")
    if "elapsed_seconds" in evidence and (type(evidence["elapsed_seconds"]) not in (int, float)
                                           or evidence["elapsed_seconds"] < 0):
        raise ValueError("Invalid elapsed time")
    if record["status"] in {"passed", "triggered"} and evidence.get("measurement_mode") in {"real_firmware", "real_simulation"}:
        if evidence.get("cleanup_verified") is not True:
            raise ValueError("Completed real execution lacks verified cleanup")
        profile = evidence.get("backend")
        if profile == "riscv32-virt" and evidence.get("completion_observed") is not True:
            raise ValueError("Completed firmware lacks completion evidence")
    return record


def inspect_run(output):
    """Bounded, read-only inspection; missing outcomes never imply executions."""
    output = checked_path(output, directory=True)
    result_path = output / "result.json"
    if result_path.exists() or result_path.is_symlink():
        before = path_state(checked_path(result_path))
        record = _validate_result(read_json(result_path))
        admission = record["evidence"].get("admission")
        if type(admission) is not dict or type(admission.get("attempt_id")) is not str:
            raise ValueError("Invalid result admission")
        profile = admission.get("profile")
        if (type(profile) is not dict or type(profile.get("id")) is not str
                or profile["id"] not in profiles):
            raise ValueError("Invalid result target profile")
        values = admission.get("values")
        if type(values) is not list or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in values):
            raise ValueError("Invalid result request values")
        if profile["id"] == "riscv32-virt" and len(values) != 2:
            raise ValueError("Invalid RV32 result vector")
        if profile["id"] != "riscv32-virt" and values:
            raise ValueError("Invalid result request vector")
        admission_path = output / "admission.json"
        admission_before = None
        if admission_path.exists() or admission_path.is_symlink():
            admission_before = path_state(checked_path(admission_path))
            admission = read_json(admission_path, 1024 * 1024)
            if admission != record["evidence"].get("admission"):
                raise ValueError("Result admission does not match the saved attempt")
        if admission_before is not None and admission_before != path_state(checked_path(admission_path)):
            raise ValueError("Admission changed during inspection")
        if before != path_state(checked_path(result_path)):
            raise ValueError("Result changed during inspection")
        return record
    admitted = read_json(output / "admission.json", 1024 * 1024)
    if type(admitted) is not dict or type(admitted.get("attempt_id")) is not str:
        raise ValueError("Invalid admitted attempt")
    return {
        "schema_version": 1,
        "status": "incomplete",
        "evidence": {
            "admission": admitted,
            "accounting": "unknown; do not infer execution or retry",
            "lifecycle": _lifecycle(output, admitted),
        },
    }


def execute_trusted(request: Request, output: Path, cancel=None, *, trust):
    """Product boundary. Explicit trust is mandatory; untrusted input never runs."""
    from .security import validate_trust
    if type(request) is not Request:
        raise ValueError("Exact Request required")
    validate_trust(request, trust)
    return _execute(request, output, cancel, trust=trust)


def execute(request: Request, output: Path, cancel=None):
    """Legacy trusted-caller interface; callers own the workload trust decision."""
    return _execute(request, output, cancel)


def _execute(request, output, cancel=None, trust=None):
    if type(request) is not Request:
        raise ValueError("Exact Request required")
    output = fresh_directory(output)
    cancel = cancel or threading.Event()
    started = time.monotonic()
    from firmavex.product.provenance import declaration
    admission = {
        "execution_provenance": declaration(request.profile),
        "schema_version": 1,
        "attempt_id": uuid.uuid4().hex,
        "profile": profiles[request.profile].to_dict(),
        "source": str(request.source.expanduser().absolute()),
        "values": list(request.values),
        "limits": (asdict(request.limits) if request.profile != "cortex-m3-mps2"
                   else {"policy": "legacy project configuration"}),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if trust is not None:
        admission["trust"] = trust
        admission["sandboxed"] = False
    _write(output / "admission.json", admission)
    ownership = _Ownership(output, admission["attempt_id"])
    primary = None
    try:
        from .implementations import ArmBackend, RiscvBackend, IcarusBackend
        backend = {"cortex-m3-mps2": ArmBackend, "riscv32-virt": RiscvBackend,
                   "verilog-icarus": IcarusBackend}[request.profile]()
        try:
            if trust is not None:
                from .security import prepare_trusted_request
                request = prepare_trusted_request(request, output, trust)
            result = backend.execute(request, output, cancel)
            record = _validate_result(result.to_dict())
        except BaseException as exc:
            primary = exc
            record = Result(
                "cancelled" if isinstance(exc, (Cancelled, KeyboardInterrupt, SystemExit)) else "infrastructure_failure",
                {**getattr(exc, "backend_evidence", {}), "error": f"{type(exc).__name__}: {exc}",
                 "notes": getattr(exc, "__notes__", [])},
            ).to_dict()
        record["evidence"].update(admission=admission, elapsed_seconds=time.monotonic() - started,
                                   ended_at_utc=datetime.now(timezone.utc).isoformat())
        try:
            _write(output / "result.json", record)
        except BaseException as persistence:
            if isinstance(primary, (KeyboardInterrupt, SystemExit)):
                primary.add_note(f"Result persistence failed: {type(persistence).__name__}: {persistence}")
                raise primary
            if primary is not None:
                persistence.add_note(f"Original backend failure: {type(primary).__name__}: {primary}")
            raise
        if isinstance(primary, (KeyboardInterrupt, SystemExit)):
            raise primary
        return json.loads(json.dumps(record))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            ownership.close()
        except BaseException as cleanup:
            if primary is not None and not (isinstance(primary, Exception) and not isinstance(cleanup, Exception)):
                primary.add_note("Attempt ownership cleanup failed: " + str(cleanup))
            else:
                if primary is None:
                    record["evidence"].update(original_status=record["status"],
                        error=f"Attempt ownership cleanup failed: {type(cleanup).__name__}: {cleanup}")
                    record["status"] = "cancelled" if not isinstance(cleanup, Exception) else "infrastructure_failure"
                    try:
                        _write(output / "result.json", record)
                    except BaseException as persistence:
                        cleanup.add_note("Final cleanup-failure persistence failed: " + str(persistence))
                raise
