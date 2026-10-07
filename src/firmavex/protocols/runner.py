"""Serial campaigns through the existing single-experiment authority."""

from typing import Protocol

from src.firmavex.evaluation.api import InputSpace
from src.firmavex.evaluation.registry import BenchmarkSpec
from src.firmavex.experiments.runner import ExperimentRunner, SessionProvider
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.protocols.results import CampaignResult, validate_record


class CampaignRegistry(SessionProvider, Protocol):
    """Administrator-owned selection and session provider, never strategy input."""

    input_space: InputSpace

    def select(self, split: str) -> tuple[BenchmarkSpec, ...]: ...


def _validate_space(space: InputSpace) -> None:
    # Declaration validation, before dispatch; the evaluator still validates and
    # admits each candidate. No execution/budget accounting happens here.
    if type(space) is not InputSpace or any(type(value) is not int for value in (space.width, space.minimum, space.maximum)):
        raise ValueError("Campaign registry must expose a canonical public InputSpace.")
    if space.width < 1 or not 0 <= space.minimum <= space.maximum <= 0xFFFFFFFF:
        raise ValueError("Campaign registry exposes an invalid public InputSpace.")


class CampaignRunner:
    """Retain ordinary aborted records and continue with independent sessions.

    Exceptions, including KeyboardInterrupt/SystemExit, propagate unchanged.
    No partial completed result is fabricated or persisted. The administrator
    can inspect experiment_runner.last_session after an interrupted attempt.
    """

    def __init__(self, registry: CampaignRegistry) -> None:
        self._registry = registry
        self._experiments = ExperimentRunner(registry)

    @property
    def experiment_runner(self) -> ExperimentRunner:
        """Administrator handle; not passed to strategies or serialization."""
        return self._experiments

    def run(self, protocol: EvaluationProtocol) -> CampaignResult:
        if type(protocol) is not EvaluationProtocol:
            raise ValueError("Campaigns require an immutable EvaluationProtocol.")
        plan = protocol.expand()
        selected = {entry.benchmark_id for entry in self._registry.select(protocol.partition)}
        if any(identifier not in selected for identifier in protocol.benchmark_ids):
            raise ValueError("Campaign contains an unknown benchmark or a benchmark outside its declared partition.")
        space = self._registry.input_space
        _validate_space(space)
        records = []
        for spec in plan:
            record = self._experiments.run(spec)
            validate_record(spec, record, space)
            records.append(record)
        return CampaignResult(protocol, tuple(records))
