"""Real host pytest subprocesses: diagnostics are not firmware evidence."""
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[2]


def probe_environment(**overrides):
    # Expected-negative synthetic probes must not populate the outer CI archive.
    environment = dict(os.environ)
    environment.pop('FIRMAVEX_CI_DIAGNOSTICS', None)
    environment.update(overrides)
    return environment


def run_selection(tmp_path, source, *options):
    test = tmp_path / 'test_ci_probe.py'
    test.write_text(source, encoding='utf-8')
    env = probe_environment(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    return subprocess.run([sys.executable, str(REPO/'tools/product_ci_tests.py'),
                           '--ci-watchdog', '-q', str(test), *options], cwd=REPO, env=env,
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
    result = run_selection(tmp_path, source, '--firmavex-test-timeout=2')
    assert result.returncode == 124, result.stdout + result.stderr
    assert 'Per-test timeout' in result.stdout
    assert any(line.startswith('::error title=CI lifecycle timeout::') for line in result.stdout.splitlines())
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
    result = run_selection(tmp_path, source, '--firmavex-test-timeout=2')
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


@pytest.mark.parametrize('phase', ['collection', 'shutdown'])
def test_ci_bounds_collection_and_leaked_thread_shutdown(tmp_path, phase):
    source = ('import time; time.sleep(10)\ndef test_probe(): pass\n'
              if phase == 'collection' else
              'import threading,time\ndef test_probe():\n threading.Thread(target=time.sleep,args=(10,)).start()\n')
    result = run_selection(tmp_path, source, '--firmavex-test-timeout=2')
    assert result.returncode == 124, result.stdout + result.stderr
    assert 'CI lifecycle timeout' in result.stdout
    assert ('test collection' if phase == 'collection' else 'interpreter shutdown') in result.stdout
    assert 'Thread' in result.stdout


def test_native_launcher_watchdog_retains_stacks_during_parent_stall(tmp_path):
    # Exercise the actual CPython watchdog with a synthetic blocked launcher,
    # not Windows firmware or mocked execution evidence.
    archive = tmp_path / 'diagnostics'
    script = '''import os,time,types
from tools import product_ci_tests as ci
original=ci.faulthandler.dump_traceback_later
ci.faulthandler.dump_traceback_later=lambda seconds,**kw: original(.5,**kw)
ci.os=types.SimpleNamespace(name='nt',environ=os.environ)
ci.run_tests=lambda *args,**kwargs: time.sleep(10)
ci.main(['--ci-watchdog'])
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=REPO,
                            env=dict(os.environ, FIRMAVEX_CI_DIAGNOSTICS=str(archive)),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    stacks = list(archive.glob('firmavex-ci-*/launcher-stacks.log'))
    assert len(stacks) == 1
    assert 'Timeout' in stacks[0].read_text()
    reported = subprocess.run([sys.executable, str(REPO/'tools/product_ci_tests.py'),
                               '--report-diagnostics'], cwd=REPO,
                              env=dict(os.environ, FIRMAVEX_CI_DIAGNOSTICS=str(archive)),
                              capture_output=True, text=True, timeout=15)
    assert reported.returncode == 0
    assert 'Native CI launcher timeout' in reported.stdout
    assert 'Timeout' in reported.stdout


def test_native_timeout_report_is_bounded_and_has_phase_and_output(tmp_path):
    root = tmp_path/'diagnostics'/'firmavex-ci-probe'
    root.mkdir(parents=True)
    (root/'launcher-stacks.log').write_text('do not report this prefix' + 'x'*100000)
    (root/'launcher-state.log').write_text('test phase')
    (root/'pytest.log').write_text('last child output')
    result = subprocess.run([sys.executable, str(REPO/'tools/product_ci_tests.py'),
                             '--report-diagnostics'], cwd=REPO,
                            env=dict(os.environ, FIRMAVEX_CI_DIAGNOSTICS=str(root.parent)),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert len(result.stdout) < 16000
    assert 'do not report this prefix' not in result.stdout
    assert 'test phase' in result.stdout and 'last child output' in result.stdout


def test_watchdog_is_opt_in_and_preserves_native_test_timeout_policy(tmp_path):
    source = tmp_path/'test_plain_probe.py'
    source.write_text('def test_probe(): pass\n')
    result = subprocess.run([sys.executable, str(REPO/'tools/product_ci_tests.py'),
                             '-q', str(source)], cwd=REPO,
                            env=probe_environment(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert '1 passed' in result.stdout
    assert 'FIRMAVEX TEST START' not in result.stdout
    assert 'FIRMAVEX pytest lifecycle' not in result.stdout


def test_missing_admission_never_starts_pytest_or_creates_report(tmp_path):
    from tools.product_ci_tests import pytest_command
    source = tmp_path/'test_never.py'
    marker = tmp_path/'dispatched'
    source.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("dispatched")\ndef test_never(): pass\n')
    report = tmp_path/'never.xml'
    result = subprocess.run(pytest_command(['-q',str(source)], report, bounded=True),
                            cwd=REPO, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 123
    assert not marker.exists() and not report.exists()


def test_test_liveness_does_not_depend_on_ci_console_drain(tmp_path, monkeypatch):
    import io
    from tools import product_ci_tests as ci
    source = tmp_path/'test_output_probe.py'
    source.write_text("def test_output():\n print('x' * 1048576)\n")
    report = tmp_path/'pytest.xml'
    original_popen = ci.subprocess.Popen
    def bounded_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        original_wait = process.wait
        process.wait = lambda timeout=None: original_wait(timeout=min(timeout or 10, 10))
        return process
    class UnavailableConsole(io.StringIO):
        @property
        def buffer(self):
            return self
        def write(self, value):
            if isinstance(value, bytes):
                raise OSError('synthetic unavailable CI console')
            return super().write(value)
    with monkeypatch.context() as patch:
        patch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
        patch.setattr(ci.subprocess, 'Popen', bounded_process)
        patch.setattr(ci.sys, 'stdout', UnavailableConsole())
        result = ci.run_tests(['-q', '-s', str(source)], report, bounded=True)
    assert result.returncode == 0
    assert len(result.stdout.encode()) <= 65536
    assert report.with_suffix('.log').stat().st_size > 1048576


def test_completed_launcher_phase_is_reported_as_administrative_notice(tmp_path):
    root = tmp_path/'diagnostics'/'firmavex-ci-probe'
    root.mkdir(parents=True)
    (root/'launcher-stacks.log').write_bytes(b'')
    (root/'launcher-state.log').write_text('completed: pytest status=1')
    result = subprocess.run([sys.executable, str(REPO/'tools/product_ci_tests.py'),
                             '--report-diagnostics'], cwd=REPO,
                            env=dict(os.environ, FIRMAVEX_CI_DIAGNOSTICS=str(root.parent)),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert '::notice title=Retained CI launcher state::completed: pytest status=1' in result.stdout
    assert '::error' not in result.stdout
    assert 'passed' not in result.stdout


def test_expected_negative_probes_do_not_pollute_outer_ci_archive(tmp_path, monkeypatch):
    archive = tmp_path/'outer-archive'
    archive.mkdir()
    (archive/'sentinel').write_text('retain')
    monkeypatch.setenv('FIRMAVEX_CI_DIAGNOSTICS', str(archive))
    result = run_selection(tmp_path, 'def test_negative(): assert False\n')
    assert result.returncode == 1
    assert [path.name for path in archive.iterdir()] == ['sentinel']
    assert (archive/'sentinel').read_text() == 'retain'
