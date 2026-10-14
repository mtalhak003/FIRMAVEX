"""Compatibility allowlists backed by actual native CI, never sandbox claims."""

import json
import os
import platform
from importlib.resources import files
from .tools import find_many
from firmavex.product.tools import file_identity


def require_windows_qualification(profile):
    if os.name != "nt":
        return
    if os.environ.get("FIRMAVEX_QUALIFY_BACKENDS") == "1":
        return  # Explicit administrator candidate qualification, not public support.
    record = json.loads(
        files("firmavex.backends")
        .joinpath("native_profiles.json")
        .read_text(encoding="utf-8")
    )
    if (
        type(record) is not dict
        or type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
        or type(record.get("profiles")) is not list
    ):
        raise RuntimeError("Invalid native compatibility catalog")
    machine = platform.machine().lower()
    architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
    for candidate in record["profiles"]:
        if (
            candidate.get("system") != "Windows"
            or candidate.get("architecture") != architecture
            or candidate.get("profile") != profile
        ):
            continue
        expected = candidate.get("tools")
        names = (
            {"qemu-system-riscv32", "gdb-multiarch"}
            if profile == "riscv32-virt"
            else {"iverilog", "vvp"}
        )
        if type(expected) is not dict or set(expected) != names:
            raise RuntimeError("Incomplete native compatibility catalog")
        selected = find_many(sorted(names))
        if all(
            file_identity(selected[name])["sha256"] == expected[name]["sha256"]
            for name in names
        ):
            return
    raise RuntimeError(
        "This native Windows runtime has not passed the recorded source/frozen/installed qualification. Use the documented verified runtime or explicit administrator candidate qualification."
    )
