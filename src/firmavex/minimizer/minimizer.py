from src.firmavex.monitor.monitor import observe_symbol


def minimize_integer_failure(
    firmware_file: str,
    input_symbol: str,
    triggering_input: int,
    failure_symbol: str,
    breakpoint: str,
    minimum_input: int = 0,
    failure_value: int = 1,
) -> dict:
    """Find the smallest integer input that still triggers the failure."""

    executions = []

    for candidate in range(minimum_input, triggering_input + 1):
        result = observe_symbol(
            firmware_file,
            symbol=failure_symbol,
            breakpoint=breakpoint,
            set_symbol=input_symbol,
            set_value=candidate,
        )

        failure_detected = (
            result["success"]
            and result["value"] == failure_value
        )

        executions.append({
            "input": candidate,
            "success": result["success"],
            "failure_value": result["value"],
            "failure_detected": failure_detected,
        })

        if failure_detected:
            return {
                "success": True,
                "minimal_input": candidate,
                "execution_count": len(executions),
                "executions": executions,
            }

    return {
        "success": all(item["success"] for item in executions),
        "minimal_input": None,
        "execution_count": len(executions),
        "executions": executions,
    }
