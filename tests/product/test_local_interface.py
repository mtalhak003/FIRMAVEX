"""Local contract/security tests; synthetic responses are not native evidence."""

import io
import json
import socket
import threading
import time
import pytest
from firmavex.product.errors import ProductError
from firmavex.product.local import LocalSession
from firmavex.product.local_stdio import serve
from firmavex.product.protocol import decode_json_object, encode_json_object


class Fake:
    cancellation_grace = 0.1

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def execute(self, command, payload, *, cancel_event, event_callback, timeout):
        self.calls.append((command, payload))
        self.started.set()
        for i in range(100):
            event_callback(
                {
                    "sequence": i + 1,
                    "kind": "progress",
                    "payload": {"stage": "synthetic"},
                }
            )
        while not self.release.wait(0.01):
            if cancel_event.is_set():
                return {"status": "cancelled", "measurement_mode": "synthetic_test"}
        return {"status": "passed", "measurement_mode": "synthetic_test"}


def finish(session, identifier):
    deadline = time.monotonic() + 10
    while session.status(identifier)["state"] in {"running", "cancellation_requested"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    return session.result(identifier)


def test_real_stdio_worker_negotiation_is_offline(monkeypatch):
    monkeypatch.setattr(
        socket, "socket", lambda *args, **kwargs: pytest.fail("Network opened")
    )
    with LocalSession() as session:
        job = session.submit("capabilities", {})
        result = finish(session, job)
        assert result["result"]["transport"] == "owned_stdio_pipes"
        assert result["result"]["policy"]["sandboxed"] is False
        assert (
            result["result"]["support"]["current_runtime_qualification"] == "not_probed"
        )


def test_submission_snapshot_cancel_retention_and_session_ownership():
    fake = Fake()
    with LocalSession(supervisor=fake) as session:
        payload = {"profile": "riscv32-virt"}
        identifier = session.submit("backend_check", payload)
        assert fake.started.wait(2)
        payload["profile"] = "changed"
        assert fake.calls[0][1]["profile"] == "riscv32-virt"
        with pytest.raises(ProductError, match="One active"):
            session.submit("doctor", {})
        with pytest.raises(ProductError, match="wait for terminal"):
            session.result(identifier)
        session.cancel(identifier)
        terminal = finish(session, identifier)
        assert terminal["result"]["status"] == "cancelled"
        assert len(session.status(identifier)["events"]) <= 64
        copied = session.result(identifier)
        copied["result"]["status"] = "forged"
        assert session.result(identifier)["result"]["status"] == "cancelled"
        with LocalSession() as other:
            with pytest.raises(ProductError, match="belong"):
                other.status(identifier)
        assert session.forget(identifier)["saved_files_deleted"] is False
        with pytest.raises(ProductError):
            session.status(identifier)


@pytest.mark.parametrize(
    "command,payload,timeout",
    [
        ("setup_runtime", {}, 10),
        ("shutdown", {}, 10),
        ("doctor", {"extra": 1}, 10),
        ("doctor", {}, True),
        ("doctor", {}, float("inf")),
        ("doctor", {}, 0),
        ("doctor", {}, 86401),
        (
            "backend_execute",
            {"request": {}, "output_dir": "never", "trust": "untrusted"},
            10,
        ),
        ("backend_execute", {"request": {}, "output_dir": "never", "trust": []}, 10),
    ],
)
def test_rejected_requests_never_dispatch(command, payload, timeout):
    fake = Fake()
    with LocalSession(supervisor=fake) as session:
        with pytest.raises(ProductError):
            session.submit(command, payload, timeout_seconds=timeout)
    assert not fake.calls


def test_eof_cancels_and_closed_session_rejects_submission():
    fake = Fake()
    session = LocalSession(supervisor=fake)
    job = session.submit("doctor", {})
    assert fake.started.wait(2)
    session.close()
    assert session.result(job)["result"]["status"] == "cancelled"
    with pytest.raises(ProductError, match="closed"):
        session.submit("doctor", {})


def test_control_flow_failure_never_becomes_success():
    class Broken(Fake):
        def execute(self, *args, **kwargs):
            raise SystemExit("synthetic interruption")

    with LocalSession(supervisor=Broken()) as session:
        job = session.submit("doctor", {})
        result = finish(session, job)
        assert result["state"] == "failed" and result["result"] is None
        assert result["error"]["category"] == "worker_interrupted"


def frame(operation="negotiate", payload=None, request_id="1", version=1):
    return encode_json_object(
        {
            "interface_version": version,
            "request_id": request_id,
            "operation": operation,
            "payload": {} if payload is None else payload,
        }
    )


def test_gateway_negotiation_and_duplicate_request_fail_closed():
    out = io.BytesIO()
    assert serve(io.BytesIO(frame() + frame()), out) == 1
    responses = [decode_json_object(line) for line in out.getvalue().splitlines()]
    assert responses[0]["ok"] is True
    assert (
        responses[1]["ok"] is False
        and responses[1]["payload"]["category"] == "protocol_error"
    )


@pytest.mark.parametrize(
    "raw",
    [
        frame(version=True),
        frame(version=2),
        b'{"request_id":"x","request_id":"y"}\n',
        b"[]\n",
        b"{bad}\n",
        b"x" * 1048577,
    ],
    ids=["boolean_version", "unsupported_version", "duplicate_request_id",
         "array", "malformed_json", "oversized_frame"],
)
def test_malformed_gateway_frames_fail_closed(raw):
    out = io.BytesIO()
    assert serve(io.BytesIO(raw), out) == 1
    assert decode_json_object(out.getvalue())["ok"] is False


def test_capacity_is_bounded_and_forget_releases_metadata_only():
    fake = Fake()
    fake.release.set()
    with LocalSession(supervisor=fake) as session:
        identifiers = []
        for _ in range(32):
            identifier = session.submit("doctor", {})
            finish(session, identifier)
            identifiers.append(identifier)
        with pytest.raises(ProductError, match="Forget"):
            session.submit("doctor", {})
        assert len(fake.calls) == 32
        session.forget(identifiers[0])
        finish(session, session.submit("doctor", {}))


def test_real_worker_crash_is_not_a_finished_test():
    import sys
    from firmavex.product.supervisor import Supervisor

    supervisor = Supervisor(
        worker_argv=[sys.executable, "-c", "raise SystemExit(7)"], cancellation_grace=1
    )
    with LocalSession(supervisor=supervisor) as session:
        identifier = session.submit("doctor", {})
        result = finish(session, identifier)
        assert result["state"] == "failed" and result["result"] is None
        assert result["error"]["category"] == "worker_interrupted"
