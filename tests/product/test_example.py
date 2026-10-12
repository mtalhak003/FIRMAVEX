import json
import subprocess

import pytest

from firmavex.product.config import load_config
from firmavex.product.errors import ProductError
from firmavex.product import example


def test_example_refuses_existing_directory(tmp_path):
    sentinel = tmp_path / "retained"
    sentinel.write_text("keep")
    with pytest.raises(ProductError) as caught:
        example.build_example(tmp_path)
    assert caught.value.category == "output_exists"
    assert sentinel.read_text() == "keep"


def test_example_build_config_and_source_identity(tmp_path, monkeypatch):
    compiler = tmp_path / "compiler"
    compiler.write_text("synthetic compiler")
    compiler.chmod(0o755)
    monkeypatch.setattr(example, "_probe", lambda command: subprocess.CompletedProcess(command, 0, "synthetic 1\n", ""))
    def build(command, **kwargs):
        from pathlib import Path
        Path(command[-1]).write_bytes(b"synthetic-test-only")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(example.subprocess, "run", build)
    result = example.build_example(tmp_path / "fresh", str(compiler))
    config = load_config(result["config_file"])
    assert config.ready_breakpoint == "product_input_ready"
    assert config.input_symbols == ("product_inputs[0]", "product_inputs[1]")
    assert config.firmware.name == "example.elf"
    assert result["build"]["triggering_inputs"] == [2, 1]
    assert result["build"]["safe_inputs"] == [0, 0]
    assert set(result["build"]["sources"]) == {"main.c", "startup.c", "linker.ld"}
    assert "product_inputs[0] = 0" in (tmp_path / "fresh/main.c").read_text()
    assert "_sbss" in (tmp_path / "fresh/startup.c").read_text()


def test_example_compilation_failure_is_structured(tmp_path, monkeypatch):
    compiler = tmp_path / "compiler"
    compiler.write_text("synthetic compiler")
    compiler.chmod(0o755)
    monkeypatch.setattr(example, "_probe", lambda command: subprocess.CompletedProcess(command, 0, "synthetic 1\n", ""))
    monkeypatch.setattr(example.subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 1, "", "failed build"))
    with pytest.raises(ProductError) as caught:
        example.build_example(tmp_path / "fresh", str(compiler))
    assert caught.value.category == "build_failed"
    assert caught.value.details["stderr"] == "failed build"


def test_example_resolves_managed_compiler_without_path_configuration(tmp_path, monkeypatch):
    from firmavex.product import runtime_pack
    compiler = tmp_path / 'managed-compiler'
    compiler.write_text('synthetic compiler')
    compiler.chmod(0o755)
    monkeypatch.setattr(runtime_pack, 'active_tools', lambda: {'compiler': str(compiler)})
    monkeypatch.setattr(example, '_probe', lambda command: subprocess.CompletedProcess(command, 0, 'synthetic 1\n', ''))
    def build(command, **kwargs):
        from pathlib import Path
        Path(command[-1]).write_bytes(b'synthetic-test-only')
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(example.subprocess, 'run', build)
    result = example.build_example(tmp_path / 'fresh')
    assert result['build']['compiler']['path'] == str(compiler)
