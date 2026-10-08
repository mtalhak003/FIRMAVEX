"""Administrator sidecar tests; fake files are never firmware measurements."""

import hashlib
import json
import subprocess
from dataclasses import fields
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.firmavex.evaluation.api import InputSpace, TrialFeedback, TrialInput
from src.firmavex.evaluation.evaluator import EvaluationSession, Observation
from src.firmavex.experiments.api import ExperimentRecord
from src.firmavex.protocols import protocol as protocol_module
from src.firmavex.protocols import provenance
from src.firmavex.protocols.controlled import controlled_cortex_m_v1
from src.firmavex.protocols.protocol import EvaluationProtocol, standard_baseline_protocol
from src.firmavex.protocols.results import CampaignResult
from src.firmavex.strategies.api import InvalidOutputReason, StrategyRun, TerminationReason
from src.firmavex.strategies.guided import guided_metadata


ID = "b-" + "1" * 32
START = "2026-10-08T07:00:00Z"
END = "2026-10-08T07:01:00+00:00"


def git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments], check=True,
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "--quiet")
    (root / "tracked.c").write_text("original\n")
    (root / ".gitignore").write_text("ignored.bin\n")
    git(root, "add", "tracked.c", ".gitignore")
    git(root, "-c", "user.name=Provenance Test", "-c", "user.email=provenance@example.test",
        "commit", "--quiet", "-m", "fixture")
    # Git state is real; tool probing is independently tested below.
    monkeypatch.setattr(provenance, "_tool_version", lambda name: {
        "status": "unavailable", "executable": None, "version": None, "error": name,
    })
    return root


@pytest.fixture
def manifest_inputs(repository):
    source = repository / "source.c"
    support = repository / "support.c"
    image = repository / "firmware.elf"
    source.write_bytes(b"unit-test source")
    support.write_bytes(b"unit-test support")
    image.write_bytes(b"unit-test artifact, not executable firmware")
    return {
        "repository": repository,
        "preset_name": "declared_test_preset",
        "firmware_images": {ID: image},
        "source_inputs": {ID: (source, support)},
        "build_metadata": {ID: {"argv": ["compiler", "source.c", "-o", "firmware.elf"]}},
        "started_at_utc": START,
    }


def declaration():
    return standard_baseline_protocol(benchmark_ids=(ID,), execution_budget=2, partition="development")


def test_environment_captures_real_clean_git_revision_and_does_not_change_tree(repository):
    before = git(repository, "status", "--short")
    nested = repository / "nested"
    nested.mkdir()
    captured = provenance.capture_environment(nested)
    assert captured["git"] == {
        "revision": git(repository, "rev-parse", "HEAD"), "status_short": "", "dirty": False,
        "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
        "index_diff_sha256": hashlib.sha256(b"").hexdigest(), "untracked_files": [],
    }
    assert captured["repository"] == str(repository)
    assert set(captured["tools"]) == {"arm-none-eabi-gcc", "qemu-system-arm", "arm-none-eabi-gdb"}
    assert captured["python"]["version"] and captured["python"]["executable"]
    assert captured["host"]["system"] and captured["captured_at_utc"].endswith("Z")
    assert git(repository, "status", "--short") == before


def test_environment_captures_staged_unstaged_untracked_and_omits_ignored_files(repository):
    (repository / "tracked.c").write_text("staged\n")
    git(repository, "add", "tracked.c")
    (repository / "tracked.c").write_text("unstaged\n")
    untracked = repository / "new source.c"
    untracked.write_bytes(b"new source bytes")
    (repository / "ignored.bin").write_bytes(b"ignored")
    captured = provenance.capture_environment(repository)
    difference = subprocess.run(
        ["git", "-C", str(repository), "diff", "--binary", "HEAD"],
        capture_output=True, check=True,
    ).stdout
    assert captured["git"]["dirty"]
    assert "MM tracked.c" in captured["git"]["status_short"]
    assert captured["git"]["tracked_diff_sha256"] == hashlib.sha256(difference).hexdigest()
    assert captured["git"]["untracked_files"] == [{
        "repository_path": "new source.c", **provenance.describe_artifact(untracked),
    }]
    assert "new source bytes" not in json.dumps(captured)


@pytest.mark.parametrize("available", [True, False])
def test_environment_records_selected_os_release_when_available(repository, monkeypatch, available):
    release = {"NAME": "Test Linux", "ID": "test", "VERSION_ID": "1", "PRETTY_NAME": "Test Linux 1", "HOME_URL": "excluded"}
    probe = Mock(return_value=release, side_effect=None if available else OSError("unavailable"))
    monkeypatch.setattr(provenance.platform, "freedesktop_os_release", probe)
    captured = provenance.capture_environment(repository)
    assert captured["host"]["platform"]
    assert captured["host"]["os_release"] == ({key: release[key] for key in ("NAME", "ID", "VERSION_ID", "PRETTY_NAME")} if available else None)


def test_environment_rejects_missing_git_repository(tmp_path):
    with pytest.raises(ValueError, match="Git provenance"):
        provenance.capture_environment(tmp_path)


def test_artifact_hash_changes_when_bytes_change_without_exposing_contents(tmp_path):
    path = tmp_path / "image.elf"
    path.write_bytes(b"first image")
    before = provenance.describe_artifact(path)
    assert before["path"] == before["requested_path"] == str(path)
    assert before["size_bytes"] == 11
    assert before["sha256"] == hashlib.sha256(b"first image").hexdigest()
    assert before["consistency"] == {"status": "stable_observed", "atomic": False}
    path.write_bytes(b"second image")
    after = provenance.describe_artifact(path)
    assert after["sha256"] != before["sha256"]
    assert after["size_bytes"] == 12
    assert "second image" not in json.dumps(after)


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_artifact_requires_file(tmp_path, kind):
    path = tmp_path / "artifact"
    if kind == "directory":
        path.mkdir()
    with pytest.raises(ValueError, match="readable file"):
        provenance.describe_artifact(path)


def test_missing_tool_has_structured_unavailable_state_without_fallback(monkeypatch):
    monkeypatch.setattr(provenance.shutil, "which", lambda name: None)
    forbidden = Mock(side_effect=AssertionError("No alternate executable may be used."))
    monkeypatch.setattr(provenance.subprocess, "run", forbidden)
    captured = provenance._tool_version("arm-none-eabi-gdb")
    assert captured["status"] == "unavailable" and captured["version"] is None
    assert "arm-none-eabi-gdb" in captured["error"]
    forbidden.assert_not_called()


@pytest.mark.parametrize("outcome", ["ok", "nonzero", "empty", "timeout", "oserror"])
def test_tool_version_probe_is_bounded_and_failures_are_explicit(monkeypatch, outcome):
    monkeypatch.setattr(provenance.shutil, "which", lambda name: "/tools/arm-none-eabi-gcc")
    result = subprocess.CompletedProcess([], 2 if outcome == "nonzero" else 0,
                                         "" if outcome == "empty" else "compiler 1.2\n", "bad" if outcome == "nonzero" else "")
    failure = {
        "timeout": subprocess.TimeoutExpired(["compiler", "--version"], 5),
        "oserror": OSError("cannot execute"),
    }.get(outcome)
    run = Mock(side_effect=failure, return_value=result)
    monkeypatch.setattr(provenance.subprocess, "run", run)
    captured = provenance._tool_version("arm-none-eabi-gcc")
    run.assert_called_once_with(["/tools/arm-none-eabi-gcc", "--version"],
                                capture_output=True, text=True, timeout=5)
    assert captured["executable"] == "/tools/arm-none-eabi-gcc"
    if outcome == "ok":
        assert captured["status"] == "ok" and captured["version"] == "compiler 1.2"
        assert captured["error"] is None
    else:
        assert captured["status"] == "error" and captured["version"] is None
        assert captured["error"]


def test_manifest_records_exact_plan_artifacts_and_explicit_unverified_build_metadata(manifest_inputs):
    protocol = declaration()
    captured = provenance.capture_campaign_manifest(protocol, **manifest_inputs)
    assert captured["schema_version"] == 1
    assert captured["kind"] == "administrator_campaign_provenance_v1"
    assert captured["preset"] == {"name": "declared_test_preset", "verification": "administrator_declared_not_verified"}
    assert captured["plan"] == protocol.plan_to_dict()
    assert captured["started_at_utc"] == START and captured["ended_at_utc"] is None
    assert captured["official_campaign_result"] is None
    benchmark, = captured["benchmarks"]
    assert benchmark["benchmark_id"] == ID
    assert benchmark["firmware_image"] == provenance.describe_artifact(manifest_inputs["firmware_images"][ID])
    assert benchmark["source_inputs"] == [provenance.describe_artifact(path) for path in manifest_inputs["source_inputs"][ID]]
    assert benchmark["build"] == {"verification": "administrator_supplied_not_verified",
                                  "metadata": manifest_inputs["build_metadata"][ID]}
    captured["benchmarks"][0]["build"]["metadata"]["argv"].clear()
    assert manifest_inputs["build_metadata"][ID]["argv"]


def test_manifest_preserves_retained_controlled_plan_after_later_guided_default_drift(manifest_inputs, monkeypatch):
    protocol = controlled_cortex_m_v1(partition="held_out")
    before = protocol.plan_to_dict()
    for name in ("firmware_images", "source_inputs", "build_metadata"):
        value = manifest_inputs[name][ID]
        manifest_inputs[name] = {identifier: value for identifier in protocol.benchmark_ids}
    monkeypatch.setattr(protocol_module, "guided_metadata", lambda seed: guided_metadata(seed, archive_size=3, mutation_attempts=1))
    captured = provenance.capture_campaign_manifest(protocol, **manifest_inputs)
    assert captured["plan"] == before == protocol.plan_to_dict()
    assert len(captured["plan"]["experiments"]) == 42
    guided = [run for run in captured["plan"]["experiments"] if run["strategy"]["name"] == "guided"]
    assert all(run["strategy"]["configuration"] == {"archive_size": 32, "mutation_attempts": 8} for run in guided)


def test_official_standard_baseline_serialization_remains_unchanged(manifest_inputs):
    protocol = declaration()
    expected = {
        "schema_version": 1, "kind": "standard_baseline_v1", "benchmark_ids": [ID],
        "execution_budget": 2, "partition": "development", "strategies": ["enumerative", "random"],
        "random_seeds": list(range(10)), "run_order": "benchmark_then_enumerative_then_random_seed",
        "infrastructure_abort_policy": "continue_independent_experiments",
    }
    before = protocol.to_json()
    provenance.capture_campaign_manifest(protocol, **manifest_inputs)
    assert protocol.to_dict() == expected
    assert protocol.to_json() == before == json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert [field.name for field in fields(TrialFeedback)] == ["status", "execution_index", "budget_remaining", "execution_signature"]


@pytest.mark.parametrize("field", ["firmware_images", "source_inputs", "build_metadata"])
@pytest.mark.parametrize("kind", ["missing", "extra"])
def test_manifest_requires_exact_benchmark_mapping_coverage(manifest_inputs, field, kind):
    manifest_inputs[field] = {} if kind == "missing" else {**manifest_inputs[field], "b-" + "2" * 32: next(iter(manifest_inputs[field].values()))}
    with pytest.raises(ValueError, match="cover exactly"):
        provenance.capture_campaign_manifest(declaration(), **manifest_inputs)


@pytest.mark.parametrize("value", [None, True, "", "2026-10-08T07:00:00", "2026-10-08T07:00:00+05:00", "bad"])
def test_manifest_rejects_invalid_start_timestamp(manifest_inputs, value):
    manifest_inputs["started_at_utc"] = value
    with pytest.raises(ValueError, match="UTC timestamp"):
        provenance.capture_campaign_manifest(declaration(), **manifest_inputs)


def test_manifest_rejects_end_before_start(manifest_inputs):
    with pytest.raises(ValueError, match="precede"):
        provenance.capture_campaign_manifest(declaration(), ended_at_utc="2026-10-08T06:59:59Z", **manifest_inputs)


@pytest.mark.parametrize("value", [None, [], (), "source.c"])
def test_manifest_requires_source_input_sequence(manifest_inputs, value):
    manifest_inputs["source_inputs"][ID] = value
    with pytest.raises(ValueError, match="source/support"):
        provenance.capture_campaign_manifest(declaration(), **manifest_inputs)


@pytest.mark.parametrize("value", [{}, {"value": float("nan")}, {"value": float("inf")}, {"value": object()}, {1: "key"}])
def test_manifest_rejects_missing_or_non_json_build_metadata(manifest_inputs, value):
    manifest_inputs["build_metadata"][ID] = value
    with pytest.raises(ValueError):
        provenance.capture_campaign_manifest(declaration(), **manifest_inputs)


def complete_result(protocol):
    records = []
    for index, spec in enumerate(protocol.expand()):
        owner = EvaluationSession(ID, InputSpace(1, 0, 4), spec.execution_budget,
                                  spec.strategy.name, lambda values: Observation(index != 2, index == 0),
                                  random_seed=spec.strategy.seed)
        if index == 3:
            termination = TerminationReason.INVALID_OUTPUT
            invalid = InvalidOutputReason.WIDTH
        else:
            invalid = None
            for value in range(spec.execution_budget):
                feedback = owner.execute(TrialInput((value,)))
                if feedback.status in {"triggered", "infrastructure_failure"}:
                    break
            termination = (TerminationReason.FAILURE_DISCOVERED if index == 0
                           else TerminationReason.SESSION_ABORTED if index == 2
                           else TerminationReason.BUDGET_EXHAUSTED)
        records.append(ExperimentRecord(spec, owner.describe(),
                                      StrategyRun(owner.result(), spec.strategy, termination, invalid)))
    return CampaignResult(protocol, tuple(records))


def test_manifest_preserves_authoritative_outcomes_classifications_and_censoring(manifest_inputs):
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(0, 1, 2))
    result = complete_result(protocol)
    before = result.to_dict()
    captured = provenance.capture_campaign_manifest(protocol, ended_at_utc=END, campaign_result=result, **manifest_inputs)
    assert captured["official_campaign_result"] == before == result.to_dict()
    assert captured["official_campaign_result"]["counts"] == {
        "planned_runs": 4, "completed_records": 4, "valid_search_runs": 2,
        "infrastructure_aborted_runs": 1, "invalid_strategy_runs": 1,
    }
    assert [record["run"]["evaluation"]["attempted_executions"] for record in captured["official_campaign_result"]["records"]] == [1, 2, 1, 0]
    assert captured["official_campaign_result"]["summaries"][1]["discovery_executions"] == [None, None, None]
    assert captured["ended_at_utc"] == "2026-10-08T07:01:00Z"


def test_manifest_rejects_completed_outcome_without_end_timestamp(manifest_inputs):
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(0,))
    with pytest.raises(ValueError, match="end timestamp"):
        provenance.capture_campaign_manifest(protocol, campaign_result=complete_result(protocol), **manifest_inputs)


def test_manifest_rejects_completed_result_plan_mismatch(manifest_inputs):
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(0,))
    changed = EvaluationProtocol((ID,), 2, "development", random_seeds=(1,))
    with pytest.raises(ValueError, match="plan differs"):
        provenance.capture_campaign_manifest(protocol, ended_at_utc=END, campaign_result=complete_result(changed), **manifest_inputs)


def test_manifest_rejects_reordered_completed_records(manifest_inputs):
    protocol = EvaluationProtocol((ID,), 2, "development", random_seeds=(0,))
    result = complete_result(protocol)
    object.__setattr__(result, "records", tuple(reversed(result.records)))
    with pytest.raises(ValueError, match="differs"):
        provenance.capture_campaign_manifest(protocol, ended_at_utc=END, campaign_result=result, **manifest_inputs)


def test_manifest_generation_never_dispatches_firmware_or_mutates_protocol(manifest_inputs, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("No firmware dispatch from provenance."))
    monkeypatch.setattr(EvaluationSession, "execute", forbidden)
    protocol = declaration()
    before = protocol.plan_to_json()
    captured = provenance.capture_campaign_manifest(protocol, **manifest_inputs)
    encoded = provenance.manifest_to_json(captured)
    assert json.loads(encoded) == captured
    assert encoded == provenance.manifest_to_json(captured)
    assert protocol.plan_to_json() == before
    forbidden.assert_not_called()


def test_sidecar_json_rejects_nonfinite_values():
    with pytest.raises(ValueError):
        provenance.manifest_to_json({"invalid": float("nan")})


@pytest.mark.parametrize("mutation", ["rewrite", "replace", "retarget"])
@pytest.mark.parametrize("stage", ["update", "hexdigest"])
def test_artifact_rejects_changes_during_read_and_digest_processing(tmp_path, monkeypatch, mutation, stage):
    target = tmp_path / "image.elf"
    target.write_bytes(b"original!" * (128 * 1024))
    requested = target
    if mutation == "retarget":
        requested = tmp_path / "image-link.elf"
        requested.symlink_to(target)
    actual_sha256 = provenance.hashlib.sha256
    changed = False

    def change():
        nonlocal changed
        if changed:
            return
        changed = True
        if mutation == "rewrite":
            target.write_bytes(b"modified!" * (128 * 1024))
        else:
            replacement = tmp_path / "replacement.elf"
            replacement.write_bytes(target.read_bytes())
            if mutation == "replace":
                replacement.replace(target)
            else:
                requested.unlink()
                requested.symlink_to(replacement)

    class Digest:
        def __init__(self):
            self.real = actual_sha256()

        def update(self, value):
            self.real.update(value)
            if stage == "update":
                change()

        def hexdigest(self):
            result = self.real.hexdigest()
            if stage == "hexdigest":
                change()
            return result

    monkeypatch.setattr(provenance.hashlib, "sha256", Digest)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="changed"):
        provenance.describe_artifact(requested)
    assert changed


def test_artifact_rejects_path_replacement_between_identity_check_and_open(tmp_path, monkeypatch):
    path = tmp_path / "image.elf"
    path.write_bytes(b"unchanged bytes")
    actual_identity = provenance._artifact_identity
    calls = 0

    def replacing_identity(requested):
        nonlocal calls
        captured = actual_identity(requested)
        calls += 1
        if calls == 1:
            replacement = tmp_path / "replacement.elf"
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
        return captured

    monkeypatch.setattr(provenance, "_artifact_identity", replacing_identity)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="before hashing"):
        provenance.describe_artifact(path)


def test_stable_artifact_records_requested_and_resolved_identity_without_atime(tmp_path):
    target = tmp_path / "image.elf"
    target.write_bytes(b"stable artifact")
    link = tmp_path / "image-link.elf"
    link.symlink_to(target)
    captured = provenance.describe_artifact(link)
    assert captured["path"] == str(target)
    assert captured["requested_path"] == str(link)
    assert captured["sha256"] == hashlib.sha256(b"stable artifact").hexdigest()
    assert captured["consistency"] == {"status": "stable_observed", "atomic": False}
    assert captured["identity"]["requested_stat"]["ino"] == link.lstat().st_ino
    assert captured["identity"]["resolved_stat"]["ino"] == target.stat().st_ino
    assert set(captured["identity"]["resolved_stat"]) == {"dev", "ino", "mode", "size", "mtime_ns", "ctime_ns"}


@pytest.mark.parametrize("mutation", ["head", "tracked_same_status", "index_same_status", "untracked_added", "untracked_same_path"])
def test_environment_rejects_git_and_content_changes_across_tool_probes(repository, monkeypatch, mutation):
    tracked = repository / "tracked.c"
    untracked = repository / "untracked.c"
    if mutation == "tracked_same_status":
        tracked.write_text("before probe\n")
    elif mutation == "index_same_status":
        tracked.write_text("first staged\n")
        git(repository, "add", "tracked.c")
        tracked.write_text("original\n")
    elif mutation == "untracked_same_path":
        untracked.write_text("before\n")
    changed = False

    def probe(name):
        nonlocal changed
        if not changed:
            changed = True
            if mutation == "head":
                git(repository, "-c", "user.name=Provenance Test", "-c", "user.email=provenance@example.test",
                    "commit", "--quiet", "--allow-empty", "-m", "new head")
            elif mutation == "tracked_same_status":
                tracked.write_text("after probe\n")
            elif mutation == "index_same_status":
                tracked.write_text("second staged\n")
                git(repository, "add", "tracked.c")
                tracked.write_text("original\n")
            else:
                untracked.write_text("after!\n")
        return {"status": "unavailable", "executable": None, "version": None, "error": name}

    monkeypatch.setattr(provenance, "_tool_version", probe)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="changed"):
        provenance.capture_environment(repository)
    assert changed


def test_environment_detects_clean_status_with_nonempty_diff(repository, monkeypatch):
    (repository / "tracked.c").write_text("modified\n")
    actual_git = provenance._git

    def inconsistent_git(root, *arguments):
        if arguments == ("status", "--short", "--untracked-files=all"):
            return b""
        return actual_git(root, *arguments)

    monkeypatch.setattr(provenance, "_git", inconsistent_git)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="clean status"):
        provenance.capture_environment(repository)


def test_environment_records_staged_difference_even_when_working_tree_matches_head(repository):
    tracked = repository / "tracked.c"
    tracked.write_text("staged change\n")
    git(repository, "add", "tracked.c")
    tracked.write_text("original\n")
    captured = provenance.capture_environment(repository)
    assert captured["git"]["dirty"]
    assert "MM tracked.c" in captured["git"]["status_short"]
    assert captured["git"]["tracked_diff_sha256"] == hashlib.sha256(b"").hexdigest()
    assert captured["git"]["index_diff_sha256"] != hashlib.sha256(b"").hexdigest()
    assert captured["consistency"] == {"status": "stable_observed", "atomic": False}


def test_environment_rejects_change_between_git_status_and_diff_read(repository, monkeypatch):
    actual_git = provenance._git
    changed = False

    def changing_git(root, *arguments):
        nonlocal changed
        result = actual_git(root, *arguments)
        if arguments == ("status", "--short", "--untracked-files=all") and not changed:
            changed = True
            (repository / "tracked.c").write_text("changed after status\n")
        return result

    monkeypatch.setattr(provenance, "_git", changing_git)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="clean status"):
        provenance.capture_environment(repository)


@pytest.mark.parametrize("stage", ["later_artifact", "tool_probe"])
def test_manifest_rejects_artifact_changed_after_its_capture_outside_git(manifest_inputs, tmp_path, monkeypatch, stage):
    image = tmp_path / "outside-repository.elf"
    image.write_bytes(b"first artifact")
    manifest_inputs["firmware_images"][ID] = image
    changed = False
    observed_image = False
    actual_artifact = provenance.describe_artifact

    def change():
        nonlocal changed
        if not changed:
            changed = True
            image.write_bytes(b"later artifact")

    def artifact(path):
        nonlocal observed_image
        captured = actual_artifact(path)
        if Path(path) == image:
            observed_image = True
        elif observed_image and Path(path).name == "support.c" and stage == "later_artifact":
            change()
        return captured

    def probe(name):
        if stage == "tool_probe":
            change()
        return {"status": "unavailable", "executable": None, "version": None, "error": name}

    monkeypatch.setattr(provenance, "describe_artifact", artifact)
    monkeypatch.setattr(provenance, "_tool_version", probe)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="Artifact changed"):
        provenance.capture_campaign_manifest(declaration(), **manifest_inputs)
    assert changed


def test_manifest_rejects_git_change_before_environment_capture(manifest_inputs, tmp_path, monkeypatch):
    image = tmp_path / "outside-repository.elf"
    image.write_bytes(b"stable artifact")
    manifest_inputs["firmware_images"][ID] = image
    actual_artifact = provenance.describe_artifact
    changed = False

    def artifact(path):
        nonlocal changed
        captured = actual_artifact(path)
        if Path(path) == image and not changed:
            changed = True
            (manifest_inputs["repository"] / "tracked.c").write_text("modified before environment\n")
        return captured

    monkeypatch.setattr(provenance, "describe_artifact", artifact)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="Git state changed across manifest"):
        provenance.capture_campaign_manifest(declaration(), **manifest_inputs)


def test_manifest_rejects_plan_change_during_capture(manifest_inputs, monkeypatch):
    protocol = declaration()
    changed = False

    def probe(name):
        nonlocal changed
        if not changed:
            changed = True
            object.__setattr__(protocol, "execution_budget", 3)
        return {"status": "unavailable", "executable": None, "version": None, "error": name}

    monkeypatch.setattr(provenance, "_tool_version", probe)
    with pytest.raises(provenance.ProvenanceConsistencyError, match="Protocol plan changed"):
        provenance.capture_campaign_manifest(protocol, **manifest_inputs)
