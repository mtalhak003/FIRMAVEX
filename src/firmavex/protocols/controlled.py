"""Administrator-owned controlled comparison v1, without executing a campaign.

This named preset composes the existing protocol and plan serializers. Its
settings are fixed before comparative outcomes; custom declarations and the
earlier frozen standard baseline retain their existing APIs and representations.
"""

import json
from dataclasses import asdict, dataclass

from src.firmavex.evaluation.api import InputSpace
from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.protocols.protocol import EvaluationProtocol
from src.firmavex.strategies.api import StrategyMetadata


CONTROLLED_PRESET_NAME = "controlled_cortex_m_v1"
CONTROLLED_SOURCE_CHECKPOINT = "d62cc715d82cf26359dc34ae96c48749bdb43403"
CONTROLLED_CORPUS_VERSION = 2
CONTROLLED_INPUT_SPACE = InputSpace(4, 0, 15)
CONTROLLED_EXECUTION_BUDGET = 256
CONTROLLED_STRATEGIES = ("enumerative", "random", "guided")
CONTROLLED_RANDOM_SEEDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
CONTROLLED_GUIDED_SEEDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
CONTROLLED_GUIDED_CONFIGURATION = (("archive_size", 32), ("mutation_attempts", 8))

# Corpus-v2 manifest order filtered by its existing administrative partition.
# These IDs contain no predicates, trigger vectors, or expected search costs.
DEVELOPMENT_BENCHMARK_IDS = (
    "b-3874d6a4a92f46758d73854abf0a08df",
    "b-08e9f32ef15d4ef0b17b65a4c211f8e2",
    "b-64a1899b33444f9fb3a82bdfe238d812",
    "b-c7a338d3ea684d149e5a45e49d235dc7",
    "b-965d82f3548943c5bfb218d7e0c5351c",
    "b-762a8f0d6fbf4b6eb34a821e9fc35c24",
)
HELD_OUT_BENCHMARK_IDS = (
    "b-b5ba43a1f81041a28dcb6e10f0754d91",
    "b-04a234ad83964671a791285172e0bcee",
)


@dataclass(frozen=True, slots=True)
class _FrozenExpansion:
    """Callable snapshot of validated immutable declarations, without defaults."""

    plan: tuple[ExperimentSpec, ...]

    def __call__(self) -> tuple[ExperimentSpec, ...]:
        return self.plan


def controlled_cortex_m_v1(*, partition: str) -> EvaluationProtocol:
    """Declare all fixtures in one partition with no tunable preset overrides.

    CampaignRunner accepts the returned canonical EvaluationProtocol directly.
    It remains responsible for checking registry partition membership. Corpus,
    image, and environment provenance must be verified administratively before
    a real campaign; creating this declaration neither builds nor runs firmware.
    The returned instance retains its validated plan for every later expansion.
    """
    if type(partition) is not str or partition not in {"development", "held_out"}:
        raise ValueError("Controlled comparison requires development or held_out.")
    identifiers = DEVELOPMENT_BENCHMARK_IDS if partition == "development" else HELD_OUT_BENCHMARK_IDS
    protocol = EvaluationProtocol(
        benchmark_ids=identifiers,
        execution_budget=CONTROLLED_EXECUTION_BUDGET,
        partition=partition,
        strategies=CONTROLLED_STRATEGIES,
        random_seeds=CONTROLLED_RANDOM_SEEDS,
        guided_seeds=CONTROLLED_GUIDED_SEEDS,
    )
    # Existing expansion uses guided defaults. Fail closed if those defaults
    # drift, rather than silently changing this frozen comparison's settings.
    plan = protocol.expand()
    for spec in plan:
        if spec.strategy.name == "guided" and spec.strategy != StrategyMetadata(
            "guided", CONTROLLED_GUIDED_CONFIGURATION, spec.strategy.seed,
        ):
            raise ValueError("Guided configuration differs from frozen controlled_cortex_m_v1 settings.")
    # Keep the exact protocol type required by existing campaign boundaries,
    # while pinning this instance's expansion instead of altering the generic
    # protocol class or recomputing guided defaults during later serialization.
    object.__setattr__(protocol, "expand", _FrozenExpansion(plan))
    return protocol


def controlled_cortex_m_v1_plan_to_dict(*, partition: str) -> dict:
    """Fresh administrator plan envelope; never a strategy callback record."""
    protocol = controlled_cortex_m_v1(partition=partition)
    return {
        "schema_version": 1,
        "preset": CONTROLLED_PRESET_NAME,
        "corpus_version": CONTROLLED_CORPUS_VERSION,
        "source_checkpoint": CONTROLLED_SOURCE_CHECKPOINT,
        "expected_input_space": asdict(CONTROLLED_INPUT_SPACE),
        "plan": protocol.plan_to_dict(),
    }


def controlled_cortex_m_v1_plan_to_json(*, partition: str) -> str:
    """Stable versioned plan data, with no automatic persistence or execution."""
    return json.dumps(
        controlled_cortex_m_v1_plan_to_dict(partition=partition),
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
