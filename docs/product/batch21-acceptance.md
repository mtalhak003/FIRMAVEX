# Batch 21: product acceptance and usability

## Baseline and evidence rules

The development branch was `product/desktop-batch11`, clean at expected commit
`d474fab63500e6a2e726caf77c207060efecaa55`. Its
[Product workflow](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40024230126)
passed, including Windows Python 3.11/3.12. Its
[Native workflow](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40024229596)
passed Windows and Ubuntu. The native macOS failure is the established RLIMIT_AS
memory-admission blocker. The Windows test-ID and native-directory repairs remain
intact; Batch 21 does not change them or the release/qualification gates.

Resume also checked the other baseline workflows: native setup failed at the
Windows private-runtime installation step, versioned installation failed on
Windows, aggregate isolation failed its fixed-probe tests, and distribution
failed its mandatory release-evidence gates. Those existing failures are not
Batch 21 acceptance successes and remain outside the four corrections.

The audit reviewed Batches 17–20 and the current backend capability matrix.
Representative fixtures use the packaged symbolized Cortex-M3 ELF (including
custom trailing-byte revisions), the packaged RV32 ELF with explicit uint32
inputs, and supported single-file ASCII Icarus testbenches. Native work uses
QEMU/GDB or Icarus through the real desktop controller and supervised worker.
No native execution is replaced by an injected controller in those tests.

Classification used below:

- **A — Actually exercised and passed:** local Linux native execution and real
  Qt/controller/worker navigation, with the named assertions below.
- **P — Partially exercised/supported:** a supported subset or a documented
  restriction; this is not full workflow acceptance.
- **M — Mocked or service-only:** synthetic Qt worker responses or pure service
  tests; no native GUI end-to-end claim.
- **U — Unsupported:** outside the supported product boundary.
- **E — Environment-blocked:** native execution cannot be admitted on the host.

Tests supply deterministic OS file-picker responses and generate fixtures; they
exercise application slots/buttons and real background operations, not manual
OS-dialog interaction. Keyboard-only, screen-reader, DPI and long human working
sessions were not audited. A marks tested fixtures, not every embedded project.

## Backend acceptance matrix

| User journey | ARM Cortex-M3 | RV32 | Single-file Verilog |
|---|---|---|---|
| Create/import | **A:** packaged example, new-build import button, new-project form; selected ELF bytes and prior-project preservation asserted | **A:** custom ELF path and named snapshot import through UI worker | **A:** custom ASCII testbench path and named snapshot import through UI worker |
| Configure | **A:** managed symbol/budget configuration and distinct imported images; opened-project execution remains pinned | **A:** two uint32 values and saved limits; decimal/hex form contract | **A:** fixed-top single-file configuration and saved limits |
| Preflight | **A:** real ARM validation in editor and unified workspace | **A:** ELF/profile static checks through UI worker | **A:** existing lexical/contract checks through UI worker; not elaboration or assertion-correctness proof |
| Execute | **A:** bounded search, triggering vector, replay, real-firmware labels and cleanup | **A:** passing/triggering input observations, readback, completion and cleanup | **A:** PASS, FAIL, compiler syntax rejection, simulator cancellation and cleanup |
| Diagnose | **A:** recorded failure/reproduction summary and authoritative accounting | **A:** recorded outcome/readback/failure diagnosis | **A:** recorded outcome and retained compiler diagnostics; assertion failure in native regression sets |
| Save/reopen | **A:** project and result reopening, source deletion after import, immutable prior images/runs | **A:** list/open saved snapshot after origin deletion; reopen saved results | **A:** same snapshot/result reopening and origin-deletion checks |
| Compare | **A:** actual individual-run comparison UI and read-only evidence | **A:** individual and regression session UI comparison | **A:** individual and regression session UI comparison |
| Verify evidence | **A/P:** explicitly select nested `arm-run` to verify registered artifacts; wrapper checks do not establish nested receipt/accounting verification | **P:** individual default verifier truthfully returns unavailable without a listed inventory; **A** regression verification includes retained firmware | **A:** listed VCD verification and regression retained-input checks; missing VCD tested on a separate evidence copy |
| Export report | **A:** native backend/ARM reports and verification-observation text report | **A:** backend report, unavailable individual-verification observation, and regression text report | **A:** backend/VCD export, verification report and regression text report |
| Regression sets | **U:** existing ARM search/reproduction retained | **A:** explicit create/save/run/diagnose/rerun/compare/verify/export with real native execution | **A:** same native regression workflow, including assertion failures |
| Invalid vectors, malformed logs/VCD and unavailable partial frames | **M:** bounded service/synthetic Qt checks where relevant | **M:** parser and partial/error UI boundaries; ordinary native passing/triggering cases are separate | **M:** malformed log/VCD parsing and UI payload boundaries; native compiler rejection, cancellation and missing-artifact copy are separately A |
| Native macOS execution | **E:** memory admission | **E:** memory admission | **E:** memory admission |
| Raw BIN/arbitrary targets, multi-file HDL, physical validation | **U:** raw BIN/arbitrary MCU/hardware | **U:** arbitrary RISC-V platforms/hardware | **U:** includes/multi-file expansion, synthesis, physical FPGA |

ARM custom import is now exercised through actual GUI import actions, not merely
`DesktopProject.create` service setup. RV32/Verilog regression fixtures still seed
configuration snapshots using the existing service before exercising their set
editor; ordinary named-configuration import/save/reopen has separate native UI
coverage. The VCD metadata viewer's malformed/bounded cases remain service or
synthetic-Qt coverage; no full waveform viewer is claimed.

## Issues, reproduction and priorities

The ranking weighs user impact, frequency, evidence/execution-integrity risk,
implementation complexity and testability. Only four justified fixes were chosen.

| Rank | Issue | Impact/frequency | Integrity risk | Complexity/testability |
|---|---|---|---|---|
| 1 | ARM new-project form silently imports the opened project's image instead of its selected ELF | High / every such import from an open project | High: wrong input identity despite a different selected file | Low / real native byte-identity assertions |
| 2 | Regression administration overwrites individual result JSON while its label/run pointer still identify the old run | High / every regression operation after individual inspection | Medium-high: misleading evidence association in the UI | Low / synthetic Qt plus actual native navigation |
| 3 | Regression errors jump to the unrelated Summary tab and leave no useful in-context recovery/partial-session view | High / invalid folders, rejected exports, interruption | Medium: lost context; existing worker still fails closed | Medium / synthetic interruption and actual native worker rejection |
| 4 | Regression vectors use `int(token, 0)` while ordinary RV32 execution uses decimal/hex parsing | Medium / padded decimal inputs and editing sets | Low: incorrect rejection, not an admitted invalid execution | Low / shared pure parser and native padded-zero vectors |

Concrete reproduction evidence before corrections:

1. Open a managed ARM project, select a different compatible ELF in **Firmware
   ELF**, choose a new folder and click **Import into new project**. `configuration()`
   intentionally pins execution to the open project's image; the import action
   incorrectly reused that pinned image. A real native fixture assertion found
   the new project's bytes lacked the selected second image's appended revision.
   `/tmp/firmavex-batch21-arm-import-before.log` records that byte mismatch.
2. Inspect any ARM/RV32/Verilog run, then **Regression test sets → List saved sets**.
   `record` and `active_run` still identified the individual run, but Result /
   evidence showed the administrative response. The three backend-specific Qt
   reproductions failed before the correction.
3. From the regression panel, export inside original evidence storage or open an
   unavailable session. The worker rejected it correctly, but the UI replaced
   the individual result context and navigated to Summary. A cancelled worker's
   validated partial regression summary was not adopted. Synthetic Qt reproductions
   cover this path; native RV32/Verilog tests additionally submit an overlapping
   export and assert preserved evidence and in-context guidance.
4. Add an RV32 configuration to a set and enter `08, 01`. Ordinary execution accepts
   that decimal notation; the set editor raised `invalid literal for int() with
   base 0: '08'`. The before-fix UI test captured this exact error.

The initial targeted Qt reproduction selection had **8 failures and 1 pass**;
these were intentional new audit assertions, not unexplained baseline native
failures. A proposed change to prioritize diagnostic excerpts was not implemented:
the representative bounded failure excerpt already contained its root cause.

## Corrections and retained guarantees

- New-project ARM import explicitly uses the visible ELF selection and existing
  configuration bindings. Save, Validate and Run of an opened project still use
  its pinned imported image. A tooltip clarifies the distinction. New-build import,
  old projects, revision files and prior evidence remain unchanged.
- Regression results are administrative output in Operation details and their own
  panel. They no longer replace an individual backend's Result / evidence or its
  saved-result context. Real native tests preserve those values across dashboard,
  compare, verify and export operations.
- Regression errors remain in their panel with concise action-specific guidance.
  Worker-inspected partial summaries can be displayed after interruption; missing
  or malformed partial frames never create an outcome. When no validated summary
  exists, the requested session folder is shown as a reference. No automatic
  retry, resume, execution or filesystem inspection was added to the Qt thread.
- Both RV32 forms reuse one bounded decimal/hex uint32 parser, including padded
  decimal values and whitespace/comma separators. Invalid dimensions, overflow,
  negative values and excessive text fail locally with guidance. HDL entries
  reject vectors explicitly. Backend preflight and Request validation remain
  mandatory, and revisions are published only through existing explicit saves.

The implementation changes desktop presentation/import selection only. It does
not alter resource policies, native-directory handling, consent, worker admission,
process ownership/cleanup, archive formats or scientific outcomes. Read-only tests
check byte-for-byte evidence preservation. Missing VCD checks use a separate copy;
original native evidence is not damaged for acceptance testing.

## Reproducible test evidence

The following two counts and before-fix observations were recorded in the
inherited, uncommitted Batch 21 report. Their temporary logs were absent when
development resumed on 2026-10-24; they are historical observations, not fresh
validation of this checkout. Fresh resume results are recorded separately below.

- Baseline native Qt audit: **12 passed** in 129.12 seconds before implementation.
- Extended native Qt acceptance: **13 passed** in 151.02 seconds; includes
  `test_real_unified_example_execution_reproduction_history_export` for all three
  backends, `test_real_custom_configuration_workflow`, both regression dashboard
  cases, actual malformed Verilog, cancellation, ARM import/reopen and built-in /
  compiled ARM journeys.
- Focused synthetic/pure Qt and product tests separately cover each correction;
  those results must not be presented as native firmware execution.

Run native acceptance with the documented trusted runtime tools on PATH and
`QT_QPA_PLATFORM=offscreen`. The local run used real Linux ARM tools plus the
existing temporary RV32/Icarus runtime assembled during prior batches. Source
fixtures use compiler-free images where possible; the compiled ARM journey ran
with an available ARM compiler. Windows qualification is determined by the
triggered CI jobs, not by these Linux observations. Native CI now also runs the
new ARM import/reopen test alongside the unified GUI journeys.

### Resume validation (2026-10-24)

Resume inspection found HEAD and the remote development branch both at
`d474fab63500e6a2e726caf77c207060efecaa55`, with these four corrections, their
tests and this report already present as uncommitted work. No completed batch
was repeated. Review retained the four-fix scope.

Focused synthetic Qt and pure service checks passed: **69 passed** in 1.94 s
(`test_acceptance_workflows.py`, `test_desktop_workflow.py`, `test_diagnosis.py`).
These checks do not execute native firmware.

The initial restricted-agent run completed with **1,443 passed, 46 skipped,
20 failed and 1 error**. Socket creation and ARM execution were denied with
`PermissionError: Operation not permitted`; this run is not native acceptance.
A second sandboxed native selection was interrupted after the same denial.
The complete suites are rerun outside the agent sandbox with application
execution policies unchanged. Ubuntu publisher QEMU 10.2.1 and Icarus 12.0
packages were extracted under `/tmp/firmavex-batch21-runtime`, alongside the
installed GDB and ARM compiler. This replaces the absent prior temporary runtime
without changing discovery or admission code.

The first host run had **1,486 passed, 16 skipped and 8 RV32 failures** in
279.78 s. Retained diagnostics identified a QEMU package-build mismatch:
the newly downloaded binary rejected the host's older `ui-opengl.so`. Matching
ARM/RV32 binaries and common, GUI, OpenGL and Spice modules were extracted from
the same publisher package build; `QEMU_MODULE_DIR` selects those modules.
No product code, limits or assertions were changed for this environment repair.
The four native RV32 backend checks then passed in 5.94 s.

Final validation on the resumed checkout:

- **Product and desktop: 1,270 passed, 7 Windows-only skips**, zero failures.
  The complete run's JUnit report confirms **all 13 native desktop tests passed**,
  including the compiled ARM journey, ARM import/reopen, all three unified
  workflows, custom configuration journeys, Verilog diagnostics/cancellation and
  RV32/Verilog regression review/export. Native-required flags were enabled.
- **Backend rerun: 224 passed, 9 skipped**, zero failures, in 36.35 s. Eight
  compiled-RV32 cases require the unavailable `riscv64-unknown-elf-gcc`; one legacy
  ARM adapter case requires the exact `arm-none-eabi-gdb` executable name. Actual
  compiler-free RV32 and ARM via GDB multiarch ran in the native journeys above.
- **Focused synthetic/pure checks: 69 passed**, separately classified above.
- `git diff --check` passed; existing assertions and release gates are unchanged.

The native-required full run also turned the nine optional backend tool skips
into failures/errors. It encountered the already documented 300 ms total-deadline
test failing in its first command. The identical failure reproduced in an
isolated snapshot of starting commit `d474fab`; the complete backend rerun passed
that test unchanged. The native-required run's backend portion is therefore not
claimed as a clean run; the separate complete backend rerun is the final result.
No threshold, test assertion or production deadline was relaxed.

Reproduce with the trusted runtimes on `PATH`, matching modules selected by
`QEMU_MODULE_DIR` if using extracted QEMU packages, and `QT_QPA_PLATFORM=offscreen`:

```sh
python -m pytest -q tests/product tests/desktop -ra
python -m pytest -q tests/backends -ra
```

Fresh local logs/JUnit reports were retained in `/tmp/firmavex-batch21-final.*`
and `/tmp/firmavex-batch21-backends.*`. They are transient local artifacts, not
uploaded release evidence. Push-triggered CI must be assessed separately.

## Remaining gaps and Batch 22 priorities

1. Make individual retained-input verification discoverable and consistent with
   regression verification, with an explicit scope and backward-compatible API.
2. Reduce navigation/discovery friction between the ARM editor, named configurations
   and regression sessions. No global history index or automatic archive relocation
   is introduced here.
3. Conduct human keyboard/screen-reader, DPI and display-size acceptance. Programmatic
   Qt tests and event-loop responsiveness do not establish full accessibility.
4. Improve saved-report provenance and cross-revision trends using existing bounded
   review services. Native instruction coverage, arbitrary custom build systems,
   hardware equivalence and complete reproducibility remain outside these tests.

macOS RLIMIT_AS, Linux isolation qualification and mandatory distribution/release
proof remain separate blockers. No release gate is weakened and no physical MCU,
FPGA validation or public release approval is claimed. Frozen main and
`evidence/windows-sandbox/` were not inspected or changed.
