"""Representative native test-set execution through unchanged backend admission."""
from pathlib import Path
import threading
from uuid import uuid4

import pytest

from firmavex.backends.api import Request, request_to_dict
from firmavex.backends import engine
from firmavex.backends.bundled import prepare_builtin_riscv
from firmavex.backends.examples import prepare
from firmavex.product import workspace, regression
from tests.backends.test_native import require


@pytest.mark.parametrize('profile', ['riscv32-virt', 'verilog-icarus'])
def test_actual_native_regression_set_and_rerun(tmp_path, profile):
    require(*(('qemu-system-riscv32', 'gdb-multiarch') if profile == 'riscv32-virt' else ('iverilog', 'vvp')))
    if profile == 'riscv32-virt':
        source = Path(prepare_builtin_riscv(tmp_path / 'example')['source'])
    else:
        prepare(profile, tmp_path / 'example')
        source = tmp_path / 'example' / 'counter.v'
    entries = []
    for i in range(2):
        if profile == 'verilog-icarus' and i:
            alternate = tmp_path / 'failure.v'
            alternate.write_text(source.read_text().replace('count===3', 'count===4'))
            source = alternate
        values = ((0, 0) if i == 0 else (2, 1)) if profile == 'riscv32-virt' else ()
        saved = workspace.save(tmp_path / 'configs', 'native ' + str(i), request_to_dict(Request(profile, source, values)))
        entries.append({'id': uuid4().hex, 'name': 'native ' + str(i), 'configuration': saved['configuration'], 'values': list(values)})
    testset = regression.save(tmp_path / 'sets', 'native suite', entries)
    directory = Path(testset['directory'])
    from firmavex.product.supervisor import Supervisor
    result = Supervisor().execute('backend_regression', {'action': 'execute', 'directory': str(directory),
        'output_dir': str(directory / 'runs' / 'first'), 'trust': 'trusted_project'})
    assert result['state'] == 'completed', result
    assert result['counts']['passed'] == 1 and result['counts']['failed'] == 1, result
    for entry in result['entries']:
        record = engine.inspect_run(Path(result['directory']) / entry['evidence'])
        assert record['evidence']['cleanup_verified'] is True
        assert all(child['reaped'] for child in record['evidence']['cleanup'])
        provenance = record['evidence']['admission']['execution_provenance']
        assert provenance['entry_id'] == entry['id']
        assert provenance['input_sha256'] == entry['input_sha256']
        assert record['evidence']['firmware' if profile == 'riscv32-virt' else 'source']['sha256'] == entry['input_sha256']
        assert record['evidence']['tools']
    # Explicit rerun preserves the first run byte-for-byte.
    before = {p.relative_to(Path(result['directory'])): p.read_bytes() for p in Path(result['directory']).rglob('*') if p.is_file()}
    rerun = regression.execute(directory, directory / 'runs' / 'second', trust='trusted_project', previous_run=result['directory'])
    assert rerun['rerun_of'] == result['run_id']
    assert all(row['comparison'] == 'same' for row in regression.compare(result['directory'], rerun['directory'])['rows'])
    assert before == {p.relative_to(Path(result['directory'])): p.read_bytes() for p in Path(result['directory']).rglob('*') if p.is_file()}
    # Full review/compare/verify/export workflow over native evidence, never execute artifacts.
    from firmavex.product import regression_review
    verified = Supervisor().execute('backend_regression', {'action': 'verify', 'directory': result['directory'],
                                                          'previous_run': rerun['directory']})
    assert verified['status'] == 'verified', verified
    assert all('Failure diagnosis' in entry['diagnostic'] for entry in verified['entries'])
    assert all(row['comparison'] == 'same' for row in verified['comparison']['rows'])
    exported = Supervisor().execute('backend_regression', {'action': 'export', 'directory': result['directory'],
        'output_dir': str(tmp_path / 'regression-report'), 'previous_run': rerun['directory']})
    assert exported['verification_status'] == 'verified'
    report = Path(exported['report']).read_text()
    assert result['run_id'] in report and 'Failure diagnosis' in report and 'Comparison:' in report
    assert list(Path(exported['report']).parent.iterdir()) == [Path(exported['report'])]
    assert before == {p.relative_to(Path(result['directory'])): p.read_bytes() for p in Path(result['directory']).rglob('*') if p.is_file()}


def test_actual_native_hdl_regression_inflight_cancellation(tmp_path):
    require('iverilog', 'vvp')
    source = tmp_path / 'loop.v'
    source.write_text('module testbench; initial begin $display("started"); forever #1; end endmodule')
    config = workspace.save(tmp_path / 'configs', 'loop', request_to_dict(Request('verilog-icarus', source)))
    entries = [{'id': uuid4().hex, 'name': str(i), 'configuration': config['configuration'], 'values': []} for i in range(2)]
    saved = regression.save(tmp_path / 'sets', 'cancel test', entries)
    event = threading.Event()
    def progress(data):
        if data.get('stage') == 'simulation_output': event.set()
    result = regression.execute(saved['directory'], Path(saved['directory']) / 'runs' / 'cancel',
                                trust='trusted_project', cancel_event=event, event_callback=progress)
    assert result['state'] == 'cancelled' and result['counts']['cancelled'] == 1, result
    assert result['counts']['not_run'] == 1
    record = engine.inspect_run(Path(result['directory']) / result['entries'][0]['evidence'])
    assert record['evidence']['cleanup_verified'] is True
    assert all(child['reaped'] for child in record['evidence']['cleanup'])
