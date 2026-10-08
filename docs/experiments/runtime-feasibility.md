# Step 18B runtime feasibility and provenance

This is a separately declared, administrative feasibility pilot, not the
`controlled_cortex_m_v1` campaign or a search-strategy comparison. The approved
starting revision is `d14ca9079a5d3465711e5c7cd95ba448a3da58db`. No frozen protocol,
strategy, predicate, oracle, feedback, accounting, or official result serializer
changes are part of this step.

## Predeclared pilot

The following sample was selected before executing the pilot. It uses existing
test-case inputs, including known failure triggers, solely to exercise normal
and triggering runtime paths. An administrator may inspect these fixtures;
neither these inputs nor expected outcomes are sent to a search strategy. The
held-out fixture is used for runtime feasibility only, without algorithm tuning.

| Fixture / partition | Opaque benchmark ID | Safe input | Trigger input |
| --- | --- | --- | --- |
| nested_branches / development | b-08e9f32ef15d4ef0b17b65a4c211f8e2 | (9, 5, 4, 5) | (12, 8, 4, 5) |
| ordered_accumulator / development | b-965d82f3548943c5bfb218d7e0c5351c | (7, 8, 7, 6) | (7, 8, 7, 5) |
| finite_state_machine / held_out | b-b5ba43a1f81041a28dcb6e10f0754d91 | (6, 3, 12, 8) | (6, 3, 12, 9) |

Run two identical rounds. In each round, execute nested safe, nested trigger,
ordered safe, ordered trigger, FSM safe, FSM trigger, in that order: **12 maximum
attempts**, six planned safe and six planned triggering. Each attempt uses a
fresh evaluator session with budget one, the real registry-built ARM ELF, and
the existing QEMU/GDB signature-collecting path. There is no search strategy,
adaptive candidate choice, retry, or campaign aggregation.

The driver writes the exact ordered plan before building or executing firmware.
Stop before the next attempt after the first infrastructure failure, unexpected
outcome, cleanup failure, or 60 seconds of accumulated attempt time. Interruptions
remain interruptions after partial pilot diagnostics are saved. This is an
admission limit, not a hard deadline: existing subprocess creation and final
cleanup do not have an overall wall-clock bound. Do not extend the sample if it
is unexpectedly slow.

Build the three images once before timing executions. Measure each
`session.execute(TrialInput(...))` with `time.monotonic_ns()`, including admitted
execution, ELF verification, QEMU/GDB startup, fixed sleep, signature stepping,
failure observation, and cleanup. Session creation, builds, provenance capture,
and report serialization are outside this per-attempt interval. Record their
separate timing where available. A scoped observer delegates to the real
`subprocess.Popen` and records owned processes, actual command lines, debugger
timeouts, cleanup escalations, reap outcomes, and pipe closure. Its small observer
overhead is included in measurements; no mocked measurement substitutes are used.

Keep plan, raw pilot observations, diagnostics, ELF files, and environment data
outside the repository and outside official campaign records. Generated outputs
are not source additions. Preflight and post-change regression tests are also
separate from the timing sample and must not run concurrently with it.

From the repository root, with the ARM/QEMU/GDB tools activated on `PATH`, use:

```sh
python tools/runtime_feasibility_pilot.py --output-dir /workspace/firmavex-step18b-pilot
```

The output directory must be new and outside the checkout. The read-only
`pilot-plan.json` and its SHA-256 precede firmware builds; `pilot-observations.json`
contains administrative measurements and partial observations if execution stops.
These files are separate from official campaign JSON. Writes are non-atomic;
this helper is not durable campaign storage.

The hardened driver makes measurement mode explicit. The normal CLI requests
`real_firmware`, but its report initially says `unverified`: a requested label
alone is not evidence of guest execution. Only matching successful compiler,
ARM ELF identity, QEMU/GDB dispatch, public signature, evaluator outcome, and
cleanup evidence can establish a real-firmware classification. Unit mechanics
tests explicitly select `synthetic_test`; they cannot declare their dummy images
and injected observations to be real firmware measurements. Unsupported modes
and contradictory unit-test metadata are rejected. This is a check of observed
execution evidence, not protection against forged traces or hostile Python
introspection.

Execution completion and final verification are separate report fields. A final
process-inspection failure preserves the error and completed attempt timings,
marks final verification failed, and makes the CLI exit nonzero. It cannot turn
completed executions into fully verified pilot success. Interruption handling
still preserves the original control-flow exception even if inspection or
storage also fails.

## Execution lifecycle audit

An admitted registry execution verifies the ELF digest, allocates a localhost
port, starts QEMU stopped at reset, and waits a fixed 0.5 seconds before checking
for an early process exit. A new batch GDB then connects, injects the four input
values, and installs the completion breakpoint. Startup directly calls `main`;
the current firmware relies on QEMU ELF loading for initial RAM contents rather
than an explicit `.data` copy / `.bss` initialization loop.

The collector hashes an ordered prefix of up to 4,096 program counters, retaining
repeats, and steps once after each sample. Completion immediately after the last
sample is untruncated; more execution beyond the prefix is truncated and resumes
with `continue`. The completion breakpoint remains required and its PC is
excluded. Failure is read only at completion. All registered executions, including
enumerative and random baselines, collect these signatures.

The default five-second timeout covers GDB communication, input injection,
stepping, continuation, and failure reading. It excludes ELF hashing, QEMU
startup, the fixed sleep, and QEMU cleanup; it is not an attempt deadline. GDB
is killed/reaped by `subprocess.run` on timeout. QEMU cleanup terminates and waits
up to two seconds, then kills and performs a final wait without a timeout. Pipes
are closed. A cleanup wait escalation is not itself a failure if kill/reap
succeeds. Infrastructure failures still consume the admitted slot, abort the
session, and suppress public partial signatures; administrator diagnostics stay
separate from strategy feedback.

Before measurement, suspected costs are the prescribed sleep, fresh process
launches, image/symbol loading, debugger setup, per-instruction remote stepping
and stop-event handling, repeated image hashing, and cleanup. Timing the full
attempt and GDB communication does not isolate every component or establish a
measured bottleneck.

## Measured pilot, 2026-10-08

Preflight verified the exact approved HEAD, a clean tree, local author/committer
identity `mtalhak003 <mtalhak003@gmail.com>`, and all required runtime tools.
The unchanged complete suite passed **875 tests in 152.63 seconds**. The existing
cloud tool activation was reused; no installation or Git configuration changed.
The pilot subsequently captured a dirty tree containing only the five Step 18B
additions, with no modifications to committed runtime/firmware files.

The actual plan was declared before builds and execution, with SHA-256
`e37a0250c8a59ea6a4b7c563858386704ae8c7de3f050a68e3a7b5a599d085b6`.
The recorded pilot start was `2026-10-08T12:42:13.796746+00:00` and end was
`2026-10-08T12:42:25.452132+00:00`. Raw plan, observations, compiler/QEMU/GDB
commands and working directories, environment snapshot, source hashes, and ELF
images are retained in `/workspace/firmavex-step18b-pilot/`, outside the checkout.
These local artifacts should be archived before the cloud workspace expires.
These are historical measurements from the original pilot. The integrity
hardening below does not rerun it, relabel its saved records, or replace any
plan, observations, ELF, or archive bytes. The new reporting fields apply to
future invocations; independent review checked the original execution evidence.

| Attempt | Fixture | Input | Actual outcome | Wall seconds |
| --- | --- | --- | --- | ---: |
| 1 | nested_branches | (9, 5, 4, 5) | safe | 0.831110415 |
| 2 | nested_branches | (12, 8, 4, 5) | triggered | 0.857709680 |
| 3 | ordered_accumulator | (7, 8, 7, 6) | safe | 0.993581354 |
| 4 | ordered_accumulator | (7, 8, 7, 5) | triggered | 0.996322936 |
| 5 | finite_state_machine | (6, 3, 12, 8) | safe | 1.105320122 |
| 6 | finite_state_machine | (6, 3, 12, 9) | triggered | 1.000402703 |
| 7 | nested_branches | (9, 5, 4, 5) | safe | 0.794108471 |
| 8 | nested_branches | (12, 8, 4, 5) | triggered | 0.835145748 |
| 9 | ordered_accumulator | (7, 8, 7, 6) | safe | 0.960830239 |
| 10 | ordered_accumulator | (7, 8, 7, 5) | triggered | 0.978545442 |
| 11 | finite_state_machine | (6, 3, 12, 8) | safe | 1.027069934 |
| 12 | finite_state_machine | (6, 3, 12, 9) | triggered | 1.022725173 |

All **12 admitted attempts completed successfully**: six safe and six triggered,
with **zero timeouts, infrastructure failures, cleanup failures, or cleanup
escalations**. All evaluator results recorded exactly one attempted/successful
execution, zero infrastructure failures, and `aborted=False`. All signatures
were untruncated; each of the six repeated input/signature pairs matched. These
are prescribed trigger tests, not search discoveries or a discovery rate.

Attempt timings: minimum **0.794108471 s**, median **0.986063398 s**, mean
**0.950239351 s**, maximum **1.105320122 s**. The nearest-rank sample p95 is also
**1.105320122 s**; with only 12 observations it supplies no reliable tail estimate.
The sum of execution intervals was **11.402872217 s**, yielding **1.052366
attempts/s** and the same successful-completion throughput. Overall pilot wall
time, including setup/builds/reporting up to final serialization, was
**11.656230016 s**, approximately **1.0295 attempts/s**. The three builds took
0.04144, 0.04201, and 0.04046 seconds, outside the per-attempt intervals.

Measured GDB `communicate()` intervals averaged **0.444798251 s**. The prescribed
sleep is 0.5 seconds per attempt, about 53% of the measured mean; its actual
sleep interval was not separately instrumented. These quantities indicate a
substantial fixed-delay and debugger cost but do not isolate instruction stepping
from input injection, loading, and other GDB work. A `Popen` spawn interval ends
when process creation returns; it does not measure complete tool readiness.

Every owned QEMU/GDB child had a recorded successful wait/reap and closed pipes.
The final owned-live-PID list and baseline/final runtime process snapshots were
empty. The driver's file descriptor count was four before and after. This is
evidence for this sample only; observer `poll()` can itself reap an already-dead
child on an exceptional cleanup path, and no general leak-freedom claim follows.

### Environment and firmware identities

The pilot used CPython **3.12.14**, GNU ARM GCC **14.2.1 20241119**
(`15:14.2.rel1-1`), QEMU **10.0.13** (`1:10.0.13+ds-0+deb13u1`), and GNU GDB
**16.3** (`Debian 16.3-1`). QEMU and `arm-none-eabi-gdb` use the cloud's existing
activation wrappers; their resolved paths and full version outputs are in the
raw environment record. Host: **Debian GNU/Linux 13 (trixie), x86_64, Linux
6.18.44, glibc 2.41**, five logical/affinity CPUs. Separately inspected visible
cgroup files reported `cpu.max=400000 100000` and `memory.max=34359738368` bytes;
these values do not establish exclusive host capacity or effective limits across
all ancestors. The minimal generator records CPU count/affinity, not a cgroup
resolver or host load.

Actual compiler commands used `-mcpu=cortex-m3 -mthumb -g -O0 -ffreestanding
-nostdlib -Wl,--build-id=none`, the existing linker script, startup, predicate,
and shared v2 harness. They were captured from the existing builder rather than
reimplemented. The transient `-o` path and final image path are both recorded.

| Built image | SHA-256 |
| --- | --- |
| nested_branches.elf | a75a166b52e8d471cf0ce85c436fa9d3cc823f60206e8cf873b4bbc991d180af |
| ordered_accumulator.elf | ede1ef8dda29946c81be11b87c775f2fbf8c160109eec2f1e8b3c5c5b19bd0cf |
| finite_state_machine.elf | 307d37c9655963fdf9711858d79d053e7efe440386171d65c61a320a8b96d6be |

### Projections, not campaign measurements

Assuming every planned attempt is executed serially at the pilot mean:

| Scope | Attempts | Estimated execution time |
| --- | ---: | ---: |
| One full-budget run | 256 | 243.26 s / 4.05 min |
| One benchmark, 21 runs | 5,376 | 5,108.49 s / 1.42 h |
| Six development benchmarks, 126 runs | 32,256 | 30,650.92 s / 8.51 h |
| Two held-out benchmarks, 42 runs | 10,752 | 10,216.97 s / 2.84 h |
| All eight benchmarks, 168 runs | 43,008 | 40,867.89 s / 11.35 h |

The fixed sleeps alone would contribute 21,504 seconds (**5.97 hours**) if all
43,008 attempts reach them. That is scheduling arithmetic, not an additional
measured duration to add to these already inclusive estimates.

The projections exclude build/setup/archive costs, campaign strategy proposal
work, and sustained operational overhead. Real campaigns can stop early on
discovery or abort; neither rate was measured here. The sample covers only three
fixtures and six deliberately chosen inputs, not the corpus-wide path mix or
strategies' candidate distributions. Long-host-load changes, instruction counts,
thermal/resource variation, cap continuation, and timeouts can change runtime.
Observed minimum/maximum arithmetic is not a confidence interval or guaranteed
bound. Zero errors in 12 attempts does not establish long-campaign reliability.
No strategy effectiveness or superiority conclusion follows from this pilot.

## Provenance design and limitations

The opt-in provenance module produces an administrator-owned JSON sidecar. It
does not run firmware, alter existing serializers, or automatically persist
anything. Retain the exact constructed protocol instance so its validated frozen
expansion is used; a named label alone is not proof of protocol authenticity.
Explicit image, source-input, and build-metadata mappings must cover exactly the
declared benchmark IDs. Include predicates, shared startup/harness/linker inputs,
and the corpus manifest in the source-input mapping. Build commands and flags
are supplied by the administrator, with their supplied provenance explicitly
marked; the pilot captures actual compiler arguments without duplicating build
logic.

Use `capture_campaign_manifest()` from
`src.firmavex.protocols.provenance` with the retained protocol, repository path,
declared preset name, exact-ID `firmware_images`, `source_inputs`, and
`build_metadata` mappings, actual UTC start/end timestamps, and optionally the
completed `CampaignResult`. Serialize the returned fresh dictionary with
`manifest_to_json()` and save it explicitly outside the checkout.
`capture_environment()` and `describe_artifact()` also support standalone
administrative snapshots, such as this non-campaign pilot. Tool version probes
have five-second subprocess communication timeouts; process creation is subject
to the same platform limitation as other subprocess timeouts.

Record actual Git revision, dirty status, tracked diff digest and untracked file
identities, file SHA-256 identities, compiler/QEMU/GDB versions and resolved
executables, Python, host/kernel/architecture/CPU availability, UTC start/end
timestamps, the exact expanded ordering/seeds/configurations/budgets, and existing
outcome classifications when a completed campaign result is supplied. Missing
tools and failed version probes are explicit diagnostic records rather than
fabricated versions. A partial capture with no end/result does not declare a
completed campaign. Administrative metadata never enters strategy callbacks.

Hashes and version strings identify a snapshot; they do not archive source
contents, images, dirty patches, tool binaries, package dependencies, host load,
or container/resource limits. Archive those separately before official execution.
Capture before and after execution to detect changes, because this opt-in helper
cannot lock a mutable filesystem or attest which configuration an external
caller actually ran. Full interrupt-safe campaign persistence remains outside
this step. No general reproducibility, leak-freedom, or search effectiveness
claim follows from a small pilot.

Hardened captures check observable consistency. File hashing compares requested
and resolved path identities, descriptor identity, size, mode, and nanosecond
modification/change metadata before and after reading and digest processing.
Git capture compares revision, status, tracked changes, index changes, and
untracked names/file identities across its capture interval. Successful captures
are explicitly marked `stable_observed`; a detected race raises
`ProvenanceConsistencyError` instead of returning apparently authoritative
metadata. A clean status cannot be paired with a nonempty tracked diff. There
is no automatic retry that silently substitutes another source state.

These checks do not lock files or the repository, establish an atomic filesystem
snapshot, or detect every adversarial change-and-restore race. Files can change
after a successful capture. Keep the workspace stable, archive the actual
inputs/images, and capture again after execution. Preset names and supplied
build metadata remain declarations, distinct from independently checked file
identities and observed consistency.

### Private archives and public research artifacts

Raw sidecars and pilot observations are **private administrative archives**.
They intentionally contain absolute repository/artifact/tool/Python paths,
filenames, supplied metadata, command lines, and diagnostics useful for review
and reproduction. They are not automatically safe to publish.

Before producing public research artifacts, review and redact identifying or
sensitive paths, filenames, supplied metadata, and diagnostics. Prefer relevant
relative paths or stable artifact identities where appropriate, and disclose
redactions that affect reproduction. Review diagnostic text and caller-supplied
build metadata as well as structured path fields. Preserve the unredacted
administrative archive separately; avoid accidentally attaching it wholesale to
a public report. Official strategy-facing and baseline result serializers remain
unchanged and do not acquire these administrative fields.

## Runtime recommendations and Step 18C criteria

No runtime optimization is implemented here. First consider a bounded readiness
check that cannot consume or disturb the GDB stub connection, and compare its
behavior with the existing delay. Give cleanup a bounded total deadline and
preserve both primary and cleanup diagnostics; drain unexpected QEMU stderr.
Address the port reservation race. Optimize redundant debugger work only after
demonstrating identical reset state, completion, signatures, failure reading,
and accounting for every strategy. Persistent processes or snapshot/reset reuse
need a separate reviewed design. Avoid selectively removing signatures from
baselines or changing guest instruction sampling for speed.

Before Step 18C, review the measured cost and available wall-clock allocation;
archive exact firmware/source/tool identities and the unchanged frozen plan;
define timeout/abort reporting and durable administrator-owned partial records;
confirm clean owned-process teardown; and acknowledge the existing 256-attempt
enumerative floor effect. Any runtime change needs regression and comparability
review before a campaign. A later higher-budget sensitivity experiment must be
separately predeclared, not selected from this pilot's discovery outcomes.

## Validation and review state

Before integrity hardening, the new provenance and pilot mechanics tests passed
**62 tests in 0.39 seconds**
(45 provenance, 17 pilot). Existing controlled/protocol tests passed **110 tests
in 0.19 seconds**, including frozen settings, expansion ordering, default-drift
protection, and official baseline compatibility. That complete
`python -m pytest -q` passed **937 tests in 153.53 seconds**, without failures or
skips. `git diff --check` and independent whitespace checks of all five untracked
additions passed. No generated artifacts are tracked or staged.

Only this document, the opt-in provenance module, the administrative pilot tool,
and their two test files were added. All pre-existing tracked files and the
index are unchanged. No runtime optimization, full controlled campaign, commit,
or push occurred. Remaining medium risks are extrapolation to unmeasured inputs
and sustained load, timeout/cleanup limitations, cooperative information
separation, incomplete archival/provenance authentication, and the existing
enumerative budget floor. The independent review subsequently identified
within-capture races, contradictory measurement labels, and final-inspection
status handling; the hardening targets those findings without altering saved
measurements or the execution framework.

After integrity hardening, focused provenance and pilot tests passed **103 tests
in 2.42 seconds** (65 provenance, 38 pilot). The complete
`python -m pytest -q` passed **978 tests in 155.49 seconds**, without failures or
skips. Regressions cover observable file/Git races, measurement evidence and
mode conflicts, final-only inspection failure, interruption preservation,
partition drift, and independent classifications of the six unique input
vectors. All five additions passed explicit untracked-file whitespace checks.
The saved plan, observations, ZIP archive, and three ELF digests remain unchanged;
no new pilot or controlled campaign was run during hardening.
