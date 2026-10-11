from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest

from firmavex.product.config import ProductConfig, load_config
from firmavex.product.errors import ProductError
from src.firmavex.evaluation.api import InputSpace
from src.firmavex.strategies.api import StrategyMetadata


def config(tmp_path, **kwargs):
    return ProductConfig(firmware=tmp_path / "firmware.elf", input_symbols=("inputs[0]", "inputs[1]"),
                         ready_breakpoint="input_ready", completion_breakpoint="complete",
                         failure_symbol="failure", **kwargs)


def test_public_records_are_canonical_and_configuration_is_frozen(tmp_path):
    value = config(tmp_path)
    assert type(value.input_space) is InputSpace
    assert value.input_space == InputSpace(2, 0, 15)
    assert type(value.strategy_metadata) is StrategyMetadata
    assert value.strategy_metadata == StrategyMetadata("enumerative")
    with pytest.raises(FrozenInstanceError):
        value.seed = 1


@pytest.mark.parametrize("strategy,seed", [("random", 0), ("guided", -99), ("random", 2**100)])
def test_explicit_seed_and_guided_configuration(tmp_path, strategy, seed):
    value = config(tmp_path, strategy=strategy, seed=seed, guided_archive_size=4,
                   guided_mutation_attempts=3)
    assert value.strategy_metadata.seed == seed
    assert value.strategy_metadata.name == strategy
    assert dict(value.strategy_metadata.configuration) == (
        {"archive_size": 4, "mutation_attempts": 3} if strategy == "guided" else {})


def test_json_round_trip_resolves_firmware_relative_to_configuration(tmp_path):
    value = config(tmp_path)
    data = value.to_dict()
    data["firmware"] = "subdirectory/my image.elf"
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data))
    loaded = load_config(path)
    assert loaded.firmware == tmp_path / "subdirectory/my image.elf"
    assert ProductConfig.from_dict(loaded.to_dict()) == loaded
    assert loaded.to_dict()["input_symbols"] == ["inputs[0]", "inputs[1]"]


@pytest.mark.parametrize("changes", [
    {"schema_version": True}, {"schema_version": 2}, {"extra": 1},
    {"firmware": ""}, {"firmware": None}, {"input_symbols": []},
    {"input_symbols": ["x", "x"]}, {"input_symbols": ["x", "failure"]},
    {"input_symbols": ["inputs[01]"]}, {"input_symbols": ["inputs[-1]"]},
    {"input_symbols": ["inputs[0][1]"]}, {"input_symbols": ["*(int*)0"]},
    {"input_symbols": ["x; quit"]}, {"input_symbols": [True]},
    {"input_symbols": ["x\ncontinue"]}, {"failure_symbol": "$pc"},
    {"failure_symbol": "failure + 1"}, {"ready_breakpoint": "main:12"},
    {"ready_breakpoint": "complete"}, {"completion_breakpoint": "finish;quit"},
    {"input_min": True}, {"input_min": -1}, {"input_min": 16},
    {"input_max": 2**32}, {"input_max": 1.0}, {"failure_value": False},
    {"failure_value": -1}, {"execution_budget": 0}, {"execution_budget": True},
    {"execution_budget": 1_000_001}, {"timeout_seconds": False},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": -0.1}, {"startup_timeout_seconds": 0},
    {"timeout_seconds": 10**1000},
    {"startup_timeout_seconds": "10"}, {"collect_signature": 1},
    {"strategy": "AI"}, {"seed": 0}, {"strategy": "random"},
    {"strategy": "random", "seed": False}, {"strategy": "guided", "seed": 0, "collect_signature": False},
    {"guided_archive_size": 0}, {"guided_mutation_attempts": True},
    {"qemu": ""}, {"gdb": ["gdb"]}, {"compiler": "gcc\n-ex quit"},
])
def test_reject_invalid_configuration_without_dispatch(tmp_path, changes):
    data = config(tmp_path).to_dict() | changes
    with pytest.raises(ProductError) as error:
        ProductConfig.from_dict(data)
    assert error.value.category == "invalid_configuration"


@pytest.mark.parametrize("text", [
    '{"schema_version":1,"schema_version":1}',
    '{"schema_version":1,"timeout_seconds":NaN}',
    '{"schema_version":1,"timeout_seconds":Infinity}',
    '{"schema_version":1,"nested":{"x":1,"x":2}}',
    '[1,2]', '{',
])
def test_json_duplicates_nonfinite_and_malformed_fail_closed(tmp_path, text):
    path = tmp_path / "project.json"
    path.write_text(text)
    with pytest.raises(ProductError) as error:
        load_config(path)
    assert error.value.category == "invalid_configuration"


def test_missing_required_field_and_unreadable_configuration(tmp_path):
    data = config(tmp_path).to_dict()
    del data["ready_breakpoint"]
    with pytest.raises(ProductError, match="Missing required"):
        ProductConfig.from_dict(data)
    with pytest.raises(ProductError, match="Unable to read"):
        load_config(tmp_path / "absent.json")


def test_supported_uint32_boundary_and_singleton_domain(tmp_path):
    value = config(tmp_path, input_min=2**32-1, input_max=2**32-1,
                   failure_value=2**32-1, timeout_seconds=1)
    assert value.input_space.accepts((2**32-1, 2**32-1))
    assert value.timeout_seconds == 1.0


@pytest.mark.parametrize("field,value", [("input_symbols", ["x"]), ("firmware", "x.elf")])
def test_direct_constructor_cannot_bypass_immutable_contract(tmp_path, field, value):
    with pytest.raises(ProductError):
        replace(config(tmp_path), **{field: value})
