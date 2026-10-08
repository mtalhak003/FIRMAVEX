# Step 17B: feedback-guided search

`strategies/guided.py` adds `GuidedStrategy` to the existing synthetic test
framework. The common `SearchStrategy` interface and Step 17A feedback semantics
are unchanged. This is an algorithm implementation and integration milestone;
it establishes no superiority over the conventional baselines and adds no AI
model or performance campaign.

## Public inputs and algorithm

The strategy receives the public description in `start()`, creates immutable
`TrialInput` proposals, and receives public `TrialFeedback` in `observe()`.
Width and inclusive integer bounds come solely from `InputSpace`. Neither the
opaque identifier nor the assigned execution budget controls proposal ordering.
Execution indices and remaining-budget fields do not control ordering either.

Step 17A supplies an optional immutable `ExecutionSignature(digest, truncated)`
on successful `safe` and `triggered` observations. Its digest hashes the ordered
prefix of at most 4,096 guest program counters, including repeats, using the
versioned SHA-256 framing. The completion-breakpoint PC is excluded. Exactly
4,096 samples followed immediately by completion is untruncated; `truncated`
means execution continued beyond the sampled prefix before completion. Collection
must reach the existing completion breakpoint before the independent failure
symbol is read. Infrastructure failures carry no signature.

Guided search treats the complete signature as an opaque equality label. It
does not interpret the digest numerically, estimate distance to a trigger, or
decode instruction addresses. The first proposal comes from seeded sparse
uniform sampling without replacement, reusing the unchanged `RandomStrategy`.
An observation with a previously unseen signature admits its proposed candidate
to a bounded FIFO archive of mutation parents. Previously seen signatures do
not admit new parents, even after their original parent has been evicted.

Each later proposal tries a bounded number of mutations. A private RNG chooses
a retained parent, one coordinate, and a different legal value uniformly for
that coordinate. Other coordinates are preserved. The first unseen resulting
tuple is proposed. A sparse visited set records proposals immediately, so
duplicate prevention does not depend on observations arriving successfully.

When no parent exists, mutation is impossible, or the bounded mutation attempts
collide with visited tuples, the fallback sampler advances until it finds an
unvisited tuple or exhausts its finite pool. Constant or missing feedback cannot
stall exploration. Every fallback index is drawn at most once. Exhaustion
returns `None` consistently, with no execution dispatch or fabricated outcome.

## Configuration, replay, and cost

Construction requires an explicit exact integer seed. Booleans and noninteger
seeds are rejected. The public settings `archive_size=32` and
`mutation_attempts=8` must be positive exact integers. These are engineering
defaults, not settings selected through benchmark or seed comparisons.
Immutable metadata records `name="guided"`, the exact seed, and both canonical
configuration pairs. Experiment declarations must specify that same complete
configuration; settings are not silently changed during construction.
`guided_metadata(seed, ...)` builds this validated declaration without creating
RNG state. The protocol participant currently uses the default configuration;
single-experiment declarations can specify other validated settings.

The mutation RNG and fallback RNG are private, independent instances initialized
from the declared seed. Global random state is neither consulted nor changed.
`start()` clears visited tuples, signature history, the archive, and exhaustion
state, and resets both seeded streams. Identical public input shape, seed,
configuration, and ordered feedback reproduce proposals in the same Python
environment. Changing only opaque identifiers or accounting fields does not
change the sequence.

For width W, k proposals, archive cap A, and mutation-attempt cap M, retained
state under the common serial runner is O(kW + AW), plus O(k) signatures and
fallback-map entries; there is no
Cartesian-domain allocation. Worst-case retained state grows with exploration
and can reach the domain size after exhaustive search. Mutation work per
proposal is O(M(W + A)), including bounded deque indexing. A fallback request
can skip many earlier proposals near
exhaustion, but total fallback draws across k proposals are at most 2k: each
accepted draw creates a proposal, and each skipped distinct draw corresponds
to an already proposed tuple. Aggregate fallback work is O(kW). These bounds
count integer/tuple operations; very large domain indices also incur Python
big-integer cost. This strategy is not constant-memory search.

## Experiment and protocol integration

Guided experiments follow the existing path:

`ExperimentRunner -> run_strategy -> public adapter -> evaluator`.

There is no separate execution, scoring, timeout, or accounting path. The
evaluator remains the authority for admission, charges, indices, counters,
abort state, discovery, and first-failure timing. A rejected or failed observation
cannot become a discovery through strategy feedback processing. Administrator
diagnostics remain outside the strategy callbacks and serialized records.

Explicit protocols may include `guided`, using a separate nonempty
`guided_seeds` schedule. A guided-only protocol declares `random_seeds=()`;
random and guided schedules retain their independently declared order. Guided
protocols are labeled as custom search protocols. The frozen standard baseline
still contains only enumerative and random, with random seeds 0 through 9; its
declaration, expansion, and serialized form are preserved. Summary seed handling
retains the legacy random schedule and adds a generic seed schedule for the new
participant, without changing discovery denominators or infrastructure-abort
classification. Adding support does not execute a campaign.
The guided-related fields `EvaluationProtocol.guided_seeds` and
`StrategySummary.seeds` change generic Python field inspection, representations,
and `dataclasses.asdict()` output, even when guided is absent. Recursive
`asdict()` dumps of campaign results also change. These generic dataclass forms
are distinct from the official versioned serialization contract: standard
baseline `to_dict()` and `to_json()` representations, expanded plans, and
baseline summary JSON retain their earlier fields and bytes.

For random summaries, an omitted or empty generic `seeds` tuple is the legacy
construction form and is filled from `random_seeds`. A nonempty generic tuple
must match the random tuple exactly, including order. Non-random summaries
reject nonempty `random_seeds`; enumerative summaries reject any seed schedule.
Guided summaries use only the generic schedule. Validation occurs before legacy
normalization, so booleans and mutable containers remain invalid.

Executions to first failure remains the primary discovery-cost measure.
Wall-clock timing is secondary and includes fresh-process startup and instruction
stepping overhead. Neither measure demonstrates effectiveness until an evaluation
protocol and implementation are frozen and a controlled comparison is run.

## Validation and limits

Unit tests use synthetic public feedback labels to isolate causality: identical
seed and proposal history with repeated versus novel signatures can produce
different later ordering. Identical feedback replays identically. Small domains
exhaust with constant or absent feedback, without duplicates. Baseline source
and behavior tests remain unchanged. One test performs two actual Cortex-M/QEMU
executions using the existing instrumentation-only fixture, forwarding a genuine
signature through the common experiment runner and into a later mutation.
It checks mechanics and accounting, without comparing strategies or selecting
seeds by observed performance.

Effectiveness depends on whether execution signatures distinguish useful
behaviors. Identical control flow with different data can share a signature;
differences after the capped prefix are invisible. Novel instruction traces
need not be closer to failure, and a bounded parent archive can discard useful
parents. Sparse deduplication and signature history can still use substantial
memory during long runs. Signature replay can depend on firmware image,
compiler layout, Python RNG implementation, QEMU/GDB versions, and environment.

The corpus remains small and controlled. Held-out fixtures in a public repository
are not secret adversarial tests. The in-process boundary is cooperative, without
process/container isolation. Production guided code receives no registry,
source, image path, debugger interface, oracle, partition, or diagnostic handle
and reads no repository files. This milestone provides no security guarantees,
AI capabilities, statistical superiority claim, or large evaluation campaign.
