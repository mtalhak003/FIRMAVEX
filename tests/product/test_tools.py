import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from firmavex.product.errors import ProductError
from firmavex.product import tools


def test_identity_is_actual_bytes(tmp_path):
    path = tmp_path / "image with spaces.elf"
    path.write_bytes(b"firmware")
    assert tools.file_identity(path) == {"path": str(path), "size_bytes": 8,
                                       "sha256": hashlib.sha256(b"firmware").hexdigest()}


def test_identity_rejects_mid_read_mutation(tmp_path, monkeypatch):
    path = tmp_path / "artifact"
    path.write_bytes(b"original")
    original = Path.open

    class MutatingReader:
        def __init__(self, stream):
            self.stream = stream
            self.changed = False
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def fileno(self): return self.stream.fileno()
        def read(self, count):
            result = self.stream.read(count)
            if not self.changed:
                self.changed = True
                with original(path, "wb") as writer:
                    writer.write(b"changed during hash")
            return result

    monkeypatch.setattr(Path, "open", lambda self, *a, **k: MutatingReader(original(self, *a, **k)))
    with pytest.raises(ProductError, match="changed while hashing"):
        tools.file_identity(path)


def test_missing_dependency_has_structured_error(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    with pytest.raises(ProductError) as caught:
        tools.discover()
    assert caught.value.category == "missing_dependency"


@pytest.fixture
def fake_tool_probes(tmp_path, monkeypatch):
    paths = {}
    for name in ("qemu-system-arm", "gdb-multiarch", "arm-none-eabi-gcc"):
        path = tmp_path / name
        path.write_text("executable")
        path.chmod(0o755)
        paths[name] = str(path)
    monkeypatch.setattr(tools.shutil, "which", lambda name: paths.get(name))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if "--version" in command:
            output = "test-tool 1.0\n"
        elif "-machine" in command:
            output = "mps2-an385 ARM MPS2 Cortex-M3\n"
        elif "show architecture" in command:
            output = "The target architecture is set to arm.\n"
        else:
            output = "FIRMAVEX_GDB_CAPABILITY_V1=" + hashlib.sha256(b"probe").hexdigest() + "\n"
        return subprocess.CompletedProcess(command, 0, output, "")
    monkeypatch.setattr(tools.subprocess, "run", run)
    return paths, calls


def test_discovery_uses_multiarch_fallback_and_capabilities(fake_tool_probes):
    paths, calls = fake_tool_probes
    result = tools.discover(require_compiler=True)
    assert result.gdb == paths["gdb-multiarch"]
    assert result.compiler == paths["arm-none-eabi-gcc"]
    assert result.identities["gdb"]["sha256"] == hashlib.sha256(b"executable").hexdigest()
    assert any("-machine" in call for call in calls)
    assert all("--nx" in call for call in calls if "--batch" in call)


def test_compiler_optional(fake_tool_probes):
    assert tools.discover().compiler is None


def test_discovery_rejects_missing_qemu_machine(fake_tool_probes, monkeypatch):
    original = tools._probe
    def probe(command, **kwargs):
        if "-machine" in command:
            return subprocess.CompletedProcess(command, 0, "other machine\n", "")
        return original(command, **kwargs)
    monkeypatch.setattr(tools, "_probe", probe)
    with pytest.raises(ProductError, match="lacks the mps2-an385"):
        tools.discover()


def test_discovery_rejects_missing_gdb_python(fake_tool_probes, monkeypatch):
    original = tools._probe
    def probe(command, **kwargs):
        if any("python import" in value for value in command):
            return subprocess.CompletedProcess(command, 0, "Python disabled\n", "")
        return original(command, **kwargs)
    monkeypatch.setattr(tools, "_probe", probe)
    with pytest.raises(ProductError, match="embedded Python"):
        tools.discover()


@pytest.mark.parametrize("failure", [OSError("missing"), subprocess.TimeoutExpired("tool", 10)])
def test_probe_failure_classified(monkeypatch, failure):
    def run(*args, **kwargs): raise failure
    monkeypatch.setattr(tools.subprocess, "run", run)
    with pytest.raises(ProductError) as caught:
        tools._probe(["tool"])
    assert caught.value.category == "dependency_probe_failed"


def test_toolchain_serialization_detached():
    result = tools.Toolchain("qemu", "gdb", identities={"qemu": {"version": "1"}})
    serialized = result.to_dict()
    serialized["identities"]["qemu"]["version"] = "modified"
    assert result.identities["qemu"]["version"] == "1"

def test_discovery_uses_managed_tools_and_explicit_override(fake_tool_probes, monkeypatch):
    from firmavex.product import runtime_pack as pack
    paths, calls = fake_tool_probes
    monkeypatch.setattr(pack, 'active_tools', lambda: {'qemu': paths['qemu-system-arm'], 'gdb': paths['gdb-multiarch']})
    result = tools.discover()
    assert result.qemu == paths['qemu-system-arm']


def test_capability_probe_cannot_read_worker_command_stream(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 0, 'version\n', '')
    monkeypatch.setattr(tools.subprocess, 'run', run)
    tools._probe(['trusted-tool', '--version'])
    assert calls[0]['stdin'] == subprocess.DEVNULL


def test_real_host_probe_receives_eof_not_parent_stdin():
    import sys
    result = tools._probe([sys.executable, '-c', 'import sys; print(repr(sys.stdin.read()))'], timeout=2)
    assert result.stdout.strip() == "''"
