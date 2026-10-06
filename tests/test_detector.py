from src.firmavex.monitor.detector import detect_failure


def test_detects_failure_condition(cortex_m_firmware):
    result = detect_failure(
        cortex_m_firmware["failure_condition"],
        failure_symbol="firmavex_failure",
        breakpoint="failure_condition.c:11",
    )

    assert result["success"] is True
    assert result["value"] == 1
    assert result["failure_detected"] is True
    assert result["expected_failure_value"] == 1
