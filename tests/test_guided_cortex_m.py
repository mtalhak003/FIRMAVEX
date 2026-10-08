"""Two real executions validate plumbing, without a search comparison."""

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from src.firmavex.compiler.cortex_m import SUPPORT_DIR
from src.firmavex.evaluation import registry as registry_module
from src.firmavex.evaluation.api import ExecutionSignature, TrialFeedback, TrialInput
from src.firmavex.experiments import runner as experiment_runner
from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.strategies.api import TerminationReason
from src.firmavex.strategies.guided import guided_metadata


def test_real_signature_guides_a_later_proposal_through_the_common_experiment_path(monkeypatch, tmp_path):
    identifier = "b-00000000000000000000000000000017"
    fixture = Path(__file__).parent / "fixtures/cortex_m/runtime_signature.c"
    shutil.copyfile(fixture, tmp_path / fixture.name)
    shutil.copyfile(SUPPORT_DIR / "corpus_v2/harness.c", tmp_path / "harness.c")
    manifest = {
        "version": 2, "target": "mps2-an385",
        "interface": {
            "width": 4, "input_domain": [0, 15], "input_symbol": "firmavex_actions",
            "failure_symbol": "firmavex_failure", "breakpoint": "benchmark_complete",
        },
        "benchmarks": [{
            "id": identifier, "name": "instrumentation_probe", "source": fixture.name,
            "split": "development",
        }],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(registry_module, "CORPUS_DIR", tmp_path)
    registry = registry_module.BenchmarkRegistry()
    built = registry.build(identifier, tmp_path / "probe.elf")
    assert built["success"], built["stderr"]

    # Fixed seed for mechanics. No seed/benchmark sweep or outcome selection.
    declaration = ExperimentSpec(identifier, guided_metadata(42), 2)
    factory = experiment_runner.create_strategy
    events = []

    def tracked_factory(metadata):
        strategy = factory(metadata)
        propose, observe = strategy.propose, strategy.observe

        def tracked_propose():
            candidate = propose()
            events.append(("propose", candidate))
            return candidate

        def tracked_observe(candidate, feedback):
            assert type(candidate) is TrialInput and type(feedback) is TrialFeedback
            assert type(feedback.execution_signature) is ExecutionSignature
            events.append(("observe", candidate, feedback))
            observe(candidate, feedback)

        strategy.propose, strategy.observe = tracked_propose, tracked_observe
        return strategy

    monkeypatch.setattr(experiment_runner, "create_strategy", tracked_factory)
    runner = experiment_runner.ExperimentRunner(registry)
    record = runner.run(declaration)
    assert record.run.termination is TerminationReason.BUDGET_EXHAUSTED, runner.last_session.diagnostics()
    assert [event[0] for event in events] == ["propose", "observe", "propose", "observe"]
    first, second = events[0][1], events[2][1]
    # The first genuine runtime signature admits a mutation parent; the later
    # proposal differs in exactly one coordinate of that parent.
    assert sum(left != right for left, right in zip(first.values, second.values)) == 1
    assert record.description.input_space.accepts(first.values)
    assert record.description.input_space.accepts(second.values)
    for event in (events[1], events[3]):
        feedback = event[2]
        assert feedback.status == "safe" and not feedback.execution_signature.truncated
    result = record.run.evaluation
    assert result == runner.last_session.result()
    assert result.attempted_executions == result.successful_executions == 2
    assert result.infrastructure_failures == 0 and not result.aborted and not result.failure_found
    assert record.run.strategy == declaration.strategy

    public = json.dumps([asdict(record.description), asdict(events[1][2]), asdict(events[3][2])])
    for private in (str(tmp_path), fixture.name, "runtime_sink", "firmavex_failure", "benchmark_complete",
                    "stdout", "stderr", "development", "0x"):
        assert private not in public
