from src.firmavex.emulator.emulator import run_firmware


def test_missing_firmware_returns_failure():
    result = run_firmware("firmware/benchmarks/cortex_m/does_not_exist.elf")

    assert result["success"] is False
    assert result["return_code"] == -1
    assert "Firmware file not found" in result["stderr"]


def test_cortex_m_firmware_times_out_after_successful_start():
    result = run_firmware(
        "firmware/benchmarks/cortex_m/minimal.elf",
        timeout=1,
    )

    assert result["success"] is True
    assert result["timed_out"] is True
