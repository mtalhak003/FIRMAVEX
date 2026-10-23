"""Local product entry points for versioned backends; no Qt or network access."""

from datetime import datetime, timezone
from pathlib import Path
import threading
import json
import time
import uuid

from firmavex.backends.api import profiles, request_from_dict
from firmavex.backends.bundled import prepare_builtin_riscv
from firmavex.product.errors import ProductError


def check(profile):
    if type(profile) is not str or profile not in profiles:
        raise ValueError("Unsupported backend profile")
    from firmavex.backends.compatibility import check as probe

    return json.loads(json.dumps(probe(profile), allow_nan=False))


def prepare(profile, output_dir, *, cancel_event=None):
    if type(profile) is not str or profile not in profiles:
        raise ValueError("Unsupported backend profile")
    from firmavex.backends.security import checked_path

    checked_path(output_dir, exists=False)
    if cancel_event is not None and cancel_event.is_set():
        raise KeyboardInterrupt("Preparation cancelled")
    if profile == "cortex-m3-mps2":
        from .services import prepare_example_project

        record = prepare_example_project(output_dir, cancel_event=cancel_event)
        return {**record, "profile": profile, "source": record["config_file"]}
    if profile == "riscv32-virt":
        return prepare_builtin_riscv(output_dir, cancel_event=cancel_event)
    from firmavex.backends.examples import prepare as prepare_source

    record = prepare_source(profile, output_dir)
    return {
        **record,
        "profile": profile,
        "source": str(Path(output_dir).expanduser().resolve() / "counter.v"),
    }


def execute(request, output_dir, *, trust, cancel_event=None, event_callback=None):
    if type(trust) is not str or trust not in {"trusted_example", "trusted_project"}:
        raise ProductError(
            "untrusted_workload",
            "Untrusted workloads are rejected because no independently verified OS sandbox is available.",
        )
    from firmavex.backends.engine import execute_trusted
    from firmavex.backends.process import observe_processes

    parsed = request_from_dict(request)
    callback = event_callback or (lambda data: None)
    callback(
        {"type": "backend_stage", "stage": "validation", "profile": parsed.profile}
    )
    with observe_processes(callback):
        result = execute_trusted(parsed, Path(output_dir), cancel_event, trust=trust)
    callback(
        {
            "type": "backend_stage",
            "stage": "finished",
            "status": result["status"],
            "profile": parsed.profile,
        }
    )
    return result


def inspect(run_dir):
    from firmavex.backends.engine import inspect_run

    return inspect_run(run_dir)


def export(run_dir, output_dir):
    from firmavex.backends.report import export as export_record

    return export_record(run_dir, output_dir)


def reproduce(run_dir, output_dir, *, trust, cancel_event=None, event_callback=None):
    from firmavex.backends.report import reproduce as replay
    from firmavex.backends.process import observe_processes

    record = inspect(run_dir)
    profile = record["evidence"].get("admission", {}).get("profile", {}).get("id")
    callback = event_callback or (lambda data: None)
    if profile != "cortex-m3-mps2":
        with observe_processes(callback):
            return replay(run_dir, output_dir, cancel_event, trust=trust)
    # The mature ARM replay path preserves its SQLite accounting and snapshots.
    if trust != "trusted_project" and trust != "trusted_example":
        raise ValueError(
            "Untrusted workloads are not supported; no verified OS sandbox is available"
        )
    if record["status"] != "triggered":
        raise ValueError("ARM reproduction requires an observed triggering vector")
    if trust == "trusted_example":
        # An archive label is not proof of provenance. Revalidate known image
        # bytes and semantics, and forbid archive-selected host executables.
        from dataclasses import replace
        from tempfile import TemporaryDirectory
        from firmavex.backends.api import Request
        from firmavex.backends.security import _arm_config, validate_trust
        from .tools import discover

        saved = _arm_config(Path(run_dir) / "arm-run/project.json")
        current = discover()
        for name in ("qemu", "gdb"):
            selected = getattr(saved, name)
            if (
                selected is not None
                and Path(selected).resolve() != Path(getattr(current, name)).resolve()
            ):
                raise ValueError(
                    "Saved ARM runtime differs from the current trusted runtime; explicit trusted-project acknowledgment is required"
                )
        with TemporaryDirectory(prefix="firmavex-replay-validation-") as temporary:
            config_file = Path(temporary).resolve() / "project.json"
            config_file.write_text(
                json.dumps(
                    replace(saved, qemu=None, gdb=None, compiler=None).to_dict()
                ),
                encoding="utf-8",
            )
            validate_trust(Request("cortex-m3-mps2", config_file), trust)
    from .services import reproduce_run
    from firmavex.backends.engine import _write
    from firmavex.backends.security import fresh_directory

    output = fresh_directory(output_dir)
    start = time.monotonic()
    from .provenance import declaration, execution_context
    with execution_context(rerun_of=record["evidence"]["admission"]["attempt_id"]):
        provenance = declaration(profile)
    admission = {
        **record["evidence"]["admission"],
        "execution_provenance": provenance,
        "attempt_id": uuid.uuid4().hex,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "reproduction_of": str(Path(run_dir).resolve()),
    }
    _write(output / "admission.json", admission)
    try:
        legacy = reproduce_run(
            Path(run_dir) / "arm-run",
            output / "arm-run",
            3,
            cancel_event=cancel_event,
            event_callback=callback,
        )
        consistent = legacy.get("outcome") == "reproduced_in_emulator"
        status = (
            "infrastructure_failure"
            if legacy.get("success") is not True or legacy["accounting"]["aborted"]
            else ("triggered" if consistent else "not_discovered")
        )
        evidence = {
            "admission": admission,
            "legacy_result": legacy,
            "measurement_mode": legacy["measurement_mode"],
            "cleanup_verified": legacy.get("execution_evidence") == "complete",
            "elapsed_seconds": time.monotonic() - start,
            "triggering_input": legacy.get("triggering_input"),
        }
        result = {"schema_version": 1, "status": status, "evidence": evidence}
        _write(output / "result.json", result)
        return {
            "status": status,
            "original_status": record["status"],
            "outcome_matches": consistent,
            "result": result,
        }
    except BaseException as exc:
        interrupted = {
            "schema_version": 1,
            "status": (
                "cancelled"
                if isinstance(exc, (KeyboardInterrupt, SystemExit))
                else "infrastructure_failure"
            ),
            "evidence": {
                "admission": admission,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": time.monotonic() - start,
                "accounting": "see authoritative arm-run SQLite; no outer count inferred",
            },
        }
        try:
            _write(output / "result.json", interrupted)
        except BaseException as secondary:
            exc.add_note(f"Reproduction persistence failed: {secondary}")
        raise
