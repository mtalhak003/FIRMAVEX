"""Fixed Linux namespace diagnostic. Never accepts or executes user workloads.

This is a feasibility assessment, not an independently qualified sandbox worker.
Even a successful probe never authorizes untrusted execution.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import tempfile
import threading

from firmavex.backends.api import Limits
from firmavex.backends.process import Processes, Cancelled

REQUIRED_CHECKS = frozenset({'input_readable', 'input_read_only', 'runtime_read_only',
                             'host_path_absent', 'host_pid_absent', 'independent_namespaces',
                             'only_loopback', 'host_listener_unreachable', 'inherited_limits',
                             'memory_allocation_denied', 'storage_write_bounded'})

GUEST = r'''
import errno,json,os,pathlib,resource,socket
expected=json.loads(__import__('sys').argv[1])
checks={}
checks['input_readable']=pathlib.Path('/input/marker').read_text()=='fixed probe input'
for label,path in [('input_read_only','/input/new'),('runtime_read_only','/usr/new')]:
 try: pathlib.Path(path).write_text('forbidden');checks[label]=False
 except OSError as exc:checks[label]=exc.errno in (errno.EROFS,errno.EACCES)
checks['host_path_absent']=not pathlib.Path(expected['host_marker']).exists()
checks['host_pid_absent']=not pathlib.Path('/proc/'+str(expected['host_pid'])).exists()
checks['independent_namespaces']=all(os.readlink('/proc/self/ns/'+key)!=value for key,value in expected['namespaces'].items())
checks['only_loopback']=socket.if_nameindex()==[(1,'lo')]
sock=socket.socket();sock.settimeout(.3)
try:sock.connect(('127.0.0.1',expected['host_port']));checks['host_listener_unreachable']=False
except OSError:checks['host_listener_unreachable']=True
finally:sock.close()
limits={key:list(resource.getrlimit(value)) for key,value in [('address_space',resource.RLIMIT_AS),('cpu',resource.RLIMIT_CPU),('file_size',resource.RLIMIT_FSIZE)]}
checks['inherited_limits']=limits['address_space'][0]==536870912 and limits['cpu'][0]==9 and limits['file_size'][0]==1048576
try: bytearray(600*1024**2); checks['memory_allocation_denied']=False
except MemoryError: checks['memory_allocation_denied']=True
try:
 with open('/work/large','wb') as stream:stream.write(b'x'*(2*1024**2))
 checks['storage_write_bounded']=False
except OSError as exc:checks['storage_write_bounded']=exc.errno in (errno.ENOSPC,errno.EFBIG)
checks['storage_write_bounded']=checks['storage_write_bounded'] and pathlib.Path('/work/large').stat().st_size<=1048576
# PID namespace init exit must reap a deliberately lingering owned descendant.
child=os.fork()
if child==0:
 import time;time.sleep(60);os._exit(0)
print(json.dumps({'checks':checks,'limits':limits,'guest_pid':os.getpid()}),flush=True)
'''


def remaining_owned(token):
    remaining, errors = [], []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            if token in (entry / 'cmdline').read_bytes():
                remaining.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            errors.append(int(entry.name))
    return remaining, errors


def assess(cancel=None):
    record = {'schema_version': 1, 'kind': 'firmavex_isolation_feasibility',
              'platform': platform.system(), 'untrusted_execution_authorized': False,
              'sandbox_qualification': 'not_established', 'status': 'blocked',
              'aggregate_cgroup_quotas': 'not_validated',
              'independent_security_review': 'required', 'checks': {}, 'diagnostics': ''}
    bwrap = shutil.which('bwrap')
    if platform.system() != 'Linux' or not bwrap or not Path('/usr/bin/python3').is_file():
        record['diagnostics'] = 'Linux, Bubblewrap and /usr/bin/python3 are required; no workload was dispatched.'
        return record
    with tempfile.TemporaryDirectory(prefix='firmavex-isolation-probe-') as temporary, socket.socket() as listener:
        root = Path(temporary)
        source = root / 'input'; source.mkdir(); (source / 'marker').write_text('fixed probe input')
        marker = root / 'host-private'; marker.write_text('not mounted')
        listener.bind(('127.0.0.1', 0)); listener.listen(1)
        expected = {'host_marker': str(marker), 'host_pid': os.getpid(),
                    'host_port': listener.getsockname()[1],
                    'namespaces': {key: os.readlink('/proc/self/ns/' + key) for key in ('mnt', 'pid', 'net', 'user')}}
        argv = [bwrap, '--unshare-all', '--unshare-user', '--die-with-parent', '--new-session',
                '--cap-drop', 'ALL', '--disable-userns', '--clearenv',
                '--setenv', 'PATH', '/usr/bin', '--setenv', 'LC_ALL', 'C',
                '--ro-bind', '/usr', '/usr']
        for name in ('bin', 'lib', 'lib64'):
            path = Path('/') / name
            if path.is_symlink(): argv += ['--symlink', str(path.readlink()), '/' + name]
            elif path.is_dir(): argv += ['--ro-bind', str(path), '/' + name]
        argv += ['--ro-bind', str(source), '/input', '--proc', '/proc', '--dev', '/dev',
                 '--size', '65536', '--tmpfs', '/tmp', '--size', '1048576', '--tmpfs', '/work',
                 '--chdir', '/work', '/usr/bin/python3', '-I', '-c', GUEST, json.dumps(expected)]
        owner = Processes(cancel if cancel is not None else threading.Event(), Limits(timeout_seconds=8, memory_bytes=536870912,
                                                   log_bytes=32768, artifact_bytes=1048576))
        original = None
        try:
            code, out, err = owner.run(argv, root)
            record['return_code'] = code
            record['diagnostics'] = err[-8192:]
            if code == 0:
                result = json.loads(out)
                if (type(result) is not dict or set(result) != {'checks', 'limits', 'guest_pid'}
                        or type(result.get('guest_pid')) is not int or result['guest_pid'] < 1
                        or result.get('limits') != {'address_space': [536870912, 536870912],
                                                    'cpu': [9, 9], 'file_size': [1048576, 1048576]}
                        or type(result.get('checks')) is not dict
                        or set(result['checks']) != REQUIRED_CHECKS
                        or any(type(value) is not bool for value in result['checks'].values())):
                    raise ValueError('Missing fixed boundary probe results')
                record['checks'] = result['checks']
                record['limits'] = result['limits']
                record['guest_pid'] = result['guest_pid']
                record['status'] = 'mechanism_checks_passed_not_qualified' if all(value is True for value in result['checks'].values()) else 'boundary_check_failed'
        except Exception as exc:
            record['status'] = 'cancelled' if isinstance(exc, Cancelled) else 'assessment_failed'
            record['diagnostics'] = type(exc).__name__ + ': ' + str(exc)
        except BaseException as exc:
            original = exc
            raise
        finally:
            try: owner.close()
            except BaseException as exc:
                if original is not None:
                    original.add_note('Isolation diagnostic cleanup failed: ' + str(exc))
                elif isinstance(exc, Exception):
                    record['status'] = 'cleanup_failed'; record['diagnostics'] += '\n' + str(exc)
                else: raise
            record['cleanup'] = owner.cleanup
            try:
                remaining, errors = remaining_owned(str(marker).encode())
            except BaseException as exc:
                if original is not None:
                    original.add_note('Final process inspection failed: ' + str(exc))
                elif not isinstance(exc, Exception):
                    raise
                remaining, errors = [], [type(exc).__name__ + ': ' + str(exc)]
            record['owned_marker_processes_remaining'] = remaining
            record['process_inspection_errors'] = errors
            record['checks']['namespace_descendants_absent'] = not remaining and not errors
            if remaining or errors:
                record['status'] = 'cleanup_verification_failed'
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    record = assess()
    # Administrative evidence only; never replace existing records.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, sort_keys=True, indent=2); stream.write('\n')
    print(json.dumps(record, sort_keys=True))
    # A completed assessment may honestly be blocked. No worker is admitted.
    return 0 if record['status'] in {'blocked', 'mechanism_checks_passed_not_qualified'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
