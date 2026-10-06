from dataclasses import FrozenInstanceError, asdict

import pytest

from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.experiments.runner import create_strategy
from src.firmavex.strategies.api import StrategyMetadata
from src.firmavex.strategies.enumerative import EnumerativeStrategy
from src.firmavex.strategies.random import RandomStrategy


ID = "b-3874d6a4a92f46758d73854abf0a08df"


@pytest.mark.parametrize("budget", [0, 7])
def test_valid_enumerative_declaration(budget):
    metadata = StrategyMetadata("enumerative")
    spec = ExperimentSpec(ID, metadata, budget)
    assert spec.strategy is metadata and spec.execution_budget == budget
    strategy = create_strategy(spec.strategy)
    assert type(strategy) is EnumerativeStrategy
    assert strategy.metadata == metadata
    assert strategy.metadata.seed is None


@pytest.mark.parametrize("seed", [0, -7, 42, 2 ** 130])
def test_valid_random_declaration_preserves_exact_explicit_seed(seed):
    metadata = StrategyMetadata("random", seed=seed)
    spec = ExperimentSpec(ID, metadata, 3)
    strategy = create_strategy(spec.strategy)
    assert type(strategy) is RandomStrategy
    assert strategy.metadata == metadata and strategy.metadata.seed == seed


@pytest.mark.parametrize("seed", [0, 42, -7])
def test_enumerative_seed_is_rejected_rather_than_ignored(seed):
    metadata = StrategyMetadata("enumerative", seed=seed)
    with pytest.raises(ValueError, match="must not declare a seed"):
        ExperimentSpec(ID, metadata, 3)
    with pytest.raises(ValueError, match="must not declare a seed"):
        create_strategy(metadata)


def test_random_without_seed_is_rejected():
    metadata = StrategyMetadata("random")
    with pytest.raises(ValueError, match="explicit integer seed"):
        ExperimentSpec(ID, metadata, 3)
    with pytest.raises(ValueError, match="explicit integer seed"):
        create_strategy(metadata)


@pytest.mark.parametrize("name", ["guided", "ai", "unknown", "package.module:factory"])
def test_unsupported_strategy_selection_is_rejected(name):
    with pytest.raises(ValueError, match="Choose the enumerative or random"):
        ExperimentSpec(ID, StrategyMetadata(name), 3)


@pytest.mark.parametrize("budget", [-1, True, False, 1.5, "3", None])
def test_invalid_budget_is_rejected(budget):
    with pytest.raises(ValueError, match="nonnegative integer"):
        ExperimentSpec(ID, StrategyMetadata("enumerative"), budget)


@pytest.mark.parametrize("identifier", ["", "/private/source.c", "b-short", 1])
def test_only_opaque_benchmark_identifiers_are_accepted(identifier):
    with pytest.raises(ValueError, match="opaque b-"):
        ExperimentSpec(identifier, StrategyMetadata("enumerative"), 3)


@pytest.mark.parametrize("name, seed", [("enumerative", None), ("random", 42)])
def test_unsupported_configuration_is_not_silently_discarded(name, seed):
    metadata = StrategyMetadata(name, (("unimplemented_option", 1),), seed=seed)
    with pytest.raises(ValueError, match="only empty configuration"):
        ExperimentSpec(ID, metadata, 3)
    with pytest.raises(ValueError, match="only empty configuration"):
        create_strategy(metadata)


@pytest.mark.parametrize("metadata", [{"name": "enumerative"}, "enumerative", object()])
def test_strategy_selection_requires_immutable_metadata(metadata):
    with pytest.raises(ValueError, match="StrategyMetadata"):
        ExperimentSpec(ID, metadata, 3)


def test_declaration_and_nested_metadata_are_immutable():
    spec = ExperimentSpec(ID, StrategyMetadata("random", seed=42), 3)
    with pytest.raises(FrozenInstanceError):
        spec.execution_budget = 999
    with pytest.raises(FrozenInstanceError):
        spec.strategy.seed = 99
    assert set(asdict(spec)) == {"benchmark_id", "strategy", "execution_budget"}


@pytest.mark.parametrize("metadata", [StrategyMetadata("enumerative"), StrategyMetadata("random", seed=42)])
def test_equivalent_declarations_have_equivalent_metadata(metadata):
    first = ExperimentSpec(ID, metadata, 3)
    second = ExperimentSpec(ID, StrategyMetadata(metadata.name, metadata.configuration, metadata.seed), 3)
    assert first == second
    assert asdict(first) == asdict(second)
    assert create_strategy(first.strategy).metadata == create_strategy(second.strategy).metadata
