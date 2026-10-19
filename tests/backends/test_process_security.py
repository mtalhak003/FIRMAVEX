"""Actual admission/resource/cleanup regression tests; no native support claims."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from firmavex.backends.api import Limits
from firmavex.backends.launcher import validate
from firmavex.backends.process import (
    Cancelled, Processes, inspect_artifacts, launcher_command, observe_processes,
)


def admission(argv=None):
    return {"schema_version": 1, "argv": argv or [sys.executable], "limits": asdict(Limits())}


@pytest.mark.parametrize("record", [
    {}, {**admission(), "extra": 1}, {**admission(), "schema_version": True},
    {**admission(), "argv": []}, {**admission(), "argv": "not-a-list"},
    admission(["relative-tool"]), admission([sys.executable, None]),
    admission([sys.executable, "bad\x00argument"]),
    {**admission(), "limits": {"timeout_seconds": True}},
])
def test_admission_rejects_malformed_records(record):
    with pytest.raises((ValueError, TypeError)):
        validate(record)


def test_admission_preserves_argument_boundaries():
    args = [sys.executable, "-c", "pass", "; touch never-created", "$(id)", "a b"]
    assert validate(admission(args))[0] == args


def test_real_argv_is_not_shell_interpreted(tmp_path):
    processes = Processes(threading.Event(), Limits())
    value = "x; touch SHOULD_NOT_EXIST $(id)"
    try:
        code, out, err = processes.run([sys.executable, "-c", "import sys;print(sys.argv[1])", value], tmp_path)
    finally:
        processes.close()
    assert code == 0, err
    assert out.strip() == value
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
    assert all(record["reaped"] for record in processes.cleanup)


def test_frozen_launcher_uses_console_sibling(tmp_path, monkeypatch):
    gui = tmp_path / "FIRMAVEX-Desktop"
    gui.write_text("gui")
    console = gui.with_name("FIRMAVEX.exe" if os.name == "nt" else "FIRMAVEX")
    console.write_text("console")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(gui))
    assert launcher_command() == [str(console), "--backend-child"]


def test_frozen_missing_console_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "GUI"))
    with pytest.raises(RuntimeError, match="frozen launcher"):
        launcher_command()


@pytest.mark.skipif(os.name != "posix", reason="POSIX resource APIs")
def test_actual_child_resource_limits(tmp_path):
    limits = Limits(memory_bytes=134217728, artifact_bytes=4096)
    script = "import resource,json;print(json.dumps([resource.getrlimit(v)[0] for v in [resource.RLIMIT_AS,resource.RLIMIT_FSIZE,resource.RLIMIT_CPU,resource.RLIMIT_CORE]]))"
    processes = Processes(threading.Event(), limits)
    try:
        code, out, err = processes.run([sys.executable, "-c", script], tmp_path)
    finally:
        processes.close()
    assert code == 0, err
    assert json.loads(out) == [134217728, 4096, 11, 0]


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux RLIMIT_AS enforcement qualification")
def test_actual_memory_allocation_cannot_exceed_limit(tmp_path):
    processes = Processes(threading.Event(), Limits(memory_bytes=67108864))
    try:
        code, out, err = processes.run([sys.executable, "-c", "data=bytearray(128*1024*1024);print('unexpected success')"], tmp_path)
    finally:
        processes.close()
    assert code != 0
    assert "unexpected success" not in out
    assert all(record["reaped"] for record in processes.cleanup)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file-size enforcement")
def test_actual_file_resource_limit_and_cleanup(tmp_path):
    processes = Processes(threading.Event(), Limits(artifact_bytes=1024))
    try:
        code, out, err = processes.run([sys.executable, "-c", "with open('large','wb') as stream:\n stream.write(b'x'*8192)"], tmp_path)
    finally:
        processes.close()
    assert code != 0
    assert (tmp_path / "large").stat().st_size <= 1024
    assert all(record["reaped"] for record in processes.cleanup)


def test_artifact_limit_applies_to_nested_directories(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/data").write_bytes(b"x" * 2048)
    with pytest.raises(RuntimeError, match="Aggregate artifact"):
        inspect_artifacts(tmp_path, 1024)


@pytest.mark.skipif(os.name != "posix", reason="Unprivileged symlink creation")
def test_artifact_inventory_rejects_symlinks(tmp_path):
    (tmp_path / "escape").symlink_to("/etc/passwd")
    with pytest.raises(RuntimeError, match="Symlink"):
        inspect_artifacts(tmp_path, 4096)


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO/hardlink APIs")
@pytest.mark.parametrize("kind", ["fifo", "hardlink"])
def test_artifact_inventory_rejects_nonregular_or_aliased_files(tmp_path, kind):
    if kind == "fifo":
        os.mkfifo(tmp_path / "unsafe")
    else:
        original = tmp_path / "original"
        original.write_text("x")
        os.link(original, tmp_path / "unsafe")
    with pytest.raises(RuntimeError, match="Nonregular or hardlinked"):
        inspect_artifacts(tmp_path, 4096)


def test_fast_exit_cannot_bypass_artifact_limit(tmp_path):
    processes = Processes(threading.Event(), Limits(artifact_bytes=1024))
    try:
        with pytest.raises(RuntimeError, match="Aggregate artifact"):
            processes.run([sys.executable, "-c", "open('a','wb').write(b'x'*800);open('b','wb').write(b'y'*800)"], tmp_path)
    finally:
        processes.close()
    assert all(record["reaped"] for record in processes.cleanup)


def test_precancel_does_not_dispatch(tmp_path):
    cancel = threading.Event()
    cancel.set()
    processes = Processes(cancel, Limits())
    with pytest.raises(Cancelled):
        processes.spawn([sys.executable, "-c", "pass"], tmp_path)
    assert not processes.children


def test_process_owner_close_is_idempotent_and_terminal(tmp_path):
    processes = Processes(threading.Event(), Limits())
    processes.run([sys.executable, "-c", "pass"], tmp_path)
    processes.close()
    original = list(processes.cleanup)
    processes.close()
    assert processes.cleanup == original
    with pytest.raises(RuntimeError, match="already closed"):
        processes.spawn([sys.executable, "-c", "pass"], tmp_path)


def test_observer_is_scoped_and_reports_exact_owned_admission(tmp_path):
    events = []
    processes = Processes(threading.Event(), Limits())
    args = [sys.executable, "-c", "print('first')"]
    try:
        with observe_processes(events.append):
            processes.run(args, tmp_path)
        processes.run([sys.executable, "-c", "print('second')"], tmp_path)
    finally:
        processes.close()
    assert len(events) == 1
    assert events[0]["stage"] == "process_started"
    assert events[0]["argv"] == args
    assert events[0]["pid"] == processes.cleanup[-1]["pid"]


def test_actual_cancel_preserves_cleanup(tmp_path):
    cancel = threading.Event()
    processes = Processes(cancel, Limits())
    timer = None
    try:
        def started(event):
            nonlocal timer
            timer = threading.Timer(.2, cancel.set)
            timer.start()
        with observe_processes(started), pytest.raises(Cancelled):
            processes.run([sys.executable, "-c", "import time;time.sleep(30)"], tmp_path)
    finally:
        if timer:
            timer.join()
        processes.close()
    assert processes.cleanup[0]["reaped"]


def test_child_launcher_bad_admission_fails_closed(tmp_path):
    result = subprocess.run([sys.executable, "-m", "firmavex.backends.launcher"],
                            input=b'{"schema_version":1}\n', capture_output=True)
    assert result.returncode == 125
    assert b"admission failed" in result.stderr

def test_posix_limits_never_raise_inherited_caps(monkeypatch):
    if os.name!='posix':pytest.skip('POSIX APIs')
    import resource
    from firmavex.backends.launcher import apply_posix_limits
    applied=[]
    monkeypatch.setattr(resource,'getrlimit',lambda kind:(1,2))
    monkeypatch.setattr(resource,'setrlimit',lambda kind,pair:applied.append((kind,pair)))
    apply_posix_limits(Limits())
    assert applied and all(pair[0]<=1 and pair[1]<=2 for _,pair in applied)
    assert dict(applied)[resource.RLIMIT_CORE]==(0,0)


def test_artifact_inventory_does_not_trust_cached_direntry_link_count(tmp_path, monkeypatch):
    """Windows DirEntry metadata can have st_nlink=0 for an ordinary file."""
    from types import SimpleNamespace
    from firmavex.backends import process
    source = tmp_path / 'ordinary'
    source.write_bytes(b'actual file')
    class Entries:
        def __enter__(self):
            return iter([SimpleNamespace(path=str(source), stat=lambda **kwargs: pytest.fail('Cached metadata used'))])
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(process.os, 'scandir', lambda path: Entries())
    assert inspect_artifacts(tmp_path, 100) == len(b'actual file')


def test_actual_hardlink_artifact_still_rejected(tmp_path):
    original = tmp_path / 'original'
    original.write_bytes(b'x')
    os.link(original, tmp_path / 'alias')
    with pytest.raises(RuntimeError, match='Nonregular or hardlinked'):
        inspect_artifacts(tmp_path, 4096)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX resource APIs')
def test_darwin_memory_admission_failure_is_not_bypassed(monkeypatch):
    import resource
    from firmavex.backends import launcher
    monkeypatch.setattr(launcher.sys, 'platform', 'darwin')
    monkeypatch.setattr(resource, 'getrlimit', lambda kind: (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    attempts = []
    def reject(kind, pair):
        attempts.append((kind, pair))
        raise ValueError('current limit exceeds maximum limit')
    monkeypatch.setattr(resource, 'setrlimit', reject)
    monkeypatch.setattr(launcher, 'darwin_memory_diagnostic', lambda: {'virtual_bytes': 400_000_000_000, 'resident_bytes': 20_000_000})
    with pytest.raises(RuntimeError, match='400000000000.*NOT bypassed'):
        launcher.apply_posix_limits(Limits())
    assert attempts == [(resource.RLIMIT_AS, (Limits().memory_bytes, Limits().memory_bytes))]
