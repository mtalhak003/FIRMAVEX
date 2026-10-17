import io
import lzma
import tarfile
import zipfile
import pytest
from firmavex.product import payload_inventory as p


def zipped(names):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        for name,data in names:archive.writestr(name,data)
    return out.getvalue()


def tarred(name='folder/file',data=b'abc',kind=tarfile.REGTYPE,target=''):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as archive:
        entry=tarfile.TarInfo(name);entry.type=kind;entry.linkname=target
        entry.size=len(data) if kind==tarfile.REGTYPE else 0
        archive.addfile(entry,io.BytesIO(data) if entry.size else None)
    return output.getvalue()


def test_actual_zip_and_tar():
    zip_result=p.inspect_bytes(zipped([('a.pyc',b'abc')]),'library.zip')
    tar_result=p.inspect_bytes(tarred('a.pyc'),'app.tar')
    assert zip_result['members']==tar_result['members']
    assert zip_result['expanded_bytes']==3
    assert p.inspect_bytes(lzma.compress(tarred()),'data.tar.xz')['expanded_bytes']==3


@pytest.mark.parametrize('name',['/absolute','../escape','a/../../escape','C:/escape','a\\escape','a/../same'])
def test_paths_fail_closed(name):
    with pytest.raises(ValueError):p.inspect_bytes(zipped([(name,b'x')]),'a.zip')
    with pytest.raises(ValueError):p.inspect_bytes(tarred(name),'a.tar')


def test_collisions_and_size_limits(monkeypatch):
    with pytest.raises(ValueError,match='colliding'):p.inspect_bytes(zipped([('A',b'a'),('a',b'b')]),'a.zip')
    monkeypatch.setattr(p,'MAX_MEMBER',2)
    with pytest.raises(ValueError,match='size limit'):p.inspect_bytes(zipped([('a',b'abc')]),'a.zip')


def test_tar_links_and_specials():
    assert p.inspect_bytes(tarred('folder/alias',kind=tarfile.SYMTYPE,target='../file'),'a.tar')['members'][0]['target']=='../file'
    with pytest.raises(ValueError):p.inspect_bytes(tarred('alias',kind=tarfile.SYMTYPE,target='../escape'),'a.tar')
    for kind in (tarfile.FIFOTYPE,tarfile.CHRTYPE,tarfile.LNKTYPE):
        with pytest.raises(ValueError):p.inspect_bytes(tarred(kind=kind),'a.tar')


def test_truncated_compression_and_opaque_executable():
    with pytest.raises((ValueError,lzma.LZMAError)):p.inspect_bytes(lzma.compress(tarred())[:-8],'a.tar.xz')
    assert p.inspect_bytes(b'MZnot run','setup.exe')['status']=='unsupported_opaque'


def test_deb_real_ar_framing():
    payload=lzma.compress(tarred())
    def entry(name,data):
        header=(name+'/').ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(data)).ljust(10)+'`\n'
        return header.encode()+data+(b'\n' if len(data)%2 else b'')
    ar=b'!<arch>\n'+entry('debian-binary',b'2.0\n')+entry('control.tar.xz',lzma.compress(tarred('control',b'Package: test\n')))+entry('data.tar.xz',payload)
    assert p.inspect_bytes(ar,'a.deb')['expanded_bytes']==17
    with pytest.raises(ValueError):p.inspect_bytes(ar[:-2],'a.deb')


def test_gzip_bomb_is_bounded(monkeypatch):
    import gzip
    monkeypatch.setattr(p,'MAX_TOTAL',1024)
    compressed=gzip.compress(b'x'*5000)
    with pytest.raises(ValueError,match='size limit'):p.inspect_bytes(compressed,'bomb.tar.gz')


def test_pax_escape_and_sparse_metadata_rejected():
    for fields in ({'path':'../escape'},{'GNU.sparse.name':'file'}):
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w',format=tarfile.PAX_FORMAT) as archive:
            entry=tarfile.TarInfo('file');entry.size=1;entry.pax_headers=fields
            archive.addfile(entry,io.BytesIO(b'x'))
        with pytest.raises(ValueError):p.inspect_bytes(out.getvalue(),'a.tar')


def test_zip_symlink_rejected():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=0o120777<<16
        archive.writestr(entry,'../outside')
    with pytest.raises(ValueError,match='links'):p.inspect_bytes(out.getvalue(),'a.zip')


def test_directory_count_preflight_precedes_zip_index_allocation(monkeypatch):
    import struct
    raw=bytearray(zipped([('one',b'1'),('two',b'2')]))
    end=raw.rfind(b'PK\x05\x06')
    struct.pack_into('<HH',raw,end+8,1,1)
    def must_not_load(*args,**kwargs):raise AssertionError('Malformed directory must fail before loading ZIP index')
    monkeypatch.setattr(p.zipfile,'ZipFile',must_not_load)
    with pytest.raises(ValueError,match='count'):p.inspect_bytes(bytes(raw),'a.zip')


def test_directory_file_collision_is_rejected():
    with pytest.raises(ValueError,match='colliding'):p.inspect_bytes(zipped([('same/',b''),('same',b'file')]),'a.zip')
