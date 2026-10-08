"""Step 18A declarations and synthetic preflight checks, without a campaign."""

import json
from dataclasses import FrozenInstanceError, asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import (
    ExecutionSignature, ExperimentSpec as Description, InputSpace, TrialFeedback,
    TrialInput,
)
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.experiments import runner as experiment_runner_module
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.protocols import protocol as protocol_module
from src.firmavex.protocols.controlled import (
    CONTROLLED_CORPUS_VERSION, CONTROLLED_EXECUTION_BUDGET,
    CONTROLLED_GUIDED_CONFIGURATION, CONTROLLED_GUIDED_SEEDS,
    CONTROLLED_INPUT_SPACE, CONTROLLED_PRESET_NAME, CONTROLLED_RANDOM_SEEDS,
    CONTROLLED_SOURCE_CHECKPOINT, CONTROLLED_STRATEGIES,
    DEVELOPMENT_BENCHMARK_IDS, HELD_OUT_BENCHMARK_IDS,
    controlled_cortex_m_v1, controlled_cortex_m_v1_plan_to_dict,
    controlled_cortex_m_v1_plan_to_json,
)
from src.firmavex.protocols.protocol import EvaluationProtocol, standard_baseline_protocol
from src.firmavex.protocols.runner import CampaignRunner
from src.firmavex.strategies.api import StrategyMetadata, TerminationReason
from src.firmavex.strategies.guided import guided_metadata


DEVELOPMENT_IDS = (
    "b-3874d6a4a92f46758d73854abf0a08df",
    "b-08e9f32ef15d4ef0b17b65a4c211f8e2",
    "b-64a1899b33444f9fb3a82bdfe238d812",
    "b-c7a338d3ea684d149e5a45e49d235dc7",
    "b-965d82f3548943c5bfb218d7e0c5351c",
    "b-762a8f0d6fbf4b6eb34a821e9fc35c24",
)
HELD_OUT_IDS = (
    "b-b5ba43a1f81041a28dcb6e10f0754d91",
    "b-04a234ad83964671a791285172e0bcee",
)
SEEDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
GUIDED_CONFIGURATION = (("archive_size", 32), ("mutation_attempts", 8))
SIGNATURE = ExecutionSignature("a" * 64)
PRIVATE = "private source /firmware.elf oracle ground_truth expected-trigger diagnostic"


def json_text(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def test_versioned_preset_constants_pin_scope_settings_and_approved_method_checkpoint():
    assert CONTROLLED_PRESET_NAME == "controlled_cortex_m_v1"
    assert CONTROLLED_CORPUS_VERSION == 2
    assert CONTROLLED_SOURCE_CHECKPOINT == "d62cc715d82cf26359dc34ae96c48749bdb43403"
    assert CONTROLLED_EXECUTION_BUDGET == 256
    assert type(CONTROLLED_EXECUTION_BUDGET) is int
    assert CONTROLLED_STRATEGIES == ("enumerative", "random", "guided")
    assert CONTROLLED_RANDOM_SEEDS == CONTROLLED_GUIDED_SEEDS == SEEDS
    assert CONTROLLED_GUIDED_CONFIGURATION == GUIDED_CONFIGURATION
    assert type(CONTROLLED_INPUT_SPACE) is InputSpace
    assert CONTROLLED_INPUT_SPACE == InputSpace(4, 0, 15)
    assert all(type(value) is int for value in asdict(CONTROLLED_INPUT_SPACE).values())
    assert DEVELOPMENT_BENCHMARK_IDS == DEVELOPMENT_IDS
    assert HELD_OUT_BENCHMARK_IDS == HELD_OUT_IDS


@pytest.mark.parametrize("partition, identifiers", [
    ("development", DEVELOPMENT_IDS), ("held_out", HELD_OUT_IDS),
])
def test_frozen_selection_matches_actual_registry_manifest_order_and_public_domain(partition, identifiers):
    # Selection reads administrative manifest metadata, not predicates/oracles.
    registry = BenchmarkRegistry()
    assert tuple(entry.benchmark_id for entry in registry.select(partition)) == identifiers
    assert registry.input_space == InputSpace(4, 0, 15)
    assert len(set(DEVELOPMENT_IDS + HELD_OUT_IDS)) == 8
    assert set(DEVELOPMENT_IDS).isdisjoint(HELD_OUT_IDS)


@pytest.mark.parametrize("partition, identifiers, count", [
    ("development", DEVELOPMENT_IDS, 126), ("held_out", HELD_OUT_IDS, 42),
])
def test_controlled_expansion_is_deterministic_complete_and_equally_budgeted(partition, identifiers, count):
    declaration = controlled_cortex_m_v1(partition=partition)
    assert type(declaration) is EvaluationProtocol
    assert declaration.benchmark_ids == identifiers
    assert declaration.partition == partition
    assert declaration.strategies == ("enumerative", "random", "guided")
    assert declaration.random_seeds == declaration.guided_seeds == SEEDS
    assert not declaration.is_standard
    plan = declaration.expand()
    assert len(plan) == count
    assert plan == declaration.expand() == controlled_cortex_m_v1(partition=partition).expand()
    expected = tuple(
        (identifier, name, seed)
        for identifier in identifiers
        for name, seeds in (("enumerative", (None,)), ("random", SEEDS), ("guided", SEEDS))
        for seed in seeds
    )
    assert tuple((spec.benchmark_id, spec.strategy.name, spec.strategy.seed) for spec in plan) == expected
    assert len(set(expected)) == count
    for spec in plan:
        assert type(spec.execution_budget) is int and spec.execution_budget == 256
        assert spec.strategy.configuration == (GUIDED_CONFIGURATION if spec.strategy.name == "guided" else ())
        assert type(spec.strategy) is StrategyMetadata
        assert not hasattr(spec, "partition")
        assert not hasattr(spec.strategy, "partition")
    with pytest.raises(FrozenInstanceError):
        declaration.execution_budget = 512
    with pytest.raises(FrozenInstanceError):
        plan[-1].strategy.seed = 11


@pytest.mark.parametrize("partition", ["development", "held_out"])
def test_named_plan_envelope_is_deterministic_and_preserves_existing_plan_records(partition):
    declaration = controlled_cortex_m_v1(partition=partition)
    expected = {
        "schema_version": 1,
        "preset": "controlled_cortex_m_v1",
        "corpus_version": 2,
        "source_checkpoint": "d62cc715d82cf26359dc34ae96c48749bdb43403",
        "expected_input_space": {"width": 4, "minimum": 0, "maximum": 15},
        "plan": declaration.plan_to_dict(),
    }
    before = declaration.plan_to_json()
    assert controlled_cortex_m_v1_plan_to_dict(partition=partition) == expected
    encoded = controlled_cortex_m_v1_plan_to_json(partition=partition)
    assert encoded == json_text(expected)
    assert encoded == controlled_cortex_m_v1_plan_to_json(partition=partition)
    assert json.loads(encoded) == expected
    assert declaration.plan_to_json() == before
    for hidden in (".elf", ".c\"", "oracle", "ground_truth", "stdout", "stderr", "firmavex_failure", "benchmark_complete"):
        assert hidden not in encoded


@pytest.mark.parametrize("partition", ["development", "held_out"])
def test_serialized_plan_is_fresh_administrative_data(partition):
    before = controlled_cortex_m_v1_plan_to_json(partition=partition)
    data = controlled_cortex_m_v1_plan_to_dict(partition=partition)
    data["expected_input_space"]["width"] = 99
    data["plan"]["protocol"]["guided_seeds"].reverse()
    data["plan"]["experiments"].clear()
    assert controlled_cortex_m_v1_plan_to_json(partition=partition) == before


def test_declaration_and_plan_serialization_do_not_build_or_execute_infrastructure(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Protocol preflight must not dispatch infrastructure."))
    for owner, method in (
        (BenchmarkRegistry, "build"), (BenchmarkRegistry, "open_session"),
        (ExperimentRunner, "run"), (CampaignRunner, "run"),
        (EvaluationSession, "execute"),
    ):
        monkeypatch.setattr(owner, method, forbidden)
    for partition in ("development", "held_out"):
        controlled_cortex_m_v1(partition=partition)
        controlled_cortex_m_v1_plan_to_dict(partition=partition)
        controlled_cortex_m_v1_plan_to_json(partition=partition)
    forbidden.assert_not_called()


@pytest.mark.parametrize("partition", [None, True, 2, "", "all", "held-out", ["development"], {"development": True}])
def test_controlled_preset_rejects_invalid_partitions(partition):
    with pytest.raises(ValueError):
        controlled_cortex_m_v1(partition=partition)


@pytest.mark.parametrize("function", [
    controlled_cortex_m_v1, controlled_cortex_m_v1_plan_to_dict,
    controlled_cortex_m_v1_plan_to_json,
])
def test_partition_is_required_and_keyword_only(function):
    with pytest.raises(TypeError):
        function()
    with pytest.raises(TypeError):
        function("development")


@pytest.mark.parametrize("field, value", [
    ("execution_budget", 512), ("random_seeds", (9,)),
    ("guided_seeds", (9,)), ("strategies", ("guided",)),
    ("guided_configuration", (("archive_size", 1), ("mutation_attempts", 1))),
    ("benchmark_ids", DEVELOPMENT_IDS[:1]),
])
def test_frozen_preset_has_no_seed_budget_configuration_or_benchmark_overrides(field, value):
    with pytest.raises(TypeError):
        controlled_cortex_m_v1(partition="development", **{field: value})


@pytest.mark.parametrize("settings", [
    {"archive_size": 31, "mutation_attempts": 8},
    {"archive_size": 32, "mutation_attempts": 7},
])
def test_guided_default_drift_fails_closed_instead_of_changing_frozen_configuration(monkeypatch, settings):
    monkeypatch.setattr(protocol_module, "guided_metadata", lambda seed: guided_metadata(seed, **settings))
    with pytest.raises(ValueError):
        controlled_cortex_m_v1(partition="development")
    with pytest.raises(ValueError):
        controlled_cortex_m_v1_plan_to_json(partition="held_out")


@pytest.mark.parametrize("partition", ["development", "held_out"])
@pytest.mark.parametrize("settings", [
    {"archive_size": 31, "mutation_attempts": 8},
    {"archive_size": 32, "mutation_attempts": 7},
])
def test_constructed_controlled_protocol_preserves_plan_after_guided_default_drift(monkeypatch, partition, settings):
    declaration = controlled_cortex_m_v1(partition=partition)
    plan = declaration.expand()
    encoded = declaration.plan_to_json()
    changed_defaults = Mock(side_effect=lambda seed: guided_metadata(seed, **settings))
    monkeypatch.setattr(protocol_module, "guided_metadata", changed_defaults)
    assert declaration.expand() == plan
    assert declaration.plan_to_json() == encoded
    assert all(item.strategy.configuration == GUIDED_CONFIGURATION for item in declaration.expand() if item.strategy.name == "guided")
    changed_defaults.assert_not_called()
    # A new declaration still refuses defaults that disagree with the preset.
    with pytest.raises(ValueError):
        controlled_cortex_m_v1(partition=partition)


def test_constructed_controlled_protocol_never_recomputes_guided_metadata(monkeypatch):
    declaration = controlled_cortex_m_v1(partition="development")
    expected = declaration.plan_to_dict()
    forbidden = Mock(side_effect=AssertionError("Frozen expansion must not consult defaults again."))
    monkeypatch.setattr(protocol_module, "guided_metadata", forbidden)
    assert declaration.plan_to_dict() == expected
    assert declaration.plan_to_json() == json_text(expected)
    forbidden.assert_not_called()


def test_standard_baseline_official_json_and_plan_remain_exactly_frozen():
    identifiers = (HELD_OUT_IDS[1], HELD_OUT_IDS[0])
    declaration = standard_baseline_protocol(
        benchmark_ids=identifiers, execution_budget=13, partition="held_out",
    )
    expected_protocol = {
        "schema_version": 1, "kind": "standard_baseline_v1",
        "benchmark_ids": list(identifiers), "execution_budget": 13,
        "partition": "held_out", "strategies": ["enumerative", "random"],
        "random_seeds": list(SEEDS),
        "run_order": "benchmark_then_enumerative_then_random_seed",
        "infrastructure_abort_policy": "continue_independent_experiments",
    }
    expected_plan = {
        "schema_version": 1, "protocol": expected_protocol,
        "experiments": [
            {"benchmark_id": identifier, "strategy": {"name": name, "configuration": {}, "seed": seed}, "execution_budget": 13}
            for identifier in identifiers
            for name, seeds in (("enumerative", (None,)), ("random", SEEDS))
            for seed in seeds
        ],
    }
    assert declaration.is_standard and declaration.guided_seeds == ()
    assert declaration.to_json() == json_text(expected_protocol)
    assert declaration.plan_to_json() == json_text(expected_plan)
    assert len(declaration.expand()) == 22


class SyntheticRegistry:
    """Administrator-owned, synthetic executors; never dispatches firmware."""

    input_space = InputSpace(4, 0, 15)

    def __init__(self, partition, *, members=(), observations=()):
        self.partition = partition
        self.members = members
        self.observations = observations
        self.owners = []
        self.executors = []
        self.select = Mock(side_effect=self._select)
        self.open_session = Mock(side_effect=self._open_session)

    def _select(self, partition):
        return tuple(SimpleNamespace(
            benchmark_id=identifier, name=PRIVATE, source=PRIVATE, split=partition,
        ) for identifier in self.members) if partition == self.partition else ()

    def _open_session(self, identifier, budget, strategy_id, *, random_seed=None):
        executor = Mock(side_effect=self.observations)
        owner = EvaluationSession(
            identifier, self.input_space, budget, strategy_id, executor,
            random_seed=random_seed,
        )
        self.owners.append(owner)
        self.executors.append(executor)
        return owner


@pytest.mark.parametrize("partition", ["development", "held_out"])
@pytest.mark.parametrize("name", ["enumerative", "random", "guided"])
def test_preset_derived_runs_keep_authoritative_measurements_and_public_callback_boundaries(monkeypatch, partition, name):
    declaration = controlled_cortex_m_v1(partition=partition)
    spec = next(item for item in declaration.expand() if item.strategy.name == name)
    strategy = experiment_runner_module.create_strategy(spec.strategy)
    strategy.start = Mock(wraps=strategy.start)
    strategy.observe = Mock(wraps=strategy.observe)
    monkeypatch.setattr(experiment_runner_module, "create_strategy", lambda metadata: strategy)
    registry = SyntheticRegistry(partition, observations=(
        Observation(True, stdout=PRIVATE, execution_signature=SIGNATURE),
        Observation(True, True, stderr=PRIVATE, execution_signature=SIGNATURE),
    ))
    runner = ExperimentRunner(registry)
    record = runner.run(spec)
    owner, = registry.owners
    assert record.declaration is spec
    assert record.description is owner.describe()
    assert record.run.evaluation == owner.result()
    result = record.run.evaluation
    assert result.execution_budget == 256
    assert result.attempted_executions == result.successful_executions == 2
    assert result.first_failure_execution == 2 and result.failure_found
    assert result.budget_remaining == 254 and not result.budget_exhausted
    assert result.infrastructure_failures == 0 and not result.aborted
    assert record.run.termination is TerminationReason.FAILURE_DISCOVERED
    registry.open_session.assert_called_once_with(
        spec.benchmark_id, 256, name, random_seed=spec.strategy.seed,
    )
    registry.select.assert_not_called()
    description, = strategy.start.call_args.args
    assert type(description) is Description
    assert set(asdict(description)) == {"benchmark_id", "input_space", "execution_budget"}
    assert description.input_space == InputSpace(4, 0, 15)
    assert strategy.observe.call_count == 2
    for call in strategy.observe.call_args_list:
        candidate, feedback = call.args
        assert type(candidate) is TrialInput and description.input_space.accepts(candidate.values)
        assert type(feedback) is TrialFeedback and feedback.execution_signature is SIGNATURE
        assert set(asdict(feedback)) == {"status", "execution_index", "budget_remaining", "execution_signature"}
        assert PRIVATE not in json_text(asdict(feedback))
        assert not hasattr(feedback, "partition") and not hasattr(candidate, "partition")
    assert PRIVATE not in record.to_json()


@pytest.mark.parametrize("partition", ["development", "held_out"])
def test_wrong_registry_partition_membership_rejects_whole_preset_before_dispatch(partition):
    other_ids = HELD_OUT_IDS if partition == "development" else DEVELOPMENT_IDS
    registry = SyntheticRegistry(partition, members=other_ids)
    with pytest.raises(ValueError, match="partition"):
        CampaignRunner(registry).run(controlled_cortex_m_v1(partition=partition))
    registry.select.assert_called_once_with(partition)
    registry.open_session.assert_not_called()
    assert registry.owners == registry.executors == []


@pytest.mark.parametrize("name", ["enumerative", "random", "guided"])
def test_preset_derived_infrastructure_abort_retains_charge_and_excludes_raw_diagnostics(name):
    declaration = controlled_cortex_m_v1(partition="development")
    spec = next(item for item in declaration.expand() if item.strategy.name == name)
    registry = SyntheticRegistry("development", observations=(Observation(False, stdout=PRIVATE, stderr=PRIVATE),))
    record = ExperimentRunner(registry).run(spec)
    result = record.run.evaluation
    assert result == registry.owners[0].result()
    assert result.attempted_executions == result.infrastructure_failures == 1
    assert result.successful_executions == 0 and result.aborted
    assert not result.failure_found and result.first_failure_execution is None
    assert result.budget_remaining == 255
    assert record.run.termination is TerminationReason.SESSION_ABORTED
    assert registry.executors[0].call_count == 1
    assert registry.owners[0].diagnostics()[0]["stderr"] == PRIVATE
    assert PRIVATE not in record.to_json()
