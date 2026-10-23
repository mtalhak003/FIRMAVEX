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
    observation = evidence.get('observation')
    if type(observation) is dict:
        lines[-1] = 'Observed behavior: ' + text('; '.join(text(k, 40) + '=' + text(v, 80) for k, v in islice(observation.items(), 8)), 700)
    if type(legacy.get('error')) is dict:
        lines.append('Retained run diagnostic: ' + '; '.join(text(k, 40) + '=' + text(v, 160) for k, v in islice(legacy['error'].items(), 8)))
    for key in ('error', 'stderr', 'stdout', 'compile_stderr', 'compile_stdout'):
        if type(evidence.get(key)) is str and evidence[key]:
            lines.append('Retained ' + key + ':\n' + text(evidence[key], 1200))
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
