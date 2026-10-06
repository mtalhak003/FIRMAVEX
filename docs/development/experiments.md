# Step 16D: one declared experiment and standardized record

The experiment layer sits above the unchanged Step 15B evaluator and Step 16A
strategy runner. It supports one enumerative or seeded random experiment at a
time. It adds no benchmark campaign, search method, aggregate research results,
statistical comparison, performance claims, or automatic result storage.

## Declaration and baseline selection

`experiments/api.py` defines the frozen `ExperimentSpec` with:

- `benchmark_id`: the existing opaque `b-` identifier.
- `strategy`: existing immutable `StrategyMetadata`.
- `execution_budget`: an explicit nonnegative integer; booleans are rejected.

This declaration describes intent. It is distinct from
`evaluation.api.ExperimentSpec`, the existing public benchmark description. The
experiment declaration does not accept paths, corpus names, split labels, live
objects, or arbitrary import strings as strategy selection.

`create_strategy` explicitly constructs only the two frozen production baselines.
`StrategyMetadata("enumerative")` requires `seed=None`.
`StrategyMetadata("random", seed=42)` requires an explicit integer seed, preserved
exactly. Neither unsupported configuration nor an enumerative seed is silently
ignored; both baselines currently require empty configuration. No random seed
is invented. Invalid declarations fail before session creation or dispatch.
Declaration validation is not a second budget-enforcement mechanism.

## Single-run execution

Administrator code builds/registers an image using the existing registry, then
calls the experiment runner. For an already built opaque ID:

```python
from src.firmavex.experiments.api import ExperimentSpec
from src.firmavex.experiments.runner import ExperimentRunner
from src.firmavex.strategies.api import StrategyMetadata

spec = ExperimentSpec(opaque_id, StrategyMetadata("random", seed=42), 100)
record = ExperimentRunner(registry).run(spec)
machine_readable = record.to_json()
```

The example seed is illustrative, not a frozen experiment schedule.
`SessionProvider` is the small administrator-side dependency satisfied by
`BenchmarkRegistry.open_session`. Unit tests can supply providers creating real
evaluation sessions around fake executors. Registry errors, such as an unknown
or unbuilt benchmark, propagate to the administrator without a fabricated run.

The runner constructs the baseline from public metadata, passes its exact name,
seed, and declared budget to `open_session`, obtains `strategy_api()`, and checks
public identity/budget/seed alignment and that the session is fresh and unused.
Zero-budget fresh sessions are valid. Session descriptions must be the existing
immutable public record and `InputSpace`, without extended/live object types.

It calls the existing `run_strategy` exactly once and wraps its actual returned
`StrategyRun`. It copies no strategy loop, directly executes no firmware, adds
no counters, and measures no new timing. The evaluator alone admits/charges
executions and owns attempts, successes, infrastructure failures, first-trigger
index/time, remaining budget, exhaustion, and abort state. Mismatched result
tags are rejected rather than silently relabeled.

## Record and machine-readable boundary

The frozen `ExperimentRecord` stores three existing immutable authorities:

- `declaration`: intended ID, baseline metadata, and budget.
- `description`: actual public ID, input space, and budget.
- `run`: the actual strategy metadata, evaluator result, termination reason,
  and optional invalid-output reason returned by the common runner.

The description preserves the actual domain used, including bounded integration
test domains. Intent and actual fields are checked for alignment; no evaluation
counter is independently reconstructed. The record contains no registry/session
instance or administrator diagnostics. Its nested records are immutable.

`to_dict()` returns fresh JSON-compatible data with `schema_version=1` and the
three fields above. Metadata configuration is an object, seed is an integer or
null, and termination/invalid-output enums are stable strings or null. The
evaluation object's existing public field names are preserved in full.

`to_json()` sorts keys, uses compact separators, rejects nonfinite numbers,
preserves integer seed literals without float conversion, and never falls back
to object reprs. Python JSON parsing round-trips arbitrary-size integer seeds;
consumers must preserve integer precision. Equivalent records produce identical
JSON. Measured timings can differ between otherwise equivalent executed runs.
There is no parser, database, automatic file write, or persistent result folder.

## Outcomes and metrics

Termination reasons remain exactly those defined by Step 16A:
`failure_discovered`, `budget_exhausted`, `strategy_stopped`, `session_aborted`,
and `invalid_strategy_output`. Domain exhaustion uses `strategy_stopped`.
The record does not collapse these into a general failure flag.

Infrastructure failure preserves charged attempts, infrastructure-failure count,
`aborted=True`, and `session_aborted`. This is not a clean budget-limited
non-discovery. The common runner prevents further dispatch after an abort.
Raw stdout/stderr stay administrator-owned. `KeyboardInterrupt` and `SystemExit`
propagate unchanged after evaluator accounting/abort updates, with no completed
record fabricated. The administrator can inspect the evaluator after an
exception through `runner.last_session`. This
administrator-only handle retains the latest created evaluator, not a history
of results, and is cleared before a new valid run attempts session creation.
It is never passed to a strategy or included in any record/serialization.

The primary search-efficiency metric is the evaluator's
`first_failure_execution`: executions to first discovered firmware failure.
For unsuccessful runs, report discovery status, attempts, budget usage, and
termination/abort distinctions. Absence of discovery is not a universal proof
that firmware cannot fail. The existing `time_to_first_failure_seconds` is a
secondary operational metric affected by QEMU/GDB startup, host load, scheduling,
and toolchain behavior. It is not the primary comparison metric. No averages,
confidence intervals, rankings, or statistical tests are calculated here.

## Information boundary and reproducibility limits

Strategies receive only the existing immutable public description, candidates,
and coarse feedback through the unchanged runner. Provider, registry, image,
source, manifest, split, oracle, diagnostics, and experiment-controller objects
never enter a strategy constructor, `start`, or `observe`. No partition field is
added to declarations or records; selecting development/held-out entries remains
an administrative registry operation. Step 16E will define campaign scheduling.

No deterministic experiment ID is added: there is no current storage/deduplication
consumer requiring one. The declaration itself captures stable logical inputs.
Comprehensive environment fingerprinting is also deferred: the repository has
no standardized provenance record, and this step adds no Git/toolchain/QEMU shell
probing. Future protocols must bind records to corpus/build, FIRMAVEX, Python,
and toolchain versions. Declared seed/configuration/budget plus actual public
domain are recorded now, without claiming cross-runtime replay guarantees.

Tests cover declaration validation, both baseline selections/orders, exact seed
propagation, budget/domain/discovery/abort/invalid-output records, interception
of mismatched or reused sessions, immutable serialization, and interruption
propagation. One bounded real path uses the unchanged v1 threshold fixture and
enumerative strategy over its original 0..255 domain: input 6 triggers after
seven QEMU/GDB executions under budget 8. This is integration coverage, not a
benchmark campaign or comparison result.

The existing cooperative in-process boundary is not adversarial sandboxing.
Process isolation, final seed schedules, repeated trials, aggregation,
development/held-out campaigns, comprehensive provenance, guided/AI search,
research comparisons, and performance claims remain deferred. No seed sweep,
outcome-based tuning, or automatic benchmark matrix is introduced.
