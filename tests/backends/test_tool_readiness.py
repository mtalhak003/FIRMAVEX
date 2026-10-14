"""Discovery regressions; fake probes never establish guest qualification."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

import pytest

from firmavex.backends import tools
from firmavex.product import runtime_pack


def executable(path, data=b"synthetic administrator-selected host tool"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o755)
    return path


def test_explicit_runtime_directory_wins_over_path(tmp_path, monkeypatch):
    chosen = executable(tmp_path / "selected runtime/bin/iverilog")
    other = executable(tmp_path / "path/bin/iverilog")
    monkeypatch.setenv("PATH", str(other.parent))
    assert tools.find("iverilog", runtime_dirs=[chosen.parent.parent], use_managed=False) == str(chosen)


def test_environment_runtime_directory_with_spaces(tmp_path, monkeypatch):
    chosen = executable(tmp_path / "runtime with spaces/bin/vvp")
    monkeypatch.setenv("FIRMAVEX_BACKEND_RUNTIME_DIRS", str(chosen.parent.parent))
    monkeypatch.setenv("PATH", "")
    assert tools.find("vvp", use_managed=False) == str(chosen)


def test_generic_gdb_alias_is_found_without_claiming_capability(tmp_path, monkeypatch):
    chosen = executable(tmp_path / "gdb")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert tools.find("gdb-multiarch", use_managed=False) == str(chosen)


def test_homebrew_riscv_compiler_alias(tmp_path, monkeypatch):
    chosen = executable(tmp_path / "riscv64-elf-gcc")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert tools.find("riscv64-unknown-elf-gcc", use_managed=False) == str(chosen)


@pytest.mark.parametrize("search_path", ["", ".", ":.", "relative/bin"])
def test_workload_directory_cannot_select_runtime(tmp_path, monkeypatch, search_path):
    executable(tmp_path / "iverilog")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", search_path)
    with pytest.raises(tools.MissingDependency):
        tools.find("iverilog", use_managed=False)


@pytest.mark.parametrize("directories", [["relative"], ["/does/not/exist"], "single-string"])
def test_invalid_explicit_directory_rejected(directories):
    with pytest.raises(ValueError):
        tools.find("vvp", runtime_dirs=directories, use_managed=False)


@pytest.mark.parametrize("name", ["../vvp", "bash", "qemu-system-riscv32; command"])
def test_unknown_runtime_names_rejected(name):
    with pytest.raises(ValueError):
        tools.find(name, use_managed=False)


def managed_context(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    generation = root / ("a" * 32)
    qemu = executable(generation / "bin/qemu-system-arm")
    rv = executable(generation / "bin/qemu-system-riscv32")
    files = {
        path.relative_to(generation).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (qemu, rv)
    }
    def active_tools(*, _verified):
        _verified[generation.name] = {"files": files}
        return {"qemu": str(qemu)}
    monkeypatch.setattr(runtime_pack, "runtime_root", lambda: root)
    monkeypatch.setattr(runtime_pack, "active_tools", active_tools)
    monkeypatch.setenv("PATH", "")
    return rv, files


def test_managed_additional_tool_requires_inventory(tmp_path, monkeypatch):
    rv, files = managed_context(tmp_path, monkeypatch)
    assert tools.find("qemu-system-riscv32") == str(rv)
    files.pop("bin/qemu-system-riscv32")
    with pytest.raises(tools.MissingDependency):
        tools.find("qemu-system-riscv32")


def test_managed_mismatch_does_not_fall_back_to_path(tmp_path, monkeypatch):
    rv, files = managed_context(tmp_path, monkeypatch)
    rv.write_bytes(b"changed after inventory")
    fallback = executable(tmp_path / "fallback/qemu-system-riscv32")
    monkeypatch.setenv("PATH", str(fallback.parent))
    with pytest.raises(RuntimeError, match="changed"):
        tools.find("qemu-system-riscv32")


def test_batch_discovery_verifies_once_per_call_without_persistent_cache(tmp_path, monkeypatch):
    rv, files = managed_context(tmp_path, monkeypatch)
    original = runtime_pack.active_tools
    calls = []
    def counted(**kwargs):
        calls.append(True)
        return original(**kwargs)
    monkeypatch.setattr(runtime_pack, "active_tools", counted)
    assert tools.find_many(("qemu-system-arm", "qemu-system-riscv32"))["qemu-system-riscv32"] == str(rv)
    assert len(calls) == 1
    rv.write_bytes(b"changed before next independent operation")
    with pytest.raises(RuntimeError, match="changed"):
        tools.find_many(("qemu-system-arm", "qemu-system-riscv32"))
    assert len(calls) == 2


def test_damaged_active_runtime_never_silently_falls_back(tmp_path, monkeypatch):
    def damaged(**kwargs):
        raise RuntimeError("managed inventory corrupt")
    monkeypatch.setattr(runtime_pack, "active_tools", damaged)
    executable(tmp_path / "vvp")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="inventory corrupt"):
        tools.find("vvp")


class FakeProcesses:
    """Administrative capability test double, never an execution measurement."""
    def __init__(self, cancel, limits):
        self.cancel = cancel
        self.closed = False
        self.commands = []

    def run(self, command, cwd):
        self.commands.append(command)
        if "-machine" in command:
            return 0, "Supported machines are:\nvirt RISC-V VirtIO board\n", ""
        if "set architecture riscv:rv32" in command:
            digest = hashlib.sha256(b"probe").hexdigest()
            return 0, f"The architecture is riscv:rv32\nFIRMAVEX_BACKEND_GDB_V1={digest}\n", ""
        return 0, "Synthetic version fixture\n", ""

    def close(self):
        self.closed = True


def fake_readiness(tmp_path, monkeypatch, process_type=FakeProcesses):
    from firmavex.backends import process
    instances = []
    def factory(*args):
        selected = process_type(*args)
        instances.append(selected)
        return selected
    monkeypatch.setattr(process, "Processes", factory)
    for name in ("qemu-system-riscv32", "gdb-multiarch", "iverilog", "vvp"):
        executable(tmp_path / name)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("FIRMAVEX_BACKEND_RUNTIME_DIRS", raising=False)
    return instances


@pytest.mark.parametrize("profile", ["riscv32-virt", "verilog-icarus"])
def test_readiness_records_observed_files_not_guest_execution(tmp_path, monkeypatch, profile):
    instances = fake_readiness(tmp_path, monkeypatch)
    result = tools.readiness(profile, use_managed=False)
    assert result["status"] == "tools_available"
    assert result["guest_execution_performed"] is False
    assert "not established" in result["native_qualification"]
    assert result["cleanup_verified"] is True
    assert instances[0].closed
    assert all(len(item["identity"]["sha256"]) == 64 for item in result["tools"].values())
    if profile == "riscv32-virt":
        assert any("set architecture riscv:rv32" in command for command in instances[0].commands)


def test_readiness_missing_tools_returns_installation_guidance(monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("FIRMAVEX_BACKEND_RUNTIME_DIRS", raising=False)
    result = tools.readiness("verilog-icarus", use_managed=False)
    assert result["status"] == "missing_dependency"
    assert result["guest_execution_performed"] is False
    assert result["installation"]["offline_after_installation"] is True


@pytest.mark.parametrize("problem", ["machine", "architecture", "python", "version"])
def test_actual_capability_requirements_fail_closed(tmp_path, monkeypatch, problem):
    class Bad(FakeProcesses):
        def run(self, command, cwd):
            code, stdout, stderr = super().run(command, cwd)
            if problem == "machine" and "-machine" in command:
                return 0, "none No board\n", ""
            if problem == "architecture" and "set architecture riscv:rv32" in command:
                return 0, stdout.replace("riscv:rv32", "i386"), ""
            if problem == "python" and "set architecture riscv:rv32" in command:
                return 0, "riscv:rv32\n", ""
            if problem == "version" and "--version" in command:
                return 0, "", ""
            return code, stdout, stderr
    instances = fake_readiness(tmp_path, monkeypatch, Bad)
    result = tools.readiness("riscv32-virt", use_managed=False)
    assert result["status"] == "dependency_probe_failed"
    assert result["error"]["message"]
    assert instances[0].closed


def test_file_change_while_probing_rejected(tmp_path, monkeypatch):
    class Changed(FakeProcesses):
        def run(self, command, cwd):
            result = super().run(command, cwd)
            if "-V" in command:
                Path(command[0]).write_bytes(b"modified during probe")
            return result
    fake_readiness(tmp_path, monkeypatch, Changed)
    result = tools.readiness("verilog-icarus", use_managed=False)
    assert result["status"] == "dependency_probe_failed"
    assert "changed during" in result["error"]["message"]


def test_failed_cleanup_cannot_report_available(tmp_path, monkeypatch):
    class CleanupFailed(FakeProcesses):
        def close(self):
            raise OSError("owned process cleanup failed")
    fake_readiness(tmp_path, monkeypatch, CleanupFailed)
    result = tools.readiness("verilog-icarus", use_managed=False)
    assert result["status"] == "dependency_probe_failed"
    assert result["cleanup_verified"] is False


def test_control_flow_exception_preserved_when_cleanup_fails(tmp_path, monkeypatch):
    class Interrupted(FakeProcesses):
        def run(self, command, cwd):
            raise KeyboardInterrupt("original interruption")
        def close(self):
            raise OSError("later cleanup error")
    fake_readiness(tmp_path, monkeypatch, Interrupted)
    with pytest.raises(KeyboardInterrupt, match="original interruption") as caught:
        tools.readiness("verilog-icarus", use_managed=False)
    assert any("cleanup" in note for note in caught.value.__notes__)


@pytest.mark.parametrize("system", ["Linux", "Darwin", "Windows", "unsupported"])
@pytest.mark.parametrize("profile", ["cortex-m3-mps2", "riscv32-virt", "verilog-icarus"])
def test_installation_guidance_is_offline_metadata(system, profile):
    result = tools.installation_guidance(profile, system=system)
    assert result["host_system"] == system
    assert result["compiler_required_for_execution"] is False
    assert result["runtime_directory_environment"] == "FIRMAVEX_BACKEND_RUNTIME_DIRS"
    assert "does not bundle" in result["redistribution"]


def test_vendor_snapshot_preserves_backend_tools_and_subtools(tmp_path):
    from firmavex.product import runtime_setup
    vendor = tmp_path / "vendor"
    for name in ("bin/qemu-system-arm.exe", "bin/qemu-system-riscv32.exe", "bin/gdb-multiarch.exe",
                 "bin/iverilog.exe", "bin/vvp.exe", "lib/ivl/ivl.exe", "lib/ivl/vvp.tgt",
                 "share/licenses/iverilog/COPYING", "bin/qemu-system-x86_64.exe"):
        executable(vendor / name)
    archive = tmp_path / "local.zip"
    runtime_setup.snapshot_runtime(vendor, archive, packages="synthetic signed-package inventory fixture")
    with zipfile.ZipFile(archive) as bundle:
        record = json.loads(bundle.read("runtime.json"))
        assert record["tools"] == {"qemu": "bin/qemu-system-arm.exe", "gdb": "bin/gdb-multiarch.exe"}
        for name in ("bin/qemu-system-riscv32.exe", "bin/iverilog.exe", "bin/vvp.exe", "lib/ivl/ivl.exe", "lib/ivl/vvp.tgt"):
            assert name in record["files"]
        assert "bin/qemu-system-x86_64.exe" not in record["files"]
    assert "mingw-w64-ucrt-x86_64-iverilog" in runtime_setup.PACKAGES


@pytest.mark.parametrize("profile,names", [("riscv32-virt", ("qemu-system-riscv32", "gdb-multiarch")),
                                         ("verilog-icarus", ("iverilog", "vvp"))])
def test_real_runtime_readiness_without_guest_dispatch(profile, names):
    if any(not shutil.which(name) for name in names):
        if os.environ.get("FIRMAVEX_REQUIRE_BACKENDS") == "1":
            pytest.fail("Required actual runtime tools are missing")
        pytest.skip("Actual host runtime unavailable")
    result = tools.readiness(profile, use_managed=False)
    assert result["status"] == "tools_available", result
    assert result["guest_execution_performed"] is False
    assert result["cleanup_verified"] is True
