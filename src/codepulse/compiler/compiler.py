import subprocess
from pathlib import Path


def compile_firmware(source_file: str, output_file: str) -> dict:
    """
    Compile a C firmware source file using GCC.

    Returns a dictionary containing:
    - success: whether compilation succeeded
    - source_file: input source path
    - output_file: generated executable path
    - stdout: compiler standard output
    - stderr: compiler error output
    - return_code: GCC exit code
    """

    source = Path(source_file)
    output = Path(output_file)

    if not source.exists():
        return {
            "success": False,
            "source_file": str(source),
            "output_file": str(output),
            "stdout": "",
            "stderr": f"Source file not found: {source}",
            "return_code": -1,
        }

    result = subprocess.run(
        [
            "gcc",
            str(source),
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    return {
        "success": result.returncode == 0,
        "source_file": str(source),
        "output_file": str(output),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "return_code": result.returncode,
    }