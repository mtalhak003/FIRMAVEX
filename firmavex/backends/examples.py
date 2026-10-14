"""Independent, reproducible source builds; never cloud-built firmware."""

from importlib.resources import files
from pathlib import Path
import threading
from .api import Limits
from .process import Processes
from .implementations import tool, finish
from .engine import _write
from firmavex.product.tools import file_identity


def prepare(profile, output):
    from .security import fresh_directory
    output = fresh_directory(output)
    resources = files("firmavex.backends").joinpath("examples")
    if profile == "verilog-icarus":
        path = output / "counter.v"
        path.write_bytes(resources.joinpath("counter.v").read_bytes())
        record = {
            "schema_version": 1,
            "profile": profile,
            "source": file_identity(path),
            "execution_performed": False,
        }
    elif profile == "riscv32-virt":
        for name in ("riscv.c", "riscv.S", "riscv.ld"):
            (output / name).write_bytes(resources.joinpath(name).read_bytes())
        compiler = tool("riscv64-unknown-elf-gcc")
        compiler_identity = file_identity(compiler)
        processes = Processes(threading.Event(), Limits(60))
        primary = None
        flags = [
            "-march=rv32im",
            "-mabi=ilp32",
            "-g",
            "-O0",
            "-ffreestanding",
            "-nostdlib",
            "-Wl,--build-id=none",
            f"-ffile-prefix-map={output}=example",
        ]
        try:
            code, version, errors = processes.run([compiler, "--version"], output)
            if code:
                raise RuntimeError(errors)
            for source, object_name in (
                ("riscv.S", "startup.o"),
                ("riscv.c", "main.o"),
            ):
                code, stdout, stderr = processes.run(
                    [
                        compiler,
                        *flags,
                        "-c",
                        str(output / source),
                        "-o",
                        str(output / object_name),
                    ],
                    output,
                )
                if code:
                    raise RuntimeError("Compiler failed: " + stderr)
            command = [
                compiler,
                *flags,
                "-T",
                str(output / "riscv.ld"),
                str(output / "startup.o"),
                str(output / "main.o"),
                "-o",
                str(output / "firmware.elf"),
            ]
            code, stdout, stderr = processes.run(command, output)
            if code:
                raise RuntimeError("Linker failed: " + stderr)
            if file_identity(compiler) != compiler_identity:
                raise RuntimeError("Compiler changed during example build")
            record = {
                "schema_version": 1,
                "profile": profile,
                "compiler": {
                    "identity": compiler_identity,
                    "version": version.splitlines()[0],
                },
                "flags": flags,
                "sources": {
                    name: file_identity(output / name)
                    for name in ("riscv.c", "riscv.S", "riscv.ld")
                },
                "firmware": file_identity(output / "firmware.elf"),
                "execution_performed": False,
                "stdout": stdout,
                "stderr": stderr,
            }
        except BaseException as exc:
            primary = exc
            raise
        finally:
            finish(processes, primary)
    else:
        raise ValueError("Use the established prepare-example command for ARM")
    _write(output / "build.json", record)
    return record
