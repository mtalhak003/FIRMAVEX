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
    source = PREFIX + f"import subprocess; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);open({str(pid_file)!r},'w').write(str(p.pid));sys.exit(3)"
    with pytest.raises(ProductError):
        Supervisor(worker(source), cancellation_grace=0.2).execute("doctor", {})
    pid = int(pid_file.read_text())
    # Linux can retain a terminated orphan briefly as a zombie; that is not a
    # running resource leak. Process state is inspected without killing others.
    for _ in range(30):
        try:
            state = open(f"/proc/{pid}/stat").read().split()[2]
        except FileNotFoundError:
            return
        if state == "Z":
            return
        time.sleep(0.02)
    pytest.fail("Owned descendant remained running after worker failure")
