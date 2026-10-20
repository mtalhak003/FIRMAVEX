"""Qt-free display contracts; compiler output is evidence, not inferred outcome."""

from copy import deepcopy

import pytest

from firmavex.desktop.diagnostics import COMPILER_DIAGNOSTIC_LIMIT, compiler_diagnostics


def record(**fields):
    return {"status": "invalid_input", "evidence": {
        "backend": "verilog-icarus", "measurement_mode": "unverified",
        "cleanup_verified": True, **fields,
    }}


def test_retained_streams_are_labeled_plain_text_without_mutation():
    value = record(compile_stderr="testbench.v:2: syntax error\n", compile_stdout="<module>\n")
    original = deepcopy(value)
    text = compiler_diagnostics(value)
    assert text == ("Compiler diagnostics\nstderr:\ntestbench.v:2: syntax error\n"
                    "\n\nstdout:\n<module>\n")
    assert value == original


@pytest.mark.parametrize("value", [None, [], "error", {}, {"evidence": None},
    {"evidence": []}, {"evidence": {"compile_stderr": "error"}},
    record(), record(compile_stderr=None, compile_stdout=42),
    record(compile_stderr=" \n\t", compile_stdout={"error": "syntax"}),
    record(backend="riscv32-virt", compile_stderr="error"),
    record(backend=[], compile_stderr="error"),
    record(compile_stderr="error", admission={"profile": {"id": "riscv32-virt"}}),
])
def test_absent_malformed_or_non_verilog_evidence_has_no_section(value):
    assert compiler_diagnostics(value) == ""


def test_saved_profile_identity_does_not_require_backend_field():
    value = {"evidence": {"admission": {"profile": {"id": "verilog-icarus"}},
                          "compile_stdout": "retained compiler output"}}
    assert "stdout:\nretained compiler output" in compiler_diagnostics(value)


def test_control_characters_normalized_only_for_display():
    value = record(compile_stderr="one\r\ntwo\rthree\t<error>\x00\x1b[31m\x7f\u0085\u202e\ud800")
    original = deepcopy(value)
    text = compiler_diagnostics(value)
    assert "one\ntwo\nthree\t<error>" in text
    assert all(char.isprintable() or char in "\n\t" for char in text)
    assert "\ufffd" in text and value == original


def test_both_oversized_streams_are_bounded_and_explicitly_truncated():
    value = record(compile_stderr="E" * 100000, compile_stdout="O" * 100000)
    text = compiler_diagnostics(value)
    assert len(text) <= COMPILER_DIAGNOSTIC_LIMIT
    assert text.count("Display truncated") == 2
    assert "stderr:\nE" in text and "stdout:\nO" in text
    assert len(value["evidence"]["compile_stderr"]) == 100000


def test_status_is_not_used_to_invent_or_reclassify_diagnostics():
    value = record(compile_stderr="warning from compiler")
    value["status"] = "passed"
    assert "warning from compiler" in compiler_diagnostics(value)
    assert value["status"] == "passed"
    assert compiler_diagnostics({"status": "invalid_input", "evidence": {
        "backend": "verilog-icarus", "error": "No compiler evidence available"}}) == ""
