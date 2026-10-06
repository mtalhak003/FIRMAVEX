import re
import socket
import subprocess
import time
from pathlib import Path


def _allocate_gdb_port() -> int:
    """Ask the OS for a free IPv4 loopback port, then release it for QEMU."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


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

    def failure(message: str, stdout: str = "") -> dict:
        return {
            "success": False, "symbol": symbol, "value": None,
            "stdout": stdout, "stderr": message,
        }

    if not firmware.exists():
        return {
            "success": False,
            "symbol": symbol,
            "value": None,
            "stdout": "",
            "stderr": f"Firmware file not found: {firmware}",
        }

    try:
        port = _allocate_gdb_port()
    except OSError as exc:
        return failure(f"Unable to allocate a localhost GDB port: {exc}")

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
        f"tcp:127.0.0.1:{port}",
    ]

    try:
        qemu = subprocess.Popen(
            qemu_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return failure(f"Unable to start QEMU: {exc}")

    try:
        time.sleep(0.5)
        if qemu.poll() is not None:
            return failure(f"QEMU exited before observation: {qemu.stderr.read()}")

        gdb_command = [
            "arm-none-eabi-gdb",
            str(firmware),
            "--batch",
            "-ex",
            f"target remote 127.0.0.1:{port}",
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

        if qemu.poll() is not None:
            return failure(f"QEMU exited during observation: {qemu.stderr.read()}", result.stdout)

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

    except subprocess.TimeoutExpired:
        return failure(f"GDB observation timed out after {timeout} seconds.")
    except OSError as exc:
        return failure(f"Unable to run GDB observation: {exc}")
    finally:
        try:
            if qemu.poll() is None:
                qemu.terminate()
            try:
                qemu.wait(timeout=2)
            except subprocess.TimeoutExpired:
                qemu.kill()
                qemu.wait()
        finally:
            qemu.stderr.close()
