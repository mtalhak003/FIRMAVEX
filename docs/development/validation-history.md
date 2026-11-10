# Testing, CI and qualification history

This register explains **how the evidence boundary developed**, rather than
repeating the [primary milestone timeline](../product/development-progress.md).
Review baseline: `da22cc6853d21cfa45fd851aa77108357f62dd7e`; review date:
November 10, 2026 (UTC). Dates below are recorded Git **committer dates converted
to Asia/Karachi**, not inferred dates of test execution. A report can describe an
earlier run than the commit that records it.

Source/test/workflow inspection in this documentation audit is independent local
inspection. Numerical results below are **attributed historical reports**, not
tests rerun by this audit. Earlier public Actions observations retain that scope;
their original logs, archives and JUnit were not newly retrieved here. User reports
remain separate. Overlapping selections must not be summed, and counts at
different revisions do not form a comparable performance series.

## 2026-10-11–13 — Batches 1–4: from unit tests to real desktop journeys

The product foundation at
[`d0a42c79fd20172184135d1ccf6d2ab8907a7c69`](https://github.com/mtalhak003/FIRMAVEX/commit/d0a42c79fd20172184135d1ccf6d2ab8907a7c69)
added a supervised worker, immutable command configuration, SQLite persistence,
bounded execution/reproduction and explicit evidence classification. The Qt
application followed in
[`406dfe0f3e1e26689869951e69b4b01ba486b119`](https://github.com/mtalhak003/FIRMAVEX/commit/406dfe0f3e1e26689869951e69b4b01ba486b119).
This made package installation, GUI event-loop responsiveness and child cleanup
separate test subjects, rather than assuming a Python API pass established a
usable installed application.

| Record | Retained result and scope | Failure/remaining boundary |
|---|---|---|
| [Batch 1 validation](../product/validation.md) | Final product selection 397 passed; complete suite 1,762 passed, no skips. Real Linux ARM example search/reproduction, not just injected executor tests. | Native Windows dispatch was blocked at that stage. These are historical Linux results, not current-commit tests. |
| [Batch 2 validation](../product/batch2-validation.md) | Desktop/product 546 passed, 4 skipped; complete suite 1,911 passed, 4 skipped. Real Qt/controller/worker/ARM workflow, cancellation and archive export; native host-process and installed-package tests in [run 38255127322](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38255127322) at `84c0561f7798ffc45096a9df6da40cd6129dd3e8`. | Batch 1 CI failure remains in the record; local Python 3.11 reproduction does not erase it. Host GUI/ownership passes did not qualify Windows/macOS firmware. |
| [Batch 3 validation](../product/batch3-validation.md) | Complete local suite 1,967 passed, 4 skipped. At `bb77217d6d254d3c231723213f3b895a4ad4372c`, recorded [distribution 38282319695](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38282319695) and [regression 38282319967](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38282319967) passed the declared native example scopes. | A vanished procfs process and tool stdin consuming the worker command channel required repairs. Windows/macOS ARM passes apply to exact tools and examples; they do not qualify arbitrary firmware or signed installers. |
| [Batch 4 record](../product/batch4.md) | Complete local suite 2,022 passed, 4 skipped. Recorded source/GUI/frozen/installed compiler-free journeys at `11b93dcab5726e372b5ce3eb2c741a7f817cfc04`; regression [38414421922](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414421922), distribution [38414422195](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414422195), setup [38414422220](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414422220). | CRLF identities, worker selection, vendor snapshot bounds and Qt shutdown required repairs. Hosted-runner reinstall/sentinel tests are narrower than consumer acceptance, cross-version migration or WSLg qualification. |

The relevant retained tests include
[real desktop ARM flow](../../tests/desktop/test_real_firmware.py),
[bundled example](../../tests/desktop/test_real_builtin.py),
[runtime synchronization](../../tests/product/test_runtime.py),
[supervision](../../tests/product/test_supervisor.py) and
[installed packaging](../../tests/product/test_packaging.py).
Their existence is source evidence; a native pass requires the actual tool/test
record. Charged evaluator attempts are not automatically independently verified
physical guest executions or hardware observations.

## 2026-10-14 — Batches 5–6: qualify each backend and execution path

[`a9810669277dad8f531f2410f40c4638d610b0f7`](https://github.com/mtalhak003/FIRMAVEX/commit/a9810669277dad8f531f2410f40c4638d610b0f7)
introduced the backend foundation; its ARM adapter repair
[`d49a85ebbefc53f76564fa5d2ae7f8e80ffc4632`](https://github.com/mtalhak003/FIRMAVEX/commit/d49a85ebbefc53f76564fa5d2ae7f8e80ffc4632)
added explicit tests preserving authoritative legacy outcomes, trigger vectors
and infrastructure aborts. Generic success could not replace evaluator-owned
accounting. See the [backend contract and measured local pilot](../product/universal-backends.md).

The methods have deliberately different evidence requirements:

| Profile | Meaningful execution observation | Unsupported inference |
|---|---|---|
| ARM Cortex-M3 / `mps2-an385` | Ready breakpoint, input injection/readback, required completion, configured failure observation; bounded search and exact-vector replay. | Arbitrary MCU/peripheral support, BIN images, vulnerability proof or hardware qualification. |
| RV32IM / QEMU `virt` | Typed two-uint32 inputs, ready/completion symbols, safe/triggering observation and fresh replay. | Automatic RV32 search, arbitrary RISC-V board compatibility or ARM-style signatures. |
| Verilog / Icarus | Real compile/simulation, exactly one accepted PASS/FAIL marker, bounded logs and supported VCD. | Independent verification of a testbench's assertions, VHDL, synthesis or physical FPGA validation. |

The unified GUI/frozen launcher change
[`c8478ce65af073e817994643afc885bd8a2a8f98`](https://github.com/mtalhak003/FIRMAVEX/commit/c8478ce65af073e817994643afc885bd8a2a8f98)
extended native qualification beyond source adapters. The
[unified record](../product/unified-desktop.md) attributes Ubuntu source/frozen/
installed ARM/RV32/HDL passes to [38546993532](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38546993532).
Windows subsequently required path/metadata and HDL-newline corrections. Its
later matching-runtime scope is retained separately; a failed overall macOS
matrix must not be called green because Windows passed.

Apple Silicon resource admission failed before dispatch. The
[native memory investigation](../product/macos-memory-admission.md), retained in
[`0d3011abbe2f6b9b1b758d067ad7bb566f81ac66`](https://github.com/mtalhak003/FIRMAVEX/commit/0d3011abbe2f6b9b1b758d067ad7bb566f81ac66),
keeps unified execution unsupported/preview-only. Earlier ARM-only macOS example
passes are not transferable to the new resource contract. The tests remain in
[backend security](../../tests/backends/test_process_security.py) and
[real unified GUI journeys](../../tests/desktop/test_real_universal.py).

## 2026-10-14–20 — Batches 7–11: liveness, build lineage and installer evidence

This phase expanded what CI could diagnose and what a release claim must prove:

| Engineering layer | Implemented check and retained evidence | What remains distinct |
|---|---|---|
| Test liveness | [CI diagnostic protocol](../product/ci-diagnostics.md): collection/setup/call/teardown/shutdown bounds, owned output files, retained JUnit/logs and short parameter IDs. Repair `1793d9abbacd84db582a0c81a9df999ef52be21a` preserves the full malformed-frame payload. | A watchdog exit or missing JUnit is failure/incomplete evidence, not a passing partial selection. The original truncated Windows exception cannot be reconstructed. |
| Release integrity and build inputs | [Batch 8](../product/batch8-release-readiness.md) and [Batch 9](../product/batch9-public-beta-hardening.md): hash-bound sidecars, scoped Python SPDX inventory, pinned Actions/build inputs and collected-file hashes. | Dependency identities are not complete native composition, publisher authenticity, license clearance or bit-identical reproducibility. |
| Genuine installer transitions | [Batch 10](../product/batch10-release-blockers.md), implementation `bba2958dc9260dd64c8fde802131f7cb7aa76070`: real baseline `19cd45736337243c64a2298285781a27499981fa` versus candidate; owned Windows uninstall-tree waiting, Ubuntu unpack/configure recovery and isolated ENOSPC design. | Workflow definitions describe enforced assertions, not proof all transitions passed. Same-build reinstall differs from a distinct-version upgrade; a selected interruption point differs from arbitrary power loss. |
| External review and isolation diagnostics | [Batch 11](../product/batch11-release-evidence.md), implementation `7965ac72907054130ca0e31fa56fdcdf71819744`: exact-manifest signed review and diagnostic evidence. Recorded local 750 passed/4 skipped plus separate 31 focused checks. | Ephemeral test keys are not publisher trust. Hosted quota observations with a failed namespace boundary do not qualify hostile execution. |

Recorded [aggregate run 39303862786](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862786)
retained quota observations and failed Bubblewrap loopback setup; the separate
[component/diagnostic run 39303862810](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862810)
retained AppArmor denials. Passing diagnostics can accurately describe a blocked
mechanism. No consumer signing, authentic external review or hostile-workload
sandbox is established by those observations.

Current source definitions remain separable:
[product matrix](../../.github/workflows/product.yml),
[native unified paths](../../.github/workflows/unified-desktop.yml),
[distribution](../../.github/workflows/desktop-distribution.yml),
[versioned installers](../../.github/workflows/versioned-install.yml),
[release evidence](../../.github/workflows/release-evidence.yml) and
[aggregate isolation](../../.github/workflows/aggregate-isolation.yml).
The product matrix contains six OS/Python host jobs and one Ubuntu actual-ARM/
research job. It is not the same matrix as native backend qualification. Runtime-
required flags make missing tools fail in the equipped qualification jobs;
optional local skips cannot replace that evidence.

## 2026-10-21–2026-11-06 — Batches 12–22: scope saved-result review precisely

The evidence progression here concerns the **meaning of inspection and
verification**, not new processor support. The following map exposes both
retained coverage and missing aggregate transcripts. Dates are commit dates.

| Date / batch / implementation | Contract and regression target | Historical validation and remaining gap |
|---|---|---|
| Oct 21 / 12 / `06405c959a27e8fd6b0dd287f6c877d65a0a6a82` | [Action guidance](../product/batch12-usability.md): explain disabled Run, consent and selected-result context while administrative operations run. | Document describes Qt/product coverage; no exact aggregate count retained there. |
| Oct 21 / 13 / `fa416e0b838f5d8a98ffb7da030d1b89564826d6` | [Recent projects and read-only review](../product/batch13-review.md); shortcuts, histories and comparison reuse saved records. | Source/test coverage is available; preferences are not an execution ledger, and comparison does not replay. |
| Oct 21 / 14 / `0a3fca3a0a38319574d4e8e803bffc09dbb1d32a` | [Mixed archive comparison and integrity scope](../product/batch14-history.md): actual nonempty listed-file hash/size checks required for `verified`. | No aggregate count retained in the report. Shared ARM wrapper inspection does not imply nested receipt verification. |
| Oct 21 / 15 / `b08288658037f86136d8afafcd2e22bf8c85277b` | [Cancellable worker verification](../product/batch15-verification.md), final consistency errors fail; session preview must not overwrite execution logs. | Reported CI statements remain historical assertions here. No exact aggregate count is supplied by this report. |
| Oct 21 / 16 / `0a097c89201d3949d238a928fe714860166dbc30` | [Observation provenance and bounded reports](../product/batch16-verification-reporting.md); original archive unchanged, metadata freshness separate from fresh hashing. | A session report is unsigned observation, not persistent evidence authenticity; no aggregate count retained there. |
| Oct 22 / 17 / `96ab00b27b8720512f116ef8e1145a0d9599dda1` | [Custom project snapshots](../product/batch17-custom-workflow.md): explicit handoff, new-build identity, named RV32/HDL revisions, static preflight. | Native and synthetic seams are distinguished in that report; opening/preflighting never substitutes for execution. |
| Oct 23 / 18 / `ca8a30ca566043352e5d14ecde27760c36be6081` | [Bounded diagnosis/comparison](../product/batch18-diagnosis.md); retained facts and unknown stages stay distinct. | Reported product/desktop 1,153 passed/13 skipped and final focused 266 passed; local Linux scope, not new-commit native CI. |
| Oct 24 / 19 / `3d9ffcb5cc0ef1c9b91796d7cab9a0835d389ec3` | [Explicit RV32/HDL test sets](../product/batch19-regression-workflows.md): pinned revisions, consent, sequential admissions and partial summaries. | Reported product/desktop 1,215 passed/7 skipped; backend 215 passed/9 skipped; final focused 256 passed. These overlap. Research Step 19 is a different milestone. |
| Oct 24 / 20 / `c077ee71cb093be55566ee478f530a92f65f38a0` | [Dashboard/aggregate verification](../product/batch20-regression-review.md): bounded retained-input/artifact reads and fresh export verification. | Reported product/desktop 1,245 passed/7 skipped; backend 215 passed/9 skipped; focused 215 passed/1 skipped. A transient 300-ms deadline failure remains documented separately from the later passing rerun. |
| Oct 24 / 21 / `bc556923b37f8d4641f95f820a89ac936afda60b` | [Backend acceptance matrix](../product/batch21-acceptance.md): real imports, saved-result preservation, regression context and cancellation. | Reported final product/desktop 1,270 passed/7 skipped; backend rerun 224 passed/9 skipped; all 13 native Qt tests passed. Earlier restricted-agent and RV32 snapshot timing failures remain in the report. |
| Nov 6 / 22 / `be5cdb97b8b7fba8bda6601d09866445d6eefc3d` | [Explicit individual retained-input verification](../product/batch22-verification-consistency.md): opt-in scope, shared aggregate read budget, backward-compatible API. | Reported focused 138 passed/1 skipped; broader 1,293 passed/17 skipped. These are host-permitted local runs, not native Windows acceptance. |

Relevant source tests remain navigable in
[run review](../../tests/product/test_run_review.py),
[verification](../../tests/product/test_verification.py),
[regression review](../../tests/product/test_regression_review.py),
[native acceptance journeys](../../tests/desktop/test_acceptance_workflows.py) and
[regression GUI workflow](../../tests/desktop/test_regression_workflow.py).
An unchecked default and an unavailable check are not failed execution or safe
firmware. Digests can agree without authenticating the observations they describe.

## 2026-11-07–09 — Batches 23–28: candidate containment versus promotion

The strict gate rejected rolling QEMU 11.1.3 when the profile expected 11.1.2.
Batch 23A diagnostics at
[`88ef1e1f9f6dbb773f43dc30918fa6f9a16d16ef`](https://github.com/mtalhak003/FIRMAVEX/commit/88ef1e1f9f6dbb773f43dc30918fa6f9a16d16ef)
preserved expected/observed identities before temporary cleanup. The
[candidate workflow](../../.github/workflows/windows-runtime-candidate.yml)
remains manual-only, exact-revision-bound and isolated from production. It tests
signed acquisition, inventory, actual low-level ARM behavior, owned resources,
and **production rejection** through source/GUI/frozen/installed paths. Its tests
do not authorize the candidate's positive execution through those product paths.

The chain added ZIP/accounting verification
([25](../product/batch25-runtime-qualification.md),
`8c4a6fa7d8611a93eb717b3231b84a6a5ff79dfe`), linked rejection/JUnit contracts
([26](../product/batch26-promotion-readiness.md),
`43f932a2f8fa1c34762ae8088a427b328ee6fc54`), installed lifecycle checks
([27](../product/batch27-qualification-closure.md),
`c42cdd000dbd117dee558fd346aa8b653ac7bf3f`), then original-artifact binding and
bounded static import auditing ([28](../product/batch28-release-readiness.md),
`66fba9b9a339b300a57df0974487d675bdc9ea8c`). Local synthetic archive and
ephemeral-key tests validate fail-closed verifier behavior, not authentic vendor
signatures or missing archive contents.

Recorded public CI observation for [42618949135](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135),
attempt 1 at `c42cdd000dbd117dee558fd346aa8b653ac7bf3f`, includes successful
installed lifecycle/rejection. The later **user-reported** original ZIP verification
is 19 receipts, 97 JUnit passed, 10 skipped, zero failures/errors; original
SHA-256 `f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`.
No independent receipt recount or original-byte verification was performed in
this documentation audit. The [November 9 entry](../product/development-progress.md#november-9-2026--windows-candidate-evidence-and-release-preparation)
preserves the attribution and earlier retrieval failures.

The installed candidate check compares console/GUI executable identities, startup,
same-package reinstall, external sentinel preservation and owned uninstall. It
does not cover every installed DLL/data file, authoritative saved-result migration,
distinct-version transition or clean consumer machine. Complete authentic signed
packages, independently trusted signing inputs, compatible package/DLL closure,
source/license review, positive product qualification and consumer acceptance
remain separate requirements. No green candidate job or archive-consistency pass
promotes QEMU 11.1.3.

## 2026-11-10 — Batch 29: report available-environment passes honestly

Implementation
[`feb1fab8b65d3626a4389a2cc1424cd8f352d01f`](https://github.com/mtalhak003/FIRMAVEX/commit/feb1fab8b65d3626a4389a2cc1424cd8f352d01f)
and documentation
[`da22cc6853d21cfa45fd851aa77108357f62dd7e`](https://github.com/mtalhak003/FIRMAVEX/commit/da22cc6853d21cfa45fd851aa77108357f62dd7e)
add project reset/static ELF checking, shortcut recovery, persistent readiness and
state feedback, readable navigation and confirmed export responses. The
[Batch 29 guide](../product/batch29-desktop-workflows.md#validation-performed)
retains exact commands and exclusions:

- New tests: **143 passed**, no skips/failures/errors/deselections.
- Desktop plus recent-project checks: **389 passed, 16 skipped**.
- Unfiltered application attempt before the final layout-only addition:
  **2,079 passed, 106 skipped, 1 failed, 6 errors**. The failure/setup errors
  require absent ARM GCC; the existing tests remain unchanged.
- Final available-environment selection: **2,080 passed, 106 skipped,
  6 deselected**, plus one real-firmware integration test excluded at collection.
  This is a scoped passing selection, not a complete-suite pass.

Real Qt widgets and actual supervised export transport were tested over explicitly
synthetic archives, including hash checks and unchanged original bytes. Firmware
execution was not performed. These were independently run during Batch 29 and are
historical retained results for this Batch 30 audit. Native Windows/macOS, equipped
runtime, frozen/installed and consumer acceptance for the new UI remain unproven.

## Evidence to retain for future milestones

Use the [milestone template](milestone-template.md) and
[history-maintenance procedure](history-maintenance.md). Record exact source SHA,
run/attempt/job, tool identities, selection, flags, counts and raw evidence before
calling a requirement passed. Preserve failing and unavailable results as well as
later repairs. Link actual installed binaries to their build and runtime subjects;
do not infer that link from an artifact name or matching version string. Keep
human/native standard-user, accessibility, enforced-offline and low-disk acceptance
separate from hosted unit/GUI smoke tests. No new runtime or installer tests, CI
dispatch, experiment or production change was needed for this documentation audit.
