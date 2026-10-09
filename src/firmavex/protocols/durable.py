"""Opt-in experiment-boundary checkpoints around the existing execution path."""

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.protocols.journal import (
    JournalStore, attempt_id, experiment_id, new_journal, validate_journal,
)
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.record_codec import validate_durable_record, validate_evaluation
from src.firmavex.protocols.recovery_context import validate_context
from src.firmavex.protocols.results import CampaignResult
from src.firmavex.protocols.runner import CampaignRegistry, _validate_space


def _error(exception: BaseException) -> dict:
    try:
        message = str(exception)
    except BaseException:
        message = "Exception message could not be captured."
    return {"type": type(exception).__name__, "message": message}


def _note(original: BaseException, message: str) -> None:
    try:
        original.add_note(message)
    except BaseException:
        # Reporting a secondary failure must not replace cancellation.
        pass


class DurableCampaignRunner:
    """Serial, single-writer campaigns; recovery never resumes a guest trial.

    The administrator supplies freshly captured compatible execution context.
    Journals and partial diagnostics stay administrative, outside the checkout.
    An unfinished attempt restarts only with explicit permission and a new ID.
    """

    def __init__(
        self, registry: CampaignRegistry, journal_path: str | Path,
        context_provider: Callable[[EvaluationProtocol], dict],
    ) -> None:
        if not callable(context_provider):
            raise ValueError("Durable campaigns require a fresh context provider.")
        self._registry = registry
        self._store = JournalStore(journal_path)
        self._context_provider = context_provider
        self._experiments = ExperimentRunner(registry)

    @property
    def experiment_runner(self) -> ExperimentRunner:
        """Latest evaluator owner, available only to the administrator."""
        return self._experiments

    def _interrupt(
        self, original: BaseException, protocol: EvaluationProtocol, context: dict,
        space, active_position: int | None, previous_owner=None,
    ) -> None:
        # Reload the actual replaced snapshot. A failing write may have failed
        # after replacement, so its in-memory predecessor is not authoritative.
        try:
            payload = self._store.read()
            records = validate_journal(payload, protocol, context, space)
            position = len(records)
            current = payload["attempts"][-1] if payload["attempts"] else None
            unfinished = current is not None and current["status"] == "running"
            interrupted_id = None
            if unfinished:
                position = current["position"]
                interrupted_id = current["attempt_id"]
                current["status"] = "interrupted"
                current["error"] = _error(original)
                owner = self._experiments.last_session if active_position == position else None
                # Position/spec equality cannot establish ownership after a
                # restart. The previous evaluator may have exactly the same
                # declaration, but its ledger still belongs to the old attempt.
                if owner is previous_owner:
                    owner = None
                if owner is not None:
                    errors = []
                    try:
                        evaluation = owner.result()
                        validate_evaluation(protocol.expand()[position], evaluation)
                        current["partial_evaluation"] = asdict(evaluation)
                    except BaseException as secondary:
                        errors.append("Partial accounting capture failed: " + _error(secondary)["message"])
                    try:
                        current["diagnostics"] = json.loads(json.dumps(owner.diagnostics(), allow_nan=False))
                    except BaseException as secondary:
                        errors.append("Diagnostic capture failed: " + _error(secondary)["message"])
                    current["capture_error"] = "; ".join(errors) or None
            payload["campaign_state"] = "interrupted"
            payload["last_error"] = {
                "position": position, "attempt_id": interrupted_id, **_error(original),
            }
            validate_journal(payload, protocol, context, space)
            self._store.write(payload)
        except BaseException as secondary:
            _note(original, "Interruption checkpoint failed: " + _error(secondary)["message"])

    def run(
        self, protocol: EvaluationProtocol, *, resume: bool = False,
        restart_interrupted: bool = False,
    ) -> CampaignResult:
        if type(protocol) is not EvaluationProtocol:
            raise ValueError("Durable campaigns require a canonical EvaluationProtocol.")
        if type(resume) is not bool or type(restart_interrupted) is not bool:
            raise ValueError("Recovery options must be exact booleans.")
        if restart_interrupted and not resume:
            raise ValueError("Interrupted restart requires explicit recovery.")
        plan = protocol.expand()
        plan_snapshot = protocol.plan_to_dict()
        if tuple(protocol.expand()) != plan:
            raise ValueError("Protocol expansion changed during campaign admission.")
        selected = {entry.benchmark_id for entry in self._registry.select(protocol.partition)}
        if any(identifier not in selected for identifier in protocol.benchmark_ids):
            raise ValueError("Campaign benchmark is unknown or outside its declared partition.")
        space = self._registry.input_space
        _validate_space(space)
        context = self._context_provider(protocol)
        validate_context(context, protocol)
        repository = Path(context["environment"]["repository"]).resolve()
        if self._store.path.resolve().is_relative_to(repository):
            raise ValueError("Campaign journals must be stored outside the repository.")
        if protocol.plan_to_dict() != plan_snapshot:
            raise ValueError("Protocol expansion changed while capturing context.")
        with self._store.locked():
            if resume:
                if not self._store.exists():
                    raise ValueError("No durable journal exists for recovery.")
                payload = self._store.read()
                records = list(validate_journal(payload, protocol, context, space))
            else:
                if self._store.exists():
                    raise ValueError("A journal already exists; recovery must be explicit.")
                payload = new_journal(protocol, context, space)
                records = []
                try:
                    self._store.write(payload, create=True)
                except BaseException as original:
                    self._interrupt(original, protocol, context, space, None)
                    raise
            if payload["campaign_state"] == "completed":
                return CampaignResult(protocol, tuple(records))
            unfinished = payload["attempts"] and payload["attempts"][-1]["status"] in {"running", "interrupted"}
            if unfinished and not restart_interrupted:
                raise ValueError("An unfinished experiment requires explicit restart_interrupted=True.")
            active_position = None
            previous_owner = None
            try:
                for position in range(len(records), len(plan)):
                    if protocol.plan_to_dict() != plan_snapshot:
                        raise ValueError("Frozen plan changed before experiment dispatch.")
                    previous = payload["attempts"][-1] if payload["attempts"] else None
                    restart = previous is not None and previous["position"] == position
                    if restart and previous["status"] == "running":
                        previous["status"] = "interrupted"
                        previous["error"] = {"type": "LostAttempt", "message": "No durable completion; process ended during this attempt."}
                    identifier = experiment_id(payload["plan_sha256"], position)
                    number = previous["number"] + 1 if restart else 1
                    current = {
                        "position": position, "experiment_id": identifier, "number": number,
                        "attempt_id": attempt_id(identifier, number),
                        "restart_of": previous["attempt_id"] if restart else None,
                        "status": "running", "partial_evaluation": None,
                        "diagnostics": [], "error": None, "capture_error": None,
                    }
                    payload["attempts"].append(current)
                    payload["campaign_state"] = "running"
                    validate_journal(payload, protocol, context, space)
                    self._store.write(payload)
                    # Establish the fresh-owner boundary before marking this
                    # attempt active or entering ExperimentRunner.run(). An
                    # interruption before it assigns a new session has unknown
                    # accounting, rather than the previous session's counters.
                    previous_owner = self._experiments.last_session
                    active_position = position
                    record = self._experiments.run(plan[position])
                    validate_durable_record(plan[position], record, space)
                    current["status"] = "completed"
                    payload["completed"].append({
                        "position": position, "experiment_id": identifier,
                        "attempt_id": current["attempt_id"], "record": record.to_dict(),
                    })
                    validate_journal(payload, protocol, context, space)
                    self._store.write(payload)
                    active_position = None
                    records.append(record)
                payload["campaign_state"] = "completed"
                validate_journal(payload, protocol, context, space)
                self._store.write(payload)
                return CampaignResult(protocol, tuple(records))
            except BaseException as original:
                self._interrupt(original, protocol, context, space, active_position, previous_owner)
                raise
