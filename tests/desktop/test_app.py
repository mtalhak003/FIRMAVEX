"""Desktop startup and command boundaries, without guest execution."""
import os
from pathlib import Path
import subprocess
import sys
import pytest
from firmavex.desktop.app import main
from firmavex.product.cli import main as cli_main


def test_desktop_help_is_available_without_qt_initialization(capsys):
    with pytest.raises(SystemExit) as caught: main(['--help'])
    assert caught.value.code==0
    assert '--project' in capsys.readouterr().out


def test_unknown_arguments_do_not_silently_start_gui(capsys):
    with pytest.raises(SystemExit) as caught: main(['--unsupported-flag'])
    assert caught.value.code==2


def test_linux_without_display_reports_setup_requirement(monkeypatch,capsys):
    monkeypatch.setattr(sys,'platform','linux')
    for key in ('DISPLAY','WAYLAND_DISPLAY','QT_QPA_PLATFORM'): monkeypatch.delenv(key,raising=False)
    assert main([])==2
    assert 'WSLg' in capsys.readouterr().err


def test_optional_desktop_command_forwards_selected_project_and_smoke(monkeypatch):
    calls=[]
    monkeypatch.setattr('firmavex.desktop.app.main',lambda args:calls.append(args) or 0)
    assert cli_main(['desktop','--project','/synthetic/project','--smoke-test'])==0
    assert calls==[['--project','/synthetic/project','--smoke-test']]


@pytest.mark.parametrize('module,arguments',[('firmavex.desktop.app',['--smoke-test']),('firmavex',['desktop','--smoke-test'])])
def test_actual_gui_widget_start_and_close_without_firmware(module,arguments,tmp_path):
    environment=os.environ.copy()
    environment['QT_QPA_PLATFORM']='offscreen'
    environment['XDG_DATA_HOME']=str(tmp_path/'data')
    result=subprocess.run([sys.executable,'-m',module,*arguments],env=environment,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    assert not (tmp_path/'data').exists()
