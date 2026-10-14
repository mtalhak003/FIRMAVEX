"""Version 1 local-session JSON-lines gateway. Owned pipes only; no listener."""

import sys
from .errors import ProductError
from .local import LocalSession
from .protocol import MAX_LINE_BYTES, decode_json_object, encode_json_object


def dispatch(session, request):
    if set(request) != {"interface_version", "request_id", "operation", "payload"}:
        raise ProductError("protocol_error", "Unexpected local request fields.")
    if (
        type(request["interface_version"]) is not int
        or request["interface_version"] != 1
    ):
        raise ProductError(
            "protocol_error",
            "Unsupported local interface version; negotiate version 1.",
        )
    identifier = request["request_id"]
    if (
        type(identifier) is not str
        or not 1 <= len(identifier) <= 128
        or not all(c.isascii() and (c.isalnum() or c in "_.:-") for c in identifier)
    ):
        raise ProductError("protocol_error", "Invalid local request identifier.")
    payload, operation = request["payload"], request["operation"]
    if type(payload) is not dict or type(operation) is not str:
        raise ProductError("protocol_error", "Invalid local request body.")
    fields = {
        "negotiate": (set(), set()),
        "submit": ({"command", "payload"}, {"timeout_seconds"}),
        "status": ({"job_id"}, set()),
        "cancel": ({"job_id"}, set()),
        "result": ({"job_id"}, set()),
        "forget": ({"job_id"}, set()),
    }
    if operation not in fields:
        raise ProductError("unsupported_operation", "Unsupported local operation.")
    required, optional = fields[operation]
    if not required <= payload.keys() or not payload.keys() <= required | optional:
        raise ProductError("invalid_request", "Invalid operation payload fields.")
    if operation == "negotiate":
        return session.capabilities()
    if operation == "submit":
        return {
            "job_id": session.submit(
                payload["command"],
                payload["payload"],
                timeout_seconds=payload.get("timeout_seconds", 3600),
            )
        }
    return getattr(session, operation)(payload["job_id"])


def serve(source, destination):
    used = set()
    with LocalSession() as session:
        for _ in range(65536):
            line = source.readline(MAX_LINE_BYTES + 1)
            if not line:
                return 0
            identifier = "protocol"
            try:
                request = decode_json_object(line)
                identifier = request.get("request_id", "protocol")
                if type(identifier) is not str or len(identifier) > 128:
                    identifier = "protocol"
                if identifier in used:
                    raise ProductError(
                        "protocol_error", "Request identifier already used."
                    )
                used.add(identifier)
                result = dispatch(session, request)
                response = {
                    "interface_version": 1,
                    "request_id": identifier,
                    "ok": True,
                    "payload": result,
                }
            except ProductError as exc:
                response = {
                    "interface_version": 1,
                    "request_id": identifier,
                    "ok": False,
                    "payload": exc.to_dict(),
                }
                # Bad framing/version/duplicates closes the private session.
                closing = exc.category == "protocol_error"
            else:
                closing = False
            try:
                data = encode_json_object(response)
            except ProductError:
                data = encode_json_object(
                    {
                        "interface_version": 1,
                        "request_id": identifier,
                        "ok": False,
                        "payload": ProductError(
                            "transport_limit",
                            "Response exceeds transport limits; inspect the saved archive.",
                        ).to_dict(),
                    }
                )
            destination.write(data)
            destination.flush()
            if closing:
                return 1
        return 1  # Bound retained identifiers and work on one connection.


def main():
    try:
        return serve(sys.stdin.buffer, sys.stdout.buffer)
    except ProductError as exc:
        print(exc.category + ": " + exc.message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
