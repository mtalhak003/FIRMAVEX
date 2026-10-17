import hashlib
from pathlib import Path
import shutil
import subprocess
import pytest
from firmavex.product.artifact_signature import message,verify,main


def test_real_ed25519_and_tamper(tmp_path):
    tool=shutil.which('openssl')
    if not tool:pytest.skip('Actual OpenSSL unavailable on this host')
    private=tmp_path/'TEST-ONLY-private.pem';public=tmp_path/'public.pem'
    subprocess.run([tool,'genpkey','-algorithm','ED25519','-out',str(private)],check=True,capture_output=True)
    subprocess.run([tool,'pkey','-in',str(private),'-pubout','-out',str(public)],check=True,capture_output=True)
    der=subprocess.check_output([tool,'pkey','-pubin','-in',str(public),'-outform','DER'])
    fingerprint=hashlib.sha256(der).hexdigest()
    artifact=tmp_path/'SYNTHETIC-test-data';artifact.write_bytes(b'not a product installer')
    payload=tmp_path/'message';payload.write_bytes(message(artifact));sig=tmp_path/'signature'
    subprocess.run([tool,'pkeyutl','-sign','-inkey',str(private),'-rawin','-in',str(payload),'-out',str(sig)],check=True,capture_output=True)
    assert verify(artifact,sig,public,fingerprint)['verification']=='passed'
    with pytest.raises(ValueError,match='Untrusted'):verify(artifact,sig,public,'0'*64)
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError,match='verification failed'):verify(artifact,sig,public,fingerprint)


def test_message_is_versioned_and_exclusive(tmp_path):
    artifact=tmp_path/'input';artifact.write_bytes(b'x');output=tmp_path/'message'
    assert message(artifact).startswith(b'FIRMAVEX-ARTIFACT-SIGNATURE-v1\0')
    assert main(['message',str(artifact),'--output',str(output)])==0
    assert main(['message',str(artifact),'--output',str(output)])==1
