"""Immutable named backend configurations and explicit, non-executing preflight.

Existing execution and saved-run formats remain authoritative. Configuration
folders own copied inputs and a runs subdirectory; no archived run is rewritten.
"""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from firmavex.backends.api import request_from_dict, request_to_dict
from firmavex.backends.security import checked_path, read_bytes, fresh_directory
from .verification import check_cancel

MAX_INPUT = 64 * 1024 * 1024
_ID = re.compile(r'[a-f0-9]{64}\Z')


def _json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('Duplicate configuration field')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Nonfinite configuration value')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def _capture(request, cancel_event=None, expected=None):
    source = checked_path(request.source)
    maximum = 1024 * 1024 if request.profile == 'cortex-m3-mps2' else min(MAX_INPUT, request.limits.artifact_bytes)
    data = read_bytes(source, maximum, cancel_event=cancel_event)
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None and (type(expected) is not str or not _ID.fullmatch(expected) or digest != expected):
        raise ValueError('Selected configuration/input changed; select or save it again explicitly')
    return source, data, digest


def _check(request, data, expected_firmware=None):
    if request.profile == 'cortex-m3-mps2':
        from .config import ProductConfig
        from .firmware import inspect_elf
        config = ProductConfig.from_dict(_json(data), base_dir=request.source.parent)
        identity = inspect_elf(config)
        if expected_firmware is not None and identity['firmware_sha256'] != expected_firmware:
            raise ValueError('Selected ARM firmware changed; import a new build explicitly')
        return ['Cortex-M3 ELF architecture, memory map, configured symbols and debug types checked.']
    if request.profile == 'riscv32-virt':
        from firmavex.backends.inputs import rv32
        rv32(data)
        return ['ELF32 little-endian RISC-V executable, virt RAM bounds and required symbol presence checked.',
                'RV32 instruction compatibility, symbol types, ready/completion stops and readback still require execution-time checks.']
    from firmavex.backends.inputs import verilog
    text = data.decode('ascii')
    verilog(text)
    findings = ['ASCII single-file input and existing system-task/include/waveform restrictions checked.']
    findings.append('Top testbench declaration ' + ('found textually.' if re.search(r'\bmodule\s+testbench\b', text) else 'not found; provide module testbench.'))
    findings.append('Result marker ' + ('found textually.' if 'FIRMAVEX_TEST_RESULT=' in text else 'not found; emit exactly one standalone FIRMAVEX_TEST_RESULT=PASS or FAIL.'))
    findings.append('Textual conventions are not syntax, elaboration, simulation or assertion-correctness verification.')
    return findings


def preflight(record, *, cancel_event=None, configuration=None, expected=None, expected_firmware=None):
    request = request_from_dict(record)
    if configuration is not None:
        _, value, saved = _manifest(configuration)
        if saved != request:
            raise ValueError('Preflight request differs from the selected saved configuration')
        expected = value['input_sha256']
    if expected_firmware is not None and request.profile != 'cortex-m3-mps2':
        raise ValueError('Firmware identity pinning requires an ARM configuration')
    source, data, digest = _capture(request, cancel_event, expected)
    findings = _check(replace(request, source=source), data, expected_firmware)
    check_cancel(cancel_event)
    return {'status': 'static_checks_passed', 'profile': request.profile, 'source': str(source),
            'source_sha256': digest, 'findings': findings, 'execution_performed': False,
            'compatibility': 'not_established_by_static_checks_alone', 'runtime_behavior': 'unverified',
            'limitation': 'Static checks only; runtime behavior, physical hardware and native qualification are not established. Execution validation remains mandatory.'}


def _encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _manifest(directory):
    directory = checked_path(directory, directory=True)
    if not _ID.fullmatch(directory.name):
        raise ValueError('Select an immutable named configuration folder')
    data = read_bytes(directory / 'configuration.json', 16384)
    if hashlib.sha256(data).hexdigest() != directory.name:
        raise ValueError('Saved configuration identity changed')
    value = _json(data)
    if (type(value) is not dict or set(value) != {'kind', 'schema_version', 'name', 'saved_at', 'request', 'input_sha256', 'origin', 'parent'}
            or value['kind'] != 'firmavex_backend_configuration' or type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['name']) is not str or not 1 <= len(value['name']) <= 80 or any(not c.isprintable() for c in value['name'])
            or type(value['saved_at']) is not str or len(value['saved_at']) > 80
            or type(value['origin']) is not str or len(value['origin']) > 4096
            or type(value['input_sha256']) is not str or not _ID.fullmatch(value['input_sha256'])
            or (value['parent'] is not None and (type(value['parent']) is not str or not _ID.fullmatch(value['parent'])))):
        raise ValueError('Unsupported named configuration metadata')
    request = request_from_dict(value['request'])
    if request.profile not in {'riscv32-virt', 'verilog-icarus'} or str(request.source) != 'input':
        raise ValueError('Unsupported saved input/profile')
    return directory, value, replace(request, source=directory / 'input')


def open_configuration(directory, *, cancel_event=None):
    directory, value, request = _manifest(directory)
    _, data, _ = _capture(request, cancel_event, value['input_sha256'])
    findings = _check(request, data)
    check_cancel(cancel_event)
    return {'configuration': str(directory), 'name': value['name'], 'identity': directory.name,
            'parent': value['parent'], 'origin': value['origin'], 'request': request_to_dict(request), 'findings': findings,
            'input_sha256': value['input_sha256'], 'execution_performed': False,
            'note': 'Uses the verified imported snapshot. Original build files are not consulted; import a new revision explicitly.'}


def _write(path, data, cancel_event):
    with path.open('xb') as stream:
        for offset in range(0, len(data), 1024 * 1024):
            check_cancel(cancel_event)
            stream.write(memoryview(data)[offset:offset + 1024 * 1024])
        stream.flush()
        os.fsync(stream.fileno())
    check_cancel(cancel_event)


def save(root, name, record, *, parent=None, cancel_event=None):
    if type(name) is not str or not 1 <= len(name.strip()) <= 80 or any(not c.isprintable() for c in name):
        raise ValueError('Use a printable configuration name of 1–80 characters')
    request = request_from_dict(record)
    if request.profile not in {'riscv32-virt', 'verilog-icarus'}:
        raise ValueError('Use the ARM project editor for ARM configurations')
    if parent is not None:
        _, previous, old_request = _manifest(parent)
        _capture(old_request, cancel_event, previous['input_sha256'])
        if old_request.profile != request.profile:
            raise ValueError('A revision must retain its backend profile')
        parent = Path(parent).name
    source, data, digest = _capture(request, cancel_event)
    findings = _check(request, data)
    value = {'kind': 'firmavex_backend_configuration', 'schema_version': 1, 'name': name.strip(),
             'saved_at': datetime.now(timezone.utc).isoformat(),
             'request': request_to_dict(replace(request, source=Path('input'))),
             'input_sha256': digest, 'origin': str(source), 'parent': parent}
    encoded = _encoded(value)
    if len(encoded) > 16384:
        raise ValueError('Configuration metadata exceeds limit')
    check_cancel(cancel_event)
    root = checked_path(root, directory=True, exists=False)
    root.mkdir(parents=True, exist_ok=True)
    root = checked_path(root, directory=True)
    check_cancel(cancel_event)
    directory = fresh_directory(root / hashlib.sha256(encoded).hexdigest())
    try:
        _write(directory / 'input', data, cancel_event)
        _write(directory / 'configuration.json', encoded, cancel_event)
    except BaseException:
        # Only files created by this operation; never recursively remove runs.
        (directory / 'configuration.json').unlink(missing_ok=True)
        (directory / 'input').unlink(missing_ok=True)
        directory.rmdir()
        raise
    return {'configuration': str(directory), 'name': name.strip(), 'identity': directory.name,
            'parent': parent, 'origin': str(source), 'request': request_to_dict(replace(request, source=directory / 'input')),
            'input_sha256': digest, 'findings': findings, 'execution_performed': False,
            'note': 'Imported snapshot selected. Previous configurations and evidence remain unchanged.'}


def listing(root, *, cancel_event=None):
    root = checked_path(root, directory=True, exists=False)
    entries = []
    if root.exists():
        for index, path in enumerate(root.iterdir()):
            check_cancel(cancel_event)
            if index >= 200:
                break
            try:
                directory, value, request = _manifest(path)
                entries.append({'configuration': str(directory), 'name': value['name'], 'profile': request.profile,
                                'saved_at': value['saved_at'], 'identity': directory.name})
            except (OSError, ValueError, TypeError, KeyError, RecursionError):
                continue
    return {'entries': entries, 'limit': 200, 'execution_performed': False}


def execute_saved(directory, output_dir, *, trust, cancel_event=None, event_callback=None):
    directory, value, request = _manifest(directory)
    output = checked_path(output_dir, directory=True, exists=False)
    if output.parent != directory / 'runs':
        raise ValueError('Named configuration runs must use its own runs folder')
    _, data, _ = _capture(request, cancel_event, value['input_sha256'])
    return execute_captured(request, output, data, trust=trust, cancel_event=cancel_event, event_callback=event_callback)


def execute_captured(request, output, data, *, trust, cancel_event=None, event_callback=None, expected_firmware=None):
    from .backend_services import execute
    check_cancel(cancel_event)
    with tempfile.TemporaryDirectory(prefix='firmavex-selected-input-') as temporary:
        source = Path(temporary) / 'input'
        if request.profile == 'cortex-m3-mps2':
            from .config import ProductConfig
            config = ProductConfig.from_dict(_json(data), base_dir=request.source.parent)
            image = read_bytes(checked_path(config.firmware), MAX_INPUT, cancel_event=cancel_event)
            if expected_firmware is not None and (type(expected_firmware) is not str or
                    not _ID.fullmatch(expected_firmware) or hashlib.sha256(image).hexdigest() != expected_firmware):
                raise ValueError('Selected ARM firmware changed; import a new build explicitly')
            firmware = Path(temporary) / 'firmware.elf'
            firmware.write_bytes(image)
            data = _encoded(replace(config, firmware=firmware).to_dict())
        source.write_bytes(data)
        return execute(request_to_dict(replace(request, source=source)), str(output), trust=trust,
                       cancel_event=cancel_event, event_callback=event_callback)


def execute_selected(record, output_dir, expected, *, trust, cancel_event=None, event_callback=None, expected_firmware=None):
    request = request_from_dict(record)
    if expected_firmware is not None and request.profile != 'cortex-m3-mps2':
        raise ValueError('Firmware identity pinning requires an ARM configuration')
    source, data, _ = _capture(request, cancel_event, expected)
    return execute_captured(replace(request, source=source), output_dir, data, trust=trust,
                            cancel_event=cancel_event, event_callback=event_callback, expected_firmware=expected_firmware)


def operation(payload, *, cancel_event=None):
    action = payload.get('action')
    fields = {'list': {'action', 'root'}, 'open': {'action', 'configuration'},
              'save': {'action', 'root', 'name', 'request'},
              'revise': {'action', 'root', 'name', 'request', 'configuration'}}
    if action not in fields or set(payload) != fields[action]:
        raise ValueError('Invalid named configuration operation')
    if action == 'list':
        return listing(payload['root'], cancel_event=cancel_event)
    if action == 'open':
        return open_configuration(payload['configuration'], cancel_event=cancel_event)
    return save(payload['root'], payload['name'], payload['request'],
                parent=payload.get('configuration'), cancel_event=cancel_event)


def arm_context(project, config):
    """Explicitly save and freeze the editor selection for workspace navigation."""
    record = project.save_config(config)
    source = project.command_config(record)
    data = read_bytes(source, 1024 * 1024)
    return {'project': str(project.root), 'source': str(source), 'sha256': hashlib.sha256(data).hexdigest(),
            'firmware_sha256': project._identity()['firmware']['sha256']}


def arm_selection(source, context=None):
    from .config import ProductConfig
    from .firmware import inspect_elf
    from firmavex.desktop.projects import DesktopProject
    source = checked_path(source)
    data = read_bytes(source, 1024 * 1024)
    matched = context is not None and str(source) == context['source']
    if matched and hashlib.sha256(data).hexdigest() != context['sha256']:
        raise ValueError('Selected ARM configuration changed; navigation rejected')
    config = ProductConfig.from_dict(_json(data), base_dir=source.parent)
    inspect_elf(config)
    project = None
    if matched:
        project = DesktopProject.open(context['project'])
        if config.firmware != project.firmware_path.resolve():
            raise ValueError('Selected ARM configuration belongs to a different image')
    elif source.name == 'project.json' and (source.parent / 'desktop-project.json').exists():
        project = DesktopProject.open(source.parent)
        if project.load_config() != config:
            raise ValueError('Selected project changed during navigation')
    return project, config
