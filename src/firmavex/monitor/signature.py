"""Private GDB collector and strict parser for a bounded guest-PC fingerprint."""

import re
from textwrap import dedent

from src.firmavex.evaluation.api import ExecutionSignature


MAX_PC_SAMPLES = 4096
DOMAIN_PREFIX = b"FIRMAVEX:guest-pc-sha256:v1\x00"
SIGNATURE_MARKER = "FIRMAVEX_SIGNATURE_V1="


def _collector_command() -> str:
    """GDB Python runs in the same stopped guest, not a second execution.

    Keep addresses inside GDB; emit only the digest after the exact existing
    completion breakpoint is hit. A capped prefix resumes to that breakpoint.
    """
    script = dedent(f"""
        import gdb
        import hashlib
        targets = gdb.breakpoints() or ()
        if len(targets) != 1 or targets[0].pending:
            raise gdb.GdbError("Signature collection requires one resolved completion breakpoint.")
        target = targets[0]
        events = []
        def on_stop(event):
            events.append(event)
        def reached_completion():
            return (len(events) == 1 and isinstance(events[0], gdb.BreakpointEvent)
                    and target in events[0].breakpoints)
        digest = hashlib.sha256({DOMAIN_PREFIX!r})
        complete = False
        gdb.events.stop.connect(on_stop)
        try:
            for _ in range({MAX_PC_SAMPLES}):
                pc = int(gdb.parse_and_eval("$pc"))
                if not 0 <= pc <= 0xffffffff:
                    raise gdb.GdbError("Signature collection observed a non-uint32 program counter.")
                digest.update(pc.to_bytes(4, "big"))
                events.clear()
                gdb.execute("stepi", to_string=True)
                if reached_completion():
                    complete = True
                    break
                if len(events) != 1 or type(events[0]) is not gdb.StopEvent:
                    raise gdb.GdbError("Signature collection encountered an unexpected execution stop.")
            truncated = not complete
            if truncated:
                events.clear()
                gdb.execute("continue", to_string=True)
                if not reached_completion():
                    raise gdb.GdbError("Signature continuation did not reach the completion breakpoint.")
            digest.update(bytes([int(truncated)]))
            gdb.write({SIGNATURE_MARKER!r} + digest.hexdigest() + ":" + str(int(truncated)) + "\\n")
        finally:
            gdb.events.stop.disconnect(on_stop)
    """)
    return f"python exec({script!r})"


def _parse_signature(stdout: str) -> ExecutionSignature:
    lines = [line for line in stdout.splitlines() if line.startswith(SIGNATURE_MARKER)]
    if len(lines) != 1:
        raise ValueError("Expected exactly one runtime-signature marker.")
    match = re.fullmatch(re.escape(SIGNATURE_MARKER) + r"([0-9a-f]{64}):([01])", lines[0])
    if match is None:
        raise ValueError("Malformed runtime-signature marker.")
    return ExecutionSignature(match[1], match[2] == "1")
