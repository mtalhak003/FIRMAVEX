"""Fake Win32 API tests are synthetic; gated native tests use host Python only."""

import ctypes
import os
import subprocess
import sys
import time

import pytest

from firmavex.product.errors import ProductError
from firmavex.product.windows_job import (
    BasicLimitInformation, DWORD, ExtendedLimitInformation, IoCounters,
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    WindowsJob,
)


class SyntheticApi:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = set(fail or [])
        self.limits = None

    def last_error(self):
        return 5

    def CreateJobObjectW(self, security, name):
        self.calls.append(("create", security, name))
        return 0 if "create" in self.fail else 123

    def SetInformationJobObject(self, handle, kind, pointer, size):
        self.calls.append(("set", handle, kind, size))
        self.limits = ExtendedLimitInformation.from_buffer_copy(ctypes.string_at(pointer, size))
        return "set" not in self.fail

    def AssignProcessToJobObject(self, job, process):
        self.calls.append(("assign", job, process))
        return "assign" not in self.fail

    def TerminateJobObject(self, job, code):
        self.calls.append(("terminate", job, code))
        return "terminate" not in self.fail

    def CloseHandle(self, job):
        self.calls.append(("close", job))
        return "close" not in self.fail


def test_windows_integer_and_structure_layout():
    assert ctypes.sizeof(DWORD) == 4
    assert ctypes.sizeof(IoCounters) == 48
    assert BasicLimitInformation.LimitFlags.offset == 16
    assert ExtendedLimitInformation.IoInfo.offset == ctypes.sizeof(BasicLimitInformation)
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(BasicLimitInformation) == 64
        assert ctypes.sizeof(ExtendedLimitInformation) == 144
        assert BasicLimitInformation.MinimumWorkingSetSize.offset == 24
        assert BasicLimitInformation.Affinity.offset == 48


def test_synthetic_owner_sets_kill_on_close_and_exact_process_handle():
    api = SyntheticApi()
    job = WindowsJob(_api=api)
    assert api.calls[1] == ("set", 123, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.sizeof(ExtendedLimitInformation))
    assert api.limits.BasicLimitInformation.LimitFlags == JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    job.assign(456)
    job.terminate()
    job.close()
    job.close()
    job.terminate()
    assert api.calls[-3:] == [("assign", 123, 456), ("terminate", 123, 1), ("close", 123)]


@pytest.mark.parametrize("failure,operation", [
    ("create", "CreateJobObjectW"), ("set", "SetInformationJobObject"),
    ("assign", "AssignProcessToJobObject"), ("terminate", "TerminateJobObject"),
    ("close", "CloseHandle"),
])
def test_synthetic_api_failures_are_structured(failure, operation):
    api = SyntheticApi({failure})
    with pytest.raises(ProductError) as raised:
        if failure in {"create", "set"}:
            WindowsJob(_api=api)
        else:
            job = WindowsJob(_api=api)
            try:
                {"assign": lambda: job.assign(456), "terminate": job.terminate, "close": job.close}[failure]()
            finally:
                api.fail.clear()
                job.close()
    assert raised.value.category == "process_ownership_failure"
    assert raised.value.details["operation"] == operation
    assert raised.value.details["winerror"] == 5
    if failure == "set":
        assert api.calls[-1] == ("close", 123)


@pytest.mark.parametrize("handle", [None, True, False, 0, -1, "456", 2.5])
def test_invalid_process_handle_is_not_assigned(handle):
    api = SyntheticApi()
    with WindowsJob(_api=api) as job:
        with pytest.raises(ProductError):
            job.assign(handle)
    assert not any(call[0] == "assign" for call in api.calls)


def test_closed_owner_rejects_assignment():
    job = WindowsJob(_api=SyntheticApi())
    job.close()
    with pytest.raises(ProductError, match="closed"):
        job.assign(456)


def test_failed_close_keeps_handle_for_explicit_retry():
    api = SyntheticApi({"close"})
    job = WindowsJob(_api=api)
    with pytest.raises(ProductError):
        job.close()
    api.fail.clear()
    job.close()
    assert [call[0] for call in api.calls].count("close") == 2


def test_set_failure_remains_primary_when_handle_close_fails():
    with pytest.raises(ProductError) as raised:
        WindowsJob(_api=SyntheticApi({"set", "close"}))
    assert raised.value.details["operation"] == "SetInformationJobObject"
    assert "ownership_cleanup_error" in raised.value.details


@pytest.mark.parametrize("original", [KeyboardInterrupt("cancelled"), SystemExit(17)])
def test_context_preserves_original_control_flow_when_close_fails(original):
    with pytest.raises(type(original)) as raised:
        with WindowsJob(_api=SyntheticApi({"close"})):
            raise original
    assert raised.value is original
    assert "cleanup also failed" in raised.value.__notes__[0]


@pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows guard only")
def test_real_api_does_not_claim_windows_ownership_on_other_hosts():
    with pytest.raises(ProductError) as raised:
        WindowsJob()
    assert raised.value.category == "unsupported_platform"


def _native_kernel():
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.OpenProcess.argtypes = [DWORD, ctypes.c_int32, DWORD]
    library.OpenProcess.restype = ctypes.c_void_p
    library.WaitForSingleObject.argtypes = [ctypes.c_void_p, DWORD]
    library.WaitForSingleObject.restype = DWORD
    library.CloseHandle.argtypes = [ctypes.c_void_p]
    library.CloseHandle.restype = ctypes.c_int32
    library.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32)]
    library.IsProcessInJob.restype = ctypes.c_int32
    return library


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows host process ownership; not ARM execution qualification")
@pytest.mark.parametrize("action", ["close", "terminate"])
def test_native_windows_job_owns_and_terminates_python_descendant(tmp_path, action):
    # Child creation waits for admission, exactly as the trusted product worker
    # does. Native Python host processes are real, not firmware measurements.
    pid_file = tmp_path / "child.pid"
    source = (
        "import sys,subprocess,time,pathlib;sys.stdin.readline();"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid));"
        "time.sleep(120)"
    )
    process = subprocess.Popen([sys.executable, "-u", "-c", source], stdin=subprocess.PIPE)
    job = WindowsJob()
    library = _native_kernel()
    child_handle = None
    try:
        job.assign(int(process._handle))
        process.stdin.write(b"admitted\n")
        process.stdin.flush()
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_file.exists(), "Owned host child did not start"
        child_handle = library.OpenProcess(0x00100000 | 0x1000, False, int(pid_file.read_text()))
        assert child_handle, f"Cannot inspect host child: {ctypes.get_last_error()}"
        member = ctypes.c_int32()
        assert library.IsProcessInJob(child_handle, job._handle, ctypes.byref(member))
        assert member.value == 1, "Host descendant did not inherit the owned job"
        getattr(job, action)()
        process.wait(timeout=10)
        assert library.WaitForSingleObject(child_handle, 10000) == 0, "Owned child survived job cleanup"
    finally:
        job.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stdin.close()
        if child_handle:
            library.CloseHandle(child_handle)
