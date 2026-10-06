# Step 15B: controlled Cortex-M evaluation foundation

These are synthetic experimental fixtures for QEMU `mps2-an385`, not production
firmware. No guided search, model, external service, or hardware target is added.

## Corpus versions

Corpus v1 in `firmware/benchmarks/cortex_m/corpus` is unchanged: five scalar
conditions and the existing input domain 0..255. Its existing CLI and all legacy
search/reproduction/minimization/reporting entry points remain available.

Corpus v2 in `firmware/benchmarks/cortex_m/corpus_v2` has eight independent
programs. Every trial accepts exactly four ordered values in 0..15, giving
65,536 possible trials per fixture. Uniform public input shape avoids revealing
the predicate family through a per-benchmark interface.

| Internal family | What it exercises | Administrator split |
|---|---|---|
| Multi-variable | Two independently controlled values constrained by bounds and a sum | Development |
| Nested branches | A path through multiple dependent branches | Development |
| Bitwise/arithmetic | Shift, XOR, addition and a masked result with another constraint | Development |
| Magic/check | Structured tag and check relationship | Development |
| Ordered accumulator | State updated across four actions; order changes the accumulated result | Development |
| Finite-state machine | Ordered transitions, alternate accepted actions and reset transitions | Held out |
| Compound constraints | Ordering, modular arithmetic, interval and difference constraints together | Development |
| Sparse relation | One accepted vector out of the finite input space | Held out |

Values are written to four debugger-controlled array elements before `main`.
The harness snapshots them and calls the predicate. Scalar families use these as
independent channels; sequence families process them in order with state local
to that single trial. Each new trial starts a fresh QEMU process. State persists
between actions inside a trial, never between independent trials. This bounded,
preloaded sequence model is not interactive peripheral/event injection.

## Evaluator and strategy boundary

`evaluation/api.py` defines immutable records and the three-operation strategy
interface. Administrator code owns `BenchmarkRegistry` and `EvaluationSession`.
Give a strategy the adapter from `session.strategy_api()`, not the registry or
administrator session. That adapter has only `describe`, `execute`, and `result`.

The strategy receives:

- An opaque `b-` identifier without a descriptive condition name.
- A common input width/bounds and its assigned execution budget.
- Trial feedback containing status, one-based execution index if dispatched,
  and remaining budget.
- Aggregate experiment results: strategy identifier, counters, first-trigger
  index and measured elapsed time, exhaustion/abort flags and optional seed.

It receives no source name/path, ELF, debugger symbol, predicate, oracle, raw
stdout/stderr, or expected execution count. `safe` only describes the submitted
trial; it never asserts that a benchmark has no failure anywhere in its domain.

The evaluator owns descriptive metadata, split assignment, build outputs,
instrumentation, raw diagnostics, and accounting. Only successful registry
builds register an image for that opaque ID. A session pins its image digest;
missing or changed images count as infrastructure failures before execution.
Failed rebuilds invalidate registration for new sessions. Rebuilding an image
at a shared path during an active experiment is unsupported; use distinct paths.

Ground truth remains in `tests/data`, never imported by production evaluation
or search. Tests consult it after observations to validate outcomes. The live
evaluator discovers a trigger only from observed firmware output.

## What blind means here

The ordinary strategy API and serialized records omit evaluator-only
information. This establishes an architectural boundary for later transport
or process adapters, not adversarial access control. The in-process adapter's
callbacks can be introspected; Python attributes are not a sandbox. A malicious
strategy with access to this checkout can read source, debug binaries, manifest
ID mappings, oracle files, administrator diagnostics, or mutate objects/images.
Canonical IDs can also be memorized across development runs.

For adversarial evaluation, keep evaluator files/processes in a separate
container or account, expose only a narrow execution transport, restrict
filesystem/process/network access, and issue run-specific opaque aliases.
Freeze benchmark/toolchain versions, feedback policy, domain, budget, seeds and
strategy configuration before held-out runs. Do not expose evaluator callbacks
or GDB. This step does not implement that isolation.

The administrator explicitly selects `development` or `held_out`; the strategy
descriptor omits the split and family. The partition establishes support for
future held-out experiments. The two committed held-out fixtures are publicly
inspectable here and are not a secret test set. Future evaluation needs fresh,
unpublished instances and controls against tuning on the evaluation set.

## Accounting and budgets

The evaluator, not the strategy, admits and charges trials. Counters cannot be
supplied in `TrialInput`. Admission/dispatch is serialized with a lock so
concurrent API requests cannot overdraw the budget; this does not introduce
parallel firmware execution.

- A valid dispatched trial is charged before calling the executor, once per
  trial rather than once per action. Repeats also count.
- Successful executions include both safe and triggering outcomes. Triggering
  executions are a subset of successful executions.
- Missing/changed images, debugger errors/timeouts, executor exceptions, and
  malformed executor results consume an attempt and increment infrastructure
  failures. They are neither safe outcomes nor trigger discoveries.
- The first infrastructure failure aborts the session. Later requests return
  `session_aborted` without executing. If a previous valid trigger exists, its
  evidence remains recorded, but `aborted=True` marks an incomplete/invalid
  comparative run. Do not rank aborted runs as ordinary completed experiments.
- Invalid input shape/type/domain returns `invalid_input` without dispatch or
  charge. It is a rejected API request, not a free firmware execution.
- Zero budgets are permitted. On exhaustion, requests return
  `budget_exhausted`, with no execution index and no executor call. Exhaustion
  can coexist with a discovered trigger or an aborted last-slot attempt; use
  the distinct feedback statuses and result flags to interpret each case.

`attempted = successful + infrastructure_failures`. Every attempted trial has
a one-based index. The first-trigger index includes all attempts. Elapsed time
is measured by a monotonic clock from admission of the first valid trial to
observation of the first trigger, including intervening strategy delays. These
are observed timings, not performance claims. Comparisons need the same hardware
and feedback policy; QEMU/GDB startup overhead is substantial.

`random_seed` is recorded metadata: no random strategy is implemented here.
`reproducibility=None` explicitly means not separately measured. Reproduction
and minimization need separate sessions/budgets; never subtract them from
search cost. The v2 runtime tests independently repeat cases to check fixture
determinism. A strategy must not create/reset its own administrator session to
replenish a budget.

## Administrator example

Run from the repository root with the existing Python/ARM/QEMU/GDB tools on PATH:

```python
from pathlib import Path
from src.firmavex.evaluation.api import TrialInput
from src.firmavex.evaluation.registry import BenchmarkRegistry

registry = BenchmarkRegistry()
benchmark = registry.select("development")[0]  # Administrator-only metadata.
built = registry.build(benchmark.benchmark_id, Path("build/v2") / f"{benchmark.benchmark_id}.elf")
if not built["success"]:
    raise RuntimeError(built["stderr"])
owner_session = registry.open_session(benchmark.benchmark_id, 10, "external-baseline", random_seed=42)
strategy = owner_session.strategy_api()
description = strategy.describe()
feedback = strategy.execute(TrialInput((0, 0, 0, 0)))
result = strategy.result()
# Keep owner_session.diagnostics() in administrator logs, never strategy feedback.
```

No example candidate is selected from an oracle. This example is an API trial,
not a search algorithm or a performance experiment.

## Validation

```sh
python -m pytest -q tests/test_evaluation.py tests/test_corpus_v2.py tests/test_runtime_integrity.py
python -m pytest -q tests/test_emulator.py tests/test_monitor.py tests/test_detector.py tests/test_search.py tests/test_reproduction_minimization.py tests/test_reporting.py
python -m pytest -q
```

The oracle tests compile the actual predicate C source with native GCC as a
shared library. They compare independent test-only mathematical/set oracles
with every input: all 256 values for each v1 predicate and all 65,536 vectors
for each v2 predicate. Ordered accumulation is checked using weighted sums;
FSM and sparse behavior use independently enumerated accepted vectors.

Host exhaustive checks are not exhaustive ARM execution. Real Cortex-M builds
and QEMU/GDB integration tests validate the target path using declared positive,
negative, reordered and neighboring cases. Each case runs twice, with triggering
and nontriggering trials in the same session to check reset behavior. The v2
tests execute 52 real QEMU trials. Real existing v1 tests remain intact. Budget,
error and information-boundary rules use controlled executors to avoid needless
QEMU launches.

All images/native shared libraries use temporary or ignored build directories;
none are versioned. Corpora remain small, deterministic and synthetic. Programs
have no realistic peripheral, interrupt, timing or large state-space behavior.
The sparse relation is sparse only relative to this declared finite domain.
The fixtures do not establish general strategy effectiveness.

## Remaining runtime limitations

The shared startup relies on QEMU loading ELF RAM sections; it is not complete
hardware `.data`/`.bss` initialization. Toolchain/QEMU/GDB versions remain
unpinned and debug paths are checkout-dependent. There is a port-release-to-bind
race and a fixed startup delay in the monitor. Firmware tests remain serial;
parallel test execution is not validated. Image hashing is an integrity check
for ordinary file changes, not protection against an adversarial file race.
Keep raw diagnostics administrator-only and never interpret infrastructure
failures as evidence that a firmware input is safe.
