"""Human explanations derived from receipts; never reclassify recorded evidence."""

_HINTS = {
    "missing_dependency": "Use runtime setup/repair, then Check runtime again. Examples do not require a compiler.",
    "dependency_probe_failed": "Inspect selected tool paths and diagnostics. A version probe is not execution qualification.",
    "infrastructure_failure": "The test could not be completed reliably. Inspect diagnostics; do not interpret this as a safe outcome.",
    "invalid_input": "Check target profile, symbol names, input dimensions and the documented firmware/testbench contract.",
    "invalid_output": "Completion or the required result marker was missing or ambiguous. Inspect debugger/simulator logs.",
    "cancelled": "Cancellation is not a passing result. Inspect charged accounting and confirmed process cleanup.",
    "incomplete": "No authoritative terminal receipt exists. Do not guess accounting or rerun automatically.",
    "untrusted_workload": "Only explicitly trusted projects and trusted host tools are supported; no hostile-input sandbox exists.",
    "worker_interrupted": "Reopen the saved run to inspect persisted receipts. Restart explicitly into a new directory only.",
    "protocol_error": "Check client/worker versions and saved diagnostics. Full receipts may need to be inspected on disk.",
}


def guidance(category):
    return _HINTS.get(
        category,
        "Review saved evidence and diagnostics before starting a separate new attempt.",
    )


def summary(record):
    evidence = record.get("evidence", {})
    if type(evidence) is not dict:
        evidence = {}
    status = record.get("status", "unknown")
    meanings = {
        "triggered": "The configured failure condition was observed.",
        "passed": "The configured check passed for this observation; this is not proof of general correctness.",
        "not_discovered": "No configured failure was found within the recorded budget; this is a bounded non-discovery.",
    }
    lines = [
        "Recorded outcome: " + str(status),
        meanings.get(status, guidance(status)),
        "Measurement: " + str(evidence.get("measurement_mode", "not established")),
        "Cleanup verified: " + str(evidence.get("cleanup_verified", "not established")),
    ]
    admission = evidence.get("admission", {})
    profile = admission.get("profile", {}) if type(admission) is dict else {}
    lines.append("Saved target: " + str(profile.get("id", "not recorded") if type(profile) is dict else "not recorded"))
    legacy = evidence.get("legacy_result", {})
    if type(legacy) is dict and type(legacy.get("accounting")) is dict:
        lines.append(
            "Charged evaluator attempts: "
            + str(legacy["accounting"].get("attempted_executions", "unknown"))
        )
        lines.append(
            "Charged attempts are not independently verified physical execution counts."
        )
    vector = evidence.get(
        "triggering_input",
        legacy.get("triggering_input") if type(legacy) is dict else None,
    )
    observation = evidence.get("observation", {})
    if type(observation) is dict and observation.get("inputs_read_back") is not None:
        lines.append("Observed input readback: " + str(observation["inputs_read_back"]))
    if vector is not None:
        lines.append("Recorded triggering vector: " + str(vector))
    lines.append(
        "Full JSON and retained diagnostics remain authoritative. No hardware or hostile-input validation is implied."
    )
    return "\n".join(lines)
