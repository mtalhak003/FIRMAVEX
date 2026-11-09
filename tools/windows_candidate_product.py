"""Candidate-only product admission checks. Never overrides production policy.

Passing means an unqualified runtime was rejected through actual product paths;
it does not qualify positive firmware execution, GUI usability or installation.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading

from firmavex.backends.api import Limits
from firmavex.backends.process import Processes
from firmavex.backends.security import checked_path, read_json
from firmavex.product.bundled_example import prepare_example
from firmavex.product.config import load_config
from firmavex.product.errors import ProductError
from firmavex.product.platform_support import WINDOWS_EXECUTABLES, WINDOWS_PROFILE_ID, WINDOWS_PROFILE_VERSION
from firmavex.product.supervisor import Supervisor
from firmavex.product.tools import file_identity
from tools import windows_runtime_candidate as candidate


def prepared_context(vendor_root, evidence_dir):
    context, root, evidence = candidate._environment(Path(vendor_root), Path(evidence_dir))
    report = read_json(evidence / 'candidate-report.json', candidate.MAX_RECORD)
    if (report.get('status') != 'candidate_source_probe_passed'
            or report.get('candidate_only') is not True or report.get('production_qualified') is not False
            or report.get('source_revision') != context['source_revision']
            or report.get('run_id') != context['run_id']):
        raise ValueError('Matching successful candidate source probe required')
    manifest = evidence / 'vendor-files.json'
    if file_identity(manifest)['sha256'] != report.get('vendor_inventory_sha256'):
        raise ValueError('Candidate inventory identity changed')
    if candidate.inventory(root) != read_json(manifest, candidate.MAX_RECORD):
        raise ValueError('Candidate prefix changed')
    tools = candidate.candidate_tools(root)
    candidate.verify_tools(tools, root)
    candidate.production_rejection(tools)
    return context, root, evidence, tools


def prepare_project(directory, tools):
    built = prepare_example(directory / 'example')
    config = replace(load_config(built['config_file']), qemu=tools.qemu, gdb=tools.gdb)
    path = directory / 'candidate-project.json'
    candidate._save(path, config.to_dict())
    return path


def rejection_details(error):
    if type(error) is not dict or error.get('category') != 'unsupported_platform':
        raise ValueError('Expected production runtime rejection')
    details = error.get('details')
    if (type(details) is not dict or details.get('required_profile') != WINDOWS_PROFILE_ID
            or type(details.get('profile_version')) is not int or details['profile_version'] != WINDOWS_PROFILE_VERSION
            or 'supervisor_cleanup_error' in details):
        raise ValueError('Missing admission identity or failed product cleanup')
    qualification = details.get('qualification')
    if (type(qualification) is not dict or qualification.get('host_architecture') != 'x86_64'
            or type(qualification.get('schema_version')) is not int or qualification['schema_version'] != 1
            or qualification.get('required_profile') != WINDOWS_PROFILE_ID
            or type(qualification.get('profile_version')) is not int
            or qualification['profile_version'] != WINDOWS_PROFILE_VERSION):
        raise ValueError('Native x64 qualification diagnostics required')
    tool_records = qualification.get('tools')
    if type(tool_records) is not dict:
        raise ValueError('Missing product runtime identities')
    for name, (version, digest) in candidate.CANDIDATE.items():
        item = tool_records.get(name)
        expected = dict(zip(('version', 'sha256'), WINDOWS_EXECUTABLES[name]))
        observed = {'version': version, 'sha256': digest}
        if (type(item) is not dict or item.get('observed') != observed or item.get('expected') != expected
                or item.get('matches') != {key: observed[key] == expected[key] for key in expected}
                or not all(type(value) is bool for value in item['matches'].values())):
            raise ValueError('Product observed a different candidate runtime')
    return {'category': error['category'], 'required_profile': WINDOWS_PROFILE_ID,
            'qualification': qualification}


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate CLI result field')
        result[key] = value
    return result


def run_cli(command, config, destination, working):
    """Use existing process ownership/limits for the CLI and its worker tree."""
    owner = Processes(threading.Event(), Limits(timeout_seconds=60))
    try:
        code, output, _ = owner.run([*command, 'run', str(config), '--output-dir', str(destination)], working)
    finally:
        primary = sys.exception()
        try:
            owner.close()
        except BaseException as cleanup:
            if primary is None or (isinstance(primary, Exception) and not isinstance(cleanup, Exception)):
                raise
            primary.add_note('Candidate CLI cleanup failed: ' + type(cleanup).__name__)
    if (type(code) is not int or code != 1 or not owner.cleanup
            or not all(row.get('reaped') is True and type(row.get('pid')) is int and row['pid'] > 0
                       and type(row.get('returncode')) is int and row['returncode'] == 1 for row in owner.cleanup)):
        raise ValueError('Unexpected CLI exit status or incomplete owned process cleanup')
    record = json.loads(output, object_pairs_hook=_json_object,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite CLI result')))
    if type(record) is not dict or record.get('success') is not False:
        raise ValueError('CLI did not preserve failed admission')
    error = rejection_details(record.get('error'))
    if destination.exists():
        raise ValueError('Rejected CLI execution created a run archive')
    return {'path': 'CLI', 'rejection': error, 'owned_process_cleanup': owner.cleanup}


def run_product_probe(vendor_root, evidence_dir, *, executable=None, distribution='source'):
    if distribution not in {'source', 'frozen', 'installed'}:
        raise ValueError('Unsupported candidate product path')
    if (distribution == 'source') != (executable is None):
        raise ValueError('Non-source paths require an explicit executable')
    context, root, evidence, tools = prepared_context(vendor_root, evidence_dir)
    selected = checked_path(executable) if executable is not None else None
    executable_identity = file_identity(selected if selected else sys.executable)
    directory = checked_path(evidence / ('product-' + distribution), directory=True, exists=False)
    directory.mkdir(exist_ok=False)
    report = {**context, 'schema_version': 1, 'candidate_only': True, 'production_qualified': False,
              'kind': 'firmavex_candidate_product_admission', 'status': 'failed',
              'scope': 'unqualified-runtime rejection only; no positive product execution',
              'distribution': distribution, 'installation_verified': False,
              'executable_origin': ('running_interpreter' if selected is None
                                    else 'caller_supplied_not_independently_verified'),
              'executable': {key: executable_identity[key] for key in ('sha256', 'size_bytes')},
              'firmware_execution': 'unknown_not_verified', 'charged_attempts': None, 'cases': []}
    try:
        config = prepare_project(directory, tools)
        worker_argv = [str(selected), '--firmavex-worker'] if selected else None
        events = []
        def event(row):
            events.append(row['kind'])
            if len(events) > 256: raise ValueError('Product event count exceeded bound')
            if row['kind'] == 'progress': raise ValueError('Rejected run unexpectedly reported runtime progress')
        destination = directory / 'worker-run'
        try:
            Supervisor(worker_argv).execute('run', {'config': str(config), 'output_dir': str(destination)},
                                            timeout=60, event_callback=event)
        except ProductError as error:
            details = rejection_details(error.to_dict())
        else:
            raise ValueError('Unqualified runtime was admitted by product worker')
        if destination.exists() or events != ['accepted', 'error']:
            raise ValueError('Rejected worker produced an archive or unexpected events')
        report['cases'].append({'path': 'supervised_worker', 'rejection': details, 'event_kinds': events})
        cli = [str(selected), '--firmavex-cli'] if selected else [sys.executable, '-m', 'firmavex.product.cli']
        report['cases'].append(run_cli(cli, config, directory / 'cli-run', directory))
        if file_identity(selected if selected else sys.executable)['sha256'] != executable_identity['sha256']:
            raise ValueError('Product executable changed during probe')
        prepared_context(root, evidence)
        report['firmware_execution'], report['charged_attempts'] = 'not_admitted', 0
        report['status'] = 'candidate_admission_rejection_passed'
    except BaseException as error:
        report['error_type'] = type(error).__name__
        raise
    finally:
        candidate._save(directory / 'product-admission.json', report, sys.exception())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor-root', required=True, type=Path)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--executable', type=Path)
    parser.add_argument('--distribution', choices=['source', 'frozen', 'installed'], default='source')
    args = parser.parse_args(argv)
    run_product_probe(args.vendor_root, args.evidence_dir, executable=args.executable, distribution=args.distribution)
    print('Candidate product admission checks passed; positive execution remains NOT PROVEN.')


if __name__ == '__main__':
    main()
