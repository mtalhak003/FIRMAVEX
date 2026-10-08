# Step 16A: common strategy execution contract

Implemented in Step 16A: a common strategy protocol, serial runner, candidate
validation, immutable run records, and unit/integration tests. Step 16B adds the
deterministic enumerative baseline; Step 16C adds seeded uniform-random search
without replacement. These baseline milestones add no guided search, AI search,
aggregate experiments, statistical comparison, persistent results, or performance
claims.
Step 17B's additive feedback-guided participant is documented separately in
[guided-search.md](guided-search.md); the earlier baseline algorithms and common
execution contract are preserved.

## Contract and lifecycle

`strategies/api.py` defines `SearchStrategy`. A strategy exposes immutable
`StrategyMetadata` and implements:

- `start(description)`: initialize from the public `ExperimentSpec`.
- `propose()`: return a `TrialInput`, or `None` to stop without executing.
- `observe(candidate, feedback)`: react to immutable public `TrialFeedback`.

Configuration/initialization belongs to the strategy constructor and `start`.
The caller supplies `run_strategy(strategy, session.strategy_api())` with a
dedicated Step 15B adapter. The runner retains the adapter; it never passes the
adapter or its callbacks to the strategy. Use one controller per session. The
runner does not add concurrency; evaluator admission remains serialized.

The runner obtains description/result through the public API, skips lifecycle
callbacks for an already terminal session, starts the strategy, validates each
proposal, executes it through the public API, delivers feedback, and checks the
evaluator's result before requesting another candidate. Strategies receive the
terminal trial's feedback. Returning `None` ends the run without an extra
execution or fabricated discovery. No callback return value can change counters.

Use the existing canonical `TrialInput(values=tuple_of_integers)`. Width and
inclusive bounds come exclusively from the public `InputSpace`; the runner has
no four-value/nibble assumption. Positions have no semantic labels. Wrong record
types (including subclasses), mutable value containers, wrong widths, booleans,
nonintegers, and out-of-domain values are rejected before `execute`. Invalid
output ends the run with an `InvalidOutputReason`; there is no firmware dispatch,
budget charge, infrastructure failure, or raw candidate representation in that
error. The evaluator still performs its own admission validation.

## Results and termination

The frozen `StrategyRun` contains the evaluator's actual `ExperimentResult`, a
public metadata snapshot, a `TerminationReason`, and an optional structured
invalid-output reason. It does not maintain separate counters or reconstruct an
evaluation result. Reasons are:

- `failure_discovered`
- `budget_exhausted`
- `session_aborted`
- `strategy_stopped`
- `invalid_strategy_output`

Abort takes precedence over a historical discovery; discovery takes precedence
over exhaustion when the last slot triggers. Existing discovery information is
retained inside the evaluator result even when the session later aborts.

The evaluator alone owns admission, charging, success/failure accounting,
first-trigger execution index/timing, budget remaining, and abort state. Its
`attempted = successful + infrastructure_failures` invariant and budget policy
are unchanged. The runner never supplies these fields, resets a session, or
reads diagnostics. `safe` describes only the submitted trial.

Lifecycle exceptions propagate, with no synthesized public run record or raw
exception text in feedback. `KeyboardInterrupt` and `SystemExit` propagate
unchanged. If interruption occurs during an admitted firmware execution, the
existing evaluator records and aborts that charged attempt before re-raising.
Failures in strategy callbacks do not become firmware infrastructure failures;
administrator code can retrieve the real evaluator result after an exception.

## Reproducibility metadata

`StrategyMetadata` records a nonempty strategy name, an explicit optional integer
seed, and immutable key/value configuration pairs. Keys are unique and sorted
for a stable snapshot; values are finite JSON-compatible scalars. Mutable/nested
containers and executable objects are rejected. Metadata never initializes or
reads global randomness. Future implementations can create a local generator
from their declared seed. Actual strategy determinism is not certified here.

Administrator code should use the same name/seed when creating the evaluation
session. The run separately records strategy-declared configuration and the
unchanged evaluator-assigned identity/seed; it does not overwrite either or
silently synchronize mismatched tags. Metadata must describe public algorithm
settings, never evaluator paths, splits, diagnostics, or oracle information.
No experiment aggregation or seed scheduling is added in this milestone.

## Information boundary

The strategy receives only the opaque benchmark ID, input width/bounds, assigned
budget, its own proposals/configuration, and coarse public feedback containing
status, execution index, and remaining budget. Step 17A additionally supplies an
optional immutable runtime execution signature; see
[runtime-signature.md](runtime-signature.md) for its exact semantics. The returned
run record adds only
public strategy metadata, termination/validation enums, and the existing public
evaluation result. Fields are immutable records/scalars, not callbacks or
administrator object references.

No source name/path, ELF path, registry entry/instance, evaluator instance,
manifest, development/held-out label, oracle, expected trigger, raw monitor
result, GDB/QEMU diagnostic, or private evaluator callback is supplied to the
strategy. Production strategy modules import only the public evaluation API.
Test doubles and administrator-side integration fixtures live in tests; their
fixed input sequences are not production baselines.

This is a controlled experimental API boundary, not adversarial sandboxing.
Malicious in-process Python can inspect frames, private state, files, or process
memory and can violate frozen-object conventions. Strategies must cooperate
with the contract. Process/container isolation and a transport boundary remain
future work; Step 15B's public held-out fixtures remain inspectable. Existing
QEMU/toolchain and image/port handoff limitations still apply.

## Step 16B: deterministic enumerative baseline

`strategies/enumerative.py` implements `EnumerativeStrategy` through the unchanged
Step 16A contract. Its metadata is `StrategyMetadata("enumerative")`: empty
configuration and no seed. Use it with the existing runner and a dedicated
opaque adapter; the strategy never calls `execute` itself.

For public width `W` and inclusive bounds `L..U`, it enumerates `[L,U]^W` in
lexicographic order, with the last position changing fastest. For width two and
bounds 0..2, the sequence is `(0,0), (0,1), (0,2), (1,0), (1,1), (1,2), (2,0),
(2,1), (2,2)`. No width, bounds, cardinality, dimension permutation, predicate,
or triggering value is hard-coded into the strategy.

`start(description)` always resets enumeration to the minimum tuple, including
after prior exhaustion or when receiving a different public shape. Fresh
instances yield the same sequence. `propose()` before `start()` raises a clear
`RuntimeError`. Descriptions must contain the valid input space already enforced
by `EvaluationSession`; this strategy adds no parallel domain-validation policy.

A cursor increments with carry and creates immutable `TrialInput` snapshots.
It guarantees uniqueness without a visited set, caches no range/product pool,
and never calculates cardinality. Retained memory is O(width), with O(width)
worst-case work per proposal, including constructing the output tuple. For v2,
the public domain happens to contain `16^4 = 65,536` tuples, but iteration does
not depend on that count. `observe` is deliberately a no-op: feedback does not
guide ordering, and the strategy maintains no execution counter or budget.

After the last tuple, every subsequent `propose()` returns `None`. If the domain
is smaller than the evaluator's budget and no failure was observed, the runner
uses existing `strategy_stopped` semantics without another dispatch or charge.
Discovery, budget exhaustion, and infrastructure abort still stop the runner
immediately; their indices, counters, timing, and final result remain entirely
evaluator-owned. Enumerating the domain without a trigger never fabricates a
discovery or an evaluator status.

Tests cover finite domains, ordering, uniqueness, reset, memory, metadata,
feedback independence, and runner/evaluator termination. A small real integration
uses the existing v1 scalar threshold corpus fixture over its original 0..255
domain through `EvaluationSession.strategy_api()`. Administrator test code owns
build/instrumentation details; the strategy sees only an opaque ID and public
shape/budget. Seven QEMU/GDB trials reach discovery. Oracle data is read only
after that test run to validate the result. No v2 predicates, domains, splits,
ground truth, monitor, or evaluator are changed, and no QEMU comparison matrix
is introduced.

Lexicographic enumeration is ordering-sensitive: a trigger near the beginning
appears easier than one near the end. This single baseline does not represent
all conventional search and is complemented by Step 16C's seeded random baseline.
Do not tune dimension order or starting values to known corpus triggers, or use
held-out knowledge. No random/guided/AI implementation, aggregate experiments,
statistical comparisons, or performance claims are added in Step 16B.

## Step 16C: seeded uniform-random baseline

`strategies/random.py` implements `RandomStrategy(seed)` through the unchanged
Step 16A contract. Construction requires an explicit integer seed: missing seeds
raise `TypeError`; `None`, booleans, strings, floats, and other noninteger values
raise `ValueError` before creating an RNG or dispatching firmware. Zero, negative,
and arbitrarily large integer seeds are supported. Metadata is
`StrategyMetadata("random", seed=seed)`, with empty configuration. The identity
fixes without-replacement semantics. RNG state, map, and cursor are not metadata.

Each instance owns a private standard-library `random.Random`, using Python's
Mersenne Twister implementation. There is no implicit seed, global random-state
use, time dependence, hash-order dependence, or OS-random default. `start` resets
the RNG to the declared seed and clears all sampling state, even after exhaustion
or a prior run using a different public input shape. `propose` before `start`
raises `RuntimeError`; `observe` is a no-op. Benchmark IDs, budgets, outcomes,
and feedback never change the candidate ordering.

The strategy derives `base = U-L+1` and exact integer cardinality `N = base**W`
from the evaluator-validated public `InputSpace`. Indices in `0..N-1` map
bijectively to tuples by base-digit decoding and adding `L` to each digit. The
last position changes fastest, matching `EnumerativeStrategy`. Domain arithmetic
and `randrange` support integers beyond machine-size range lengths.

Sampling is a lazy Fisher-Yates shuffle of an implicit identity array. For `r`
remaining slots, draw `j = rng.randrange(r)`, emit the index mapped at slot `j`,
move the last live slot into slot `j`, and shrink the live interval. Only changed
slot mappings are stored; the discarded tail mapping is removed. Every remaining
candidate occupies exactly one live slot, so each has selection probability
`1/r` under uniform integer draws. Induction gives a uniform permutation under
that RNG model, and removed candidates cannot be selected again. `randrange`
uses unbiased bounded integer selection, not modulo reduction or retrying
duplicate candidates. No hash sorting, weighting, mutation, or guidance is used.
The structural test covers all `4!` legal draw paths for a tiny domain and finds
each permutation once; it is not an empirical statistical proof.

Initialization does not materialize candidates or an index pool. After `k`
proposals, sampling storage is O(k) integer map entries, plus private RNG state
and O(width) decoding/output memory. Entries are removed as the live domain
shrinks, but hash-table capacity can retain earlier allocations. Worst-case
storage can be O(N) after many proposals; this is a sparse proposal-dependent
structure, not a constant-memory permutation. Arbitrary-size index integers
also require space proportional to their bit lengths. No `TrialInput` objects
are cached by the strategy, and no visited set or duplicate-retry loop exists.

After complete exhaustion, `propose` consistently returns `None`. The unchanged
runner uses `strategy_stopped` when the domain ends before the execution budget.
Discovery, budget exhaustion, and infrastructure abort use existing termination
semantics. All execution charging, first-trigger index/time, counters, and abort
state remain evaluator-owned; the number of remaining sampling slots is not an
execution budget. Both baselines share the contract, candidate representation,
public domain, runner, and accounting. Their search-order difference is fixed
lexicographic order versus a seeded uniform ordering without replacement.

Exact replay requires the same implementation, seed, and input space within the
supported environment. The project does not freeze its own PRNG or bounded-draw
algorithm; Python/runtime changes can change exact sequences. Record strategy
and Python versions as well as public metadata in future experiments. Replaying
a seed is an engineering reproducibility property, not evidence that random
search is better or worse. No permanent or cross-language sequence guarantee is
claimed.

The real integration test uses predeclared seed 42, independently of firmware
outcomes, with the existing v1 threshold ELF and a test-only scalar domain 0..2.
Three fresh QEMU/GDB trials are non-triggering and exhaust that tiny domain,
leaving two of five execution slots unused. This proves the real dispatch path
through the opaque adapter and evaluator without claiming discovery. The test
restriction does not alter any manifest, corpus predicate, production domain,
split, or ground truth. No seeds were searched or selected for early triggers.

Individual runs are seed-dependent. Future comparisons must use multiple
predeclared seeds, chosen without benchmark-outcome or held-out knowledge. Use
the same declared seed set across comparable benchmark runs where appropriate,
and report aggregate outcomes rather than favorable individual seeds. Step 16C
does not select the final experiment seed set, run seed sweeps/optimization, or
implement aggregation, statistical comparisons, guided/AI search, persistent
storage, or performance claims. Those comparison policies belong to a later
experiment-runner milestone.
