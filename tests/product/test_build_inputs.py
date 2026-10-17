"""Offline integrity checks for reviewed immutable CI inputs."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def test_actions_are_immutable_and_catalogued():
    pins = json.loads((ROOT/'packaging/action-pins.json').read_text())['actions']
    observed=set()
    for workflow in (ROOT/'.github/workflows').glob('*.yml'):
        for action, ref in re.findall(r'uses:\s*([\w-]+/[\w-]+)@([^\s]+)',workflow.read_text()):
            assert action in pins, (workflow,action)
            assert re.fullmatch('[0-9a-f]{40}',ref), (workflow,ref)
            assert ref==pins[action]['commit']
            observed.add(action)
    assert observed==set(pins)


def test_build_lock_exact_hashes_and_platform_dependencies():
    text=(ROOT/'packaging/build-requirements.lock').read_text()
    requirements=text.replace('\\\n','').splitlines()
    names=[]
    for line in requirements:
        if not line or line.startswith('#'):continue
        assert re.match(r'[\w-]+==[\w.]+',line)
        assert re.findall(r'--hash=sha256:[0-9a-f]{64}(?=\s|$)',line)
        assert not re.search(r'https?://|--extra-index|--trusted-host',line)
        names.append(line.split('==')[0].lower())
    assert len(names)==len(set(names))
    assert {'pyside6','shiboken6','pyinstaller','pefile','macholib','colorama'}<=set(names)


def test_build_dependency_drift_rejected(tmp_path,monkeypatch):
    import pytest
    from tools import check_build_inputs
    lock=tmp_path/'lock'
    lock.write_text('example==1.2 --hash=sha256:'+'a'*64+'\n')
    monkeypatch.setattr(check_build_inputs.metadata,'version',lambda name:'1.2')
    assert check_build_inputs.check(lock)['verification']=='passed'
    monkeypatch.setattr(check_build_inputs.metadata,'version',lambda name:'1.3')
    with pytest.raises(ValueError,match='drift'):check_build_inputs.check(lock)


def test_platform_markers_and_empty_lock(tmp_path,monkeypatch):
    import pytest
    from tools import check_build_inputs
    lock=tmp_path/'lock'
    lock.write_text('missing==1 ; python_version < "1" --hash=sha256:'+'a'*64+'\n')
    with pytest.raises(ValueError,match='Empty'):check_build_inputs.check(lock)


def test_product_version_is_consistent():
    import tomllib
    from firmavex import __version__
    project=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert project['project']['version']==__version__=='0.3.0.dev2'
    assert 'AppVersion='+__version__.replace('.dev','-dev') in (ROOT/'packaging/windows.iss').read_text()


def test_cli_reports_actual_product_version(capsys):
    import pytest
    from firmavex.product.cli import parser
    with pytest.raises(SystemExit) as stopped:parser().parse_args(['--version'])
    assert stopped.value.code==0
    assert capsys.readouterr().out.strip()=='FIRMAVEX 0.3.0.dev2'
