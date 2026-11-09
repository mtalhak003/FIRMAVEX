"""Synthetic metadata contracts only; these fixtures are not native evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import windows_candidate_artifact as binding
from tests.product.test_windows_candidate_evidence import (
    archive as fixture_archive, installed_records, product_records, records,
)

SHA, REVISION, RUN, ATTEMPT, ARTIFACT = 'a'*64, 'b'*40, 123, 2, 456
ARCHIVE_VERIFIER = binding.evidence.verify_archive


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    artifact = {'id': ARTIFACT, 'expired': False,
        'name': 'Windows-UNQUALIFIED-runtime-candidate-' + REVISION, 'digest': 'sha256:' + SHA,
        'size_in_bytes': 1, 'archive_download_url':
            f'https://api.github.com/repos/mtalhak003/FIRMAVEX/actions/artifacts/{ARTIFACT}/zip',
        'workflow_run': {'id': RUN, 'head_sha': REVISION, 'head_branch': binding.BRANCH},
        'created_at': '2026-11-09T10:30:00Z'}
    attempt = {'id': RUN, 'run_attempt': ATTEMPT, 'head_sha': REVISION, 'head_branch': binding.BRANCH,
        'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success', 'path': binding.WORKFLOW,
        'repository': {'full_name': binding.REPOSITORY}, 'head_repository': {'full_name': binding.REPOSITORY},
        'run_started_at': '2026-11-09T10:00:00Z', 'updated_at': '2026-11-09T11:00:00Z'}
    paths = (tmp_path/'artifact.json', tmp_path/'attempt.json')
    calls = []
    def archive(path, **kwargs):
        calls.append((path, kwargs))
        return {'validation': 'passed', 'candidate_only': True, 'production_qualified': False}
    monkeypatch.setattr(binding.evidence, 'verify_archive', archive)
    return artifact, attempt, paths, calls


def verify(metadata, **overrides):
    artifact, attempt, paths, _ = metadata
    for path, value in zip(paths, (artifact, attempt)):
        path.write_text(json.dumps(value), encoding='utf-8')
    expected = {'expected_sha256': SHA, 'expected_revision': REVISION, 'expected_run_id': RUN,
                'expected_attempt': ATTEMPT, 'expected_artifact_id': ARTIFACT, **overrides}
    return binding.verify('original.zip', *paths, **expected)


def test_valid_metadata_requires_both_archive_scopes_without_claiming_authenticity(metadata):
    result = verify(metadata)
    assert result['validation'] == 'passed' and result['metadata_binding'] == 'passed'
    assert result['production_qualified'] is False and result['candidate_only'] is True
    assert result['run_attempt'] == ATTEMPT and result['artifact_id'] == ARTIFACT
    assert result['metadata_capture_consistency'] == 'stable_observed' and result['atomic_snapshot'] is False
    assert 'artifact origin in the asserted attempt' in result['not_proven']
    assert metadata[3] == [('original.zip', {'expected_sha256': SHA, 'expected_revision': REVISION,
        'expected_run_id': str(RUN), 'require_product_paths': True, 'require_installed_path': True})]
    # The metadata size is bounded, but is not assumed to equal ZIP filesystem size.
    assert metadata[0]['size_in_bytes'] == 1


@pytest.mark.parametrize('field,value', [('expected_sha256', 'A'*64), ('expected_revision', 'invalid'),
    ('expected_run_id', True), ('expected_run_id', '123'), ('expected_run_id', 0),
    ('expected_attempt', True), ('expected_attempt', 10001), ('expected_artifact_id', False),
    ('expected_artifact_id', 2**63)])
def test_expected_identity_types_fail_before_archive_dispatch(metadata, field, value):
    assert verify(metadata, **{field: value})['validation'] == 'failed'
    assert not metadata[3]


@pytest.mark.parametrize('record,field,value', [
    (0, 'id', True), (0, 'id', ARTIFACT+1), (0, 'expired', 0), (0, 'expired', True),
    (0, 'name', 'other'), (0, 'digest', SHA), (0, 'size_in_bytes', True), (0, 'size_in_bytes', 0),
    (0, 'size_in_bytes', binding.evidence.MAX_ARCHIVE+1),
    (0, 'archive_download_url', 'https://untrusted.invalid/archive.zip?credential=private'),
    (1, 'id', True), (1, 'run_attempt', True), (1, 'run_attempt', ATTEMPT+1),
    (1, 'head_sha', 'c'*40), (1, 'head_branch', 'main'), (1, 'event', 'push'),
    (1, 'status', 'in_progress'), (1, 'conclusion', 'failure'), (1, 'path', 'other.yml'),
    (1, 'repository', {'full_name': 'other/repo'}), (1, 'head_repository', None),
    (0, 'workflow_run', {'id': True, 'head_sha': REVISION, 'head_branch': binding.BRANCH}),
    (0, 'workflow_run', {'id': RUN, 'head_sha': REVISION, 'head_branch': 'main'}),
    (0, 'workflow_run', {'id': RUN+1, 'head_sha': REVISION, 'head_branch': binding.BRANCH}),
    (0, 'workflow_run', {'id': RUN, 'head_sha': 'c'*40, 'head_branch': binding.BRANCH}),
])
def test_metadata_mismatch_never_dispatches_archive_or_echoes_payload(metadata, record, field, value):
    metadata[record][field] = value
    result = verify(metadata)
    assert result['validation'] == 'failed' and not metadata[3]
    assert 'private' not in json.dumps(result) and 'untrusted.invalid' not in json.dumps(result)


@pytest.mark.parametrize('record,field,value', [
    (0, 'created_at', '2026-11-09T09:59:59Z'), (0, 'created_at', '2026-11-09T11:00:01Z'),
    (0, 'created_at', '2026-11-09T10:30:00'), (0, 'created_at', '2026-11-09T10:30:00+05:00'),
    (0, 'created_at', '2026-13-09T10:30:00Z'), (0, 'created_at', False),
    (1, 'run_started_at', '2026-11-09T12:00:00Z'), (1, 'updated_at', '2026-11-09T09:00:00Z'),
])
def test_timestamps_must_be_utc_and_contained_without_authenticity_claim(metadata, record, field, value):
    metadata[record][field] = value
    assert verify(metadata)['validation'] == 'failed' and not metadata[3]


@pytest.mark.parametrize('created', ['2026-11-09T10:00:00Z', '2026-11-09T11:00:00+00:00'])
def test_timestamp_inclusive_boundaries(metadata, created):
    metadata[0]['created_at'] = created
    assert verify(metadata)['validation'] == 'passed'


@pytest.mark.parametrize('payload', [b'{"id":1,"id":2}', b'{"value":NaN}', b'[]', b'not JSON'])
def test_malformed_or_duplicate_metadata_fails_closed(metadata, payload):
    paths = metadata[2]
    paths[0].write_bytes(payload); paths[1].write_text('{}')
    result = binding.verify('never-opened.zip', *paths, expected_sha256=SHA, expected_revision=REVISION,
        expected_run_id=RUN, expected_attempt=ATTEMPT, expected_artifact_id=ARTIFACT)
    assert result['validation'] == 'failed' and not metadata[3]


def test_metadata_read_bound_is_enforced_before_archive(metadata, monkeypatch):
    monkeypatch.setattr(binding, 'MAX_METADATA', 1)
    assert verify(metadata)['validation'] == 'failed' and not metadata[3]


def test_archive_failure_is_preserved_as_failure_after_metadata_pass(metadata, monkeypatch):
    monkeypatch.setattr(binding.evidence, 'verify_archive', lambda *a, **k:
        {'validation': 'failed', 'candidate_only': True, 'production_qualified': False,
         'failures': [{'code': 'archive_digest_mismatch'}]})
    result = verify(metadata)
    assert result['validation'] == 'failed' and result['metadata_binding'] == 'passed'
    assert result['archive_validation']['failures'] == [{'code': 'archive_digest_mismatch'}]


@pytest.mark.parametrize('index', [0, 1])
def test_metadata_changes_during_archive_review_fail_closed(metadata, monkeypatch, index):
    def changed(*args, **kwargs):
        metadata[2][index].write_text('{"changed":true}', encoding='utf-8')
        return {'validation': 'passed', 'candidate_only': True, 'production_qualified': False}
    monkeypatch.setattr(binding.evidence, 'verify_archive', changed)
    result = verify(metadata)
    assert result['validation'] == 'failed'
    assert result['failures'] == [{'code': 'metadata_changed_during_verification'}]
    assert result['metadata_capture_consistency'] == 'not_verified'
    assert result['archive_validation']['validation'] == 'passed'  # Retain the separately completed check.


def test_real_read_only_archive_verifier_rejects_nonzip_after_metadata_binding(metadata, monkeypatch):
    """Actual verifier integration with invalid synthetic bytes, never native evidence."""
    artifact, attempt, paths, _ = metadata
    archive = paths[0].with_name('invalid-synthetic.zip')
    archive.write_bytes(b'not an archive; synthetic rejection fixture')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    artifact['digest'] = 'sha256:' + digest
    for path, value in zip(paths, (artifact, attempt)):
        path.write_text(json.dumps(value), encoding='utf-8')
    before = {path: path.read_bytes() for path in (*paths, archive)}
    monkeypatch.setattr(binding.evidence, 'verify_archive', ARCHIVE_VERIFIER)
    result = binding.verify(archive, *paths, expected_sha256=digest, expected_revision=REVISION,
        expected_run_id=RUN, expected_attempt=ATTEMPT, expected_artifact_id=ARTIFACT)
    assert result['metadata_binding'] == 'passed' and result['validation'] == 'failed'
    assert result['archive_validation']['archive_sha256'] == digest
    assert result['archive_validation']['failures'] == [{'code': 'malformed_or_unreadable_evidence'}]
    assert {path: path.read_bytes() for path in before} == before
    assert set(paths[0].parent.iterdir()) == set(before)


def test_actual_wrapper_and_zip_verifier_accept_consistent_synthetic_installed_scope(
        tmp_path, metadata, installed_records, monkeypatch):
    """Real code composition, but all metadata/receipts/image bytes are synthetic."""
    artifact, attempt, paths, _ = metadata
    original = fixture_archive(tmp_path, installed_records)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    revision = 'a'*40  # The independently labelled synthetic ZIP fixture's revision.
    artifact.update(name='Windows-UNQUALIFIED-runtime-candidate-' + revision, digest='sha256:' + digest)
    artifact['workflow_run']['head_sha'] = revision
    attempt['head_sha'] = revision
    for path, value in zip(paths, (artifact, attempt)):
        path.write_text(json.dumps(value), encoding='utf-8')
    before = {path: path.read_bytes() for path in (*paths, original)}
    monkeypatch.setattr(binding.evidence, 'verify_archive', ARCHIVE_VERIFIER)
    result = binding.verify(original, *paths, expected_sha256=digest, expected_revision=revision,
        expected_run_id=RUN, expected_attempt=ATTEMPT, expected_artifact_id=ARTIFACT)
    assert result['validation'] == 'passed', result
    archive = result['archive_validation']
    assert archive['installed_lifecycle']['required'] is True
    assert archive['product_admission']['required'] is True
    assert archive['attempt_receipts'] == 19 and archive['junit']['passed'] == 21
    assert result['production_qualified'] is False and result['metadata_capture_consistency'] == 'stable_observed'
    assert {path: path.read_bytes() for path in before} == before
    assert set(tmp_path.iterdir()) == set(before)


@pytest.mark.parametrize('control', [KeyboardInterrupt, SystemExit])
def test_control_flow_exceptions_are_not_swallowed(metadata, monkeypatch, control):
    def interrupt(*args, **kwargs): raise control('original interruption')
    monkeypatch.setattr(binding.evidence, 'verify_archive', interrupt)
    with pytest.raises(control, match='original interruption'): verify(metadata)


def test_cli_failure_is_nonzero_and_does_not_echo_private_paths(tmp_path):
    result = subprocess.run([sys.executable, '-m', 'tools.windows_candidate_artifact', 'private-original.zip',
        '--artifact-metadata', str(tmp_path/'secret-artifact.json'),
        '--attempt-metadata', str(tmp_path/'secret-attempt.json'), '--sha256', SHA, '--revision', REVISION,
        '--run-id', str(RUN), '--attempt', str(ATTEMPT), '--artifact-id', str(ARTIFACT)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    record = json.loads(result.stdout)
    assert record['validation'] == 'failed' and record['production_qualified'] is False
    assert 'secret-artifact' not in result.stdout and str(tmp_path) not in result.stdout
