"""Read-only binding of separately obtained GitHub metadata to a candidate ZIP.

No download, extraction, execution, repair or promotion occurs here. Metadata
consistency and timestamp containment do not authenticate GitHub or prove that
an artifact originated in the asserted attempt. Obtain originals independently.
"""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from firmavex.backends.security import read_bytes
from tools import windows_candidate_evidence as evidence

MAX_METADATA = 1024**2
REPOSITORY = 'mtalhak003/FIRMAVEX'
BRANCH = 'product/desktop-batch11'
WORKFLOW = '.github/workflows/windows-runtime-candidate.yml'


def _timestamp(value):
    evidence.require(type(value) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)', value),
        'invalid_metadata_timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    evidence.require(parsed.utcoffset() == timedelta(0), 'invalid_metadata_timestamp')
    return parsed


def verify(path, artifact_metadata_path, attempt_metadata_path, *, expected_sha256,
           expected_revision, expected_run_id, expected_attempt, expected_artifact_id):
    """Check supplied metadata before invoking the read-only full ZIP verifier."""
    result = {'schema_version': 1, 'kind': 'firmavex_windows_candidate_artifact_binding',
        'candidate_only': True, 'production_qualified': False, 'validation': 'failed',
        'metadata_binding': 'failed', 'metadata_capture_consistency': 'not_verified',
        'atomic_snapshot': False, 'failures': [],
        'scope': 'consistency of independently supplied metadata and original ZIP; no authentication',
        'not_proven': ['GitHub metadata authenticity', 'artifact origin in the asserted attempt',
                       'publisher trust', 'runtime production qualification']}
    try:
        evidence.require(evidence._sha(expected_sha256) and type(expected_revision) is str
            and re.fullmatch(r'[0-9a-f]{40}', expected_revision)
            and evidence._integer(expected_run_id, 1) and evidence._integer(expected_attempt, 1, 10000)
            and evidence._integer(expected_artifact_id, 1), 'invalid_expected_identity')
        artifact_bytes = read_bytes(artifact_metadata_path, MAX_METADATA)
        attempt_bytes = read_bytes(attempt_metadata_path, MAX_METADATA)
        artifact, attempt = evidence._json(artifact_bytes), evidence._json(attempt_bytes)
        evidence.require(type(artifact) is dict and type(attempt) is dict, 'invalid_metadata_record')
        evidence.require(type(artifact.get('id')) is int and artifact['id'] == expected_artifact_id
            and artifact.get('expired') is False
            and artifact.get('name') == 'Windows-UNQUALIFIED-runtime-candidate-' + expected_revision
            and artifact.get('digest') == 'sha256:' + expected_sha256
            and evidence._integer(artifact.get('size_in_bytes'), 1, evidence.MAX_ARCHIVE)
            and artifact.get('archive_download_url') ==
                f'https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{expected_artifact_id}/zip',
            'artifact_metadata_mismatch')
        workflow_run = artifact.get('workflow_run')
        evidence.require(type(workflow_run) is dict and type(workflow_run.get('id')) is int
            and workflow_run['id'] == expected_run_id and workflow_run.get('head_sha') == expected_revision
            and workflow_run.get('head_branch') == BRANCH, 'artifact_run_binding_mismatch')
        evidence.require(type(attempt.get('id')) is int and attempt['id'] == expected_run_id
            and type(attempt.get('run_attempt')) is int and attempt['run_attempt'] == expected_attempt
            and attempt.get('head_sha') == expected_revision and attempt.get('head_branch') == BRANCH
            and attempt.get('event') == 'workflow_dispatch' and attempt.get('status') == 'completed'
            and attempt.get('conclusion') == 'success' and attempt.get('path') == WORKFLOW,
            'attempt_metadata_mismatch')
        for field in ('repository', 'head_repository'):
            repository = attempt.get(field)
            evidence.require(type(repository) is dict and repository.get('full_name') == REPOSITORY,
                             'attempt_repository_mismatch')
        started = _timestamp(attempt.get('run_started_at'))
        updated = _timestamp(attempt.get('updated_at'))
        created = _timestamp(artifact.get('created_at'))
        evidence.require(started <= created <= updated, 'artifact_timestamp_outside_attempt')
        result.update(metadata_binding='passed', source_revision=expected_revision,
            run_id=expected_run_id, run_attempt=expected_attempt, artifact_id=expected_artifact_id,
            artifact_metadata_sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            attempt_metadata_sha256=hashlib.sha256(attempt_bytes).hexdigest())
        archive = evidence.verify_archive(path, expected_sha256=expected_sha256,
            expected_revision=expected_revision, expected_run_id=str(expected_run_id),
            require_product_paths=True, require_installed_path=True)
        evidence.require(type(archive) is dict and archive.get('candidate_only') is True
            and archive.get('production_qualified') is False
            and archive.get('validation') in {'passed', 'failed'}, 'invalid_archive_validation_result')
        result['archive_validation'] = archive
        evidence.require(read_bytes(artifact_metadata_path, MAX_METADATA) == artifact_bytes
            and read_bytes(attempt_metadata_path, MAX_METADATA) == attempt_bytes,
            'metadata_changed_during_verification')
        result['metadata_capture_consistency'] = 'stable_observed'
        result['validation'] = archive['validation']
        if archive['validation'] != 'passed':
            result['failures'] = [{'code': 'archive_validation_failed'}]
    except evidence.EvidenceError as error:
        result['failures'] = [{'code': error.code}]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
        result['failures'] = [{'code': 'malformed_or_unreadable_metadata'}]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--artifact-metadata', required=True, type=Path)
    parser.add_argument('--attempt-metadata', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--run-id', required=True, type=int)
    parser.add_argument('--attempt', required=True, type=int)
    parser.add_argument('--artifact-id', required=True, type=int)
    args = parser.parse_args(argv)
    result = verify(args.archive, args.artifact_metadata, args.attempt_metadata,
        expected_sha256=args.sha256, expected_revision=args.revision, expected_run_id=args.run_id,
        expected_attempt=args.attempt, expected_artifact_id=args.artifact_id)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['validation'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
