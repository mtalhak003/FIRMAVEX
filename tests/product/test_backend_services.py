"""Product trust/transport contracts and compiler-free backend preparation."""

import json
from pathlib import Path
import pytest
from firmavex.product import backend_services
from firmavex.product.errors import ProductError
from firmavex.product.protocol import encode_event
from firmavex.backends.api import Request, request_to_dict
from firmavex.backends.bundled import (
    catalog,
    prepare_builtin_riscv,
    validate_builtin_riscv,
)


@pytest.mark.parametrize("trust", [None, "untrusted", "REAL", ""])
def test_untrusted_rejected_before_output_or_dispatch(tmp_path, trust):
    request = request_to_dict(Request("riscv32-virt", tmp_path / "missing", (2, 1)))
    with pytest.raises(ProductError, match="Untrusted"):
        backend_services.execute(request, tmp_path / "out", trust=trust)
    assert not (tmp_path / "out").exists()


def test_readiness_is_strict_wire_json(monkeypatch):
    from firmavex.backends import compatibility

    monkeypatch.setattr(
        compatibility,
        "check",
        lambda profile: {"tools": ("qemu", "gdb"), "methods": ("symbol-observation",)},
    )
    result = backend_services.check("riscv32-virt")
    assert result["tools"] == ["qemu", "gdb"]
    encode_event("readiness", 1, "result", result)


def test_builtin_riscv_integrity_and_no_compiler(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("No subprocess during preparation"),
    )
    record = backend_services.prepare("riscv32-virt", tmp_path / "new")
    assert record["compiler_required"] is False and record["firmware_executed"] is False
    assert (
        validate_builtin_riscv(record["source"])["sha256"]
        == catalog()[0]["image_sha256"]
    )
    assert (tmp_path / "new/image-provenance.json").exists()
    with pytest.raises(FileExistsError):
        prepare_builtin_riscv(tmp_path / "new")
    Path(record["source"]).write_bytes(b"wrong")
    with pytest.raises(ValueError, match="not the verified"):
        validate_builtin_riscv(record["source"])


def test_cli_requires_explicit_trust(tmp_path):
    from firmavex.backends.cli import main

    assert (
        main(
            [
                "execute",
                "riscv32-virt",
                str(tmp_path / "x"),
                "--values",
                "2",
                "1",
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "out").exists()


def test_prepare_unknown_profile_does_not_write(tmp_path):
    with pytest.raises(ValueError):
        backend_services.prepare("vhdl", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_arm_progress_is_diagnostic_and_nonce_bound():
    from firmavex.product.runtime import _debugger_script
    from types import SimpleNamespace

    config = SimpleNamespace(
        input_symbols=("a", "b"),
        ready_breakpoint="ready",
        completion_breakpoint="done",
        failure_symbol="failed",
        failure_value=1,
        collect_signature=False,
    )
    script = _debugger_script(config, (2, 1), 12345, "NONCE=")
    assert script.count("gdb.flush()") == 2
    assert script.index('"stage": "injected"') < script.index(
        "observed = int(unsigned32"
    )
    assert "continue_to(completion)" in script

def test_windows_reparse_path_fails_closed(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from firmavex.backends.security import checked_path
    original=Path.lstat
    def state(path,*args,**kwargs):
        value=original(path,*args,**kwargs)
        if path==tmp_path:return SimpleNamespace(st_mode=value.st_mode,st_nlink=value.st_nlink,st_file_attributes=0x400)
        return value
    monkeypatch.setattr(Path,'lstat',state)
    with pytest.raises(ValueError,match='reparse'):
        checked_path(tmp_path/'new-output',exists=False)
