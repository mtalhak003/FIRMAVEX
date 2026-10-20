"""Bounded display text derived from retained evidence; never modify receipts."""

COMPILER_DIAGNOSTIC_LIMIT = 8192
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
