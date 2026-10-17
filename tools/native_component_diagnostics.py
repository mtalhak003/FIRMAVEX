"""Read-only native build evidence. No unknown file is promoted by this diagnostic."""
import argparse
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
    for row in diagnostics:
        message=json.dumps(row,sort_keys=True)
        print('::notice title=Unresolved native file::'+message[:3500].replace('%','%25').replace('\n','%0A').replace('\r','%0D'))
    print(json.dumps({'counts':result['counts'],'unresolved':len(diagnostics)}))

if __name__=='__main__':main()
