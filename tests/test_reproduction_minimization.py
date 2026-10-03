from src.firmavex.reproducer.reproducer import reproduce_failure
from src.firmavex.minimizer.minimizer import minimize_integer_failure


FIRMWARE = "firmware/benchmarks/cortex_m/failure_condition.elf"


def test_failure_is_reproducible():
    result = reproduce_failure(
        FIRMWARE,
        input_symbol="firmavex_input",
        input_value=6,
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
        attempts=3,
    )

    assert result["success"] is True
    assert result["reproducible"] is True
    assert result["input"] == 6
    assert len(result["executions"]) == 3


def test_minimizer_finds_smallest_trigger():
    result = minimize_integer_failure(
        FIRMWARE,
        input_symbol="firmavex_input",
        triggering_input=10,
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
        minimum_input=0,
    )

    assert result["success"] is True
    assert result["minimal_input"] == 6
    assert result["execution_count"] == 7
