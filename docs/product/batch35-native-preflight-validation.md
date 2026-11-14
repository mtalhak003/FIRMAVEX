# Batch 35 — controlled native Windows preflight validation

**Report date:** November 14, 2026, Asia/Karachi.
**Reviewed preflight baseline:** `90af3e836c81bd0dc9a27dcea076f19ce7ee15e6`.
**Delivery status:** portable implementation and Linux validation completed;
**native Windows execution, PowerShell parsing and Windows ACL qualification
remain NOT RUN / NOT PROVEN**. This is a developer-supervised administrative
workflow, not desktop, runtime, installer, signing or release qualification.

## Recovery and implementation

The original approved worktree was recovered at detached HEAD `90af3e8` with an
empty index and three untracked drafts. Those drafts were inspected and extended;
no reset, clean, replacement checkout, reconstruction or branch switch occurred.
The earlier **43 passed / 1 failed** result preceded the input-admission repair
and is historical, not current validation. The recovered 66-case selection passed
before the additional repair regressions were added; that did not establish the
absence of the subsequently tested defects.

The implementation consists of:

- [PowerShell 7 operator wrapper](../../tools/validate_windows_preflight.ps1).
  It requires native Windows, an exact expected revision, explicit controlled-input
  acknowledgment, an existing operator-trusted virtual-environment Python and a
  validated absolute Git executable. It refuses nonlocal/ambiguous paths, static
  reparse parents, reused output and overlapping source/input/venv/output trees.
- [Python validation harness](../../tools/windows_preflight_validation.py).
  It verifies the named development branch, clean scoped checkout, baseline
  ancestry, allowed changes and actual reviewed source bytes; supervises a fixed
  synthetic test selection; runs repeated inert file assessments; and writes a
  fresh evidence archive. Its native entry has no Linux/WSL bypass.
- [Synthetic harness regressions](../../tests/product/test_windows_preflight_validation.py).
  These test failures, cancellation and mocked Windows ownership without launching
  QEMU, GDB, firmware, installers, signers or supplied application files.

### Repairs retained and completed

| Finding | Repair and validation boundary |
|---|---|
| Bare Git could select a current-directory/PATH executable downstream | The wrapper passes its validated absolute `git.exe` through a required argument. Python forwards it to every Git call, rejects unsafe locations and never falls back to PATH. Windows requires the literal `.exe` filename. |
| Cleanup-only control-flow exceptions became ordinary failures | Cleanup attempts remain bounded; KeyboardInterrupt, SystemExit and custom BaseException control flow propagate as their original objects. An already-active interruption retains priority with cleanup notes. |
| Failure-record persistence could swallow a new interruption | A new persistence interruption supersedes an ordinary primary error; an existing primary interruption is preserved. Partial evidence is retained without inventing completion. |
| Inputs could change during the test phase before repeated assessment | The admitted inventory is retained and compared with assessment and final snapshots. The dedicated input-admission mutation regression passes. |
| Host Git/Python/pytest settings could redirect or expand work | Git redirect/config/helper variables are cleared, global/system config and replacement objects are disabled, fsmonitor/hooks/external diff are constrained, and remote transport/lazy-fetch paths are disabled. Python bootstrap uses `-E -s -B`; pytest uses a fixed configuration, no auto-loaded plugins and controlled temporary directories. |
| Clean Git status alone did not establish working-file source pins | Index visibility flags and local filter/include configuration are refused. Reviewed blob bytes are compared with bounded actual working bytes. Only LF/CRLF text normalization is permitted; raw SHA-256 fingerprints remain recorded and are compared again afterward. |
| Encoded XML could evade ASCII DTD/entity checks | JUnit input must be bounded UTF-8 without NUL; declarations are checked before XML parsing. Duplicate/missing cases, multiple outcomes and incorrect selection accounting are rejected. |

Git worktree binding is checked before status scanning. Checkout admission occurs
before supplied-input snapshots or archive creation. These are defenses for a
trusted developer checkout, not authentication of arbitrary Git repositories,
configuration, Python installations or host loaders.

## What the workflow actually does

1. Verify the **exact reviewed Batch 35 delivery SHA** and clean named
   `product/desktop-batch11` checkout. Independently require Batch 34 ancestry and
   unchanged reviewed preflight/test/helper contents. Do not pass the Batch 34 SHA
   as the delivery revision: it predates the harness.
2. Require an existing supported venv and reviewed local Git/Python tools. No
   package manager or dependency installer runs. Local Git filter/include
   configurations are unsupported and cause refusal; do not disable host security
   controls to make a refusal pass.
3. Create one fresh output root outside the repository, venv and optional supplied
   staging tree. Existing directories/files are not reused or overwritten.
4. Run exactly the reviewed preflight and file-state suites: **162 cases**, comprising
   158 preflight cases and four file-state cases. The required NTFS case is tracked
   separately. No arbitrary test arguments or runtime tests are accepted.
5. Create four benign synthetic input sets under owned `fixtures/`, separately
   from `assessments/`: missing evidence, a lexical-refusal string, a normal path
   containing spaces and plain text, and a malformed receipt. No real executable
   is created or dispatched by these fixture assessments.
6. Assess every selected manifest twice, compare deterministic JSON, and compare
   input byte identities/absence states before, between and after assessments.
   Optional supplied inputs are also compared with their pre-test admission
   snapshot. Invalid manifests explicitly limit inventory coverage to the manifest;
   they do not establish unchanged unassessed members.
7. Recheck checkout/source/host context, persist result and checksums, then write
   the completion marker. Failures and interruption preserve partial archives.

`generated_synthetic` identifies harness-created inputs. Optional supplied files
are `operator_supplied_unverified`, even if they are genuine vendor binaries.
Only actual Windows execution can produce the native-functional host observation;
no caller label can approve runtime capability, signature trust or production use.
Unit-test mocks of Windows facts remain synthetic test data.

## Native Windows command — execution pending

Use an existing native Windows PowerShell 7 verification checkout at the **full
Batch 35 commit from the delivery report**, on the named development branch,
with its existing `.venv\Scripts\python.exe`. The wrapper changes no Git branch,
configuration, source files or security policy. It performs no fetch/install.
If the revision is wrong, the checkout is dirty, a dependency is missing or a
security control blocks the script/interpreter, preserve the situation and stop.

From that checkout root, replace only the SHA placeholder:

```powershell
$Out = Join-Path $env:LOCALAPPDATA ('FIRMAVEX-Preflight-Batch35-' + [guid]::NewGuid().ToString('N'))
& (Join-Path $PSHOME 'pwsh.exe') -NoLogo -NoProfile -File .\tools\validate_windows_preflight.ps1 `
    -ExpectedHead 'FULL_REVIEWED_BATCH35_COMMIT_SHA' -Output $Out -ConfirmControlledInputs
$Code = $LASTEXITCODE
Write-Host "Harness exit: $Code; private output: $Out"
```

The default command needs no QEMU/GDB/runtime files. It exercises only the fixed
synthetic suites and synthetic assessments. It was source-checked here, **not
parsed or executed by PowerShell**. No execution-policy bypass, signing purchase,
privilege grant, Defender/SAC change or installer step is authorized.

For a separately reviewed supplied manifest, additionally pass both `-Manifest`
and `-StagingRoot` as absolute ordinary local paths. Every referenced input must
be inside that staging root. Use stable developer-controlled copies only, with no
concurrent untrusted writers. Never point this workflow at original campaign
archives, backups, protected/private evidence or live mutable runtime generations.
The harness records hashes, not copies of supplied input contents.

### Exit codes

| Exit | Operator workflow meaning |
|---|---|
| `0` | Fixed tests passed without skips and expected diagnostic assessments completed consistently. **Not runtime/signing qualification.** |
| `1` | Workflow completed with skipped/unverified test cases; inspect actual reasons. |
| `2` | Precondition, test, input-consistency, persistence or harness failure. Preserve output if created. |
| interruption | Normal control-flow cancellation propagates; partial output remains, and a failure marker is attempted. |

These are **harness** codes. Baseline preflight codes `1`/`2` are retained per
assessment as diagnostic findings; an expected blocked synthetic input is not
misreported as a failed test or a successful qualification.

## Evidence archive and safe interpretation

| Member | Scope |
|---|---|
| `STARTED.json` | Admission/start context, exact source and baseline, host metadata and nonqualification flags |
| `pytest/console.log`, `pytest/results.xml` | Private original output of the selected synthetic host tests; may contain local paths/hostname in failures/JUnit |
| `pytest/process-temp/`, `pytest/temporary-root/` | Owned process/test temporary data; preserved without broad cleanup or recursive publication |
| `fixtures/` | Generated benign synthetic text/JSON inputs, never original campaign/runtime evidence |
| `assessments/<case>/first.json`, `second.json`, `summary.txt` | Sanitized preflight findings, repeated deterministically |
| `result.json`, `summary.txt` | Workflow classifications, test counts, input identities, source fingerprints and limitations |
| `SHA256SUMS`, `COMPLETE.json` | Listed-file integrity records and terminal completion metadata, not signatures/authentication |
| `FAILED.json` | Failed/interrupted workflow record; **overrides COMPLETE if both exist** |

Accept completion only with **no FAILED marker**, valid completion/result JSON
and matching listed checksums/result/inventory hashes. Marker existence alone is
insufficient: a late fsync/close failure can leave complete-looking bytes followed
by FAILED. Missing/partial markers mean incomplete evidence. Never edit or repair
an archive to improve its classification; use a fresh output for a new attempt.

Checksums cover explicitly registered evidence files, not a recursive inventory of
every test temporary file or symlink. Do not blindly ZIP/publish the whole root.
Keep raw logs private and review/redact a separate publication copy. No automatic
upload, telemetry or CI dispatch occurs. Source hashes and caller receipts do not
authenticate the host, package publisher or original evidence.

## Actual validation and evidence provenance

The final [development-history entry](development-progress.md#2026-11-14--batch-35-controlled-preflight-validation-harness)
records exact commands/counts. Actual execution here was **Linux with Python
3.12.14**, not Windows or WSL qualification. The focused suite uses synthetic
inputs and mocked Windows jobs/control flow. The related selection includes the
existing preflight/file-state cases; native NTFS semantics are skipped on Linux.

A real portable integration exercised the supervised **Python-only** 162-case
selection, all four generated assessments, archive sealing and checksum
verification. It reported **161 passed, 1 native-NTFS skip, zero failures/errors**;
missing evidence remained `missing`, and the lexical, malformed-receipt and
non-PE text cases were `blocked` as expected. Reports were deterministic and
observed inputs unchanged. The record explicitly sets
`evidence_class=portable_synthetic_validation`, `native_windows_verified=false`,
`checkout_verified=false` and `working_tree_dirty=true`: it exercised uncommitted
portable helpers, not the native operator or clean-checkout admission path.

A separate read-only Linux smoke used the explicit existing `/usr/bin/git` with
the harness's real argument/environment controls. Revision/root binding, raw
configuration/index guards and actual-byte comparisons for all **15** reviewed
baseline source files passed. It performed no Git mutation and did not establish
native Windows Git behavior or full named-branch operator admission.

Its private ephemeral archive was
`/tmp/firmavex-batch35-final-portable-ngawveav/archive`; no archive/output is
committed or promised as a downloadable/native artifact. The tested harness
SHA-256 was
`1c964c2dfbd75a103282f83bf9b33848380aecf7eb4cc2f069ac31b86c6c0995`.
PowerShell source-contract assertions passed; PowerShell parsing, PSScriptAnalyzer,
Windows job execution, wrapper end-to-end execution and native ACL tests were
**NOT RUN**, because no native Windows/PowerShell environment was available.

## Remaining limits and readiness

- Preserve [Batch 34 B34-03](batch34-preflight-security-review.md): hostile parent
  replacement can redirect a read before rejection. Controlled-input acknowledgment
  is a precondition, not an independently enforced isolation boundary.
- Existing Git, repository metadata and the venv are operator-trusted. These
  checks do not authenticate all installed Python/DLL dependencies or sandbox an
  adversarial developer environment. Complete local baseline objects are required;
  the workflow will not acquire missing inputs or qualify a package set.
- File/count and read limits do not guarantee OS memory/time or filesystem
  isolation. Pytest waits are bounded; raw console growth is checked **after**
  completion, not hard-capped live. Provision adequate disk space and preserve
  failures. No strict live log quota is claimed.
- Output directory mode `0700` is not proof of Windows ACL privacy. Use a private
  controlled parent and verify native permissions separately.
- Native path, reparse, sharing/locking, Python/Git selection, interruption and
  cleanup behavior remain pending on actual Windows. Do not grant privileges or
  weaken checks to remove legitimate symlink/FIFO skips.
- Runtime capabilities, complete DLL/legal closure, signature trust, Smart App
  Control acceptance, firmware execution and production/release approval remain
  unassessed. All corresponding security/qualification flags remain false.

**Next milestone:** run the reviewed native operator command on controlled
Windows, retain the original private archive and actual counts/skips/failures,
then review it within this scope. No release, runtime promotion or main merge is
authorized by a successful harness run.
