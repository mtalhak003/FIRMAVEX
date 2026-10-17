"""Read-only native build evidence. No unknown file is promoted by this diagnostic."""
import argparse
import base64
import zlib
import hashlib
import json
from pathlib import Path
from firmavex.product.component_inventory import audit,toc_rows,source_identity
from firmavex.product.release_bundle import canonical


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('application',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    result=audit(a.application,toc='build/desktop/COLLECT-00.toc',repo='.')
    (a.output/'baseline-component-sbom.json').write_bytes(canonical(result))
    rows=[]
    for toc in sorted(Path('build/desktop').glob('*.toc')):
        try:entries,digest=toc_rows(toc)
        except (ValueError,SyntaxError):continue
        rows.extend((str(toc),digest,*row) for row in entries)
    diagnostics=[]
    for entry in result['unresolved_ownership']:
        path=entry['path'];actual=source_identity(a.application/path)
        candidates=[]
        for toc,digest,dest,src,kind in rows:
            if (path==dest or path=='_internal/'+dest or path.endswith('/'+dest)
                    or Path(path).name==Path(dest).name):
                source=Path(src)
                if source.is_file():
                    identity=source_identity(source)
                    candidates.append({'toc':toc,'dest':dest,'source':str(source),'kind':kind,'matches_bytes':identity==actual,'identity':identity})
        diagnostics.append({'path':path,'identity':actual,'candidates':candidates})
    (a.output/'unresolved-build-evidence.json').write_bytes(canonical(diagnostics))
    # Public annotations are bounded so diagnostics remain accessible even when
    # authenticated artifact/log download is unavailable. No credentials recorded.
    print('::notice title=Baseline component counts::'+json.dumps(result['counts']))
    raw=canonical(diagnostics);encoded=base64.b64encode(zlib.compress(raw,9)).decode('ascii')
    chunks=[encoded[i:i+2800] for i in range(0,len(encoded),2800)]
    if len(chunks)>8:raise ValueError('Diagnostic annotation size exceeded; artifact retained')
    for index,chunk in enumerate(chunks):
        print('::notice title=Compressed native diagnostic::'+json.dumps({'kind':'firmavex_native_diagnostic_zlib_base64','index':index,'count':len(chunks),'sha256':hashlib.sha256(raw).hexdigest(),'data':chunk}))
    print(json.dumps({'counts':result['counts'],'unresolved':len(diagnostics)}))

if __name__=='__main__':main()
