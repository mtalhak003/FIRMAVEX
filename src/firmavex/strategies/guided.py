"""Seeded signature-novelty parent mutations through public evaluation records."""

from collections import deque
from random import Random

from src.firmavex.evaluation.api import (
    ExecutionSignature, ExperimentSpec, InputSpace, TrialFeedback, TrialInput,
)
from src.firmavex.strategies.api import StrategyMetadata
from src.firmavex.strategies.random import RandomStrategy


def guided_metadata(
    seed: int, *, archive_size: int = 32, mutation_attempts: int = 8,
) -> StrategyMetadata:
    """Validate and record all public settings without constructing a sampler."""
    if type(seed) is not int:
        raise ValueError("GuidedStrategy requires an explicit integer seed.")
    for name, value in (("archive_size", archive_size), ("mutation_attempts", mutation_attempts)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"GuidedStrategy {name} must be a positive integer.")
    return StrategyMetadata(
        "guided", (("archive_size", archive_size), ("mutation_attempts", mutation_attempts)), seed,
    )


class GuidedStrategy:
    """Keep novel-signature parents and mutate one public input coordinate.

    Novelty uses signature equality only. A bounded FIFO archive supplies
    parents; bounded mutation attempts fall back to the unchanged seeded
    random sampler. Sparse proposal history prevents duplicates and guarantees
    finite exhaustion without materializing the domain. Retained history is
    O(proposals * width), not constant memory. Execution accounting and stopping
    on failure/budget/abort remain the common runner's responsibility.
    """

    def __init__(
        self, seed: int, *, archive_size: int = 32, mutation_attempts: int = 8,
    ) -> None:
        self._metadata = guided_metadata(
            seed, archive_size=archive_size, mutation_attempts=mutation_attempts,
        )
        self._archive_size = archive_size
        self._mutation_attempts = mutation_attempts
        self._rng = Random(seed)
        self._fallback = RandomStrategy(seed)
        self._space: InputSpace | None = None
        self._visited: set[tuple[int, ...]] = set()
        self._seen_signatures: set[ExecutionSignature] = set()
        self._parents: deque[TrialInput] = deque()
        self._exhausted = False

    @property
    def metadata(self) -> StrategyMetadata:
        return self._metadata

    def start(self, description: ExperimentSpec) -> None:
        # EvaluationSession already validates the public width and uint32 bounds.
        self._space = description.input_space
        self._visited.clear()
        self._seen_signatures.clear()
        self._parents.clear()
        self._exhausted = False
        self._rng.seed(self._metadata.seed)
        self._fallback.start(description)

    def propose(self) -> TrialInput | None:
        if self._space is None:
            raise RuntimeError("GuidedStrategy must be started before proposing candidates.")
        if self._exhausted:
            return None
        base = self._space.maximum - self._space.minimum + 1
        if self._parents and base > 1:
            for _ in range(self._mutation_attempts):
                parent = self._parents[self._rng.randrange(len(self._parents))]
                position = self._rng.randrange(self._space.width)
                # Uniformly select an alternative value without rejection retries.
                value = self._space.minimum + self._rng.randrange(base - 1)
                if value >= parent.values[position]:
                    value += 1
                values = list(parent.values)
                values[position] = value
                candidate = TrialInput(tuple(values))
                if candidate.values not in self._visited:
                    self._visited.add(candidate.values)
                    return candidate
        # Every skipped tuple was already proposed. The finite fallback pool
        # removes each draw permanently, so collisions cannot cause a retry loop.
        for candidate in iter(self._fallback.propose, None):
            if candidate.values not in self._visited:
                self._visited.add(candidate.values)
                return candidate
        self._exhausted = True
        return None

    def observe(self, candidate: TrialInput, feedback: TrialFeedback) -> None:
        """Retain a parent only for previously unseen successful signatures."""
        if self._space is None:
            raise RuntimeError("GuidedStrategy must be started before observing candidates.")
        if (
            type(candidate) is not TrialInput
            or not self._space.accepts(candidate.values)
            or candidate.values not in self._visited
        ):
            raise ValueError("GuidedStrategy observations require a canonical previously proposed input.")
        if type(feedback) is not TrialFeedback:
            raise ValueError("GuidedStrategy observations require canonical immutable TrialFeedback.")
        # Repeat public-record validation at this boundary to reject forged or
        # extended signatures before they can become archive state.
        TrialFeedback.__post_init__(feedback)
        signature = feedback.execution_signature
        if feedback.status not in {"safe", "triggered"} or signature is None:
            return
        if signature not in self._seen_signatures:
            self._seen_signatures.add(signature)
            self._parents.append(candidate)
            if len(self._parents) > self._archive_size:
                self._parents.popleft()
