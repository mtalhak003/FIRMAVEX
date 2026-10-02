from src.firmavex.monitor.monitor import observe_symbol


def test_observe_firmavex_marker():
    result = observe_symbol(
        "firmware/benchmarks/cortex_m/minimal.elf",
        symbol="firmavex_marker",
        breakpoint="minimal.c:7",
    )

    assert result["success"] is True
    assert result["symbol"] == "firmavex_marker"
    assert result["value"] == 0xF1A5
