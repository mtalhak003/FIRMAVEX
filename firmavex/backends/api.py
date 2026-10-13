"""Version 1 heterogeneous execution contract. No debugger objects cross it."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from types import MappingProxyType
import math
import threading


@dataclass(frozen=True)
class Capabilities:
    methods: tuple[str, ...]
    input_kind: str
    waveforms: bool = False
    hardware: bool = False
    sandboxed: bool = False
    resource_policy: str = "legacy project configuration"


@dataclass(frozen=True)
class TargetProfile:
    id: str
    architecture: str
    tool_names: tuple[str, ...]
    capabilities: Capabilities
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


profiles = MappingProxyType(
    {
        "cortex-m3-mps2": TargetProfile(
            "cortex-m3-mps2",
            "armv7-m",
            ("qemu-system-arm", "arm-none-eabi-gdb"),
            Capabilities(("search",), "legacy-product-project"),
        ),
        "riscv32-virt": TargetProfile(
            "riscv32-virt",
            "rv32im",
            ("qemu-system-riscv32", "gdb-multiarch"),
            Capabilities(
                ("symbol-observation",),
                "uint32-vector",
                resource_policy="shared wall, per-child CPU, address-space, file and log limits",
            ),
        ),
        "verilog-icarus": TargetProfile(
            "verilog-icarus",
            "verilog",
            ("iverilog", "vvp"),
            Capabilities(
                ("testbench",),
                "source-testbench",
                True,
                resource_policy="shared wall, per-child CPU, address-space, file and log limits",
            ),
        ),
    }
)


@dataclass(frozen=True)
class Limits:
    timeout_seconds: float = 10
    log_bytes: int = 524288
    artifact_bytes: int = 16777216
    memory_bytes: int = 2147483648

    def __post_init__(self):
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 3600
        ):
            raise ValueError("Invalid wall-clock limit")
        if (
            type(self.memory_bytes) is not int
            or not 67108864 <= self.memory_bytes <= 8589934592
        ):
            raise ValueError("Invalid address-space limit")
        for value in (self.log_bytes, self.artifact_bytes):
            if type(value) is not int or not 1024 <= value <= 67108864:
                raise ValueError("Invalid byte limit")


@dataclass(frozen=True)
class Request:
    profile: str
    source: Path
    values: tuple[int, ...] = ()
    limits: Limits = Limits()
    schema_version: int = 1

    def __post_init__(self):
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or type(self.profile) is not str
            or self.profile not in profiles
        ):
            raise ValueError("Unsupported request/profile version")
        if type(self.source) is not Path and not isinstance(self.source, Path):
            raise ValueError("source must be a Path")
        if type(self.values) is not tuple or any(
            type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in self.values
        ):
            raise ValueError("Inputs must be immutable uint32 values")
        if type(self.limits) is not Limits:
            raise ValueError("limits must be an exact Limits record")
        if self.profile == "cortex-m3-mps2" and self.limits != Limits():
            raise ValueError(
                "ARM limits remain owned by its existing project configuration"
            )
        if self.profile == "riscv32-virt" and len(self.values) != 2:
            raise ValueError("RV32 example contract requires two inputs")
        if self.profile != "riscv32-virt" and self.values:
            raise ValueError("This profile does not accept vector arguments")


@dataclass(frozen=True)
class Result:
    status: str
    evidence: dict
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


class Backend(Protocol):
    profile: TargetProfile

    def execute(
        self, request: Request, output: Path, cancel: threading.Event
    ) -> Result: ...


def request_to_dict(request):
    """Wire form for local integrations; source denotes an explicitly local file."""
    if type(request) is not Request:
        raise ValueError("Exact Request required")
    return {
        "schema_version": request.schema_version,
        "profile": request.profile,
        "source": str(request.source),
        "values": list(request.values),
        "limits": asdict(request.limits),
    }


def request_from_dict(record):
    if type(record) is not dict or set(record) != {
        "schema_version",
        "profile",
        "source",
        "values",
        "limits",
    }:
        raise ValueError("Invalid request fields")
    if (
        type(record["source"]) is not str
        or not record["source"]
        or type(record["values"]) is not list
        or type(record["limits"]) is not dict
    ):
        raise ValueError("Invalid request wire types")
    try:
        return Request(
            record["profile"],
            Path(record["source"]),
            tuple(record["values"]),
            Limits(**record["limits"]),
            record["schema_version"],
        )
    except TypeError as exc:
        raise ValueError("Invalid limit fields") from exc
