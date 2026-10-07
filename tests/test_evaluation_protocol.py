"""Protocol declarations use synthetic opaque IDs, never firmware outcomes."""

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from src.firmavex.protocols.protocol import EvaluationProtocol, standard_baseline_protocol


ID_A = "b-" + "a" * 32
ID_B = "b-" + "b" * 32
SEEDS = tuple(range(10))


def protocol(**changes):
    return EvaluationProtocol(**({
        "benchmark_ids": (ID_A, ID_B),
        "execution_budget": 5,
        "partition": "development",
    } | changes))


@pytest.mark.parametrize("field, value", [
    ("benchmark_ids", (ID_B,)), ("execution_budget", 9),
    ("partition", "held_out"), ("random_seeds", (8,)),
    ("strategies", ("random",)),
])
def test_protocol_is_immutable(field, value):
    declaration = protocol()
    with pytest.raises(FrozenInstanceError):
        setattr(declaration, field, value)


@pytest.mark.parametrize("budget", [0, -1, True, False, 1.0, "5", None])
def test_protocol_requires_an_explicit_positive_integer_budget(budget):
    with pytest.raises(ValueError):
        protocol(execution_budget=budget)


@pytest.mark.parametrize("budget", [1, 5, 2 ** 100])
def test_protocol_preserves_the_exact_positive_budget(budget):
    assert protocol(execution_budget=budget).execution_budget == budget


@pytest.mark.parametrize("identifiers", [
    (), (ID_A, ID_A), [ID_A], ID_A, None,
    ("benchmark-A",), ("/private/image.elf",),
    ("b-" + "A" * 32,), ("b-" + "0" * 31,), (7,),
])
def test_invalid_empty_duplicate_mutable_or_nonopaque_benchmark_ids_are_rejected(identifiers):
    with pytest.raises(ValueError):
        protocol(benchmark_ids=identifiers)


def test_declared_benchmark_order_is_preserved_without_sorting():
    declaration = protocol(benchmark_ids=(ID_B, ID_A))
    assert declaration.benchmark_ids == (ID_B, ID_A)


@pytest.mark.parametrize("partition", ["held-out", "all", "development/held_out", "", None, 1])
def test_partition_metadata_requires_one_existing_administrative_split(partition):
    with pytest.raises(ValueError):
        protocol(partition=partition)


@pytest.mark.parametrize("partition", ["development", "held_out"])
def test_standard_protocol_fixes_both_baselines_and_the_outcome_independent_seed_schedule(partition):
    declaration = standard_baseline_protocol(
        benchmark_ids=(ID_B, ID_A), execution_budget=7, partition=partition,
    )
    assert declaration.strategies == ("enumerative", "random")
    assert declaration.random_seeds == SEEDS
    assert declaration.execution_budget == 7
    assert declaration.benchmark_ids == (ID_B, ID_A)
    assert declaration.partition == partition
    assert declaration.is_standard


@pytest.mark.parametrize("budget", [0, -1, True])
def test_standard_protocol_rejects_scientifically_empty_or_invalid_budgets(budget):
    with pytest.raises(ValueError):
        standard_baseline_protocol(benchmark_ids=(ID_A,), execution_budget=budget, partition="development")


def test_standard_protocol_does_not_accept_a_replacement_seed_schedule():
    with pytest.raises(TypeError):
        standard_baseline_protocol(
            benchmark_ids=(ID_A,), execution_budget=1, partition="development", random_seeds=(99,),
        )


@pytest.mark.parametrize("seeds", [
    (), (0, 0), (True,), (False,), (1.0,), ("1",), (None,),
    [0, 1], "01", None,
])
def test_random_schedule_rejects_empty_duplicate_noninteger_or_mutable_values(seeds):
    with pytest.raises(ValueError):
        protocol(random_seeds=seeds)


def test_custom_schedule_preserves_signed_large_seeds_and_declared_order():
    seeds = (9, -1, 2 ** 130, 0)
    declaration = protocol(random_seeds=seeds)
    assert declaration.random_seeds == seeds
    assert not declaration.is_standard
    decoded = json.loads(declaration.to_json())
    assert str(2 ** 130) in declaration.to_json()
    assert decoded == declaration.to_dict()


@pytest.mark.parametrize("strategies", [
    (), ("enumerative", "enumerative"), ("random", "random"),
    ("random", "enumerative"), ("guided",), ("AI",),
    ["enumerative", "random"], "random", None, (1,),
])
def test_strategy_selection_rejects_empty_duplicate_reversed_mutable_and_unsupported_names(strategies):
    with pytest.raises(ValueError):
        protocol(strategies=strategies)


def test_enumerative_only_requires_no_random_seed_declaration():
    declaration = protocol(strategies=("enumerative",), random_seeds=())
    assert declaration.strategies == ("enumerative",)
    assert declaration.random_seeds == ()
    assert not declaration.is_standard
    with pytest.raises(ValueError):
        protocol(strategies=("enumerative",), random_seeds=(0,))


def test_random_only_is_explicitly_custom_and_preserves_every_declared_seed():
    declaration = protocol(strategies=("random",), random_seeds=(3, 0))
    assert declaration.strategies == ("random",)
    assert declaration.random_seeds == (3, 0)
    assert not declaration.is_standard


def test_protocol_serialization_is_stable_json_with_schema_and_no_private_build_information():
    declaration = protocol()
    assert declaration.to_json() == replace(declaration).to_json()
    decoded = json.loads(declaration.to_json())
    assert decoded == declaration.to_dict()
    assert decoded["schema_version"] == 1
    assert SEEDS == declaration.random_seeds
    for hidden in ("source", ".elf", ".c", "oracle", "ground_truth", "stdout", "stderr"):
        assert hidden not in declaration.to_json()


def test_protocol_serialization_returns_fresh_data_without_mutating_the_declaration():
    declaration = protocol()
    before = declaration.to_json()
    data = declaration.to_dict()
    data.clear()
    assert declaration.to_json() == before


def test_partition_is_an_explicit_serialized_administrative_choice():
    development = protocol()
    held_out = replace(development, partition="held_out")
    assert development.to_json() != held_out.to_json()
    assert "development" in development.to_json()
    assert "held_out" in held_out.to_json()
