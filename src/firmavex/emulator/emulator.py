import subprocess
from pathlib import Path


def run_firmware(firmware_file: str, timeout: float = 1.0) -> dict:
    """
    Run a Cortex-M3 firmware image using QEMU.

    Returns a dictionary containing:
    - success: whether QEMU successfully executed the firmware
    - firmware_file: firmware image path
    - stdout: emulator standard output
    - stderr: emulator error output
    - return_code: emulator exit code, or None if stopped by timeout
    - timed_out: whether FIRMAVEX stopped execution after the time limit
    """

    firmware = Path(firmware_file)

    if not firmware.exists():
        return {
            "success": False,
            "firmware_file": str(firmware),
            "stdout": "",
            "stderr": f"Firmware file not found: {firmware}",
            "return_code": -1,
            "timed_out": False,
        }

    command = [
        "qemu-system-arm",
        "-M",
        "mps2-an385",
        "-kernel",
        str(firmware),
        "-display",
        "none",
        "-serial",
        "null",
        "-monitor",
        "none",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "success": True,
            "firmware_file": str(firmware),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "return_code": None,
            "timed_out": True,
        }

    return {
        "success": result.returncode == 0,
        "firmware_file": str(firmware),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "return_code": result.returncode,
        "timed_out": False,
    }
