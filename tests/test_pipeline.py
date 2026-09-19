from src.firmavex.pipeline.pipeline import analyze_and_compile


def test_pipeline_with_vulnerable_firmware(tmp_path):
    output_file = tmp_path / "buffer_overflow.exe"

    result = analyze_and_compile(
        "firmware/vulnerable/buffer_overflow.c",
        str(output_file),
    )

    assert result["success"] is True

    assert result["analysis"]["success"] is True
    assert len(result["analysis"]["findings"]) == 1

    finding = result["analysis"]["findings"][0]

    assert finding["function"] == "strcpy"
    assert finding["severity"] == "High"

    assert result["compilation"]["success"] is True
    assert output_file.exists()


def test_pipeline_with_safe_firmware(tmp_path):
    output_file = tmp_path / "safe.exe"

    result = analyze_and_compile(
        "firmware/safe/safe.c",
        str(output_file),
    )

    assert result["success"] is True

    assert result["analysis"]["success"] is True
    assert result["analysis"]["findings"] == []

    assert result["compilation"]["success"] is True
    assert output_file.exists()
