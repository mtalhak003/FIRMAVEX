import ctypes
import itertools
import json
import subprocess
from pathlib import Path

import pytest

from src.firmavex.evaluation.api import TrialInput
from src.firmavex.evaluation.registry import BenchmarkRegistry
from src.firmavex.benchmarks.cortex_m import load_benchmarks


DATA = Path(__file__).parent / "data"
ORACLE = json.loads((DATA / "cortex_m_v2_ground_truth.json").read_text())
V1_ORACLE = json.loads((DATA / "cortex_m_v1_ground_truth.json").read_text())
NAMES = tuple(ORACLE["benchmarks"])


def expected(name, values):
    """Evaluator/test-only oracle; no strategy uses this to pick candidates."""
    a, b, c, d = values
    truth = ORACLE["benchmarks"][name]
    if name == "multi_variable":
        return a + b == truth["sum"] and a >= truth["minimums"][0] and b >= truth["minimums"][1]
    if name == "nested_branches":
        return a >= truth["outer_minimum"] and b < a and c == a - b and d - c == 1
    if name == "bitwise_arithmetic":
        return (((a * 2 ** truth["shift"]) ^ b) + c) % (truth["mask"] + 1) == truth["target"] and d == a ^ c
    if name == "magic_check":
        return [a, b, c] == truth["tag"] and d == (sum(truth["tag"]) ^ truth["xor"]) % truth["modulus"]
    if name == "ordered_accumulator":
        return a == truth["first"] and sum(value * weight for value, weight in zip(values, truth["weights"])) == truth["total"]
    if name in {"finite_state_machine", "sparse_relation"}:
        return list(values) in truth["accepted_sequences"]
    if name == "compound_constraints":
        lower, upper = truth["third_range"]
        return a > b and (a + b) % truth["sum_modulus"] == truth["sum_remainder"] and lower <= c <= upper and d == a - b and d <= truth["maximum_difference"]
    raise AssertionError(f"Missing oracle for {name}")


@pytest.fixture(scope="session")
def v2_images(tmp_path_factory):
    registry = BenchmarkRegistry()
    directory = tmp_path_factory.mktemp("cortex_m_v2")
    images = {}
    for item in (*registry.select("development"), *registry.select("held_out")):
        image = directory / f"{item.benchmark_id}.elf"
        built = registry.build(item.benchmark_id, image)
        assert built["success"], built["stderr"]
        images[item.name] = (item, image)
    return registry, images


@pytest.mark.parametrize("name", NAMES)
def test_v2_builds_arm_elf(name, v2_images):
    _, images = v2_images
    header = images[name][1].read_bytes()[:20]
    assert header[:6] == b"\x7fELF\x01\x01"
    assert int.from_bytes(header[18:20], "little") == 40


@pytest.mark.parametrize("name", NAMES)
def test_v2_deterministic_runtime_and_reset(name, v2_images):
    registry, images = v2_images
    benchmark, image = images[name]
    cases = ORACLE["benchmarks"][name]["cases"]
    run = registry.open_session(benchmark.benchmark_id, 2 * len(cases), "runtime-validation")
    for _ in range(2):
        for values, trigger in cases:
            feedback = run.execute(TrialInput(tuple(values)))
            assert feedback.status == ("triggered" if trigger else "safe"), run.diagnostics()
    result = run.result()
    assert result.attempted_executions == result.successful_executions == 2 * len(cases)
    assert result.infrastructure_failures == 0
    assert result.failure_triggering_executions == 2 * sum(trigger for _, trigger in cases)
    assert result.budget_exhausted
    assert run.execute(TrialInput((0, 0, 0, 0))).status == "budget_exhausted"


def test_ordered_accumulator_arm_permutation_preserves_first_value_gate(v2_images):
    registry, images = v2_images
    benchmark, _ = images["ordered_accumulator"]
    run = registry.open_session(benchmark.benchmark_id, 2, "order-validation")
    assert run.execute(TrialInput((7, 8, 7, 5))).status == "triggered", run.diagnostics()
    assert run.execute(TrialInput((7, 7, 8, 5))).status == "safe", run.diagnostics()
    result = run.result()
    assert result.attempted_executions == result.successful_executions == 2
    assert result.infrastructure_failures == 0
    assert result.failure_triggering_executions == 1
    assert result.budget_exhausted and not result.aborted


def host_predicate(source, destination, vector):
    compiled = subprocess.run(
        ["gcc", "-std=c11", "-O0", "-shared", "-fPIC", str(source), "-o", str(destination)],
        capture_output=True, text=True,
    )
    assert compiled.returncode == 0, compiled.stderr
    function = ctypes.CDLL(str(destination)).benchmark_condition
    function.argtypes = [ctypes.POINTER(ctypes.c_uint32) if vector else ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    return function


@pytest.mark.parametrize("name", NAMES)
def test_v2_oracle_exhaustively_matches_actual_c_predicate(name, tmp_path):
    registry = BenchmarkRegistry()
    specs = (*registry.select("development"), *registry.select("held_out"))
    benchmark = next(item for item in specs if item.name == name)
    function = host_predicate(benchmark.source, tmp_path / "predicate.so", True)
    triggers = tested = 0
    for values in itertools.product(range(16), repeat=4):
        oracle = int(expected(name, values))
        actual = function((ctypes.c_uint32 * 4)(*values))
        assert actual == oracle, values
        tested += 1
        triggers += actual
    assert tested == 65536
    assert 0 < triggers < tested
    if name == "sparse_relation":
        assert triggers == 1
    for values, trigger in ORACLE["benchmarks"][name]["cases"]:
        assert expected(name, values) == bool(trigger)


@pytest.mark.parametrize("benchmark", load_benchmarks(), ids=lambda item: item.name)
def test_v1_oracle_exhaustively_matches_actual_c_predicate(benchmark, tmp_path):
    function = host_predicate(benchmark.source, tmp_path / "predicate.so", False)
    intervals = V1_ORACLE["benchmarks"][benchmark.name]["trigger_intervals"]
    for value in range(256):
        oracle = int(any(lower <= value <= upper for lower, upper in intervals))
        assert function(value) == oracle, value


def test_v2_registry_and_oracle_versions_agree():
    registry = BenchmarkRegistry()
    assert ORACLE["corpus_version"] == 2
    assert (registry.input_space.width, registry.input_space.minimum, registry.input_space.maximum) == (4, 0, 15)
    names = {item.name for item in (*registry.select("development"), *registry.select("held_out"))}
    assert names == set(NAMES)
