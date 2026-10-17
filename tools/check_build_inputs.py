"""Fail closed on lock/version drift in the active build environment (offline)."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
from packaging.requirements import Requirement


def check(path):
    text=Path(path).read_text(encoding='utf-8').replace('\\\n','')
    expected={}
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'): continue
        requirement=Requirement(line.split('--hash=')[0].strip())
        if requirement.marker and not requirement.marker.evaluate(): continue
        if len(requirement.specifier)!=1 or next(iter(requirement.specifier)).operator!='==':
            raise ValueError('Build requirements must be exact versions')
        expected[requirement.name]=str(next(iter(requirement.specifier)).version)
    if not expected: raise ValueError('Empty build lock')
    observed={}
    for name,version in sorted(expected.items()):
        actual=metadata.version(name)
        if actual!=version: raise ValueError(f'Build dependency drift: {name}: expected {version}, observed {actual}')
        observed[name]=actual
    return {'schema_version':1,'verification':'passed','locked_versions':observed,
            'scope':'expected_versions; installation hashes enforced by pip --require-hashes, not inferred from versions'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock',default='packaging/build-requirements.lock')
    args=parser.parse_args(argv)
    try: print(json.dumps(check(args.lock),sort_keys=True)); return 0
    except (OSError,ValueError,metadata.PackageNotFoundError) as exc:
        print(str(exc),file=__import__('sys').stderr);return 1

if __name__=='__main__':raise SystemExit(main())
