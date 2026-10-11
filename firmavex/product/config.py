"""Versioned, immutable user-project configuration; no debugger expressions."""

from dataclasses import dataclass, fields
import json
import math
from pathlib import Path
import re

from src.firmavex.evaluation.api import InputSpace
from src.firmavex.strategies.api import StrategyMetadata
from src.firmavex.strategies.guided import guided_metadata
from firmavex.product.errors import ProductError


SCHEMA_VERSION = 1
UINT32_MAX = (1 << 32) - 1
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
BINDING = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(0|[1-9][0-9]*)\])?\Z")


def _invalid(message: str) -> None:
    raise ProductError("invalid_configuration", message)


@dataclass(frozen=True, kw_only=True)
class ProductConfig:
    firmware: Path
    input_symbols: tuple[str, ...]
    ready_breakpoint: str
    completion_breakpoint: str
    failure_symbol: str
    input_min: int = 0
    input_max: int = 15
    failure_value: int = 1
    execution_budget: int = 64
    strategy: str = "enumerative"
    seed: int | None = None
    timeout_seconds: float = 10.0
    startup_timeout_seconds: float = 5.0
    collect_signature: bool = True
    guided_archive_size: int = 32
    guided_mutation_attempts: int = 8
    qemu: str | None = None
    gdb: str | None = None
    compiler: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.firmware, Path):
            _invalid("firmware must be a pathlib.Path.")
        object.__setattr__(self, "firmware", self.firmware.expanduser().resolve())
        if type(self.input_symbols) is not tuple or not self.input_symbols:
            _invalid("input_symbols must be a nonempty immutable tuple.")
        for name in (*self.input_symbols, self.failure_symbol):
            if type(name) is not str or BINDING.fullmatch(name) is None:
                _invalid("Input and failure bindings must be C identifiers or one array element.")
        if len(set(self.input_symbols)) != len(self.input_symbols):
            _invalid("Input bindings must be distinct.")
        if self.failure_symbol in self.input_symbols:
            _invalid("The failure binding must not also be an input.")
        for name in (self.ready_breakpoint, self.completion_breakpoint):
            if type(name) is not str or IDENTIFIER.fullmatch(name) is None:
                _invalid("Breakpoints must be plain C function names.")
        if self.ready_breakpoint == self.completion_breakpoint:
            _invalid("Input-ready and completion breakpoints must be distinct.")
        for key in ("input_min", "input_max", "failure_value"):
            value = getattr(self, key)
            if type(value) is not int or not 0 <= value <= UINT32_MAX:
                _invalid(f"{key} must be an unsigned 32-bit integer.")
        if self.input_min > self.input_max:
            _invalid("input_min must not exceed input_max.")
        if type(self.execution_budget) is not int or not 1 <= self.execution_budget <= 1_000_000:
            _invalid("execution_budget must be an integer from 1 to 1000000.")
        for key in ("timeout_seconds", "startup_timeout_seconds"):
            value = getattr(self, key)
            if type(value) not in (int, float) or not 0 < value <= 3600 or not math.isfinite(value):
                _invalid(f"{key} must be a finite positive number no greater than 3600.")
            object.__setattr__(self, key, float(value))
        if type(self.collect_signature) is not bool:
            _invalid("collect_signature must be a boolean.")
        if type(self.strategy) is not str or self.strategy not in {"enumerative", "random", "guided"}:
            _invalid("strategy must be enumerative, random, or guided.")
        if self.strategy == "enumerative":
            if self.seed is not None:
                _invalid("The enumerative strategy must not have a seed.")
        elif type(self.seed) is not int:
            _invalid("Random and guided strategies require an explicit integer seed.")
        for key in ("guided_archive_size", "guided_mutation_attempts"):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= 1_000_000:
                _invalid(f"{key} must be an integer from 1 to 1000000.")
        if self.strategy == "guided" and not self.collect_signature:
            _invalid("Guided search requires runtime signature collection.")
        for key in ("qemu", "gdb", "compiler"):
            value = getattr(self, key)
            if value is not None and (type(value) is not str or not value.strip()
                                      or any(ord(char) < 32 for char in value)):
                _invalid(f"{key} must be a nonempty executable path or null.")

    @property
    def input_space(self) -> InputSpace:
        return InputSpace(len(self.input_symbols), self.input_min, self.input_max)

    @property
    def strategy_metadata(self) -> StrategyMetadata:
        if self.strategy == "guided":
            return guided_metadata(self.seed, archive_size=self.guided_archive_size,
                                   mutation_attempts=self.guided_mutation_attempts)
        return StrategyMetadata(self.strategy, seed=self.seed)

    def to_dict(self) -> dict:
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["firmware"] = str(self.firmware)
        result["input_symbols"] = list(self.input_symbols)
        return {"schema_version": SCHEMA_VERSION, **result}

    @classmethod
    def from_dict(cls, data: dict, *, base_dir: Path = Path(".")) -> "ProductConfig":
        if type(data) is not dict:
            _invalid("Project configuration must be a JSON object.")
        if type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
            _invalid("Unsupported or missing project schema_version; expected 1.")
        allowed = {field.name for field in fields(cls)} | {"schema_version"}
        unknown = set(data) - allowed
        if unknown:
            _invalid(f"Unknown project fields: {', '.join(sorted(map(str, unknown)))}.")
        values = {key: value for key, value in data.items() if key != "schema_version"}
        if type(values.get("firmware")) is not str or not values["firmware"].strip():
            _invalid("firmware must be a nonempty path string.")
        values["firmware"] = Path(base_dir) / Path(values["firmware"]).expanduser()
        if type(values.get("input_symbols")) is not list:
            _invalid("input_symbols must be a JSON array.")
        values["input_symbols"] = tuple(values["input_symbols"])
        try:
            return cls(**values)
        except TypeError as exc:
            raise ProductError("invalid_configuration", f"Missing required project fields: {exc}") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def load_config(path: str | Path) -> ProductConfig:
    path = Path(path).expanduser().resolve()
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: _invalid(f"Non-finite JSON value: {value}."))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProductError("invalid_configuration", f"Unable to read project configuration: {exc}") from exc
    return ProductConfig.from_dict(data, base_dir=path.parent)
