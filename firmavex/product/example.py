"""Build the independent product example; never use research fixtures."""

from importlib.resources import files, as_file
import json
from pathlib import Path
import subprocess
import time

from firmavex.product.errors import ProductError
from firmavex.product.tools import _resolve, file_identity, _probe


def _compile(command, cancel_event):
    if cancel_event is None:
        return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    from .runtime import _spawn, _cleanup
    if cancel_event.is_set():
        raise KeyboardInterrupt("Example build cancelled.")
    process, stdout, stderr = _spawn(command)
    primary = None
    try:
        deadline = time.monotonic() + 60
        while process.poll() is None:
            if cancel_event.is_set():
                raise KeyboardInterrupt("Example build cancelled.")
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, 60)
            time.sleep(0.02)
        stdout.thread.join(timeout=2)
        stderr.thread.join(timeout=2)
        return subprocess.CompletedProcess(command, process.returncode, stdout.text(), stderr.text())
    except BaseException as exc:
        primary = exc
        raise
    finally:
        cleanup = _cleanup([("compiler", process, stdout, stderr)], primary)
        if not cleanup["success"] and primary is None:
            raise ProductError("cleanup_failure", "Compiler process cleanup failed.", cleanup)


def build_example(output_dir: Path, compiler: str | None = None, *, cancel_event=None) -> dict:
    output_dir = Path(output_dir).expanduser().absolute()
    # Exclusively own a fresh directory, including partial build diagnostics.
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ProductError("output_exists", "Example output must be a fresh directory.") from exc
    except OSError as exc:
        raise ProductError("output_unavailable", f"Unable to create example output: {exc}") from exc
    from .runtime_pack import active_tools
    executable = _resolve("arm-none-eabi-gcc", compiler or active_tools().get("compiler"))
    identity = file_identity(executable)
    identity["version"] = _probe([executable, "--version"]).stdout.splitlines()[0]
    resources = files("firmavex.product").joinpath("resources/example")
    source_identities = {}
    for name in ("main.c", "startup.c", "linker.ld"):
        data = resources.joinpath(name).read_bytes()
        path = output_dir / name
        path.write_bytes(data)
        source_identities[name] = file_identity(path)
    firmware = output_dir / "example.elf"
    command = [executable, "-mcpu=cortex-m3", "-mthumb", "-g", "-O0",
               "-ffreestanding", "-nostdlib", "-Wl,--build-id=none",
               "-T", str(output_dir / "linker.ld"),
               str(output_dir / "startup.c"), str(output_dir / "main.c"),
               "-o", str(firmware)]
    try:
        result = _compile(command, cancel_event)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProductError("build_failed", f"Example build failed: {exc}") from exc
    if result.returncode:
        raise ProductError("build_failed", "ARM compiler rejected the product example.",
                           {"stdout": result.stdout, "stderr": result.stderr})
    if file_identity(executable) != {key: identity[key] for key in ("path", "sha256", "size_bytes")}:
        raise ProductError("artifact_changed", "Compiler changed during example build.")
    config = example_configuration(executable)
    config_path = output_dir / "project.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    evidence = {"schema_version": 1, "compiler": identity, "command": command,
                "sources": source_identities, "firmware": file_identity(firmware),
                "safe_inputs": [0, 0], "triggering_inputs": [2, 1],
                "stdout": result.stdout, "stderr": result.stderr}
    (output_dir / "build.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return {"output_dir": str(output_dir), "firmware": str(firmware),
            "firmware_file": str(firmware), "config_file": str(config_path),
            "config": str(config_path), "command": command, "build": evidence}


def example_configuration(compiler=None):
    return {"schema_version": 1, "firmware": "example.elf",
              "input_symbols": ["product_inputs[0]", "product_inputs[1]"],
              "input_min": 0, "input_max": 3,
              "ready_breakpoint": "product_input_ready",
              "completion_breakpoint": "product_complete",
              "failure_symbol": "product_failure", "failure_value": 1,
              "execution_budget": 16, "strategy": "enumerative", "seed": None,
              "timeout_seconds": 10.0, "startup_timeout_seconds": 5.0,
              "collect_signature": True,
              "guided_archive_size": 32, "guided_mutation_attempts": 8,
              "compiler": compiler, "qemu": None, "gdb": None}
