"""Explicit runtime discovery; probes run host tools, never guest firmware."""

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from firmavex.product.errors import ProductError
from .file_state import path_state, handle_state


def file_identity(path: str | Path) -> dict:
    """Reject observable replacement/modification while reading an artifact."""
    path = Path(path).resolve(strict=True)
    before = path.stat()
    initial = path_state(path, before)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        opened = handle_state(stream.fileno())
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
        finished = handle_state(stream.fileno())
    after = path.stat()
    if not (initial == opened == finished == path_state(path, after)):
        raise ProductError("artifact_changed", f"Artifact changed while hashing: {path}")
    return {"path": str(path), "sha256": digest.hexdigest(), "size_bytes": after.st_size}


def _resolve(name: str, supplied: str | None) -> str:
    selected = supplied or shutil.which(name)
    if selected is None:
        raise ProductError("missing_dependency", f"Required tool not found: {name}")
    path = Path(selected).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ProductError("missing_dependency", f"Tool is not an executable file: {path}")
    return str(path)


def _probe(command: list[str], *, timeout: float = 10.0) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=timeout, errors="replace",
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}), env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProductError("dependency_probe_failed", f"Unable to probe {command[0]}: {exc}") from exc
    if result.returncode:
        raise ProductError("dependency_probe_failed", f"Tool probe failed: {command[0]}",
                           {"stdout": result.stdout, "stderr": result.stderr,
                            "return_code": result.returncode})
    return result


@dataclass(frozen=True)
class Toolchain:
    qemu: str
    gdb: str
    compiler: str | None = None
    identities: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        import copy
        return {"qemu": self.qemu, "gdb": self.gdb, "compiler": self.compiler,
                "identities": copy.deepcopy(self.identities)}


def discover(config=None, *, require_compiler: bool = False, _managed: bool = True) -> Toolchain:
    from .runtime_pack import active_tools, verify_selected_generation
    needs_managed = not getattr(config, "qemu", None) or not getattr(config, "gdb", None) or (require_compiler and not getattr(config, "compiler", None))
    managed = active_tools() if _managed and needs_managed else {}
    qemu = _resolve("qemu-system-arm", getattr(config, "qemu", None) or managed.get("qemu"))
    supplied_gdb = getattr(config, "gdb", None) or managed.get("gdb")
    gdb = _resolve("arm-none-eabi-gdb", supplied_gdb or shutil.which("arm-none-eabi-gdb")
                   or shutil.which("gdb-multiarch") or shutil.which("gdb"))
    supplied_compiler = getattr(config, "compiler", None) or (managed.get("compiler") if require_compiler else None)
    compiler = (_resolve("arm-none-eabi-gcc", supplied_compiler)
                if require_compiler or supplied_compiler is not None else None)
    if _managed:
        for selected in (qemu, gdb, compiler):
            if selected is not None:
                verify_selected_generation(selected)
    identities = {}
    for name, path in (("qemu", qemu), ("gdb", gdb), ("compiler", compiler)):
        if path is None:
            continue
        before = file_identity(path)
        version = _probe([path, "--version"]).stdout.strip().splitlines()
        if not version:
            raise ProductError("dependency_probe_failed", f"Tool has no version output: {path}")
        if before != file_identity(path):
            raise ProductError("artifact_changed", f"Tool changed during discovery: {path}")
        identities[name] = {**before, "version": version[0]}
    machines = _probe([qemu, "-machine", "help"]).stdout
    if not any(line.split() and line.split()[0] == "mps2-an385"
               for line in machines.splitlines()):
        raise ProductError("unsupported_runtime", "QEMU lacks the mps2-an385 machine.")
    result = _probe([gdb, "--nx", "--nh", "--batch", "-iex", "set auto-load off", "-iex", "set python dont-write-bytecode on",
                     "-ex", "python import hashlib; print('FIRMAVEX_GDB_CAPABILITY_V1=' + hashlib.sha256(b'probe').hexdigest())"])
    expected = "FIRMAVEX_GDB_CAPABILITY_V1=" + hashlib.sha256(b"probe").hexdigest()
    if expected not in result.stdout.splitlines():
        raise ProductError("unsupported_runtime", "GDB requires working embedded Python and hashlib.")
    architecture = _probe([gdb, "--nx", "--nh", "--batch", "-iex", "set auto-load off", "-iex", "set python dont-write-bytecode on",
                            "-ex", "set architecture arm", "-ex", "show architecture"])
    if "arm" not in architecture.stdout.lower():
        raise ProductError("unsupported_runtime", "GDB does not support the ARM target.")
    for name, path in (("qemu", qemu), ("gdb", gdb), ("compiler", compiler)):
        if path is not None and any(file_identity(path)[key] != identities[name][key]
                                    for key in ("path", "sha256", "size_bytes")):
            raise ProductError("artifact_changed", f"Tool changed during capability probes: {path}")
    return Toolchain(qemu, gdb, compiler, identities)
