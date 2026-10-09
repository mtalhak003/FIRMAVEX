"""Versioned administrator journals; atomic snapshots, never execution ledgers."""

from contextlib import contextmanager
from dataclasses import asdict
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from src.firmavex.protocols.record_codec import decode_evaluation, decode_record


class JournalError(ValueError):
    """Invalid, incompatible, or unsafe recovery data."""


def canonical_json(value) -> str:
    def check(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise JournalError("Journal keys must be strings.")
            for child in item.values():
                check(child)
        elif type(item) in (list, tuple):
            for child in item:
                check(child)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise JournalError("Journal values must be JSON data.")
        elif type(item) is float and not math.isfinite(item):
            raise JournalError("Journal numbers must be finite.")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(b"firmavex-journal-v1\0" + canonical_json(value).encode("utf-8")).hexdigest()


def experiment_id(plan_sha256: str, position: int) -> str:
    return "e-" + fingerprint({"plan_sha256": plan_sha256, "position": position})


def attempt_id(identifier: str, number: int) -> str:
    return "a-" + fingerprint({"experiment_id": identifier, "attempt_number": number})


def new_journal(protocol, context: dict, space) -> dict:
    plan = protocol.plan_to_dict()
    return {
        "schema_version": 1, "kind": "firmavex_campaign_journal",
        "plan": plan, "plan_sha256": fingerprint(plan),
        "context": json.loads(canonical_json(context)), "context_sha256": fingerprint(context),
        "input_space": asdict(space), "recovery_policy": "experiment_boundary_explicit_restart",
        "durability": {"directory_sync_unsupported_observed": False},
        "campaign_state": "planned", "completed": [], "attempts": [], "last_error": None,
    }


def _keys(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise JournalError(f"Invalid {label} fields.")


def _error(value):
    _keys(value, ("type", "message"), "attempt error")
    if any(type(value[key]) is not str for key in value) or not value["type"]:
        raise JournalError("Invalid interruption diagnostic.")


def _cleanup(action, original, label):
    try:
        action()
    except BaseException as secondary:
        if original is None:
            raise
        if isinstance(original, Exception) and not isinstance(secondary, Exception):
            raise secondary from original
        try:
            original.add_note(f"{label} failed: {type(secondary).__name__}: {secondary}")
        except BaseException:
            pass


def _close(descriptor, original=None):
    _cleanup(lambda: os.close(descriptor), original, "Journal descriptor cleanup")


def _close_stream(stream, original=None):
    _cleanup(stream.close, original, "Temporary journal close")


def validate_journal(payload, protocol, context, space) -> tuple:
    """Reject incompatible plans, contexts, histories, or result classifications."""
    from src.firmavex.protocols.recovery_context import validate_context

    _keys(payload, (
        "schema_version", "kind", "plan", "plan_sha256", "context", "context_sha256",
        "input_space", "recovery_policy", "durability", "campaign_state", "completed", "attempts", "last_error",
    ), "journal")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1 or payload["kind"] != "firmavex_campaign_journal":
        raise JournalError("Unsupported journal version or kind.")
    canonical_json(payload)
    validate_context(context, protocol)
    plan = protocol.plan_to_dict()
    if payload["plan_sha256"] != fingerprint(plan) or canonical_json(payload["plan"]) != canonical_json(plan):
        raise JournalError("Recovery plan or ordering differs from the frozen plan.")
    if payload["context_sha256"] != fingerprint(context) or canonical_json(payload["context"]) != canonical_json(context):
        raise JournalError("Recovery execution/provenance context differs.")
    if canonical_json(payload["input_space"]) != canonical_json(asdict(space)):
        raise JournalError("Recovery input space differs.")
    if payload["recovery_policy"] != "experiment_boundary_explicit_restart":
        raise JournalError("Unsupported recovery policy.")
    _keys(payload["durability"], ("directory_sync_unsupported_observed",), "durability metadata")
    if type(payload["durability"]["directory_sync_unsupported_observed"]) is not bool:
        raise JournalError("Directory-sync observation must be an exact boolean.")
    if type(payload["campaign_state"]) is not str or payload["campaign_state"] not in {"planned", "running", "interrupted", "completed"}:
        raise JournalError("Invalid campaign state.")
    if type(payload["completed"]) is not list or type(payload["attempts"]) is not list:
        raise JournalError("Completed records and attempts must be ordered lists.")
    specs = protocol.expand()
    completed_attempts = []
    previous = None
    position = 0
    by_id = {}
    for index, attempt in enumerate(payload["attempts"]):
        _keys(attempt, (
            "position", "experiment_id", "number", "attempt_id", "restart_of", "status",
            "partial_evaluation", "diagnostics", "error", "capture_error",
        ), "attempt")
        if type(attempt["position"]) is not int or attempt["position"] != position or position >= len(specs):
            raise JournalError("Attempt history skips or reorders the frozen plan.")
        number = previous["number"] + 1 if previous is not None and previous["position"] == position else 1
        identifier = experiment_id(payload["plan_sha256"], position)
        if type(attempt["number"]) is not int or attempt["number"] != number:
            raise JournalError("Invalid restarted-attempt number.")
        if attempt["experiment_id"] != identifier or attempt["attempt_id"] != attempt_id(identifier, number):
            raise JournalError("Invalid stable experiment/attempt identity.")
        restart_of = previous["attempt_id"] if number > 1 else None
        if attempt["restart_of"] != restart_of or (number > 1 and previous["status"] != "interrupted"):
            raise JournalError("Restart must identify an earlier interrupted attempt.")
        if type(attempt["status"]) is not str or attempt["status"] not in {"running", "interrupted", "completed"}:
            raise JournalError("Invalid attempt status.")
        if type(attempt["diagnostics"]) is not list or any(type(item) is not dict for item in attempt["diagnostics"]):
            raise JournalError("Attempt diagnostics must be administrative JSON objects.")
        if attempt["capture_error"] is not None and type(attempt["capture_error"]) is not str:
            raise JournalError("Invalid partial-accounting capture error.")
        if attempt["partial_evaluation"] is not None:
            decode_evaluation(attempt["partial_evaluation"], specs[position])
        if attempt["status"] == "interrupted":
            _error(attempt["error"])
        elif attempt["error"] is not None or attempt["partial_evaluation"] is not None or attempt["diagnostics"] or attempt["capture_error"] is not None:
            raise JournalError("Only interrupted attempts may contain partial accounting/diagnostics.")
        if attempt["status"] == "running" and index != len(payload["attempts"]) - 1:
            raise JournalError("A running attempt must be the last attempt.")
        by_id[attempt["attempt_id"]] = attempt
        if attempt["status"] == "completed":
            completed_attempts.append(attempt)
            position += 1
        previous = attempt
    if len(payload["completed"]) != len(completed_attempts):
        raise JournalError("Completed prefix and attempt history disagree.")
    records = []
    for position, (entry, attempt) in enumerate(zip(payload["completed"], completed_attempts)):
        _keys(entry, ("position", "experiment_id", "attempt_id", "record"), "completed entry")
        if (type(entry["position"]) is not int or entry["position"] != position
                or entry["experiment_id"] != attempt["experiment_id"] or entry["attempt_id"] != attempt["attempt_id"]):
            raise JournalError("Duplicate or out-of-order completed prefix.")
        records.append(decode_record(entry["record"], specs[position], space))
    last_error = payload["last_error"]
    if last_error is not None:
        _keys(last_error, ("position", "attempt_id", "type", "message"), "campaign interruption")
        if type(last_error["position"]) is not int or not 0 <= last_error["position"] <= len(records):
            raise JournalError("Invalid campaign interruption position.")
        _error({key: last_error[key] for key in ("type", "message")})
        if last_error["attempt_id"] is not None:
            if type(last_error["attempt_id"]) is not str:
                raise JournalError("Invalid campaign interruption attempt identity.")
            attempt = by_id.get(last_error["attempt_id"])
            if attempt is None or attempt["status"] != "interrupted" or attempt["position"] != last_error["position"]:
                raise JournalError("Campaign interruption identifies no interrupted attempt.")
            if {key: last_error[key] for key in ("type", "message")} != attempt["error"]:
                raise JournalError("Campaign interruption contradicts its attempt diagnostic.")
    state = payload["campaign_state"]
    final_attempt = payload["attempts"][-1] if payload["attempts"] else None
    if state == "planned" and (payload["attempts"] or records or last_error is not None):
        raise JournalError("Planned journal must not contain executed history.")
    if state == "running" and (final_attempt is None or final_attempt["status"] == "interrupted"):
        raise JournalError("Running journal requires an active attempt or completed boundary.")
    if state == "interrupted":
        if last_error is None:
            raise JournalError("Interrupted journal requires interruption information.")
        if last_error["position"] != len(records):
            raise JournalError("Current interruption must identify the unfinished experiment boundary.")
        if final_attempt is not None and final_attempt["status"] == "running":
            raise JournalError("An observed interruption must classify its unfinished attempt.")
        if last_error["attempt_id"] is not None and (
            final_attempt is None or last_error["attempt_id"] != final_attempt["attempt_id"]
        ):
            raise JournalError("Current interruption must identify the final interrupted attempt.")
    if state == "completed" and (len(records) != len(specs) or len(completed_attempts) != len(specs)):
        raise JournalError("Incomplete data cannot declare campaign completion.")
    return tuple(records)


def export_recovery_history(payload, protocol, context, space) -> dict:
    """Export validated, deterministic administrator history, never strategy data.

    Completed official records remain unchanged. Missing partial ledgers remain
    unknown; known-count subtotals do not assert the total physical work when
    any attempt lacks accounting. The export contains private diagnostics and
    must be reviewed before publication.
    """
    records = validate_journal(payload, protocol, context, space)
    completed = {
        entry["attempt_id"]: record
        for entry, record in zip(payload["completed"], records)
    }
    attempts = []
    completed_executions = abandoned_executions = unknown_attempts = 0
    unknown_abandoned_attempts = 0
    for attempt in payload["attempts"]:
        record = completed.get(attempt["attempt_id"])
        if record is not None:
            evaluation = asdict(record.run.evaluation)
            accounting = "completed_authoritative"
            completed_executions += evaluation["attempted_executions"]
        elif attempt["partial_evaluation"] is not None:
            evaluation = attempt["partial_evaluation"]
            accounting = "partial_authoritative"
            abandoned_executions += evaluation["attempted_executions"]
        else:
            evaluation = None
            accounting = "unknown"
            unknown_attempts += 1
            if attempt["status"] == "interrupted":
                unknown_abandoned_attempts += 1
        attempts.append({
            **attempt, "restarted": attempt["restart_of"] is not None,
            "included_in_completed_results": record is not None,
            "accounting_status": accounting, "evaluation": evaluation,
        })
    known_executions = completed_executions + abandoned_executions
    result = {
        "schema_version": 1, "kind": "firmavex_campaign_recovery_history",
        "journal_sha256": fingerprint(payload), "plan_sha256": payload["plan_sha256"],
        "context_sha256": payload["context_sha256"], "campaign_state": payload["campaign_state"],
        "durability": payload["durability"],
        "completed_records_sha256": fingerprint([entry["record"] for entry in payload["completed"]]),
        "summary": {
            "planned_experiments": len(payload["plan"]["experiments"]), "completed_experiments": len(records),
            "final_campaign_completed": payload["campaign_state"] == "completed",
            "experiment_attempts_recorded": len(attempts),
            "interrupted_attempts": sum(attempt["status"] == "interrupted" for attempt in attempts),
            "restart_attempts": sum(attempt["restarted"] for attempt in attempts),
            "interruption_observed": payload["last_error"] is not None or any(
                attempt["status"] == "interrupted" for attempt in attempts
            ),
            "known_completed_firmware_executions": completed_executions,
            "known_abandoned_firmware_executions": abandoned_executions,
            "unknown_abandoned_attempts": unknown_abandoned_attempts,
            "unknown_accounting_attempts": unknown_attempts,
            "known_physical_firmware_executions": known_executions,
            "physical_firmware_executions": known_executions if unknown_attempts == 0 else None,
        },
        "attempts": attempts, "last_error": payload["last_error"],
    }
    return json.loads(canonical_json(result))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JournalError("Duplicate JSON keys in journal.")
        result[key] = value
    return result


class JournalStore:
    """POSIX single-writer snapshots with explicit post-replacement uncertainty.

    A directory-fsync failure after replacement propagates: the new pathname
    may exist but crash durability is unknown. Unsupported directory sync is
    exposed through directory_sync_supported and retained cumulatively in
    campaign metadata. A false retained flag means no observed limitation,
    never a guarantee of directory support or power-loss durability.
    """

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.directory_sync_supported = None
        self._directory_sync_unsupported_observed = False

    def exists(self):
        return self.path.exists()

    @contextmanager
    def locked(self):
        try:
            import fcntl
        except ImportError as exc:
            raise JournalError("Durable campaigns require POSIX advisory file locks.") from exc
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(str(self.path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        primary = None
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise JournalError("Campaign journal is already owned by another runner.") from exc
            yield self
        except BaseException as exc:
            primary = exc
            raise
        finally:
            _close(descriptor, primary)

    def read(self):
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                                  parse_constant=lambda value: (_ for _ in ()).throw(JournalError(f"Nonfinite JSON value: {value}")))
            _keys(document, ("schema_version", "payload_sha256", "payload"), "snapshot envelope")
            if type(document["schema_version"]) is not int or document["schema_version"] != 1:
                raise JournalError("Unsupported journal envelope version.")
            if document["payload_sha256"] != fingerprint(document["payload"]):
                raise JournalError("Journal checksum mismatch.")
            payload = document["payload"]
            if (type(payload) is dict and payload.get("kind") == "firmavex_campaign_journal"
                    and type(payload.get("durability")) is dict
                    and payload["durability"].get("directory_sync_unsupported_observed") is True):
                self.directory_sync_supported = False
                self._directory_sync_unsupported_observed = True
            return payload
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise JournalError(f"Unable to read valid campaign journal: {exc}") from exc

    def write(self, payload, *, create=False):
        durability = payload.get("durability") if type(payload) is dict else None
        campaign_metadata = (type(payload) is dict and payload.get("kind") == "firmavex_campaign_journal"
                             and type(durability) is dict
                             and set(durability) == {"directory_sync_unsupported_observed"}
                             and type(durability["directory_sync_unsupported_observed"]) is bool)
        if campaign_metadata and self._directory_sync_unsupported_observed:
            durability["directory_sync_unsupported_observed"] = True
        self._write_once(payload, create=create)
        if (campaign_metadata and self._directory_sync_unsupported_observed
                and durability.get("directory_sync_unsupported_observed") is False):
            # Retain the limitation before returning success. One additional
            # replacement is enough: the cumulative observation is now true,
            # regardless of whether that replacement can sync its directory.
            durability["directory_sync_unsupported_observed"] = True
            self._write_once(payload)

    def _write_once(self, payload, *, create=False):
        document = {"schema_version": 1, "payload_sha256": fingerprint(payload), "payload": payload}
        encoded = (canonical_json(document) + "\n").encode("utf-8")
        if create and self.exists():
            raise JournalError("Campaign journal already exists; choose explicit recovery.")
        temporary = None
        primary = None
        try:
            stream = tempfile.NamedTemporaryFile(mode="wb", dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp", delete=False)
            temporary = Path(stream.name)
            stream_primary = None
            try:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException as exc:
                stream_primary = exc
                raise
            finally:
                _close_stream(stream, stream_primary)
            os.replace(temporary, self.path)
            temporary = None
            directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            directory_primary = None
            try:
                try:
                    os.fsync(directory)
                    self.directory_sync_supported = True
                except OSError as exc:
                    if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                        raise
                    self.directory_sync_supported = False
                    self._directory_sync_unsupported_observed = True
            except BaseException as exc:
                directory_primary = exc
                raise
            finally:
                _close(directory, directory_primary)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            if temporary is not None:
                _cleanup(lambda: temporary.unlink(missing_ok=True), primary, "Temporary journal cleanup")
