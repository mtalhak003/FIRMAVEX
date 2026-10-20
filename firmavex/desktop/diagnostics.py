"""Bounded display text derived from retained evidence; never modify receipts."""

COMPILER_DIAGNOSTIC_LIMIT = 8192
ARM_REPRODUCTION_LIMIT = 4096
_STREAM_LIMIT = (COMPILER_DIAGNOSTIC_LIMIT - 512) // 2


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
