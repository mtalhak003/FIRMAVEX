"""Read-only, bounded presentations of recorded observations and diagnostic files."""
from itertools import islice
from pathlib import Path
import re

from firmavex.backends.security import read_bytes
from firmavex.product.verification import check_cancel

FILE_LIMIT = 1024 * 1024
TEXT_LIMIT = 8192
SIGNAL_LIMIT = 128
LINE_LIMIT = 20000


def text(value, limit=TEXT_LIMIT):
    if value is None:
        return 'unavailable'
    if type(value) not in (str, int, bool):
        return 'unavailable'
    value = str(value)
    return ''.join(c if c.isprintable() or c in '\n\t' else '\ufffd' for c in value[:limit]) + ('\n[Display truncated]' if len(value) > limit else '')


def classification(status):
    if type(status) is not str:
        return 'unavailable'
    return {'triggered': 'firmware/test failure', 'configured_failure_observed': 'firmware/test failure',
            'reproduced_in_emulator': 'firmware/test failure', 'cancelled': 'cancellation',
            'infrastructure_failure': 'tool or infrastructure failure',
            'invalid_input': 'input rejected', 'invalid_output': 'invalid output',
            'reproduction_inconsistent': 'inconsistent reproduction',
            'passed': 'no failure recorded', 'not_discovered': 'no failure within recorded search',
            'no_failure_within_budget': 'no failure within recorded search',
            'domain_exhausted': 'no failure within recorded search'}.get(status, 'unavailable')


def replay_explanation(backend):
    if backend == 'cortex-m3-mps2':
        return ('ARM replay repeats saved inputs in QEMU/GDB under the supported Cortex-M3 MPS2 configuration. '
                'Only recorded matching observations and completed repetitions support reproduction; firmware, configuration, '
                'runtime and host assumptions must be reviewed. This does not establish hardware equivalence or complete reproducibility.')
    if backend == 'riscv32-virt':
        return ('RISC-V replay reruns the retained RV32 input and values in QEMU/GDB. A new observation is not an ARM-style '
                'repeated reproduction verdict or proof of hardware equivalence or complete reproducibility.')
    if backend == 'verilog-icarus':
        return ('Verilog replay reruns the retained constrained testbench with Icarus. Results depend on simulator and environment; '
                'this is not physical FPGA validation or complete reproducibility.')
    return 'Replay guarantees unavailable for this record.'


def _riscv_failure_detail(record, evidence):
    """Present supported adapter metadata, never infer a cause from log words.

    This is a primary execution-pipeline diagnostic, not proof of guest dispatch,
    an assertion, a build result or archive authenticity. Older or contradictory
    metadata remains unavailable. Cleanup has its existing separate evidence.
    """
    identities = []
    if 'backend' in evidence:
        identities.append(evidence['backend'])
    admission = evidence.get('admission')
    if type(admission) is dict and 'profile' in admission:
        profile = admission['profile']
        identities.append(profile.get('id') if type(profile) is dict else None)
    if record.get('kind') == 'firmavex_product_result':
        identities.append('cortex-m3-mps2')
    if not any(type(value) is str and value == 'riscv32-virt' for value in identities):
        return []
    stages = {'tool_probe': 'Runtime version probe', 'qemu_startup': 'QEMU startup',
              'debugger_observation': 'Debugger observation', 'completion_validation': 'Completion validation',
              'identity_validation': 'Identity validation'}
    causes = {'timeout': 'Timeout', 'tool_exit': 'Tool process exited',
              'invalid_observation': 'Invalid completion observation',
              'identity_changed': 'Retained input or runtime identity changed',
              'infrastructure_error': 'Infrastructure error; specific cause not established',
              'cancelled': 'Cancellation'}
    value = evidence.get('failure_diagnostic')
    # The record has six fields. Check length before iterating arbitrary metadata.
    valid = (type(value) is dict and len(value) == 6
             and set(value) == {'schema_version', 'backend', 'stage', 'category', 'tool', 'return_code'})
    if valid:
        phase, cause, tool, code = (value[key] for key in ('stage', 'category', 'tool', 'return_code'))
        valid = (type(value['schema_version']) is int and value['schema_version'] == 1
                 and value['backend'] == 'riscv32-virt'
                 and all(type(identity) is str and identity == 'riscv32-virt' for identity in identities)
                 and type(phase) is str and 0 < len(phase) <= 32 and phase in stages
                 and type(cause) is str and 0 < len(cause) <= 32 and cause in causes
                 and (tool is None or type(tool) is str and len(tool) <= 4 and tool in {'qemu', 'gdb'}))
    if valid:
        expected_tools = {'tool_probe': {'qemu', 'gdb'}, 'qemu_startup': {'qemu'},
                          'debugger_observation': {'gdb'}, 'completion_validation': {'gdb'},
                          'identity_validation': {None, 'qemu', 'gdb'}}
        valid = (tool in expected_tools[phase]
                 and record.get('status') == ('cancelled' if cause == 'cancelled' else 'infrastructure_failure')
                 and (cause != 'invalid_observation' or phase == 'completion_validation')
                 and (cause != 'identity_changed' or phase == 'identity_validation'))
        if cause == 'tool_exit':
            valid = (valid and phase in {'tool_probe', 'qemu_startup', 'debugger_observation'}
                     and type(code) is int and -(2**31) <= code <= 2**32 - 1
                     and (code != 0 or phase == 'qemu_startup'))
        else:
            valid = valid and code is None
    lines = ['RV32 execution diagnostic',
             'Recorded phase: ' + (stages[phase] if valid else 'unavailable'),
             'Recorded cause: ' + (causes[cause] if valid else 'unavailable'),
             'Recorded tool: ' + (tool if valid and tool is not None else 'unavailable'),
             'Recorded exit code: ' + (str(code) if valid and code is not None else 'unavailable'),
             'Build outcome: not assessed (this run imports an ELF; it does not compile firmware).',
             'Assertion cause: not established by a configured failure flag.',
             'This is retained primary pipeline metadata, not proof of a firmware crash, hang or assertion.']
    return lines


def diagnosis(record):
    if type(record) is not dict:
        record = {}
    evidence = record.get('evidence', {})
    evidence = evidence if type(evidence) is dict else {}
    admission = evidence.get('admission', {})
    admission = admission if type(admission) is dict else {}
    profile = admission.get('profile', {})
    backend = profile.get('id') if type(profile) is dict else None
    legacy = evidence.get('legacy_result', record)
    legacy = legacy if type(legacy) is dict else {}
    status = record.get('status', legacy.get('outcome'))
    if record.get('kind') == 'firmavex_product_result':
        backend = 'cortex-m3-mps2'
    # Presence identifies a retained phase, not a successful completion.
    stage = evidence.get('stage')
    if stage is None and evidence.get('completion_observed') is True:
        stage = 'completion observed'
    if stage is None and backend == 'verilog-icarus':
        stage = 'simulation output retained' if 'returncode' in evidence else 'compiler output retained' if 'compile_stderr' in evidence else None
    lines = ['Failure diagnosis', 'Execution stage: ' + text(stage, 200),
             'Failure category: ' + classification(status), 'Recorded outcome: ' + text(status, 200),
             'Attempt/run identity: ' + text(admission.get('attempt_id', legacy.get('run_id')), 200),
             'Expected behavior: ' + text(evidence.get('expected'), 500),
             'Observed behavior: ' + text(evidence.get('observation'), 500)]
    from .provenance import recorded
    provenance = recorded(admission)
    if type(provenance) is dict:
        for field in ('configuration_revision', 'input_sha256', 'test_set_id', 'test_set_revision', 'entry_id', 'rerun_of', 'host_os', 'host_architecture', 'target_assumptions'):
            lines.append(field.replace('_', ' ').capitalize() + ': ' + text(provenance.get(field), 200))
    observation = evidence.get('observation')
    if type(observation) is dict:
        lines[6] = 'Observed behavior: ' + text('; '.join(text(k, 40) + '=' + text(v, 80) for k, v in islice(observation.items(), 8)), 700)
    if type(legacy.get('error')) is dict:
        lines.append('Retained run diagnostic: ' + '; '.join(text(k, 40) + '=' + text(v, 160) for k, v in islice(legacy['error'].items(), 8)))
    for key in ('error', 'stderr', 'stdout', 'compile_stderr', 'compile_stdout'):
        if type(evidence.get(key)) is str and evidence[key]:
            lines.append('Retained ' + key + ':\n' + text(evidence[key], 1200))
    # Preserve existing cause-first excerpts, including short saved-run previews.
    lines.extend(_riscv_failure_detail(record, evidence))
    lines.append('Next investigation: ' + ('Review retained partial logs and cleanup evidence before an explicit rerun.' if status == 'cancelled' else
                 'Compare retained inputs, runtime identities and logs; inspect missing evidence before drawing a conclusion.'))
    lines.append(replay_explanation(backend))
    return '\n'.join(lines)


def inspect_artifact(path, *, cancel_event=None):
    """Never execute files. Whole-file byte bound plus line/token/display bounds."""
    suffix = Path(path).suffix.lower()
    if suffix not in {'.log', '.txt', '.out', '.err', '.vcd'}:
        return 'Unsupported diagnostic artifact type.'
    try:
        data = read_bytes(path, FILE_LIMIT, cancel_event=cancel_event)
        if suffix != '.vcd':
            return text(data[:TEXT_LIMIT].decode('utf-8', errors='replace')) + ('\n[Display truncated]' if len(data) > TEXT_LIMIT else '')
        content = data.decode('ascii', errors='replace')
        signals, timescale, first, last = [], None, None, None
        lines = content.splitlines()
        if len(lines) > LINE_LIMIT:
            return 'VCD inspection unavailable: line limit exceeded.'
        # Tokenize the bounded header only, allowing multiline VCD directives.
        end_marker = re.search(r'\$enddefinitions\s+\$end', content)
        if end_marker is None:
            return 'Malformed or unsupported VCD header.'
        header = content[:end_marker.start()]
        for match in re.finditer(r'\$timescale\s+([^$]{1,80})\$end', header):
            timescale = ' '.join(match[1].split())
        declarations = 0
        for match in re.finditer(r'\$var\s+([^$]{1,512})\$end', header):
            check_cancel(cancel_event)
            declarations += 1
            parts = match[1].split()
            if len(parts) < 4:
                return 'Malformed VCD signal declaration.'
            if len(signals) == SIGNAL_LIMIT:
                return 'VCD inspection unavailable: signal limit exceeded.'
            signals.append(text(' '.join(parts[3:]), 160))
        if header.count('$var') != declarations:
            return 'Malformed or unsupported VCD signal declaration.'
        for line in content[end_marker.end():].splitlines():
            check_cancel(cancel_event)
            if line.startswith('#'):
                if not re.fullmatch(r'#[0-9]{1,20}', line):
                    return 'Malformed VCD timestamp.'
                value = int(line[1:])
                if last is not None and value < last:
                    return 'Malformed VCD timestamp order.'
                first = value if first is None else first
                last = value
        return text('VCD metadata only; values are not rendered or validated.\nTimescale: ' + text(timescale, 80) +
                    '\nFirst timestamp: ' + text(first) + '\nLast timestamp: ' + text(last) +
                    '\nDuration in timestamp units: ' + text(last - first if first is not None else None) +
                    '\nSignal references (scope not resolved):\n' + '\n'.join(signals))
    except (OSError, ValueError, RuntimeError):
        return 'Diagnostic artifact unavailable: missing, unsafe, changed or exceeds inspection limits.'
