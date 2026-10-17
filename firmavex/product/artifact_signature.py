"""Offline Ed25519 artifact-digest signature verification; not OS code signing."""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from .release import _identity

DOMAIN=b'FIRMAVEX-ARTIFACT-SIGNATURE-v1\0'


def message(artifact):
    identity=_identity(artifact)
    return DOMAIN+bytes.fromhex(identity['sha256'])+struct.pack('>Q',identity['size_bytes'])


def verify(artifact, signature, public_key, trusted_key_sha256, *, openssl=None):
    if not re.fullmatch('[0-9a-f]{64}',trusted_key_sha256):raise ValueError('Pin the SHA-256 of the trusted Ed25519 public key DER')
    tool=openssl or shutil.which('openssl')
    if not tool:raise ValueError('OpenSSL is required for detached signature verification')
    artifact,signature,public_key=map(Path,(artifact,signature,public_key))
    before=[_identity(p) for p in (artifact,signature,public_key)]
    if before[1]['size_bytes']!=64 or before[2]['size_bytes']>16384:raise ValueError('Invalid signature/public-key size')
    result=subprocess.run([str(tool),'pkey','-pubin','-in',str(public_key),'-outform','DER'],capture_output=True,timeout=10)
    der=result.stdout
    if result.returncode or len(der)!=44 or der[:12]!=bytes.fromhex('302a300506032b6570032100'):
        raise ValueError('Expected an Ed25519 public key')
    fingerprint=hashlib.sha256(der).hexdigest()
    if not hmac.compare_digest(fingerprint,trusted_key_sha256):raise ValueError('Untrusted signing public key')
    with tempfile.TemporaryDirectory(prefix='firmavex-signature-') as temp:
        payload=Path(temp)/'message';payload.write_bytes(message(artifact))
        checked=subprocess.run([str(tool),'pkeyutl','-verify','-pubin','-inkey',str(public_key),'-rawin','-in',str(payload),'-sigfile',str(signature)],capture_output=True,timeout=10)
    if checked.returncode:raise ValueError('Artifact signature verification failed')
    if [_identity(p) for p in (artifact,signature,public_key)]!=before:raise ValueError('Signature inputs changed during verification')
    return {'schema_version':1,'verification':'passed','algorithm':'Ed25519',
            'framing':'FIRMAVEX-ARTIFACT-SIGNATURE-v1 + sha256 bytes + uint64 big-endian size',
            'artifact':before[0],'public_key_der_sha256':fingerprint,
            'scope':'detached artifact identity; not Authenticode, Developer ID, notarization, or legal approval'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('message');m.add_argument('artifact',type=Path);m.add_argument('--output',required=True,type=Path)
    v=sub.add_parser('verify');v.add_argument('artifact',type=Path);v.add_argument('--signature',required=True,type=Path)
    v.add_argument('--public-key',required=True,type=Path);v.add_argument('--trusted-key-sha256',required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='message':
            payload=message(args.artifact)
            with args.output.open('xb') as stream:stream.write(payload)
            result={'message_sha256':hashlib.sha256(payload).hexdigest(),'artifact_signed':False}
        else:result=verify(args.artifact,args.signature,args.public_key,args.trusted_key_sha256)
        print(json.dumps(result,sort_keys=True));return 0
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(str(exc),file=__import__('sys').stderr);return 1

if __name__=='__main__':raise SystemExit(main())
