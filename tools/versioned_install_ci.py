"""Real installer transitions on disposable Windows/Ubuntu CI hosts only.

Never use on a personal checkout/machine: this owns the FIRMAVEX installation.
Saved demonstration results are independent of both installation directories.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from firmavex.backends.api import Limits
from firmavex.backends.process import Processes,Cancelled
from firmavex.product.release_bundle import canonical

BASELINE='19cd45736337243c64a2298285781a27499981fa'


def snapshot(root):
    result={}
    for file in sorted(Path(root).rglob('*')):
        if file.is_symlink():raise ValueError('Unexpected result link')
        if file.is_file():result[file.relative_to(root).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
    if not result:raise ValueError('Missing saved result evidence')
    return result


@contextmanager
def environment(values):
    old=os.environ.copy()
    try:os.environ.clear();os.environ.update(values);yield
    finally:os.environ.clear();os.environ.update(old)


@contextmanager
def preserving_cleanup(callback):
    primary=None
    try:yield
    except BaseException as exc:primary=exc;raise
    finally:
        try:callback()
        except BaseException as failure:
            if primary is None:raise
            primary.add_note('Qualification resource cleanup failed: '+repr(failure))


def absolute_command(args, env):
    command=list(map(str,args))
    if not command:raise ValueError('Missing installer command')
    if not Path(command[0]).is_absolute():
        executable=shutil.which(command[0],path=env.get('PATH',os.defpath))
        if not executable:raise ValueError('Required installer tool unavailable: '+command[0])
        command[0]=str(Path(executable).resolve(strict=True))
    return command


class Qualification:
    def __init__(self,baseline,candidate,output):
        if os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('Disposable GitHub runner required; this tool installs/uninstalls system packages')
        self.baseline=Path(baseline).resolve();self.candidate=Path(candidate).resolve();self.root=Path(output).resolve()
        self.root.mkdir(parents=True,exist_ok=False);self.logs=self.root/'logs';self.logs.mkdir()
        self.rows=[];self.child_env=os.environ.copy();self.child_env['QT_QPA_PLATFORM']='offscreen'
        self.saved=self.root/'saved-baseline-demo';self.saved_hashes=None;self.counter=0
        self.revision=subprocess.check_output(['git','-C',str(self.candidate),'rev-parse','HEAD'],text=True).strip()
        actual=subprocess.check_output(['git','-C',str(self.baseline),'rev-parse','HEAD'],text=True).strip()
        if actual!=BASELINE or actual==self.revision:raise ValueError('Expected two distinct pinned Git revisions')

    def run(self,label,args,*,env=None,expect=0,cancel=None):
        args=absolute_command(args,env or os.environ)
        self.counter+=1
        owner=Processes(cancel or threading.Event(),Limits(timeout_seconds=300,artifact_bytes=64*1024**2,log_bytes=8*1024**2))
        primary=None
        row={'phase':label,'exit_code':None,'cleanup':[]}
        self.rows.append(row)
        try:
            with environment(env or os.environ.copy()):code,out,err=owner.run(list(map(str,args)),self.logs)
            (self.logs/f'{self.counter:02}-{label}.stdout').write_text(out,encoding='utf-8')
            (self.logs/f'{self.counter:02}-{label}.stderr').write_text(err,encoding='utf-8')
            row['exit_code']=code
            if expect==0 and code!=0:
                installer_tail=''
                for arg in args:
                    if str(arg).upper().startswith('/LOG='):
                        log=Path(str(arg)[5:]).resolve()
                        if log.is_relative_to(self.logs.resolve()) and log.is_file():
                            with log.open('rb') as stream:
                                stream.seek(max(0,log.stat().st_size-4096));raw=stream.read(4096)
                            installer_tail=raw.decode('utf-16-le' if b'\x00' in raw else 'utf-8',errors='replace')
                row['installer_log_tail']=installer_tail
                raise RuntimeError(label+' exit_code='+str(code)+': '+err[-1500:]+out[-500:]+installer_tail[-1800:])
            if expect=='failure' and code==0:raise RuntimeError(label+' unexpectedly succeeded')
            return code,out,err
        except BaseException as exc:
            primary=exc;row['failure']={'type':type(exc).__name__,'diagnostic':str(exc)};raise
        finally:
            try:
                owner.close()
                row['cleanup']=owner.cleanup
            except BaseException as cleanup:
                row['cleanup_failure']={'type':type(cleanup).__name__,'diagnostic':str(cleanup)}
                if primary is None:raise
                primary.add_note('Installer process cleanup failed: '+repr(cleanup))

    def unchanged(self):
        if snapshot(self.saved)!=self.saved_hashes:raise RuntimeError('Authoritative saved result/evidence bytes changed')

    def inspect(self,label):
        self.run(label,[self.engine,'--firmavex-cli','inspect',self.saved/'search'],env=self.child_env)
        self.unchanged()

    def gui(self,label):
        self.run(label,[self.gui_engine,'--smoke-test'],env=self.child_env)

    def identity(self,label,expected):
        installed=self.engine.parent/'distribution-manifest.json'
        record=json.loads(installed.read_text(encoding='utf-8'))
        if record['git_revision']!=expected:raise RuntimeError('Wrong installed source revision')
        actual=hashlib.sha256(self.engine.read_bytes()).hexdigest()
        if record['files'][self.engine.name]['sha256']!=actual:raise RuntimeError('Installed executable differs from built revision')
        if os.name!='nt':
            installed_version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','firmavex-desktop'],text=True).strip()
            wanted='0.3.0~dev1' if expected==BASELINE else '0.3.0~dev2'
            if installed_version!=wanted:raise RuntimeError('Wrong installed package version')
        elif expected!=BASELINE and record.get('application_version')!='0.3.0.dev2':
            raise RuntimeError('Wrong candidate version metadata')
        return {'phase':label,'git_revision':expected,'engine_sha256':actual,'application_version':record.get('application_version','0.3.0.dev1 (pinned baseline)')}

    def windows(self):
        destination=self.root/'installed application';self.engine=destination/'FIRMAVEX.exe';self.gui_engine=destination/'FIRMAVEX-Desktop.exe'
        self.child_env['LOCALAPPDATA']=str(self.root/'user data')
        # Reuse the legally separate, locally produced signed-vendor snapshot.
        from firmavex.product.runtime_setup import snapshot_runtime
        from firmavex.product.runtime_pack import install
        ucrt=Path(os.environ['MSYS2_LOCATION'])/'ucrt64'
        archive=self.root/'local-runtime.zip'
        packages=Path(os.environ['FIRMAVEX_VENDOR_PACKAGES_FILE']).read_text(encoding='utf-8')
        with environment(self.child_env):
            digest=snapshot_runtime(ucrt,archive,packages=packages)
            activation=install(archive,digest)
        self.rows.append({'phase':'signed_vendor_local_snapshot','sha256':digest,'activation':activation})
        self.child_env['PATH']=os.environ['SystemRoot']+';'+os.environ['SystemRoot']+'\\System32'
        if shutil.which('python',path=self.child_env['PATH']) or shutil.which('arm-none-eabi-gcc',path=self.child_env['PATH']):raise RuntimeError('Developer tool present on child PATH')
        older=self.baseline/'dist/FIRMAVEX-Windows-unsigned.exe';newer=self.candidate/'dist/FIRMAVEX-Windows-unsigned.exe'
        def args(installer,log):return [installer,'/SP-','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/DIR='+str(destination),'/LOG='+str(log)]
        self.run('install-baseline',args(older,self.logs/'baseline-install.log'))
        self.rows.append(self.identity('baseline-identity',BASELINE));self.gui('baseline-gui')
        self.run('baseline-real-firmware',[self.engine,'--firmavex-cli','demo-builtin','--output-dir',self.saved],env=self.child_env)
        from tools.desktop_native_evidence import capture
        self.rows.append({'phase':'baseline-real-receipts','evidence':capture(self.saved)})
        self.saved_hashes=snapshot(self.saved)
        # Observe an actual Inno file-install log entry, then cancel the owned
        # installer tree. A too-fast completed installer is NOT counted as an interruption.
        log=self.logs/'interrupted-upgrade.log';cancel=threading.Event();stop=threading.Event();observed=[]
        def interrupt():
            while not stop.wait(.01):
                if log.exists():
                    raw=log.read_bytes()
                    if b'Installing the file' in raw or 'Installing the file'.encode('utf-16-le') in raw:
                        observed.append(True);cancel.set();return
        thread=threading.Thread(target=interrupt,daemon=True);thread.start()
        interrupted=False
        try:self.run('interrupted-upgrade',args(newer,log),cancel=cancel)
        except Cancelled:
            if self.rows[-1].get('cleanup_failure'):raise
            interrupted=True
        finally:stop.set();thread.join(2)
        if not interrupted or not observed:raise RuntimeError('Actual installer interruption was not established')
        self.unchanged();self.rows.append({'phase':'interrupted-installation','observed_file_installation':True,'cancelled_owned_tree':True})
        self.run('recover-upgrade',args(newer,self.logs/'recovered-upgrade.log'))
        self.rows.append(self.identity('candidate-identity',self.revision));self.gui('candidate-gui');self.inspect('upgraded-reopen')
        # Supported rollback is uninstall-new/install-old, never an unsupported
        # in-place downgrade or a schema migration claim.
        self.run('uninstall-candidate',[destination/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(self.logs/'uninstall-candidate.log')]);self.unchanged()
        self.run('rollback-install-baseline',args(older,self.logs/'rollback.log'));self.rows.append(self.identity('rollback-identity',BASELINE));self.inspect('rollback-reopen')
        self.run('uninstall-baseline',[destination/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(self.logs/'uninstall-baseline.log')]);self.unchanged()
        self.run('reinstall-candidate',args(newer,self.logs/'reinstall.log'));self.inspect('reinstall-reopen')
        self.run('final-uninstall',[destination/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(self.logs/'final-uninstall.log')]);self.unchanged()
        return {'offline_network_enforced':False,'standard_user_token':'not_independently_qualified','low_disk_installer':'not_qualified'}

    def linux(self):
        self.engine=Path('/opt/firmavex/FIRMAVEX');self.gui_engine=Path('/opt/firmavex/FIRMAVEX-Desktop')
        if os.geteuid()==0:raise RuntimeError('Application acceptance must run as ordinary runner user')
        tool_dir=self.root/'runtime-only';tool_dir.mkdir()
        for name in ('qemu-system-arm','gdb-multiarch'):
            target=shutil.which(name)
            if not target:raise RuntimeError('Missing native runtime '+name)
            (tool_dir/name).symlink_to(target)
        self.child_env['PATH']=str(tool_dir)
        older=self.baseline/'dist/FIRMAVEX-Linux-amd64.deb';newer=self.candidate/'dist/FIRMAVEX-Linux-amd64.deb'
        self.run('install-baseline',['sudo','dpkg','-i',older]);self.rows.append(self.identity('baseline-identity',BASELINE));self.gui('baseline-gui')
        self.run('baseline-real-firmware',[self.engine,'--firmavex-cli','demo-builtin','--output-dir',self.saved],env=self.child_env)
        from tools.desktop_native_evidence import capture
        self.rows.append({'phase':'baseline-real-receipts','evidence':capture(self.saved)});self.saved_hashes=snapshot(self.saved)
        # Real package-manager phase boundary: unpacked but not configured.
        self.run('upgrade-unpack',['sudo','dpkg','--unpack',newer]);self.unchanged()
        _,state,_=self.run('unconfigured-state',['dpkg-query','-W','-f=${Status}','firmavex-desktop'])
        if state.strip()!='install ok unpacked':raise RuntimeError('Unconfigured interruption boundary missing')
        self.run('recover-configure',['sudo','dpkg','--configure','firmavex-desktop']);self.rows.append(self.identity('candidate-identity',self.revision));self.gui('candidate-gui');self.inspect('upgraded-reopen')
        # Real low-space installer failure, confined to this disposable app's
        # /opt directory; never fill the runner root filesystem.
        mounted=False
        with preserving_cleanup(lambda: self.run('unmount-low-space',['sudo','umount','/opt/firmavex']) if mounted else None):
            self.run('mount-low-space',['sudo','mount','-t','tmpfs','-o','size=16k','tmpfs','/opt/firmavex']);mounted=True
            _,out,err=self.run('low-space-install',['sudo','dpkg','-i',newer],expect='failure')
            if 'No space left' not in out+err:raise RuntimeError('Installer failure did not establish ENOSPC')
            self.unchanged()
        self.run('repair-low-space',['sudo','dpkg','-i',newer]);self.inspect('repaired-reopen')
        restricted=self.root/'restricted';restricted.mkdir();restricted.chmod(0o500)
        with preserving_cleanup(lambda: restricted.chmod(0o700)):self.run('restricted-output',[self.engine,'--firmavex-cli','prepare-example','--output-dir',restricted/'output'],env=self.child_env,expect='failure')
        self.unchanged()
        self.run('rollback-baseline',['sudo','dpkg','-i',older]);self.rows.append(self.identity('rollback-identity',BASELINE));self.inspect('rollback-reopen')
        self.run('uninstall',['sudo','dpkg','-r','firmavex-desktop']);self.unchanged()
        self.run('reinstall',['sudo','dpkg','-i',newer]);self.inspect('reinstall-reopen')
        # Drop root privileges inside an independently isolated network namespace.
        command=['sudo','unshare','--net','/bin/sh','-c','/usr/sbin/ip link set lo up && exec "$@"','sh','/usr/bin/sudo','-u','#'+str(os.getuid()),'/usr/bin/env','PATH='+str(tool_dir),'QT_QPA_PLATFORM=offscreen',str(self.engine),'--firmavex-cli','demo-builtin','--output-dir',str(self.root/'offline-demo')]
        self.run('offline-real-firmware',command)
        self.rows.append({'phase':'offline-receipts','evidence':capture(self.root/'offline-demo')})
        self.run('final-uninstall',['sudo','dpkg','-r','firmavex-desktop']);self.unchanged()
        return {'offline_network_enforced':True,'standard_user_application':True,'interruption_scope':'real unpack/configure boundary; not arbitrary mid-copy power loss'}

    def execute(self):
        record={'schema_version':1,'kind':'firmavex_versioned_installer_qualification','baseline_git_revision':BASELINE,
                'candidate_git_revision':self.revision,'baseline_version':'0.3.0.dev1','candidate_version':'0.3.0.dev2',
                'platform':sys.platform,'measurement':'real_hosted_ci_not_physical_consumer','passed':False,'phases':self.rows}
        primary=None
        try:
            record['limitations']=self.windows() if os.name=='nt' else self.linux()
            record.update(passed=True,saved_file_sha256=self.saved_hashes)
            return record
        except BaseException as exc:
            primary=exc
            record['failure']={'type':type(exc).__name__,'diagnostic':str(exc)};raise
        finally:
            try:(self.root/'versioned-lifecycle.json').write_bytes(canonical(record))
            except BaseException as failure:
                if primary is None:raise
                primary.add_note('Qualification receipt persistence failed: '+repr(failure))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
    try:
        result=Qualification(args.baseline,args.candidate,args.output).execute()
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as exc:
        message=str(exc)[-3500:].replace('%','%25').replace('\n','%0A').replace('\r','%0D')
        print('::error title=Versioned installer qualification::'+message);return 1

if __name__=='__main__':raise SystemExit(main())
