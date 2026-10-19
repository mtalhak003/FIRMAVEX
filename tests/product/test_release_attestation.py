"""Ephemeral review keys test authority boundaries, never publisher approval."""
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

import pytest

from firmavex.product.artifact_signature import message
from firmavex.product.release import _identity
from firmavex.product.release_attestation import verify


@pytest.fixture
def review(tmp_path):
    tool=shutil.which('openssl')
    if not tool:pytest.skip('OpenSSL unavailable')
    private=tmp_path/'TEST-ONLY-private.pem';public=tmp_path/'public.pem'
    subprocess.run([tool,'genpkey','-algorithm','ED25519','-out',str(private)],check=True,capture_output=True)
    subprocess.run([tool,'pkey','-in',str(private),'-pubout','-out',str(public)],check=True,capture_output=True)
    pin=hashlib.sha256(subprocess.check_output([tool,'pkey','-pubin','-in',str(public),'-outform','DER'])).hexdigest()
    manifest=tmp_path/'manifest.json';manifest.write_text('synthetic manifest')
    check='component_license_and_corresponding_source_review'
    policy=tmp_path/'independent-policy.json'
    policy.write_text(json.dumps({'schema_version':1,'keys':{pin:{'reviewer':'Test reviewer','checks':[check]}}}))
    record={'schema_version':1,'kind':'firmavex_release_review_attestation','subject':_identity(manifest),
            'reviewer':'Test reviewer','key_sha256':pin,'issued_at':'2026-01-01T00:00:00Z',
            'expires_at':'2027-01-01T00:00:00Z','checks':[check],
            'evidence':{check:{'sha256':'a'*64,'size_bytes':100}}}
    attestation=tmp_path/'review.json';signature=tmp_path/'review.sig'
    def sign():
        attestation.write_text(json.dumps(record))
        payload=tmp_path/'message';payload.write_bytes(message(attestation))
        subprocess.run([tool,'pkeyutl','-sign','-inkey',str(private),'-rawin','-in',str(payload),'-out',str(signature)],check=True,capture_output=True)
    sign()
    return record,sign,(attestation,signature,public,policy,manifest)


def test_real_review_signature_binds_subject_and_authority(review):
    record,sign,args=review
    now=datetime(2026,6,1,tzinfo=timezone.utc)
    assert verify(*args,now=now)['checks']==record['checks']
    args[-1].write_text('different release')
    with pytest.raises(ValueError,match='different release'):verify(*args,now=now)


@pytest.mark.parametrize('mutation,match',[
    ({'checks':['authentic_artifact_signatures']},'authority'),
    ({'reviewer':'Impersonated reviewer'},'authority'),
    ({'expires_at':'2026-02-01T00:00:00Z'},'expired'),
    ({'issued_at':'2026-12-01T00:00:00Z'},'not yet valid'),
    ({'evidence':{}},'evidence'),
    ({'schema_version':True},'Unsupported'),
])
def test_valid_signature_cannot_override_policy_or_expiry(review,mutation,match):
    record,sign,args=review;record.update(mutation);sign()
    with pytest.raises(ValueError,match=match):verify(*args,now=datetime(2026,6,1,tzinfo=timezone.utc))


def test_tampered_signed_review_is_rejected(review):
    record,sign,args=review
    args[0].write_text(args[0].read_text()+' ')
    with pytest.raises(ValueError,match='signature verification failed'):
        verify(*args,now=datetime(2026,6,1,tzinfo=timezone.utc))


def test_policy_revocation_rejects_previously_signed_review(review):
    _,_,args=review
    args[3].write_text(json.dumps({'schema_version':1,'keys':{}}))
    with pytest.raises(ValueError,match='authority'):
        verify(*args,now=datetime(2026,6,1,tzinfo=timezone.utc))


def test_signed_review_does_not_approve_unsigned_release(review,tmp_path):
    from firmavex.product.release_bundle import create
    from firmavex.product.release_approval import main
    record,sign,args=review
    repo=tmp_path/'repo';repo.mkdir();(repo/'LICENSE').write_text('fixture notice')
    subprocess.run(['git','init','-q',str(repo)],check=True)
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
    sbom=tmp_path/'component-sbom.json'
    sbom.write_text(json.dumps({'schema_version':1,'kind':'firmavex_file_component_sbom',
        'release_approved':False,'legal_approval':False,'git_dirty':False,
        'files':[],'components':{},'unresolved_ownership':[],
        'counts':{'regular_files':0,'verified_ownership':0,'unverified_ownership':0}}))
    bundle=tmp_path/'bundle';create([sbom],repo=repo,output=bundle)
    record['subject']=_identity(bundle/'release-manifest.json')
    # Keep this integration check valid independently of the test execution date.
    record['issued_at']='2020-01-01T00:00:00Z';record['expires_at']='2099-01-01T00:00:00Z';sign()
    output=tmp_path/'assessment.json'
    assert main(['--sbom',str(sbom),'--bundle',str(bundle),'--artifact-dir',str(tmp_path),
        '--output',str(output),'--require-approved','--attestation',str(args[0]),
        '--signature',str(args[1]),'--public-key',str(args[2]),'--trust-policy',str(args[3])])==1
    result=json.loads(output.read_text())
    assert result['checks'][record['checks'][0]]=='passed'
    assert result['checks']['authentic_artifact_signatures']=='not_supplied'
    assert result['release_approved'] is False
