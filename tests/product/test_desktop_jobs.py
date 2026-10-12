"""Desktop preparation jobs are supervised and never execute guest firmware."""

import io
import json
import subprocess
import sys
import threading

import pytest

from firmavex.product import services
from firmavex.product.example import _compile
from firmavex.product.protocol import encode_command
from firmavex.product.worker import serve


def test_supervised_example_command_is_not_guest_execution(monkeypatch, tmp_path):
    calls = []
    def build(output, *, cancel_event):
        calls.append((output, cancel_event))
        return {"config_file": str(tmp_path / "project.json")}
    monkeypatch.setattr("firmavex.product.example.build_example", build)
    output = io.BytesIO()
    result = serve(io.BytesIO(encode_command("build-1", "build_example", {"output_dir": str(tmp_path / "new")})), output)
    # EOF requests cancellation. Use a completed response directly below to
    # verify the service contract without depending on the input-thread race.
    assert result in (0, 1)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert messages[0]["kind"] == "accepted"
    assert not any(m.get("payload", {}).get("firmware_dispatched") is True for m in messages)
    assert len(calls) <= 1
    completed = services.build_example_project(tmp_path / "other")
    assert completed["success"]
    assert completed["firmware_dispatched"] is False
    assert completed["operation"] == "independent_example_build"


def test_example_cancel_before_dispatch_preserves_cancellation(monkeypatch, tmp_path):
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr("firmavex.product.example.build_example", lambda *a, **k: pytest.fail("must not build"))
    with pytest.raises(KeyboardInterrupt):
        services.build_example_project(tmp_path / "unused", cancel_event=cancel)
    assert not (tmp_path / "unused").exists()


def test_cancellable_compiler_host_process_capture():
    result = _compile([sys.executable, "-c", "print('host process test only')"], threading.Event())
    assert result.returncode == 0
    assert result.stdout.strip() == "host process test only"


def test_cancelled_compiler_reaped_and_original_control_flow(monkeypatch):
    from firmavex.product import runtime
    spawned = []
    actual = runtime._spawn
    def spawn(command):
        result = actual(command)
        spawned.append(result)
        return result
    monkeypatch.setattr(runtime, "_spawn", spawn)
    cancel = threading.Event()
    timer = threading.Timer(0.1, cancel.set)
    timer.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            _compile([sys.executable, "-c", "import time; time.sleep(60)"], cancel)
    finally:
        timer.cancel()
        timer.join(timeout=1)
    assert len(spawned) == 1
    process, stdout, stderr = spawned[0]
    assert process.poll() is not None
    assert not stdout.thread.is_alive() and not stderr.thread.is_alive()
    assert stdout.stream.closed and stderr.stream.closed
