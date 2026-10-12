"""Product orchestration around the unchanged evaluator and strategy contracts.

Every executable observation is fresh. Successful inputs and runtime receipts
are product-owned records, not extra strategy feedback. Injected executors are
private test seams and are always identified as synthetic_test.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import threading
from typing import Any, Callable
from uuid import uuid4

from src.firmavex.evaluation.api import TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.runner import create_strategy
from src.firmavex.strategies.runner import run_strategy
from src.firmavex.strategies.api import TerminationReason

from .config import ProductConfig, load_config
from .errors import ProductError
from .firmware import inspect_elf
from .runtime import FirmwareExecutor
from .store import RunStore
from .tools import discover


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config(value: ProductConfig | str | Path) -> ProductConfig:
    return value if type(value) is ProductConfig else load_config(value)


def doctor() -> dict:
    tools = discover()
    return {
        "schema_version": 1, "success": True, "tools": tools.to_dict(),
        "host": {"system": platform.system(), "machine": platform.machine()},
        "native_execution": "unsupported" if os.name == "nt" else "experimental",
        "limitations": [
            "Native Windows process-tree supervision is not implemented in Batch 1.",
            "macOS native execution and installers have not been verified.",
            "Only symbolized Cortex-M3 ELF compatible with mps2-an385 is supported.",
        ],
    }


def validate_project(config_or_path: ProductConfig | str | Path) -> dict:
    config = _config(config_or_path)
    image = inspect_elf(config)
    tools = discover(config)
    return {
        "schema_version": 1, "success": True, "configuration": config.to_dict(),
        "firmware": image, "tools": tools.to_dict(),
        "validation_scope": "ELF/configuration/tool capabilities; guest compatibility requires execution",
    }


def _emit(callback: Callable | None, payload: dict) -> None:
    if callback is not None:
        callback(payload)


def _report(result: dict) -> str:
    accounting = result.get("accounting") or {}
    lines = [
        "# FIRMAVEX product test result", "",
        f"Outcome: **{result.get('outcome', 'unknown')}**",
        f"Run state: **{result['state']}**",
        f"Measurement mode: **{result.get('measurement_mode', 'unknown')}**",
        f"Execution evidence: **{result.get('execution_evidence', 'incomplete')}**", "",
        f"Triggering input: {json.dumps(result.get('triggering_input'))}",
        f"Charged evaluator attempts: {accounting.get('attempted_executions', 'unknown')}",
        f"Completed observations: {accounting.get('successful_executions', 'unknown')}",
        f"Infrastructure failures: {accounting.get('infrastructure_failures', 'unknown')}", "",
        "No configured failure within a budget is not proof that firmware is safe.",
        "Charged evaluator attempts are not independently verified physical executions.",
        "Observations concern the declared QEMU environment, not physical hardware.",
        "A matching runtime signature is not a coverage or complete-path guarantee.", "",
    ]
    if result.get("reproduction") is not None:
        lines.extend(["Reproduction: " + json.dumps(result["reproduction"], sort_keys=True), ""])
    if result.get("error"):
        lines.extend(["Diagnostics: " + json.dumps(result["error"], sort_keys=True), ""])
    return "\n".join(lines)


class _RecordedSession:
    def __init__(self, owner, executor, store, mode, cancel_event, callback):
        self.owner, self.executor, self.store = owner, executor, store
        self.mode, self.cancel_event, self.callback = mode, cancel_event, callback
        self.receipt = None
        self.triggering_input = None
        self.evidence_complete = True

    def describe(self):
        return self.owner.describe()

    def result(self):
        return self.owner.result()

    def execute(self, trial):
        if self.cancel_event.is_set():
            raise KeyboardInterrupt("Product run cancelled before admission.")
        self.receipt = None
        self.store.append_event("trial_requested", {"input": list(trial.values)})
        before = self.owner.result().attempted_executions
        try:
            feedback = self.owner.execute(trial)
        except BaseException as exc:
            # Read the evaluator only after its admission lock has unwound.
            accounting = asdict(self.owner.result())
            if accounting["attempted_executions"] > before:
                evidence = dict(getattr(self.executor, "last_evidence", {}) or {})
                evidence["measurement_mode"] = self.mode
                try:
                    self.store.record_attempt({
                        "input": list(trial.values), "feedback": None,
                        "accounting": accounting, "evidence": evidence,
                        "interrupted": True,
                    })
                except BaseException as persistence_error:
                    exc.add_note("Interrupted-attempt persistence failed: " + str(persistence_error))
            self.evidence_complete = False
            raise
        evidence = dict(self.receipt.evidence if self.receipt is not None else {})
        evidence["measurement_mode"] = self.mode
        # Retain the exact known vector even if persisting its receipt fails.
        if feedback.status == "triggered" and self.triggering_input is None:
            self.triggering_input = list(trial.values)
        self.store.record_attempt({
            "input": list(trial.values), "feedback": asdict(feedback),
            "accounting": asdict(self.owner.result()), "evidence": evidence,
            "interrupted": False,
        })
        completed = feedback.status in {"safe", "triggered"}
        if completed and not all(evidence.get(key) is True for key in
                                 ("guest_dispatched", "input_injected", "completion_reached", "cleanup_verified")):
            self.evidence_complete = False
        if not completed:
            self.evidence_complete = False
        _emit(self.callback, {
            "type": "trial_complete", "input": list(trial.values),
            "feedback": asdict(feedback), "accounting": asdict(self.owner.result()),
        })
        return feedback


def _execute_project(config, output_dir, *, cancel_event=None, event_callback=None,
                     replay_values=None, replay_attempts=0, parent=None,
                     _executor_factory=None):
    if os.name == "nt" and _executor_factory is None:
        raise ProductError("unsupported_platform",
                           "Native Windows execution needs tested process-tree supervision; Batch 1 does not claim it.")
    validated = validate_project(config)
    config = _config(config)
    tools = discover(config)
    cancel = cancel_event if cancel_event is not None else threading.Event()
    mode = "real_firmware" if _executor_factory is None else "synthetic_test"
    run_id = str(uuid4())
    budget = config.execution_budget if replay_values is None else replay_attempts
    strategy_name = config.strategy if replay_values is None else "reproduction"
    with RunStore(Path(output_dir), create=True) as store:
        metadata = {
            "schema_version": 1, "run_id": run_id, "created_at_utc": _utc(),
            "application": "firmavex-desktop", "configuration": config.to_dict(),
            "firmware": validated["firmware"], "tools": tools.to_dict(),
            "measurement_mode": mode, "parent": parent,
            "operation": "search" if replay_values is None else "reproduction",
        }
        store.initialize(metadata)
        owner = None
        recorded = None
        imported_identity = validated["firmware"]
        try:
            store.add_artifact("firmware.elf", config.firmware)
            imported = replace(config, firmware=store.root / "firmware.elf")
            imported_identity = inspect_elf(imported)
            if imported_identity["firmware_sha256"] != validated["firmware"]["firmware_sha256"]:
                raise ProductError("firmware_changed", "Firmware changed during import; no execution admitted.")
            saved_config = imported.to_dict()
            saved_config["firmware"] = "firmware.elf"
            store.write_json("project.json", saved_config)

            def runtime_event(event):
                store.append_event("runtime", event)
                _emit(event_callback, event)

            executor = (
                FirmwareExecutor(imported, tools=tools, cancel_event=cancel, event_callback=runtime_event)
                if _executor_factory is None else _executor_factory(imported, tools, cancel, runtime_event)
            )
            recorded = None

            def execute(values):
                receipt = executor.execute(values)
                if recorded is not None:
                    recorded.receipt = receipt
                observation = receipt.observation
                # A symbol value alone is insufficient for a successful product observation.
                if observation.success and (not all(receipt.evidence.get(key) is True for key in
                                                   ("guest_dispatched", "input_injected", "completion_reached", "cleanup_verified"))
                                            or (mode == "real_firmware" and receipt.evidence.get("measurement_mode") != "real_firmware")):
                    return Observation(False, stderr="Runtime completion/cleanup evidence is incomplete.")
                return observation

            owner = EvaluationSession(
                "b-" + uuid4().hex, imported.input_space, budget, strategy_name, execute,
                random_seed=imported.seed if replay_values is None else None,
            )
            recorded = _RecordedSession(owner, executor, store, mode, cancel, event_callback)
            if replay_values is None:
                run = run_strategy(create_strategy(imported.strategy_metadata), recorded)
                termination = run.termination.value
            else:
                for _ in range(replay_attempts):
                    recorded.execute(TrialInput(tuple(replay_values)))
                    if owner.result().aborted:
                        break
                termination = "reproduction_complete"
            accounting = asdict(owner.result())
            if accounting["aborted"]:
                state, outcome = "failed", "infrastructure_failure"
            elif replay_values is not None:
                state = "completed"
                outcome = ("reproduced_in_emulator" if accounting["failure_triggering_executions"] == replay_attempts
                           else "reproduction_inconsistent")
            elif accounting["failure_found"]:
                state, outcome = "completed", "configured_failure_observed"
            elif termination == TerminationReason.INVALID_OUTPUT.value:
                state, outcome = "failed", "invalid_output"
            elif accounting["budget_exhausted"]:
                state, outcome = "completed", "no_failure_within_budget"
            else:
                state, outcome = "completed", "domain_exhausted"
            result = {
                "schema_version": 1, "kind": "firmavex_product_result",
                "run_id": run_id, "state": state, "success": state == "completed" and recorded.evidence_complete,
                "outcome": outcome, "termination": termination, "ended_at_utc": _utc(),
                "measurement_mode": mode, "accounting": accounting,
                "triggering_input": recorded.triggering_input,
                "execution_evidence": "complete" if recorded.evidence_complete else "incomplete",
                "firmware_sha256": imported_identity["firmware_sha256"], "parent": parent,
                "error": None if not owner.diagnostics() else {
                    **owner.diagnostics()[-1], "values": list(owner.diagnostics()[-1]["values"])},
            }
            if replay_values is not None:
                result["reproduction"] = {
                    "requested_attempts": replay_attempts,
                    "completed_observations": accounting["successful_executions"],
                    "matching_observations": accounting["failure_triggering_executions"],
                    "status": "indeterminate" if accounting["aborted"] else outcome,
                    "input": list(replay_values),
                }
            _persist_result(store, result)
            return result
        except BaseException as exc:
            # Cancellation preserves the engine's charged attempts and original exception.
            result = {
                "schema_version": 1, "kind": "firmavex_product_result", "run_id": run_id,
                "state": "cancelled" if not isinstance(exc, Exception) else "failed",
                "success": False, "outcome": "cancelled" if not isinstance(exc, Exception) else "infrastructure_failure",
                "measurement_mode": mode, "accounting": asdict(owner.result()) if owner is not None else None,
                "triggering_input": recorded.triggering_input if recorded is not None else None,
                "execution_evidence": "incomplete", "ended_at_utc": _utc(),
                "firmware_sha256": imported_identity["firmware_sha256"], "parent": parent,
                "error": {"category": getattr(exc, "category", "execution_error"),
                          "message": str(exc), "exception_type": type(exc).__name__},
            }
            try:
                _persist_result(store, result)
            except BaseException as persistence_error:
                if hasattr(exc, "add_note"):
                    exc.add_note("Partial-result persistence also failed: " + str(persistence_error))
            raise


def _persist_result(store, result):
    store.write_json("result.json", result)
    store.write_text("report.md", _report(result))
    store.verify_artifacts()
    store.finish(result)


def run_project(config_or_path, output_dir, *, cancel_event=None, event_callback=None,
                _executor_factory=None):
    return _execute_project(config_or_path, output_dir, cancel_event=cancel_event,
                            event_callback=event_callback, _executor_factory=_executor_factory)


def _read_run(run_dir):
    with RunStore(Path(run_dir)) as store:
        snapshot = store.snapshot()
        artifacts = store.verify_artifacts()
        result = snapshot["result"]
        if result is not None and result.get("kind") == "firmavex_product_result" and (store.root / "result.json").is_file():
            saved = json.loads((store.root / "result.json").read_text(encoding="utf-8"))
            if saved != result:
                raise ProductError("evidence_incomplete", "Result artifact contradicts the stored result.")
        if snapshot["state"] == "completed" and result is None:
            raise ProductError("evidence_incomplete", "Completed run has no result.")
        if result is not None and result.get("kind") == "firmavex_product_result":
            snapshot["accounting_verification"] = _verify_product_result(snapshot, artifacts)
            if "project.json" in artifacts:
                project = load_config(store.root / "project.json").to_dict()
                declared = dict(snapshot["metadata"]["configuration"])
                project.pop("firmware")
                declared.pop("firmware")
                if project != declared:
                    raise ProductError("evidence_incomplete", "Saved project and recorded configuration disagree.")
        elif snapshot["state"] == "completed":
            raise ProductError("evidence_incomplete", "Completed archive is not a versioned product result.")
        return snapshot, artifacts


def _verify_product_result(snapshot, artifacts):
    """Cross-check retained receipts against evaluator counters, never invent them."""
    result, metadata = snapshot["result"], snapshot["metadata"]

    def require(condition, message):
        if not condition:
            raise ProductError("evidence_incomplete", message)

    require(result.get("run_id") == metadata.get("run_id"), "Run identities disagree.")
    require(result.get("measurement_mode") == metadata.get("measurement_mode")
            and result.get("measurement_mode") in {"real_firmware", "synthetic_test"},
            "Measurement modes disagree.")
    require({"result.json", "report.md"} <= artifacts.keys(), "Terminal result artifacts are missing.")
    accounting = result.get("accounting")
    if accounting is None:
        require(snapshot["state"] != "completed" and not snapshot["attempts"],
                "Missing evaluator accounting cannot describe a completed execution.")
        return
    require({"firmware.elf", "project.json"} <= artifacts.keys(), "Executable project artifacts are missing.")
    require(result.get("firmware_sha256") == metadata.get("firmware", {}).get("firmware_sha256")
            == artifacts["firmware.elf"]["sha256"], "Retained firmware identities disagree.")
    attempted = accounting.get("attempted_executions")
    require(type(attempted) is int and attempted >= len(snapshot["attempts"]),
            "Attempt ledger and evaluator accounting disagree; interrupted accounting may be unknown.")
    gap = attempted - len(snapshot["attempts"])
    require(gap == 0 or (snapshot["state"] in {"failed", "cancelled"}
                        and result.get("execution_evidence") == "incomplete"),
            "Completed result cannot contain missing execution receipts.")
    config = ProductConfig.from_dict(metadata["configuration"])
    budget = accounting.get("execution_budget")
    require(type(budget) is int and 0 <= attempted <= budget
            and accounting.get("budget_remaining") == budget - attempted,
            "Execution budget accounting is inconsistent.")
    if metadata.get("operation") == "search":
        require(budget == metadata.get("configuration", {}).get("execution_budget"),
                "Recorded search budget differs from its declared configuration.")
    successful = failures = triggers = 0
    first_trigger = None
    first_values = None
    for index, item in enumerate(snapshot["attempts"], 1):
        record = item["record"]
        require(config.input_space.accepts(tuple(record["input"])), "Retained input is outside its configured input space.")
        feedback, evidence = record.get("feedback"), record.get("evidence", {})
        require(evidence.get("measurement_mode") == result["measurement_mode"],
                "Attempt measurement mode disagrees.")
        status = feedback.get("status") if type(feedback) is dict else None
        if feedback is not None:
            require(type(feedback.get("execution_index")) is int and feedback["execution_index"] == index
                    and type(feedback.get("budget_remaining")) is int and feedback["budget_remaining"] == budget - index,
                    "Retained feedback index or budget contradicts evaluator accounting.")
        if status in {"safe", "triggered"}:
            require(not record.get("interrupted") and all(evidence.get(key) is True for key in
                    ("guest_dispatched", "input_injected", "completion_reached", "cleanup_verified")),
                    "Completed observation lacks required runtime evidence.")
            successful += 1
            if status == "triggered":
                triggers += 1
                if first_trigger is None:
                    first_trigger, first_values = index, record["input"]
        else:
            require(status == "infrastructure_failure" or (status is None and record.get("interrupted") is True),
                    "Charged attempt lacks a recognized evaluator outcome.")
            failures += 1
        counts = record.get("accounting", {})
        require(counts.get("attempted_executions") == index
                and counts.get("successful_executions") == successful
                and counts.get("infrastructure_failures") == failures
                and counts.get("failure_triggering_executions") == triggers,
                "Attempt accounting contradicts its observations.")
    if gap:
        # A persisted evaluator result is retained as a statement of its counters;
        # missing receipts remain missing, and cannot verify guest execution.
        final_successes, final_errors = accounting.get("successful_executions"), accounting.get("infrastructure_failures")
        require(type(final_successes) is int and type(final_errors) is int
                and final_successes >= successful and final_errors >= failures
                and final_successes + final_errors == attempted,
                "Partial final accounting is internally inconsistent.")
        return {"status": "incomplete_receipts", "missing_receipts": gap,
                "execution_verification": "failed", "counters_source": "persisted_evaluator_result"}
    require(accounting.get("successful_executions") == successful
            and accounting.get("infrastructure_failures") == failures
            and accounting.get("failure_triggering_executions") == triggers
            and accounting.get("first_failure_execution") == first_trigger
            and accounting.get("failure_found") is (first_trigger is not None)
            and result.get("triggering_input") == first_values,
            "Terminal discovery/accounting contradicts retained observations.")
    if snapshot["attempts"]:
        require(accounting == snapshot["attempts"][-1]["record"]["accounting"],
                "Final accounting differs from the last authoritative evaluator receipt.")
    require(accounting.get("aborted") is (failures > 0), "Abort state contradicts infrastructure failures.")
    require(snapshot["state"] != "completed" or (failures == 0 and result.get("execution_evidence") == "complete"),
            "Completed result contains incomplete or failed observations.")
    return {"status": "receipt_accounting_consistent", "missing_receipts": 0,
            "inspection_is_not_independent_execution_verification": True}


def inspect_run(run_dir):
    snapshot, artifacts = _read_run(run_dir)
    return {
        "schema_version": 1, "run_directory": str(Path(run_dir).absolute()),
        "state": snapshot["state"], "metadata": snapshot["metadata"],
        "result": snapshot["result"], "attempts_recorded": len(snapshot["attempts"]),
        "artifact_verification": artifacts,
        "accounting_verification": snapshot.get("accounting_verification", {"status": "unknown"}),
        "uncommitted_result_artifact": snapshot["result"] is not None
        and snapshot["result"].get("accounting_status") == "unknown"
        and "result.json" in artifacts,
        "recovery_required": snapshot["state"] in {"created", "running"},
        "inspection_is_not_execution_verification": True,
    }


def reproduce_run(run_dir, output_dir, attempts=3, *, cancel_event=None, event_callback=None,
                  _executor_factory=None):
    if type(attempts) is not int or not 1 <= attempts <= 100:
        raise ProductError("configuration_error", "Reproduction attempts must be from 1 to 100.")
    snapshot, _ = _read_run(run_dir)
    result = snapshot["result"]
    if result is None or result.get("triggering_input") is None:
        raise ProductError("no_saved_trigger", "No exact triggering input is retained in this run.")
    if result["measurement_mode"] != "real_firmware" and _executor_factory is None:
        raise ProductError("synthetic_result", "Synthetic test observations cannot be promoted to real-firmware reproduction.")
    config = load_config(Path(run_dir) / "project.json")
    identity = inspect_elf(config)
    if identity["firmware_sha256"] != result["firmware_sha256"]:
        raise ProductError("firmware_changed", "Saved firmware identity changed; reproduction rejected.")
    current_tools = discover(config).to_dict()
    if current_tools != snapshot["metadata"]["tools"]:
        raise ProductError("toolchain_changed", "Selected tools changed; this is not an equivalent-environment reproduction.")
    return _execute_project(
        config, output_dir, cancel_event=cancel_event, event_callback=event_callback,
        replay_values=result["triggering_input"], replay_attempts=attempts,
        parent={"run_id": result["run_id"], "operation": "reproduction"},
        _executor_factory=_executor_factory,
    )


def recover_run(run_dir):
    RunStore.recover_interrupted(Path(run_dir))
    return inspect_run(run_dir)


def restart_run(run_dir, output_dir, *, cancel_event=None, event_callback=None):
    snapshot, _ = _read_run(run_dir)
    if snapshot["state"] not in {"interrupted", "cancelled", "failed"}:
        raise ProductError("restart_not_authorized", "Only an explicitly interrupted/cancelled/failed run can be restarted.")
    config = load_config(Path(run_dir) / "project.json")
    identity = inspect_elf(config)
    if identity["firmware_sha256"] != snapshot["metadata"].get("firmware", {}).get("firmware_sha256"):
        raise ProductError("firmware_changed", "Saved firmware identity changed; restart rejected.")
    if discover(config).to_dict() != snapshot["metadata"].get("tools"):
        raise ProductError("toolchain_changed", "Selected tools changed; prepare a separate project instead of equivalent restart.")
    return _execute_project(config, output_dir, cancel_event=cancel_event, event_callback=event_callback,
                            parent={"run_id": snapshot["metadata"]["run_id"], "operation": "restart",
                                    "warning": "Fresh full search; abandoned work may be repeated."})


def export_run(run_dir, output_dir):
    snapshot, _ = _read_run(run_dir)
    if snapshot["result"] is None:
        raise ProductError("incomplete_run", "No terminal result is available for export.")
    output = Path(output_dir)
    if output.is_symlink() or output.exists():
        raise ProductError("output_exists", "Export refuses an existing output directory.")
    output.mkdir(parents=True)
    # Private administrative export: paths and diagnostics require publication review.
    data = json.dumps(snapshot, sort_keys=True, indent=2, allow_nan=False) + "\n"
    (output / "evidence.json").write_text(data, encoding="utf-8")
    (output / "report.md").write_text(_report(snapshot["result"]), encoding="utf-8")
    manifest = {}
    for name in ("evidence.json", "report.md"):
        content = (output / name).read_bytes()
        manifest[name] = {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}
    (output / "SHA256SUMS").write_text(
        "".join(f"{entry['sha256']}  {name}\n" for name, entry in sorted(manifest.items())), encoding="utf-8")
    return {"schema_version": 1, "success": True, "output_directory": str(output.absolute()),
            "files": manifest, "private_administrative_export": True,
            "firmware_executed": False}


def run_demo(output_dir, *, cancel_event=None, event_callback=None):
    from .example import build_example
    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        raise ProductError("output_exists", "Demo refuses an existing output directory.")
    output.mkdir(parents=True)
    built = build_example(output / "build")
    config_file = built["config_file"]
    validated = validate_project(config_file)
    search = run_project(config_file, output / "search", cancel_event=cancel_event, event_callback=event_callback)
    if search["outcome"] != "configured_failure_observed" or search["triggering_input"] != [2, 1]:
        raise ProductError("demo_verification_failed", "Independent example did not produce its defined triggering vector.")
    replay = reproduce_run(output / "search", output / "reproduction", 3,
                           cancel_event=cancel_event, event_callback=event_callback)
    if replay["outcome"] != "reproduced_in_emulator":
        raise ProductError("demo_verification_failed", "Independent example reproduction failed.")
    exported = export_run(output / "search", output / "export")
    summary = {"schema_version": 1, "success": True, "measurement_mode": "real_firmware",
               "output_directory": str(output.absolute()), "validation": validated,
               "search": search, "reproduction": replay, "export": exported,
               "research_campaign_executed": False}
    (output / "demo.json").write_text(json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


def build_example_project(output_dir, *, cancel_event=None, event_callback=None):
    """Supervised desktop preparation: compile the independent example only."""
    from .example import build_example
    cancel = cancel_event if cancel_event is not None else threading.Event()
    if cancel.is_set():
        raise KeyboardInterrupt("Example build cancelled before admission.")
    _emit(event_callback, {"type": "build_started", "firmware_dispatched": False})
    built = build_example(output_dir, cancel_event=cancel)
    if cancel.is_set():
        raise KeyboardInterrupt("Example build cancelled; no firmware was executed.")
    return {"success": True, **built, "firmware_dispatched": False,
            "operation": "independent_example_build"}
