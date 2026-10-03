from src.firmavex.generator.search import search_failure
from src.firmavex.reproducer.reproducer import reproduce_failure
from src.firmavex.minimizer.minimizer import minimize_integer_failure


def generate_failure_report(
    firmware_file: str,
    input_symbol: str,
    failure_symbol: str,
    breakpoint: str,
    candidates,
    failure_value: int = 1,
    reproduction_attempts: int = 3,
) -> dict:
    """Search, reproduce, minimize, and summarize runtime failure evidence."""

    candidates = list(candidates)

    search_result = search_failure(
        firmware_file=firmware_file,
        input_symbol=input_symbol,
        failure_symbol=failure_symbol,
        breakpoint=breakpoint,
        candidates=candidates,
        failure_value=failure_value,
    )

    report = {
        "firmware_file": firmware_file,
        "input_symbol": input_symbol,
        "failure_symbol": failure_symbol,
        "failure_value": failure_value,
        "failure_found": search_result["failure_found"],
        "search_execution_count": search_result["execution_count"],
        "triggering_input": search_result["triggering_input"],
        "reproducible": False,
        "reproduction_attempts": 0,
        "minimal_triggering_input": None,
        "minimization_execution_count": 0,
    }

    if not search_result["success"] or not search_result["failure_found"]:
        report["success"] = search_result["success"]
        return report

    triggering_input = search_result["triggering_input"]

    reproduction_result = reproduce_failure(
        firmware_file=firmware_file,
        input_symbol=input_symbol,
        input_value=triggering_input,
        failure_symbol=failure_symbol,
        breakpoint=breakpoint,
        attempts=reproduction_attempts,
        failure_value=failure_value,
    )

    report["reproducible"] = reproduction_result["reproducible"]
    report["reproduction_attempts"] = reproduction_result["attempts"]

    if not reproduction_result["success"]:
        report["success"] = False
        return report

    minimum_input = min(candidates) if candidates else 0

    minimization_result = minimize_integer_failure(
        firmware_file=firmware_file,
        input_symbol=input_symbol,
        triggering_input=triggering_input,
        failure_symbol=failure_symbol,
        breakpoint=breakpoint,
        minimum_input=minimum_input,
        failure_value=failure_value,
    )

    report["minimal_triggering_input"] = minimization_result["minimal_input"]
    report["minimization_execution_count"] = minimization_result["execution_count"]
    report["success"] = (
        reproduction_result["reproducible"]
        and minimization_result["success"]
        and minimization_result["minimal_input"] is not None
    )

    return report
