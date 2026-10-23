"""Bounded read-only reports and explicit fresh reproduction, never recovery."""

import hashlib
import json
from pathlib import Path
import tempfile
from .api import Request, Limits
from .engine import execute, execute_trusted, inspect_run, _write
from .security import (EXPORT_BYTES, EXPORT_FILES, artifact_name, checked_path,
                       fresh_directory, read_bytes)
from firmavex.product.file_state import path_state


def _safe_text(value, maximum=1024):
    return "".join(c if ord(c) >= 32 else " " for c in str(value))[:maximum].replace("`", "'").replace("<", "&lt;")


def _saved_artifacts(output, record, *, cancel_event=None, event_callback=None):
    from firmavex.product.verification import check_cancel, digest
    report = event_callback or (lambda *args, **kwargs: None)
    items = record["evidence"].get("artifacts", [])
    if type(items) is not list or len(items) > EXPORT_FILES - 16:
        raise ValueError("Invalid artifact inventory")
    report('inventory', names=[item.get('name', '[invalid metadata]') if type(item) is dict else '[invalid metadata]' for item in items])
    collected = {}
    total = 0
    for index, item in enumerate(items):
        check_cancel(cancel_event)
        report('artifact', index=index, state='checking')
        if type(item) is not dict:
            report('artifact', index=index, state='unavailable_metadata')
            raise ValueError("Invalid artifact metadata")
        try:
            name = artifact_name(item.get("name"))
        except ValueError:
            report('artifact', index=index, state='unavailable_metadata')
            raise
        key = name.casefold()
        if key in {n.casefold() for n in collected} or key in {"result.json", "report.md", "checksums.json"}:
            report('artifact', index=index, state='unavailable_metadata')
            raise ValueError("Artifact name collision")
        expected = item.get("sha256")
        size = item.get("size_bytes")
        if (type(expected) is not str or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)
                or type(size) is not int or not 0 <= size <= EXPORT_BYTES):
            report('artifact', index=index, state='unavailable_metadata')
            raise ValueError("Invalid artifact digest/size")
        data = read_bytes(output / name, EXPORT_BYTES, cancel_event=cancel_event) if cancel_event is not None else read_bytes(output / name, EXPORT_BYTES)
        if len(data) != size or digest(data, cancel_event) != expected:
            report('artifact', index=index, state='hash_mismatch')
            raise ValueError("Saved artifact no longer matches execution evidence")
        total += len(data)
        if total > EXPORT_BYTES:
            raise ValueError("Export artifact byte limit exceeded")
        collected[name] = data
        report('artifact', index=index, state='hash_match')
    return collected


def _logs(record):
    evidence = record["evidence"]
    logs = {}
    for key in ("stdout", "stderr", "compile_stdout", "compile_stderr"):
        if key in evidence:
            if type(evidence[key]) is not str:
                raise ValueError("Invalid log evidence")
            logs[key + ".txt"] = evidence[key].encode("utf-8")
    processes = evidence.get("process_logs", [])
    if type(processes) is not list or len(processes) > 64:
        raise ValueError("Invalid process log inventory")
    for index, item in enumerate(processes):
        if type(item) is not dict:
            raise ValueError("Invalid process log")
        for channel in ("stdout", "stderr"):
            value = item.get(channel, "")
            if type(value) is not str:
                raise ValueError("Invalid process log")
            logs[f"process-{index:04d}-{channel}.txt"] = value.encode("utf-8")
    return logs


def _arm_payload(output, record):
    """Retain the established SQLite receipt ledger without inventing evidence."""
    if record["evidence"]["admission"]["profile"]["id"] != "cortex-m3-mps2":
        return {}
    root = output / "arm-run"
    if not root.exists() and not root.is_symlink():
        if record["evidence"].get("legacy_result") is not None:
            raise ValueError("ARM receipt archive is missing")
        return {}
    from firmavex.product import services
    from .process import inspect_artifacts
    root = checked_path(root, directory=True)
    # Admit the entire owned store before the legacy reader hashes any files.
    # This keeps that unchanged, otherwise unbounded reader within this export's
    # aggregate byte/count limits and rejects links/special files beforehand.
    inspect_artifacts(root, EXPORT_BYTES)
    database = checked_path(root / "run.sqlite3")
    before = path_state(database)
    snapshot, artifacts = services._read_run(root)
    if before != path_state(checked_path(database)):
        raise ValueError("ARM receipt database changed during export capture")
    original = record["evidence"].get("legacy_result")
    if original is not None and snapshot.get("result") != original:
        raise ValueError("ARM wrapper and authoritative result disagree")
    attempts = snapshot.get("attempts")
    if type(attempts) is not list or len(attempts) * 2 + 4 > EXPORT_FILES:
        raise ValueError("ARM attempt log retention limit exceeded")
    archive = {**snapshot, "artifact_verification": artifacts,
               "inspection_is_not_execution_verification": True}
    payload = {"arm-evidence.json": json.dumps(archive, sort_keys=True, indent=2,
                                               allow_nan=False).encode("utf-8")}
    for index, item in enumerate(attempts):
        if type(item) is not dict or type(item.get("record")) is not dict:
            raise ValueError("Invalid ARM attempt record")
        evidence = item["record"].get("evidence", {})
        if type(evidence) is not dict:
            raise ValueError("Invalid ARM attempt evidence")
        for channel in ("stdout", "stderr"):
            value = evidence.get(channel, "")
            if type(value) is not str:
                raise ValueError("Invalid ARM attempt log")
            payload[f"arm-attempt-{index + 1:06d}-{channel}.txt"] = value.encode("utf-8")
    return payload


def export(output, destination):
    """Copy only evidence-listed, verified artifacts/logs to a fresh directory.

    Includes waveform bytes, never just a path to the original artifact. No
    arbitrary archive extraction, recursion, symlink following, or overwrite.
    """
    output = checked_path(output, directory=True)
    record = inspect_run(output)
    artifacts = _saved_artifacts(output, record)
    logs = _logs(record)
    arm = _arm_payload(output, record)
    for name in arm:
        if name.casefold() in {n.casefold() for n in (*artifacts, *logs)}:
            raise ValueError("ARM export name collision")
    if {name.casefold() for name in artifacts} & {name.casefold() for name in logs}:
        raise ValueError("Artifact/log name collision")
    payload = {**artifacts, **logs, **arm}
    if len(payload) + 3 > EXPORT_FILES or sum(map(len, payload.values())) > EXPORT_BYTES:
        raise ValueError("Export retention limit exceeded")
    if inspect_run(output) != record:
        raise ValueError("Run record changed during export capture")
    evidence = record["evidence"]
    admission = evidence.get("admission", {})
    text = (
        "# FIRMAVEX backend result\n\n"
        f"Status: **{record['status']}**\n\n"
        f"Target: `{_safe_text(admission.get('profile', {}).get('id', 'unknown'))}`\n\n"
        f"Request vector: `{_safe_text(admission.get('values', []))}`\n\n"
        f"Search triggering vector: `{_safe_text(evidence.get('triggering_input', 'not a search result'))}`\n\n"
        f"Diagnostic: `{_safe_text(evidence.get('error', 'none'))}`\n\n"
        f"Elapsed wall time: {_safe_text(evidence.get('elapsed_seconds', 'unknown'))} seconds.\n\n"
        f"Measurement classification: `{_safe_text(evidence.get('measurement_mode', 'legacy or unknown'))}`\n\n"
        f"Cleanup verified: `{_safe_text(evidence.get('cleanup_verified', 'see legacy result'))}`\n\n"
        "Exports contain administrator-owned logs and may disclose paths or supplied metadata. Review before publication.\n\n"
        "This is a local tool observation, not hardware validation or a security guarantee.\n"
        "HDL results express the supplied testbench assertion, not proof of design correctness.\n"
    )
    from firmavex.product.presentation import summary
    text += "\n## Interpretation and troubleshooting\n\n" + "\n\n".join(
        _safe_text(line) for line in summary(record).splitlines()) + "\n"
    payload["result.json"] = json.dumps(record, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    payload["REPORT.md"] = text.encode("utf-8")
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    checksum_bytes = json.dumps(hashes, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    if sum(map(len, payload.values())) + len(checksum_bytes) > EXPORT_BYTES:
        raise ValueError("Export retention limit exceeded including report")
    destination = fresh_directory(destination)
    for name, data in payload.items():
        with (destination / name).open("xb") as stream:
            stream.write(data)
    _write(destination / "checksums.json", hashes)
    return {"status": "exported", "destination": str(destination), "files": hashes}


def reproduce(output, destination, cancel=None, *, trust=None):
    """Legacy trusted-caller replay; safe product callers must pass explicit trust."""
    output = checked_path(output, directory=True)
    record = inspect_run(output)
    if record["status"] not in {"passed", "triggered"}:
        raise ValueError("Only completed observations may be reproduced")
    evidence = record["evidence"]
    profile = evidence["admission"]["profile"]["id"]
    if profile not in {"riscv32-virt", "verilog-icarus"}:
        raise ValueError("Use the existing product reproduction command for ARM")
    name = "firmware.elf" if profile == "riscv32-virt" else "testbench.v"
    expected = evidence["firmware" if profile == "riscv32-virt" else "source"]["sha256"]
    data = read_bytes(output / name, EXPORT_BYTES)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Saved input artifact no longer matches evidence")
    # Freeze the bytes that were verified above: re-reading the mutable saved
    # artifact later would leave a verification-to-dispatch gap. This directory
    # is owned by the caller and removed only after execution/cleanup completes.
    temporary = tempfile.TemporaryDirectory(prefix="firmavex-backend-replay-")
    primary = None
    try:
        source = Path(temporary.name).resolve() / name
        source.write_bytes(data)
        request = Request(profile, source, tuple(evidence["admission"]["values"]),
                          Limits(**evidence["admission"]["limits"]))
        from firmavex.product.provenance import execution_context
        with execution_context(rerun_of=record["evidence"]["admission"]["attempt_id"]):
            result = (execute(request, Path(destination), cancel) if trust is None else
                      execute_trusted(request, Path(destination), cancel, trust=trust))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            temporary.cleanup()
        except BaseException as cleanup:
            if primary is not None and not (isinstance(primary, Exception) and not isinstance(cleanup, Exception)):
                primary.add_note("Replay temporary cleanup failed: " + str(cleanup))
            else:
                raise
    # Return the actual outcome, never force agreement with the original.
    return {"status": result["status"], "original_status": record["status"],
            "outcome_matches": result["status"] == record["status"], "result": result}
