import io
import threading
import time
from types import SimpleNamespace

import pytest

from firmavex.product.errors import ProductError
from firmavex.product.protocol import MAX_LINE_BYTES, decode_command, decode_event, encode_command
from firmavex.product.worker import Worker, serve


def message(command, payload=None, identifier="job"):
    return decode_command(encode_command(identifier, command, payload or {}))


def events(stream):
    return [decode_event(line) for line in stream.getvalue().splitlines()]


def joined(worker):
    worker._thread.join(timeout=2)
    assert not worker._thread.is_alive()


def synthetic(**extra):
    return {"measurement_mode": "synthetic_test", **extra}


def test_doctor_dispatch_and_monotonic_events():
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(doctor=lambda: synthetic(available=True)))
    worker.handle(message("doctor"))
    joined(worker)
    records = events(output)
    assert [e["sequence"] for e in records] == [1, 2]
    assert records[-1]["payload"]["measurement_mode"] == "synthetic_test"
    assert [e["kind"] for e in records] == ["accepted", "result"]


@pytest.mark.parametrize("command,payload,attribute,arguments", [
    ("validate", {"config": "c"}, "validate_project", ("c",)),
    ("inspect", {"run_dir": "r"}, "inspect_run", ("r",)),
    ("export", {"run_dir": "r", "output_dir": "o"}, "export_run", ("r", "o")),
    ("recover", {"run_dir": "r"}, "recover_run", ("r",)),
])
def test_readonly_or_export_commands_dispatch(command, payload, attribute, arguments):
    calls = []
    def service(*args):
        calls.append(args)
        return synthetic()
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(**{attribute: service}))
    worker.handle(message(command, payload))
    joined(worker)
    assert calls == [arguments]
    assert events(output)[-1]["kind"] == "result"


@pytest.mark.parametrize("command,payload,attribute", [
    ("run", {"config": "c", "output_dir": "o"}, "run_project"),
    ("reproduce", {"run_dir": "r", "output_dir": "o", "attempts": 2}, "reproduce_run"),
    ("demo", {"output_dir": "o"}, "run_demo"),
    ("restart", {"run_dir": "r", "output_dir": "o"}, "restart_run"),
])
def test_execution_services_receive_cancel_and_progress(command, payload, attribute):
    observed = []
    def service(*args, cancel_event, event_callback):
        observed.append((args, cancel_event))
        event_callback(synthetic(attempted_executions=1))
        return synthetic(status="no_failure_observed_within_budget")
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(**{attribute: service}))
    worker.handle(message(command, payload))
    joined(worker)
    assert isinstance(observed[0][1], threading.Event)
    assert [e["kind"] for e in events(output)] == ["accepted", "progress", "result"]


def test_active_job_refuses_parallel_dispatch_and_accepts_cancel():
    admitted = threading.Event()
    finished = threading.Event()
    calls = []
    def run(*args, cancel_event, event_callback):
        calls.append(args)
        admitted.set()
        assert cancel_event.wait(2)
        finished.set()
        raise KeyboardInterrupt
    services = SimpleNamespace(run_project=run, inspect_run=lambda _: synthetic(status="cancelled", attempted_executions=1))
    output = io.BytesIO()
    worker = Worker(output, services)
    worker.handle(message("run", {"config": "c", "output_dir": "o"}))
    assert admitted.wait(2)
    worker.handle(message("run", {"config": "c", "output_dir": "o2"}, "second"))
    worker.handle(message("cancel", {"job_request_id": "job"}, "cancel"))
    joined(worker)
    assert len(calls) == 1 and finished.is_set()
    records = events(output)
    assert any(e["payload"].get("category") == "worker_busy" for e in records)
    terminal = [e for e in records if e["request_id"] == "job"][-1]
    assert terminal["kind"] == "error"
    assert terminal["payload"]["category"] == "cancelled"
    assert terminal["payload"]["details"]["partial_result"]["attempted_executions"] == 1


def test_eof_cancels_and_joins_job_without_completed_record():
    output = io.BytesIO()
    ended = threading.Event()
    def run(*args, cancel_event, event_callback):
        assert cancel_event.wait(2)
        ended.set()
        raise KeyboardInterrupt
    services = SimpleNamespace(run_project=run, inspect_run=lambda _: synthetic(status="cancelled"))
    exitcode = serve(io.BytesIO(encode_command("job", "run", {"config": "c", "output_dir": "o"})), output, services)
    assert ended.is_set() and exitcode == 1
    assert not any(e["kind"] == "result" for e in events(output))


def test_error_diagnostics_retained():
    def doctor():
        raise ProductError("missing_tool", "No GDB", {"executable": "gdb"})
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(doctor=doctor))
    worker.handle(message("doctor"))
    joined(worker)
    assert events(output)[-1]["payload"] == {"category": "missing_tool", "message": "No GDB", "details": {"executable": "gdb"}}


def test_unexpected_failure_is_not_success():
    def doctor():
        raise RuntimeError("broken service")
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(doctor=doctor))
    worker.handle(message("doctor"))
    joined(worker)
    assert worker.failed
    assert events(output)[-1]["payload"]["category"] == "worker_failure"


@pytest.mark.parametrize("command,payload", [
    ("doctor", {"unexpected": True}), ("run", {"config": "c"}),
    ("inspect", {"run_dir": "r", "output_dir": "o"}),
])
def test_invalid_fields_do_not_dispatch(command, payload):
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace())
    worker.handle(message(command, payload))
    assert worker._thread is None
    assert events(output)[-1]["kind"] == "error"


def test_duplicate_request_id_does_not_dispatch_twice():
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(doctor=lambda: synthetic()))
    worker.handle(message("doctor"))
    joined(worker)
    worker.handle(message("doctor"))
    assert events(output)[-1]["payload"]["category"] == "protocol_error"


def test_malformed_line_stops_worker():
    output = io.BytesIO()
    assert serve(io.BytesIO(b"bad\n"), output, SimpleNamespace()) == 1
    assert events(output)[-1]["payload"]["category"] == "protocol_error"


@pytest.mark.parametrize("attempts", [0, -1, True, 101, "3"])
def test_reproduction_is_bounded(attempts):
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace())
    worker.handle(message("reproduce", {"run_dir": "r", "output_dir": "o", "attempts": attempts}))
    joined(worker)
    assert events(output)[-1]["payload"]["category"] == "configuration_error"


def test_shutdown_does_not_accept_new_work():
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace())
    worker.handle(message("shutdown", identifier="shutdown"))
    worker.handle(message("doctor"))
    assert worker.stopping
    assert events(output)[-1]["payload"]["category"] == "worker_stopping"


def test_failed_encoding_does_not_consume_an_event_sequence():
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace())
    worker.emit("job", "accepted", {})
    with pytest.raises(ProductError):
        worker.emit("job", "result", {"unbounded": "x" * MAX_LINE_BYTES})
    worker.emit("job", "error", ProductError("protocol_error", "Too large").to_dict())
    assert [event["sequence"] for event in events(output)] == [1, 2]


def test_diagnostic_preview_preserves_original_records_vectors_and_counts():
    import hashlib
    stdout = "é" * 5000
    original = synthetic(
        triggering_input=[2, 1], accounting={"attempted_executions": 10},
        evidence={"gdb_stdout": stdout, "stderr": "x" * 12000},
    )
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace())
    worker.emit("job", "result", original)
    received = events(output)[-1]["payload"]
    assert original["evidence"]["gdb_stdout"] == stdout
    assert len(received["evidence"]["gdb_stdout"].encode("utf-8")) == 4096
    assert received["triggering_input"] == original["triggering_input"]
    assert received["accounting"] == original["accounting"]
    metadata = received["transport_preview"]
    assert metadata["archive_records_modified"] is False
    assert metadata["diagnostics_truncated"] is True
    record = metadata["truncated_fields"][0]
    assert record["original_sha256"] == hashlib.sha256(stdout.encode()).hexdigest()
    assert record["original_utf8_bytes"] == len(stdout.encode())


def test_oversized_result_sends_protocol_error_with_archive_path_and_no_gap():
    output = io.BytesIO()
    services = SimpleNamespace(run_project=lambda *args, **kwargs: synthetic(
        triggering_input=list(range(200000)), untouched="x" * MAX_LINE_BYTES))
    worker = Worker(output, services)
    worker.handle(message("run", {"config": "c", "output_dir": "archive"}))
    joined(worker)
    records = events(output)
    assert [event["sequence"] for event in records] == [1, 2]
    assert records[-1]["kind"] == "error"
    assert records[-1]["payload"]["category"] == "protocol_error"
    assert records[-1]["payload"]["details"]["run_directory"] == "archive"


def test_oversized_error_payload_has_a_bounded_truthful_fallback():
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace())
    worker._active_output_dir = "archive"
    worker.emit("job", "error", ProductError("original_error", "error", {
        "partial_result": {"untouched": "x" * MAX_LINE_BYTES}}).to_dict())
    record = events(output)[-1]
    assert record["sequence"] == 1
    assert record["payload"]["category"] == "protocol_error"
    assert record["payload"]["details"]["run_directory"] == "archive"


def test_runtime_setup_failure_transports_diagnostic_without_generic_worker_error(tmp_path, monkeypatch):
    from firmavex.product import runtime_setup
    def failed(**kwargs):
        raise PermissionError(13, 'private credential')
    monkeypatch.setattr(runtime_setup, '_install_vendor_runtime', failed)
    output = io.BytesIO()
    worker = Worker(output, SimpleNamespace(setup_runtime=lambda **kwargs:
        runtime_setup.install_vendor_runtime(root=tmp_path / 'runtimes', **kwargs)))
    worker.handle(message('setup_runtime'))
    joined(worker)
    error = events(output)[-1]['payload']
    assert error['category'] == 'runtime_setup_io_failed'
    assert error['details']['diagnostic_file'] in error['message']
    assert 'private credential' not in str(error)
