"""Read-only aggregate observations and bounded reports over synthetic receipts."""
import json
from pathlib import Path
import threading

import pytest

from firmavex.backends.engine import _write
from firmavex.backends.security import bounded_reads, read_bytes
from firmavex.product import regression, regression_review as review
from firmavex.product.tools import file_identity
from tests.product.test_regression import setup_set, fake_executor, output
from tests.product.test_workspace import contents


def session(tmp_path, monkeypatch, name='run'):
    config, entries, saved = setup_set(tmp_path)
    fake_executor(monkeypatch)
    result = regression.execute(saved['directory'], output(saved, name), trust='trusted_project')
    for entry in result['entries']:
        root = Path(result['directory']) / entry['evidence']
        source = root / 'testbench.v'
        source.write_bytes(Path(config['configuration'], 'input').read_bytes())
        wave = root / 'waveform.vcd'; wave.write_bytes(b'$enddefinitions $end\n#0\n#1\n')
        record = json.loads((root / 'result.json').read_text())
        record['evidence'].update(source=file_identity(source), artifacts=[{'name': wave.name, **file_identity(wave)}])
        _write(root / 'result.json', record)
    return saved, result


def test_dashboard_search_data_and_verification_never_modify_evidence(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    before = contents(Path(saved['directory']))
    dashboard = review.dashboard(tmp_path / 'sets', directory=saved['directory'])
    assert dashboard['sets'][0]['name'] == 'My set'
    assert dashboard['sessions'][0]['counts']['failed'] == 1
    assert len(dashboard['configurations']) == 3
    result = review.review(run['directory'], verify_evidence=True)
    assert result['status'] == 'verified' and result['counts']['verified'] == 3
    assert all(row['association'] == 'same' for row in result['entries'])
    assert sum(len(row['artifacts']) for row in result['entries']) == 6
    assert result['budget']['consumed'] <= review.READ_BYTES
    assert contents(Path(saved['directory'])) == before


@pytest.mark.parametrize('mutation,state', [('missing', 'missing'), ('changed', 'changed'), ('malformed', 'unavailable'), ('legacy', 'unverified')])
def test_artifact_and_association_states(tmp_path, monkeypatch, mutation, state):
    _, run = session(tmp_path, monkeypatch)
    root = Path(run['directory']) / run['entries'][0]['evidence']
    record = json.loads((root / 'result.json').read_text())
    if mutation == 'missing': (root / 'waveform.vcd').unlink()
    if mutation == 'changed': (root / 'waveform.vcd').write_bytes(b'changed')
    if mutation == 'malformed': record['evidence']['artifacts'][0]['sha256'] = 'bad'
    if mutation == 'legacy': del record['evidence']['admission']['execution_provenance']
    _write(root / 'result.json', record)
    before = contents(Path(run['directory']))
    result = review.review(run['directory'], verify_evidence=True)
    assert result['entries'][0]['state'] == state
    assert result['status'] != 'verified'
    assert contents(Path(run['directory'])) == before


def test_no_implicit_verification_and_partial_not_run(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    root = Path(run['directory'])
    summary = json.loads((root / 'regression.json').read_text())
    summary['entries'][2].update(status='not_run', category='not_run', evidence=None)
    summary['state'] = 'cancelled'; regression._publish(root, summary)
    result = review.review(root)
    assert result['status'] == 'unverified' and result['entries'][2]['state'] == 'unavailable'
    assert all(not row['artifacts'] for row in result['entries'])
    assert result['summary']['counts']['not_run'] == 1


def test_cancellation_retains_finished_artifact_observations(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    event = threading.Event()
    count = 0
    def cancel(progress):
        nonlocal count
        if progress['phase'] == 'artifact':
            count += 1
            if count == 3: event.set()
    before = contents(Path(run['directory']))
    result = review.review(run['directory'], verify_evidence=True, cancel_event=event, event_callback=cancel)
    assert result['status'] == 'cancelled'
    assert result['entries'][0]['artifacts'][0]['state'] == 'verified'
    assert result['entries'][1]['state'] == 'unverified'
    assert contents(Path(run['directory'])) == before


def test_identity_mismatch_cannot_be_aggregate_verified(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    root = Path(run['directory'])
    summary = json.loads((root / 'regression.json').read_text())
    summary['entries'][0]['input_sha256'] = '0' * 64
    regression._publish(root, summary)
    result = review.review(root, verify_evidence=True)
    assert result['entries'][0]['association'] == 'changed'
    assert result['entries'][0]['state'] == 'changed'
    assert all(item['state'] == 'verified' for item in result['entries'][0]['artifacts'])


def test_aggregate_artifact_and_byte_budgets_fail_closed(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    monkeypatch.setattr(review, 'ARTIFACTS', 1)
    result = review.review(run['directory'], verify_evidence=True)
    assert result['limit_reached'] and result['status'] == 'unverified'
    assert result['counts']['verified'] == 0
    monkeypatch.setattr(review, 'READ_BYTES', 10)
    with pytest.raises(ValueError): review.review(run['directory'], verify_evidence=True)


def test_shared_read_budget_counts_recapture_and_resets(tmp_path):
    path = tmp_path / 'file'; path.write_bytes(b'123')
    with bounded_reads(16) as budget:
        assert read_bytes(path, 100) == b'123'
        assert budget['consumed'] == 6
        assert read_bytes(path, 100) == b'123'
        with pytest.raises(ValueError): read_bytes(path, 100)
        assert budget['consumed'] <= 16
    assert read_bytes(path, 100) == b'123'
    with bounded_reads(100, calls=1):
        read_bytes(path, 100)
        with pytest.raises(ValueError): read_bytes(path, 100)


def test_changed_summary_invalidates_overall_verified_claim(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    root = Path(run['directory'])
    original = review.verification.verify
    def changing(*a, **kw):
        result = original(*a, **kw)
        summary = json.loads((root / 'regression.json').read_text())
        summary['name'] = 'externally changed'; regression._publish(root, summary)
        return result
    monkeypatch.setattr(review.verification, 'verify', changing)
    result = review.review(root, verify_evidence=True)
    assert result['summary_observation'] == 'changed' and result['status'] != 'verified'


def test_text_export_freshly_verifies_sanitizes_and_preserves_original(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    root = Path(run['directory'])
    record_path = root / run['entries'][0]['evidence'] / 'result.json'
    record = json.loads(record_path.read_text()); record['evidence']['stderr'] = 'bad\x1b\x00log'
    _write(record_path, record)
    before = contents(Path(saved['directory']))
    result = review.export(root, tmp_path / 'report')
    report = Path(result['report']).read_text()
    assert run['run_id'] in report and 'Failure diagnosis' in report
    assert '\x1b' not in report and '\x00' not in report
    assert result['verification_status'] == 'verified'
    assert sorted(p.name for p in Path(result['report']).parent.iterdir()) == ['regression.txt']
    assert Path(result['report']).stat().st_size <= review.REPORT_BYTES
    assert contents(Path(saved['directory'])) == before
    with pytest.raises(FileExistsError): review.export(root, tmp_path / 'report')
    # A previous UI observation cannot be submitted as current verification.
    (root / run['entries'][0]['evidence'] / 'waveform.vcd').write_bytes(b'changed')
    assert review.export(root, tmp_path / 'changed-report')['verification_status'] == 'changed'


def test_export_rejects_evidence_overlap_and_cancellation(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    for destination in (Path(run['directory']) / 'report', Path(saved['directory']) / 'report', Path(run['directory']).parent):
        with pytest.raises(ValueError, match='outside original'):
            review.export(run['directory'], destination)
    event = threading.Event(); event.set()
    with pytest.raises(KeyboardInterrupt): review.export(run['directory'], tmp_path / 'cancelled-report', cancel_event=event)
    assert not (tmp_path / 'cancelled-report').exists()


def test_comparison_changed_missing_and_incomparable_definitions(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    second = Path(saved['directory']) / 'runs' / 'second'; second.mkdir()
    summary = json.loads(Path(run['directory'], 'regression.json').read_text())
    summary['entries'][0].update(status='triggered', category='failed')
    summary['entries'].pop()
    summary['run_id'] = 'a' * 32
    regression._publish(second, summary)
    result = review.compare(run['directory'], second)
    assert [r['comparison'] for r in result['rows']] == ['changed', 'same', 'missing']
    assert result['revision_comparison'] == 'same'
    summary['entries'][0]['configuration_revision'] = 'b' * 64
    summary['revision'] = 'c' * 64; regression._publish(second, summary)
    result = review.compare(run['directory'], second)
    assert result['revision_comparison'] == 'changed'
    assert result['rows'][0]['comparison'] == 'not comparable'
    assert result['rows'][0]['definition'] == 'changed'


@pytest.mark.parametrize('data', [b'{}', b'not json', b'x' * (regression.SUMMARY_BYTES + 1)])
def test_malformed_sessions_rejected_without_repair(tmp_path, data):
    root = tmp_path / 'bad'; root.mkdir(); (root / 'regression.json').write_bytes(data)
    with pytest.raises(ValueError): review.review(root, verify_evidence=True)
    assert (root / 'regression.json').read_bytes() == data


def test_global_dashboard_and_missing_previous_are_explicit(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    dashboard = review.dashboard(tmp_path / 'sets')
    assert dashboard['sessions'][0]['run_id'] == run['run_id']
    result = review.review(run['directory'], verify_evidence=True, previous_run=tmp_path / 'missing')
    assert result['status'] == 'verified' and result['comparison']['status'] == 'unavailable'
    report = review.export(run['directory'], tmp_path / 'report', previous_run=tmp_path / 'missing')
    assert 'unavailable' in Path(report['report']).read_text()


def test_export_protects_configuration_and_previous_session(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    config = saved['entries'][0]['configuration']
    with pytest.raises(ValueError, match='outside original'):
        review.export(run['directory'], Path(config) / 'report')
    previous = tmp_path / 'previous'; previous.mkdir()
    with pytest.raises(ValueError, match='outside original'):
        review.export(run['directory'], previous / 'report', previous_run=previous)


def test_report_limit_failure_leaves_no_destination(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    before = contents(Path(run['directory']))
    monkeypatch.setattr(review, 'REPORT_BYTES', 20)
    with pytest.raises(ValueError, match='report exceeds'):
        review.export(run['directory'], tmp_path / 'report')
    assert not (tmp_path / 'report').exists()
    assert contents(Path(run['directory'])) == before


def test_missing_backend_input_identity_is_not_verified(tmp_path, monkeypatch):
    _, run = session(tmp_path, monkeypatch)
    record_path = Path(run['directory']) / run['entries'][0]['evidence'] / 'result.json'
    record = json.loads(record_path.read_text()); del record['evidence']['source']
    _write(record_path, record)
    result = review.review(run['directory'], verify_evidence=True)
    assert result['status'] != 'verified'
    assert result['entries'][0]['association'] == 'unavailable'


def test_dashboard_bounds_session_scan(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    root = Path(saved['directory']) / 'runs'
    summary = json.loads(Path(run['directory'], 'regression.json').read_text())
    for index in range(205):
        directory = root / str(index); directory.mkdir()
        regression._publish(directory, summary)
    result = review.dashboard(tmp_path / 'sets')
    assert result['session_candidates'] == 200 and len(result['sessions']) == 50


def test_aggregate_context_propagates_cancellation_to_metadata_reads(tmp_path):
    path = tmp_path / 'metadata.json'; path.write_bytes(b'{}')
    event = threading.Event(); event.set()
    with bounded_reads(100, cancel_event=event) as budget:
        with pytest.raises(KeyboardInterrupt): read_bytes(path, 100)
        assert budget['consumed'] == 0
    assert read_bytes(path, 100) == b'{}'


def test_read_only_worker_actions_cannot_execute_workloads(tmp_path, monkeypatch):
    import io
    import subprocess
    from firmavex.product.worker import Worker
    from firmavex.product.protocol import encode_command, decode_command, decode_event
    saved, run = session(tmp_path, monkeypatch)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('Review must not execute any program'))
    payloads = [dict(action='dashboard', root=str(tmp_path / 'sets')),
                dict(action='session_compare', left=run['directory'], right=run['directory']),
                dict(action='review', directory=run['directory']),
                dict(action='verify', directory=run['directory']),
                dict(action='export', directory=run['directory'], output_dir=str(tmp_path / 'report'))]
    for index, payload in enumerate(payloads):
        stream = io.BytesIO(); worker = Worker(stream)
        worker.handle(decode_command(encode_command(str(index), 'backend_regression', payload)))
        worker._thread.join(timeout=10)
        assert not worker._thread.is_alive()
        result = [decode_event(line) for line in stream.getvalue().splitlines()][-1]
        assert result['kind'] == 'result', result


def test_unavailable_observations_and_changed_classifications_are_not_same(tmp_path, monkeypatch):
    saved, run = session(tmp_path, monkeypatch)
    target = Path(saved['directory']) / 'runs' / 'other'; target.mkdir()
    summary = json.loads(Path(run['directory'], 'regression.json').read_text())
    summary['entries'][0]['category'] = 'infrastructure_error'
    summary['entries'][1].update(status='not_run', category='not_run', evidence=None)
    summary['state'] = 'stopped'; regression._publish(target, summary)
    result = review.compare(run['directory'], target)
    assert result['rows'][0]['comparison'] == 'changed'
    assert result['rows'][1]['comparison'] == 'unavailable'
    assert result['left']['counts']['failed'] == 1
    assert result['right']['counts']['not_run'] == 1
