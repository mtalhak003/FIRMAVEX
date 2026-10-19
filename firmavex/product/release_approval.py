"""Fail-closed release readiness assessment. Integrity is not release approval."""
import argparse
import base64
import binascii
import subprocess
import json
import hashlib
import re
from pathlib import Path

from .release_bundle import canonical, verify
from firmavex.backends.security import read_json


def license_evidence(components):
    """Check retained notice bytes; this is evidence integrity, not legal review."""
    missing=[];count=0
    for key,component in components.items():
        if type(component) is not dict or type(component.get('notices')) is not list:
            raise ValueError('Invalid component license evidence')
        if not component['notices']:missing.append(key)
        for notice in component['notices']:
            if type(notice) is not dict or notice.get('content_encoding')!='base64':
                raise ValueError('Invalid retained license evidence')
            try:raw=base64.b64decode(notice['content_base64'],validate=True)
            except (KeyError,TypeError,ValueError,binascii.Error) as exc:
                raise ValueError('Invalid retained license bytes') from exc
            if (type(notice.get('size_bytes')) is not int or notice['size_bytes']!=len(raw)
                    or notice.get('sha256')!=hashlib.sha256(raw).hexdigest()):
                raise ValueError('License evidence identity mismatch')
            count+=1
    return {'retained_notices':count,'components_without_notices':missing,
            'legal_approval':False}


def assess(sbom):
    if (type(sbom) is not dict or sbom.get('kind')!='firmavex_file_component_sbom'
            or type(sbom.get('schema_version')) is not int or sbom.get('schema_version')!=1 or sbom.get('release_approved') is not False
            or sbom.get('legal_approval') is not False):
        raise ValueError('Unsupported or self-promoted component inventory')
    files=sbom.get('files');components=sbom.get('components')
    if type(files) is not list or type(components) is not dict or len(files)>50000:
        raise ValueError('Invalid component inventory')
    seen=set();verified=0
    for file in files:
        if not isinstance(file,dict) or type(file.get('path')) is not str or file['path'] in seen:
            raise ValueError('Invalid/duplicate component file')
        seen.add(file['path'])
        if file.get('ownership')=='verified_build_input_lineage':
            if file.get('component_id') not in components or not file.get('evidence'):
                raise ValueError('Missing component lineage evidence')
            component=components[file['component_id']]
            evidence=file['evidence']
            if type(evidence) is not dict:raise ValueError('Invalid component lineage evidence')
            if (hashlib.sha256(canonical(component)).hexdigest()!=file['component_id']
                    or evidence.get('method') not in {'installed_RECORD_sha256_and_packaged_bytes','git_blob_and_packaged_bytes','build_interpreter_path_and_packaged_bytes','dpkg_registration_and_packaged_bytes'}
                    or evidence.get('build_input_sha256')!=file.get('sha256')
                    or not re.fullmatch('[0-9a-f]{64}',str(evidence.get('toc_sha256','')))):
                raise ValueError('Invalid component lineage evidence')
            verified+=1
        elif file.get('ownership')!='unverified':raise ValueError('Unknown ownership classification')
    counts={'regular_files':len(files),'verified_ownership':verified,'unverified_ownership':len(files)-verified}
    if type(sbom.get('counts')) is not dict or any(type(v) is not int for v in sbom['counts'].values()) or sbom.get('counts')!=counts or len(sbom.get('unresolved_ownership',[]))!=counts['unverified_ownership']:
        raise ValueError('Contradictory ownership accounting')
    licenses=license_evidence(components)
    checks={'license_evidence_integrity':'passed' if not licenses['components_without_notices'] else 'failed',
            'source_checkout_clean':'passed' if sbom.get('git_dirty') is False else 'failed',
            'collected_file_ownership':'passed' if not counts['unverified_ownership'] else 'failed',
            'component_license_and_corresponding_source_review':'external_approval_missing',
            'embedded_executable_and_installer_composition':'incomplete',
            'authentic_artifact_signatures':'not_supplied',
            'physical_consumer_acceptance':'external_evidence_missing',
            'versioned_installer_lifecycle':'separate_qualification_required'}
    return {'schema_version':1,'kind':'firmavex_release_approval','release_approved':False,
            'checks':checks,'counts':counts,'license_evidence':licenses,'scope':'Proofs missing; no automatic promotion from hashes or self-reported booleans',
            'blockers':[name for name,value in checks.items() if value!='passed']}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sbom',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--artifact-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--require-approved',action='store_true')
    p.add_argument('--attestation',type=Path);p.add_argument('--signature',type=Path)
    p.add_argument('--public-key',type=Path);p.add_argument('--trust-policy',type=Path)
    args=p.parse_args(argv)
    try:
        from .release import _identity
        manifest_before=_identity(args.bundle/'release-manifest.json')
        sbom_before=_identity(args.sbom)
        integrity=verify(args.bundle,args.artifact_dir)
        sbom=read_json(args.sbom,64*1024**2)
        # The exact SBOM must be bound by the verified artifact manifest.
        manifest=read_json(args.bundle/'release-manifest.json')
        from .release import _identity
        if manifest['artifacts'].get(args.sbom.name)!=_identity(args.sbom):
            raise ValueError('SBOM is not bound by verified release manifest')
        result={**assess(sbom),'integrity':integrity}
        review_args=(args.attestation,args.signature,args.public_key,args.trust_policy)
        if any(review_args):
            if not all(review_args):raise ValueError('Review requires attestation, signature, public key and independent trust policy')
            from .release_attestation import verify as verify_review
            review=verify_review(*review_args,args.bundle/'release-manifest.json')
            result['verified_review']=review
            for check in review['checks']:result['checks'][check]='passed'
            result['blockers']=[name for name,value in result['checks'].items() if value!='passed']
        if (_identity(args.sbom)!=sbom_before
                or _identity(args.bundle/'release-manifest.json')!=manifest_before):
            raise ValueError('Release evidence changed during assessment')
        # Detached reviews cannot establish authentic installer signatures.
        result['release_approved']=not result['blockers']
        with args.output.open('xb') as stream:stream.write(canonical(result))
        print(json.dumps(result,sort_keys=True))
        import os
        if args.require_approved and not result['release_approved'] and os.environ.get('GITHUB_ACTIONS')=='true':
            print('::error title=Release approval blocked::'+', '.join(result['blockers']),flush=True)
        return 1 if args.require_approved and not result['release_approved'] else 0
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(str(exc),file=__import__('sys').stderr);return 1

if __name__=='__main__':raise SystemExit(main())
