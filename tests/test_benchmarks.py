from pathlib import Path

from src.firmavex.analyzer.analyzer import analyze_firmware


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_DIR = PROJECT_ROOT / "firmware"


def get_findings(filename: str, category: str) -> list:
    source_file = FIRMWARE_DIR / category / filename

    result = analyze_firmware(str(source_file))

    assert result["success"] is True
    return result["findings"]


def test_safe_benchmarks_have_no_findings():
    benchmarks = [
        "safe.c",
        "memcpy_safe.c",
        "memcpy_fixed_size_safe.c",
    ]

    for filename in benchmarks:
        findings = get_findings(filename, "safe")

        assert findings == [], (
            f"{filename} produced unexpected findings: {findings}"
        )


def test_buffer_overflow_benchmark():
    findings = get_findings(
        "buffer_overflow.c",
        "vulnerable",
    )

    assert any(
        finding["type"] == "Potential buffer overflow"
        and finding["function"] == "strcpy"
        and finding["severity"] == "High"
        for finding in findings
    )


def test_format_string_benchmark():
    findings = get_findings(
        "format_string.c",
        "vulnerable",
    )

    assert any(
        finding["type"] == "Potential format string vulnerability"
        and finding["function"] == "printf"
        and finding["severity"] == "High"
        for finding in findings
    )


def test_memcpy_overflow_benchmark():
    findings = get_findings(
        "memcpy_overflow.c",
        "vulnerable",
    )

    assert any(
        finding["type"] == "Potential buffer overflow"
        and finding["function"] == "memcpy"
        and finding["severity"] == "High"
        for finding in findings
    )


def test_memcpy_numeric_overflow_benchmark():
    findings = get_findings(
        "memcpy_numeric_overflow.c",
        "vulnerable",
    )

    assert any(
        finding["type"] == "Potential buffer overflow"
        and finding["function"] == "memcpy"
        and finding["severity"] == "High"
        for finding in findings
    )