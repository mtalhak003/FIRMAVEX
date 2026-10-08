"""Pilot mechanics tests; synthetic clocks/executors are not runtime measurements."""

import ctypes
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.firmavex.evaluation.api import ExecutionSignature, InputSpace, TrialFeedback, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.protocols import provenance
from tools import runtime_feasibility_pilot as pilot


def test_fixed_pilot_is_twelve_predeclared_attempts_in_exact_order():
    expected = [
        ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", [9, 5, 4, 5], "safe", "development"),
        ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", [12, 8, 4, 5], "triggered", "development"),
        ("b-965d82f3548943c5bfb218d7e0c5351c", [7, 8, 7, 6], "safe", "development"),
        ("b-965d82f3548943c5bfb218d7e0c5351c", [7, 8, 7, 5], "triggered", "development"),
        ("b-b5ba43a1f81041a28dcb6e10f0754d91", [6, 3, 12, 8], "safe", "held_out"),
        ("b-b5ba43a1f81041a28dcb6e10f0754d91", [6, 3, 12, 9], "triggered", "held_out"),
    ] * 2
    plan = pilot.pilot_plan()
    assert plan["maximum_attempts"] == 12
    assert plan["execution_budget_per_session"] == 1
    assert plan["cumulative_attempt_time_limit_ns"] == 60_000_000_000
    assert [(item["benchmark_id"], item["values"], item["expected_status"], item["partition"])
            for item in plan["ordered_attempts"]] == expected
    assert [item["ordinal"] for item in plan["ordered_attempts"]] == list(range(1, 13))
    assert [item["round"] for item in plan["ordered_attempts"]] == [1] * 6 + [2] * 6
    assert "not_controlled_campaign" in plan["purpose"]


def test_plan_callers_cannot_modify_later_declarations():
    first = pilot.pilot_plan()
    first["ordered_attempts"][0]["values"][0] = 99
    assert pilot.pilot_plan()["ordered_attempts"][0]["values"] == [9, 5, 4, 5]


def test_output_must_be_new_and_outside_checkout(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        pilot._new_output_directory(pilot.REPOSITORY / "not-created-pilot")
    with pytest.raises(FileExistsError):
        pilot._new_output_directory(tmp_path)
    new = tmp_path / "new"
    assert pilot._new_output_directory(new) == new.resolve()


def test_real_popen_observer_delegates_and_restores():
    original = subprocess.Popen
    observer = pilot.ProcessObserver()
    command = [sys.executable, "-c", "print('host-process-only')"]
    with observer.installed():
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert subprocess.Popen is original
    assert result.stdout == "host-process-only\n"
    records = observer.completed_records()
    assert len(records) == 1 and records[0]["command"] == command
    assert records[0]["cwd"] == str(Path.cwd())
    assert records[0]["pid"] > 0 and records[0]["return_code"] == 0
    assert all(records[0]["pipes_closed"].values())
    assert {event["operation"] for event in records[0]["operations"]} >= {"spawn", "communicate", "wait", "context_exit"}
    assert pilot._cleanup_failures(records) == []


def test_real_host_process_timeout_is_observed_and_reaped():
    observer = pilot.ProcessObserver()
    with observer.installed():
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run([sys.executable, "-c", "import time; time.sleep(5)"],
                           capture_output=True, text=True, timeout=0.05)
    record, = observer.completed_records()
    assert record["return_code"] is not None
    assert any(event["operation"] == "communicate" and event.get("error_type") == "TimeoutExpired"
               for event in record["operations"])
    assert any(event["operation"] == "kill" for event in record["operations"])
    assert pilot._cleanup_failures([record]) == []


def test_observer_restores_popen_on_interruption():
    original = subprocess.Popen
    with pytest.raises(KeyboardInterrupt):
        with pilot.ProcessObserver().installed():
            raise KeyboardInterrupt()
    assert subprocess.Popen is original


def test_successful_kill_escalation_is_not_cleanup_failure():
    process = {"pid": 17, "return_code": -9, "pipes_closed": {"stderr": True}, "operations": [
        {"operation": "wait", "error_type": "TimeoutExpired", "error": "two-second wait"},
        {"operation": "kill"}, {"operation": "wait"},
    ]}
    assert pilot._cleanup_failures([process]) == []
    process["return_code"] = None
    process["pipes_closed"]["stderr"] = False
    process["operations"].append({"operation": "terminate", "error_type": "OSError", "error": "signal failed"})
    failures = pilot._cleanup_failures([process])
    assert len(failures) == 3
    assert any("remains unreaped/alive" in message for message in failures)
    assert any("open process pipe" in message for message in failures)
    assert any("signal failed" in message for message in failures)


def test_timing_statistics_use_all_attempts_and_authoritative_counts():
    attempts = [{"elapsed_ns": seconds * 1_000_000_000,
                 "evaluation": {"attempted_executions": 1, "successful_executions": int(seconds != 3),
                                "infrastructure_failures": int(seconds == 3)},
                 "timed_out": seconds == 3, "cleanup_failures": []} for seconds in (1, 2, 3)]
    summary = pilot.timing_summary(attempts)
    assert summary["minimum_seconds"] == 1
    assert summary["mean_seconds"] == summary["median_seconds"] == 2
    assert summary["maximum_seconds"] == summary["p95_nearest_rank_seconds"] == 3
    assert summary["attempted_executions"] == 3 and summary["successful_completions"] == 2
    assert summary["timeouts"] == summary["infrastructure_failures"] == 1
    assert summary["attempts_per_second"] == 0.5
    assert summary["successful_completions_per_second"] == pytest.approx(1 / 3)
    assert summary["projected_seconds_at_sample_mean"] == {
        "one_256_attempt_run": 512, "one_21_run_benchmark": 10752,
        "six_development_benchmarks": 64512, "two_held_out_benchmarks": 21504,
        "all_168_runs": 86016,
    }
    assert pilot.timing_summary([])["attempts_per_second"] is None


@pytest.fixture
def unit_driver(monkeypatch, tmp_path):
    """Fake firmware for control-flow tests, explicitly marked unit-test environment."""
    output = tmp_path / "unit-test-only-output"
    clock = SimpleNamespace(now=0)
    dispatched = []
    behavior = {"error": None, "infra": False, "mismatch": False, "elapsed_ns": 1_000_000_000}
    real_specs = [spec for split in ("development", "held_out") for spec in pilot.BenchmarkRegistry().select(split)]
    expected = {
        ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", (9, 5, 4, 5)): "safe",
        ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", (12, 8, 4, 5)): "triggered",
        ("b-965d82f3548943c5bfb218d7e0c5351c", (7, 8, 7, 6)): "safe",
        ("b-965d82f3548943c5bfb218d7e0c5351c", (7, 8, 7, 5)): "triggered",
        ("b-b5ba43a1f81041a28dcb6e10f0754d91", (6, 3, 12, 8)): "safe",
        ("b-b5ba43a1f81041a28dcb6e10f0754d91", (6, 3, 12, 9)): "triggered",
    }

    class UnitRegistry:
        def select(self, split):
            return [spec for spec in real_specs if spec.split == split]

        def build(self, identifier, path):
            assert (output / "pilot-plan.json").is_file()
            path.write_bytes(b"unit-test dummy firmware; never executed")
            return {"success": True, "output_file": str(path), "stderr": "", "stdout": "", "return_code": 0}

        def open_session(self, identifier, budget, strategy_id):
            assert budget == 1 and strategy_id == "feasibility-pilot"

            def executor(values):
                dispatched.append((identifier, values))
                clock.now += behavior["elapsed_ns"]
                if behavior["error"] is not None:
                    raise behavior["error"]
                if behavior["infra"]:
                    return Observation(False, stderr="unit-test infrastructure diagnostic")
                triggered = expected[identifier, values] == "triggered"
                return Observation(True, not triggered if behavior["mismatch"] else triggered)

            return EvaluationSession(identifier, InputSpace(4, 0, 15), budget, strategy_id, executor)

    def environment(repository):
        assert repository == pilot.REPOSITORY
        plan_path = output / "pilot-plan.json"
        assert hashlib.sha256(plan_path.read_bytes()).hexdigest() == (output / "pilot-plan.sha256").read_text().strip()
        assert plan_path.stat().st_mode & 0o222 == 0
        return {"unit_test_only": True}

    monkeypatch.setattr(pilot, "BenchmarkRegistry", UnitRegistry)
    monkeypatch.setattr(pilot.time, "monotonic_ns", lambda: clock.now)
    monkeypatch.setattr(provenance, "capture_environment", environment)
    return output, dispatched, behavior


def test_fixed_limit_dispatches_exactly_twelve_then_stops(unit_driver):
    output, dispatched, _ = unit_driver
    report = pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert len(dispatched) == 12
    assert report["stop_reason"] == "completed_fixed_sample"
    assert report["requested_measurement_mode"] == report["measurement"] == "synthetic_test"
    assert report["final_verification"] == "passed"
    assert report["summary"]["attempted_executions"] == report["summary"]["successful_completions"] == 12
    assert report["summary"]["infrastructure_failures"] == 0
    assert report["total_pilot_wall_seconds"] == 12
    persisted = json.loads((output / "pilot-observations.json").read_text())
    assert persisted["summary"] == report["summary"]


def test_sixty_second_limit_stops_before_another_admission(unit_driver):
    output, dispatched, behavior = unit_driver
    behavior["elapsed_ns"] = 60_000_000_000
    report = pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert len(dispatched) == 1
    assert report["stop_reason"] == "cumulative_attempt_time_limit"
    assert report["summary"]["attempted_executions"] == 1


@pytest.mark.parametrize("kind, reason", [("infra", "infrastructure_failure"), ("mismatch", "outcome_mismatch")])
def test_first_bad_outcome_prevents_later_dispatch(unit_driver, kind, reason):
    output, dispatched, behavior = unit_driver
    behavior[kind] = True
    report = pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert len(dispatched) == 1 and report["stop_reason"] == reason
    assert report["summary"]["attempted_executions"] == 1
    if kind == "infra":
        assert report["summary"]["infrastructure_failures"] == 1
        assert report["attempts"][0]["evaluation"]["aborted"]
        assert "unit-test infrastructure diagnostic" in report["attempts"][0]["diagnostics"][0]["stderr"]


def test_cleanup_failure_prevents_later_dispatch(unit_driver, monkeypatch):
    output, dispatched, _ = unit_driver
    original = pilot._cleanup_failures
    calls = []

    def cleanup(processes):
        calls.append(None)
        return ["unit-test cleanup failure"] if len(calls) > 3 else original(processes)

    monkeypatch.setattr(pilot, "_cleanup_failures", cleanup)
    report = pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert len(dispatched) == 1 and report["stop_reason"] == "cleanup_failure"
    assert report["summary"]["cleanup_failure_attempts"] == 1


@pytest.mark.parametrize("exception", [KeyboardInterrupt("unit-test cancellation"), SystemExit("unit-test termination")])
def test_interrupted_attempt_is_persisted_charged_and_reraised(unit_driver, exception):
    output, dispatched, behavior = unit_driver
    behavior["error"] = exception
    with pytest.raises(type(exception)) as caught:
        pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert caught.value is exception and len(dispatched) == 1
    report = json.loads((output / "pilot-observations.json").read_text())
    assert report["stop_reason"] == "interrupted"
    assert report["summary"]["attempted_executions"] == report["summary"]["infrastructure_failures"] == 1
    assert report["summary"]["successful_completions"] == 0
    assert report["attempts"][0]["evaluation"]["aborted"]
    assert exception.__class__.__name__ in report["attempts"][0]["diagnostics"][0]["stderr"]


def test_final_storage_failure_does_not_replace_keyboard_interrupt(unit_driver, monkeypatch):
    output, dispatched, behavior = unit_driver
    interruption = KeyboardInterrupt("original control flow")
    behavior["error"] = interruption
    write = pilot._write_json

    def fail_observations(path, value, **kwargs):
        if path.name == "pilot-observations.json":
            raise OSError("unit-test disk failure")
        return write(path, value, **kwargs)

    monkeypatch.setattr(pilot, "_write_json", fail_observations)
    with pytest.raises(KeyboardInterrupt) as caught:
        pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert caught.value is interruption and len(dispatched) == 1
    assert any("disk failure" in note for note in interruption.__notes__)


def test_post_interruption_inspection_failure_preserves_actual_accounting(unit_driver, monkeypatch):
    output, dispatched, behavior = unit_driver
    interruption = SystemExit("original control flow")
    behavior["error"] = interruption
    inspect_processes = pilot.ProcessObserver.completed_records
    calls = []

    def fail_attempt_inspection(observer, start=0):
        calls.append(None)
        if len(calls) == 4:
            raise OSError("unit-test inspection failure")
        return inspect_processes(observer, start)

    monkeypatch.setattr(pilot.ProcessObserver, "completed_records", fail_attempt_inspection)
    with pytest.raises(SystemExit) as caught:
        pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert caught.value is interruption and len(dispatched) == 1
    report = json.loads((output / "pilot-observations.json").read_text())
    assert report["summary"]["attempted_executions"] == report["summary"]["infrastructure_failures"] == 1
    assert "inspection failure" in report["attempts"][0]["inspection_error"]


@pytest.mark.parametrize("mode", [None, True, "unknown"])
def test_unsupported_mode_does_not_create_output(tmp_path, mode):
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="measurement_mode"):
        pilot.run_pilot(output, measurement_mode=mode)
    assert not output.exists()


def test_real_request_rejects_explicit_unit_environment_without_dispatch(unit_driver):
    output, dispatched, _ = unit_driver
    report = pilot.run_pilot(output)
    assert dispatched == [] and report["builds"] == []
    assert report["requested_measurement_mode"] == "real_firmware"
    assert report["measurement"] == "unverified" and report["final_verification"] == "failed"
    assert report["execution_completion"] == "measurement_mode_conflict"
    assert any("unit_test_only" in message for message in report["verification_errors"])


def test_real_caller_label_alone_cannot_verify_fake_builds(unit_driver, monkeypatch):
    output, dispatched, _ = unit_driver
    monkeypatch.setattr(provenance, "capture_environment", lambda _: {})
    report = pilot.run_pilot(output, measurement_mode="real_firmware")
    assert dispatched == [] and len(report["builds"]) == 3
    assert report["measurement"] == "unverified" and report["final_verification"] == "failed"
    assert report["execution_completion"] == "build_evidence_failure"
    assert any("ARM ELF32" in message for message in report["verification_errors"])


def test_partition_drift_is_rejected_before_build_or_dispatch(unit_driver, monkeypatch):
    output, dispatched, _ = unit_driver
    select = pilot.BenchmarkRegistry.select

    def changed_select(registry, split):
        return [replace(spec, split="development") if spec.name == "finite_state_machine" else spec
                for spec in select(registry, split)]

    monkeypatch.setattr(pilot.BenchmarkRegistry, "select", changed_select)
    with pytest.raises(ValueError, match="identities"):
        pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert dispatched == []
    report = json.loads((output / "pilot-observations.json").read_text())
    assert report["builds"] == [] and report["final_verification"] == "failed"


def test_final_only_inspection_failure_retains_completion_and_fails_cli(unit_driver, monkeypatch):
    output, dispatched, _ = unit_driver
    original_run = pilot.run_pilot
    inspect_processes = pilot.ProcessObserver.completed_records
    calls = []

    def final_inspection_failure(observer, start=0):
        calls.append(None)
        # Three builds, twelve attempt inspections and twelve progress reports.
        if len(calls) == 28:
            raise OSError("unit-test final inspection failure")
        return inspect_processes(observer, start)

    monkeypatch.setattr(pilot.ProcessObserver, "completed_records", final_inspection_failure)
    monkeypatch.setattr(pilot, "run_pilot", lambda path: original_run(path, measurement_mode="synthetic_test"))
    monkeypatch.setattr(sys, "argv", ["pilot-unit-test", "--output-dir", str(output)])
    assert pilot.main() == 1
    report = json.loads((output / "pilot-observations.json").read_text())
    assert len(dispatched) == report["summary"]["successful_completions"] == 12
    assert report["execution_completion"] == "completed_fixed_sample"
    assert report["final_verification"] == "failed" and report["stop_reason"] == "final_verification_failed"
    assert report["owned_live_pids"] is None
    assert report["process_inspection_error"]["message"] == "unit-test final inspection failure"


@pytest.mark.parametrize("secondary", [KeyboardInterrupt("secondary interruption"), SystemExit("secondary termination")])
def test_finalization_control_flow_does_not_replace_original_interruption(unit_driver, monkeypatch, secondary):
    output, dispatched, behavior = unit_driver
    original = KeyboardInterrupt("original interruption")
    behavior["error"] = original
    write = pilot._write_json

    def fail_observations(path, value, **kwargs):
        if path.name == "pilot-observations.json":
            raise secondary
        return write(path, value, **kwargs)

    monkeypatch.setattr(pilot, "_write_json", fail_observations)
    with pytest.raises(KeyboardInterrupt) as caught:
        pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert caught.value is original and len(dispatched) == 1
    assert any(type(secondary).__name__ in note for note in original.__notes__)


def test_failed_storage_and_stderr_do_not_replace_original_interruption(unit_driver, monkeypatch):
    output, dispatched, behavior = unit_driver
    original = KeyboardInterrupt("original interruption")
    behavior["error"] = original
    write = pilot._write_json

    def fail_observations(path, value, **kwargs):
        if path.name == "pilot-observations.json":
            raise OSError("unit-test storage failure")
        return write(path, value, **kwargs)

    def failed_stderr(message):
        raise BrokenPipeError("unit-test stderr failure")

    monkeypatch.setattr(pilot, "_write_json", fail_observations)
    monkeypatch.setattr(sys, "stderr", SimpleNamespace(write=failed_stderr, flush=lambda: None))
    with pytest.raises(KeyboardInterrupt) as caught:
        pilot.run_pilot(output, measurement_mode="synthetic_test")
    assert caught.value is original and len(dispatched) == 1
    assert any("storage failure" in note for note in original.__notes__)


@pytest.fixture
def evidence_records(tmp_path):
    """Forged consistency records only; not an attestation or firmware measurement."""
    def process(command, pid, return_code=0):
        return {"command": command, "pid": pid, "return_code": return_code,
                "pipes_closed": {"stdout": True, "stderr": True},
                "operations": [{"operation": "spawn"}, {"operation": "communicate"}, {"operation": "wait"}]}

    report = {"builds": [], "attempts": []}
    for index, (identifier, name) in enumerate((
        ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", "nested_branches"),
        ("b-965d82f3548943c5bfb218d7e0c5351c", "ordered_accumulator"),
        ("b-b5ba43a1f81041a28dcb6e10f0754d91", "finite_state_machine"),
    )):
        image = tmp_path / f"{name}.elf"
        header = bytearray(52)
        header[:7] = b"\x7fELF\x01\x01\x01"
        header[18:20] = (40).to_bytes(2, "little")
        image.write_bytes(header)
        source = str(pilot.CORPUS_DIR / f"{name}.c")
        command = ["/tool/arm-none-eabi-gcc", "-mcpu=cortex-m3", "-mthumb", "-g", "-O0", "-ffreestanding",
                   "-nostdlib", "-Wl,--build-id=none", "-T", str(pilot.SUPPORT_DIR / "linker.ld"),
                   str(pilot.SUPPORT_DIR / "startup.c"), source, str(pilot.CORPUS_DIR / "harness.c"),
                   "-o", str(tmp_path / "transient-firmware.elf")]
        report["builds"].append({"benchmark_id": identifier, "source": source,
                                  "result": {"success": True, "return_code": 0, "output_file": str(image)},
                                  "image": provenance.describe_artifact(image), "processes": [process(command, 100 + index)]})
    identifier = "b-08e9f32ef15d4ef0b17b65a4c211f8e2"
    owner = EvaluationSession(identifier, InputSpace(4, 0, 15), 1, "evidence-unit-test",
                              lambda _: Observation(True, execution_signature=ExecutionSignature("a" * 64)))
    feedback = owner.execute(TrialInput((9, 5, 4, 5)))
    image = report["builds"][0]["image"]["path"]
    from src.firmavex.monitor.signature import _collector_command
    gdb = ["arm-none-eabi-gdb", image, "--batch"]
    for command in ["target remote 127.0.0.1:54321", "set variable firmavex_actions[0] = 9",
                    "set variable firmavex_actions[1] = 5", "set variable firmavex_actions[2] = 4",
                    "set variable firmavex_actions[3] = 5", "break benchmark_complete", _collector_command(),
                    'printf "FIRMAVEX_VALUE=0x%x\\n", firmavex_failure']:
        gdb.extend(["-ex", command])
    report["attempts"].append({"ordinal": 1, "benchmark_id": identifier, "values": [9, 5, 4, 5],
                               "evaluation": asdict(owner.result()), "feedback": asdict(feedback),
                               "processes": [process(["qemu-system-arm", "-M", "mps2-an385", "-kernel", image,
                                                     "-S", "-gdb", "tcp:127.0.0.1:54321"], 201, -15), process(gdb, 202)]})
    return report


def test_real_evidence_consistency_requires_more_than_a_requested_label(evidence_records):
    assert pilot._real_evidence_errors(evidence_records) == []
    assert pilot._real_evidence_errors({"requested_measurement_mode": "real_firmware", "builds": [], "attempts": []})


@pytest.mark.parametrize("missing", ["compiler", "elf", "qemu", "gdb", "signature", "port", "input", "budget", "digest"])
def test_missing_or_conflicting_real_evidence_fails_closed(evidence_records, missing):
    report = evidence_records
    attempt = report["attempts"][0]
    if missing == "compiler":
        report["builds"][0]["processes"] = []
    elif missing == "elf":
        Path(report["builds"][0]["image"]["path"]).write_bytes(b"not an ELF")
    elif missing in {"qemu", "gdb"}:
        attempt["processes"] = [record for record in attempt["processes"] if missing not in record["command"][0]]
    elif missing == "signature":
        attempt["feedback"]["execution_signature"] = None
    elif missing == "port":
        command = attempt["processes"][1]["command"]
        command[command.index("target remote 127.0.0.1:54321")] = "target remote 127.0.0.1:1234"
    elif missing == "input":
        command = attempt["processes"][1]["command"]
        command[command.index("set variable firmavex_actions[0] = 9")] = "set variable firmavex_actions[0] = 10"
    elif missing == "budget":
        attempt["evaluation"]["execution_budget"] = 2
    else:
        report["builds"][0]["image"]["sha256"] = "0" * 64
    assert pilot._real_evidence_errors(report)


def test_literal_pilot_vectors_agree_with_test_oracle_and_existing_c_sources(tmp_path):
    oracle = json.loads((Path(__file__).parent / "data/cortex_m_v2_ground_truth.json").read_text())["benchmarks"]
    cases = {
        "nested_branches": [((9, 5, 4, 5), 0), ((12, 8, 4, 5), 1)],
        "ordered_accumulator": [((7, 8, 7, 6), 0), ((7, 8, 7, 5), 1)],
        "finite_state_machine": [((6, 3, 12, 8), 0), ((6, 3, 12, 9), 1)],
    }
    for name, vectors in cases.items():
        shared = tmp_path / f"{name}.so"
        compiled = subprocess.run(["gcc", "-shared", "-fPIC", str(pilot.CORPUS_DIR / f"{name}.c"), "-o", str(shared)],
                                  capture_output=True, text=True)
        assert compiled.returncode == 0, compiled.stderr
        function = ctypes.CDLL(str(shared)).benchmark_condition
        function.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
        function.restype = ctypes.c_uint32
        declared_cases = {(tuple(values), outcome) for values, outcome in oracle[name]["cases"]}
        for values, outcome in vectors:
            assert (values, outcome) in declared_cases
            assert function((ctypes.c_uint32 * 4)(*values)) == outcome
