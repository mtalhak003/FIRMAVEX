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


def test_comment_does_not_create_finding(tmp_path):
    source_file = tmp_path / "comment_test.c"

    source_file.write_text(
        """
        #include <stdio.h>

        int main(void)
        {
            // strcpy(buffer, input);
            printf("CodePulse\\n");
            return 0;
        }
        """,
        encoding="utf-8",
    )

    result = analyze_firmware(str(source_file))

    assert result["success"] is True
    assert result["findings"] == []


def test_string_literal_does_not_create_finding(tmp_path):
    source_file = tmp_path / "string_test.c"

    source_file.write_text(
        """
        #include <stdio.h>

        int main(void)
        {
            printf("strcpy(buffer, input);");
            return 0;
        }
        """,
        encoding="utf-8",
    )

    result = analyze_firmware(str(source_file))

    assert result["success"] is True
    assert result["findings"] == []


def test_multiline_comment_does_not_create_finding(tmp_path):
    source_file = tmp_path / "multiline_comment_test.c"

    source_file.write_text(
        """
        #include <stdio.h>

        int main(void)
        {
            /*
                strcpy(buffer, input);
            */
            printf("CodePulse\\n");
            return 0;
        }
        """,
        encoding="utf-8",
    )

    result = analyze_firmware(str(source_file))

    assert result["success"] is True
    assert result["findings"] == []


def test_format_string_vulnerability_is_detected():
    result = analyze_firmware(
        "firmware/vulnerable/format_string.c"
    )

    assert result["success"] is True
    assert len(result["findings"]) == 1

    finding = result["findings"][0]

    assert finding["function"] == "printf"
    assert finding["type"] == "Potential format string vulnerability"
    assert finding["severity"] == "High"