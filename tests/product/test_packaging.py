"""Validate distributable contents and imports outside the source checkout."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

import elftools
import pytest


REPOSITORY = Path(__file__).resolve().parents[2]


def _run(command, *, cwd, timeout=120, check=True):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, text=True,
        check=check, timeout=timeout,
    )


@pytest.fixture(scope="module")
def distributions(tmp_path_factory):
    working = tmp_path_factory.mktemp("package outside checkout")
    source = working / "source"
    source.mkdir()
    for name in ("pyproject.toml", "MANIFEST.in", "README.md", "LICENSE"):
        shutil.copy2(REPOSITORY / name, source / name)
    for name in ("firmavex", "src", "firmware", "docs", "tests"):
        shutil.copytree(
            REPOSITORY / name, source / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.elf", "*.bin", "*.exe"),
        )
    output = working / "distributions"
    output.mkdir()
    _run(
        [sys.executable, "-B", "-c",
         "import setuptools.build_meta as b,sys; destination=sys.argv[1]; b.build_wheel(destination); b.build_sdist(destination)",
         str(output)], cwd=source,
    )
    return working, next(output.glob("*.whl")), next(output.glob("*.tar.gz"))


def test_wheel_contains_product_and_single_legacy_namespace(distributions):
    _, wheel, _ = distributions
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert "firmavex/__init__.py" in names
    assert "firmavex/product/cli.py" in names
    assert "firmavex/desktop/app.py" in names
    assert "firmavex/desktop/window.py" in names
    assert "firmavex/product/windows_job.py" in names
    assert "src/firmavex/evaluation/api.py" in names
    assert "firmavex/evaluation/api.py" not in names
    assert "firmware/benchmarks/cortex_m/startup.c" in names
    assert "firmware/benchmarks/cortex_m/linker.ld" in names
    assert "firmware/benchmarks/cortex_m/corpus/manifest.json" in names
    assert "firmware/benchmarks/cortex_m/corpus_v2/manifest.json" in names
    assert "firmavex/product/resources/example/main.c" in names
    assert "firmavex/product/resources/example/startup.c" in names
    assert "firmavex/product/resources/example/linker.ld" in names
    assert not any(name.startswith("tests/") for name in names)
    assert not any("ground_truth" in name for name in names)
    assert not any(Path(name).suffix.lower() in {".elf", ".bin", ".exe", ".pyc", ".db", ".sqlite3"} for name in names)
    assert not any("__pycache__" in name or "/.git/" in name for name in names)


def test_sdist_contains_build_inputs_and_product_tests(distributions):
    _, _, source = distributions
    with tarfile.open(source) as archive:
        names = {"/".join(Path(name).parts[1:]) for name in archive.getnames()}
    assert "pyproject.toml" in names
    assert "docs/product/install.md" in names
    assert "tests/product/test_packaging.py" in names
    assert "firmavex/product/resources/example/main.c" in names
    assert "src/firmavex/strategies/guided.py" in names
    assert not any(name.startswith("tests/test_") for name in names)
    assert not any("ground_truth" in name for name in names)
    assert not any(Path(name).suffix.lower() in {".elf", ".bin", ".exe", ".pyc"} for name in names)


def test_installed_wheel_imports_resources_and_cli_outside_checkout(distributions):
    working, wheel, _ = distributions
    installed = working / "installed"
    _run([sys.executable, "-B", "-m", "pip", "install", "--no-deps", "--no-compile",
          "--target", str(installed), str(wheel)], cwd=working)
    script = """
import importlib, importlib.util, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import firmavex
from src.firmavex.evaluation.api import TrialInput, ExecutionSignature
from src.firmavex.evaluation import api
from src.firmavex.compiler.cortex_m import SUPPORT_DIR
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.benchmarks.cortex_m import load_benchmarks
assert TrialInput is api.TrialInput
assert TrialInput is importlib.import_module('src.firmavex.evaluation.api').TrialInput
assert importlib.util.find_spec('firmavex.evaluation') is None
assert pathlib.Path(api.__file__).is_relative_to(sys.argv[1])
assert (SUPPORT_DIR / 'startup.c').is_file()
assert (SUPPORT_DIR / 'linker.ld').is_file()
assert len(load_benchmarks()) == 5
registry = BenchmarkRegistry()
assert len(registry.select('development')) == 6
assert len(registry.select('held_out')) == 2
assert (pathlib.Path(firmavex.__file__).parent / 'product/resources/example/main.c').is_file()
print(json.dumps({'version': firmavex.__version__, 'module': api.__name__}))
"""
    checked = _run([sys.executable, "-I", "-B", "-c", script, str(installed)], cwd=working)
    assert json.loads(checked.stdout) == {"version": "0.2.0.dev1", "module": "src.firmavex.evaluation.api"}
    help_script = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('firmavex',run_name='__main__')"
    help_result = _run([sys.executable, "-I", "-B", "-c", help_script, str(installed), "--help"], cwd=working)
    for command in ("doctor", "validate", "run", "reproduce", "export", "desktop"):
        assert command in help_result.stdout


def test_installed_entry_point_supervises_worker_outside_checkout(distributions):
    """A real install must let the child interpreter import the same wheel."""
    working, wheel, _ = distributions
    environment = working / "virtual environment"
    _run([sys.executable, "-B", "-m", "venv", "--system-site-packages", str(environment)], cwd=working)
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    # Supply the already-installed pure-Python runtime dependency locally so
    # this regression never downloads packages during the test suite.
    purelib = Path(_run([str(python), "-I", "-B", "-c",
                        "import sysconfig; print(sysconfig.get_path('purelib'))"], cwd=working).stdout.strip())
    shutil.copytree(Path(elftools.__file__).parent, purelib / "elftools",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    _run([str(python), "-B", "-m", "pip", "install", "--no-deps", "--no-compile",
          "--ignore-installed", str(wheel)], cwd=working)
    # Inspecting a missing archive must return a service error, not fail to
    # import the child worker. This does not dispatch tools or firmware.
    result = _run([str(python), "-I", "-B", "-m", "firmavex", "inspect",
                   str(working / "missing run")], cwd=working, check=False)
    assert result.returncode == 1
    response = json.loads(result.stdout)
    assert response["success"] is False
    assert response["error"]["category"] not in {"worker_failure", "worker_interrupted", "worker_timeout"}
    assert "database" in response["error"]["message"].lower()
    entry_point = scripts / ("firmavex.exe" if os.name == "nt" else "firmavex")
    help_result = _run([str(entry_point), "--help"], cwd=working)
    assert "reproduce" in help_result.stdout
    desktop_entry = scripts / ("firmavex-desktop.exe" if os.name == "nt" else "firmavex-desktop")
    desktop_help = _run([str(desktop_entry), "--help"], cwd=working)
    assert "--project" in desktop_help.stdout and "--smoke-test" in desktop_help.stdout
