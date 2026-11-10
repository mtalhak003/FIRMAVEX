# Research history and experimental contract map

This companion expands the research portion of the
[primary chronological history](../product/development-progress.md). Its purpose
is to explain how source analysis became a controlled execution experiment and
which claims the retained evidence permits. It is not a new campaign report.

Review cutoff: `da22cc6853d21cfa45fd851aa77108357f62dd7e`.
Review date: November 10, 2026 (UTC). Unless a measurement timestamp is explicitly
quoted, dates below are recorded Git **committer** dates converted to
**Asia/Karachi**. They identify commits, not inferred experiment dates, effort,
approval meetings or author activity. References use the reachable canonical
history; no historical commit is rewritten by this documentation update.

**Evidence labels:** **Git/source** means inspected committed metadata or
implementation/tests; **historical report** means a retained document's assertion,
not a fresh execution; **user report** means the available conversation supplied
the result; **NOT PROVEN** identifies missing or out-of-scope evidence. Test code
and a commit message alone do not establish that a test passed. No runtime tests
or firmware experiments were run for this documentation audit.

## September 14–21, 2026 — source analysis before target execution

**Objective and implementation (Git/source).** The initial repository was followed
by CodePulse scaffolding, C fixtures, a native GCC compiler wrapper, static
function-call checks and an analysis/compilation pipeline. The initial analyzer
matched calls to `strcpy`, `strcat`, `gets` and `sprintf` and returned line-oriented
findings. The pipeline ran analysis first, then native compilation, retaining a
structured failure if analysis or compilation failed. Native GCC compilation
was not ARM target execution.

**Failure-driven changes (Git/source).** September 18 commits removed comments,
string contents and multiline comments from the analysis path. September 19–21
changes added format-string checks, improved numeric `memcpy` reasoning and
context-aware `strcpy` checks, alongside benchmark expectations. These changes
show concrete false-positive/context-handling repairs; they do not establish
complete C parsing, sound vulnerability detection or general firmware coverage.
The project was renamed FIRMAVEX on September 19. A historical rationale for the
name or every heuristic choice was not retained.

**Validation and remaining gap.** Source/tests are retained. No independently
reviewed aggregate test transcript or original CI artifact was established for
this phase. The next execution phase addressed observable target behavior rather
than converting heuristic findings into proven runtime failures.

Sources: [initial repository](https://github.com/mtalhak003/FIRMAVEX/commit/e189416b0efedf219def144b7e1aa2044ac87fb1),
[compiler](https://github.com/mtalhak003/FIRMAVEX/commit/68a20cf5419acaad402b890a08bfc99bdb9f4eeb),
[analyzer](https://github.com/mtalhak003/FIRMAVEX/commit/3b8714d1b45f1d637fc2238db62f991c6f4df935),
[pipeline](https://github.com/mtalhak003/FIRMAVEX/commit/72cf2158cf2442e89a991d25b85119efb53eb961),
[comment repair](https://github.com/mtalhak003/FIRMAVEX/commit/2d3fffa6d7c71394bb94694cfd2dc126b6a38057),
[string repair](https://github.com/mtalhak003/FIRMAVEX/commit/9610292bca29701ee007b0867ef6543896cae04b),
[multiline repair](https://github.com/mtalhak003/FIRMAVEX/commit/3e38bf83feeee40ef3d1181ca8428eb31ced4e81),
[rename](https://github.com/mtalhak003/FIRMAVEX/commit/1381da24366da5a374e3e05b2287688269f72242),
[context-aware copy checks](https://github.com/mtalhak003/FIRMAVEX/commit/c70449eeb5c99104dd5bf522a97eb071353af4d8).

## October 3–6 — Cortex-M execution and reproducible fixture builds

The October 3–4 stages added a Cortex-M3 execution target, QEMU, GDB symbol
monitoring, configured failure detection, search, exact-input reproduction,
integer minimization and structured reporting. Their separate component
boundaries are retained in Git. The early integration tests depended on ignored,
manually built ELF images; runtime observations also needed explicit failure
propagation and per-run debugger-port isolation.

**Step 15A, October 6 (Git/source).** A shared `arm-none-eabi-gcc` builder replaced
that prebuild dependency for both old fixtures and a versioned five-condition
corpus: threshold, exact value, bounded range, bit mask and arithmetic. Shared
instrumentation exposes `firmavex_input`, `firmavex_failure` and
`benchmark_complete`; each scalar candidate lies in `0..255`. Compiler flags,
startup, linker inputs and output-safety rules are documented in the
[benchmark build contract](../../firmware/benchmarks/cortex_m/README.md).

| Failure addressed | Implemented integrity rule | Validation retained in source | Limitation |
|---|---|---|---|
| A later trigger could conceal an earlier failed observation | Search and minimization abort immediately; preserve attempted executions and candidate diagnostics | `tests/test_runtime_integrity.py` | An infrastructure failure remains distinct from a non-triggering observation |
| Independent observations shared TCP 1234 | Allocate an available loopback port and pass it to QEMU and GDB | Monitor integrity tests | A release-to-bind race remains; parallel firmware execution was not qualified |
| Compiler output could overwrite a source/linker input | Reject output aliases before compilation; replace output only after a successful build | Output-safety tests | Byte equality is tested for the same paths/toolchain, not promised across environments |
| Build metadata might reveal oracle inputs | Ground truth stays test-only, separate from the manifest/runtime build path | Corpus/oracle and search tests | Public source and symbols remain inspectable; this is not adversarial isolation |

**Validation and next step.** These are inspected source/test changes; no new
aggregate passing count is inferred. Fresh temporary builds support a clean
checkout with the required external tools. Shared startup relies on QEMU ELF
loading, not a complete physical-board initialization implementation. Step 15B
then made budgets and strategy-visible information evaluator-owned.

Sources: [execution target](https://github.com/mtalhak003/FIRMAVEX/commit/5f5c17abb22924d4c53222a807b6ff4455723b23),
[QEMU](https://github.com/mtalhak003/FIRMAVEX/commit/23aa92b619878c8615b96ce107bec4fc8c5003ad),
[GDB monitor](https://github.com/mtalhak003/FIRMAVEX/commit/d0ab65746dbfa94a73a5f12e4c2ac108357e3104),
[reporting checkpoint](https://github.com/mtalhak003/FIRMAVEX/commit/f0a92d8112a0ab242e28e7f12dbd39c8ea1febfd),
[Step 15A](https://github.com/mtalhak003/FIRMAVEX/commit/e03ff47f0f739517ae6c1b5c9db958ca756d7c8e).

## October 6 — Step 15B: evaluator authority and information separation

**Objective and design (Git/source).** Corpus v2 added eight synthetic fixtures
with a common public shape: four uint32 coordinates, each in `0..15`, or
65,536 candidate vectors per fixture. Opaque identifiers, a public immutable
description/input/feedback/result interface and administrative split/registry
data separated strategy proposals from image selection and oracle access.

The evaluator charges admission **before** dispatch and serializes admission.
Invalid API inputs and requests after exhaustion/abort do not dispatch. The first
infrastructure failure aborts the session. A valid earlier trigger stays recorded
if a later observation fails, while `aborted=True` prevents treating the overall
run as an ordinary valid search. `KeyboardInterrupt` and `SystemExit` after
admission charge the attempt, record administrator diagnostics, abort, then
re-raise the original exception; later requests return `session_aborted`.

**Validation (historical report).** The
[evaluation document](evaluation.md#validation) describes native-GCC exhaustive
oracle checks over all 256 v1 inputs and all 65,536 vectors per v2 predicate,
plus 52 declared QEMU v2 trials. Host-oracle enumeration is not exhaustive ARM
execution. Budget, malformed-result, interruption and diagnostic-separation tests
are retained in the [Step 15B commit](https://github.com/mtalhak003/FIRMAVEX/commit/944bdb52867f12e0004959a45d33febf8be1526c).

**Limitations.** The Python adapter is a cooperative information boundary, not
process isolation. Public held-out source is organizationally separated, not
secret. Small predicates do not model realistic peripheral, interrupt, timing or
large state-space behavior. Tool versions/layout and QEMU startup assumptions
remain relevant to repeatability.

## October 7–8 — from strategy callbacks to a frozen comparison

The following map identifies contract changes rather than treating each added
class as an independently validated experimental result.

| Milestone / commit date | Implementation and supported reasoning | Validation/evidence boundary | Unfinished work at that stage |
|---|---|---|---|
| [16A](https://github.com/mtalhak003/FIRMAVEX/commit/26d0e7c6aeb2e1289b01cb51849c49e9244773ad), October 7 | Common `start(description)`, `propose()` and `observe(candidate, feedback)` protocol; runner owns callback sequencing and evaluator owns counts | Strategy lifecycle/type/invalid-output tests retained; [interface contract](strategies.md) | No strategy-performance result |
| [16B](https://github.com/mtalhak003/FIRMAVEX/commit/0694e99dd46d477881c537ea697999e692f917e1), October 7 | Deterministic lexicographic enumeration, last coordinate fastest, O(width) state, reset on `start()` | Order/restart/exhaustion tests retained | Deterministic run is one repetition, not ten independent seeds |
| [16C](https://github.com/mtalhak003/FIRMAVEX/commit/aeede4d2475c81120c9afe74493fe2bd77c391f5), October 7 | Explicit private seed, lazy Fisher–Yates uniform sampling without replacement; feedback-independent baseline | Replay/global-RNG/uniqueness tests retained | Sparse state grows with explored candidates; no seed tuning established |
| [16D](https://github.com/mtalhak003/FIRMAVEX/commit/ebeb9faac1491065b9fef593b40115d4758f7af5), October 7 | Standard immutable experiment declarations/records through the existing runner/evaluator | [Record contract](experiments.md) and corresponding tests | No persistent campaign store |
| [16E](https://github.com/mtalhak003/FIRMAVEX/commit/e64d036476ca2b8607b1dc050f695e6000364f02), October 7 | Ordered campaign expansion, one enumerative run plus random seeds 0–9, per-fixture summaries and partition checks | [Frozen baseline contract](evaluation-protocol.md); tests retain aborted/invalid/censored distinctions | No mid-campaign persistence; matched numeric labels are not independent trajectories |
| [17A](https://github.com/mtalhak003/FIRMAVEX/commit/4449f6f870e695b911a742405cd44a7acce5a144), October 8 | Runtime-derived immutable signature, with no source/oracle data in feedback | [Historical report](runtime-signature.md#tested): 85 focused tests and three fresh controlled QEMU observations | Single-step overhead; equal signatures do not prove equal complete behavior |
| [17B](https://github.com/mtalhak003/FIRMAVEX/commit/d62cc715d82cf26359dc34ae96c48749bdb43403), October 8 | Signature novelty admits FIFO mutation parents; bounded single-coordinate mutation and sparse seeded fallback avoid duplicate proposals and ensure finite-domain progress | [Historical report](guided-search.md#validation-and-limits): feedback-causality/replay/exhaustion tests and two actual Cortex-M observations | No comparison, AI model, distance-to-failure metric or general superiority established |

For Steps 16A–16E, the audit establishes retained tests and contracts, not a new
aggregate passing-test transcript. The standard baseline's official JSON and
expansion order remain distinct from later custom/guided protocols. Additive
dataclass fields change generic `asdict()`/introspection; official baseline
`to_dict()`/`to_json()` compatibility does not promise unchanged dataclass layout.

**Signature boundary (Git/source).** SHA-256 uses version/domain bytes, ordered
fixed-width big-endian uint32 PCs and an explicit truncation marker. Repeated PCs
are retained; the completion PC is excluded. The final `stepi` after sample 4,096
can itself reach completion: that sequence is **untruncated**. Otherwise the
collector continues to the required completion breakpoint and marks truncation.
Timeout/error paths publish no partial signature. This precise boundary is
supported by `src/firmavex/monitor/signature.py` and collector tests; older prose
must be read with that distinction. A digest is an equality label, not semantic
distance, code coverage or AI guidance. Registered corpus executions collect it
for every strategy, so runtime overhead also applies to the baselines.

## October 8 — Step 18A: the frozen controlled protocol

**Objective and implementation (Git/source).**
[Step 18A](https://github.com/mtalhak003/FIRMAVEX/commit/d14ca9079a5d3465711e5c7cd95ba448a3da58db)
added `controlled_cortex_m_v1`, separately from `standard_baseline_protocol`.
Construction validates guided settings and retains an immutable expansion so
later default drift cannot silently change an already-created plan. See the
[full declaration](../experiments/controlled-evaluation-v1.md).

| Frozen property | Exact value |
|---|---|
| Corpus and target | Corpus v2; QEMU `mps2-an385`; input width 4, inclusive bounds `0..15` |
| Development order | `multi_variable`, `nested_branches`, `bitwise_arithmetic`, `magic_check`, `ordered_accumulator`, `compound_constraints` |
| Held-out order | `finite_state_machine`, `sparse_relation` |
| Per-fixture experiment order | Enumerative once (`seed=None`), random seeds 0–9, guided seeds 0–9 |
| Guided configuration | `archive_size=32`, `mutation_attempts=8` |
| Per-experiment evaluator budget | 256 charged attempted executions, identical for all strategies |
| Development plan | 6 fixtures × 21 runs = 126 experiments; at most 32,256 charged attempts in completed runs |
| Held-out plan | 2 fixtures × 21 runs = 42 experiments; at most 10,752 charged attempts in completed runs |
| All declared runs | 168 experiments; at most 43,008 charged attempts in completed runs |

**Failure/interpretation limit retained.** Administrative oracle inspection after
the initial freeze showed zero possible enumerative discoveries under the 256
cap across these fixtures; the earliest enumerative discovery is attempt 3,328.
This severe floor effect is a corpus/order property, not a campaign measurement.
Equal budgets equalize charged-attempt opportunity, not effectiveness across
search orders. Conditional executions-to-first-failure statistics must accompany
discovery rates and censoring; a lower conditional cost can reflect discovery of
only easier cases. No new result-dependent settings, seed selection or general
superiority conclusion follows. A higher-budget sensitivity study would require
separate predeclaration and disclosure of prior oracle exposure.

**Validation and next step.** Protocol tests retain selection, order, budget,
split and configuration-drift checks. Plan metadata declares intended provenance;
it does not independently authenticate executing source, compiler, ELF or host.
The next two steps addressed feasibility and durable recovery, not effectiveness.

## October 8–9 — Steps 18B–18C: measurement and durable accounting

| Stage | What was implemented and why | Historical validation | Limits and next step |
|---|---|---|---|
| [18B](https://github.com/mtalhak003/FIRMAVEX/commit/24c53e2a917548b3bbb3b82191783adcc7fe1325), October 8 | Predeclared bounded real-firmware pilot and opt-in provenance; distinguish actual environment/images from supplied labels; reject observable file/Git races; preserve final-inspection failure | [Report](../experiments/runtime-feasibility.md): 12 admitted successful attempts, six prescribed safe/six prescribed triggered, zero timeouts/infrastructure/cleanup failures; final hardening 103 focused and 978 complete-suite tests passed with no failures/skips | Raw external pilot archives were not independently inspected here; stable-observed capture is explicitly non-atomic and cannot defeat every race |
| [18C](https://github.com/mtalhak003/FIRMAVEX/commit/4cdedd23997aa3455585512f03bbe69b179ad887), October 9 | Durable administrator journal, ordered completed prefix, fresh attempt ownership, context binding, explicit resume/restart authorization and recovery-history export | [Report](../experiments/campaign-recovery.md#development-validation): 514 focused and 1,365 complete-suite tests passed, no failures/skips; no new real pilot or controlled campaign in that validation | POSIX advisory locks/sync are bounded claims; unknown interrupted counts remain unknown; restart can add physical work and bias eligibility if selected after outcomes |

The original 18B pilot report gives UTC timestamps
`2026-10-08T12:42:13.796746+00:00` through
`2026-10-08T12:42:25.452132+00:00`, mean attempt interval **0.950239351 s**,
and interval throughput **1.052366 attempts/s**. Its **8.51 h** development and
**11.35 h** full-plan estimates assume all 32,256/43,008 attempts occur at that
mean, excluding sustained campaign overhead. They are projections, not measured
campaign durations or confidence bounds. The fixed 0.5-second startup delay is
already included in those attempt intervals, not an extra cost to add again.
Prescribed pilot trigger vectors are not search discoveries. The original pilot
also included two held-out FSM vectors; that administrative pilot exposure is
documented and must not be hidden as a claim of untouched secret holdout data.

Recovery preserves completed experiment records without rerunning them. An
unfinished experiment requires an explicit restart from its beginning, not
mid-experiment strategy continuation. Its new evaluator result owns its own
budget, while prior known/unknown abandoned work stays in recovery history.
Charged evaluator attempts and independently verified physical guest executions
are different evidence claims. A journal hash or successful resume does not
repair missing guest-execution evidence.

## Step 19 follow-on — local preparation and preliminary analysis

**Dates and artifacts not independently established.** The available conversation
describes portable WSL preparation, launch/recovery and read-only analysis tools
at research checkpoint `4cdedd23997aa3455585512f03bbe69b179ad887`, followed by
paper-revision tools. Those transferred packages and the user's local archives
are not present as newly inspected evidence in this audit. A document filename
or conversation timestamp is not used to invent a commit or experiment date.

| Available statement | Evidence class | Permitted conclusion / unresolved gap |
|---|---|---|
| Local preparation printed six builds, 126 planned experiments, stable-observed/non-atomic provenance and zero completed experiments/dispatches | User report, retained command output in conversation | Preparation was reported validated at that point; it is not a completed campaign |
| Separate local execution/analysis later produced journal-derived tables and five figures | User report | Later journal observations were reported; no numerical strategy ranking is reconstructed here without the actual tables/archive |
| `execution_verification = failed`; supplementary evidence absent at zero-based position 7 (`multi_variable`, random seed 6) | User report and retained research restrictions | All derived findings remain **PRELIMINARY and JOURNAL-DERIVED**; the missing evidence is not repaired by plotting or journal consistency |
| Read-only analysis/paper revisions preserve original archive/backup and use separate outputs | User-reported workflow requirement | No completed experiment may be rerun or missing execution record fabricated to fill the gap |
| WSL preparation builds local ELFs and captures local tools/artifacts | User-reported package requirement, consistent with committed provenance design | Cloud-built images/tool identities cannot stand in for local execution provenance |

The six-development-fixture plan, seeds, guided settings, order and budgets remain
the frozen values above. Held-out campaign execution, hardware validation,
statistical significance, general superiority and AI-based guidance are not
established. The later Windows **Batch 27** user-reported ZIP pass is a separate
desktop evidence subject; it cannot change Step 19's failed execution-verification
status. Research-paper work was subsequently paused for desktop product work;
this audit supplies no new comparative result.

## What a future research handoff still needs

- The original plan/context/journal, exact code and ELF identities, complete
  authoritative experiment records and recovery-history export, with the
  interruption/restart policy and unknown accounting retained.
- Original supplementary execution evidence, or an explicit permanent gap at
  position 7; never infer missing bytes or relabel journal records as verified
  physical executions.
- Actual analysis code/version, input/output hashes, tables and figures before
  reviewing numerical claims. Preserve censoring, one-versus-ten replication,
  matched-seed interpretation and the enumerative floor effect.
- An independently declared next experiment if budgets, seeds, settings or data
  partitions change. Public held-out exposure and pilot access must be disclosed.

These are evidence requirements, not authorization to run a campaign. Product
milestones and runtime qualification continue in the
[primary history](../product/development-progress.md); historical debugging and
validation must remain scoped to their exact source, platform and evidence.
