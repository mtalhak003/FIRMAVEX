"""Bounded display text derived from retained evidence; never modify receipts."""

COMPILER_DIAGNOSTIC_LIMIT = 8192
ARM_REPRODUCTION_LIMIT = 4096
_STREAM_LIMIT = (COMPILER_DIAGNOSTIC_LIMIT - 512) // 2

_ERROR_ACTIONS = {
    "missing_dependency": "Open runtime setup / repair, then check the selected runtime again. The built-in firmware example does not need a compiler.",
    "dependency_probe_failed": "Check the selected executable paths and retained diagnostics, then run the runtime check again. Tool availability is not execution qualification.",
    "unsupported_platform": "The selected platform or runtime is not admitted. Review the expected and observed identities in diagnostics; use a qualified runtime without disabling admission checks.",
    "unsupported_runtime": "Check that QEMU supports the selected board and that GDB supports the target. Select the documented compatible runtime and check readiness again.",
    "runtime_pack_invalid": "Use runtime setup / repair to verify or restore a trusted runtime generation. Do not replace the recorded tool identities to force admission.",
    "invalid_firmware": "Select a readable, compatible ELF image, then check its compatibility. Raw BIN and arbitrary MCU images are not supported.",
    "unsupported_firmware": "Review the target, memory layout and required symbols. ARM testing needs the documented Cortex-M3 MPS2 ELF contract; use the built-in example as a reference.",
    "invalid_configuration": "Review the selected input, symbol bindings and execution settings, then validate again. No execution success is assumed from this message.",
    "configuration_error": "Review the input and execution settings, then validate again before starting a separate run.",
    "invalid_input": "Review the selected backend's input contract. RV32 requires two uint32 values; HDL requires the supported testbench format.",
    "cancelled": "Wait for worker cleanup, then inspect any saved partial record. Cancellation is not a passing test and does not automatically restart work.",
    "worker_interrupted": "Inspect the saved run before recovery or an explicit restart. Missing terminal accounting remains unknown; abandoned work may repeat in a new run.",
    "worker_timeout": "Wait for process cleanup and inspect retained diagnostics. A timeout is an infrastructure failure, not evidence of a safe input.",
    "infrastructure_failure": "Inspect retained diagnostics and cleanup information before a separate attempt. An incomplete observation is not a safe result.",
    "invalid_output": "Inspect the debugger or simulator logs for missing completion or result markers. A trigger alone does not establish successful completion.",
    "firmware_changed": "The saved and selected firmware identities differ. Keep the original result and import the new build as a separate project or revision.",
    "toolchain_changed": "The selected tools differ from the saved run. Preserve its evidence and use a separate project for the changed environment.",
    "output_exists": "Choose a new, empty export destination. Existing results and exports must not be overwritten.",
    "incomplete_run": "Inspect the run's saved state first. Export requires an authoritative terminal result; do not invent missing observations.",
    "no_saved_trigger": "Select a saved run containing an exact triggering vector before requesting reproduction.",
}


def operation_error_text(error, operation=None):
    """Bounded GUI guidance; never infer outcomes, counts or trust from an error.

    Only category/message fields are read here. Separate administrative details,
    stream and environment fields stay in the existing diagnostics view; a
    message may still contain diagnostic text. Display this string as plain text.
    """
    def visible(value, limit, fallback):
        if type(value) is not str or not value:
            return fallback
        text = ''.join(char if char.isprintable() else '\ufffd' for char in value[:limit])
        return text + ('…' if len(value) > limit else '')
    value = error if type(error) is dict else {}
    category = visible(value.get('category'), 80, 'operation_failed')
    message = visible(value.get('message'), 1200, 'The operation could not be completed.')
    action = _ERROR_ACTIONS.get(category,
        "Review the retained diagnostics and selected project before starting a separate operation. No successful execution is assumed.")
    if type(operation) is str and operation in {'export', 'backend_export', 'backend_verification_report', 'export_verification_report'}:
        action += " No completed export is confirmed. Choose a new writable destination after inspecting the failure."
    return category + ': ' + message + '\nNext: ' + action


def compiler_diagnostics(record):
    """Return retained Verilog compiler output, or no section without evidence.

    Identity comes from the record, never the currently selected UI profile.
    Both streams get a bounded preview; stderr is shown first. Non-printing
    characters are replaced for display only. This does not infer compilation
    success/failure or alter the recorded outcome and measurement classification.
    """
    if type(record) is not dict or type(record.get("evidence")) is not dict:
        return ""
    evidence = record["evidence"]
    identities = []
    if "backend" in evidence:
        identities.append(evidence["backend"])
    admission = evidence.get("admission")
    if type(admission) is dict:
        profile = admission.get("profile")
        if type(profile) is dict and "id" in profile:
            identities.append(profile["id"])
    if not identities or any(value != "verilog-icarus" for value in identities):
        return ""
    sections = []
    for field, label in (("compile_stderr", "stderr"), ("compile_stdout", "stdout")):
        value = evidence.get(field)
        if type(value) is not str or not value:
            continue
        # Slice before normalization/sanitization to bound work on large logs.
        preview = value[:_STREAM_LIMIT].replace("\r\n", "\n").replace("\r", "\n")
        preview = "".join(char if char.isprintable() or char in "\n\t" else "\ufffd"
                          for char in preview)
        if not preview.strip() and len(value) <= _STREAM_LIMIT:
            continue
        if len(value) > _STREAM_LIMIT:
            preview += "\n[Display truncated; complete retained output remains in the evidence.]"
        sections.append(label + ":\n" + preview)
    if not sections:
        return ""
    return "Compiler diagnostics\n" + "\n\n".join(sections)


def arm_reproduction_summary(record):
    """Display recorded ARM replay evidence without calculating a verdict/count.

    Interrupted replays may lack a reproduction object. Their recorded parent
    operation (or nested admission reproduction_of) identifies the replay; absent
    replay fields remain unknown, even if accounting contains similar counts.
    """
    if type(record) is not dict:
        return ""
    backend_status = None
    interrupted_replay = False
    if record.get("kind") == "firmavex_product_result":
        result = record
    else:
        evidence = record.get("evidence")
        if type(evidence) is not dict:
            return ""
        admission = evidence.get("admission")
        if type(admission) is not dict:
            return ""
        profile = admission.get("profile")
        if type(profile) is not dict or profile.get("id") != "cortex-m3-mps2":
            return ""
        result = evidence.get("legacy_result")
        if type(result) is not dict or result.get("kind") != "firmavex_product_result":
            # A wrapper can retain only an interruption record. Do not substitute
            # its status or accounting for absent authoritative ARM replay fields.
            if type(admission.get("reproduction_of")) is not str or not admission["reproduction_of"]:
                return ""
            result = {}
            interrupted_replay = True
        backend_status = record.get("status")
    parent = result.get("parent")
    if not interrupted_replay and "reproduction" not in result and not (
        type(parent) is dict and parent.get("operation") == "reproduction"
    ):
        return ""
    reproduction = result.get("reproduction")
    reproduction = reproduction if type(reproduction) is dict else {}
    accounting = result.get("accounting")
    accounting = accounting if type(accounting) is dict else {}

    def text(value):
        if type(value) is not str or not value:
            return "unknown"
        preview = "".join(c if c.isprintable() else "\ufffd" for c in value[:160])
        if not preview.strip():
            return "unknown"
        return preview + (" [display truncated]" if len(value) > 160 else "")

    def count(value, minimum=0, maximum=2**64 - 1):
        return str(value) if type(value) is int and minimum <= value <= maximum else "unknown"

    def vector(value):
        if (type(value) is not list or not 1 <= len(value) <= 64
                or any(type(v) is not int or not 0 <= v <= 0xFFFFFFFF for v in value)):
            return "unknown"
        return "[" + ", ".join(str(v) for v in value) + "]"

    lines = [
        "ARM reproduction summary",
        "Saved replay input: " + vector(reproduction.get("input")),
        "Newly observed triggering input: " + vector(result.get("triggering_input")),
        "Requested repetitions: " + count(reproduction.get("requested_attempts"), 1, 100),
        "Completed observations: " + count(reproduction.get("completed_observations")),
        "Matching failure observations: " + count(reproduction.get("matching_observations")),
        "Infrastructure failures: " + count(accounting.get("infrastructure_failures")),
        "Recorded reproduction status: " + text(reproduction.get("status")),
        "Recorded outcome: " + text(result.get("outcome")),
        "Recorded run state: " + text(result.get("state")),
        "Measurement mode: " + text(result.get("measurement_mode")),
        "Evidence completeness: " + text(result.get("execution_evidence")),
    ]
    if backend_status is not None:
        lines.append("Recorded backend status: " + text(backend_status))
    lines.append("A triggering observation alone does not establish successful reproduction. "
                 "Full recorded evidence remains authoritative.")
    return "\n".join(lines)
