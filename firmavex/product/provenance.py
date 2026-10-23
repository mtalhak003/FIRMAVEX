"""Bounded declarations for new executions; never reconstruct historical claims."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import platform

_context = ContextVar('firmavex_execution_provenance', default={})


@contextmanager
def execution_context(**fields):
    allowed = {'configuration_revision', 'configuration_created_at', 'input_sha256',
               'test_set_id', 'test_set_revision', 'entry_id', 'regression_run_id', 'rerun_of'}
    if not fields.keys() <= allowed or len(json.dumps(fields)) > 4096:
        raise ValueError('Invalid execution provenance')
    if any(type(v) is not str or not v or len(v) > 4096 or not v.isprintable() for v in fields.values()):
        raise ValueError('Invalid execution provenance value')
    token = _context.set(dict(fields))
    try:
        yield
    finally:
        _context.reset(token)


def declaration(profile):
    targets = {'riscv32-virt': 'QEMU virt / rv32; ready, input readback and completion contract',
               'verilog-icarus': 'Icarus single-file testbench; fixed testbench top and result marker',
               'cortex-m3-mps2': 'QEMU MPS2 AN385 / Cortex-M3; configured symbol observation'}
    return {'schema_version': 1, 'backend': profile, 'target_assumptions': targets[profile],
            'host_os': platform.system(), 'host_architecture': platform.machine(),
            'python_version': platform.python_version(), **_context.get(),
            'scope': 'Recorded software environment assumptions, not hardware equivalence or execution authenticity.',
            'runtime_identity_reference': 'evidence.tools; ARM retained archive metadata.tools',
            'input_identity_reference': 'evidence.firmware/source; ARM legacy_result.firmware_sha256'}


def recorded(admission):
    """Unknown/malformed optional provenance is unavailable, never reconstructed."""
    value = admission.get('execution_provenance')
    required = {'schema_version', 'backend', 'target_assumptions', 'host_os', 'host_architecture',
                'python_version', 'scope', 'runtime_identity_reference', 'input_identity_reference'}
    optional = {'configuration_revision', 'configuration_created_at', 'input_sha256', 'test_set_id',
                'test_set_revision', 'entry_id', 'regression_run_id', 'rerun_of'}
    profile = admission.get('profile')
    if (type(value) is not dict or not required <= value.keys() or not value.keys() <= required | optional
            or type(value.get('schema_version')) is not int or value['schema_version'] != 1
            or type(profile) is not dict or value.get('backend') != profile.get('id')):
        return None
    if any(type(v) is not str or not v or len(v) > 4096 or not v.isprintable()
           for k, v in value.items() if k != 'schema_version'):
        return None
    return value
