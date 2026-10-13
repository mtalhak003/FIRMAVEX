"""Fresh-run persistence and dispatch, never automatic retries or resumes."""

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


def _write(path, record):
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name == "posix":
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def inspect_run(output):
    """Read-only inspection: an admitted record without result has unknown lifecycle/accounting."""
    output = Path(output)
    if (output / "result.json").exists():
        return json.loads((output / "result.json").read_text())
    admitted = json.loads((output / "admission.json").read_text())
    return {
        "schema_version": 1,
        "status": "incomplete",
        "evidence": {
            "admission": admitted,
            "accounting": "unknown; do not infer execution or retry",
            "lifecycle": "running or interrupted; result absence alone cannot distinguish",
        },
    }


def execute(request: Request, output: Path, cancel=None):
    if type(request) is not Request:
        raise ValueError("Exact Request required")
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    cancel = cancel or threading.Event()
    started = time.monotonic()
    admission = {
        "schema_version": 1,
        "attempt_id": uuid.uuid4().hex,
        "profile": profiles[request.profile].to_dict(),
        "source": str(request.source.expanduser().resolve()),
        "values": list(request.values),
        "limits": (
            asdict(request.limits)
            if request.profile != "cortex-m3-mps2"
            else {"policy": "legacy project configuration"}
        ),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write(output / "admission.json", admission)
    from .implementations import ArmBackend, RiscvBackend, IcarusBackend

    backend = {
        "cortex-m3-mps2": ArmBackend,
        "riscv32-virt": RiscvBackend,
        "verilog-icarus": IcarusBackend,
    }[request.profile]()
    try:
        result = backend.execute(request, output, cancel)
    except BaseException as exc:
        result = Result(
            (
                "cancelled"
                if isinstance(exc, (Cancelled, KeyboardInterrupt, SystemExit))
                else "infrastructure_failure"
            ),
            {
                **getattr(exc, "backend_evidence", {}),
                "error": f"{type(exc).__name__}: {exc}",
                "notes": getattr(exc, "__notes__", []),
            },
        )
        record = result.to_dict()
        record["evidence"].update(
            admission=admission,
            elapsed_seconds=time.monotonic() - started,
            ended_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        try:
            _write(output / "result.json", record)
        except BaseException as persistence:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                exc.add_note(
                    f"Result persistence failed: {type(persistence).__name__}: {persistence}"
                )
                raise exc
            persistence.add_note(
                f"Original backend failure: {type(exc).__name__}: {exc}"
            )
            raise
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return json.loads(json.dumps(record))
    record = result.to_dict()
    record["evidence"].update(
        admission=admission,
        elapsed_seconds=time.monotonic() - started,
        ended_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    _write(output / "result.json", record)
    return json.loads(json.dumps(record))
