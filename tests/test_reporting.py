from src.firmavex.reporting.report import generate_failure_report


FIRMWARE = "firmware/benchmarks/cortex_m/failure_condition.elf"


def test_generate_failure_report():
    report = generate_failure_report(
        firmware_file=FIRMWARE,
        input_symbol="firmavex_input",
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
        candidates=range(0, 11),
        reproduction_attempts=3,
    )

    assert report["success"] is True
    assert report["failure_found"] is True
    assert report["triggering_input"] == 6
    assert report["search_execution_count"] == 7

    assert report["reproducible"] is True
    assert report["reproduction_attempts"] == 3

    assert report["minimal_triggering_input"] == 6
    assert report["minimization_execution_count"] == 7


def test_generate_report_when_no_failure_exists():
    report = generate_failure_report(
        firmware_file=FIRMWARE,
        input_symbol="firmavex_input",
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
        candidates=range(0, 6),
    )

    assert report["success"] is True
    assert report["failure_found"] is False
    assert report["triggering_input"] is None
    assert report["reproducible"] is False
    assert report["minimal_triggering_input"] is None
