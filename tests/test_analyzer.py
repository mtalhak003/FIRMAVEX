from src.codepulse.analyzer.analyzer import analyze_firmware


def test_safe_firmware_has_no_findings():
    result = analyze_firmware("firmware/safe/safe.c")

    assert result["success"] is True
    assert result["findings"] == []


def test_vulnerable_firmware_detects_strcpy():
    result = analyze_firmware(
        "firmware/vulnerable/buffer_overflow.c"
    )

    assert result["success"] is True
    assert len(result["findings"]) == 1

    finding = result["findings"][0]

    assert finding["function"] == "strcpy"
    assert finding["type"] == "Potential buffer overflow"
    assert finding["severity"] == "High"
    assert finding["line"] == 9