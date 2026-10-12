import os
import sys
import threading

import pytest

from firmavex.product.errors import ProductError
from firmavex.product.supervisor import Supervisor


def worker(source):
    return [sys.executable, "-u", "-c", source]


PREFIX = "import sys,json; m=json.loads(sys.stdin.readline()); r=m['request_id']; "


def test_real_subprocess_transport_returns_synthetic_result():
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test','status':'done'}}),flush=True)"
    result = Supervisor(worker(source), cancellation_grace=1).execute("doctor", {})
    assert result == {"measurement_mode": "synthetic_test", "status": "done"}


def test_progress_callback():
    source = PREFIX + "\nfor seq,kind in [(1,'accepted'),(2,'progress'),(3,'result')]:\n print(json.dumps({'schema_version':1,'request_id':r,'sequence':seq,'kind':kind,'payload':{'measurement_mode':'synthetic_test'}}),flush=True)\n"
    records = []
    Supervisor(worker(source), cancellation_grace=1).execute("doctor", {}, event_callback=records.append)
    assert [r["kind"] for r in records] == ["accepted", "progress", "result"]


@pytest.mark.parametrize("body", [
    "print('not json',flush=True)",
    "print(json.dumps({'schema_version':1,'request_id':r,'sequence':2,'kind':'result','payload':{}}),flush=True)",
    "print(json.dumps({'schema_version':1,'request_id':'other','sequence':1,'kind':'result','payload':{}}),flush=True)",
    "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'shutdown','payload':{}}),flush=True)",
])
def test_bad_event_fails_closed(body):
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(PREFIX + body), cancellation_grace=1).execute("doctor", {})
    assert exc.value.category == "protocol_error"


def test_eof_without_terminal_record_is_interrupted():
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(PREFIX + "sys.exit(4)"), cancellation_grace=1).execute("doctor", {})
    assert exc.value.category == "worker_interrupted"


def test_worker_error_propagates_useful_diagnostics():
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'error','payload':{'category':'missing_tool','message':'No debugger','details':{'name':'gdb'}}}),flush=True)"
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(source), cancellation_grace=1).execute("doctor", {})
    assert exc.value.category == "missing_tool"
    assert exc.value.details == {"name": "gdb"}


def test_timeout_requests_cancel_then_fails_despite_late_result():
    source = PREFIX + "c=json.loads(sys.stdin.readline()); print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test','status':'cancelled'}}),flush=True)"
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(source), cancellation_grace=1).execute("run", {}, timeout=0.05)
    assert exc.value.category == "worker_timeout"


def test_explicit_cancel_reaches_child():
    cancel = threading.Event()
    cancel.set()
    source = PREFIX + "c=json.loads(sys.stdin.readline()); print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test','cancel_received':c['command']=='cancel'}}),flush=True)"
    result = Supervisor(worker(source), cancellation_grace=1).execute("run", {}, cancel_event=cancel)
    assert result["cancel_received"] is True


def test_noisy_stderr_does_not_deadlock():
    source = PREFIX + "sys.stderr.write('x'*200000);sys.stderr.flush(); print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test'}}),flush=True)"
    assert Supervisor(worker(source), cancellation_grace=1).execute("doctor", {}, timeout=3)["measurement_mode"] == "synthetic_test"


def test_result_followed_by_nonzero_exit_is_not_success():
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test','completed':True}}),flush=True); sys.exit(7)"
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(source), cancellation_grace=1).execute("doctor", {})
    assert exc.value.category == "worker_failure"
    assert exc.value.details["returncode"] == 7
    assert exc.value.details["partial_result"]["completed"] is True


def test_result_followed_by_cleanup_hang_is_not_success():
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test'}}),flush=True); import time;time.sleep(30)"
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(source), cancellation_grace=0.1).execute("doctor", {})
    assert exc.value.category == "cleanup_failure"
    assert exc.value.details["partial_result"]["measurement_mode"] == "synthetic_test"


def test_original_error_preserved_when_cleanup_also_fails():
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'error','payload':{'category':'infrastructure_failure','message':'original failure','details':{}}}),flush=True); import time;time.sleep(30)"
    with pytest.raises(ProductError) as exc:
        Supervisor(worker(source), cancellation_grace=0.1).execute("doctor", {})
    assert exc.value.category == "infrastructure_failure"
    assert exc.value.message == "original failure"
    assert "supervisor_cleanup_error" in exc.value.details


def test_missing_worker_executable_is_structured_error():
    with pytest.raises(ProductError) as exc:
        Supervisor(["/nonexistent/firmavex-worker"]).execute("doctor", {})
    assert exc.value.category == "worker_failure"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc ownership inspection; no Windows/macOS coverage implied")
def test_owned_descendant_terminated_after_worker_dies(tmp_path):
    import time
    pid_file = tmp_path / "descendant.pid"
    ready_file = tmp_path / "host-child-inspected"
    source = PREFIX + (
        "import subprocess,pathlib,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));"
        "deadline=time.monotonic()+10;"
        f"\nwhile not pathlib.Path({str(ready_file)!r}).exists() and time.monotonic()<deadline: time.sleep(.005)"
        "\nsys.exit(3)"
    )
    with pytest.raises(ProductError):
        Supervisor(worker(source), cancellation_grace=0.2).execute("doctor", {})
    pid = int(pid_file.read_text())
    # Linux can retain a terminated orphan briefly as a zombie; that is not a
    # running resource leak. Process state is inspected without killing others.
    for _ in range(30):
        try:
            state = open(f"/proc/{pid}/stat").read().split()[2]
        except (FileNotFoundError, ProcessLookupError):
            # procfs may return ENOENT or ESRCH when the reaped process
            # disappears between opening and reading its stat file.
            return
        if state == "Z":
            return
        time.sleep(0.02)
    pytest.fail("Owned descendant remained running after worker failure")


class SyntheticJob:
    def __init__(self, process, *, close_fails=False):
        self.process = process
        self.calls = []
        self.close_fails = close_fails

    def close(self):
        self.calls.append("close")
        if self.close_fails:
            raise ProductError("process_ownership_failure", "synthetic close failure")

    def terminate(self):
        self.calls.append("terminate")
        if self.process.poll() is None:
            self.process.kill()


def test_ownership_is_established_before_first_worker_command(monkeypatch, tmp_path):
    received = tmp_path / "received"
    owned = []

    def establish(process):
        assert not received.exists()
        job = SyntheticJob(process)
        owned.append(job)
        return job

    monkeypatch.setattr(Supervisor, "_create_windows_job", staticmethod(establish))
    source = PREFIX + f"open({str(received)!r},'w').write('command');print(json.dumps({{'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{{'measurement_mode':'synthetic_test'}}}}),flush=True)"
    result = Supervisor(worker(source), cancellation_grace=1).execute("doctor", {})
    assert result["measurement_mode"] == "synthetic_test"
    assert received.read_text() == "command"
    assert owned[0].calls == ["close"]
    assert owned[0].process.poll() is not None


@pytest.mark.parametrize("original", [ProductError("process_ownership_failure", "synthetic admission failure"), KeyboardInterrupt("cancel admission"), SystemExit(23)])
def test_ownership_failure_never_dispatches_and_reaps_worker(monkeypatch, tmp_path, original):
    received = tmp_path / "received"
    processes = []

    def establish(process):
        processes.append(process)
        raise original

    monkeypatch.setattr(Supervisor, "_create_windows_job", staticmethod(establish))
    source = PREFIX + f"open({str(received)!r},'w').write('command')"
    with pytest.raises(type(original)) as raised:
        Supervisor(worker(source), cancellation_grace=1).execute("doctor", {})
    assert raised.value is original
    assert not received.exists()
    assert processes[0].poll() is not None
    assert all(stream.closed for stream in (processes[0].stdin, processes[0].stdout, processes[0].stderr))


@pytest.mark.parametrize("original", [KeyboardInterrupt("original cancellation"), SystemExit(29)])
def test_original_control_flow_preserved_when_owned_job_close_fails(monkeypatch, original):
    jobs = []

    def establish(process):
        job = SyntheticJob(process, close_fails=True)
        jobs.append(job)
        return job

    def interrupt(event):
        raise original

    monkeypatch.setattr(Supervisor, "_create_windows_job", staticmethod(establish))
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'progress','payload':{'measurement_mode':'synthetic_test'}}),flush=True);sys.stdin.read()"
    with pytest.raises(type(original)) as raised:
        Supervisor(worker(source), cancellation_grace=1).execute("doctor", {}, event_callback=interrupt)
    assert raised.value is original
    assert "Cannot close" in raised.value.__notes__[0]
    assert jobs[0].calls == ["close", "terminate", "close"]
    assert jobs[0].process.poll() is not None


def test_job_close_failure_rejects_otherwise_successful_result(monkeypatch):
    monkeypatch.setattr(Supervisor, "_create_windows_job", staticmethod(lambda process: SyntheticJob(process, close_fails=True)))
    source = PREFIX + "print(json.dumps({'schema_version':1,'request_id':r,'sequence':1,'kind':'result','payload':{'measurement_mode':'synthetic_test'}}),flush=True)"
    with pytest.raises(ProductError) as raised:
        Supervisor(worker(source), cancellation_grace=1).execute("doctor", {})
    assert raised.value.category == "cleanup_failure"
    assert raised.value.details["partial_result"]["measurement_mode"] == "synthetic_test"


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows host child tree; no ARM qualification implied")
def test_native_windows_supervisor_reaps_python_descendant_after_worker_death(tmp_path):
    import ctypes
    import time
    pid_file = tmp_path / "host-child.pid"
    source = PREFIX + f"import subprocess,pathlib;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));sys.exit(3)"
    # Open a synchronization handle while the actual child is still alive;
    # retaining this handle permits reliable post-cleanup termination checks.
    child_handles = []
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
    library.OpenProcess.restype = ctypes.c_void_p
    library.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    library.WaitForSingleObject.restype = ctypes.c_uint32
    library.CloseHandle.argtypes = [ctypes.c_void_p]
    library.CloseHandle.restype = ctypes.c_int32

    def capture_handle():
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.005)
        if pid_file.exists():
            handle = library.OpenProcess(0x00100000, False, int(pid_file.read_text()))
            if handle:
                child_handles.append(handle)
                ready_file.write_text("inspected")

    inspector = threading.Thread(target=capture_handle)
    inspector.start()
    try:
        with pytest.raises(ProductError):
            Supervisor(worker(source), cancellation_grace=0.2).execute("doctor", {})
        inspector.join(timeout=11)
        assert child_handles, "Could not establish actual host child inspection"
        assert library.WaitForSingleObject(child_handles[0], 10000) == 0, "Owned Windows host child survived worker cleanup"
    finally:
        inspector.join(timeout=11)
        for handle in child_handles:
            library.CloseHandle(handle)
