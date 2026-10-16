"""Publish actual pytest outcomes to the public Actions job summary.

This does not dispatch experiments independently; it runs exactly the supplied
regression test selection and preserves its process exit status. GitHub's raw
logs require authentication on some public repositories, so short failure
summaries aid external verification without calling authenticated APIs.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import signal
import faulthandler
from contextlib import nullcontext, contextmanager
import xml.etree.ElementTree as ET


def pytest_command(args, report, *, bounded):
    return [sys.executable, '-u', '-c',
               "import sys,runpy; admitted=sys.stdin.buffer.read(1); sys.exit(123) if admitted != b'1' else None; sys.argv[0]='pytest'; runpy.run_module('pytest',run_name='__main__')",
               *(['-p', 'tools.product_ci_diagnostics'] if bounded else []),
               *args, '--junitxml='+str(report)]

def run_tests(args, report, *, bounded=False):
    """Stream bounded diagnostic history; own pytest descendants on every exit."""
    def phase(name):
        report.with_name('launcher-state.log').write_text(name + '\n', encoding='utf-8')
    phase('import Windows ownership API')
    from firmavex.product.windows_job import WindowsJob
    command = pytest_command(args, report, bounded=bounded)
    kwargs = {'start_new_session': True} if os.name == 'posix' else {}
    phase('create admitted pytest child')
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               **kwargs)
    owner = None
    transcript = report.with_suffix('.log').open('wb')
    history = bytearray()
    lock = threading.Lock()
    def stream():
        while True:
            data = os.read(process.stdout.fileno(), 4096)
            if not data:
                break
            transcript.write(data)
            transcript.flush()
            with lock:
                history.extend(data)
                del history[:-65536]
            # Binary writes retain traceback text even with a non-UTF8 console.
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    try:
        if os.name == 'nt':
            phase('assign Windows Job Object')
            owner = WindowsJob()
            owner.assign(int(process._handle))
        phase('release admitted child')
        process.stdin.write(b'1')
        process.stdin.close()
        reader = threading.Thread(target=stream, daemon=True)
        reader.start()
        try:
            phase('wait for pytest completion')
            process.wait(timeout=540 if bounded else 900)
        except subprocess.TimeoutExpired:
            print(f'::error::Pytest selection exceeded {540 if bounded else 900}s; terminating owned test tree.', flush=True)
            raise
    finally:
        if owner is not None:
            phase('close Windows Job Object')
            owner.close()
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        phase('reap pytest')
        process.wait(timeout=10)
        phase('join transcript reader')
        if 'reader' in locals():
            reader.join(timeout=10)
            if reader.is_alive():
                raise RuntimeError('CI output reader did not finish after owned tree cleanup')
        phase('close transcript pipes')
        process.stdout.close()
        transcript.close()
    with lock:
        output = bytes(history).decode('utf-8', errors='replace')
    phase('completed: pytest status=' + str(process.returncode))
    return subprocess.CompletedProcess(command, process.returncode, stdout=output)


def report_diagnostics():
    """Expose only bounded retained timeout details; do not dispatch pytest."""
    destination = os.environ.get('FIRMAVEX_CI_DIAGNOSTICS')
    if not destination:
        return 0
    for stack in sorted(Path(destination).glob('firmavex-ci-*/launcher-stacks.log')):
        if not stack.stat().st_size:
            continue
        # Seek from EOF to bound memory even for unexpectedly large files.
        def tail(path, limit):
            if not path.exists():
                return '(not present)'
            with path.open('rb') as handle:
                handle.seek(max(0, path.stat().st_size-limit))
                return handle.read(limit).decode('utf-8', errors='replace')
        detail = (tail(stack.with_name('launcher-state.log'), 1024) + '\n'
                  + tail(stack, 10000) + '\n' + tail(stack.with_name('pytest.log'), 4000))
        escaped = detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Native CI launcher timeout::'+escaped, flush=True)
    return 0


@contextmanager
def launcher_deadline(report, *, enabled):
    # Native watchdog remains active through startup, cleanup and reporting.
    with report.with_name('launcher-stacks.log').open('wb') as stack_file:
        if enabled and os.name == 'nt':
            faulthandler.dump_traceback_later(600, file=stack_file, exit=True)
        try:
            yield
        finally:
            if enabled and os.name == 'nt':
                faulthandler.cancel_dump_traceback_later()


def main(arguments=None):
    args = sys.argv[1:] if arguments is None else arguments
    if args == ['--report-diagnostics']:
        return report_diagnostics()
    bounded = '--ci-watchdog' in args
    args = [arg for arg in args if arg != '--ci-watchdog']
    destination = os.environ.get('FIRMAVEX_CI_DIAGNOSTICS')
    if destination:
        Path(destination).mkdir(parents=True, exist_ok=True)
        directory = tempfile.mkdtemp(prefix='firmavex-ci-', dir=destination)
        context = nullcontext(directory)
    else:
        context = tempfile.TemporaryDirectory(prefix='firmavex-ci-')
    with context as directory:
        report = Path(directory)/'pytest.xml'
        with launcher_deadline(report, enabled=bounded):
            return complete_selection(args, report, bounded=bounded)


def complete_selection(args, report, *, bounded):
    print('::notice title=FIRMAVEX CI launcher::entered supervised test selection', flush=True)
    process = run_tests(args, report, bounded=bounded)
    if process.returncode:
        diagnostic = ('pytest exited ' + str(process.returncode) + '; actual final process output: ' + process.stdout[-7000:])
        escaped = diagnostic.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::error title=FIRMAVEX test process failure::'+escaped, flush=True)
    if report.exists():
        tree = ET.parse(report)
        for case in tree.findall('.//testcase'):
            problem = case.find('failure')
            if problem is None: problem = case.find('error')
            if problem is not None:
                diagnostic = case.get('classname','') + '.' + case.get('name','') + ': ' + (problem.text or problem.get('message',''))[-3000:]
                # Public Actions annotations remain visible when access to
                # raw logs/job summaries requires authentication.
                escaped = diagnostic.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
                print('::error title=FIRMAVEX regression failure::'+escaped, flush=True)
    destination = os.environ.get('GITHUB_STEP_SUMMARY')
    if destination:
        lines=['## FIRMAVEX regression selection', '',
               'Command: `python -m pytest ' + ' '.join(args).replace('`','') + '`', '',
               'Actual pytest exit status: **'+str(process.returncode)+'**', '']
        if report.exists():
            tree = ET.parse(report)
            cases = tree.findall('.//testcase')
            failed=[case for case in cases if case.find('failure') is not None or case.find('error') is not None]
            skipped=sum(case.find('skipped') is not None for case in cases)
            lines.append(f'JUnit cases: {len(cases)}; failures/errors: {len(failed)}; skipped: {skipped}.')
            for case in failed[:20]:
                problem=case.find('failure')
                if problem is None: problem=case.find('error')
                text=(problem.text or problem.get('message',''))[:4000].replace('```','~~~')
                lines.extend(['', '### '+case.get('classname','')+'.'+case.get('name',''), '```text', text, '```'])
        else:
            lines.extend(['No JUnit record was produced; collection or startup may have failed.',
                          '```text',process.stdout[-8000:].replace('```','~~~'),'```'])
        with Path(destination).open('a',encoding='utf-8') as stream:
            stream.write('\n'.join(lines)+'\n')
    return process.returncode

if __name__=='__main__':
    raise SystemExit(main())
