from src.firmavex.monitor.monitor import observe_symbol


def reproduce_failure(
    firmware_file: str,
    input_symbol: str,
    input_value: int,
    failure_symbol: str,
    breakpoint: str,
    attempts: int = 3,
    failure_value: int = 1,
) -> dict:
    """Repeat a triggering input to determine whether the failure is reproducible."""

    executions = []

    for attempt in range(1, attempts + 1):
        result = observe_symbol(
            firmware_file,
            symbol=failure_symbol,
            breakpoint=breakpoint,
            set_symbol=input_symbol,
            set_value=input_value,
        )

        failure_detected = (
            result["success"]
            and result["value"] == failure_value
        )

        executions.append({
            "attempt": attempt,
            "success": result["success"],
            "failure_value": result["value"],
            "failure_detected": failure_detected,
        })

    reproducible = (
        len(executions) == attempts
        and all(item["failure_detected"] for item in executions)
    )

    return {
        "success": all(item["success"] for item in executions),
        "input": input_value,
        "attempts": attempts,
        "reproducible": reproducible,
        "executions": executions,
    }
