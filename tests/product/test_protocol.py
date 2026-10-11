"""Transport rejects malformed records instead of guessing their meaning."""

import json

import pytest

from firmavex.product.errors import ProductError
from firmavex.product.protocol import (
    MAX_LINE_BYTES, decode_command, decode_event, encode_command, encode_event,
)


def test_command_roundtrip():
    value = decode_command(encode_command("job-1", "run", {"config": "space name.json", "output_dir": "out"}))
    assert value == {"schema_version": 1, "request_id": "job-1", "command": "run", "payload": {"config": "space name.json", "output_dir": "out"}}


def test_event_roundtrip():
    assert decode_event(encode_event("job-1", 3, "progress", {"charged_attempts": 2}))["sequence"] == 3


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"schema_version": 2}, {"schema_version": "1"},
    {"request_id": ""}, {"request_id": "x" * 129}, {"request_id": "a\nb"},
    {"command": "unknown"}, {"command": 1}, {"payload": []}, {"extra": 1},
])
def test_invalid_command(change):
    value = {"schema_version": 1, "request_id": "x", "command": "doctor", "payload": {}}
    value.update(change)
    with pytest.raises(ProductError, match="."):
        decode_command(json.dumps(value))


@pytest.mark.parametrize("text", [
    b"\xff", "[]", "{}", "null", "not json",
    '{"schema_version":1,"schema_version":1,"request_id":"x","command":"doctor","payload":{}}',
    '{"schema_version":1,"request_id":"x","command":"doctor","payload":{"x":NaN}}',
    '{"schema_version":1,"request_id":"x","command":"doctor","payload":{"x":Infinity}}',
])
def test_malformed_json_rejected(text):
    with pytest.raises(ProductError):
        decode_command(text)


@pytest.mark.parametrize("sequence", [True, 0, -1, "1", None])
def test_exact_event_sequence_type(sequence):
    with pytest.raises(ProductError):
        encode_event("job", sequence, "result", {})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), (1, 2)])
def test_non_json_payload_rejected(value):
    with pytest.raises(ProductError):
        encode_command("job", "doctor", {"value": value})


def test_line_size_limit():
    with pytest.raises(ProductError, match="size limit"):
        decode_command(b" " * (MAX_LINE_BYTES + 1))
    with pytest.raises(ProductError, match="size limit"):
        encode_event("x", 1, "result", {"large": "x" * MAX_LINE_BYTES})


def test_depth_limit():
    value = {}
    for _ in range(34):
        value = {"nested": value}
    with pytest.raises(ProductError, match="nesting"):
        encode_command("x", "doctor", value)


def test_unknown_event_kind_rejected():
    with pytest.raises(ProductError):
        encode_event("x", 1, "done_without_evidence", {})
