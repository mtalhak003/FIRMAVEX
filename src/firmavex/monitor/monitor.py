import re
import subprocess
import time
from pathlib import Path


def observe_symbol(
    firmware_file: str,
    symbol: str,
    breakpoint: str,
    timeout: float = 5.0,
    set_symbol: str | None = None,
    set_value: int | None = None,
) -> dict:
    """Run Cortex-M3 firmware and observe a symbol at a GDB breakpoint."""

    firmware = Path(firmware_file)

    if not firmware.exists():
        return {
            "success": False,
            "symbol": symbol,
            "value": None,
            "stdout": "",
            "stderr": f"Firmware file not found: {firmware}",
        }

    qemu_command = [
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
        "-S",
        "-gdb",
        "tcp::1234",
    ]

    qemu = subprocess.Popen(
        qemu_command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        time.sleep(0.5)

        gdb_command = [
            "arm-none-eabi-gdb",
            str(firmware),
            "--batch",
            "-ex",
            "target remote localhost:1234",
        ]

        if set_symbol is not None and set_value is not None:
            gdb_command.extend([
                "-ex",
                f"set variable {set_symbol} = {set_value}",
            ])

        gdb_command.extend([
            "-ex",
            f"break {breakpoint}",
            "-ex",
            "continue",
            "-ex",
            f'printf "FIRMAVEX_VALUE=0x%x\\n", {symbol}',
        ])

        result = subprocess.run(
            gdb_command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        match = re.search(
            r"FIRMAVEX_VALUE=0x([0-9a-fA-F]+)",
            result.stdout,
        )

        if result.returncode != 0 or match is None:
            return {
                "success": False,
                "symbol": symbol,
                "value": None,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        return {
            "success": True,
            "symbol": symbol,
            "value": int(match.group(1), 16),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    finally:
        qemu.terminate()

        try:
            qemu.wait(timeout=2)
        except subprocess.TimeoutExpired:
            qemu.kill()
            qemu.wait()
