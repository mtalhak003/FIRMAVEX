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
import xml.etree.ElementTree as ET


def main(arguments=None):
    args = sys.argv[1:] if arguments is None else arguments
    with tempfile.TemporaryDirectory(prefix='firmavex-ci-') as directory:
        report = Path(directory)/'pytest.xml'
        process = subprocess.run([sys.executable, '-m', 'pytest', *args, '--junitxml='+str(report)],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
        print(process.stdout, end='', flush=True)
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
