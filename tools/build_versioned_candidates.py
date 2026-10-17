"""Build distinct pinned Git revisions; retain identities, not renamed copies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

BASELINE='19cd45736337243c64a2298285781a27499981fa'


def build(baseline,candidate,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for label,source,version in [('baseline',Path(baseline).resolve(),'0.3.0.dev1'),('candidate',Path(candidate).resolve(),'0.3.0.dev2')]:
        revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        if label=='baseline' and revision!=BASELINE:raise ValueError('Wrong baseline Git revision')
        if label=='candidate' and revision==BASELINE:raise ValueError('Candidate is the same source revision')
        if subprocess.check_output(['git','-C',str(source),'status','--porcelain']):raise ValueError('Build requires a clean source checkout')
        if tomllib.loads((source/'pyproject.toml').read_text())['project']['version']!=version:raise ValueError('Wrong source product version')
        commands=[[sys.executable,'-m','PyInstaller','--clean','--noconfirm','packaging/desktop.spec'],
                  [sys.executable,'-m','tools.desktop_distribution_manifest','dist/FIRMAVEX']]
        if os.name=='nt':
            commands.append([str(Path(os.environ['ProgramFiles(x86)'])/'Inno Setup 6/ISCC.exe'),'packaging/windows.iss'])
            installer=source/'dist/FIRMAVEX-Windows-unsigned.exe';engine=source/'dist/FIRMAVEX/FIRMAVEX.exe'
        else:
            commands.append([sys.executable,'-m','tools.build_linux_deb','dist/FIRMAVEX','dist/FIRMAVEX-Linux-amd64.deb'])
            installer=source/'dist/FIRMAVEX-Linux-amd64.deb';engine=source/'dist/FIRMAVEX/FIRMAVEX'
        for index,command in enumerate(commands):
            log=output/f'{label}-{index}.log'
            with log.open('xb') as stream:
                result=subprocess.run(command,cwd=source,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
            if result.returncode:
                message=log.read_bytes()[-3500:].decode('utf-8',errors='replace').replace('%','%25').replace('\n','%0A').replace('\r','%0D')
                print('::error title=Distinct revision build '+label+'::'+message,flush=True)
                raise RuntimeError('Build failed: '+label)
        manifest=json.loads((engine.parent/'distribution-manifest.json').read_text(encoding='utf-8'))
        if manifest['git_revision']!=revision or manifest['dirty']:raise ValueError('Built provenance does not match clean source revision')
        row={'source_revision':revision,'version':version,
             'source_tree':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip(),
             'engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),
             'installer_sha256':hashlib.sha256(installer.read_bytes()).hexdigest()}
        rows.append(row)
        (output/f'{label}-identity.json').write_text(json.dumps(row,indent=2)+'\n')
    if rows[0]['engine_sha256']==rows[1]['engine_sha256'] or rows[0]['source_tree']==rows[1]['source_tree']:
        raise ValueError('Distinct source/binary revisions not established')
    print(json.dumps({'kind':'firmavex_distinct_installer_builds','builds':rows},sort_keys=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    build(args.baseline,args.candidate,args.output)
