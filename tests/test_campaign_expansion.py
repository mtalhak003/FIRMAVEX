"""Campaign planning is cheap: these tests never construct an executor."""

import json
from dataclasses import FrozenInstanceError

import pytest

from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.protocols.protocol import EvaluationProtocol, standard_baseline_protocol


ID_A = "b-" + "a" * 32
ID_B = "b-" + "b" * 32


def identity(spec):
    return spec.benchmark_id, spec.strategy.name, spec.strategy.seed


def test_standard_plan_has_exact_benchmark_baseline_seed_order():
    protocol = standard_baseline_protocol(
        benchmark_ids=(ID_B, ID_A), execution_budget=5, partition="development",
    )
    plan = protocol.expand()
    expected = []
    for identifier in (ID_B, ID_A):
        expected.append((identifier, "enumerative", None))
        expected.extend((identifier, "random", seed) for seed in range(10))
    assert tuple(map(identity, plan)) == tuple(expected)
    assert len(plan) == 22


@pytest.mark.parametrize("partition", ["development", "held_out"])
@pytest.mark.parametrize("seeds", [(0,), (3, 1), (0, 1, 2)])
def test_custom_plan_preserves_order_and_has_one_enumerative_and_one_random_run_per_seed(partition, seeds):
    protocol = EvaluationProtocol((ID_A, ID_B), 7, partition, random_seeds=seeds)
    plan = protocol.expand()
    for identifier in protocol.benchmark_ids:
        runs = [spec for spec in plan if spec.benchmark_id == identifier]
        assert [identity(spec) for spec in runs] == [
            (identifier, "enumerative", None),
            *((identifier, "random", seed) for seed in seeds),
        ]
        assert sum(spec.strategy.name == "enumerative" for spec in runs) == 1
        assert [spec.strategy.seed for spec in runs if spec.strategy.name == "random"] == list(seeds)


@pytest.mark.parametrize("strategies, seeds, expected", [
    (("enumerative",), (), (("enumerative", None),)),
    (("random",), (9, 2), (("random", 9), ("random", 2))),
    (("enumerative", "random"), (0,), (("enumerative", None), ("random", 0))),
])
def test_explicit_supported_subsets_expand_without_implicit_experiments(strategies, seeds, expected):
    protocol = EvaluationProtocol((ID_A,), 1, "development", random_seeds=seeds, strategies=strategies)
    assert [(spec.strategy.name, spec.strategy.seed) for spec in protocol.expand()] == list(expected)


def test_plan_is_immutable_and_every_child_is_an_existing_valid_experiment_declaration():
    plan = EvaluationProtocol((ID_A,), 2, "development", random_seeds=(0,)).expand()
    assert type(plan) is tuple
    assert all(type(spec) is ExperimentSpec for spec in plan)
    with pytest.raises(TypeError):
        plan[0] = plan[1]
    with pytest.raises(FrozenInstanceError):
        plan[0].execution_budget = 99


@pytest.mark.parametrize("budget", [1, 8, 10 ** 12])
def test_all_comparable_runs_use_exactly_the_same_budget_without_strategy_specific_modification(budget):
    protocol = EvaluationProtocol((ID_A, ID_B), budget, "development", random_seeds=(0, 1))
    plan = protocol.expand()
    assert {spec.execution_budget for spec in plan} == {budget}
    assert all(spec.strategy.configuration == () for spec in plan)


def test_plan_is_deterministic_has_no_duplicate_experiment_specs_and_does_not_mutate_protocol():
    protocol = EvaluationProtocol((ID_B, ID_A), 4, "development", random_seeds=(8, 0, -1))
    before = protocol.to_json()
    first = protocol.expand()
    assert first == protocol.expand()
    assert len(first) == len(set(map(identity, first)))
    assert protocol.to_json() == before


def test_partition_changes_administrative_plan_metadata_without_changing_child_strategy_declarations():
    development = EvaluationProtocol((ID_A,), 3, "development", random_seeds=(0,))
    held_out = EvaluationProtocol((ID_A,), 3, "held_out", random_seeds=(0,))
    assert development.expand() == held_out.expand()
    for spec in held_out.expand():
        assert not hasattr(spec.strategy, "partition")
        assert not hasattr(spec, "partition")
    assert development.plan_to_json() != held_out.plan_to_json()


def test_plan_serialization_is_stable_json_and_preserves_null_enumerative_seed():
    protocol = EvaluationProtocol((ID_A,), 3, "development", random_seeds=(0, 1))
    encoded = protocol.plan_to_json()
    assert encoded == protocol.plan_to_json()
    decoded = json.loads(encoded)
    assert decoded == protocol.plan_to_dict()
    assert decoded["schema_version"] == 1
    assert '"seed":null' in encoded
    assert '"seed":0' in encoded
    assert '"seed":1' in encoded


def test_plan_serialization_is_fresh_and_excludes_private_registry_details():
    protocol = EvaluationProtocol((ID_A,), 3, "held_out", random_seeds=(0,))
    before = protocol.plan_to_json()
    protocol.plan_to_dict().clear()
    assert protocol.plan_to_json() == before
    for hidden in ("source", ".elf", "stdout", "stderr", "oracle", "ground_truth"):
        assert hidden not in before
