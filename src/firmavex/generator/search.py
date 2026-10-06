from src.firmavex.monitor.monitor import observe_symbol


def search_failure(
    firmware_file: str,
    input_symbol: str,
    failure_symbol: str,
    breakpoint: str,
    candidates,
    failure_value: int = 1,
) -> dict:
    """Search candidate inputs until one triggers the failure condition."""

    executions = []

    for candidate in candidates:
        result = observe_symbol(
            firmware_file,
            symbol=failure_symbol,
            breakpoint=breakpoint,
            set_symbol=input_symbol,
            set_value=candidate,
        )

        execution = {
            "input": candidate,
            "success": result["success"],
            "failure_value": result["value"],
            "failure_detected": (
                result["success"]
                and result["value"] == failure_value
            ),
        }

        executions.append(execution)

        if not result["success"]:
            return {
                "success": False,
                "failure_found": False,
                "triggering_input": None,
                "execution_count": len(executions),
                "executions": executions,
                "error": {
                    "message": "Firmware observation failed; search aborted.",
                    "input": candidate,
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                },
            }

        if execution["failure_detected"]:
            return {
                "success": True,
                "failure_found": True,
                "triggering_input": candidate,
                "execution_count": len(executions),
                "executions": executions,
            }

    return {
        "success": all(item["success"] for item in executions),
        "failure_found": False,
        "triggering_input": None,
        "execution_count": len(executions),
        "executions": executions,
    }
