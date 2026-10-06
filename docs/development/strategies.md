# Step 16A: common strategy execution contract

Implemented in Step 16A: a common strategy protocol, serial runner, candidate
validation, immutable run records, and unit/integration tests. Step 16B adds the
deterministic enumerative baseline described below. No seeded random baseline,
guided search, AI search, aggregate experiments, statistical comparison,
persistent results, or performance claims are implemented.

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
status, execution index, and remaining budget. The returned run record adds only
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
all conventional search and will later be complemented by seeded random search.
Do not tune dimension order or starting values to known corpus triggers, or use
held-out knowledge. No random/guided/AI implementation, aggregate experiments,
statistical comparisons, or performance claims are added in Step 16B.
