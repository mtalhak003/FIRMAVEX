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
import shutil
import xml.etree.ElementTree as ET


def run_tests(args, report):
    """Stream bounded diagnostic history; own pytest descendants on every exit."""
    from firmavex.product.windows_job import WindowsJob
    command = [sys.executable, '-u', '-c',
               "import sys,runpy; sys.stdin.buffer.read(1); sys.argv[0]='pytest'; runpy.run_module('pytest',run_name='__main__')", '-p',
               'tools.product_ci_diagnostics', *args, '--junitxml='+str(report)]
    kwargs = {'start_new_session': True} if os.name == 'posix' else {}
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
            owner = WindowsJob()
            owner.assign(int(process._handle))
        process.stdin.write(b'1')
        process.stdin.close()
        reader = threading.Thread(target=stream, daemon=True)
        reader.start()
        try:
            process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            print('::error::Pytest selection exceeded 900s; terminating owned test tree.', flush=True)
            raise
    finally:
        if owner is not None:
            owner.close()
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        if 'reader' in locals():
            reader.join(timeout=10)
            if reader.is_alive():
                raise RuntimeError('CI output reader did not finish after owned tree cleanup')
        process.stdout.close()
        transcript.close()
    with lock:
        output = bytes(history).decode('utf-8', errors='replace')
    return subprocess.CompletedProcess(command, process.returncode, stdout=output)


def main(arguments=None):
    args = sys.argv[1:] if arguments is None else arguments
    with tempfile.TemporaryDirectory(prefix='firmavex-ci-') as directory:
        report = Path(directory)/'pytest.xml'
        try:
            process = run_tests(args, report)
        finally:
            destination = os.environ.get('FIRMAVEX_CI_DIAGNOSTICS')
            if destination:
                archive = Path(destination) / Path(directory).name
                archive.mkdir(parents=True, exist_ok=False)
                for source in Path(directory).iterdir():
                    shutil.copyfile(source, archive/source.name)
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
