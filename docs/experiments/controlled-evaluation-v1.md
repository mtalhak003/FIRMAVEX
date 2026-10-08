# Step 18A: controlled Cortex-M evaluation protocol v1

This document declares `controlled_cortex_m_v1`, a separate, versioned comparison
of enumerative, seeded random, and feedback-guided search. Step 18A prepares the
plan and validates its contracts; it does not execute the main campaign or
publish search-performance results. The declaration is pending human review
before a Git checkpoint and later experimental execution.

The approved implementation checkpoint used to select these settings is
`d62cc715d82cf26359dc34ae96c48749bdb43403` (`Add feedback-guided firmware search
strategy`). Settings below are selected as engineering constraints without
inspecting strategy-performance outcomes, selecting successful seeds, or reading
expected triggers. Changing the settings after viewing results requires a new
protocol version and an explicit account of the change.

## Existing infrastructure and the additive preset

The existing path remains:

```text
EvaluationProtocol.expand() -> ExperimentSpec
    -> CampaignRunner -> ExperimentRunner -> run_strategy()
    -> strategy adapter -> EvaluationSession -> registered firmware observation
    -> authoritative ExperimentRecord -> CampaignResult / StrategySummary
```

The evaluator admits and charges executions, determines failure-symbol outcomes,
owns diagnostics, and aborts sessions on infrastructure failures. The runners
control the existing strategy lifecycle and termination. Campaign results retain
the exact ordered records and derive summaries from evaluator measurements.
There is no second execution counter, new execution loop, or new result type.

`src/firmavex/protocols/controlled.py` provides:

```python
from src.firmavex.protocols.controlled import (
    controlled_cortex_m_v1,
    controlled_cortex_m_v1_plan_to_dict,
    controlled_cortex_m_v1_plan_to_json,
)

development = controlled_cortex_m_v1(partition="development")
held_out = controlled_cortex_m_v1(partition="held_out")
development_plan_json = controlled_cortex_m_v1_plan_to_json(
    partition="development",
)
```

These calls declare and serialize plans; they do not build or execute firmware.
The factory accepts only the existing two partition names and returns the exact
existing immutable `EvaluationProtocol` type. It offers no budget, strategy,
seed, or guided-configuration overrides. The expanded guided metadata must match
the pinned configuration below; future drift in generic guided defaults fails
closed at construction instead of silently changing this preset. Each returned
instance retains the validated immutable experiment tuple, so later expansion,
plan serialization, and campaign validation do not recompute guided defaults.
This uses the existing protocol type and execution interfaces. Reconstructing
or cloning a generic `EvaluationProtocol` from its dataclass fields creates a
custom declaration without this snapshot; use the controlled factory and retain
its returned instance for the frozen preset.

The administrator plan envelope has `schema_version=1`,
`preset="controlled_cortex_m_v1"`, `corpus_version=2`, the fixed
`source_checkpoint` above, `expected_input_space={"width": 4, "minimum": 0,
"maximum": 15}`, and `plan=protocol.plan_to_dict()`. The envelope binds the
declaration to its intended corpus, domain, and source checkpoint. It is planning
metadata, not proof of the actual compiler, ELF, environment, or running source
version, and is not a strategy input. JSON serialization is deterministic and
does not write a file automatically.

The historical `standard_baseline_protocol` remains enumerative plus random
seeds 0–9. Its official serialization and expansion ordering remain unchanged.
The new three-strategy preset uses the existing explicit custom-search protocol
representation and does not relabel itself as the standard baseline.

## Included corpus and administrative partitions

Include all eight existing corpus-v2 benchmarks for QEMU `mps2-an385`, filtering
the committed manifest by partition while preserving its order. No benchmark,
predicate, ground-truth record, opaque identifier, or split is changed. The common
public domain is four ordered uint32 input values, each in the inclusive range
0–15, containing `16**4 = 65,536` possible candidates.

The following mapping is administrator documentation of existing manifest
metadata; it includes no expected input, trigger constant, or failure condition.
Benchmark family names and partition labels are not passed to strategies.

| Phase | Manifest order within phase | Opaque benchmark ID | Existing family name |
| --- | --- | --- | --- |
| Development | 1 | `b-3874d6a4a92f46758d73854abf0a08df` | multi_variable |
| Development | 2 | `b-08e9f32ef15d4ef0b17b65a4c211f8e2` | nested_branches |
| Development | 3 | `b-64a1899b33444f9fb3a82bdfe238d812` | bitwise_arithmetic |
| Development | 4 | `b-c7a338d3ea684d149e5a45e49d235dc7` | magic_check |
| Development | 5 | `b-965d82f3548943c5bfb218d7e0c5351c` | ordered_accumulator |
| Development | 6 | `b-762a8f0d6fbf4b6eb34a821e9fc35c24` | compound_constraints |
| Held out | 1 | `b-b5ba43a1f81041a28dcb6e10f0754d91` | finite_state_machine |
| Held out | 2 | `b-04a234ad83964671a791285172e0bcee` | sparse_relation |

Development and held-out phases use separate protocols and separate campaign
results. Execute development first and held out only after design and protocol
decisions are frozen; this phase order is administrative, not a new combined
protocol or strategy-visible field. Never pool the two phases into one claimed
held-out result. Held-out results cannot justify changing settings and rerunning
the same partition as if it remained untouched.

The held-out source, manifest, and test oracle are publicly checked in. This is
an organizational holdout, not an unpublished, adversarially secret benchmark.
The in-process adapter is a cooperative boundary and cannot prevent deliberate
filesystem access or Python introspection. Report any prior exposure or design
choices informed by the public held-out corpus when interpreting later results.

## Frozen configuration, seeds, budget, and ordering

| Strategy | Repetitions per benchmark | Seeds | Configuration |
| --- | --- | --- | --- |
| `enumerative` | 1 | `None` | Empty configuration |
| `random` | 10 | `(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)` | Empty configuration |
| `guided` | 10 | `(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)` | `archive_size=32`, `mutation_attempts=8` |

The evaluator-owned execution budget is **256 attempted executions per run** for
every strategy and benchmark. This power-of-two engineering cap explores at
most `256 / 65,536 = 0.390625%` of a benchmark's finite public domain. It bounds
the intended workload while leaving a substantial unexamined domain. It is not
a claim that 256 is optimal, sufficient to discover any particular failure, or
selected from expected-trigger locations or observed discovery rates.

Administrative oracle inspection after the initial freeze confirmed that this
**256-execution budget guarantees zero enumerative discoveries across all eight
current fixtures**, assuming successful observations. The first 256 proposals
fix the first two coordinates to `(0, 0)`, and no fixture triggers in that
prefix. The earliest enumerative discovery anywhere in the current corpus is
at execution **3,328**, beyond the frozen cap. These are properties of the
checked-in predicates and ordering, not measured campaign results or information
supplied to strategies.

This creates a strong floor effect and limits interpretation. Equal budgets
ensure equal opportunity in execution count, not equal effectiveness across
search orders. Rare-trigger fixtures also provide little discovery evidence
within this cap. No general superiority conclusion can follow from this preset
alone. A separately predeclared higher-budget sensitivity experiment may be
necessary later; it must retain its own declaration and be reported separately,
with disclosure of this administrative oracle exposure. The frozen budget and
seed schedules are unchanged.

Enumerative uses its unchanged lexicographic ordering with the last position
fastest. Random uses its unchanged private seeded RNG and uniform sampling
without replacement. Guided uses its unchanged signature-novelty parent archive,
bounded single-coordinate mutations, and seeded fallback exploration. All three
avoid duplicate proposals before domain exhaustion. Neither baseline changes
proposal order in response to execution feedback.

The guided configuration is the existing reviewed 32-parent / 8-mutation-attempt
configuration, pinned explicitly for this preset. Identical numeric seed
schedules improve traceability; they do not make random and guided trajectories
identical or cross-strategy runs statistically independent. Guided's fallback
uses the same seed convention as random, so related initial candidates are an
existing algorithm property that must be acknowledged in interpretation.

For each benchmark in the partition order above, the exact run order is:

```text
enumerative, seed None
random, seeds 0 through 9 in order
guided, seeds 0 through 9 in order
then the next benchmark
```

Do not repeat enumerative ten times to fabricate a matching stochastic sample.
Do not select best seeds, omit unsuccessful seeds, reorder runs after viewing
outcomes, or substitute a seed sweep. Record all declared seeds, including
infrastructure-aborted or invalid runs.

## Fair execution conditions and repeatability

For a given benchmark, every strategy uses the same registered ELF image,
public input space, failure symbol/completion breakpoint, execution budget,
evaluator semantics, runtime-signature policy, and QEMU/GDB environment. Build
once administratively with the existing shared Cortex-M compiler, register that
image, and reuse it across that benchmark's runs. The registry checks its image
digest before each execution; strategies receive neither the image nor its
paths, source, symbols, family name, partition, or oracle.

Every experiment opens a fresh evaluation session. Every admitted candidate
launches fresh QEMU and GDB processes, so firmware state does not carry between
candidates or runs. The common runner stops on first discovery, exhaustion,
invalid output, or session abort. Reproduction or minimization, if later
performed, needs separately declared sessions and budgets and cannot be counted
as search executions or subtracted from the discovery index.

Deterministic replay requires the same strategy version, complete metadata,
seed, public domain, and feedback history. Real signature replay additionally
requires an equivalent firmware image and runtime environment. Before a later
reviewed campaign, archive the approved plan and implementation revision;
compiler, linker, QEMU, GDB, and Python versions; build flags and input hashes;
ELF SHA-256 digests; host/runtime configuration; and the exact official records.
Keep raw diagnostics and build paths administrator-owned. This milestone
provides no automatic environment capture or persistent result store. The fixed
source-checkpoint field alone does not supply those missing measurements.

The automated scope is limited: the preset validates its settings and expanded
guided metadata. The generic `CampaignRunner` verifies partition membership and
one canonical registry input space matching returned records, but does not bind
that space to this preset's expected `(width=4, minimum=0, maximum=15)`, check
corpus/source hashes, or authenticate the reference checkpoint. The plan
envelope declares provenance; it does not enforce its authenticity at execution.

Before a later campaign, the administrator **must** verify:

- `registry.input_space == CONTROLLED_INPUT_SPACE` from the preset module.
- The exact manifest version, `mps2-an385` target, opaque IDs, partition labels,
  and filtered order agree with this declaration.
- Corpus predicates, harness, startup code, linker script, and other frozen
  source inputs agree with the approved source checkpoint; record the reviewed
  protocol revision and actual source/build hashes.
- Registered ELF hashes and compiler/build settings are fixed across strategies
  for each benchmark, and the actual host/tool environment is recorded.

This manual binding is a remaining MEDIUM reproducibility risk, not an automatic
full-freeze guarantee. Step 18A preflight observed Python 3.12.14, ARM GCC 14.2.1,
GDB 16.3, and QEMU 10.0.13. These versions are an environment inventory, not a
bundled toolchain lock, measured throughput, or proof that a future campaign
uses the same tools. Review any environment change before executing that plan.

## Primary metrics and non-discovery

Report metrics separately for each benchmark, strategy, and partition. Preserve
the ordered per-run evaluator measurements and all raw classification counts.

1. **Failure discovery rate under budget** is discovered valid runs divided by
   valid runs. A valid run excludes infrastructure-aborted and invalid-strategy
   runs. Report planned/completed, valid, discovered, non-discovered, aborted,
   and invalid counts beside the rate. When there are no valid runs, the rate is
   undefined (`None` / JSON `null`), not zero. Enumerative's one deterministic
   result is one result under its fixed ordering, not a statistical estimate of
   discovery probability.
2. **Executions to first failure** uses the evaluator's positive
   `first_failure_execution` for discovered valid runs. Preserve each eligible
   index and the existing conditional minimum, median, and maximum. Always
   interpret these successful-run statistics alongside discovery rate and the
   full counts. A lower median among fewer discoveries does not establish a
   better overall method.

A valid budget-limited non-discovery is right-censored at its actual attempted
execution count with respect to time-to-discovery. It remains in the discovery
rate denominator and has no observed first-failure cost. Strategy/domain
exhaustion without discovery is reported as its actual termination and attempts;
it is not relabeled as budget exhaustion or discovery. Neither kind receives an
imputed cost of budget, budget plus one, infinity, or zero. Current summary
`discovery_executions` uses `None` for these missing observations and for invalid
runs; the underlying record and classification counts distinguish their reasons.
No survival-analysis or statistical-significance implementation is added here.

## Infrastructure, invalid output, and interruptions

An admitted execution consumes one attempted-execution slot even if firmware
observation fails or is interrupted. Infrastructure failure aborts that session
immediately, exposes structured failure status without a signature, and prevents
later firmware dispatch from that session. Preserve the record and report the
infrastructure failure separately from a valid search non-discovery. The
existing campaign continues with later independent experiments after an ordinary
recorded abort. Invalid strategy output is another separate classification,
never silently treated as safe firmware behavior or an infrastructure failure.

If an underlying record preserves discovery before a subsequent infrastructure
abort, preserve its original discovery information but exclude that aborted run
from the valid discovery numerator and conditional successful-cost sample.
Infrastructure reliability includes aborted counts and their denominator of
planned/completed runs; report invalid output separately. Administrator-owned
diagnostics may explain causes without entering strategies or official records.

`KeyboardInterrupt`, `SystemExit`, and other control-flow interruptions propagate
after the evaluator records the admitted attempt and abort state. The existing
experiment/campaign runners do not manufacture a completed record or partial
`CampaignResult`; there is no resume/checkpoint or partial-result persistence.
Administrators can inspect the last session in memory. A campaign that did not
complete its declared plan cannot be presented as a completed comparison.

Do not automatically rerun failed runs, replenish budgets, retry until a seed
succeeds, or replace missing runs with another seed. Report the reliability
issue. An invalidated campaign and any subsequently approved rerun need an
explicit recorded decision. Exact-plan replications retain the protocol version
and are labeled as separate executions; never silently merge selected records
from them. Changing frozen settings or execution semantics requires a new
versioned declaration rather than a replacement labeled as the original run.

## Secondary timing and current measurement gaps

Wall-clock timing and measurable execution throughput are secondary operational
metrics; primary comparisons use evaluator-owned discovery and execution counts.
The existing `time_to_first_failure_seconds` starts immediately before the first
admitted execution and is recorded after a triggering observation returns. It
includes image-integrity checks, QEMU/GDB launch/connect overhead, startup sleep,
stepping, cleanup, and strategy proposal/observation processing between
executions. It
excludes builds and the first strategy initialization/proposal. Non-discoveries
have no first-failure time. It is not native guest execution time.

There is currently no total-run duration or execution-throughput field. A future
reviewed capture may externally measure host wall time around declared runs,
state whether builds are included, and calculate attempted executions divided
by measured seconds. Do not infer those measurements from the first-failure
field, omit setup costs without disclosure, or fabricate timing for censored
runs. No new timer or throughput collector is implemented by Step 18A.

## Expected workload and runtime feasibility

| Phase | Benchmarks | Runs | Maximum charged attempts |
| --- | --- | --- | --- |
| Development | 6 | `6 * 21 = 126` | `126 * 256 = 32,256` |
| Held out | 2 | `2 * 21 = 42` | `42 * 256 = 10,752` |
| Both separate phases | 8 | 168 | 43,008 |

These are declared maxima, not measured execution counts. Discovery, exhaustion,
invalid output, or infrastructure abort can stop a run earlier.

The current observation path launches fresh QEMU and GDB for every candidate and
sleeps 0.5 seconds after QEMU launch. Conditional on all 43,008 attempted
executions reaching that sleep, the prescribed sleeps alone total
`43,008 * 0.5 = 21,504 seconds`, approximately **5.97 hours**. This arithmetic
floor excludes all process launch, debugger, guest, hash, build, cleanup, and
strategy costs. It is not observed throughput, a guaranteed campaign duration,
or an upper bound; earlier terminations and pre-launch failures change the count.

All registered executions, including the baselines, collect Step 17A signatures.
GDB samples PCs in order, retaining repeats, and single-steps at most 4,096 guest
instructions. The completion breakpoint PC is excluded. Completion immediately
after the 4,096th sample is untruncated; additional execution beyond that prefix
sets `truncated=True` and continues normally to the required completion
breakpoint before observing failure. Capping never supplies a second execution
or determines whether failure occurred.

The default five-second GDB subprocess timeout covers connection, injection,
stepping, continuation, and failure-symbol reading. ELF verification, QEMU
startup delay, and cleanup are outside that timeout; it is not an overall
wall-clock deadline. QEMU cleanup terminates, waits up to two seconds, then kills
if necessary. Slow debugger or host behavior can become an infrastructure abort,
not a valid non-discovery. Single stepping can dominate tiny synthetic firmware,
and the startup/cleanup cost prevents assuming that a large matrix is practical.

Existing small real integration tests establish controlled signature replay,
safe-behavior differentiation, and feedback-to-guided-proposal plumbing. They do
not measure corpus-wide throughput, discovery rates, or comparative efficacy.
The complete suite is a regression check, not a campaign feasibility measurement.

Before Step 18C, use a separately reviewed, predeclared bounded feasibility pilot
with selected workload limits to measure runtime and reliability. Label it as a
pilot, keep it separate from the frozen main campaign, and do not tune the main
seeds, budget, or guided settings from pilot discovery outcomes. No such pilot or
performance matrix is run in Step 18A.

If feasibility proves inadequate, readiness polling, persistent debugger
connections, verified reset/snapshot execution, or other runtime changes require
another reviewed milestone. Preserve fresh-state semantics, signature meaning,
timeouts, cleanup, and evaluator accounting, and apply any revised runtime
uniformly to every strategy before freezing a new campaign version. This
milestone implements no runtime optimization or parallel execution.

## Threats to validity and interpretation limits

- Eight small synthetic benchmarks and two public held-out examples provide a
  controlled initial corpus. They do not establish results for external firmware,
  physical hardware, production workloads, or broader populations.
- Prior public knowledge of predicates or held-out sources can bias development.
  Preserve the cooperative information boundary and disclose exposure; opaque
  IDs and hashing do not provide secrecy or process isolation.
- A SHA-256 fingerprint of a bounded PC sequence is neither coverage nor distance
  to failure. Identical paths with different data, identical truncated prefixes,
  or changed instruction layout can limit or change useful feedback.
- Fixed benchmark/strategy/seed ordering improves replay but can confound
  secondary wall-clock comparisons with host load, warming, and temporal drift.
  Record conditions rather than claim that fixed order removes this bias.
- Ten seeded repetitions support descriptive per-benchmark reporting, not an
  automatic significance claim; one enumerative run has a different repetition
  design. Shared seed conventions do not make strategy samples independent.
- Timeout sensitivity, toolchain/version dependence, port-allocation races,
  absent persistence, and debugger overhead can affect reliability and cost.
  Excluding aborts from valid rates requires showing their counts explicitly.
- The generic campaign runner does not automatically authenticate the declared
  source checkpoint, corpus hashes, or expected domain. Administrator checks and
  archived provenance are required to bind a completed campaign to this preset.
- Conditional successful-discovery costs can hide low discovery rates unless
  interpreted with censoring, non-discoveries, and all denominators.

Step 18A changes no benchmark predicate, ground truth, split, strategy behavior,
runtime feedback, or evaluator accounting. It supplies a declaration and
validation foundation. No superiority, AI, novelty, security, or readiness claim
and no performance result follows from this protocol.
