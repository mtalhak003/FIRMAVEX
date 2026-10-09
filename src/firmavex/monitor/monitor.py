import re
import socket
import subprocess
import time
from pathlib import Path

from src.firmavex.monitor.signature import _collector_command, _parse_signature


def _allocate_gdb_port() -> int:
    """Ask the OS for a free IPv4 loopback port, then release it for QEMU."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _cleanup_qemu(qemu: subprocess.Popen, primary: BaseException | None) -> None:
    """Attempt every cleanup stage without replacing an active exception."""
    errors: list[tuple[str, BaseException]] = []

    def attempt(operation, action):
        try:
            action()
        except BaseException as exc:
            errors.append((operation, exc))

    try:
        running = qemu.poll() is None
    except BaseException as exc:
        errors.append(("poll", exc))
        running = True
    if running:
        attempt("terminate", qemu.terminate)
    try:
        qemu.wait(timeout=2)
        reaped = True
    except subprocess.TimeoutExpired:
        # A process that ignores termination still gets the normal kill path.
        reaped = False
    except BaseException as exc:
        errors.append(("wait", exc))
        reaped = False
    if not reaped:
        attempt("kill", qemu.kill)
        # A failed kill must not turn cancellation into an unbounded wait.
        attempt("reap", lambda: qemu.wait(timeout=2))
    attempt("stderr close", lambda: qemu.stderr.close())

    if errors:
        # Preserve an original cancellation. A new cleanup cancellation must
        # outrank ordinary errors, including an ordinary observation error.
        cancellation = next(
            (exc for _, exc in errors if not isinstance(exc, Exception)), None,
        )
        error = (
            primary if primary is not None and not isinstance(primary, Exception)
            else cancellation if cancellation is not None
            else primary if primary is not None else errors[0][1]
        )
        for operation, secondary in errors:
            try:
                detail = str(secondary)
            except BaseException:
                detail = "<diagnostic unavailable>"
            try:
                error.add_note(
                    f"QEMU cleanup {operation} failed: "
                    f"{type(secondary).__name__}: {detail}"
                )
            except BaseException:
                # Diagnostic formatting must not replace cancellation either.
                pass
        if error is not primary:
            if primary is not None:
                # Keep the preceding observation error administrator-visible
                # while allowing the newly requested cancellation to propagate.
                raise error from primary
            raise error


def observe_symbol(
    firmware_file: str,
    symbol: str,
    breakpoint: str,
    timeout: float = 5.0,
    set_symbol: str | None = None,
    set_value: int | None = None,
    *,
    input_values: dict[str, int] | None = None,
    collect_signature: bool = False,
) -> dict:
    """Run Cortex-M3 firmware and observe a symbol at a GDB breakpoint."""

    firmware = Path(firmware_file)

    def failure(message: str, stdout: str = "") -> dict:
        return {
            "success": False, "symbol": symbol, "value": None,
            "stdout": stdout, "stderr": message,
        }

    if type(collect_signature) is not bool:
        return failure("collect_signature must be a boolean.")
    if input_values is not None and set_symbol is not None:
        return failure("Use either input_values or set_symbol, not both.")
    if input_values is not None and (type(input_values) is not dict or any(
        type(name) is not str
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?", name) is None
        or type(value) is not int or not 0 <= value <= 0xFFFFFFFF
        for name, value in input_values.items()
    )):
        return failure("Inputs must name scalar symbols/array elements with uint32 values.")

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

    primary = None
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

        if input_values is not None:
            for name, value in input_values.items():
                gdb_command.extend(["-ex", f"set variable {name} = {value}"])

        gdb_command.extend([
            "-ex",
            f"break {breakpoint}",
            "-ex",
            _collector_command() if collect_signature else "continue",
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

        observation = {
            "success": True,
            "symbol": symbol,
            "value": int(match.group(1), 16),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if collect_signature:
            try:
                observation["execution_signature"] = _parse_signature(result.stdout)
            except ValueError as exc:
                return failure(f"{result.stderr}\nRuntime signature collection failed: {exc}".strip(), result.stdout)
        return observation

    except subprocess.TimeoutExpired as exc:
        # subprocess may provide bytes even when text=True. Keep partial
        # collection diagnostics administrator-owned, never as a signature.
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        return failure(f"{stderr}\nGDB observation timed out after {timeout} seconds.".strip(), stdout)
    except OSError as exc:
        return failure(f"Unable to run GDB observation: {exc}")
    except BaseException as exc:
        # sys.exc_info() can inherit an unrelated caller's active handler.
        # Only this observation's propagating exception owns its cleanup.
        primary = exc
        raise
    finally:
        _cleanup_qemu(qemu, primary)
