"""Actual tool availability probes, never a claim of native qualification."""

import os
from pathlib import Path
import tempfile
import threading
from .api import Limits, profiles
from .implementations import finish, tool
from .process import Processes
from firmavex.product.tools import file_identity


def check(profile):
    if profile not in profiles:
        raise ValueError("Unsupported profile")
    if profile == "cortex-m3-mps2":
        from firmavex.product.services import doctor

        return doctor()
    if os.name != "posix":
        return {
            "status": "unsupported_platform",
            "profile": profile,
            "reason": "New native Windows backends have not been qualified",
        }
    processes = Processes(threading.Event(), Limits())
    primary = None
    tools = {}
    try:
        with tempfile.TemporaryDirectory(prefix="firmavex-backend-probe-") as directory:
            for name in profiles[profile].tool_names:
                path = tool(name)
                code, out, err = processes.run(
                    [path, "-V" if profile == "verilog-icarus" else "--version"],
                    Path(directory),
                )
                if code:
                    raise RuntimeError(f"Capability probe failed for {name}: {err}")
                tools[name] = {
                    "identity": file_identity(path),
                    "version": (out or err).splitlines()[0],
                }
        return {
            "status": "tools_available",
            "profile": profiles[profile].to_dict(),
            "tools": tools,
            "guest_execution_performed": False,
            "native_qualification": "not established by version probes",
        }
    except BaseException as exc:
        primary = exc
        raise
    finally:
        finish(processes, primary)
