"""Synthetic RV32 adapter-state regressions, never native execution evidence.

Only invented temporary bytes and process doubles are used. The adapter's normal
measurement labels under these mocks do not establish real firmware execution.
"""
from contextlib import nullcontext
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from firmavex.backends.api import Request
from firmavex.backends.engine import execute, inspect_run
from firmavex.backends import implementations as adapter
from firmavex.backends.process import Cancelled


@dataclass
class Scenario:
    root: Path
    source: Path
    qemu: Path
    gdb: Path
    output: Path
    probe_codes: dict = field(default_factory=dict)
    probe_error: BaseException | None = None
    probe_stdout: str = 'Invented version fixture\n'
    startup_error: BaseException | None = None
    qemu_exit: int | None = None
    endpoint_unavailable: bool = False
    debugger_error: BaseException | None = None
    debugger_code: int = 0
    completion_error: BaseException | None = None
    changed_identity: str | None = None
    cleanup_error: BaseException | None = None
    triggered: bool = True
    instances: list = field(default_factory=list)
    admission_calls: list = field(default_factory=list)
    connection_calls: list = field(default_factory=list)

    def request(self):
        return Request('riscv32-virt', self.source, (2, 1))

    def direct(self):
        self.output.mkdir()
        return adapter.RiscvBackend().execute(self.request(), self.output, threading.Event())

    def recorded(self):
        return execute(self.request(), self.output, threading.Event())


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    source, qemu, gdb = (tmp_path / name for name in ('invented-input.elf', 'invented-qemu', 'invented-gdb'))
    for path in (source, qemu, gdb):
        path.write_bytes(b'Synthetic inert test bytes, not an executable or actual firmware.\n')
    state = Scenario(tmp_path, source, qemu, gdb, tmp_path / 'fresh output')
    monkeypatch.setattr(adapter, 'require_native_candidate', lambda profile: state.admission_calls.append(profile))
    monkeypatch.setattr('firmavex.backends.inputs.rv32', lambda data: None)
    monkeypatch.setattr('firmavex.backends.tools.find_many', lambda names: {
        'qemu-system-riscv32': str(qemu), 'gdb-multiarch': str(gdb)})
    monkeypatch.setattr(adapter, '_allocate_port', lambda: 34567)
    # Replace this module's time object, rather than mutating global time used by pytest.
    ticks = iter(range(1000))
    monkeypatch.setattr(adapter, 'time', SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda delay: None))

    def connection(address, timeout):
        state.connection_calls.append((address, timeout))
        assert address == ('127.0.0.1', 34567)
        if state.endpoint_unavailable:
            raise OSError('Synthetic unavailable endpoint')
        return nullcontext()
    monkeypatch.setattr(adapter.socket, 'create_connection', connection)

    class Processes:
        def __init__(self, cancel, limits):
            self.cancel, self.limits = cancel, limits
            self.children, self.cleanup, self.commands = [], [], []
            self.close_calls = 0
            state.instances.append(self)

        def run(self, command, output, **kwargs):
            self.commands.append((list(command), dict(kwargs)))
            if command[1:] == ['--version']:
                if state.probe_error is not None:
                    raise state.probe_error
                role = 'qemu' if command[0] == str(qemu) else 'gdb'
                return state.probe_codes.get(role, 0), state.probe_stdout, 'Synthetic tool diagnostic'
            assert command[0] == str(gdb) and '--batch' in command
            if state.debugger_error is not None:
                raise state.debugger_error
            return state.debugger_code, 'Invented debugger output; parsed only by a stub.', 'Synthetic debugger diagnostic'

        def spawn(self, command, output):
            self.commands.append((list(command), {}))
            assert command[0] == str(qemu) and '-M' in command and 'virt' in command
            child = SimpleNamespace(pid=4242, poll=lambda: state.qemu_exit, returncode=state.qemu_exit)
            log = SimpleNamespace(text=lambda: 'Invented process log')
            self.children.append((child, log, log, None))
            return child, log, log

        def check(self):
            if state.startup_error is not None:
                raise state.startup_error

        def close(self):
            self.close_calls += 1
            self.cleanup = [{'pid': item[0].pid, 'reaped': state.cleanup_error is None} for item in self.children]
            if state.cleanup_error is not None:
                raise state.cleanup_error
    monkeypatch.setattr(adapter, 'Processes', Processes)

    def completion(stdout, marker, config, values):
        if state.completion_error is not None:
            raise state.completion_error
        if state.changed_identity is not None:
            target = {'firmware': state.output / 'firmware.elf', 'qemu': qemu, 'gdb': gdb}[state.changed_identity]
            target.write_bytes(b'Synthetic changed identity\n')
        return {'success': True, 'ready_reached': True,
                'inputs_read_back': dict(zip(config.input_symbols, values)), 'completion_reached': True,
                'observed_value': 1 if state.triggered else 0, 'triggered': state.triggered}
    monkeypatch.setattr(adapter, '_parse_completion', completion)
    return state


def diagnostic(category, stage, tool, code=None):
    return {'schema_version': 1, 'backend': 'riscv32-virt', 'stage': stage,
            'category': category, 'tool': tool, 'return_code': code}


@pytest.mark.parametrize('triggered,expected', [(False, 'passed'), (True, 'triggered')], ids=['safe', 'triggered'])
def test_successful_observation_does_not_invent_failure_metadata(scenario, triggered, expected):
    scenario.triggered = triggered
    result = scenario.direct().to_dict()
    assert result['status'] == expected
    assert 'failure_diagnostic' not in result['evidence']
    assert result['evidence']['completion_observed'] is True
    assert result['evidence']['observation']['inputs_read_back'] == {'input_a': 2, 'input_b': 1}
    assert result['evidence']['cleanup_verified'] is True
    assert scenario.instances[0].close_calls == 1
    assert scenario.admission_calls == ['riscv32-virt']
    commands = [command for command, _ in scenario.instances[0].commands]
    assert len(commands) == 4
    assert all('gcc' not in value for command in commands for value in command)


@pytest.mark.parametrize('role,code', [('qemu', 17), ('gdb', 19)], ids=['qemu', 'gdb'])
def test_probe_nonzero_exit_is_recorded_without_guessing_firmware_cause(scenario, role, code):
    scenario.probe_codes[role] = code
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('tool_exit', 'tool_probe', role, code)
    assert result['evidence']['completion_observed'] is False
    assert scenario.instances[0].close_calls == 1
    assert inspect_run(scenario.output) == result


@pytest.mark.parametrize('code', [0, 7, -9], ids=['early-success-exit', 'nonzero', 'negative'])
def test_qemu_exit_before_endpoint_is_precisely_retained(scenario, code):
    scenario.qemu_exit = code
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('tool_exit', 'qemu_startup', 'qemu', code)
    assert not scenario.connection_calls
    assert scenario.instances[0].close_calls == 1


def test_typed_startup_timeout_is_not_reconstructed_from_message(scenario):
    error = TimeoutError('No keyword relevant to classification')
    scenario.startup_error = error
    with pytest.raises(TimeoutError) as caught:
        scenario.direct()
    assert caught.value is error
    assert error.backend_evidence['failure_diagnostic'] == diagnostic('timeout', 'qemu_startup', 'qemu')
    assert error.backend_evidence['cleanup_verified'] is True


def test_endpoint_deadline_has_startup_phase_and_no_completed_observation(scenario):
    scenario.endpoint_unavailable = True
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('timeout', 'qemu_startup', 'qemu')
    assert scenario.connection_calls and result['evidence']['completion_observed'] is False
    assert inspect_run(scenario.output) == result


def test_typed_debugger_timeout_is_distinct_from_startup(scenario):
    scenario.debugger_error = TimeoutError('Synthetic deadline')
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('timeout', 'debugger_observation', 'gdb')
    assert result['evidence']['completion_observed'] is False
    assert scenario.instances[0].close_calls == 1
    assert inspect_run(scenario.output) == result


def test_typed_probe_timeout_identifies_probe_tool(scenario):
    scenario.probe_error = TimeoutError('Synthetic probe deadline')
    result = scenario.recorded()
    assert result['evidence']['failure_diagnostic'] == diagnostic('timeout', 'tool_probe', 'qemu')
    assert result['status'] == 'infrastructure_failure'


@pytest.mark.parametrize('code', [2, -11], ids=['nonzero', 'negative'])
def test_debugger_nonzero_exit_is_a_tool_failure_not_assertion(scenario, code):
    scenario.debugger_code = code
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('tool_exit', 'debugger_observation', 'gdb', code)
    assert result['evidence']['completion_observed'] is False


def test_invalid_completion_has_specific_observation_evidence(scenario):
    scenario.completion_error = ValueError('Synthetic malformed completion record')
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('invalid_observation', 'completion_validation', 'gdb')
    assert result['evidence']['completion_observed'] is False


@pytest.mark.parametrize('subject,tool', [('firmware', None), ('qemu', 'qemu'), ('gdb', 'gdb')],
                         ids=['firmware', 'qemu', 'gdb'])
def test_changed_identity_is_only_recorded_after_actual_comparison(scenario, subject, tool):
    scenario.changed_identity = subject
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('identity_changed', 'identity_validation', tool)
    # A completed debugger record does not make a later identity failure successful.
    assert result['evidence']['completion_observed'] is True
    assert inspect_run(scenario.output) == result


@pytest.mark.parametrize('message', ['timeout', 'assertion failed', 'TimeoutError: assert failed'],
                         ids=['timeout-word', 'assertion-word', 'both-words'])
def test_exception_text_cannot_invent_typed_timeout_or_assertion(scenario, message):
    scenario.debugger_error = RuntimeError(message)
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('infrastructure_error', 'debugger_observation', 'gdb')


@pytest.mark.parametrize('error', [Cancelled('Synthetic cancellation'), KeyboardInterrupt('Synthetic interrupt'),
                                  SystemExit(37)], ids=['cancelled', 'keyboard', 'exit'])
def test_cancellation_metadata_preserves_original_control_flow_and_cleanup(scenario, error):
    scenario.debugger_error = error
    with pytest.raises(type(error)) as caught:
        scenario.direct()
    assert caught.value is error
    assert error.backend_evidence['failure_diagnostic'] == diagnostic('cancelled', 'debugger_observation', 'gdb')
    assert error.backend_evidence['cleanup_verified'] is True
    assert scenario.instances[0].close_calls == 1


@pytest.mark.parametrize('error', [KeyboardInterrupt('Synthetic interrupt'), SystemExit(39)], ids=['keyboard', 'exit'])
def test_engine_persists_cancellation_without_changing_original_exception(scenario, error):
    scenario.debugger_error = error
    with pytest.raises(type(error)) as caught:
        scenario.recorded()
    assert caught.value is error
    saved = inspect_run(scenario.output)
    assert saved['status'] == 'cancelled'
    assert saved['evidence']['failure_diagnostic'] == diagnostic('cancelled', 'debugger_observation', 'gdb')


def test_cleanup_only_failure_cannot_become_a_success_or_invent_primary_cause(scenario):
    scenario.cleanup_error = RuntimeError('Synthetic cleanup failure')
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['cleanup_verified'] is False
    assert 'failure_diagnostic' not in result['evidence']
    assert result['evidence']['completion_observed'] is True
    assert inspect_run(scenario.output) == result


def test_cleanup_failure_preserves_primary_diagnostic_and_no_success(scenario):
    scenario.debugger_error = TimeoutError('Synthetic debugger timeout')
    scenario.cleanup_error = RuntimeError('Synthetic cleanup failure')
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('timeout', 'debugger_observation', 'gdb')
    assert result['evidence']['cleanup_verified'] is False


def test_pre_execution_import_failure_does_not_invent_a_reached_phase(scenario):
    scenario.source.unlink()
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert 'failure_diagnostic' not in result['evidence']
    assert not scenario.instances
    assert inspect_run(scenario.output) == result


def test_host_assertion_exception_is_not_classified_as_guest_assertion(scenario):
    scenario.debugger_error = AssertionError('Synthetic host-side assertion, not guest evidence')
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('infrastructure_error', 'debugger_observation', 'gdb')


def test_unrecognized_control_exception_is_preserved_without_inventing_cancellation_kind(scenario):
    error = BaseException('Synthetic custom control flow')
    scenario.debugger_error = error
    with pytest.raises(BaseException) as caught:
        scenario.direct()
    assert caught.value is error
    assert error.backend_evidence['failure_diagnostic'] == diagnostic('infrastructure_error', 'debugger_observation', 'gdb')
    assert scenario.instances[0].close_calls == 1


def test_empty_successful_probe_output_retains_unknown_infrastructure_cause(scenario):
    scenario.probe_stdout = ''
    result = scenario.recorded()
    assert result['status'] == 'infrastructure_failure'
    assert result['evidence']['failure_diagnostic'] == diagnostic('infrastructure_error', 'tool_probe', 'qemu')
    assert result['evidence']['completion_observed'] is False
    assert scenario.instances[0].close_calls == 1
    assert inspect_run(scenario.output) == result


def test_saved_failure_diagnostic_survives_export_without_modifying_original(scenario):
    from firmavex.backends.report import export

    scenario.debugger_error = TimeoutError('Synthetic timeout for export consistency')
    original = scenario.recorded()
    result_file = scenario.output / 'result.json'
    before = result_file.read_bytes(), result_file.stat().st_mtime_ns
    destination = scenario.root / 'fresh exported report'
    exported = export(scenario.output, destination)
    assert exported['status'] == 'exported'
    copied = json.loads((destination / 'result.json').read_bytes())
    assert copied == original
    assert copied['evidence']['failure_diagnostic'] == diagnostic('timeout', 'debugger_observation', 'gdb')
    checksums = json.loads((destination / 'checksums.json').read_bytes())
    assert checksums['result.json'] == hashlib.sha256((destination / 'result.json').read_bytes()).hexdigest()
    assert (result_file.read_bytes(), result_file.stat().st_mtime_ns) == before
    assert inspect_run(scenario.output) == original
