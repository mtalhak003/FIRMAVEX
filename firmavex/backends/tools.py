"""Offline runtime discovery and actual capability probes.

These checks execute administrator-trusted host programs, never guest inputs.
Executable identity and version probes are evidence of availability, not native
qualification, publisher authentication, or a sandbox boundary.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import tempfile
import threading

from firmavex.product.tools import file_identity


_ALIASES = {
    "qemu-system-riscv32": ("qemu-system-riscv32",),
    "qemu-system-arm": ("qemu-system-arm",),
    "gdb-multiarch": ("gdb-multiarch", "gdb"),
    "arm-none-eabi-gdb": ("arm-none-eabi-gdb", "gdb-multiarch", "gdb"),
    "iverilog": ("iverilog",),
    "vvp": ("vvp",),
    "riscv64-unknown-elf-gcc": ("riscv64-unknown-elf-gcc", "riscv64-elf-gcc"),
}


class MissingDependency(RuntimeError):
    """No executable in the explicitly trusted discovery locations."""


@dataclass(frozen=True)
class Selection:
    path: str
    source: str
    expected_sha256: str | None = None


def _aliases(name):
    if name not in _ALIASES:
        raise ValueError("Unsupported runtime tool name")
    names = _ALIASES[name]
    return tuple(item for value in names for item in (value, value + ".exe")) if os.name == "nt" else names


def _directories(runtime_dirs):
    if runtime_dirs is None:
        raw = os.environ.get("FIRMAVEX_BACKEND_RUNTIME_DIRS", "")
        runtime_dirs = tuple(raw.split(os.pathsep)) if raw else ()
    if isinstance(runtime_dirs, (str, bytes, Path)):
        raise ValueError("runtime_dirs must be a sequence of absolute directories")
    selected = []
    for raw in runtime_dirs:
        path = Path(raw).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("Runtime directories must be existing absolute directories")
        for candidate in (path, path / "bin"):
            if candidate.is_dir() and candidate not in selected:
                selected.append(candidate)
    return selected


def _managed():
    # The existing schema-1 ARM manifest can inventory additional executables.
    # It remains unchanged; only inventoried siblings are eligible for discovery.
    from firmavex.product.runtime_pack import active_tools, runtime_root

    verified = {}
    active = active_tools(_verified=verified)
    if not active:
        return []
    root = runtime_root().resolve()
    result = []
    for name, path in active.items():
        selected = Path(path).resolve(strict=True)
        parts = selected.relative_to(root).parts
        generation = parts[0]
        manifest = verified.get(generation)
        if manifest is None:
            raise RuntimeError("Active runtime lacks a verified file inventory")
        result.append((selected.parent, root / generation, manifest["files"]))
    return result


def _context(runtime_dirs=None, use_managed=True):
    return _directories(runtime_dirs), _managed() if use_managed else []


def _executable(path):
    if path.is_file() and os.access(path, os.X_OK):
        return str(path.resolve(strict=True))
    return None


def _locate(name, context):
    names = _aliases(name)
    directories, managed = context
    for directory in directories:
        for alias in names:
            selected = _executable(directory / alias)
            if selected:
                return Selection(selected, "administrator_runtime_directory")
    for directory, generation, inventory in managed:
        for alias in names:
            candidate = directory / alias
            relative = candidate.relative_to(generation).as_posix()
            if relative not in inventory:
                continue
            selected = _executable(candidate)
            if not selected or file_identity(selected)["sha256"] != inventory[relative]:
                raise RuntimeError("Managed runtime executable changed after inventory verification")
            return Selection(selected, "verified_managed_generation", inventory[relative])
    # Relative/empty PATH entries would allow the workload directory to select
    # a host executable. Exclude them even when an administrator PATH includes it.
    safe_path = os.pathsep.join(
        raw for raw in os.environ.get("PATH", "").split(os.pathsep)
        if raw and Path(raw).is_absolute()
    )
    for alias in names if safe_path else ():
        selected = shutil.which(alias, path=safe_path)
        if selected and _executable(Path(selected)):
            return Selection(str(Path(selected).resolve(strict=True)), "administrator_path")
    raise MissingDependency(
        f"Missing runtime dependency: {name}. Install the documented publisher runtime "
        "or select an administrator-trusted runtime directory."
    )


def find(name, *, runtime_dirs=None, use_managed=True):
    """Return an absolute executable path without dispatching any subprocess."""
    _aliases(name)
    return _locate(name, _context(runtime_dirs, use_managed)).path


def find_many(names, *, runtime_dirs=None, use_managed=True):
    """Resolve one operation's tools with one fresh managed-inventory check.

    This is a within-call optimization only. No cached filesystem identities or
    inventory decisions survive into subsequent calls.
    """
    names = tuple(names)
    for name in names:
        _aliases(name)
    context = _context(runtime_dirs, use_managed)
    return {name: _locate(name, context).path for name in names}


def installation_guidance(profile, *, system=None):
    """Local installation guidance; this function makes no network requests."""
    from .api import profiles

    if profile not in profiles:
        raise ValueError("Unsupported profile")
    system = system or platform.system()
    packages = {
        "cortex-m3-mps2": ("qemu-system-arm gdb-multiarch", "qemu gdb"),
        "riscv32-virt": ("qemu-system-misc gdb-multiarch", "qemu gdb"),
        "verilog-icarus": ("iverilog", "icarus-verilog"),
    }[profile]
    command = None
    if system == "Linux":
        command = "sudo apt-get install " + packages[0]
        note = "The command applies to Ubuntu/Debian. Other Linux distributions need their equivalent packages."
    elif system == "Darwin":
        command = "brew install " + packages[1]
        note = "Use the official Homebrew packages; actual capabilities are checked after installation."
    elif system == "Windows":
        note = (
            "Use the first-launch wizard's consented MSYS2 publisher installation, "
            "or an administrator-verified UCRT64 runtime. The provider retains ARM/RV32 QEMU, "
            "multiarchitecture GDB and Icarus. Existing ARM-only generations need repair "
            "to obtain the added tools. Native execution qualification is separate from installation."
        )
    else:
        note = "No installation provider is documented for this operating system."
    return {
        "profile": profile,
        "host_system": system,
        "command": command,
        "instructions": note,
        "offline_after_installation": True,
        "compiler_required_for_execution": False,
        "runtime_directory_environment": "FIRMAVEX_BACKEND_RUNTIME_DIRS",
        "trust_requirement": "Host runtime executables must come from an administrator-trusted publisher.",
        "redistribution": "FIRMAVEX does not bundle these runtimes. Retain notices and review component/source obligations before redistribution.",
    }


def readiness(profile, *, runtime_dirs=None, use_managed=True, cancel=None):
    """Probe actual tool files and capabilities without executing firmware/HDL."""
    from .api import Limits, profiles
    from .process import Processes

    if profile not in profiles:
        raise ValueError("Unsupported profile")
    if profile == "cortex-m3-mps2":
        from firmavex.product.services import doctor

        result = doctor()
        return {**result, "installation": installation_guidance(profile)}
    tools = {}
    result = {
        "status": "dependency_probe_failed",
        "profile": profiles[profile].to_dict(),
        "tools": tools,
        "guest_execution_performed": False,
        "native_qualification": "not established by availability or version probes",
        "installation": installation_guidance(profile),
    }
    processes = None
    try:
        context = _context(runtime_dirs, use_managed)
        selections = {name: _locate(name, context) for name in profiles[profile].tool_names}
        processes = Processes(cancel if cancel is not None else threading.Event(), Limits(30))
        with tempfile.TemporaryDirectory(prefix="firmavex-readiness-") as directory:
            try:
                for name, selection in selections.items():
                    before = file_identity(selection.path)
                    if selection.expected_sha256 is not None and before["sha256"] != selection.expected_sha256:
                        raise RuntimeError("Managed runtime changed before probing")
                    code, stdout, stderr = processes.run(
                        [selection.path, "-V" if profile == "verilog-icarus" else "--version"],
                        Path(directory),
                    )
                    version = (stdout or stderr).strip().splitlines()
                    if code or not version:
                        raise RuntimeError(f"Version probe failed for {name}: {stderr}")
                    tools[name] = {"identity": before, "version": version[0], "selection": selection.source}
                if profile == "riscv32-virt":
                    code, stdout, stderr = processes.run(
                        [selections["qemu-system-riscv32"].path, "-machine", "help"], Path(directory)
                    )
                    if code or not any(line.split() and line.split()[0] == "virt" for line in stdout.splitlines()):
                        raise RuntimeError("QEMU lacks the RISC-V virt machine")
                    code, stdout, stderr = processes.run([
                        selections["gdb-multiarch"].path, "--nx", "--nh", "--batch",
                        "-iex", "set auto-load off", "-iex", "set python dont-write-bytecode on",
                        "-ex", "set architecture riscv:rv32", "-ex", "show architecture",
                        "-ex", "python import hashlib; print('FIRMAVEX_BACKEND_GDB_V1=' + hashlib.sha256(b'probe').hexdigest())",
                    ], Path(directory))
                    import hashlib

                    expected = "FIRMAVEX_BACKEND_GDB_V1=" + hashlib.sha256(b"probe").hexdigest()
                    if code or "riscv:rv32" not in stdout or expected not in stdout.splitlines():
                        raise RuntimeError("GDB requires RV32 architecture and working embedded Python/hashlib")
                for name, selection in selections.items():
                    if tools[name]["identity"] != file_identity(selection.path):
                        raise RuntimeError(f"Tool changed during capability probes: {name}")
            finally:
                import sys

                original = sys.exception()
                try:
                    processes.close()
                    result["cleanup_verified"] = True
                except BaseException as cleanup:
                    result["cleanup_verified"] = False
                    if original is None:
                        raise
                    original.add_note(f"Readiness cleanup failed: {type(cleanup).__name__}: {cleanup}")
                    if isinstance(original, Exception) and not isinstance(cleanup, Exception):
                        raise
        result["status"] = "tools_available"
        return result
    except MissingDependency as exc:
        result.update(status="missing_dependency", error={"type": type(exc).__name__, "message": str(exc)})
    except Exception as exc:
        result.update(error={"type": type(exc).__name__, "message": str(exc)})
        from .process import Cancelled

        if isinstance(exc, Cancelled):
            result["status"] = "cancelled"
    return result
