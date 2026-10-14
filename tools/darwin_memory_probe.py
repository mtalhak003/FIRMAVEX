"""Bounded administrative native-memory investigation, never firmware qualification.

Compiles repository-owned C in a fresh output directory on actual Darwin. No
production policy is changed, no workload supplied by the user is dispatched,
and no successful API call is treated as proof of enforcement or isolation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys

CAPS = (134217728, 2147483648)


def _run(argv, *, env, timeout=30):
    process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    primary = None
    try:
        out, err = process.communicate(timeout=timeout)
        if len(out) + len(err) > 1024 * 1024:
            raise ValueError('Probe output exceeds limit')
        return process.returncode, out.decode('utf-8'), err.decode('utf-8', errors='replace')
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note('Probe cleanup failed: ' + str(cleanup))
        finally:
            process.stdout.close()
            process.stderr.close()


def validate_observation(record, mode, cap, code):
    if type(record) is not dict or record.get('mode') != mode or type(record.get('cap_bytes')) is not int or record['cap_bytes'] != cap:
        raise ValueError('Malformed native probe record')
    for field in ('uid', 'virtual_bytes', 'resident_bytes'):
        if type(record.get(field)) is not int or record[field] < 0:
            raise ValueError('Malformed native memory diagnostic')
    if mode in {'as', 'data'}:
        if type(record.get('admitted')) is not bool or type(record.get('effective_cap_bytes')) is not int or not 0 <= record['effective_cap_bytes'] <= cap:
            raise ValueError('Invalid memory admission observation')
        if code != (0 if record['admitted'] else 125):
            raise ValueError('Native admission/exec status is contradictory')
    elif code != 0 or record.get('enforcement_verified') is not False:
        raise ValueError('An API probe is not enforcement qualification')
    return record


def investigate(output):
    if sys.platform != 'darwin':
        raise RuntimeError('Requires actual Darwin; cross-platform mocks cannot qualify macOS')
    output = Path(output).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which('clang')
    if compiler is None:
        raise RuntimeError('Apple clang/SDK unavailable')
    source = Path(__file__).parent / 'native/darwin_memory_probe.c'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    binary = output / 'darwin-memory-probe'
    env = dict(os.environ)
    code, stdout, stderr = _run([compiler, '--version'], env=env)
    if code:
        raise RuntimeError('Compiler identity probe failed: ' + stderr)
    compiler_version = stdout
    flags = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror']
    code, stdout, stderr = _run([compiler, *flags, str(source), '-o', str(binary)], env=env)
    (output / 'build.log').write_text(stdout + stderr, encoding='utf-8')
    if code:
        raise RuntimeError('Native probe compilation failed: ' + stderr)
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError('Probe source changed during compilation')
    records = []
    for allocator in ('default', 'nano_disabled'):
        selected_env = dict(env)
        if allocator == 'nano_disabled':
            selected_env['MallocNanoZone'] = '0'
        else:
            selected_env.pop('MallocNanoZone', None)
        for mode in ('as', 'data', 'footprint', 'memorystatus'):
            for cap in CAPS:
                code, stdout, stderr = _run([str(binary), mode, str(cap)], env=selected_env)
                observation = validate_observation(json.loads(stdout), mode, cap, code)
                record = {'allocator': allocator, 'observation': observation,
                          'exit_status': code, 'stderr': stderr}
                records.append(record)
                print('::notice title=Darwin native memory investigation::' + json.dumps(record, sort_keys=True), flush=True)
    result = {'schema_version': 1, 'kind': 'native_os_memory_investigation',
              'firmware_executions': 0, 'sandbox_qualification': False,
              'production_limits_changed': False,
              'system': platform.system(), 'architecture': platform.machine(),
              'kernel': platform.release(), 'macos': platform.mac_ver()[0],
              'compiler_version': compiler_version, 'compiler': compiler,
              'compile_flags': flags, 'source_sha256': source_hash,
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'records': records}
    (output / 'investigation.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        investigate(args.output)
    except Exception as exc:
        print('::error title=Darwin investigation failed::' + str(exc).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
