"""Fixed systemd-supervised Linux quota assessment; never a general worker.

Requires administrator authorization on a disposable host with a running systemd.
It cannot accept workload paths, commands or arbitrary guest code. Positive checks
are feasibility evidence, not independent sandbox qualification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

GUESTS={
 'cpu':"import time,json;s=time.monotonic();c=time.process_time();\nwhile time.monotonic()-s<2: pass\nprint(json.dumps({'wall':time.monotonic()-s,'cpu':time.process_time()-c}))",
 'pids':"""import os,time,json,resource
children=[];denied=False;quota_write_denied=False
group=next(line[3:] for line in open('/proc/self/cgroup').read().splitlines() if line.startswith('0::'))
try:open('/sys/fs/cgroup'+group+'/pids.max','w').write('max')
except OSError as e:
 if e.errno not in (1,13,30):raise
 quota_write_denied=True
try:
 for _ in range(16):
  try: pid=os.fork()
  except OSError as e:
   if e.errno!=11:raise
   denied=True;break
  if pid==0:time.sleep(.5);os._exit(0)
  children.append(pid)
 print(json.dumps({'spawned':len(children),'denied':denied,'quota_write_denied':quota_write_denied,'rlimit_nproc':resource.getrlimit(resource.RLIMIT_NPROC)}),flush=True)
finally:
 for pid in children:os.waitpid(pid,0)
""",
 'memory':"import sys;print('fixed-memory-probe-admitted',flush=True);data=bytearray(512*1024**2);\nfor i in range(0,len(data),4096):data[i]=1\nprint(len(data),flush=True)",
}


def admission():
    return {'linux':sys.platform.startswith('linux'),'systemd_running':Path('/run/systemd/system').is_dir(),
            'systemd_run_available':shutil.which('systemd-run') is not None,
            'administrator':os.name=='posix' and os.geteuid()==0,
            'unprivileged_cgroup_writable':os.access('/sys/fs/cgroup',os.W_OK),
            'kvm_device_present':Path('/dev/kvm').exists()}


def unit_command(unit,user,mode,*,source,python,namespace_output):
    if mode not in {*GUESTS,'namespace'}:raise ValueError('Only fixed probe modes are supported')
    memory='256M' if mode=='namespace' else '128M'
    tasks='8' if mode=='pids' else '64'
    log_root=Path(namespace_output).parent.parent
    command=['systemd-run','--quiet','--service-type=exec','--unit='+unit,
             '--property=StandardOutput=append:'+str(log_root/(unit+'.stdout')),
             '--property=StandardError=append:'+str(log_root/(unit+'.stderr')),
             '--property=LimitFSIZE=1048576',
             '--property=User='+str(user),'--property=WorkingDirectory='+str(source),
             '--property=MemoryAccounting=yes','--property=CPUAccounting=yes',
             '--property=MemoryMax='+memory,'--property=MemorySwapMax=0','--property=TasksMax='+tasks,
             '--property=CPUQuota=50%','--property=RuntimeMaxSec=30s',
             '--property=RemainAfterExit=yes','--property=NoNewPrivileges=yes','--property=ProtectControlGroups=yes',
             '--property=ProtectKernelTunables=yes','--property=RestrictSUIDSGID=yes',
             '--property=KillMode=control-group','--property=TimeoutStopSec=5s']
    marker=log_root/(unit+'.admit')
    action=("os.execv("+repr(str(python))+","+repr([str(python),'-m','tools.isolation_feasibility','--output',str(namespace_output)])+")") if mode=='namespace' else GUESTS[mode]
    bootstrap="import os,time\ndeadline=time.monotonic()+10\nwhile not os.path.exists("+repr(str(marker))+"):\n if time.monotonic()>deadline:raise RuntimeError('Supervisor admission not granted')\n time.sleep(.02)\n"+action
    command+=['/usr/bin/python3','-c',bootstrap]
    return command


def guest_account(user):
    import pwd
    return pwd.getpwnam(user)


def assess(*,source,python,user,output):
    if Path(source).resolve()!=Path(__file__).resolve().parents[1] or Path(python).resolve()!=Path(sys.executable).resolve():
        raise ValueError('Only this checkout and executing interpreter can launch the fixed probe')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    capability=admission()
    record={'schema_version':1,'kind':'firmavex_aggregate_isolation_feasibility',
            'admission':capability,'checks':{},'units':[],
            'untrusted_execution_authorized':False,'sandbox_qualification':'not_established',
            'scope':'fixed probes only; no hostile workload authorization or public execution API'}
    if not all(capability[k] for k in ('linux','systemd_running','systemd_run_available','administrator')):
        record.update(status='blocked',diagnostic='Root-authorized running systemd supervisor required; no resource limit was bypassed')
        (output/'assessment.json').write_text(json.dumps(record,indent=2)+'\n');return record
    account=guest_account(user)
    if account.pw_uid==0:raise ValueError('The fixed guest must use an unprivileged account')
    guest_output=output/'guest';guest_output.mkdir()
    os.chown(guest_output,account.pw_uid,account.pw_gid)
    # Root checks the configured external limits after execution. The guest cannot
    # author the verdict or alter its control group. Keep units until readback.
    primary=None
    try:
        for mode in ('cpu','pids','memory','namespace'):
            name='firmavex-fixed-'+uuid.uuid4().hex+'.service'
            namespace_output=guest_output/'namespace.json'
            row={'mode':mode,'unit':name};record['units'].append(row)
            try:
                command=unit_command(name,user,mode,source=source,python=python,namespace_output=namespace_output)
                admission_result=subprocess.run(command,capture_output=True,timeout=15)
                row['admission_exit_code']=admission_result.returncode
                row['admission_diagnostics']=admission_result.stderr.decode('utf-8',errors='replace')[-4096:]
                deadline=time.monotonic()+35
                while True:
                    props=subprocess.run(['systemctl','show',name,'-p','Result','-p','MemoryMax','-p','MemoryPeak','-p','MemorySwapMax','-p','TasksMax','-p','CPUQuotaPerSecUSec','-p','CPUUsageNSec','-p','ActiveState','-p','SubState','-p','ExecMainCode','-p','ExecMainStatus','-p','ControlGroup'],capture_output=True,text=True,timeout=10,check=True)
                    fields=dict(line.split('=',1) for line in props.stdout.splitlines() if '=' in line)
                    if 'kernel_limits' not in row and fields.get('ControlGroup'):
                        group=fields['ControlGroup']
                        if not group.startswith('/system.slice/') or Path(group).name!=name or '..' in Path(group).parts:
                            raise RuntimeError('Unexpected supervised cgroup path')
                        root=Path('/sys/fs/cgroup')/group.lstrip('/')
                        limits={key:(root/key).read_text().strip() for key in ('memory.max','memory.swap.max','pids.max','cpu.max')}
                        quota,period=limits['cpu.max'].split()
                        wanted_memory=str(256*1024**2 if mode=='namespace' else 128*1024**2)
                        if (limits['memory.max']!=wanted_memory or limits['memory.swap.max']!='0'
                                or limits['pids.max']!=('8' if mode=='pids' else '64')
                                or quota=='max' or int(quota)*2!=int(period)):
                            raise RuntimeError('Effective kernel quotas were not admitted')
                        row['kernel_limits']=limits;row['kernel_cgroup']=group
                        with (output/(name+'.admit')).open('xb') as marker:marker.write(b'fixed-probe-admitted\n')
                    if fields.get('SubState')=='exited' or fields.get('ActiveState') in {'failed','inactive'}:break
                    if time.monotonic()>=deadline:raise TimeoutError('Fixed supervised unit did not finish')
                    time.sleep(.1)
                row['supervisor_readback']=fields
                if 'kernel_limits' not in row:raise RuntimeError('Fixed probe never received verified kernel admission')
                code=int(fields.get('ExecMainStatus','1'))
                if fields.get('ExecMainCode') in {'2','3'}:code+=128
                row['returncode']=code if admission_result.returncode==0 else admission_result.returncode
                for channel in ('stdout','stderr'):
                    path=output/(name+'.'+channel)
                    if path.exists() and path.stat().st_size>1024**2:raise ValueError('Supervisor log limit exceeded')
                    row[channel]=path.read_text(encoding='utf-8',errors='replace')[-8192:] if path.exists() else ''
                configured=(fields.get('MemoryMax')==str(256*1024**2 if mode=='namespace' else 128*1024**2)
                            and fields.get('MemorySwapMax')=='0'
                            and fields.get('TasksMax')==('8' if mode=='pids' else '64')
                            and fields.get('CPUQuotaPerSecUSec')=='500ms')
                if not configured:raise RuntimeError('External quota readback differs from requested limits')
                if mode=='cpu':
                    values=json.loads(row['stdout'].splitlines()[-1])
                    record['checks']['cpu_quota']=row['returncode']==0 and values['wall']>=2 and 0<values['cpu']<=values['wall']*.7+.1
                elif mode=='pids':
                    values=json.loads(row['stdout'].splitlines()[-1])
                    record['checks']['process_quota']=row['returncode']==0 and values['denied'] is True and values['quota_write_denied'] is True and 1<=values['spawned']<=7 and (values['rlimit_nproc'][0]==-1 or values['rlimit_nproc'][0]>32)
                elif mode=='memory':
                    record['checks']['aggregate_memory_kill']=row['returncode']!=0 and fields.get('Result')=='oom-kill' and 'fixed-memory-probe-admitted' in row['stdout']
                else:
                    if not namespace_output.exists():raise RuntimeError('No fixed namespace assessment was produced')
                    nested=json.loads(namespace_output.read_text());row['namespace_assessment']=nested
                    record['checks']['filesystem_process_network_boundaries']=(row['returncode']==0 and nested['status']=='mechanism_checks_passed_not_qualified' and all(nested['checks'].values()) and nested['untrusted_execution_authorized'] is False)
            finally:
                original=sys.exception()
                try:
                    cleanup=subprocess.run(['systemctl','stop',name],capture_output=True,text=True,timeout=15)
                    row['stop_exit_code']=cleanup.returncode
                    final=subprocess.run(['systemctl','show',name,'-p','ActiveState','-p','LoadState','-p','ControlGroup'],capture_output=True,text=True,timeout=10)
                    row['final_supervisor_state']=final.stdout
                    row['cleanup_verified']=cleanup.returncode==0 and final.returncode in (0,1) and ('ActiveState=inactive' in final.stdout or 'ActiveState=failed' in final.stdout) and 'ControlGroup=\n' in final.stdout
                    group=row.get('kernel_cgroup')
                    if group:
                        procs=Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs'
                        if procs.exists() and procs.read_text().strip():row['cleanup_verified']=False
                    subprocess.run(['systemctl','reset-failed',name],capture_output=True,timeout=10)
                except BaseException as cleanup_error:
                    row['cleanup_verified']=False;row['cleanup_failure']=repr(cleanup_error)
                    if original is None:raise
                    original.add_note('Independent unit cleanup failed: '+repr(cleanup_error))
            if row.get('cleanup_verified') is not True:raise RuntimeError('Supervisor cleanup unverified; no further probes admitted')
            if not all(record['checks'].values()):raise RuntimeError('Fixed quota/boundary check failed; no further probes admitted')
        record['checks']['supervisor_cleanup']=all(row.get('cleanup_verified') is True for row in record['units'])
        record['status']='fixed_checks_passed_not_qualified' if len(record['checks'])==5 and all(record['checks'].values()) else 'failed'
    except BaseException as exc:
        primary=exc
        record.update(status='failed',diagnostic=repr(exc))
        if not isinstance(exc,Exception):raise
    finally:
        try:(output/'assessment.json').write_text(json.dumps(record,indent=2)+'\n')
        except BaseException as persistence:
            if primary is None:raise
            primary.add_note('Isolation assessment persistence failed: '+repr(persistence))
    return record


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--python',type=Path,required=True);p.add_argument('--user',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
    try:
        record=assess(source=args.source.resolve(strict=True),python=args.python.resolve(strict=True),user=args.user,output=args.output)
        print(json.dumps(record,sort_keys=True))
        if record['status']!='fixed_checks_passed_not_qualified':
            print('::error title=Aggregate isolation not qualified::'+str(record.get('diagnostic',record['checks']))[-3000:]);return 1
        return 0
    except Exception as exc:
        print('::error title=Aggregate isolation failure::'+str(exc)[-3000:]);return 1

if __name__=='__main__':raise SystemExit(main())
