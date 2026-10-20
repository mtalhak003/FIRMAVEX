"""Recorded replay presentation only; synthetic cases are not native evidence."""

from copy import deepcopy

import pytest

from firmavex.desktop.diagnostics import ARM_REPRODUCTION_LIMIT, arm_reproduction_summary


def replay(**changes):
    return {"kind": "firmavex_product_result", "state": "completed",
            "outcome": "reproduced_in_emulator", "measurement_mode": "synthetic_test",
            "execution_evidence": "complete", "triggering_input": [2, 1],
            "parent": {"operation": "reproduction"},
            "accounting": {"infrastructure_failures": 0},
            "reproduction": {"input": [2, 1], "requested_attempts": 3,
                "completed_observations": 3, "matching_observations": 3,
                "status": "reproduced_in_emulator"}, **changes}


@pytest.mark.parametrize("status,matches,completed,failures,state", [
    ("reproduced_in_emulator", 3, 3, 0, "completed"),
    ("reproduction_inconsistent", 2, 3, 0, "completed"),
    ("indeterminate", 1, 1, 1, "failed"),
    ("cancelled", 0, 0, 1, "cancelled"),
])
def test_replay_fields_and_classification_are_preserved(status, matches, completed, failures, state):
    value = replay(state=state, outcome="infrastructure_failure" if failures else status)
    value["reproduction"].update(status=status, matching_observations=matches,
                                  completed_observations=completed)
    value["accounting"]["infrastructure_failures"] = failures
    original = deepcopy(value)
    text = arm_reproduction_summary(value)
    for line in ["Saved replay input: [2, 1]", "Newly observed triggering input: [2, 1]",
                 "Requested repetitions: 3", f"Completed observations: {completed}",
                 f"Matching failure observations: {matches}", f"Infrastructure failures: {failures}",
                 f"Recorded reproduction status: {status}", f"Recorded outcome: {value['outcome']}",
                 f"Recorded run state: {state}", "Measurement mode: synthetic_test",
                 "Evidence completeness: complete"]:
        assert line in text
    assert "alone does not establish successful reproduction" in text
    assert value == original


def test_actual_cancelled_shape_does_not_infer_missing_replay_fields():
    value = replay(state="cancelled", outcome="cancelled", execution_evidence="incomplete")
    del value["reproduction"]
    value["accounting"].update(successful_executions=2, failure_triggering_executions=1, execution_budget=3)
    text = arm_reproduction_summary(value)
    assert "Requested repetitions: unknown" in text
    assert "Completed observations: unknown" in text
    assert "Matching failure observations: unknown" in text
    assert "Saved replay input: unknown" in text
    assert "Recorded reproduction status: unknown" in text
    assert "Recorded outcome: cancelled" in text


@pytest.mark.parametrize("requested", [0, 101])
def test_requested_count_outside_recorded_contract_is_unknown(requested):
    value = replay()
    value['reproduction']['requested_attempts'] = requested
    assert 'Requested repetitions: unknown' in arm_reproduction_summary(value)


def test_replay_input_is_not_replaced_with_trigger_and_no_match_stays_unknown():
    value = replay(triggering_input=None)
    text = arm_reproduction_summary(value)
    assert "Saved replay input: [2, 1]" in text
    assert "Newly observed triggering input: unknown" in text


@pytest.mark.parametrize("value", [None, [], {}, {"kind": "firmavex_product_result"},
    {"evidence": {"legacy_result": replay()}},
    {"evidence": {"admission": {"profile": {"id": "riscv32-virt"}}, "legacy_result": replay()}},
])
def test_absent_replay_or_non_arm_identity_has_no_summary(value):
    assert arm_reproduction_summary(value) == ""


@pytest.mark.parametrize("bad", [None, True, -1, "3", [], {}, 2**100])
def test_malformed_counts_are_unknown(bad):
    value = replay(accounting={"infrastructure_failures": bad}, triggering_input=bad)
    value["reproduction"] = {"requested_attempts": bad, "completed_observations": bad,
                             "matching_observations": bad, "status": bad, "input": bad}
    text = arm_reproduction_summary(value)
    for label in ("Requested repetitions", "Completed observations", "Matching failure observations",
                  "Infrastructure failures", "Saved replay input", "Newly observed triggering input"):
        assert label + ": unknown" in text


@pytest.mark.parametrize("field", ["accounting", "reproduction"])
def test_malformed_containers_are_unknown(field):
    text = arm_reproduction_summary(replay(**{field: []}))
    assert ("Infrastructure failures: unknown" if field == "accounting" else
            "Recorded reproduction status: unknown") in text


def test_text_is_plain_bounded_and_records_are_untouched():
    value = replay(outcome="<failure>\x00\x1b\u202e\ud800\n" + "x" * 100000,
                   state={}, measurement_mode=True, execution_evidence=None,
                   triggering_input=[0xFFFFFFFF] * 64)
    value["reproduction"]["input"] = [0xFFFFFFFF] * 64
    original = deepcopy(value)
    text = arm_reproduction_summary(value)
    assert len(text) <= ARM_REPRODUCTION_LIMIT
    assert "<failure>" in text and "[display truncated]" in text
    assert all(c.isprintable() or c == "\n" for c in text)
    assert "Recorded run state: unknown" in text
    assert "Measurement mode: unknown" in text and "Evidence completeness: unknown" in text
    assert value == original


@pytest.mark.parametrize("vector", [[], [True], [-1], [2**32], [1] * 65, "2, 1", [1, "2"]])
def test_malformed_vector_is_unknown(vector):
    value = replay(triggering_input=vector)
    value["reproduction"]["input"] = vector
    text = arm_reproduction_summary(value)
    assert "Saved replay input: unknown" in text and "Newly observed triggering input: unknown" in text


def test_nested_arm_status_is_separate_and_missing_authoritative_record_is_unknown():
    value = {"status": "infrastructure_failure", "evidence": {
        "admission": {"profile": {"id": "cortex-m3-mps2"}, "reproduction_of": "/saved"},
        "legacy_result": replay(outcome="infrastructure_failure")}}
    original = deepcopy(value)
    text = arm_reproduction_summary(value)
    assert "Recorded backend status: infrastructure_failure" in text
    assert "Recorded outcome: infrastructure_failure" in text
    assert value == original
    del value["evidence"]["legacy_result"]
    text = arm_reproduction_summary(value)
    assert "ARM reproduction summary" in text and "Requested repetitions: unknown" in text
    assert "Measurement mode: unknown" in text
    assert "Recorded backend status: infrastructure_failure" in text
