from src.firmavex.compiler.compiler import compile_firmware


def test_compile_safe_firmware():
    result = compile_firmware(
        "firmware/safe/safe.c",
        "firmware/safe/safe.exe",
    )

    assert result["success"] is True
    assert result["return_code"] == 0
