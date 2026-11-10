# Troubleshooting history and engineering lessons

This register explains significant failures and repairs through Batch 29; the
[primary timeline](../product/development-progress.md) records the wider sequence.
Audit source: `da22cc6853d21cfa45fd851aa77108357f62dd7e`. Review date:
November 10, 2026. No runtime tests, experiments or CI jobs were run to write this
register.

**Date basis:** dated headings below use the cited commits' recorded **committer
dates converted to Asia/Karachi**. They locate retained engineering work, not
necessarily the original failure or experiment date. A range groups repair
commits; it does not measure elapsed effort. Source inspection can confirm what
a repair changed without proving the original incident's complete cause.

**Evidence labels:** **Git/source** means inspected implementation, test or commit;
**historical report** attributes observations to a retained document; **CI
observation (historical)** means that document records an exact run/job, not that
its raw logs were downloaded again here; **user report** remains attributed.
**NOT PROVEN** identifies an unresolved requirement. Passing a test selection,
receipt verifier or candidate stage does not establish full product qualification.

## 2026-09-18 — Analyzer matches inside comments and strings

- **Symptom / evidence — Git/source:** the initial text analyzer needed to exclude
  comments and string contents before matching risky source constructs. Three
  successive repairs and their regressions are retained:
  [comments `2d3fffa`](https://github.com/mtalhak003/FIRMAVEX/commit/2d3fffa6d7c71394bb94694cfd2dc126b6a38057),
  [strings `9610292`](https://github.com/mtalhak003/FIRMAVEX/commit/9610292bca29701ee007b0867ef6543896cae04b),
  [multiline comments `3e38bf8`](https://github.com/mtalhak003/FIRMAVEX/commit/3e38bf83feeee40ef3d1181ca8428eb31ced4e81).
- **Repair / result:** lexer-like comment/string handling replaced progressively
  narrower text removal. The diffs retain test cases; an original aggregate
  passing transcript was not established in this review.
- **Lesson / limit:** negative examples belong beside positive detections. These
  heuristic matches are not proof of exploitable behavior or a complete parser.

## 2026-10-06 — Failed observations must stop search and minimization

- **Symptom / evidence — Git/source:** before Step 15A hardening, continuing after
  `success=False` could allow a later trigger to mask an infrastructure failure.
  [Step 15A `e03ff47`](https://github.com/mtalhak003/FIRMAVEX/commit/e03ff47f0f739517ae6c1b5c9db958ca756d7c8e)
  adds immediate failed-result returns to both search and integer minimization,
  preserving execution lists, candidate values and available debugger diagnostics.
- **Repair / result:** the same commit replaces TCP port 1234 with per-observation
  loopback allocation, handles launch/timeout/early-exit failures and strengthens
  termination/reaping. [Integrity tests](../../tests/test_runtime_integrity.py)
  retain regression coverage. Test presence is not a fresh runtime execution.
- **Lesson / limit:** an unavailable observation is not a safe candidate. Dynamic
  port allocation reduces cross-run collisions but leaves a port-release/handoff
  race; it is not a parallel-execution or atomic-reservation guarantee.

## 2026-10-06 — Cancellation after admission consumes an execution

- **Symptom / evidence — Git/source:** a control-flow interruption after charging
  admission must not leave a session resumable with incomplete accounting.
  [Step 15B `944bdb5`](https://github.com/mtalhak003/FIRMAVEX/commit/944bdb52867f12e0004959a45d33febf8be1526c)
  records the interrupted attempt as an infrastructure failure, marks the session
  aborted and re-raises the original `KeyboardInterrupt` or `SystemExit`.
- **Repair / result:** later execute requests return the existing aborted state
  before dispatch. Administrator diagnostics remain outside public strategy
  feedback. [Evaluator regressions](../../tests/test_evaluation.py) cover the
  interruption and post-abort behavior; see the
  [accounting contract](evaluation.md).
- **Lesson / limit:** preserve both cancellation semantics and charged accounting.
  Charged evaluator attempts do not independently establish physical guest work;
  the cooperative Python API is not an adversarial isolation boundary.

## 2026-10-08 — Signature caps, truncation and failed partial observations

- **Symptom / evidence — retained contract and tests:** sampling exactly the PC
  cap is insufficient to establish that execution continued beyond the prefix.
  [Step 17A `4449f6f`](https://github.com/mtalhak003/FIRMAVEX/commit/4449f6f870e695b911a742405cd44a7acce5a144)
  retains bounded sampling, completion synchronization, versioned hash framing and
  fake-debugger boundary regressions in
  [monitor-signature tests](../../tests/test_monitor_signature.py).
- **Repair / result:** [the signature contract](runtime-signature.md) distinguishes
  exact-cap completion from an omitted further guest PC. Completion PC is excluded,
  repeated PCs are retained, and timeout/error does not publish a partial hash to
  strategy feedback. Full-workflow test counts must be attributed to the retained
  record; this register did not rerun them.
- **Lesson / limit:** telemetry bounds need boundary semantics, not just array
  length checks. Signatures reveal a bounded execution fingerprint, not coverage
  distance, failure proximity or general search superiority.

## 2026-10-08–09 — Provenance races and stale recovery accounting

- **Symptom / evidence — Git/source and historical reports:** an apparently stable
  hash can be misleading if files or Git state change during capture. An
  interrupted new experiment can also inherit stale counters if attempt ownership
  is not fresh. [Step 18B `24c53e2`](https://github.com/mtalhak003/FIRMAVEX/commit/24c53e2a917548b3bbb3b82191783adcc7fe1325)
  and [Step 18C `4cdedd2`](https://github.com/mtalhak003/FIRMAVEX/commit/4cdedd23997aa3455585512f03bbe69b179ad887)
  retain the checks and tests for these concerns.
- **Repair / result:** [provenance](../experiments/runtime-feasibility.md) checks
  observed file/Git consistency and labels successful capture `atomic=False`;
  synthetic measurements cannot be labeled real firmware from a caller's label
  alone. [Durable recovery](../experiments/campaign-recovery.md) associates partial
  counters with the current attempt, validates journal positions, preserves
  original cancellation and exports unknown abandoned accounting explicitly.
- **Lesson / limit:** race detection is not a locked filesystem snapshot. Recovery
  must preserve completed records and disclose restarted/unknown work; a journal
  history alone is not independent proof of firmware execution.

## 2026-10-12 — Native metadata and process-disappearance races

- **Symptom / evidence — historical report:**
  [Batch 2 validation](../product/batch2-validation.md) records mismatched Windows
  `stat`/`fstat` metadata in initial native checks.
  [Batch 3 validation](../product/batch3-validation.md) records a Linux procfs
  `ESRCH` while a descendant disappeared, causing regression run `38277517111`
  to fail.
- **Repair / result — Git/source:**
  [native Windows metadata `84c0561`](https://github.com/mtalhak003/FIRMAVEX/commit/84c0561f7798ffc45096a9df6da40cd6129dd3e8)
  uses comparable Win32 metadata sources;
  [procfs cleanup `ebde3da`](https://github.com/mtalhak003/FIRMAVEX/commit/ebde3da5f0decde180ead4660ca2c75cedda8c96)
  accepts only ENOENT/ESRCH as disappearance, preserving permission/live-process
  failures. The later Batch 3 report records successful runs separately.
- **Lesson / limit:** compare the same native identity semantics and distinguish
  disappearance from inspection denial. A repair commit alone does not prove
  that every process-cleanup failure had that cause.

## 2026-10-12 — GDB version probe inherited the worker command stream

- **Symptom / evidence — historical report:** Batch 3's integrated Windows probe
  timed out at GDB `--version` inside the supervisor. Probes and uncancelled
  compilation inherited command-channel stdin.
- **Repair / result — Git/source and historical CI observation:**
  [`bb77217`](https://github.com/mtalhak003/FIRMAVEX/commit/bb77217d6d254d3c231723213f3b895a4ad4372c)
  supplies `DEVNULL` to those tool subprocesses instead of extending timeouts.
  [Batch 3's final record](../product/batch3-validation.md#final-observed-ci-result)
  attributes passing distribution run `38282319695` and seven-job regression run
  `38282319967` to this exact revision. Original receipts/logs were not reread for
  this register.
- **Lesson / limit:** inherited standard streams are part of subprocess ownership.
  Low-level QEMU success does not establish that supervised/frozen product paths
  preserve their command protocol.

## 2026-10-13 — Beta packaging, cleanup and repeated preflight costs

- **Symptom / evidence — historical report:** [Batch 4](../product/batch4.md)
  retains CRLF source-hash differences, case-insensitive packaged-worker selection,
  oversized vendor snapshots, read-only files/private GPG agents, Qt shutdown
  aborts, repeated ctypes setup and redundant generation hashing.
- **Repair / result — Git/source:**
  [checkout/worker selection `e48d867`](https://github.com/mtalhak003/FIRMAVEX/commit/e48d867ac6dabf5a9100ef018c13d22b4534d5a3),
  [private cleanup `90d154f`](https://github.com/mtalhak003/FIRMAVEX/commit/90d154f136f1b5b58bddd73019bb40c50da166c3),
  [explicit shutdown/verification `f29195f`](https://github.com/mtalhak003/FIRMAVEX/commit/f29195fd723d2a871f854e79881ce04eb3eb4434),
  [metadata bindings `adc7720`](https://github.com/mtalhak003/FIRMAVEX/commit/adc7720235562529b6e2ab38204d121c6bd9ea6b),
  and [missing-completion initialization `9aadba8`](https://github.com/mtalhak003/FIRMAVEX/commit/9aadba8b20db522cc6e78fc6e1da723493a7e250)
  retain scoped fixes. The report records later native outcomes and beta limits.
- **Lesson / limit:** improve the lifecycle and measurement boundary while keeping
  missing-completion assertions, integrity checks and cleanup failures visible.
  An unsigned development installer remains unsigned after functional tests pass.

## 2026-10-14 — Native contracts and macOS memory admission

- **Symptom / evidence — historical report:** initial universal tests exposed
  inherited-limit handling, Windows artifact/capture behavior and HDL line-ending
  differences. [Inherited limits `a4a2932`](https://github.com/mtalhak003/FIRMAVEX/commit/a4a293271fe3e08afe41ca425bbb1457cce569e8),
  [Windows capture `86c8184`](https://github.com/mtalhak003/FIRMAVEX/commit/86c81846e20b9b66ffb242a51b7da407f1907910)
  and [HDL lines `3dfc028`](https://github.com/mtalhak003/FIRMAVEX/commit/3dfc028110b9a64fcc7ddc33cc5a7876b3581bc7)
  retain distinct repairs rather than a blanket relaxation.
- **Unresolved cause / evidence:**
  [the macOS investigation](../product/macos-memory-admission.md) records a Python
  virtual map of 420,837,490,688 bytes versus requested 128 MiB/2 GiB AS caps.
  XNU rejects lowering the map limit below its current size. The independent small
  C helper still mapped roughly 420 GB virtually; nano-off did not solve admission.
  Mach footprint returned `KERN_NO_ACCESS`; memorystatus returned `EPERM`.
  Virtual reservation must not be called resident RAM consumption.
- **Result / limit — historical CI observations:** native probe jobs and
  [`0d3011a`](https://github.com/mtalhak003/FIRMAVEX/commit/0d3011abbe2f6b9b1b758d067ad7bb566f81ac66)
  retain the failure. macOS remains **desktop preview; native unified execution
  unsupported**. A small launcher or supervisor alone adds no alternative hard
  memory ceiling. Historical ARM-only passes/DMG startup do not remove this block.
- **Lesson:** narrow platform support when a required control cannot be qualified;
  do not enlarge caps, substitute polling or call process supervision a sandbox.

## 2026-10-14–17 — Windows CI stalls and oversized diagnostic identities

- **Symptom / evidence:** run `38601295586` was cancelled with incomplete Windows
  jobs. Earlier raw logs were unavailable. A cancelled overall run alone cannot
  establish a deadlock, GitHub concurrency issue or the detailed cause of each job.
- **Repairs — Git/source:**
  [bounded diagnostics `18e9cc5`](https://github.com/mtalhak003/FIRMAVEX/commit/18e9cc5c98ca8f28887f0d31347c0ddbb2fcf837)
  adds per-test/collection/shutdown liveness and owned cleanup;
  [file-based output `e89d5d1`](https://github.com/mtalhak003/FIRMAVEX/commit/e89d5d158c9b976f4647dfae6c7ce36e15ec222c)
  removes reliance on console-forwarder pipe EOF. These changes improve failure
  localization; their existence is not proof that every original stall was pipe
  deadlock.
- **Separately identified defect — historical report/source:**
  [CI diagnostics](../product/ci-diagnostics.md) records a 1,048,659-character
  pytest node ID for an unchanged 1,048,577-byte malformed frame and a rejected
  1,069 KiB step summary. Windows environment limits affect `PYTEST_CURRENT_TEST`.
  [`1793d9a`](https://github.com/mtalhak003/FIRMAVEX/commit/1793d9abbacd84db582a0c81a9df999ef52be21a)
  uses short parameter IDs and bounded public labels with digest suffixes; full
  payloads/assertions remain. The original raw Windows exception was not recovered
  from the truncated annotation.
- **Lesson / limit:** bound diagnostic identities independently of adversarial
  payload size. Watchdog exit is failure, absent JUnit is not a pass, and missing
  logs leave causal uncertainty even after plausible defects are repaired.

## 2026-10-17 — Installer completion is a process-tree property

- **Symptom / evidence — Git/source and historical report:** Windows uninstall
  transition checks needed retained exit codes and full owned Inno descendant
  completion, not merely waiting for the initial launcher.
  [Exit diagnostics `025161b`](https://github.com/mtalhak003/FIRMAVEX/commit/025161bdd9e6a4c7ae931b709d7abd1fa7e3a12d)
  and [owned-tree waiter `b56400e`](https://github.com/mtalhak003/FIRMAVEX/commit/b56400e48f6f2025435ef70e17a794a0c652d779)
  retain the corrections and [installer tests](../../tests/product/test_versioned_install_ci.py).
- **Result / limit:** [Batch 11](../product/batch11-release-evidence.md) records
  native qualification requirements; [Batch 27](../product/batch27-qualification-closure.md)
  later adds owned lifecycle evidence. Same-package reinstall/sentinel preservation
  is narrower than a distinct-version upgrade preserving authoritative run data.
- **Lesson:** wait for owned effects and test the exact transition being claimed.
  A failed interruption before uninstaller creation may leave a partial
  disposable installation; this cannot be reported as successful rollback.

## 2026-10-19–21 — Linux namespace policy blocked aggregate isolation

- **Symptom / evidence — historical CI observations:**
  [Batch 11's follow-up](../product/batch11-release-evidence.md#hosted-follow-up-and-python-314-regression)
  records successful CPU/process/memory checks but `RTM_NEWADDR: Operation not
  permitted` in the namespace phase, with cleanup retained. Separate diagnostics
  recorded AppArmor `unprivileged_userns` denials for `setpcap` and `net_admin`.
- **Repair / result:** [`72fe794`](https://github.com/mtalhak003/FIRMAVEX/commit/72fe794ec391f85ca432ac75110c627a5e267289)
  retains the denial and makes buffered file-size regression failure deterministic
  by closing the stream explicitly. The
  [review package `b8dd215`](https://github.com/mtalhak003/FIRMAVEX/commit/b8dd215b47ae4293417431cbea28f37b2e4fa4c1)
  records an **inactive, incomplete, unapproved** AppArmor draft and unresolved
  invocation/identity/descriptor/capability/transition questions.
- **Lesson / limit:** positive resource checks do not qualify namespace isolation.
  A policy-denial diagnosis is not authorization to weaken host protections.
  The [Linux review](../security/linux-isolation-review/README.md) remains a review
  of a proposed direction, not a working hostile-workload sandbox.

## 2026-10-21 — Original process handles and destination aliases

- **Symptom / evidence — Git/source:** PID-based reinspection can lose the exact
  child identity needed to establish cleanup; report destination aliases can
  evade simple archive-prefix checks.
- **Repair / result:**
  [original-handle termination `b967c1b`](https://github.com/mtalhak003/FIRMAVEX/commit/b967c1ba2ca07fe337619e75c47c191af186c20d)
  retains native Windows process identity checks and regression coverage;
  [destination aliases `34e3c5e`](https://github.com/mtalhak003/FIRMAVEX/commit/34e3c5e9f0e13d4dbbb0be9c76ba033fe39b745d)
  rejects alternate spellings that would write through an archive path.
  [Verification-report limits](../product/batch16-verification-reporting.md)
  retain the scope of those exports.
- **Lesson / limit:** textual path/PID equality is not physical identity. These
  checks detect supported alias cases; they do not establish atomic snapshots or
  adversarial sandbox isolation.

## 2026-10-24 — A second oversized pytest ID and deep Windows working directories

- **Confirmed distinct incidents — historical report:**
  [Batch 20's repair record](../product/batch20-windows-repair.md) identifies a
  131,073-byte malformed-session parameter that overflowed Windows environment
  limits during test setup/teardown. Short IDs preserve the payload/assertions;
  the report attributes passing Windows 3.11/3.12 jobs to run `40022757709` at
  [`c7050f4`](https://github.com/mtalhak003/FIRMAVEX/commit/c7050f40de2de36681cd4dc916fe5a4fe4a4752a).
- **Separate runtime cause:** diagnostic run `40022757696` independently recorded
  `WinError 267` for both RV32 and Verilog at 286-character execution directories.
  Python could access those directories while native `CreateProcessW` cwd failed.
  Harmless local Windows child probes corroborated the path behavior; they were
  not firmware qualification.
- **Repair / result — Git/source:**
  [`d474fab`](https://github.com/mtalhak003/FIRMAVEX/commit/d474fab63500e6a2e726caf77c207060efecaa55)
  uses an existing short spelling only after same-directory and security checks;
  unsupported volumes fail closed and recommend shorter storage paths.
  [Native-path regressions](../../tests/backends/test_native_paths.py) preserve
  rejection cases. The repair report's local Linux counts do not establish a
  post-fix Windows end-to-end pass.
- **Lesson:** separately diagnose errors sharing a symptom, and distinguish
  collection/host-launcher defects from guest outcomes.

## 2026-11-07 — Rolling Windows packages no longer matched the qualified runtime

- **Symptom / evidence — operator-supplied result retained in the historical
  [acquisition investigation](../product/batch23-acquisition-investigation.md):**
  run `42279061789` acquired QEMU package `11.1.3-1`/executable `11.1.3`, whereas
  production requires `11.1.2` and its different SHA-256. GDB `18.1-3` matched.
  This register did not independently retrieve that diagnostic artifact.
- **Repair / result:**
  [diagnostics `88ef1e1`](https://github.com/mtalhak003/FIRMAVEX/commit/88ef1e1f9f6dbb773f43dc30918fa6f9a16d16ef)
  persist sanitized expected/observed versions/hashes before private vendor
  cleanup. [The diagnostic contract](../product/batch23-runtime-diagnostics.md)
  explicitly retains the inherited GPG-agent-cleanup interruption limitation.
  Batch 23C established no independently verifiable immutable older package set;
  publisher proxy denials do not prove that no such set exists.
- **Lesson / limit:** a pinned bootstrap does not freeze rolling package results.
  Preserve rejection, earlier valid generations and diagnostics; do not downgrade
  one binary into incompatible current dependencies or silently approve a new hash.

## 2026-11-07–08 — Candidate preflight compatibility without production bypass

The [candidate contract](../product/batch23-runtime-candidate.md) and scoped diffs
retain the following repairs. Dates locate those commits, not every referenced
run. No row authorizes candidate production admission.

| Symptom / evidence | Minimal repair and safeguard | Remaining uncertainty / lesson |
|---|---|---|
| GitHub rejected job-level `runner.temp` expressions before jobs | [Valid path context `60d9e63`](https://github.com/mtalhak003/FIRMAVEX/commit/60d9e639a643e596860de75f8b5d014785c75d0d) changes workflow initialization | YAML acceptance is not native test success; use contexts valid at their evaluation stage. |
| Successful empty repository `pacman-conf SigLevel` was rejected | [Inherited policy `012adeb`](https://github.com/mtalhak003/FIRMAVEX/commit/012adeb1662bacf869bc48e38667061393a2f3a1) falls back only for successful whitespace/empty output | Failed queries and explicit weak policy still fail; both `PackageRequired` and `PackageTrustedOnly` remain mandatory. |
| Valid case-sensitive `pacman -Q` names rejected | [Inventory parser `2e9a35f`](https://github.com/mtalhak003/FIRMAVEX/commit/2e9a35f7868560d09cc1426bb7d880cf9cdb9eb3) accepts the supported vendor spelling | Malformed and duplicate entries remain rejected; do not infer which original entry failed without its retained evidence. |
| Publisher regular hardlinks failed the strict input-file check | [Closed groups `2c1d335`](https://github.com/mtalhak003/FIRMAVEX/commit/2c1d335bdbccfa3eb8a340005d74d2c4f93f4272) inventories every alias and rejects outside/ambiguous groups | Exact rejected entry in run `42420701603` was unavailable in the report; publisher layout evidence is narrower than that missing trace. Shared product path validation is unchanged. |
| CI launcher could not import installed `firmavex` after MSYS2 PATH changes | [Pinned interpreter/module launch `e27456c`](https://github.com/mtalhak003/FIRMAVEX/commit/e27456c297d6aacb4365005347b6afdf944f70bb) uses setup-Python's exact executable and `-m` | Addresses interpreter drift and direct-script import-path assumptions without a global path/admission bypass. |
| Existing output directory was validated as a regular file | [Directory validation `237e9f6`](https://github.com/mtalhak003/FIRMAVEX/commit/237e9f64352d1aac7105f7461db5d76dacf57612) checks both existing/new directory paths | Link/reparse/special-file and unsafe-parent rejection remain; shared `checked_path` is not weakened. |

The previously recorded successful source-stage run `42505041359` is evidence
for its candidate revision and selected checks only. Rolling signed acquisition
still does not supply an immutable distributable dependency closure. The
[candidate tests](../../tests/product/test_windows_runtime_candidate.py) are
partly synthetic locally; native-only selections require their explicit workflow.

## 2026-11-09 — Evidence access, receipt consistency and installer claim boundaries

- **Symptom / evidence — historical reports:** missing/forbidden artifact access
  and inconsistent artifact listings prevented some independent original-ZIP
  inspections. Neither public success badges nor displayed digests supply missing
  receipt bytes. [Batch 25 `8c4a6fa`](https://github.com/mtalhak003/FIRMAVEX/commit/8c4a6fa7d8611a93eb717b3231b84a6a5ff79dfe),
  [26 `43f932a`](https://github.com/mtalhak003/FIRMAVEX/commit/43f932a2f8fa1c34762ae8088a427b328ee6fc54),
  [27 `c42cdd0`](https://github.com/mtalhak003/FIRMAVEX/commit/c42cdd000dbd117dee558fd346aa8b653ac7bf3f)
  and [28 `66fba9b`](https://github.com/mtalhak003/FIRMAVEX/commit/66fba9b9a339b300a57df0974487d675bdc9ea8c)
  progressively bind original ZIP metadata, receipts, JUnit cases, installed
  lifecycle and static PE import evidence.
- **Result / evidence classes:** the existing history records native run
  `42618949135` as successful for source/resource and normal source/GUI/frozen/
  installed **admission rejection**, plus narrow lifecycle checks. The user reports
  original artifact `13675538108` passed with **19 receipts, 97 JUnit passed,
  10 skipped, zero failures/errors** and SHA-256
  `f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`.
  The original ZIP was not independently reviewed for this register.
- **Lesson / limit:** a consistent archive is not independent publisher trust;
  a static import inventory is not complete dynamic DLL closure; negative
  admission tests are not positive application execution. Keep authentic signed
  archives/independent keys, package-to-installed ownership, license/source duties,
  consumer acceptance and explicit profile approval as separate open requirements.
  See the [Batch 28 matrix](../product/batch28-release-readiness.md).

## 2026-11-10 — Batch 29 truthful export and GUI regression boundaries

- **Symptom / evidence — retained local validation report:** local export-start/
  destination failures could leave earlier success feedback visible; malformed
  worker replies needed explicit presentation validation. New GUI tests initially
  also assumed temporary Qt menu wrappers stayed alive, wait predicates could
  return lists and signal dictionaries retained Python object identity.
- **Repair / result:**
  [implementation `feb1fab`](https://github.com/mtalhak003/FIRMAVEX/commit/feb1fab8b65d3626a4389a2cc1424cd8f352d01f)
  clears stale status before admission/local validation and confirms the actual
  requested destination and required file/hash fields. Tests use a retained menu,
  bounded boolean/event waits and content equality. The
  [Batch 29 guide](../product/batch29-desktop-workflows.md#validation-performed)
  records **143 new tests passed**, **389 desktop/recent tests passed with
  16 skipped**, and final available-environment regressions **2,080 passed,
  106 skipped, 6 deselected**, with one integration test excluded.
- **Preserved failure:** an earlier unfiltered run had **2,079 passed,
  106 skipped, 1 failed and 6 errors** because ARM GCC was absent. Existing tests
  were unchanged; explicit exclusions are documented, not a complete-suite pass.
  Real worker export tests use explicitly synthetic saved records and do not run
  firmware. Native Windows validation of this revision remains NOT PROVEN.
- **Lesson:** presentation must reflect confirmed outcomes and expose uncertainty.
  A successful stale label, synthetic transport test or filtered suite cannot
  stand in for a completed export or unavailable native execution evidence.

## Applying the lessons to future work

1. Record the symptom, exact source/run/attempt and accessible evidence before
   asserting a cause. Keep hypotheses and inaccessible evidence explicit.
2. Preserve input payloads, security gates and failure assertions while repairing
   harnesses or platform normalization. Add the smallest regression that would
   have caught the actual defect.
3. Capture diagnostics before private cleanup, bound public output and retain
   original interruption/failed accounting. Unknown work remains unknown.
4. Require the exact platform, runtime identities and application path for each
   support claim. Keep simulated, synthetic, host-only and guest evidence distinct.
5. Retain the failed run beside later scoped successes. Use the
   [milestone template](milestone-template.md) and
   [history maintenance procedure](history-maintenance.md); never replace absent
   original evidence with reconstructed results.
