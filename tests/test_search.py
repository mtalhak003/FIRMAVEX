from src.firmavex.generator.search import search_failure


def test_search_discovers_first_failure_trigger(cortex_m_firmware):
    result = search_failure(
        cortex_m_firmware["failure_condition"],
        input_symbol="firmavex_input",
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
        candidates=range(0, 11),
    )

    assert result["success"] is True
    assert result["failure_found"] is True
    assert result["triggering_input"] == 6
    assert result["execution_count"] == 7


def test_search_reports_no_failure(cortex_m_firmware):
    result = search_failure(
        cortex_m_firmware["failure_condition"],
        input_symbol="firmavex_input",
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
        candidates=range(0, 6),
    )

    assert result["success"] is True
    assert result["failure_found"] is False
    assert result["triggering_input"] is None
    assert result["execution_count"] == 6
