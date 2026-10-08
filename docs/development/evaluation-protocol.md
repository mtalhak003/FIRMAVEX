# Step 16E: frozen baseline evaluation protocol

The separate Step 18A three-strategy preset is documented in
[controlled Cortex-M evaluation protocol v1](../experiments/controlled-evaluation-v1.md).
The historical standard baseline described below remains unchanged.

The protocol layer declares and executes a reproducible campaign above the
unchanged Step 16D single-experiment framework. It freezes comparison rules
before guided search is implemented. It defines methodology and produces data;
it publishes no baseline performance results or claims of superiority.

## Declaration and standard baseline protocol

`protocols/protocol.py` defines the frozen `EvaluationProtocol`:

- `benchmark_ids`: a nonempty ordered tuple of unique existing opaque IDs.
- `execution_budget`: one explicit positive integer for every experiment.
- `partition`: the administrative `development` or `held_out` scope.
- `random_seeds`: an ordered immutable tuple of unique integer seeds.
- `strategies`: an immutable selection of the supported conventional baselines.

Tuple fields are required rather than silently converting mutable collections.
Booleans are not integers for budget/seed validation. Unsupported strategies,
duplicate IDs or seeds, malformed IDs, and contradictory declarations raise
`ValueError`. Baseline ordering is canonical: enumerative before random. A
protocol including random requires seeds; a protocol without random requires an
empty seed tuple.

`standard_baseline_protocol` explicitly accepts benchmark IDs, budget, and
partition. It freezes both baselines and this exact seed schedule:

```python
(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
```

The schedule is declared in Step 16E before guided search. It is independent of
benchmark, partition, outcomes, and future guided-method performance. Seeds must
not be replaced, removed, optimized, or selected after viewing results.

The standard protocol runs one deterministic enumerative experiment and ten
random experiments per benchmark. Enumerative is not repeated artificially to
match the random repetitions. `is_standard` identifies declarations matching
the standard baseline/seed rules. Explicit custom protocols may use fewer seeds
or a supported baseline subset for bounded tests; they are not the standard
research protocol. The production standard schedule remains ten seeds.

The standard campaign requires a positive budget. This is stricter than Step
16D, whose lower-level API also permits zero-budget experiments. The evaluator
remains the only authority enforcing admission and charging firmware executions.

```python
from src.firmavex.protocols.protocol import standard_baseline_protocol

protocol = standard_baseline_protocol(
    benchmark_ids=(opaque_id,), execution_budget=100, partition="development",
)
planned_experiments = protocol.expand()
planned_json = protocol.plan_to_json()
```

This example declares and serializes a plan; it does not execute firmware.

## Ordering, selection, and fair comparison

`expand()` returns an immutable tuple of existing Step 16D `ExperimentSpec`
objects. It validates the entire declaration before execution. For each opaque
ID in the exact declared order, the standard expansion is:

```text
benchmark: enumerative, seed None
benchmark: random, seed 0
benchmark: random, seed 1
...
benchmark: random, seed 9
then the next declared benchmark
```

All experiments use the same declared budget. Expansion uses no filesystem
discovery, set ordering, outcome-dependent ordering, or randomized run schedule.
There is no separate plan class or new execution counter.

`CampaignRunner` checks every selected ID against the administrator's existing
`registry.select(partition)` before the first experiment. Unknown IDs and IDs
outside the declared partition fail before dispatch. Registry selection checks
membership; it never replaces the declared benchmark order. Selected private
benchmark records, source names, paths, and split information remain outside
the strategy interface.

`CampaignRegistry` describes the administrative selection/session dependency;
the existing built `BenchmarkRegistry` satisfies it. The registry's public
`InputSpace` is validated and captured before the first experiment as the common
domain for the campaign. Each returned record must match its planned declaration
and that domain. Records
with mismatched identity, seed, budget, order, or input space are rejected rather
than relabeled or accepted as a comparable campaign.

For a given benchmark, both baselines use the same budget, firmware image,
failure criterion, evaluator semantics, public input space, and opaque API.
Their intended difference is search ordering: lexicographic enumeration versus
seeded uniform sampling without replacement. The protocol changes neither
baseline nor its accounting behavior.

## Campaign execution and interruptions

`protocols/runner.py` implements this path:

```text
EvaluationProtocol -> ExperimentSpec tuple -> CampaignRunner
    -> existing ExperimentRunner -> existing StrategyRunner
    -> opaque evaluation adapter -> evaluator / firmware
    -> exact ExperimentRecords -> CampaignResult
```

`CampaignRunner(registry).run(protocol)` invokes the existing `ExperimentRunner`
once per planned experiment and retains each exact returned record in order.
It adds no firmware dispatch path, strategy loop, evaluator counters, or timing
measurements. Each experiment receives a fresh independent evaluation session.

Images must already be successfully built and registered administratively.
The existing registry has no public image-readiness query, so selection
validation is not a guarantee that every image is ready. Session-creation
exceptions propagate without a fabricated completed campaign. Image-access
failures during evaluator execution produce ordinary infrastructure-aborted
records under the existing registry/evaluator behavior. The campaign does not
inspect private registry image dictionaries or duplicate build/session machinery.

An ordinary recorded infrastructure abort is retained, classified separately,
and excluded from valid search metrics. The campaign continues with later
independent experiments, using fresh sessions. Invalid strategy output is also
retained and reported separately; it is neither a valid non-discovery nor an
infrastructure failure.

`KeyboardInterrupt` and `SystemExit` propagate immediately and unchanged. No
completed `CampaignResult` is manufactured for an interrupted campaign. Any
admitted interrupted execution remains charged and aborted by the existing
evaluator. Administrators can inspect the latest owner through
`runner.experiment_runner.last_session`; raw diagnostics never enter strategies
or campaign serialization. There is no checkpoint, resume, partial-result
persistence, or automatic result file.

## Immutable results and per-benchmark summaries

`protocols/results.py` defines frozen `CampaignResult` and `StrategySummary`
records. A completed campaign contains its protocol, the complete ordered tuple
of exact `ExperimentRecord` objects, and summaries scoped by benchmark and
strategy. Results validate correspondence with the entire declared plan.
Campaign counts are exposed through `planned_run_count`,
`completed_record_count`, `valid_search_run_count`,
`infrastructure_aborted_run_count`, and `invalid_strategy_run_count`.

Each strategy summary preserves its benchmark, strategy, declared budget, run
counts, discovered and non-discovered valid counts, infrastructure aborts,
invalid strategy runs, discovery rate, eligible per-run discovery indices, and
conditional min/median/max executions to first discovery. Per-run records
preserve seeds, attempted executions, actual termination, and secondary timing.
No global cost summary merges heterogeneous benchmarks or disguises the
one-versus-ten repetition design.

For each benchmark/strategy scope:

```text
valid_runs = completed runs excluding infrastructure aborts and invalid output
discovered_runs = valid runs whose evaluator reports failure_found
discovery_rate = discovered_runs / valid_runs, or None when valid_runs == 0
```

The raw counts accompany the rate. All declared random seeds remain represented,
including non-discoveries and infrastructure-aborted seeds. There is no best-seed
selection. An undefined rate serializes as `null`, not an invented zero percent.

Execution cost uses only the evaluator's authoritative
`first_failure_execution`. The eligible per-run discovery index is:

- discovered valid run: its integer first-trigger execution index;
- valid non-discovery: `None`;
- infrastructure-aborted or invalid strategy run: `None`.

The underlying `ExperimentRecord` is never rewritten. If an infrastructure abort
follows an earlier discovery, its raw record still preserves that original
discovery information, while the aborted run contributes no eligible discovery
index, discovery-rate numerator, or successful-cost sample.

`first_failure_executions` contains only discovered valid execution indices.
Minimum, median, and maximum are calculated only over that sample; all three
are `None` when it is empty. Median uses `statistics.median`: the middle sorted
value for an odd sample and the arithmetic mean of the two middle values for an
even sample. No mean is added. Conditional statistics must always be interpreted
alongside discovery rate and counts.

Budget-limited non-discovery is right-censored with respect to discovery cost.
It never receives budget, budget-plus-one, infinity, or another fabricated
discovery cost. Actual attempts, remaining budget, and termination distinguish
budget exhaustion from strategy/domain exhaustion; the protocol does not infer
termination from counts. Wall-clock and first-trigger elapsed time remain
secondary operational measurements preserved in individual records. No timing
ranking or aggregate timing metric is added.

## Interpretation and partition policy

A synthetic example with ten valid random runs, six discoveries, and median
successful discovery index twenty means both a discovery rate of six out of ten
and median cost twenty among the six successful runs. It cannot be reduced to
"random finds failures in twenty executions." An enumerative discovery at index
seven means its single deterministic ordering discovered within budget; it does
not establish a statistical discovery probability.

Development campaigns may later support guided-method engineering. Held-out
campaigns should be reserved for evaluation after guided design decisions are
frozen. Partition is administrative protocol metadata, never a strategy
constructor argument, `start()` description, feedback field, or strategy
metadata entry. Identical public descriptions produce identical baseline
behavior regardless of the administrative partition label.

The checked-in held-out sources and manifest are accessible. This partition is
organizational, not a secret adversarial test set. The existing in-process
opaque adapter is a cooperative information boundary, not a sandbox.

## Serialization, integration, and deferred work

Protocol, campaign result, and individual summaries provide JSON-compatible
`to_dict`/`to_json` serialization. Summaries are also included in campaign output;
protocol plan serialization is exposed as `plan_to_dict` and `plan_to_json`.
Schema version is `1`. JSON keys are sorted, formatting is compact, tuples become
JSON arrays, enums use stable strings, integer
seeds remain exact, and `None` becomes `null`. Nonfinite values are rejected;
there is no repr fallback, private filesystem path, or automatic file write.
Equivalent immutable data serialize identically; measured timing can differ
between real executions.

Campaign IDs are deferred because there is no storage or deduplication consumer.
Comprehensive environment/build fingerprinting is also deferred. Declarations
preserve ordering, budget, baselines, seeds, and partition, and records preserve
the actual public domain; future research campaigns must additionally bind
results to corpus/build, FIRMAVEX, Python, toolchain, and emulator versions.
Cross-environment replay is not guaranteed by this schema.

Campaign-scale tests use fake infrastructure. The small real integration test
uses one unchanged legacy threshold fixture, its original public domain 0..255,
budget one, and a custom seed tuple `(0,)`: enumerative executes input zero and
exhausts its budget without discovery; random seed zero executes input 197 and
discovers the existing threshold failure at execution one. There are exactly
two QEMU/GDB executions total. This exercises the full layered path without
running the standard ten-seed real campaign. These are integration assertions,
not research-performance evidence. No full development campaign or held-out
campaign is run for Step 16E.

A future guided strategy requires deliberate supported-strategy registration
and a deliberate extension of the Step 16D factory, not an arbitrary plugin or
placeholder. It must preserve the existing accounting, discovery definition,
censoring, infrastructure-abort policy, and serialization fundamentals.

Deferred work includes guided/heuristic/AI search and tuning, final
baseline-versus-guided experiments, full development and held-out campaigns,
significance testing, confidence intervals, survival analysis, plots,
persistent result storage, comprehensive provenance, runtime optimization,
persistent QEMU, and adversarial process/filesystem isolation. Step 16E adds no
new firmware predicate, oracle, split, baseline semantics, or performance claim.
