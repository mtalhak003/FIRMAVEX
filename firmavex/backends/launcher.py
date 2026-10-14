"""Private child admission for source and frozen applications, not a sandbox.

Waiting for stdin lets the parent establish Windows Job ownership before tools
run. Only the trusted execution supervisor should send this private protocol.
"""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
from .api import Limits

MAX_ADMISSION_BYTES = 65536


def validate(record):
    if type(record) is not dict or set(record) != {"schema_version", "argv", "limits"}:
        raise ValueError("Invalid child admission fields")
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("Unsupported child admission version")
    args = record["argv"]
    if type(args) is not list or not 1 <= len(args) <= 1024:
        raise ValueError("Invalid child argv")
    if any(type(arg) is not str or "\x00" in arg for arg in args):
        raise ValueError("Child arguments must be NUL-free strings")
    executable = Path(args[0])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("Child executable must be an existing absolute regular file")
    if type(record["limits"]) is not dict:
        raise ValueError("Invalid child resource limits")
    limits = Limits(**record["limits"])
    return args, limits


def apply_posix_limits(limits):
    import resource
    requested = ((resource.RLIMIT_AS, limits.memory_bytes),
                 (resource.RLIMIT_FSIZE, limits.artifact_bytes),
                 (resource.RLIMIT_CPU, math.ceil(limits.timeout_seconds)+1),
                 (resource.RLIMIT_CORE, 0))
    for kind, value in requested:
        inherited_soft, inherited_hard = resource.getrlimit(kind)
        # Never raise an inherited hard limit (notably on Darwin runners).
        finite = [cap for cap in (value,inherited_soft,inherited_hard) if cap != resource.RLIM_INFINITY]
        effective = min(finite)
        try:
            resource.setrlimit(kind, (effective,effective))
        except (OSError,ValueError) as exc:
            raise RuntimeError(f'Resource limit {kind} failed: requested={value}, inherited={(inherited_soft,inherited_hard)}, effective={effective}: {exc}') from exc


def main():
    try:
        payload = sys.stdin.buffer.readline(MAX_ADMISSION_BYTES + 1)
        if not payload.endswith(b"\n") or len(payload) > MAX_ADMISSION_BYTES:
            raise ValueError("Missing or oversized child admission")
        args, limits = validate(json.loads(payload))
        if os.name == "posix":
            apply_posix_limits(limits)
            os.execv(args[0], args)
        elif os.name == "nt":
            child = subprocess.Popen(args, stdin=subprocess.DEVNULL, close_fds=True)
            return child.wait()
        else:
            raise RuntimeError("Unsupported child execution platform")
    except Exception as exc:
        print(f"Backend child admission failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
