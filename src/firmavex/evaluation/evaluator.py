"""Evaluator-owned accounting. Strategies submit values, never count executions."""

import time
from threading import Lock
from collections.abc import Callable
from dataclasses import dataclass

from src.firmavex.evaluation.api import (
    ExperimentResult, ExperimentSpec, InputSpace, StrategyHandle, TrialFeedback, TrialInput,
)


@dataclass(frozen=True)
class Observation:
    """Internal executor output. Raw diagnostics never enter strategy feedback."""

    success: bool
    triggered: bool = False
    stdout: str = ""
    stderr: str = ""


class EvaluationSession:
    """One evaluator-created budget, serial trials, fresh firmware per execution.

    Only describe/execute/result and their records form the strategy API.
    This Python object is not an isolation boundary against introspection.
    """

    def __init__(
        self, benchmark_id: str, input_space: InputSpace, execution_budget: int,
        strategy_id: str, executor: Callable[[tuple[int, ...]], Observation],
        *, random_seed: int | None = None,
    ):
        if type(execution_budget) is not int or execution_budget < 0:
            raise ValueError("Execution budget must be a nonnegative integer.")
        if any(type(value) is not int for value in (input_space.width, input_space.minimum, input_space.maximum)) or input_space.width < 1 or not 0 <= input_space.minimum <= input_space.maximum <= 0xFFFFFFFF:
            raise ValueError("Invalid input space.")
        if random_seed is not None and type(random_seed) is not int:
            raise ValueError("Random seed must be an integer or None.")
        self._spec = ExperimentSpec(benchmark_id, input_space, execution_budget)
        self._strategy_id = strategy_id
        self._executor = executor
        self._seed = random_seed
        self._attempted = self._successful = self._errors = self._triggers = 0
        self._first_failure = None
        self._first_failure_time = None
        self._started = None
        self._aborted = False
        self._diagnostics: list[dict] = []
        self._lock = Lock()

    def describe(self) -> ExperimentSpec:
        return self._spec

    def strategy_api(self) -> StrategyHandle:
        """Give strategies this adapter, not the administrator session/registry."""
        return StrategyHandle(self.describe, self.execute, self.result)

    def execute(self, trial: TrialInput) -> TrialFeedback:
        # Admission and dispatch are serialized; concurrent requests cannot
        # overdraw the budget or launch parallel firmware executions.
        with self._lock:
            return self._execute(trial)

    def _execute(self, trial: TrialInput) -> TrialFeedback:
        remaining = self._spec.execution_budget - self._attempted
        if self._aborted:
            return TrialFeedback("session_aborted", None, remaining)
        if remaining == 0:
            return TrialFeedback("budget_exhausted", None, 0)
        if not isinstance(trial, TrialInput) or not self._spec.input_space.accepts(trial.values):
            return TrialFeedback("invalid_input", None, remaining)
        if self._started is None:
            self._started = time.monotonic()
        # Charge before dispatch, including executors that raise or time out.
        self._attempted += 1
        try:
            observed = self._executor(trial.values)
            if not isinstance(observed, Observation) or type(observed.success) is not bool or type(observed.triggered) is not bool:
                raise ValueError("Executor returned a malformed observation.")
        except Exception as exc:
            observed = Observation(False, stderr=f"{type(exc).__name__}: {exc}")
        except BaseException as exc:
            # Cancellation still consumes the admitted execution. Record it
            # before propagating the original control-flow exception.
            self._record_failure(trial, Observation(False, stderr=f"{type(exc).__name__}: {exc}"))
            raise
        if not observed.success:
            self._record_failure(trial, observed)
            status = "infrastructure_failure"
        else:
            self._successful += 1
            status = "triggered" if observed.triggered else "safe"
            if observed.triggered:
                self._triggers += 1
                if self._first_failure is None:
                    self._first_failure = self._attempted
                    self._first_failure_time = time.monotonic() - self._started
        return TrialFeedback(status, self._attempted, self._spec.execution_budget - self._attempted)

    def _record_failure(self, trial: TrialInput, observed: Observation) -> None:
        self._errors += 1
        self._aborted = True
        self._diagnostics.append({
            "execution_index": self._attempted, "values": trial.values,
            "stdout": observed.stdout, "stderr": observed.stderr,
        })

    def result(self) -> ExperimentResult:
        with self._lock:
            return self._result()

    def _result(self) -> ExperimentResult:
        remaining = self._spec.execution_budget - self._attempted
        return ExperimentResult(
            benchmark_id=self._spec.benchmark_id, strategy_id=self._strategy_id,
            execution_budget=self._spec.execution_budget,
            attempted_executions=self._attempted, successful_executions=self._successful,
            infrastructure_failures=self._errors, failure_triggering_executions=self._triggers,
            failure_found=self._first_failure is not None,
            first_failure_execution=self._first_failure,
            time_to_first_failure_seconds=self._first_failure_time,
            budget_remaining=remaining, budget_exhausted=remaining == 0,
            aborted=self._aborted, random_seed=self._seed, reproducibility=None,
        )

    def diagnostics(self) -> tuple[dict, ...]:
        """Evaluator/admin-only; never serialize or expose this to a strategy."""
        return tuple(dict(item) for item in self._diagnostics)
