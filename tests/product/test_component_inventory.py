import hashlib
from pathlib import Path
import subprocess
import pytest
from firmavex.product import component_inventory as c
from firmavex.product.release_approval import assess


def repo(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'LICENSE').write_text('MIT test fixture')
    (tmp_path/'asset').write_bytes(b'known bytes')
    subprocess.run(['git','-C',str(tmp_path),'add','.'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
    return tmp_path


def test_actual_git_blob_lineage_and_mutated_input(tmp_path,monkeypatch):
    source=repo(tmp_path/'repo')
    app=tmp_path/'app';app.mkdir();(app/'asset').write_bytes(b'known bytes')
    toc=tmp_path/'toc';toc.write_text(repr(([('asset',str(source/'asset'),'DATA')],)))
    monkeypatch.setattr(c,'python_owners',lambda:{})
    monkeypatch.setattr(c,'_os_owner',lambda source:None)
    result=c.audit(app,toc=toc,repo=source)
    assert result['counts']=={'regular_files':1,'verified_ownership':1,'unverified_ownership':0}
    assert result['files'][0]['evidence']['method']=='git_blob_and_packaged_bytes'
    assert assess(result)['release_approved'] is False
    (source/'asset').write_bytes(b'new bytes')
    assert c.audit(app,toc=toc,repo=source)['counts']['unverified_ownership']==1


def test_registered_record_must_match_actual_bytes(tmp_path,monkeypatch):
    import base64
    source=repo(tmp_path/'repo');external=tmp_path/'external';external.write_bytes(b'known bytes')
    app=tmp_path/'app';app.mkdir();(app/'file').write_bytes(b'known bytes')
    toc=tmp_path/'toc';toc.write_text(repr(([('file',str(external),'DATA')],)))
    digest=base64.urlsafe_b64encode(hashlib.sha256(b'known bytes').digest()).decode().rstrip('=')
    component={'name':'Test dependency','version':'1','notices':[]}
    monkeypatch.setattr(c,'python_owners',lambda:{str(external):[(component,digest)]})
    assert c.audit(app,toc=toc,repo=source)['counts']['verified_ownership']==1
    monkeypatch.setattr(c,'python_owners',lambda:{str(external):[(component,digest),({**component,'name':'Other'},digest)]})
    assert c.audit(app,toc=toc,repo=source)['counts']['verified_ownership']==0


def test_source_hardlinks_are_read_only(tmp_path):
    import os
    path=tmp_path/'source';path.write_bytes(b'bytes')
    os.link(path,tmp_path/'alias')
    assert c.source_identity(path)['sha256']==hashlib.sha256(b'bytes').hexdigest()


def test_toc_is_literal_data_and_bounded(tmp_path,monkeypatch):
    toc=tmp_path/'toc';toc.write_text("__import__('os').system('false')")
    with pytest.raises(ValueError):c.toc_rows(toc)
    toc.write_text(repr(([('x','/tmp/x','DATA')],)))
    assert c.toc_rows(toc)[0][0][0]=='x'


def test_gate_rejects_forged_counts_and_approval():
    base={'schema_version':1,'kind':'firmavex_file_component_sbom','release_approved':False,
          'legal_approval':False,'files':[],'components':{},'unresolved_ownership':[],
          'counts':{'regular_files':0,'verified_ownership':0,'unverified_ownership':0}}
    assert assess(base)['release_approved'] is False
    for field,value in [('release_approved',True),('legal_approval',True),('counts',{})]:
        with pytest.raises(ValueError):assess({**base,field:value})


def test_mid_audit_registered_owner_change_fails(tmp_path,monkeypatch):
    source=repo(tmp_path/'repo');app=tmp_path/'app';app.mkdir();(app/'asset').write_bytes(b'known bytes')
    toc=tmp_path/'toc';toc.write_text(repr(([('asset',str(source/'asset'),'DATA')],)))
    calls=[]
    def owners():
        calls.append(1)
        return {} if len(calls)==1 else {'new_registration':[]}
    monkeypatch.setattr(c,'python_owners',owners)
    with pytest.raises(ValueError,match='ownership changed'):c.audit(app,toc=toc,repo=source)


def test_license_evidence_retains_exact_original_bytes(tmp_path):
    import base64
    path=tmp_path/'COPYRIGHT';raw=b'License text: \xff\x00\n';path.write_bytes(raw)
    notice=c.license_notice(path,'COPYRIGHT')
    assert base64.b64decode(notice['content_base64'])==raw
    assert notice['sha256']==hashlib.sha256(raw).hexdigest()


def test_actual_bound_sbom_requires_nonzero_approval_exit(tmp_path):
    from firmavex.product.release_bundle import create
    from firmavex.product.release_approval import main
    import json
    source=repo(tmp_path/'repo')
    sbom=tmp_path/'component-sbom.json'
    data={'schema_version':1,'kind':'firmavex_file_component_sbom','release_approved':False,
          'legal_approval':False,'files':[],'components':{},'unresolved_ownership':[],
          'counts':{'regular_files':0,'verified_ownership':0,'unverified_ownership':0}}
    sbom.write_text(json.dumps(data))
    create([sbom],repo=source,output=tmp_path/'bundle')
    output=tmp_path/'approval.json'
    args=['--sbom',str(sbom),'--bundle',str(tmp_path/'bundle'),'--artifact-dir',str(tmp_path),'--output',str(output),'--require-approved']
    assert main(args)==1
    record=json.loads(output.read_text())
    assert record['release_approved'] is False
    assert 'component_license_and_corresponding_source_review' in record['blockers']


def test_git_changes_during_initial_file_capture_are_rejected(tmp_path,monkeypatch):
    source=repo(tmp_path/'repo');app=tmp_path/'app';app.mkdir();(app/'asset').write_bytes(b'known bytes')
    toc=tmp_path/'toc';toc.write_text(repr(([('asset',str(source/'asset'),'DATA')],)))
    original=c.capture;calls=[]
    def changing(path):
        result=original(path);calls.append(1)
        if len(calls)==1:(source/'new-untracked-file').write_text('observed change')
        return result
    monkeypatch.setattr(c,'capture',changing)
    monkeypatch.setattr(c,'python_owners',lambda:{})
    with pytest.raises(ValueError,match='provenance changed'):c.audit(app,toc=toc,repo=source)


def test_windows_toc_destinations_match_posix_inventory_paths(tmp_path,monkeypatch):
    source=repo(tmp_path/'repo')
    app=tmp_path/'app';(app/'_internal'/'notices').mkdir(parents=True)
    (app/'_internal'/'notices'/'asset').write_bytes(b'known bytes')
    toc=tmp_path/'toc';toc.write_text(repr(([('notices\\asset',str(source/'asset'),'DATA')],)))
    monkeypatch.setattr(c,'python_owners',lambda:{})
    monkeypatch.setattr(c,'_os_owner',lambda source:None)
    result=c.audit(app,toc=toc,repo=source)
    assert result['counts']=={'regular_files':1,'verified_ownership':1,'unverified_ownership':0}
    assert result['files'][0]['path']=='_internal/notices/asset'
    assert result['files'][0]['evidence']['method']=='git_blob_and_packaged_bytes'
