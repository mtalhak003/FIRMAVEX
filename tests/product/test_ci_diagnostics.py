"""Real host pytest subprocesses: diagnostics are not firmware evidence."""
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[2]


def run_selection(tmp_path, source, *options):
    test = tmp_path / 'test_ci_probe.py'
    test.write_text(source, encoding='utf-8')
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    return subprocess.run([sys.executable, str(REPO/'tools/product_ci_tests.py'),
                           '-q', str(test), *options], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=25)


def test_ci_reports_completed_test_and_preserves_failure(tmp_path):
    result = run_selection(tmp_path, 'def test_probe():\n assert False, "probe failure"\n')
    assert result.returncode == 1
    assert 'FIRMAVEX TEST START' in result.stdout
    assert 'FIRMAVEX TEST END' in result.stdout
    assert 'probe failure' in result.stdout


@pytest.mark.parametrize('phase', ['setup', 'call', 'teardown'])
def test_ci_watchdog_names_stalled_test_and_fails_with_stacks(tmp_path, phase):
    setup = 'time.sleep(10)' if phase == 'setup' else 'pass'
    call = 'time.sleep(10)' if phase == 'call' else 'pass'
    teardown = 'time.sleep(10)' if phase == 'teardown' else 'pass'
    source = f'''import pytest,time
@pytest.fixture
def fixture():
 {setup}
 yield
 {teardown}
def test_stalled(fixture):
 {call}
'''
    result = run_selection(tmp_path, source, '--firmavex-test-timeout=0.5')
    assert result.returncode == 124, result.stdout + result.stderr
    assert 'Per-test timeout' in result.stdout
    assert 'test_stalled' in result.stdout
    assert 'Thread' in result.stdout
    assert 'Timeout' in result.stdout or 'time.sleep' in result.stdout
    assert 'FIRMAVEX TEST END' not in result.stdout


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf'])
def test_ci_watchdog_rejects_invalid_limits(tmp_path, value):
    result = run_selection(tmp_path, 'def test_probe(): pass\n', '--firmavex-test-timeout='+value)
    assert result.returncode != 0
    assert 'must be positive and finite' in result.stdout


def test_watchdog_exit_reaps_owned_host_descendant(tmp_path):
    pid_file = tmp_path / 'child.pid'
    source = f'''import subprocess,sys,time
from pathlib import Path
def test_stalled():
 child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
 Path({str(pid_file)!r}).write_text(str(child.pid))
 time.sleep(10)
'''
    result = run_selection(tmp_path, source, '--firmavex-test-timeout=1')
    assert result.returncode == 124, result.stdout + result.stderr
    pid = int(pid_file.read_text())
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int32
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                assert kernel.WaitForSingleObject(handle, 10000) == 0
            finally:
                assert kernel.CloseHandle(handle)
        else:
            assert ctypes.get_last_error() == 87, 'Cannot verify descendant exit'
    elif sys.platform.startswith('linux'):
        state = Path(f'/proc/{pid}/stat')
        try:
            assert state.read_text().split()[2] == 'Z', 'Owned descendant still running'
        except (FileNotFoundError, ProcessLookupError):
            pass
    else:
        deadline = time.monotonic() + 3
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            assert time.monotonic() < deadline, 'Owned descendant still running'
            time.sleep(0.01)
