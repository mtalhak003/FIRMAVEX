"""CI-only ARM source probe. Never installs, patches or qualifies a runtime."""
import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import threading

from firmavex.backends.security import checked_path, read_bytes
from firmavex.product.errors import ProductError
from firmavex.product.runtime_pack import _atomic_json
from firmavex.product.tools import discover, file_identity

CANDIDATE = {
    'qemu': ('QEMU emulator version 11.1.3', 'f7e69cf3c284bad6a3b1c4159d2a88001f285c28f890dd2f8e56186682840cc7'),
    'gdb': ('GNU gdb (GDB) 18.1', 'f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236'),
}
PACKAGES = {'mingw-w64-ucrt-x86_64-qemu': '11.1.3-1',
            'mingw-w64-ucrt-x86_64-gdb-multiarch': '18.1-3'}
# Administrative inventory limits, not changes to execution/resource policies.
MAX_FILES, MAX_BYTES = 100000, 8 * 1024**3
MAX_RECORD = 32 * 1024**2
MAX_OUTPUT_BYTES = 128 * 1024**2
WORKFLOW = 'mtalhak003/FIRMAVEX/.github/workflows/windows-runtime-candidate.yml@refs/heads/product/desktop-batch11'


def context(env, system, machine, head):
    if (system != 'win32' or machine.lower() not in {'amd64', 'x86_64'}
            or env.get('GITHUB_ACTIONS') != 'true'
            or env.get('GITHUB_REPOSITORY') != 'mtalhak003/FIRMAVEX'
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_WORKFLOW_REF') != WORKFLOW
            or not re.fullmatch(r'[0-9a-f]{40}', head)
            or env.get('GITHUB_SHA') != head
            or env.get('FIRMAVEX_CANDIDATE_REVISION') != head
            or not re.fullmatch(r'[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', ''))):
        raise ValueError('Explicit native Windows candidate workflow context required')
    return {'source_revision': head, 'run_id': env['GITHUB_RUN_ID'],
            'host': {'os': 'Windows', 'architecture': 'x86_64'}}


def package_inventory(data):
    if len(data) > 1024**2:
        raise ValueError('Package inventory exceeds bound')
    result = {}
    for line in data.splitlines():
        fields = line.split()
        if (len(fields) != 2 or not re.fullmatch(r'[a-z0-9][a-z0-9+_.-]{0,159}', fields[0])
                or not re.fullmatch(r'[0-9][A-Za-z0-9.+_:~-]{0,127}', fields[1])
                or fields[0] in result or len(result) >= 4096):
            raise ValueError('Invalid or duplicate package inventory entry')
        result[fields[0]] = fields[1]
    if any(result.get(name) != version for name, version in PACKAGES.items()):
        raise ValueError('Candidate package versions changed; review required')
    return result


def signature_policy(data):
    tokens = data.split()
    allowed = {'PackageRequired', 'PackageTrustedOnly', 'DatabaseRequired',
               'DatabaseOptional', 'DatabaseTrustedOnly'}
    if (not {'PackageRequired', 'PackageTrustedOnly'} <= set(tokens)
            or not set(tokens) <= allowed):
        raise ValueError('Trusted publisher package signatures must remain required')
    return sorted(set(tokens))


def inventory(root):
    """Hash the complete UCRT64 prefix, not just selected EXEs or guessed DLLs."""
    root = checked_path(root, directory=True)
    pending, rows, total, entries = [root], {}, 0, 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as stream:
            for entry in stream:
                entries += 1
                if entries > MAX_FILES:
                    raise ValueError('Vendor inventory entry limit exceeded')
                is_directory = entry.is_dir(follow_symlinks=False)
                path = checked_path(entry.path, directory=is_directory)
                if is_directory:
                    pending.append(path)
                    continue
                if path.stat().st_size > 512 * 1024**2:
                    raise ValueError('Vendor file exceeds per-file inventory bound')
                identity = file_identity(path)
                total += identity['size_bytes']
                if total > MAX_BYTES:
                    raise ValueError('Vendor inventory byte limit exceeded')
                rows[path.relative_to(root).as_posix()] = {
                    key: identity[key] for key in ('sha256', 'size_bytes')}
    if not any(name.startswith('share/licenses/') for name in rows):
        raise ValueError('Vendor license inventory missing')
    return rows


def _save(path, record, primary=None):
    try:
        # Match the existing atomic writer, including its platform newline.
        size = len(json.dumps(record, sort_keys=True, allow_nan=False).encode('utf-8')) + len(os.linesep)
        if size > MAX_RECORD:
            raise ValueError('Candidate record exceeds byte bound')
        checked_path(path, exists=False)
        with os.scandir(path.parent) as entries:
            used = sum(entry.stat(follow_symlinks=False).st_size for entry in entries
                       if entry.is_file(follow_symlinks=False) and entry.name != path.name)
        if used + size > MAX_OUTPUT_BYTES:
            raise ValueError('Candidate metadata/log retention limit exceeded')
        _atomic_json(path, record)
        return True
    except BaseException as error:
        if primary is None or (isinstance(primary, Exception) and not isinstance(error, Exception)):
            raise
        primary.add_note('Candidate evidence persistence failed')
        return False


def candidate_tools(root):
    from types import SimpleNamespace
    root = checked_path(root, directory=True)
    tools = discover(SimpleNamespace(qemu=str(root / 'bin/qemu-system-arm.exe'),
                                    gdb=str(root / 'bin/gdb-multiarch.exe')), _managed=False)
    return tools


def verify_tools(tools, root):
    for name, (version, digest) in CANDIDATE.items():
        path = checked_path(getattr(tools, name))
        expected_name = 'qemu-system-arm.exe' if name == 'qemu' else 'gdb-multiarch.exe'
        if path != root / 'bin' / expected_name:
            raise ValueError('Candidate tool selected outside the declared prefix')
        claimed, actual = tools.identities.get(name, {}), file_identity(path)
        if (claimed.get('version') != version or claimed.get('sha256') != digest
                or actual['sha256'] != digest):
            raise ValueError('Candidate executable identity changed; review required')


def production_rejection(tools):
    from firmavex.product.platform_support import require_native_support
    try:
        require_native_support(tools)
    except ProductError as error:
        if error.category != 'unsupported_platform':
            raise
        return error.details
    raise ValueError('Candidate unexpectedly admitted by production policy')


def _environment(root, output):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
    result = context(os.environ, sys.platform, platform.machine(), head)
    temporary = checked_path(os.environ['RUNNER_TEMP'], directory=True)
    root = checked_path(root, directory=True)
    output = checked_path(output, exists=False)
    if temporary not in root.parents or temporary not in output.parents or root in output.parents:
        raise ValueError('Candidate vendor/output storage must be separate private runner paths')
    return result, root, output


def preflight(root, packages, policy, output):
    env, root, output = _environment(root, output)
    if output.exists():
        raise FileExistsError('Candidate output must be new')
    package_data = read_bytes(packages, 1024**2).decode('ascii')
    signature_data = read_bytes(policy, 4096).decode('ascii')
    report = {**env, 'schema_version': 1, 'kind': 'firmavex_windows_runtime_candidate',
              'candidate_only': True, 'production_qualified': False,
              'status': 'candidate_preflight_failed', 'cases': [],
              'candidate_expected': {name: {'version': version, 'sha256': digest}
                                     for name, (version, digest) in CANDIDATE.items()},
              'pending': ['GUI journeys', 'frozen application execution', 'installed application execution',
                          'upgrade/rollback/uninstall', 'standard-user/offline/low-disk acceptance',
                          'independent profile review'], 'atomic_snapshot': False}
    output.mkdir(parents=True, exist_ok=False)
    try:
        report['signature_policy'] = signature_policy(signature_data)
        tools = candidate_tools(root)
        from firmavex.product.platform_support import _qualification_details
        observed = _qualification_details(tools.identities, platform.machine())['tools']
        report['tools'] = {name: {**observed[name]['observed'], 'size_bytes': tools.identities[name]['size_bytes']}
                           for name in CANDIDATE}
        verify_tools(tools, root)
        report['packages'] = package_inventory(package_data)
        report['production_rejection'] = production_rejection(tools)
        _save(output / 'vendor-files.json', inventory(root))
        report['vendor_inventory_sha256'] = file_identity(output / 'vendor-files.json')['sha256']
        report['status'] = 'candidate_preflight_only'
    except BaseException as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        _save(output / 'candidate-report.json', report, sys.exception())
    return report


def source_probe(root, output):
    from firmavex.product.bundled_example import prepare_example
    from firmavex.product.config import load_config
    from firmavex.product.runtime import FirmwareExecutor
    from src.firmavex.evaluation.evaluator import EvaluationSession
    from src.firmavex.evaluation.api import TrialInput
    from src.firmavex.strategies.enumerative import EnumerativeStrategy
    from src.firmavex.strategies.runner import run_strategy

    env, root, output = _environment(root, output)
    report = json.loads(read_bytes(output / 'candidate-report.json', MAX_RECORD))
    if (report.get('source_revision') != env['source_revision'] or report.get('run_id') != env['run_id']
            or report.get('status') != 'candidate_preflight_only' or report.get('production_qualified') is not False):
        raise ValueError('Candidate preflight missing, stale or already consumed')
    manifest = output / 'vendor-files.json'
    if file_identity(manifest)['sha256'] != report['vendor_inventory_sha256']:
        raise ValueError('Candidate vendor inventory changed')
    expected_files = json.loads(read_bytes(manifest, MAX_RECORD))
    if inventory(root) != expected_files:
        raise ValueError('Vendor prefix changed after preflight')
    tools = candidate_tools(root)
    verify_tools(tools, root)
    production_rejection(tools)
    built = prepare_example(output / 'example')
    config = load_config(built['config_file'])
    receipts = []
    persistence_failures = []

    def session(name, cfg, budget, cancel=None, callback=None):
        executor = FirmwareExecutor(cfg, tools, cancel, callback)
        def execute(values):
            try:
                return executor.execute(values).observation
            finally:
                primary = sys.exception()
                evidence = executor.last_evidence
                if evidence is not None:
                    cleanup_bad = not evidence['cleanup_verified'] or not all(p['reaped'] for p in evidence['cleanup']['processes'])
                    if cleanup_bad and primary is not None:
                        primary.add_note('Candidate execution cleanup was not verified')
                    receipts.append(evidence)
                    if not _save(output / f'candidate-receipt-{len(receipts):02}.json', {
                        'candidate_only': True, 'production_qualified': False, 'case': name, 'runtime': evidence}, primary):
                        persistence_failures.append(name)
                    if cleanup_bad and primary is None:
                        raise RuntimeError('Candidate execution cleanup was not verified')
        return EvaluationSession('candidate-product-example', cfg.input_space, budget, name, execute)

    def completed(name, run):
        evidence = receipts[-1]
        if (persistence_failures or not evidence['cleanup_verified'] or (not run.result().aborted and
                (evidence.get('measurement_mode') != 'real_firmware'
                 or not all(evidence.get(key) for key in ('guest_dispatched', 'input_injected', 'completion_reached'))))):
            raise RuntimeError('Candidate execution evidence is incomplete')
        report['cases'].append({'name': name, 'accounting': asdict(run.result())})

    report['status'] = 'candidate_source_probe_running'
    try:
        for values, expected in (((2, 1), 1), ((2, 0), 0)):
            for symbol, value in (('product_failure', expected), ('initialized_data', 0x13579bdf)):
                cfg = replace(config, failure_symbol=symbol, failure_value=1 if symbol == 'product_failure' else value)
                run = session(f'{symbol}-{values[0]}-{values[1]}', cfg, 1)
                feedback = run.execute(TrialInput(values))
                if feedback.status != ('triggered' if value == cfg.failure_value else 'safe') or receipts[-1]['observed_value'] != value:
                    raise RuntimeError('Candidate input/initialized-data/failure observation mismatch')
                completed(f'{symbol}-{values}', run)
        run = session('enumerative-search', config, 16)
        result = run_strategy(EnumerativeStrategy(), run.strategy_api())
        if (result.evaluation.attempted_executions != 10 or not result.evaluation.failure_found
                or result.evaluation.infrastructure_failures or receipts[-1]['inputs'] != [2, 1]):
            raise RuntimeError('Candidate search outcome/accounting mismatch')
        completed('enumerative-search', run)
        run = session('reproduction', config, 3)
        for _ in range(3):
            if run.execute(TrialInput((2, 1))).status != 'triggered':
                raise RuntimeError('Candidate reproduction mismatch')
        completed('reproduction', run)
        for cancelled in (False, True):
            event = threading.Event()
            def progress(row):
                if cancelled and row.get('stage') == 'injected': event.set()
            cfg = replace(config, completion_breakpoint='Default_Handler', timeout_seconds=5.0)
            run = session('cancel' if cancelled else 'timeout', cfg, 2, event, progress)
            if cancelled:
                try: run.execute(TrialInput((2, 1)))
                except KeyboardInterrupt: pass
                else: raise RuntimeError('Candidate cancellation did not propagate')
                if not event.is_set(): raise RuntimeError('Cancellation preceded actual injection')
            elif run.execute(TrialInput((2, 1))).status != 'infrastructure_failure':
                raise RuntimeError('Candidate timeout was not an infrastructure failure')
            result = run.result()
            if not (result.aborted and result.attempted_executions == result.infrastructure_failures == 1):
                raise RuntimeError('Candidate interrupted-attempt accounting mismatch')
            if (not receipts[-1]['input_injected'] or not receipts[-1]['guest_dispatched']
                    or receipts[-1]['error_category'] != ('cancelled' if cancelled else 'timeout')):
                raise RuntimeError('Candidate cancellation/timeout did not follow actual injection')
            before = len(receipts)
            if run.execute(TrialInput((2, 1))).status != 'session_aborted' or len(receipts) != before:
                raise RuntimeError('Aborted candidate session dispatched another execution')
            completed('cancel' if cancelled else 'timeout', run)
        if inventory(root) != expected_files:
            raise ValueError('Vendor prefix changed during candidate tests')
        if (len(receipts) != 19 or len({row['attempt_id'] for row in receipts}) != 19
                or not all(row['cleanup_verified'] for row in receipts)):
            raise RuntimeError('Candidate receipt count, identity or cleanup mismatch')
        verify_tools(candidate_tools(root), root)
        production_rejection(candidate_tools(root))
        report['status'] = 'candidate_source_probe_passed'
    except BaseException as error:
        report.update(status='candidate_source_probe_failed', error_type=type(error).__name__)
        raise
    finally:
        _save(output / 'candidate-report.json', report, sys.exception())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor-root', type=Path, required=True)
    parser.add_argument('--package-inventory', type=Path, required=True)
    parser.add_argument('--signature-policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    preflight(args.vendor_root, args.package_inventory, args.signature_policy, args.output)
    print('Candidate preflight captured; production qualification remains FALSE.')


if __name__ == '__main__':
    main()
