"""Shared debug-firmware build for the QEMU mps2-an385 Cortex-M3 target."""

import shutil
import subprocess
import tempfile
from pathlib import Path


SUPPORT_DIR = Path(__file__).resolve().parents[3] / "firmware/benchmarks/cortex_m"


def build_cortex_m_firmware(
    source_file: str | Path,
    output_file: str | Path,
    *,
    extra_sources: tuple[str | Path, ...] = (),
) -> dict:
    """Build a fresh ELF with symbols, without modifying source files.

    All benchmark and legacy fixture builds use this command. Diagnostics use
    the native compiler result convention; missing prerequisites return -1.
    """
    source = Path(source_file).resolve()
    output = Path(output_file).resolve()
    sources = [(SUPPORT_DIR / "startup.c").resolve(), source]
    sources.extend(Path(path).resolve() for path in extra_sources)
    linker = (SUPPORT_DIR / "linker.ld").resolve()
    result = {
        "success": False,
        "source_file": str(source),
        "output_file": str(output),
        "stdout": "",
        "stderr": "",
        "return_code": -1,
    }
    if output in [*sources, linker]:
        result["stderr"] = f"Unsafe output path: {output} resolves to a build input."
        return result
    for path in [*sources, linker]:
        if not path.is_file():
            result["stderr"] = f"Build input not found: {path}"
            return result

    compiler = shutil.which("arm-none-eabi-gcc")
    if compiler is None:
        result["stderr"] = (
            "ARM toolchain unavailable: arm-none-eabi-gcc was not found on PATH. "
            "Install the GNU Arm embedded toolchain (Debian: gcc-arm-none-eabi) "
            "and add its bin directory to PATH."
        )
        return result

    command = [
        compiler, "-mcpu=cortex-m3", "-mthumb", "-g", "-O0",
        "-ffreestanding", "-nostdlib", "-Wl,--build-id=none",
        "-T", str(linker), *(str(path) for path in sources),
    ]
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
            built_image = Path(temporary) / "firmware.elf"
            completed = subprocess.run(
                [*command, "-o", str(built_image)],
                cwd=SUPPORT_DIR.parents[2], capture_output=True, text=True,
            )
            if completed.returncode == 0:
                built_image.replace(output)
    except OSError as exc:
        result["stderr"] = f"Unable to build Cortex-M3 firmware: {exc}"
        return result
    result.update(
        success=completed.returncode == 0,
        stdout=completed.stdout,
        stderr=completed.stderr,
        return_code=completed.returncode,
    )
    return result
