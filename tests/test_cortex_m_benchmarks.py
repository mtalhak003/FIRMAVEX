import json
from pathlib import Path

import pytest

from src.firmavex.benchmarks.cortex_m import build_benchmark, load_benchmarks
from src.firmavex.compiler.cortex_m import build_cortex_m_firmware
from src.firmavex.generator.search import search_failure
from src.firmavex.monitor.monitor import observe_symbol
from src.firmavex.reporting.report import generate_failure_report


# Evaluation-only oracle. Production builders and search never import this file.
GROUND_TRUTH = json.loads(
    (Path(__file__).parent / "data/cortex_m_v1_ground_truth.json").read_text()
)
NAMES = tuple(GROUND_TRUTH["benchmarks"])


def test_corpus_interface_has_no_ground_truth():
    benchmarks = load_benchmarks()
    assert {item.name for item in benchmarks} == set(NAMES)
    for benchmark in benchmarks:
        assert benchmark.corpus_version == GROUND_TRUTH["corpus_version"] == 1
        assert (benchmark.input_min, benchmark.input_max) == (0, 255)
        assert set(vars(benchmark)) == {
            "name", "corpus_version", "source", "input_symbol",
            "failure_symbol", "breakpoint", "input_min", "input_max",
        }


@pytest.mark.parametrize("name", NAMES)
def test_benchmark_compilation(name, cortex_m_corpus):
    _, image = cortex_m_corpus[name]
    header = image.read_bytes()[:20]
    assert header[:4] == b"\x7fELF"
    assert header[4:6] == b"\x01\x01"  # 32-bit, little-endian
    assert int.from_bytes(header[18:20], "little") == 40  # ARM


@pytest.mark.parametrize(
    "name,input_value,expected",
    [(name, value, expected) for name in NAMES
     for value, expected in GROUND_TRUTH["benchmarks"][name]["cases"]],
)
def test_expected_trigger_behavior(name, input_value, expected, cortex_m_corpus):
    benchmark, image = cortex_m_corpus[name]
    result = observe_symbol(
        str(image), symbol=benchmark.failure_symbol,
        breakpoint=benchmark.breakpoint,
        set_symbol=benchmark.input_symbol, set_value=input_value,
    )
    assert result["success"], result
    assert result["value"] == expected


@pytest.mark.parametrize("name", NAMES)
def test_baseline_executions_to_failure(name, cortex_m_corpus):
    benchmark, image = cortex_m_corpus[name]
    # Identical policy/domain for every benchmark; do not derive candidates from
    # ground truth. Only the assertions below consult the evaluation oracle.
    candidates = range(benchmark.input_min, benchmark.input_max + 1)
    result = search_failure(
        str(image), input_symbol=benchmark.input_symbol,
        failure_symbol=benchmark.failure_symbol, breakpoint=benchmark.breakpoint,
        candidates=candidates,
    )
    assert result["success"], result
    assert result["failure_found"] is True
    first_trigger = GROUND_TRUTH["benchmarks"][name]["trigger_intervals"][0][0]
    assert result["triggering_input"] == first_trigger
    assert result["execution_count"] == first_trigger + 1
    assert len(result["executions"]) == result["execution_count"]


def test_missing_arm_toolchain_has_useful_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    result = build_benchmark(load_benchmarks()[0], tmp_path / "missing.elf")
    assert result["success"] is False
    assert result["return_code"] == -1
    assert "arm-none-eabi-gcc" in result["stderr"]
    assert "PATH" in result["stderr"]
    assert not (tmp_path / "missing.elf").exists()


def test_corpus_works_with_reporting_pipeline(cortex_m_corpus):
    benchmark, image = cortex_m_corpus["threshold"]
    report = generate_failure_report(
        str(image), input_symbol=benchmark.input_symbol,
        failure_symbol=benchmark.failure_symbol, breakpoint=benchmark.breakpoint,
        candidates=range(0, 7), reproduction_attempts=2,
    )
    assert report["success"], report
    assert report["triggering_input"] == 6
    assert report["search_execution_count"] == 7
    assert report["reproducible"] is True
    assert report["reproduction_attempts"] == 2
    assert report["minimal_triggering_input"] == 6
    assert report["minimization_execution_count"] == 7


def test_missing_source_has_useful_error(tmp_path):
    result = build_cortex_m_firmware(tmp_path / "missing.c", tmp_path / "missing.elf")
    assert result["success"] is False
    assert "Build input not found" in result["stderr"]


def test_compilation_failure_preserves_diagnostics(tmp_path):
    source = tmp_path / "invalid.c"
    source.write_text("this is not valid C;\n")
    result = build_cortex_m_firmware(source, tmp_path / "invalid.elf")
    assert result["success"] is False
    assert result["return_code"] != 0
    assert "invalid.c" in result["stderr"]


def test_rebuilding_uses_current_source(tmp_path):
    source = tmp_path / "fixture.c"
    source.write_text("volatile unsigned value = 1; int main(void) { while (1) {} }\n")
    image = tmp_path / "nested/fixture.elf"
    first = build_cortex_m_firmware(source, image)
    assert first["success"], first["stderr"]
    original = image.read_bytes()
    repeated = build_cortex_m_firmware(source, tmp_path / "repeat.elf")
    assert repeated["success"], repeated["stderr"]
    assert (tmp_path / "repeat.elf").read_bytes() == original
    source.write_text("volatile unsigned value = 2; int main(void) { while (1) {} }\n")
    second = build_cortex_m_firmware(source, image)
    assert second["success"], second["stderr"]
    assert image.read_bytes() != original
    updated = image.read_bytes()
    source.write_text("invalid C\n")
    failed = build_cortex_m_firmware(source, image)
    assert failed["success"] is False
    assert image.read_bytes() == updated
