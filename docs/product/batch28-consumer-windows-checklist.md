# Batch 28: clean consumer-Windows acceptance checklist

**Not an executed acceptance report.** Review date: 2026-11-09 (Asia/Karachi).
Baseline: `c42cdd000dbd117dee558fd346aa8b653ac7bf3f`.
All consumer rows start **NOT PROVEN**. Hosted CI installation/rejection checks
and GUI smoke tests are supporting observations, not a substitute for this trial.

This checklist specializes [consumer acceptance](consumer-acceptance.md) for a
developer-supervised, clean Windows x64 machine or disposable VM. It does not
require access to any previous private trial evidence. Do not use historical
research archives or run comparative/held-out experiments.

## Entry conditions: stop if these are missing

1. Record Windows edition/build, CPU, RAM/disk capacity, screen resolution/scaling,
   tester/date, native versus virtual host, and whether the account is standard
   or administrator. A VM is not physical hardware qualification.
2. Obtain the exact reviewed installer/build revision, checksum and independently
   authentic signing information. Keep unsigned preview testing explicitly
   separate from the signed public-release requirement. A matching checksum is
   integrity evidence, not publisher authenticity.
3. Keep Smart App Control, Defender and other host protections enabled. If a
   protection blocks the application, retain the message and mark the journey
   BLOCKED/NOT PROVEN. Do not disable it, remove provenance or silently bypass it.
4. Obtain a legitimately qualified runtime package set with independently verified
   signatures, compatible dependencies and required notices. The current QEMU
   11.1.3 candidate remains production-rejected. Its rejection can be tested, but
   positive execution rows remain blocked until separately authorized readiness
   conditions are met; see the [positive qualification proposal](batch28-positive-qualification-proposal.md).
5. Use only trusted bundled examples and documented supported ELF/target profiles.
   Raw BIN, arbitrary MCU/platforms, physical hardware and hostile firmware/HDL
   isolation are outside this trial. Do not call HDL simulation firmware fuzzing.
6. Choose fresh, independent project, result and administrative evidence folders
   outside the checkout and application installation. Preserve originals. Keep
   outputs private until paths, filenames, diagnostics and supplied metadata have
   been reviewed for publication.

The operator should not need Python, a compiler or terminal commands to complete
ordinary GUI journeys. A supervising developer may collect hashes, networking
state, process handles and logs independently. Record that supervision rather
than presenting the procedure as unsupervised consumer installation.

## Recording rules

For each row record **PASS / FAIL / NOT PROVEN**, expected and observed behavior,
exact installer/application/runtime/firmware identities, timestamps, and evidence
locations/digests. Use NOT PROVEN for blocked, unavailable or unperformed work.
Do not convert a missing result into PASS. Retain failed attempts and cleanup
errors. A screenshot proves visible behavior only; receipt/accounting checks
need their original machine-readable records.

| ID | Journey and method | Pass criteria | Initial status |
|---|---|---|---|
| W01 | Clean per-user installation as a standard user, without Python/compiler on the execution path | Installer behavior, requested privileges and destination are explained; app starts through normal Windows shortcuts. No hidden developer-tool setup is required. | NOT PROVEN |
| W02 | First-launch wizard and missing-runtime state | Target/backend compatibility and missing dependencies are clear; no false "ready" state. Canceling setup leaves existing data/runtime generations intact. | NOT PROVEN |
| W03 | Runtime installation, verification and repair | Authentic package/source/signature and closure checks are retained. Tamper an inactive disposable copy only; detection fails closed and repair restores verified bytes without replacing unrelated generations. | NOT PROVEN |
| W04 | Candidate rejection | The unqualified candidate produces accurate expected/observed identity diagnostics, no dispatched firmware, no fabricated result and no charged attempt. Older valid generations remain unchanged. This negative path is not positive runtime qualification. | NOT PROVEN |
| W05 | Compiler-free example through normal GUI | Supported `mps2-an385` example opens, runs and shows accurate progress, configured failure and exact triggering input `[2, 1]`; matching initialized-data/runtime evidence and cleanup are retained. | NOT PROVEN |
| W06 | Bounded reproduction and reopening | Three fresh requested observations reproduce the saved exact vector; reopening history after application restart preserves authoritative results, identities and receipts. Changed firmware/tools are rejected as non-equivalent reproduction. | NOT PROVEN |
| W07 | Report and evidence export | New export folder receives understandable report and checksum-bearing evidence; counts, units, vector and failure classification agree with the original run. Existing output is not overwritten; export does not execute firmware. | NOT PROVEN |
| W08 | Enforced offline repeat after prerequisites are installed | Test operator records networking disabled/blocked independently, then repeats GUI example, replay, reopen and export successfully without accounts or a network request requirement. A checkbox, absent telemetry setting or CI's unused network is insufficient proof. | NOT PROVEN |
| W09 | Keyboard-only and assistive interaction | All first-run, project, run/cancel, result and export actions are reachable with logical focus/order and usable labels. Record actual screen-reader behavior, contrast, zoom/high-DPI and display scaling; automated Qt accessibility metadata alone is insufficient. | NOT PROVEN |
| W10 | Cancellation at declared stages | Cancel before dispatch and after admitted progress. UI remains responsive; charged attempts and interrupted/aborted state are truthful; no normal completion is invented and no owned worker/QEMU/GDB tree remains. | NOT PROVEN |
| W11 | Timeouts, tool failure and missing completion | A bounded disposable test produces an infrastructure/error outcome, retained diagnostics and correct charged accounting. A failure symbol alone cannot replace completion evidence. | NOT PROVEN |
| W12 | Application/worker interruption and explicit recovery | Terminate only the declared owned test process. Reopen as interrupted, not completed. Inspection/recovery executes no firmware. An explicit restart uses a fresh linked run and discloses potentially repeated abandoned work. | NOT PROVEN |
| W13 | Same-package reinstall and uninstall | Preserve independent projects/results byte-for-byte, await uninstaller descendants, remove application executables and registration as documented, and record leftovers. Reinstall can reopen preserved data. | NOT PROVEN |
| W14 | Distinct-version upgrade and supported rollback | Use a separately declared approved older/newer pair and actual saved results. Compare archive hashes before/after. Same-package reinstall does not qualify this row; unsupported schema downgrade is not implied. | NOT PROVEN |
| W15 | Low-disk and denied-write handling | Use a bounded disposable volume or controlled filesystem quota; never fill the host system disk. Installation, run persistence and export fail clearly, retain truthful incomplete state, preserve existing data and allow documented recovery. | NOT PROVEN |
| W16 | Interrupted installation | Establish an actual declared installer boundary before cancellation. Retain original interruption and partial-install diagnostics; verify recovery/removal. Missing uninstaller or partial leftovers are failed cleanup, not successful rollback. | NOT PROVEN |
| W17 | Paths and ordinary file operations | Exercise spaces, non-ASCII names and supported Windows path lengths; unsafe links/reparse points and unsupported paths fail clearly. Cancel file dialogs without altering current projects/results. No security/path restriction is weakened. | NOT PROVEN |
| W18 | Session reliability and error guidance | Run a predeclared bounded sequence with open/reopen/cancel/export; prevent duplicate submissions and stale-result attribution. Errors identify action and remedy while preserving original accounting. Record exact duration; one short trial does not prove long-run stability. | NOT PROVEN |

Offline enforcement applies only to a disposable test host after dependencies
have been legitimately obtained. Do not disable host security services or alter
the developer's regular machine to manufacture an offline result. Record local
network policy separately from application functionality.

## Automated support versus human evidence

- The candidate workflow can exercise owned silent install/reinstall/uninstall,
  executable identities, GUI startup and admission rejection. Its external
  sentinel is not an authoritative existing saved-result archive, and its hosted
  token is not proof of ordinary standard-user operation.
- Unit/offscreen Qt tests can check form state, classification, argument handling,
  cleanup logic and report contracts. They cannot establish actual native Windows
  execution, real installer behavior, screen-reader usability or offline
  enforcement.
- Native source probes can establish defined ARM observations and resource
  behavior within their exact scope. They do not establish positive frozen or
  installed product execution when production admission rejects that runtime.
- Real GUI navigation, Windows security prompts, first-user comprehension,
  accessibility, offline enforcement and the clean-machine environment need
  separately retained human/native evidence. Current run/artifact verification
  belongs in the Batch 28 readiness matrix, not inferred from this checklist.

## End-of-trial review

1. Recheck installed application/runtime identities, authoritative accounting,
   exact triggering vectors, reproduction records and exports. Distinguish charged
   evaluator attempts from independently verified guest executions.
2. Independently verify owned process cleanup; process-name absence alone is
   insufficient. Report cleanup failures and remaining files without destroying
   original evidence.
3. Compare preserved independent result/project hashes. Keep failed, interrupted
   and non-discovery outcomes distinguishable from configured failures.
4. Publish a row-by-row signed-off report only after reviewing sensitive paths and
   diagnostics. Archive original evidence privately and publish redacted copies
   separately, with a documented relationship to originals.
5. Leave the release decision explicit. Passing this limited ARM trial would not
   establish all-target Windows support, macOS execution, hardware correctness,
   hostile-workload sandboxing or general public-beta readiness.

No trial, firmware execution, installer operation or test suite was run while
preparing this document. All initial statuses above remain NOT PROVEN.
