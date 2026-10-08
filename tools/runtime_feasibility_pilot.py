"""Bounded administrator pilot using real firmware, separate from campaigns.

The executable path never substitutes an executor or changes runtime behavior.
Process observations delegate to the real Popen implementation. Unit tests may
replace dependencies to exercise stop/persistence behavior, not measure firmware.
"""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time


REPOSITORY = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(REPOSITORY))

from src.firmavex.compiler.cortex_m import SUPPORT_DIR
from src.firmavex.evaluation.api import ExecutionSignature, TrialInput
from src.firmavex.evaluation.registry import BenchmarkRegistry, CORPUS_DIR


MAX_ATTEMPTS = 12
ATTEMPT_TIME_LIMIT_NS = 60_000_000_000
_SAMPLE = (
    ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", "nested_branches", (9, 5, 4, 5), "safe"),
    ("b-08e9f32ef15d4ef0b17b65a4c211f8e2", "nested_branches", (12, 8, 4, 5), "triggered"),
    ("b-965d82f3548943c5bfb218d7e0c5351c", "ordered_accumulator", (7, 8, 7, 6), "safe"),
    ("b-965d82f3548943c5bfb218d7e0c5351c", "ordered_accumulator", (7, 8, 7, 5), "triggered"),
    ("b-b5ba43a1f81041a28dcb6e10f0754d91", "finite_state_machine", (6, 3, 12, 8), "safe"),
    ("b-b5ba43a1f81041a28dcb6e10f0754d91", "finite_state_machine", (6, 3, 12, 9), "triggered"),
)


def pilot_plan() -> dict:
    """Fixed sample, including expected administrative outcomes, before execution."""
    return {
        "schema_version": 1,
        "purpose": "runtime_feasibility_pilot_not_controlled_campaign",
        "approved_checkpoint": "d14ca9079a5d3465711e5c7cd95ba448a3da58db",
        "declared_at_utc": _utc_now(),
        "maximum_attempts": MAX_ATTEMPTS,
        "cumulative_attempt_time_limit_ns": ATTEMPT_TIME_LIMIT_NS,
        "execution_budget_per_session": 1,
        "stop_policy": "no retries; stop after interruption, infrastructure/cleanup failure, outcome/accounting mismatch, or time limit",
        "ordered_attempts": [
            {"ordinal": index + 1, "round": index // len(_SAMPLE) + 1,
             "benchmark_id": identifier, "name": name,
             "partition": "held_out" if name == "finite_state_machine" else "development",
             "values": list(values), "expected_status": expected}
            for index, (identifier, name, values, expected) in enumerate(_SAMPLE * 2)
        ],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _new_output_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(REPOSITORY):
        raise ValueError("Pilot output must be outside the repository checkout.")
    resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def _runtime_process_snapshot() -> list[dict]:
    """Linux diagnostic snapshot; unrelated pre-existing processes are retained."""
    records = []
    for entry in Path("/proc").iterdir() if Path("/proc").is_dir() else ():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().split(b"\0")
            executable = Path(command[0].decode(errors="replace")).name
            if executable not in {"qemu-system-arm", "arm-none-eabi-gdb", "gdb-multiarch"}:
                continue
            stat = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            records.append({"pid": int(entry.name), "start_ticks": int(stat[19]), "executable": executable})
        except (OSError, ValueError, IndexError):
            continue
    return sorted(records, key=lambda item: item["pid"])


def _fd_count() -> int | None:
    try:
        return len(list(Path("/proc/self/fd").iterdir()))
    except OSError:
        return None


class ProcessObserver:
    """Observe real children without changing commands, timeout, or signals.

    Popen replacement is scoped to this serial pilot process. Its trace adds
    small Python observer overhead and is not a process-isolation mechanism.
    """

    def __init__(self):
        self.records: list[dict] = []
        self.processes: list[subprocess.Popen] = []

    @contextmanager
    def installed(self):
        original = subprocess.Popen
        observer = self

        class TrackedPopen(original):
            def __init__(self, args, *positional, **keywords):
                command = [str(item) for item in args] if isinstance(args, (list, tuple)) else str(args)
                self.pilot_record = {"command": command, "pid": None, "operations": [],
                                     "cwd": str(Path(keywords.get("cwd") or Path.cwd()).resolve())}
                observer.records.append(self.pilot_record)
                self._observe("spawn", lambda: super(TrackedPopen, self).__init__(args, *positional, **keywords))
                self.pilot_record["pid"] = self.pid
                observer.processes.append(self)

            def _observe(self, operation, invoke):
                event = {"operation": operation}
                self.pilot_record["operations"].append(event)
                started = time.monotonic_ns()
                try:
                    return invoke()
                except BaseException as exc:
                    event.update(error_type=type(exc).__name__, error=str(exc))
                    raise
                finally:
                    event["elapsed_ns"] = time.monotonic_ns() - started

            def communicate(self, *args, **kwargs):
                return self._observe("communicate", lambda: super(TrackedPopen, self).communicate(*args, **kwargs))

            def wait(self, *args, **kwargs):
                return self._observe("wait", lambda: super(TrackedPopen, self).wait(*args, **kwargs))

            def terminate(self):
                return self._observe("terminate", lambda: super(TrackedPopen, self).terminate())

            def kill(self):
                return self._observe("kill", lambda: super(TrackedPopen, self).kill())

            def __exit__(self, *args):
                return self._observe("context_exit", lambda: super(TrackedPopen, self).__exit__(*args))

        subprocess.Popen = TrackedPopen
        try:
            yield self
        finally:
            subprocess.Popen = original

    def completed_records(self, start: int = 0) -> list[dict]:
        for process in self.processes:
            record = process.pilot_record
            record["return_code"] = process.poll()
            record["pipes_closed"] = {
                name: getattr(process, name).closed
                for name in ("stdin", "stdout", "stderr") if getattr(process, name) is not None
            }
        return self.records[start:]


def _cleanup_failures(processes: list[dict]) -> list[str]:
    failures = []
    for process in processes:
        if process["pid"] is None:  # Failed spawn is infrastructure, not a leaked child.
            continue
        if process.get("return_code") is None:
            failures.append(f"PID {process['pid']} remains unreaped/alive")
        if not all(process.get("pipes_closed", {}).values()):
            failures.append(f"PID {process['pid']} has an open process pipe")
        for event in process["operations"]:
            if (event["operation"] in {"terminate", "kill", "wait", "context_exit"}
                    and "error_type" in event and event["error_type"] != "TimeoutExpired"):
                failures.append(f"PID {process['pid']} {event['operation']}: {event['error_type']}: {event['error']}")
    return failures


def timing_summary(attempts: list[dict]) -> dict:
    """Descriptive wall-time sample and linear projections, not campaign results."""
    timings = sorted(attempt["elapsed_ns"] / 1e9 for attempt in attempts)
    evaluations = [attempt["evaluation"] for attempt in attempts if attempt["evaluation"] is not None]
    attempted = sum(result["attempted_executions"] for result in evaluations)
    successful = sum(result["successful_executions"] for result in evaluations)
    total = sum(timings)
    mean = statistics.mean(timings) if timings else None
    return {
        "sample_count": len(timings), "attempted_executions": attempted,
        "accounting_unavailable_attempts": len(attempts) - len(evaluations),
        "successful_completions": successful,
        "timeouts": sum(attempt["timed_out"] is True for attempt in attempts),
        "timeout_inspection_unavailable_attempts": sum(attempt["timed_out"] is None for attempt in attempts),
        "infrastructure_failures": sum(result["infrastructure_failures"] for result in evaluations),
        "cleanup_failure_attempts": sum(bool(attempt["cleanup_failures"]) for attempt in attempts),
        "total_attempt_seconds": total,
        "minimum_seconds": min(timings) if timings else None,
        "median_seconds": statistics.median(timings) if timings else None,
        "mean_seconds": mean,
        "maximum_seconds": max(timings) if timings else None,
        "p95_nearest_rank_seconds": timings[math.ceil(0.95 * len(timings)) - 1] if timings else None,
        "attempts_per_second": attempted / total if total > 0 else None,
        "successful_completions_per_second": successful / total if total > 0 else None,
        "projected_seconds_at_sample_mean": {
            label: count * mean if mean is not None else None
            for label, count in (("one_256_attempt_run", 256), ("one_21_run_benchmark", 5376),
                                 ("six_development_benchmarks", 32256), ("two_held_out_benchmarks", 10752),
                                 ("all_168_runs", 43008))
        },
    }


def _accounting_errors(attempt: dict) -> list[str]:
    result = attempt.get("evaluation")
    if type(result) is not dict:
        return ["Evaluator accounting is unavailable."]
    counts = ("execution_budget", "attempted_executions", "successful_executions",
              "infrastructure_failures", "failure_triggering_executions", "budget_remaining")
    if any(type(result.get(name)) is not int for name in counts):
        return ["Evaluator counts are not exact integers."]
    successful, failed = result["successful_executions"], result["infrastructure_failures"]
    triggered = result["failure_triggering_executions"]
    if (result["execution_budget"] != 1 or result["attempted_executions"] != 1
            or successful not in (0, 1) or failed not in (0, 1) or successful + failed != 1
            or triggered not in (0, 1) or triggered > successful or result["budget_remaining"] != 0
            or result.get("budget_exhausted") is not True or result.get("aborted") is not bool(failed)
            or result.get("failure_found") is not bool(triggered)
            or result.get("first_failure_execution") != (1 if triggered else None)):
        return ["Evaluator accounting does not describe one coherent charged attempt."]
    feedback = attempt.get("feedback")
    if feedback is not None:
        expected = "infrastructure_failure" if failed else "triggered" if triggered else "safe"
        if (feedback.get("status") != expected or feedback.get("execution_index") != 1
                or feedback.get("budget_remaining") != 0):
            return ["Feedback contradicts evaluator accounting."]
    return []


def _process_trace(records: list[dict], executable: str, *, successful: bool = False) -> dict:
    matches = [record for record in records if type(record.get("command")) is list
               and record["command"] and Path(record["command"][0]).name == executable]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one observed {executable} process.")
    record = matches[0]
    if type(record.get("pid")) is not int or record["pid"] <= 0:
        raise ValueError(f"{executable} has no observed child PID.")
    spawns = [event for event in record["operations"] if event["operation"] == "spawn"]
    if len(spawns) != 1 or "error_type" in spawns[0]:
        raise ValueError(f"{executable} has no successful observed spawn.")
    communications = [event for event in record["operations"] if event["operation"] == "communicate"]
    if successful and (record.get("return_code") != 0 or not communications
                       or any("error_type" in event for event in communications)):
        raise ValueError(f"{executable} has no successful observed completion.")
    return record


def _option(command: list[str], name: str) -> str:
    if command.count(name) != 1:
        raise ValueError(f"Expected exactly one {name} command option.")
    return command[command.index(name) + 1]


def _real_evidence_errors(report: dict, *, require_attempts: bool = True) -> list[str]:
    """Check observed evidence consistency, not authenticity against hostile code."""
    errors = []
    expected_ids = {item[0] for item in _SAMPLE}
    builds = report.get("builds", [])
    if len(builds) != 3 or {entry["benchmark_id"] for entry in builds} != expected_ids:
        return ["Real firmware classification requires the three observed builds."]
    images = {}
    for entry in builds:
        try:
            if entry["result"]["success"] is not True or entry["result"]["return_code"] != 0:
                raise ValueError("Build result was not successful.")
            artifact = entry["image"]
            image = Path(artifact["path"]).resolve()
            data = image.read_bytes()
            if (len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01"
                    or int.from_bytes(data[18:20], "little") != 40):
                raise ValueError("Image is not ARM ELF32 little-endian firmware.")
            if len(data) != artifact["size_bytes"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
                raise ValueError("Current image does not match its recorded digest/size.")
            if image != Path(entry["result"]["output_file"]).resolve():
                raise ValueError("Build output and image identities disagree.")
            compiler = _process_trace(entry["processes"], "arm-none-eabi-gcc", successful=True)
            command = compiler["command"]
            required = {"-mcpu=cortex-m3", "-mthumb", "-g", "-O0", "-ffreestanding", "-nostdlib",
                        "-Wl,--build-id=none", str(SUPPORT_DIR / "startup.c"), str(CORPUS_DIR / "harness.c"),
                        entry["source"]}
            if not required.issubset(command) or _option(command, "-T") != str(SUPPORT_DIR / "linker.ld"):
                raise ValueError("Observed compiler command does not match this firmware build.")
            _option(command, "-o")
            if _cleanup_failures(entry["processes"]):
                raise ValueError("Build process cleanup failed.")
            images[entry["benchmark_id"]] = image
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            errors.append(f"Build {entry.get('benchmark_id')}: {exc}")
    attempts = report.get("attempts", [])
    if require_attempts and not attempts:
        errors.append("No admitted firmware execution was observed.")
    for attempt in attempts:
        prefix = f"Attempt {attempt.get('ordinal')}: "
        errors.extend(prefix + message for message in _accounting_errors(attempt))
        try:
            image = images[attempt["benchmark_id"]]
            successful = attempt["evaluation"]["successful_executions"] == 1
            if successful:
                feedback = attempt["feedback"]
                if feedback is None or type(feedback.get("execution_signature")) is not dict:
                    raise ValueError("Successful real execution has no public Step 17A signature.")
                ExecutionSignature(**feedback["execution_signature"])
            qemu = _process_trace(attempt["processes"], "qemu-system-arm")
            gdb = _process_trace(attempt["processes"], "arm-none-eabi-gdb", successful=successful)
            qemu_command, gdb_command = qemu["command"], gdb["command"]
            if (_option(qemu_command, "-M") != "mps2-an385" or "-S" not in qemu_command
                    or Path(_option(qemu_command, "-kernel")).resolve() != image
                    or len(gdb_command) < 2 or Path(gdb_command[1]).resolve() != image):
                raise ValueError("Observed QEMU/GDB image or target differs from the build.")
            endpoint = _option(qemu_command, "-gdb")
            if not endpoint.startswith("tcp:127.0.0.1:") or not 1 <= int(endpoint.rsplit(":", 1)[1]) <= 65535:
                raise ValueError("Observed QEMU GDB endpoint is invalid.")
            commands = [gdb_command[index + 1] for index, item in enumerate(gdb_command[:-1]) if item == "-ex"]
            writes = [f"set variable firmavex_actions[{index}] = {value}"
                      for index, value in enumerate(attempt["values"])]
            if commands[:6] != [f"target remote {endpoint[4:]}", *writes, "break benchmark_complete"]:
                raise ValueError("Observed debugger port, input writes, or breakpoint differs from the declaration.")
            if (len(commands) != 8 or not commands[6].startswith("python exec(")
                    or "FIRMAVEX_SIGNATURE_V1=" not in commands[6]
                    or "FIRMAVEX_VALUE=" not in commands[7] or "firmavex_failure" not in commands[7]):
                raise ValueError("Observed signature collection/failure observation commands are missing.")
            if _cleanup_failures(attempt["processes"]) or attempt.get("inspection_error"):
                raise ValueError("Execution cleanup is failed or unknown.")
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            errors.append(prefix + str(exc))
    return errors


def run_pilot(output_directory: Path, *, measurement_mode: str = "real_firmware") -> dict:
    """Run at most the fixed twelve real attempts and persist partial diagnostics."""
    from src.firmavex.protocols.provenance import capture_environment, describe_artifact

    if type(measurement_mode) is not str or measurement_mode not in {"real_firmware", "synthetic_test"}:
        raise ValueError("measurement_mode must be real_firmware or synthetic_test.")
    overall_started = time.monotonic_ns()
    output = _new_output_directory(output_directory)
    plan = pilot_plan()
    plan_path = output / "pilot-plan.json"
    _write_json(plan_path, plan, exclusive=True)
    plan_digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    digest_path = output / "pilot-plan.sha256"
    digest_path.write_text(plan_digest + "\n", encoding="utf-8")
    plan_path.chmod(0o444)
    digest_path.chmod(0o444)
    report = {
        "schema_version": 1, "purpose": plan["purpose"],
        "requested_measurement_mode": measurement_mode,
        "measurement": "unverified" if measurement_mode == "real_firmware" else "synthetic_test",
        "final_verification": "pending", "verification_errors": [],
        "plan_sha256": plan_digest, "started_at_utc": _utc_now(),
        "environment": None,
        "observer_note": "Delegated real Popen tracing adds slight Python overhead; no runtime commands or semantics changed.",
        "baseline_runtime_processes": _runtime_process_snapshot(), "baseline_fd_count": _fd_count(),
        "builds": [], "attempts": [], "stop_reason": "not_started", "execution_completion": "not_started",
    }
    observer = ProcessObserver()

    def fail_verification(message: str):
        if message not in report["verification_errors"]:
            report["verification_errors"].append(message)
        report["final_verification"] = "failed"

    def persist(*, final: bool = False):
        report["updated_at_utc"] = _utc_now()
        report["total_pilot_wall_seconds"] = (time.monotonic_ns() - overall_started) / 1e9
        report["summary"] = timing_summary(report["attempts"])
        for key, inspect in (("final_runtime_processes", _runtime_process_snapshot), ("final_fd_count", _fd_count)):
            try:
                report[key] = inspect()
                if report[key] is None:
                    fail_verification(f"{key} is unavailable; resource state is unknown.")
            except Exception as exc:
                report[key] = None
                fail_verification(f"{key} inspection failed: {type(exc).__name__}: {exc}")
        try:
            report["processes"] = observer.completed_records()
        except Exception as exc:
            report["processes"] = observer.records
            report["process_inspection_error"] = {"type": type(exc).__name__, "message": str(exc)}
            report["owned_live_pids"] = None
            fail_verification(f"Final process inspection failed: {type(exc).__name__}: {exc}")
        else:
            if "process_inspection_error" in report:
                report["owned_live_pids"] = None
            else:
                report["owned_live_pids"] = [record["pid"] for record in report["processes"]
                                             if record["pid"] is not None and record.get("return_code") is None]
                if report["owned_live_pids"]:
                    fail_verification("Owned child processes remain alive/unreaped.")
        if report["stop_reason"] != "final_verification_failed":
            report["execution_completion"] = report["stop_reason"]
        if final:
            for attempt in report["attempts"]:
                for message in _accounting_errors(attempt):
                    fail_verification(f"Attempt {attempt['ordinal']}: {message}")
                if attempt.get("inspection_error"):
                    fail_verification(attempt["inspection_error"])
            if measurement_mode == "real_firmware":
                for message in _real_evidence_errors(report):
                    fail_verification(message)
            if not report["verification_errors"]:
                report["final_verification"] = "passed"
                if measurement_mode == "real_firmware":
                    report["measurement"] = "real_firmware"
        if report["final_verification"] == "failed" and report["stop_reason"] != "interrupted":
            report["stop_reason"] = "final_verification_failed"
        _write_json(output / "pilot-observations.json", report)

    try:
        report["environment"] = capture_environment(REPOSITORY)
        if measurement_mode == "real_firmware" and report["environment"].get("unit_test_only") is True:
            fail_verification("unit_test_only environment contradicts the requested real firmware measurement.")
            report["stop_reason"] = "measurement_mode_conflict"
            return report
        registry = BenchmarkRegistry()
        specs = {spec.benchmark_id: spec for split in ("development", "held_out") for spec in registry.select(split)}
        selected = tuple(dict.fromkeys(item[0] for item in _SAMPLE))
        if any(identifier not in specs or specs[identifier].name != name
               or specs[identifier].split != ("held_out" if name == "finite_state_machine" else "development")
               for identifier, name, _, _ in _SAMPLE):
            fail_verification("Pilot benchmark ID/name/partition identities differ from the declaration.")
            raise ValueError("Pilot benchmark identities no longer match the declared sample.")
        report["sources"] = [describe_artifact(path) for path in (
            SUPPORT_DIR / "startup.c", SUPPORT_DIR / "linker.ld", CORPUS_DIR / "manifest.json",
            CORPUS_DIR / "harness.c", *(specs[identifier].source for identifier in selected),
        )]
        with observer.installed():
            for identifier in selected:
                before = len(observer.records)
                build_started = time.monotonic_ns()
                built = registry.build(identifier, output / f"{specs[identifier].name}.elf")
                build_elapsed_ns = time.monotonic_ns() - build_started
                processes = observer.completed_records(before)
                entry = {"benchmark_id": identifier, "name": specs[identifier].name,
                         "source": str(specs[identifier].source),
                         "elapsed_ns": build_elapsed_ns,
                         "result": built, "processes": processes, "cleanup_failures": _cleanup_failures(processes)}
                report["builds"].append(entry)
                if built["success"]:
                    entry["image"] = describe_artifact(Path(built["output_file"]))
                if not built["success"] or entry["cleanup_failures"]:
                    report["stop_reason"] = "build_failure"
                    return report
            if measurement_mode == "real_firmware":
                evidence_errors = _real_evidence_errors(report, require_attempts=False)
                if evidence_errors:
                    for message in evidence_errors:
                        fail_verification(message)
                    report["stop_reason"] = "build_evidence_failure"
                    return report
            cumulative_ns = 0
            for declaration in plan["ordered_attempts"]:
                if cumulative_ns >= ATTEMPT_TIME_LIMIT_NS:
                    report["stop_reason"] = "cumulative_attempt_time_limit"
                    break
                owner = registry.open_session(declaration["benchmark_id"], 1, "feasibility-pilot")
                before = len(observer.records)
                started = time.monotonic_ns()
                feedback = None
                interruption = None
                try:
                    feedback = owner.execute(TrialInput(tuple(declaration["values"])))
                except BaseException as exc:
                    interruption = exc
                elapsed_ns = time.monotonic_ns() - started
                cumulative_ns += elapsed_ns
                attempt = {**declaration, "elapsed_ns": elapsed_ns,
                           "feedback": asdict(feedback) if feedback is not None else None,
                           "evaluation": None, "diagnostics": [], "processes": [],
                           "cleanup_failures": [], "timed_out": None}
                report["attempts"].append(attempt)
                if interruption is not None:
                    report["stop_reason"] = "interrupted"
                    attempt["exception"] = {"type": type(interruption).__name__, "message": str(interruption)}
                try:
                    # Retain actual accounting before optional process inspection.
                    attempt["evaluation"] = asdict(owner.result())
                    attempt["diagnostics"] = list(owner.diagnostics())
                    processes = observer.completed_records(before)
                    attempt["processes"] = processes
                    attempt["cleanup_failures"] = _cleanup_failures(processes)
                    attempt["timed_out"] = any(event.get("error_type") == "TimeoutExpired"
                                                and event["operation"] == "communicate"
                                                for process in processes for event in process["operations"])
                except BaseException as exc:
                    if interruption is None:
                        raise
                    message = f"Post-interruption inspection failed: {type(exc).__name__}: {exc}"
                    attempt["inspection_error"] = message
                    fail_verification(message)
                    if hasattr(interruption, "add_note"):
                        interruption.add_note(message)
                if interruption is not None:
                    raise interruption
                if attempt["evaluation"]["infrastructure_failures"]:
                    report["stop_reason"] = "infrastructure_failure"
                elif attempt["cleanup_failures"]:
                    report["stop_reason"] = "cleanup_failure"
                elif attempt["evaluation"]["attempted_executions"] != 1:
                    report["stop_reason"] = "accounting_mismatch"
                elif feedback.status != declaration["expected_status"]:
                    report["stop_reason"] = "outcome_mismatch"
                else:
                    report["stop_reason"] = "in_progress"
                persist()
                if report["stop_reason"] != "in_progress":
                    break
            else:
                report["stop_reason"] = "completed_fixed_sample"
        return report
    except BaseException as exc:
        report["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        if report["stop_reason"] != "interrupted":
            report["stop_reason"] = "driver_exception"
        raise
    finally:
        report["ended_at_utc"] = _utc_now()
        original_error = sys.exc_info()[1]
        try:
            persist(final=True)
        except BaseException as exc:
            if original_error is None:
                raise
            message = f"Unable to persist final pilot diagnostics: {type(exc).__name__}: {exc}"
            if hasattr(original_error, "add_note"):
                original_error.add_note(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    report = run_pilot(arguments.output_dir)
    print(json.dumps({"output_directory": str(arguments.output_dir.resolve()),
                      "stop_reason": report["stop_reason"], "summary": report["summary"]}, sort_keys=True))
    return 0 if report["stop_reason"] == "completed_fixed_sample" and report["final_verification"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
