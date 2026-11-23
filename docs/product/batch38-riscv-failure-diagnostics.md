# Batch 38 — RV32 failure diagnostics and result inspection

**Report date:** November 23, 2026, Asia/Karachi.
**Starting checkpoint:** `d97cfed271142cf06a8a879f8906b2220b820290`.
**Scope:** an additive RV32 primary execution diagnostic and its read-only desktop
presentation. This is not runtime, installer, hardware or release qualification.
Native Windows validation remains **PENDING**.

## Why this change

The [existing Batch 18 diagnosis](batch18-diagnosis.md) already explains recorded
outcomes, shows retained logs and supports fresh and saved results. The gap was
more specific: RV32 failures often retained only an exception string and the
broad `infrastructure_failure` status. A reviewer could not reliably distinguish
an actual typed timeout from other failures without guessing from log wording.

The implementation adds structured facts at the existing RV32 execution boundary
in [the adapter](../../firmavex/backends/implementations.py). The
[shared diagnosis renderer](../../firmavex/product/diagnosis.py) displays supported
fields. Existing desktop Summary integration is reused; no second diagnostic UI,
new backend, automatic rerun or new search behavior is introduced.

The [project overview](../../README.md), [unified capability guide](unified-desktop.md)
and [release policy](release-policy.md) retain the supported target and readiness
boundaries. This batch improves one practical inspection task while leaving the
separate runtime acquisition, signing and consumer-acceptance blockers unresolved.

## Using the desktop

1. Open the **Backends** workspace in an existing trusted installation.
2. Select a saved RV32 run in **Saved job history** and click **Open selected**,
   or choose **Open saved run…** for an explicitly selected run directory.
3. Read **Summary**, including the recorded outcome, retained diagnostics and
   **RV32 execution diagnostic**. Opening a saved run does not execute firmware.
4. Review the full saved JSON and cleanup evidence before deciding whether to
   authorize a separate new run. A timeout is not a safe result or an automatic
   reason to retry.

Fresh results use the same renderer. The controls are plain-text, read-only result
views. Existing ARM and Verilog workflows remain separate and unchanged. Tool
readiness, explicit trust, target compatibility and production admission continue
to govern any future execution; displaying a diagnostic does not waive them.

Older runs without structured metadata can still be opened. Missing, unsupported
or contradictory details show **unavailable** rather than a reconstructed cause.
No archive is migrated or backfilled. The selected UI backend cannot lend an
identity to a different saved result, and opening a later record clears stale
visible detail through the existing result refresh path.

## Retained diagnostic contract

A caught RV32 primary failure may add this optional object inside result evidence:

```json
{
  "failure_diagnostic": {
    "schema_version": 1,
    "backend": "riscv32-virt",
    "stage": "debugger_observation",
    "category": "timeout",
    "tool": "gdb",
    "return_code": null
  }
}
```

This is an illustrative schema example, **not real execution evidence**. The
object contains exactly six fields. The outer result schema and recorded terminal
status are unchanged. Successful passed/triggered observations do not acquire a
failure object merely because text in their logs sounds concerning.

| Field | Meaning and validation boundary |
|---|---|
| `schema_version` | Exact integer `1`; booleans and unsupported versions are unavailable. |
| `backend` | `riscv32-virt`, consistent with the available outer result/admission identity. Conflicts are unavailable. |
| `stage` | A known adapter pipeline phase; not proof that a guest executed or a breakpoint was reached. |
| `category` | A supported primary condition derived from execution state or exception type, never a log keyword. |
| `tool` | `qemu`, `gdb` or `null`, consistent with that phase; identifies context, not successful dispatch. |
| `return_code` | A bounded exact integer only for a recorded tool exit; otherwise `null`. Boolean/string codes are rejected. |

Supported phases:

| Stored phase | Displayed context |
|---|---|
| `tool_probe` | Runtime version probe |
| `qemu_startup` | QEMU startup, including local endpoint preparation |
| `debugger_observation` | Debugger observation and its preparation |
| `completion_validation` | Validation of the required completed-observation record |
| `identity_validation` | Recorded firmware/runtime identity comparison |

Supported categories:

| Category | Evidence supporting the label | What it does not establish |
|---|---|---|
| `timeout` | An actual caught `TimeoutError` in the recorded phase | Firmware infinite loop, guest hang, crash or assertion |
| `tool_exit` | An explicitly observed process/version-probe return code | Why the host tool exited or whether the guest caused it |
| `invalid_observation` | A `ValueError` from completion-record validation | A successfully completed safe observation or guest assertion |
| `identity_changed` | An actual unequal firmware or runtime identity comparison | Malicious intent or the cause of the change |
| `cancelled` | Existing recognized cancellation/control-flow types | A passing test or authorization to resume |
| `infrastructure_error` | Another caught primary pipeline exception | A more specific cause that was not recorded |

QEMU can exit with code `0` before its debugger endpoint is ready; this is still
an observed early exit, not successful firmware completion. A `0` debugger or
version-probe code does not support the adapter's `tool_exit` label. Negative exit
codes are retained as numbers without guessing a signal, memory limit or guest
failure cause.

The renderer checks exact shape, version, field types, bounded known strings,
backend identity and status/phase/tool/code relationships. For example, a timeout
object attached to `passed`, a GDB exit attached to QEMU startup, an unsupported
assertion category or an integer-like Boolean is not displayed as an established
cause. These are consistency checks on retained declarations, not source or archive
authentication.

## Build, assertion and cleanup limits

The RV32 execution path accepts an ELF and does not compile firmware. Its new
section therefore says **Build outcome: not assessed**. Existing preparation and
compiler diagnostics are not replaced, and no build result is inferred from
runtime output.

The configured `failure_flag` identifies the configured condition. It is not
necessarily a C assertion, CPU exception or vulnerability. The display explicitly
states that an assertion cause is not established by that flag. A host-side
`AssertionError`, or log text containing `assert` or `TimeoutError`, cannot supply
a guest assertion or timeout verdict.

This object describes the **primary caught pipeline failure**, not every possible
failure. Import, validation or tool-selection errors occurring before the existing
recording boundary retain their established generic handling. Cleanup-only errors
also retain their existing evidence without inventing a primary phase. When cleanup
fails after a primary timeout, the timeout remains primary metadata and cleanup
failure stays visible in the separate existing cleanup fields. Original control-flow
exceptions, terminal statuses, limits, inputs and cleanup execution remain unchanged.

The full result JSON naturally retains the optional field through existing
persistence and export. The readable exported report's existing summary format is
not changed by this batch; do not promise that its text includes the new desktop
section. No new report-export controls are added.

## Regression coverage and unsuccessful attempt

The [adapter regressions](../../tests/backends/test_riscv_diagnostics.py) use only
invented temporary bytes, process doubles and controlled parser/validation seams.
They cover safe and triggering observations, probes, startup/debugger deadlines,
explicit exits, invalid completion, identity changes, generic exceptions,
cancellation, persistence/export and cleanup. Their mocked normal-path labels do
not establish real firmware execution.

The [diagnosis tests](../../tests/product/test_diagnosis.py) exercise strict and
ambiguous metadata, misleading log wording, bounded read-only rendering and evidence
immutability. The [desktop tests](../../tests/desktop/test_universal.py) reuse the
existing view/controller fixtures for fresh and reopened results, stale-detail
clearing and non-executing plain-text inspection.

The pre-change focused selection passed **118 tests in 4.89 seconds**. The first
combined implementation run then reported **202 passed, 1 failed in 5.39 seconds**:
the new section pushed a retained `WinError 267` beyond the first 1,024 characters
expected by an existing preview regression. The fix moved the new section after
the existing retained diagnostics; the old assertion was preserved unchanged.
A later intermediate combined selection passed **206 tests in 5.05 seconds**
before the final additional producer tests. These intermediate counts are not the
final delivery result and are not additive.

### Final validation record

Actual final Linux validation used the existing trusted Python 3.12.14 environment
with Qt offscreen. No dummy Qt implementation replaced the installed PySide6 UI.

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/backends/test_riscv_diagnostics.py tests/product/test_diagnosis.py \
  tests/product/test_compiler_diagnostics.py tests/desktop/test_universal.py
```

**208 passed**, zero failed/errored/skipped/deselected, **6.26 seconds**.

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/backends/test_riscv_diagnostics.py tests/backends/test_backends.py \
  tests/backends/test_records_security.py tests/product/test_diagnosis.py \
  tests/product/test_run_review.py tests/product/test_backend_services.py \
  tests/product/test_compiler_diagnostics.py tests/product/test_packaging_universal.py \
  tests/product/test_build_inputs.py tests/desktop/test_universal.py \
  tests/desktop/test_window.py tests/desktop/test_batch29_diagnostics.py \
  tests/desktop/test_batch29_universal.py
```

**479 passed, 21 skipped**, zero failed/errored/deselected, **11.15 seconds**.
The existing required-tool checks produced these skips, with no test disabled:

| Existing test location | Skips | Recorded reason |
|---|---:|---|
| `test_backends.py:23` | 11 | Missing `iverilog,vvp` |
| `test_backends.py:143` | 3 | Missing `riscv64-unknown-elf-gcc,qemu-system-riscv32,gdb-multiarch` |
| `test_backends.py:157` | 1 | Same missing RV32 toolchain/runtime |
| `test_backends.py:23` | 3 | Same missing RV32 toolchain/runtime |
| `test_backends.py:23` | 1 | Missing `qemu-system-arm,arm-none-eabi-gdb` |
| `test_backends.py:23` | 1 | Missing `riscv64-unknown-elf-gcc` |
| `test_records_security.py:517` | 1 | Actual ARM tools unavailable |

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_packaging.py
```

**4 passed**, zero failed/errored/skipped/deselected, **5.06 seconds**. These build
temporary wheel/source distributions and check installed Python resources, CLI
entry points and worker imports outside the checkout. They are not frozen/native
installer acceptance. Selections overlap and are not a complete project suite.

The synthetic producer suite contains 32 cases, including empty version output
remaining a generic infrastructure error and exact diagnostic preservation in
exported JSON/checksums without changing the original result bytes/mtime.
Independent source review found no blocking defect in the bounded scope. Static
checks passed: five Python AST parses, whitespace across all eight changed files,
167 local documentation links, 23 anchors and 101 existing commit references.
`git diff --check` passed; new untracked files were inspected and checked separately.

Actual runtime tools are unavailable in this Linux environment: QEMU, ARM/RISC-V
compiler/GDB tools and Icarus components required by the existing real-execution
tests were not found. Their missing-tool skips are limitations, not passes. Linux
offscreen Qt tests and synthetic adapter tests cannot establish native Windows,
WSL, macOS, physical hardware, real ARM/RV32 guest execution, frozen desktop or
installer qualification. No CI result for the new commit is claimed and no workflow
was manually dispatched.

## Compatibility and remaining work

- No ARM execution, evaluator accounting, execution-signature, strategy, benchmark
  predicate, production admission, runtime pin, signing rule or frozen research
  change is included.
- Existing outcomes and bounded execution/cleanup behavior remain authoritative.
  Diagnostic text cannot promote an infrastructure failure to a trigger or pass.
- New metadata is additive; older archives remain readable, with unavailable fields.
  There is no SQLite migration or rewrite of saved results.
- Retained logs may contain private paths or supplied metadata. Continue reviewing
  exports before publication. The new structured fields contain only fixed phase,
  category, tool and numeric exit facts, not new environment or credential captures.
- Existing path/resource controls are retained. This adds no hostile-input sandbox,
  signature trust, independent runtime attestation or public-release approval.

The next useful validation is the unchanged real RV32 workflow on a separately
available compatible, trusted QEMU/GDB environment, preserving actual failure,
completion, cancellation and cleanup evidence. Windows validation requires real
native Windows evidence and existing admission; QEMU 11.1.3 is not promoted here.
