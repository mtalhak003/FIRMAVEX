"""Offline, scoped review attestations bound to an exact release manifest.

Trust policy is an independently provisioned administrative input. Never accept a
policy or a fingerprint merely because it arrived alongside a candidate bundle.
"""
from datetime import datetime, timezone
import re
from pathlib import Path

from firmavex.backends.security import read_json
from .artifact_signature import verify as verify_signature
from .release import _identity

REVIEW_CHECKS = frozenset({
    'component_license_and_corresponding_source_review',
    'embedded_executable_and_installer_composition',
    'physical_consumer_acceptance',
    'versioned_installer_lifecycle',
})


def verify(attestation, signature, public_key, trust_policy, manifest, *, now=None):
    """Verify bytes, authority, subject, review evidence identities and validity.

    Signing an attestation does not sign the installer. Artifact authenticity is
    a separate gate and cannot be asserted through this review protocol.
    """
    attestation = Path(attestation)
    before = _identity(attestation)
    subject = _identity(manifest)
    policy_before = _identity(trust_policy)
    policy = read_json(trust_policy)
    record = read_json(attestation)
    if (type(policy) is not dict or set(policy) != {'schema_version', 'keys'}
            or type(policy['schema_version']) is not int or policy['schema_version'] != 1
            or type(policy['keys']) is not dict):
        raise ValueError('Invalid independently supplied review trust policy')
    if (type(record) is not dict or set(record) != {
            'schema_version', 'kind', 'subject', 'reviewer', 'key_sha256',
            'issued_at', 'expires_at', 'checks', 'evidence'}
            or type(record['schema_version']) is not int or record['schema_version'] != 1
            or record['kind'] != 'firmavex_release_review_attestation'):
        raise ValueError('Unsupported review attestation')
    pin = record['key_sha256']
    if type(pin) is not str or not re.fullmatch('[0-9a-f]{64}', pin):
        raise ValueError('Invalid review signing key')
    authority = policy['keys'].get(pin)
    if (type(authority) is not dict or set(authority) != {'reviewer', 'checks'}
            or type(authority['reviewer']) is not str or not authority['reviewer']
            or authority['reviewer'] != record['reviewer']
            or type(authority['checks']) is not list
            or any(type(c) is not str or c not in REVIEW_CHECKS for c in authority['checks'])):
        raise ValueError('Untrusted review authority')
    checks = record['checks']
    if (type(checks) is not list or not checks
            or any(type(c) is not str or c not in authority['checks'] for c in checks)
            or len(set(checks)) != len(checks)):
        raise ValueError('Review exceeds signing authority')
    if record['subject'] != subject:
        raise ValueError('Review belongs to a different release manifest')
    evidence = record['evidence']
    if type(evidence) is not dict or set(evidence) != set(checks):
        raise ValueError('Each review requires an evidence identity')
    for identity in evidence.values():
        if (type(identity) is not dict or set(identity) != {'sha256', 'size_bytes'}
                or type(identity['sha256']) is not str
                or not re.fullmatch('[0-9a-f]{64}', identity['sha256'])
                or type(identity['size_bytes']) is not int or identity['size_bytes'] <= 0):
            raise ValueError('Invalid review evidence identity')
    def timestamp(value):
        if type(value) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', value):
            raise ValueError('Review timestamps must be UTC seconds')
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    issued, expires = timestamp(record['issued_at']), timestamp(record['expires_at'])
    current = now or datetime.now(timezone.utc)
    if not issued <= current < expires:
        raise ValueError('Review is expired or not yet valid')
    signed = verify_signature(attestation, signature, public_key, pin)
    if (_identity(attestation) != before or signed['artifact'] != before
            or _identity(manifest) != subject or _identity(trust_policy) != policy_before):
        raise ValueError('Review inputs changed during verification')
    return {'checks': checks, 'reviewer': record['reviewer'], 'subject': subject,
            'attestation': before, 'public_key_der_sha256': pin,
            'evidence': evidence, 'expires_at': record['expires_at']}
