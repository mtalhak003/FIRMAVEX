"""Strategy-facing records and protocol: no build metadata or evaluator oracle."""

from dataclasses import dataclass
from collections.abc import Callable
import re
from typing import Literal, Protocol


@dataclass(frozen=True)
class InputSpace:
    """Exactly `width` ordered uint32 values, each within inclusive bounds."""

    width: int
    minimum: int
    maximum: int

    def accepts(self, values: tuple[int, ...]) -> bool:
        return (
            type(values) is tuple and len(values) == self.width
            and all(type(value) is int and self.minimum <= value <= self.maximum for value in values)
        )


@dataclass(frozen=True)
class TrialInput:
    values: tuple[int, ...]


@dataclass(frozen=True)
class ExperimentSpec:
    benchmark_id: str
    input_space: InputSpace
    execution_budget: int


TrialStatus = Literal[
    "safe", "triggered", "infrastructure_failure", "budget_exhausted",
    "invalid_input", "session_aborted",
]


@dataclass(frozen=True)
class ExecutionSignature:
    """Opaque SHA-256 of an ordered, bounded guest-PC sequence (version 1).

    Equality is meaningful within an equivalent image/runtime environment,
    not a claim of coverage or complete path identity.
    """

    digest: str
    truncated: bool = False

    def __post_init__(self) -> None:
        if type(self.digest) is not str or re.fullmatch(r"[0-9a-f]{64}", self.digest) is None:
            raise ValueError("Execution signature must be a lowercase 64-character SHA-256 digest.")
        if type(self.truncated) is not bool:
            raise ValueError("Execution-signature truncation must be a boolean.")


def _validate_execution_signature(signature: ExecutionSignature) -> None:
    if type(signature) is not ExecutionSignature:
        raise ValueError("Execution signature must be a canonical immutable ExecutionSignature.")
    # Recheck at the observation boundary, including deliberately forged records.
    ExecutionSignature.__post_init__(signature)


@dataclass(frozen=True)
class TrialFeedback:
    status: TrialStatus
    execution_index: int | None
    budget_remaining: int
    execution_signature: ExecutionSignature | None = None

    def __post_init__(self) -> None:
        if self.execution_signature is not None:
            _validate_execution_signature(self.execution_signature)
            if self.status not in {"safe", "triggered"}:
                raise ValueError("Only successful execution feedback may contain a signature.")


@dataclass(frozen=True)
class ExperimentResult:
    benchmark_id: str
    strategy_id: str
    execution_budget: int
    attempted_executions: int
    successful_executions: int
    infrastructure_failures: int
    failure_triggering_executions: int
    failure_found: bool
    first_failure_execution: int | None
    time_to_first_failure_seconds: float | None
    budget_remaining: int
    budget_exhausted: bool
    aborted: bool
    random_seed: int | None
    reproducibility: bool | None  # Not measured by this single-session runner.


class StrategySession(Protocol):
    def describe(self) -> ExperimentSpec: ...
    def execute(self, trial: TrialInput) -> TrialFeedback: ...
    def result(self) -> ExperimentResult: ...


class StrategyHandle:
    """Only the three strategy operations, ready for a later transport adapter.

    Callbacks remain introspectable in-process; this is not a security sandbox.
    """

    __slots__ = ("_describe", "_execute", "_result")

    def __init__(
        self, describe: Callable[[], ExperimentSpec],
        execute: Callable[[TrialInput], TrialFeedback],
        result: Callable[[], ExperimentResult],
    ):
        self._describe, self._execute, self._result = describe, execute, result

    def describe(self) -> ExperimentSpec:
        return self._describe()

    def execute(self, trial: TrialInput) -> TrialFeedback:
        return self._execute(trial)

    def result(self) -> ExperimentResult:
        return self._result()
