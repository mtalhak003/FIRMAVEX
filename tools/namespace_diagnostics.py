"""Disposable-root, fixed namespace reproducer and kernel-policy diagnostics.

Diagnostic comparisons are not security qualification and run no user workload.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import time
import uuid


def capture(user,output):
    if os.environ.get('GITHUB_ACTIONS')!='true' or sys.platform!='linux' or os.geteuid()!=0:raise ValueError('Disposable native Linux CI administrator required')
    account=pwd.getpwnam(user)
    if account.pw_uid==0:raise ValueError('Unprivileged reproducer account required')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    bwrap=shutil.which('bwrap');ip=shutil.which('ip')
    if not bwrap or not ip:raise ValueError('Bubblewrap/iproute2 required')
    record={'kind':'firmavex_namespace_policy_diagnostic','security_qualification':False,'untrusted_execution_authorized':False,'cases':[],'host':{}}
    for path in ['/proc/version','/proc/self/status','/proc/self/attr/current','/sys/kernel/security/lsm','/proc/sys/kernel/unprivileged_userns_clone','/proc/sys/kernel/apparmor_restrict_unprivileged_userns']:
        try:record['host'][path]=Path(path).read_text()[:8192]
        except OSError as exc:record['host'][path]={'unavailable':str(exc)}
    for label,properties in [('plain',[]),('no_new_privileges',['NoNewPrivileges=yes']),('protected_kernel',['ProtectKernelTunables=yes']),('combined',['NoNewPrivileges=yes','ProtectKernelTunables=yes','ProtectControlGroups=yes','RestrictSUIDSGID=yes'])]:
        unit='firmavex-netdiag-'+uuid.uuid4().hex+'.service'
        stdout=output/(label+'.stdout');stderr=output/(label+'.stderr')
        # Only the fixed /bin/true runs. Minimal bwrap reproduction includes the
        # network/user namespaces and readonly root; no firmware or HDL is loaded.
        command=['systemd-run','--quiet','--wait','--unit='+unit,'--property=User='+user,'--property=MemoryMax=268435456','--property=MemorySwapMax=0','--property=TasksMax=32','--property=CPUQuota=50%','--property=RuntimeMaxSec=15s','--property=KillMode=control-group','--property=StandardOutput=append:'+str(stdout),'--property=StandardError=append:'+str(stderr)]
        command+=['--property='+p for p in properties]
        command+=[bwrap,'--unshare-user','--unshare-net','--die-with-parent','--new-session','--ro-bind','/','/','/bin/true']
        row={'case':label,'properties':properties,'argv':command};record['cases'].append(row)
        primary=None
        try:
            r=subprocess.run(command,capture_output=True,text=True,timeout=25);row.update(returncode=r.returncode,supervisor_stderr=r.stderr[-2048:])
        except BaseException as exc:primary=exc;row['exception']=repr(exc);raise
        finally:
            try:
                stop=subprocess.run(['systemctl','stop',unit],capture_output=True,text=True,timeout=10)
                final=subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','ControlGroup'],capture_output=True,text=True,timeout=10)
                row['final_supervisor_state']=final.stdout
                row['cleanup_verified']=stop.returncode==0 and 'ControlGroup=\n' in final.stdout and ('ActiveState=inactive' in final.stdout or 'ActiveState=failed' in final.stdout)
                for channel,path in [('stdout',stdout),('stderr',stderr)]:row[channel]=path.read_text(errors='replace')[-8192:] if path.exists() else ''
                subprocess.run(['systemctl','reset-failed',unit],capture_output=True,timeout=10)
            except BaseException as cleanup:
                if primary is None:raise
                primary.add_note('Diagnostic cleanup failed: '+repr(cleanup))
            (output/'diagnostics.json').write_text(json.dumps(record,indent=2)+'\n')
        if not row['cleanup_verified']:raise RuntimeError('Unverified diagnostic cleanup')
    journal=subprocess.run(['journalctl','-k','--since','10 minutes ago','--no-pager'],capture_output=True,text=True,timeout=10)
    record['kernel_denials']=[line for line in journal.stdout.splitlines() if any(word in line.lower() for word in ('bwrap','userns','netlink'))][-30:]
    record['journal_returncode']=journal.returncode
    (output/'diagnostics.json').write_text(json.dumps(record,indent=2)+'\n')
    print('::notice title=Namespace minimal reproducer::'+json.dumps(record,sort_keys=True)[-3500:].replace('%','%25').replace('\n','%0A').replace('\r','%0D'))
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--user',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    capture(a.user,a.output)
