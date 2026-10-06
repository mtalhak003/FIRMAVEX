"""Lexicographic Cartesian enumeration without materializing the domain."""

from src.firmavex.evaluation.api import ExperimentSpec, InputSpace, TrialFeedback, TrialInput
from src.firmavex.strategies.api import StrategyMetadata


class EnumerativeStrategy:
    """Enumerate the evaluator-validated public space, last position fastest.

    start() always resets the cursor, including after exhaustion. Feedback is
    deliberately ignored: the common runner controls execution and termination.
    No budget, discovery index, domain cardinality, or visited set is maintained.
    """

    def __init__(self) -> None:
        self._metadata = StrategyMetadata("enumerative")
        self._space: InputSpace | None = None
        self._next: list[int] | None = None

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    def start(self, description: ExperimentSpec) -> None:
        # EvaluationSession already validates width and inclusive uint32 bounds.
        self._space = description.input_space
        self._next = [self._space.minimum] * self._space.width

    def propose(self) -> TrialInput | None:
        if self._space is None:
            raise RuntimeError("EnumerativeStrategy must be started before proposing candidates.")
        if self._next is None:
            return None
        candidate = TrialInput(tuple(self._next))
        for position in range(self._space.width - 1, -1, -1):
            if self._next[position] < self._space.maximum:
                self._next[position] += 1
                break
            self._next[position] = self._space.minimum
        else:
            self._next = None
        return candidate

    def observe(self, candidate: TrialInput, feedback: TrialFeedback) -> None:
        """Accept coarse feedback without adapting the enumeration order."""
