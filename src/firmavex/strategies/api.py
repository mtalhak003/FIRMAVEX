"""Algorithm-independent strategy contract using only public evaluation records."""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.firmavex.evaluation.api import ExperimentResult, ExperimentSpec, TrialFeedback, TrialInput


ConfigValue = str | int | float | bool | None


@dataclass(frozen=True)
class StrategyMetadata:
    """Public configuration snapshot; scalar entries are canonicalized by key.

    A seed is explicit metadata, not a request to initialize global randomness.
    Configurations contain no mutable containers or executable objects.
    """

    name: str
    configuration: tuple[tuple[str, ConfigValue], ...] = ()
    seed: int | None = None

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("Strategy name must be a nonempty string.")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("Strategy seed must be an integer or None.")
        if type(self.configuration) is not tuple:
            raise ValueError("Strategy configuration must be an immutable tuple of pairs.")
        keys = set()
        for entry in self.configuration:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("Strategy configuration entries must be key/value pairs.")
            key, value = entry
            if type(key) is not str or not key or key in keys:
                raise ValueError("Strategy configuration keys must be unique nonempty strings.")
            if type(value) not in (str, int, float, bool, type(None)) or (type(value) is float and not math.isfinite(value)):
                raise ValueError("Strategy configuration values must be finite immutable scalars.")
            keys.add(key)
        object.__setattr__(self, "configuration", tuple(sorted(self.configuration)))


class SearchStrategy(Protocol):
    """Strategies receive records, never a session, executor, or callback.

    Return None from propose() to stop normally. Lifecycle callback exceptions
    propagate to the caller; their messages are never added to public records.
    """

    @property
    def metadata(self) -> StrategyMetadata: ...

    def start(self, description: ExperimentSpec) -> None: ...

    def propose(self) -> TrialInput | None: ...

    def observe(self, candidate: TrialInput, feedback: TrialFeedback) -> None: ...


class TerminationReason(str, Enum):
    FAILURE_DISCOVERED = "failure_discovered"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SESSION_ABORTED = "session_aborted"
    STRATEGY_STOPPED = "strategy_stopped"
    INVALID_OUTPUT = "invalid_strategy_output"


class InvalidOutputReason(str, Enum):
    CANDIDATE_TYPE = "candidate_type"
    WIDTH = "candidate_width"
    VALUES = "candidate_values"
    EVALUATOR_REJECTED = "evaluator_rejected"


@dataclass(frozen=True)
class StrategyRun:
    """One run, retaining the evaluator's actual immutable result unchanged."""

    evaluation: ExperimentResult
    strategy: StrategyMetadata
    termination: TerminationReason
    invalid_output: InvalidOutputReason | None = None
