"""Frozen asset/sidecar coverage and fail-closed native qualification checks.

Synthetic records in validator tests are never qualification measurements.
Actual source/frozen runtime validation is performed by the native workflow.
"""

from pathlib import Path
import runpy
import sys
import types

from elftools.elf.elffile import ELFFile
import pytest

from tools import universal_desktop_ci as qualification


ROOT = Path(__file__).resolve().parents[2]


def test_frozen_spec_collects_backend_assets_and_preserves_sidecars(monkeypatch):
    calls = []
    built = []

    def collect_data(package):
        calls.append(package)
        directory = ROOT.joinpath(*package.split("."))
        return [(str(path), str(path.parent.relative_to(directory.parent)))
                for path in directory.rglob("*") if path.is_file() and path.suffix in {".json", ".v", ".S", ".c", ".ld", ".md"}]

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_submodules = lambda package: [package]
    hooks.collect_data_files = collect_data
    monkeypatch.setitem(sys.modules, "PyInstaller", types.ModuleType("PyInstaller"))
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", types.ModuleType("PyInstaller.utils"))
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)

    def analysis(entries, **kwargs):
        built.append(("Analysis", entries, kwargs))
        return types.SimpleNamespace(pure=[], binaries=[], datas=kwargs["datas"], scripts=[
            ("desktop_entry", entries[0], "PYSOURCE"),
            ("desktop_gui_entry", entries[1], "PYSOURCE"),
            ("pyi_rth_inspect", "runtime-hook", "PYSOURCE"),
        ])

    def exe(pyz, scripts, binaries, **kwargs):
        built.append(("EXE", scripts, kwargs))
        return kwargs["name"]

    result = runpy.run_path(str(ROOT / "packaging/desktop.spec"), init_globals={
        "SPECPATH": str(ROOT / "packaging"), "Analysis": analysis,
        "PYZ": lambda data: data, "EXE": exe, "COLLECT": lambda *args, **kw: (args, kw),
        "BUNDLE": lambda *args, **kw: (args, kw),
    })
    assert "firmavex.backends" in calls
    assets = {Path(source).name for source, destination in result["a"].datas}
    assert {"image.json", "riscv.c", "riscv.S", "riscv.ld", "counter.v"} <= assets
    executables = {item[2]["name"]: item for item in built if item[0] == "EXE"}
    assert set(executables) == {"FIRMAVEX", "FIRMAVEX-Desktop"}
    assert executables["FIRMAVEX"][2]["console"] is True
    assert executables["FIRMAVEX-Desktop"][2]["console"] is False
    assert {item[0] for item in executables["FIRMAVEX"][1]} == {"desktop_entry", "pyi_rth_inspect"}
    assert {item[0] for item in executables["FIRMAVEX-Desktop"][1]} == {"desktop_gui_entry", "pyi_rth_inspect"}


def test_bundled_rv_catalog_is_actual_elf_and_compiler_free(tmp_path):
    from firmavex.backends.bundled import prepare_builtin_riscv

    record = prepare_builtin_riscv(tmp_path / "prepared example")
    assert record["compiler_required"] is False and record["firmware_executed"] is False
    assert Path(record["source"]).read_bytes()[:4] == b"\x7fELF"
    assert qualification._sha256(record["source"]) == record["firmware"]["sha256"]
    with Path(record["source"]).open("rb") as stream:
        elf = ELFFile(stream)
        assert elf.elfclass == 32 and elf["e_machine"] == "EM_RISCV"


def test_controlled_rv_loop_preserves_image_and_ready_prologue(tmp_path):
    from firmavex.backends.bundled import prepare_builtin_riscv

    record = prepare_builtin_riscv(tmp_path / "original")
    original = Path(record["source"])
    content = original.read_bytes()
    patched = tmp_path / "declared loop.elf"
    qualification._rv_loop(original, patched)
    assert original.read_bytes() == content
    with original.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = elf.get_section_by_name(".symtab").get_symbol_by_name("input_ready")[0]
        address = symbol["st_value"] + symbol["st_size"] - 4
        segment = next(s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"
                       and s["p_vaddr"] <= address < s["p_vaddr"] + s["p_filesz"])
        offset = segment["p_offset"] + address - segment["p_vaddr"]
    assert patched.read_bytes() == content[:offset] + bytes.fromhex("6f000000") + content[offset + 4:]
    assert len(patched.read_bytes()) == len(content)


@pytest.fixture
def rv_result():
    return {"schema_version": 1, "status": "triggered", "evidence": {
        "cleanup_verified": True, "cleanup": [], "measurement_mode": "real_firmware",
        "tools": {"qemu": {"identity": {"sha256": "a" * 64}, "version": "test fixture only"}},
        "completion_observed": True, "observation": {"success": True},
    }}


@pytest.mark.parametrize("field,value", [
    ("measurement_mode", "synthetic_test"), ("measurement_mode", "unverified"),
    ("cleanup_verified", False), ("completion_observed", False),
    ("tools", {}), ("observation", {"success": False}),
])
def test_qualification_rejects_label_or_incomplete_native_evidence(rv_result, field, value):
    rv_result["evidence"][field] = value
    with pytest.raises(ValueError):
        qualification.verify_completed(rv_result, "riscv32-virt", "triggered")


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("status", "passed"), ("status", "infrastructure_failure")])
def test_qualification_rejects_wrong_contract_or_outcome(rv_result, field, value):
    rv_result[field] = value
    with pytest.raises(ValueError):
        qualification.verify_completed(rv_result, "riscv32-virt", "triggered")


def test_qualification_rejects_missing_tool_identity(rv_result):
    rv_result["evidence"]["tools"]["qemu"]["identity"]["sha256"] = "abc"
    with pytest.raises(ValueError, match="digest"):
        qualification.verify_completed(rv_result, "riscv32-virt", "triggered")


@pytest.mark.parametrize("change", ["missing-waveform", "nonzero-returncode", "wrong-mode"])
def test_hdl_qualification_requires_simulator_outcome_and_waveform(change):
    record = {"schema_version": 1, "status": "passed", "evidence": {
        "cleanup_verified": True, "cleanup": [], "measurement_mode": "real_simulation",
        "returncode": 0, "artifacts": [{"name": "waveform.vcd"}],
        "tools": {"simulator": {"identity": {"sha256": "c" * 64}, "version": "test fixture only"}},
    }}
    if change == "missing-waveform":
        record["evidence"]["artifacts"] = []
    elif change == "nonzero-returncode":
        record["evidence"]["returncode"] = 1
    else:
        record["evidence"]["measurement_mode"] = "real_firmware"
    with pytest.raises(ValueError):
        qualification.verify_completed(record, "verilog-icarus", "passed")


def test_qualification_does_not_overwrite_or_dispatch_in_existing_output(tmp_path, monkeypatch):
    sentinel = tmp_path / "saved results"
    sentinel.write_bytes(b"unchanged")
    monkeypatch.setattr(qualification, "Supervisor", lambda **kw: pytest.fail("No worker should be created"))
    with pytest.raises(FileExistsError):
        qualification.qualify(tmp_path)
    assert sentinel.read_bytes() == b"unchanged"


def test_native_notice_has_actual_digest_version_but_not_administrative_paths(rv_result, capsys):
    rv_result["evidence"]["tools"]["qemu"]["identity"]["path"] = "/private/user/runtime/qemu"
    summary = qualification._runtime_notice("riscv32-virt", rv_result, None, frozen=True)
    notice = capsys.readouterr().out
    assert "Universal runtime qualification" in notice
    assert "/private/user" not in notice
    assert summary["tools"]["qemu"]["sha256"] == "a" * 64
    assert summary["execution_path"] == "frozen"


def test_cli_returns_failure_without_claiming_qualification(tmp_path, monkeypatch, capsys):
    def failed(*args):
        raise RuntimeError("native runtime missing")
    monkeypatch.setattr(qualification, "qualify", failed)
    assert qualification.main(["--output", str(tmp_path / "new")]) == 1
    text = capsys.readouterr().out
    assert "::error" in text and "native runtime missing" in text
    assert "::notice" not in text


def test_record_does_not_serialize_nonfinite_measurements(tmp_path):
    with pytest.raises(ValueError):
        qualification._record(tmp_path / "record.json", {"elapsed_seconds": float("nan")})


def test_universal_workflow_requires_actual_three_os_and_source_frozen_qualification():
    text = (ROOT / ".github/workflows/unified-desktop.yml").read_text()
    for token in ("ubuntu-24.04", "windows-latest", "macos-14", "FIRMAVEX_REQUIRE_BACKENDS",
                  "mingw-w64-ucrt-x86_64-iverilog", "icarus-verilog", "tests/desktop/test_real_universal.py",
                  "--engine", "packaging/desktop.spec"):
        assert token in text
    assert "continue-on-error" not in text
    assert "product/desktop-batch6" in text


def test_existing_installer_qualification_workflows_preserved():
    beta = (ROOT / ".github/workflows/desktop-beta.yml").read_text()
    distribution = (ROOT / ".github/workflows/desktop-distribution.yml").read_text()
    assert "product/desktop-batch6" in beta and "product/desktop-batch6" in distribution
    assert "-FirmwareQualification" in beta
    assert "test_windows_install.ps1" in distribution
    assert "FIRMAVEX-Linux-amd64.deb" in distribution
    assert "FIRMAVEX-macOS-unnotarized.dmg" in distribution
