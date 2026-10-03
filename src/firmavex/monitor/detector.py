from src.firmavex.monitor.monitor import observe_symbol


def detect_failure(
    firmware_file: str,
    failure_symbol: str,
    breakpoint: str,
    failure_value: int = 1,
) -> dict:
    """Detect a firmware failure from an observed runtime symbol."""

    observation = observe_symbol(
        firmware_file,
        symbol=failure_symbol,
        breakpoint=breakpoint,
    )

    if not observation["success"]:
        return {
            **observation,
            "failure_detected": False,
            "expected_failure_value": failure_value,
        }

    return {
        **observation,
        "failure_detected": observation["value"] == failure_value,
        "expected_failure_value": failure_value,
    }
