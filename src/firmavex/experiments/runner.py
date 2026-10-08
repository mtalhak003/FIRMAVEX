"""One declared experiment using the existing session and strategy runners."""

from typing import Protocol

from src.firmavex.evaluation.evaluator import EvaluationSession
from src.firmavex.experiments.api import ExperimentRecord, ExperimentSpec, _check_description, _check_identity, _validate_strategy
from src.firmavex.strategies.api import SearchStrategy, StrategyMetadata
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.guided import GuidedStrategy
from src.firmavex.strategies.random import RandomStrategy
from src.firmavex.strategies.runner import run_strategy


class SessionProvider(Protocol):
    """Administrator dependency, satisfied by a built BenchmarkRegistry."""

    def open_session(
        self, benchmark_id: str, execution_budget: int, strategy_id: str,
        *, random_seed: int | None = None,
    ) -> EvaluationSession: ...


def create_strategy(metadata: StrategyMetadata) -> SearchStrategy:
    """Explicit strategy selection, taking public metadata only."""
    _validate_strategy(metadata)
    if metadata.name == "enumerative":
        return EnumerativeStrategy()
    if metadata.name == "random" and metadata.seed is not None:
        return RandomStrategy(metadata.seed)
    if metadata.name == "guided" and metadata.seed is not None:
        return GuidedStrategy(metadata.seed, **dict(metadata.configuration))
    raise ValueError("Seeded experiments require an explicit integer seed.")


class ExperimentRunner:
    """Create a fresh session and delegate exactly once to run_strategy.

    The provider owns registration/builds; the retained session owns diagnostics.
    Neither is a strategy input. KeyboardInterrupt/SystemExit and other exceptions propagate
    unchanged; no completed record is fabricated after an interrupted run.
    """

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions
        self._last_session: EvaluationSession | None = None

    @property
    def last_session(self) -> EvaluationSession | None:
        """Administrator-only owner for diagnostics/interruption inspection.

        Retain only the latest session, never serialize it or give it to a
        strategy. A new valid run clears this handle before session creation.
        """
        return self._last_session

    def run(self, spec: ExperimentSpec) -> ExperimentRecord:
        if type(spec) is not ExperimentSpec:
            raise ValueError("Experiments require an ExperimentSpec declaration.")
        self._last_session = None
        strategy = create_strategy(spec.strategy)
        if strategy.metadata != spec.strategy:
            raise ValueError("Constructed strategy metadata differs from the declaration.")
        owner = self._sessions.open_session(
            spec.benchmark_id, spec.execution_budget, strategy.metadata.name,
            random_seed=strategy.metadata.seed,
        )
        self._last_session = owner
        adapter = owner.strategy_api()
        description = adapter.describe()
        _check_description(spec, description)
        initial = adapter.result()
        _check_identity(spec, initial)
        if initial.attempted_executions != 0 or initial.aborted or initial.failure_found:
            raise ValueError("An experiment requires a fresh, unused evaluation session.")
        run = run_strategy(strategy, adapter)
        return ExperimentRecord(spec, description, run)
