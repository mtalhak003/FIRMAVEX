"""Strict, bounded JSON-line transport shared by the worker and its supervisor."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import ProductError

SCHEMA_VERSION = 1
MAX_LINE_BYTES = 1_048_576
COMMANDS = frozenset({"doctor", "validate", "run", "reproduce", "inspect", "export", "recover", "restart", "cancel", "shutdown", "demo", "build_example"})
EVENT_KINDS = frozenset({"accepted", "progress", "result", "error", "cancelling", "shutdown"})
_REQUEST_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def _fail(message: str) -> None:
    raise ProductError("protocol_error", message)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("Duplicate JSON object keys are forbidden.")
        result[key] = value
    return result


def _json_value(value: Any, depth: int = 0) -> None:
    if depth > 32:
        _fail("JSON nesting exceeds the protocol limit.")
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item, depth + 1)
        return
    _fail("Protocol values must be finite, ordinary JSON values.")


def _decode(line: str | bytes) -> dict[str, Any]:
    try:
        if isinstance(line, bytes):
            if len(line) > MAX_LINE_BYTES:
                _fail("Protocol line exceeds the size limit.")
            line = line.decode("utf-8", errors="strict")
        elif type(line) is str:
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                _fail("Protocol line exceeds the size limit.")
        else:
            _fail("Protocol line must be UTF-8 text.")
        value = json.loads(line, object_pairs_hook=_object,
                           parse_constant=lambda _: _fail("Nonfinite JSON values are forbidden."))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProductError("protocol_error", "Malformed protocol JSON.") from exc
    if type(value) is not dict:
        _fail("Protocol message must be an object.")
    _json_value(value)
    return value


def _base(value: dict[str, Any], keys: set[str]) -> None:
    if set(value) != keys:
        _fail("Protocol message contains missing or unsupported fields.")
    if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
        _fail("Unsupported protocol schema version.")
    if type(value["request_id"]) is not str or _REQUEST_ID.fullmatch(value["request_id"]) is None:
        _fail("Invalid request identifier.")
    if type(value["payload"]) is not dict:
        _fail("Protocol payload must be an object.")


def decode_command(line: str | bytes) -> dict[str, Any]:
    value = _decode(line)
    _base(value, {"schema_version", "request_id", "command", "payload"})
    if type(value["command"]) is not str or value["command"] not in COMMANDS:
        _fail("Unsupported worker command.")
    return value


def decode_event(line: str | bytes) -> dict[str, Any]:
    value = _decode(line)
    _base(value, {"schema_version", "request_id", "sequence", "kind", "payload"})
    if type(value["sequence"]) is not int or value["sequence"] < 1:
        _fail("Event sequence must be a positive integer.")
    if type(value["kind"]) is not str or value["kind"] not in EVENT_KINDS:
        _fail("Unsupported event kind.")
    return value


def encode_command(request_id: str, command: str, payload: dict[str, Any]) -> bytes:
    return _encode({"schema_version": SCHEMA_VERSION, "request_id": request_id,
                    "command": command, "payload": payload}, decode_command)


def encode_event(request_id: str, sequence: int, kind: str, payload: dict[str, Any]) -> bytes:
    return _encode({"schema_version": SCHEMA_VERSION, "request_id": request_id,
                    "sequence": sequence, "kind": kind, "payload": payload}, decode_event)


def _encode(value: dict[str, Any], validate: Any) -> bytes:
    _json_value(value)
    try:
        data = (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProductError("protocol_error", "Cannot encode protocol message.") from exc
    validate(data)
    return data
