"""Bounded, read-only archive inspection. No extracted member is executed or written."""
import gzip
import hashlib
import io
import lzma
from pathlib import Path, PurePosixPath
import struct
import tarfile
import zipfile
import zlib

MAX_TOTAL = 512 * 1024**2
MAX_MEMBER = 128 * 1024**2
MAX_FILES = 20000
MAX_DEPTH = 2


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name
            or name.startswith('/') or ':' in name or '..' in PurePosixPath(name).parts):
        raise ValueError('Unsafe archive member path')
    return str(PurePosixPath(name))


def _hash(stream, limit):
    digest=hashlib.sha256(); count=0
    while chunk:=stream.read(min(1024**2,limit-count+1)):
        count+=len(chunk)
        if count>limit:raise ValueError('Expanded archive size limit exceeded')
        digest.update(chunk)
    return digest.hexdigest(),count


def _decoded(data, kind):
    if kind=='xz': decoder=lzma.LZMADecompressor(memlimit=256*1024**2)
    else:decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
    output=bytearray();pending=data
    while True:
        chunk=decoder.decompress(pending,max_length=min(1024**2,MAX_TOTAL-len(output)+1))
        output.extend(chunk)
        if len(output)>MAX_TOTAL:raise ValueError('Expanded archive size limit exceeded')
        if decoder.eof:
            if decoder.unused_data:raise ValueError('Concatenated compressed archives unsupported')
            break
        if kind=='xz':
            if decoder.needs_input:raise ValueError('Truncated compressed archive')
            pending=b''
        else:
            pending=decoder.unconsumed_tail
            if not pending:raise ValueError('Truncated compressed archive')
    return bytes(output)


def _tar_preflight(data):
    offset=0;count=0
    while offset+512<=len(data):
        header=data[offset:offset+512];offset+=512
        if header==b'\0'*512:
            if any(data[offset:]):raise ValueError('Nonzero tar trailer')
            return
        info=tarfile.TarInfo.frombuf(header,'utf-8','strict');count+=1
        if count>MAX_FILES or info.size<0 or info.size>MAX_MEMBER:raise ValueError('Tar member limit exceeded')
        if info.type in (tarfile.XHDTYPE,tarfile.XGLTYPE,tarfile.GNUTYPE_LONGNAME,tarfile.GNUTYPE_LONGLINK):
            if info.size>65536:raise ValueError('Tar metadata limit exceeded')
            metadata=data[offset:offset+info.size]
            if b'GNU.sparse' in metadata or b' size=' in metadata:raise ValueError('Tar sparse/size overrides unsupported')
        elif not (info.isfile() or info.isdir() or info.issym()):
            raise ValueError('Unsupported tar entry type')
        offset+=((info.size+511)//512)*512
        if offset>len(data):raise ValueError('Truncated tar member')
    raise ValueError('Missing tar terminator')


def _inspect_bytes(data, name, depth=0):
    if len(data)>MAX_TOTAL or depth>MAX_DEPTH:raise ValueError('Archive inspection limit exceeded')
    lower=name.lower()
    if lower.endswith('.deb'):
        if not data.startswith(b'!<arch>\n'):raise ValueError('Invalid Debian ar archive')
        pos=8;payloads=[];seen=set();members=[];total=0
        while pos<len(data):
            header=data[pos:pos+60];pos+=60
            if len(header)!=60 or header[58:]!=b'`\n':raise ValueError('Invalid ar header')
            member=header[:16].decode('ascii').strip().rstrip('/')
            safe_name(member)
            if member in seen:raise ValueError('Duplicate ar member')
            seen.add(member)
            size=int(header[48:58].strip())
            if not 0<=size<=MAX_TOTAL or pos+size>len(data):raise ValueError('Invalid ar size')
            raw=data[pos:pos+size]
            if member.startswith(('data.tar','control.tar')):
                payloads.append((member,raw))
            elif member=='debian-binary':
                if raw!=b'2.0\n':raise ValueError('Unsupported Debian version')
                members.append({'path':member,'type':'file','sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)})
            else:raise ValueError('Unsupported Debian ar member')
            pos+=size+(size%2)
        if 'debian-binary' not in seen or len([n for n,_ in payloads if n.startswith('data.tar')])!=1 or len([n for n,_ in payloads if n.startswith('control.tar')])!=1:
            raise ValueError('Missing/ambiguous Debian payload')
        statuses=[]
        for member,raw in payloads:
            result=inspect_bytes(raw,member,depth+1);total+=result['expanded_bytes'];statuses.append(result['status'])
            if total>MAX_TOTAL:raise ValueError('Expanded Debian archive limit exceeded')
            members.extend({**value,'path':member+'!/'+value['path']} for value in result['members'])
        return {'status':'inspected_without_extraction' if all(s=='inspected_without_extraction' for s in statuses) else 'unsupported_opaque',
                'members':members,'expanded_bytes':total}
    if lower.endswith(('.tar.xz','.tar.gz','.tgz')):
        data=_decoded(data,'xz' if lower.endswith('.xz') else 'gz');lower='payload.tar'
    entries=[];seen=set();total=0
    def record(member, stream=None, size=0, target=None):
        nonlocal total
        member=safe_name(member)
        if member=='.':return
        if member.casefold() in seen:raise ValueError('Duplicate/colliding archive member')
        seen.add(member.casefold())
        if len(seen)>MAX_FILES:raise ValueError('Archive member count limit exceeded')
        if target is not None:
            import posixpath
            if target.startswith('/') or '\\' in target or ':' in target or '\x00' in target:
                raise ValueError('Unsafe archive link')
            safe_name(posixpath.normpath(str(PurePosixPath(member).parent)+'/'+target))
            entries.append({'path':member,'type':'symlink','target':target});return
        if size<0 or size>MAX_MEMBER:raise ValueError('Archive member size limit exceeded')
        digest,count=_hash(stream,min(MAX_MEMBER,MAX_TOTAL-total))
        if count!=size:raise ValueError('Archive member size mismatch')
        total+=count
        entries.append({'path':member,'type':'file','sha256':digest,'size_bytes':count})
    if lower.endswith('.zip'):
        end=data.rfind(b'PK\x05\x06',max(0,len(data)-65557))
        if end<0 or end+22>len(data):raise ValueError('Missing ZIP directory')
        _,disk,cd_disk,n_disk,n,size,offset,comment=struct.unpack('<4s4H2LH',data[end:end+22])
        if disk or cd_disk or n_disk!=n or n>MAX_FILES or n==65535 or size>32*1024**2 or end+22+comment!=len(data):
            raise ValueError('Unsupported ZIP directory')
        if offset+size!=end:raise ValueError('Unsupported ZIP central directory framing')
        position=offset;actual=0
        while position<end:
            if position+46>end or data[position:position+4]!=b'PK\x01\x02':raise ValueError('Invalid ZIP directory entry')
            length,extra,comment_length=struct.unpack_from('<HHH',data,position+28)
            position+=46+length+extra+comment_length;actual+=1
            if position>end or actual>MAX_FILES or actual>n:raise ValueError('ZIP directory count/size mismatch')
        if actual!=n:raise ValueError('ZIP directory count mismatch')
        zip_names=set()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                canonical_name=safe_name(info.filename).casefold()
                if canonical_name in zip_names:raise ValueError('Duplicate/colliding archive member')
                zip_names.add(canonical_name)
                if info.is_dir():continue
                if (info.external_attr>>16)&0o170000==0o120000 or info.flag_bits&1:
                    raise ValueError('ZIP links/encryption unsupported')
                with archive.open(info) as stream:record(info.filename,stream,info.file_size)
    elif lower.endswith('.tar'):
        _tar_preflight(data)
        with tarfile.open(fileobj=io.BytesIO(data),mode='r|') as archive:
            for info in archive:
                safe_name(info.name)
                if info.isdir():continue
                if info.issym():record(info.name,target=info.linkname)
                elif info.isfile():record(info.name,archive.extractfile(info),info.size)
                else:raise ValueError('Unsupported tar entry')
    else:return {'status':'unsupported_opaque','members':[],'expanded_bytes':0}
    return {'status':'inspected_without_extraction','members':sorted(entries,key=lambda v:v['path']),'expanded_bytes':total}


def inspect_bytes(data, name, depth=0):
    try:return _inspect_bytes(data,name,depth)
    except (tarfile.TarError,zipfile.BadZipFile,lzma.LZMAError,zlib.error,UnicodeError) as exc:
        raise ValueError('Malformed/unsupported archive: '+str(exc)) from exc


def inspect(path):
    from .release import _identity
    path=Path(path);before=_identity(path)
    if before['size_bytes']>MAX_TOTAL:raise ValueError('Archive input size limit exceeded')
    result=inspect_bytes(path.read_bytes(),path.name)
    if _identity(path)!=before:raise ValueError('Archive changed during inspection')
    return {'archive':path.name,'identity':before,**result,'executed_members':False}
