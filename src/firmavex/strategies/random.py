"""Seeded uniform sampling without replacement over the public input space."""

from random import Random

from src.firmavex.evaluation.api import ExperimentSpec, InputSpace, TrialFeedback, TrialInput
from src.firmavex.strategies.api import StrategyMetadata


def _decode_index(index: int, space: InputSpace, base: int) -> TrialInput:
    """Decode an admitted domain index, last position changing fastest."""
    values = [space.minimum] * space.width
    for position in range(space.width - 1, -1, -1):
        index, digit = divmod(index, base)
        values[position] += digit
    return TrialInput(tuple(values))


class RandomStrategy:
    """Lazy Fisher-Yates with a private RNG and O(proposals) sparse index map.

    The seed is required. start() resets both RNG and sampling state. Feedback
    never changes the order; the common runner owns dispatch and termination.
    Exact replay assumes the same Python RNG/strategy implementation.
    """

    def __init__(self, seed: int) -> None:
        if type(seed) is not int:
            raise ValueError("RandomStrategy requires an explicit integer seed.")
        self._metadata = StrategyMetadata("random", seed=seed)
        self._rng = Random(seed)
        self._space: InputSpace | None = None
        self._base = 0
        self._remaining = 0
        self._swaps: dict[int, int] = {}

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    def start(self, description: ExperimentSpec) -> None:
        # EvaluationSession validates the public width and uint32 bounds.
        self._space = description.input_space
        self._base = self._space.maximum - self._space.minimum + 1
        self._remaining = self._base ** self._space.width
        self._swaps.clear()
        self._rng.seed(self._metadata.seed)

    def propose(self) -> TrialInput | None:
        if self._space is None:
            raise RuntimeError("RandomStrategy must be started before proposing candidates.")
        if self._remaining == 0:
            return None
        # The map represents only changed slots of an implicit identity array.
        # Select uniformly among live slots, move the tail into the selected
        # slot, and remove the tail. No retries or modulo reduction are used.
        slot = self._rng.randrange(self._remaining)
        index = self._swaps.get(slot, slot)
        tail = self._remaining - 1
        replacement = self._swaps.pop(tail, tail)
        if slot != tail:
            self._swaps[slot] = replacement
        self._remaining = tail
        return _decode_index(index, self._space, self._base)

    def observe(self, candidate: TrialInput, feedback: TrialFeedback) -> None:
        """Accept public feedback without changing the seeded sampling order."""
