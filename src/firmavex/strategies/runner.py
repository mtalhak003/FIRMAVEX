"""Serial strategy lifecycle controller; execution accounting stays external."""

from src.firmavex.evaluation.api import ExperimentResult, InputSpace, StrategySession, TrialInput
from src.firmavex.strategies.api import (
    InvalidOutputReason, SearchStrategy, StrategyMetadata, StrategyRun, TerminationReason,
)


def _terminal(result: ExperimentResult) -> TerminationReason | None:
    # Infrastructure failure takes precedence even after an earlier discovery.
    if result.aborted:
        return TerminationReason.SESSION_ABORTED
    if result.failure_found:
        return TerminationReason.FAILURE_DISCOVERED
    if result.budget_exhausted:
        return TerminationReason.BUDGET_EXHAUSTED
    return None


def _invalid(candidate: object, space: InputSpace) -> InvalidOutputReason | None:
    # Reject subclasses as well as alternate candidate wrappers: the canonical
    # record must not carry extra state, properties, or mutable values.
    if type(candidate) is not TrialInput or type(candidate.values) is not tuple:
        return InvalidOutputReason.CANDIDATE_TYPE
    if len(candidate.values) != space.width:
        return InvalidOutputReason.WIDTH
    if not space.accepts(candidate.values):
        return InvalidOutputReason.VALUES
    return None


def run_strategy(strategy: SearchStrategy, session: StrategySession) -> StrategyRun:
    """Run one strategy through describe/execute/result only.

    The caller supplies a Step 15B strategy adapter, retains administrator
    ownership, and dedicates this session to this runner. No adapter or result
    counters are passed into the strategy. Exceptions, including cancellation,
    propagate unchanged; the evaluator owns accounting for interrupted trials.
    """
    metadata = strategy.metadata
    if type(metadata) is not StrategyMetadata:
        raise ValueError("Strategy metadata must be a StrategyMetadata record.")
    description = session.describe()
    result = session.result()
    reason = _terminal(result)
    if reason is not None:
        return StrategyRun(result, metadata, reason)
    strategy.start(description)
    while True:
        result = session.result()
        reason = _terminal(result)
        if reason is not None:
            return StrategyRun(result, metadata, reason)
        candidate = strategy.propose()
        if candidate is None:
            return StrategyRun(session.result(), metadata, TerminationReason.STRATEGY_STOPPED)
        invalid = _invalid(candidate, description.input_space)
        if invalid is not None:
            return StrategyRun(session.result(), metadata, TerminationReason.INVALID_OUTPUT, invalid)
        feedback = session.execute(candidate)
        strategy.observe(candidate, feedback)
        result = session.result()
        reason = _terminal(result)
        if reason is not None:
            return StrategyRun(result, metadata, reason)
        if feedback.status == "invalid_input":
            return StrategyRun(result, metadata, TerminationReason.INVALID_OUTPUT, InvalidOutputReason.EVALUATOR_REJECTED)
        if feedback.status in {"infrastructure_failure", "session_aborted"}:
            return StrategyRun(result, metadata, TerminationReason.SESSION_ABORTED)
        if feedback.status == "triggered":
            return StrategyRun(result, metadata, TerminationReason.FAILURE_DISCOVERED)
        if feedback.status == "budget_exhausted":
            return StrategyRun(result, metadata, TerminationReason.BUDGET_EXHAUSTED)
