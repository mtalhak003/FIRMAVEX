"""Evidence-backed collected-file lineage, with separate legal release blockers.

A verified mapping establishes byte identity to a recorded build input and its
registered owner. It does not establish authenticity of an upstream publisher,
license compatibility, complete embedded composition, or legal clearance.
"""
import argparse
import ast
import base64
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import sysconfig

from .frozen_inventory import capture
from .payload_inventory import inspect
from .release import _identity, _git
from .file_state import path_state, handle_state
from .release_bundle import canonical, notice_identity


def toc_rows(path):
    path=Path(path)
    if path.stat().st_size>32*1024**2:raise ValueError('Build TOC exceeds limit')
    raw=path.read_bytes()
    tree=ast.parse(raw,mode='eval')
    for count,node in enumerate(ast.walk(tree)):
        if count>500000:raise ValueError('Build TOC structure exceeds limit')
    value=ast.literal_eval(tree)
    rows=[]
    def visit(value,depth=0):
        if depth>24:raise ValueError('Build TOC nesting exceeds limit')
        if isinstance(value,(tuple,list)):
            if len(value)==3 and all(type(v) is str for v in value) and value[2] in {'DATA','BINARY','EXTENSION','EXECUTABLE'}:
                # TOCs use host separators; collected inventory paths are POSIX.
                rows.append((value[0].replace('\\','/'),value[1],value[2]));return
            for member in value:visit(member,depth+1)
    visit(value)
    if not rows:raise ValueError('No supported build TOC entries')
    if path.read_bytes()!=raw:raise ValueError('Build TOC changed during inspection')
    return rows,hashlib.sha256(raw).hexdigest()


def license_notice(path, name):
    path=Path(path).resolve(strict=True)
    identity=notice_identity(path)
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=identity['sha256'] or notice_identity(path)!=identity:
        raise ValueError('License evidence changed during capture')
    return {'name':name,**identity,'content_encoding':'base64',
            'content_base64':base64.b64encode(raw).decode('ascii'),
            'delivery_scope':'SBOM evidence; installed notice coverage requires review'}


def source_identity(path):
    """Read-only package inputs may be package-manager hardlinks."""
    before=path_state(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size>2*1024**3:
        raise ValueError('Unsupported build input')
    with path.open('rb') as stream:
        if handle_state(stream.fileno())!=before:raise ValueError('Build input changed')
        values=[]
        for _ in range(2):
            stream.seek(0);digest=hashlib.sha256();count=0
            while chunk:=stream.read(1024**2):
                count+=len(chunk)
                if count>2*1024**3:raise ValueError('Build input exceeds limit')
                digest.update(chunk)
            values.append((digest.hexdigest(),count))
            if handle_state(stream.fileno())!=before:raise ValueError('Build input changed')
    if values[0]!=values[1] or path_state(path)!=before:raise ValueError('Build input changed')
    return {'sha256':values[0][0],'size_bytes':values[0][1]}


def python_owners():
    index={}
    for dist in metadata.distributions():
        name=dist.metadata.get('Name');version=dist.version
        if not name or not version:continue
        notices=[]
        for file in dist.files or []:
            spelling=str(file).replace('\\','/')
            if '.dist-info/' in spelling and ('/licenses/' in spelling.lower() or Path(spelling).name.lower().startswith(('license','copying','notice'))):
                notices.append(license_notice(dist.locate_file(file),spelling))
        component={'name':name,'version':version,'origin':'installed_python_distribution',
                   'declared_license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                   'notices':sorted(notices,key=lambda n:n['name']),'legal_review':'required','corresponding_source_review':'required'}
        for file in dist.files or []:
            digest=getattr(file,'hash',None)
            if digest and digest.mode=='sha256':
                key=str(Path(dist.locate_file(file)).resolve())
                entry=(component,digest.value)
                if entry not in index.setdefault(key,[]):index[key].append(entry)
    return index


def registered_stdlib_source(source):
    name=source.name.split('.',1)[0]
    if name not in sys.stdlib_module_names:return False
    try:spec=importlib.util.find_spec(name)
    except (ImportError,ValueError):return False
    return spec is not None and spec.origin not in (None,'built-in','frozen') and Path(spec.origin).resolve()==source.resolve()


def _os_owner(source):
    if not sys.platform.startswith('linux'):return None
    spellings=[str(source),str(source.resolve())]
    if str(source.resolve()).startswith('/usr/lib/'):
        spellings.append(str(source.resolve()).replace('/usr/lib/','/lib/',1))
    for spelling in dict.fromkeys(spellings):
        result=subprocess.run(['dpkg-query','-S',spelling],capture_output=True,text=True,timeout=10)
        if result.returncode:continue
        matches=[]
        for line in result.stdout.splitlines():
            package,separator,path=line.rpartition(': ')
            if separator and path==spelling and not package.startswith('diversion'):matches.append(package)
        if len(matches)!=1:continue
        package=matches[0]
        result=subprocess.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}',package],capture_output=True,text=True,timeout=10,check=True)
        fields=result.stdout.split('\t')
        if len(fields)!=4:raise ValueError('Invalid OS package metadata')
        notice=Path('/usr/share/doc')/package.split(':')[0]/'copyright'
        return {'name':fields[0],'version':fields[1],'source_package':fields[2],
                'source_version':fields[3],'origin':'installed_dpkg_registration',
                'notices':[license_notice(notice,'copyright')] if notice.is_file() else [],
                'declared_license':None,'legal_review':'required','corresponding_source_review':'required'}
    return None


def audit(application, *, toc, repo, archives=()):
    application=Path(application).resolve(strict=True);repo=Path(repo).resolve(strict=True)
    git_before=_git(repo)
    revision=git_before[0]
    inventory=capture(application)
    rows,toc_hash=toc_rows(toc)
    python_index=python_owners()
    from firmavex import __version__
    firstparty={'name':'FIRMAVEX','version':__version__,'origin':'git_tracked_source',
                'declared_license':'MIT','notices':[license_notice(repo/'LICENSE','LICENSE')],
                'legal_review':'required','corresponding_source_review':'required'}
    stdlib=Path(sysconfig.get_path('stdlib')).resolve()
    libdir=Path(sysconfig.get_config_var('LIBDIR') or sys.base_prefix)
    library_names={str(sysconfig.get_config_var('LDLIBRARY') or ''),str(sysconfig.get_config_var('INSTSONAME') or ''), 'python'+str(sys.version_info.major)+str(sys.version_info.minor)+'.dll'}
    libraries={str((directory/name).resolve()) for directory in (libdir,Path(sys.base_prefix)/'lib',Path(sys.base_prefix)) for name in library_names if name}
    components={};files=[];unresolved=[];archive_records=[];source_proofs={}
    def component_id(component):
        key=hashlib.sha256(canonical(component)).hexdigest()
        components[key]=component
        return key
    for record in inventory['files']:
        if record['type']!='file':continue
        name=record['path'];entry={**record,'ownership':'unverified','component_id':None,'evidence':None}
        candidates=[r for r in rows if name==r[0] or name=='_internal/'+r[0] or name.endswith('/Frameworks/'+r[0]) or name.endswith('/Resources/'+r[0])]
        verified=[]
        for dest,source,kind in candidates:
            source=Path(source).resolve(strict=True)
            if not source.is_file():continue
            identity=source_identity(source)
            if identity!={k:record[k] for k in ('sha256','size_bytes')}:continue
            component=None;method=None
            registered=python_index.get(str(source.resolve()))
            encoded=base64.urlsafe_b64encode(bytes.fromhex(identity['sha256'])).decode().rstrip('=')
            matching={canonical(c):c for c,h in (registered or []) if h==encoded}
            if len(matching)>1:continue
            if matching:
                component,method=next(iter(matching.values())),'installed_RECORD_sha256_and_packaged_bytes'
            elif source.resolve().is_relative_to(repo):
                relative=source.resolve().relative_to(repo).as_posix()
                original=subprocess.run(['git','-C',str(repo),'show',revision+':'+relative],capture_output=True,timeout=10)
                if original.returncode==0 and hashlib.sha256(original.stdout).hexdigest()==identity['sha256']:
                    component,method=firstparty,'git_blob_and_packaged_bytes'
                    if relative.startswith('packaging/licenses/'):
                        component={**firstparty,'name':'FIRMAVEX curated third-party notices','declared_license':None,'origin':'git_tracked_upstream_notice_copy_not_relicensed'}
            if component is None and (str(source.resolve()) in libraries or
                    registered_stdlib_source(source)):
                component={'name':'CPython','version':sys.version.split()[0],'origin':'executing_build_interpreter',
                           'declared_license':'PSF; bundled dependencies require independent review',
                           'notices':[license_notice(repo/'packaging/licenses/Python-LICENSE.txt','packaged Python notice; applicable-build review required')] if (repo/'packaging/licenses/Python-LICENSE.txt').is_file() else [],'legal_review':'required','corresponding_source_review':'required'}
                method='build_interpreter_path_and_packaged_bytes'
            if component is None:
                try:component=_os_owner(source)
                except FileNotFoundError:component=None
                if component is not None:method='dpkg_registration_and_packaged_bytes'
            if component is not None:
                source_proofs[source]=(identity,component,method)
                verified.append((component,{'method':method,'build_input_sha256':identity['sha256'],'build_input_name':source.name,'toc_sha256':toc_hash}))
        unique={canonical(v[0]):v for v in verified}
        if len(unique)==1:
            component,evidence=next(iter(unique.values()))
            entry.update(ownership='verified_build_input_lineage',component_id=component_id(component),evidence=evidence)
        else:unresolved.append({'path':name,'reason':'ambiguous_owner' if unique else 'no_byte_verified_registered_owner'})
        files.append(entry)
        if name.endswith('.zip'):archive_records.append(inspect(application/name))
    for archive in archives:archive_records.append(inspect(archive))
    # All mappings are revalidated against actual application bytes. No review
    # conclusion can be promoted automatically by a successful hash match.
    if capture(application)!=inventory:raise ValueError('Application changed during component audit')
    if toc_rows(toc)[1]!=toc_hash or _git(repo)!=git_before:
        raise ValueError('Build provenance changed during audit')
    if python_owners()!=python_index:raise ValueError('Registered Python ownership changed during audit')
    for source,(identity,component,method) in source_proofs.items():
        if source_identity(source)!=identity:raise ValueError('Build input changed during audit')
        if method=='dpkg_registration_and_packaged_bytes' and _os_owner(source)!=component:
            raise ValueError('Registered OS ownership changed during audit')
    by_hash={}
    for entry in files:
        if entry['component_id'] is not None:by_hash.setdefault(entry['sha256'],set()).add(entry['component_id'])
    archive_verified=archive_unverified=0
    for archive in archive_records:
        for member in archive['members']:
            if member['type']!='file':continue
            owners=by_hash.get(member['sha256'],set())
            member['component_id']=next(iter(owners)) if len(owners)==1 else None
            member['ownership']='verified_collected_bytes' if len(owners)==1 else 'unverified'
            if len(owners)==1:archive_verified+=1
            else:archive_unverified+=1
    return {'schema_version':1,'kind':'firmavex_file_component_sbom','git_revision':revision,
            'scope':'collected bytes to registered build inputs; not publisher authenticity or legal clearance',
            'git_dirty':bool(git_before[1]),'tracked_diff_sha256':git_before[2],
            'consistency':{'status':'stable_observed','atomic':False},
            'files':files,'components':components,'archives':archive_records,'unresolved_ownership':unresolved,
            'counts':{'regular_files':len(files),'verified_ownership':len(files)-len(unresolved),'unverified_ownership':len(unresolved)},
            'archive_counts':{'verified_members':archive_verified,'unverified_members':archive_unverified},
            'legal_approval':False,'release_approved':False,
            'blockers':['Independent component/license and corresponding-source review required',
                        'Opaque embedded executable/PYZ composition not fully expanded']+(['Unresolved collected-file ownership'] if unresolved else [])}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('application',type=Path)
    p.add_argument('--toc',required=True,type=Path);p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--archive',action='append',default=[],type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args(argv)
    try:
        if args.output.resolve().is_relative_to(args.application.resolve()):raise ValueError('Audit output must be outside application')
        result=audit(args.application,toc=args.toc,repo=args.repo,archives=args.archive)
        with args.output.open('xb') as stream:stream.write(canonical(result))
        summary={'counts':result['counts'],'archive_counts':result['archive_counts'],'git_revision':result['git_revision'], 'sbom_sha256':hashlib.sha256(canonical(result)).hexdigest(),'release_approved':False}
        print(json.dumps(summary))
        if os.environ.get('GITHUB_ACTIONS')=='true':print('::notice title=Component ownership audit::'+json.dumps(summary),flush=True)
        return 0
    except (OSError,ValueError,SyntaxError,subprocess.SubprocessError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
