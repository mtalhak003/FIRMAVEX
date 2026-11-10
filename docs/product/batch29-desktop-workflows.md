# Batch 29 — Desktop project, readiness and export workflows

Implementation: [`feb1fab8b65d3626a4389a2cc1424cd8f352d01f`](https://github.com/mtalhak003/FIRMAVEX/commit/feb1fab8b65d3626a4389a2cc1424cd8f352d01f),
from baseline `677bb7e94097ed9512be200ffb544350b4c4523e`.
Report date: November 10, 2026 (UTC). This is a desktop usability update, not a
runtime qualification, installer release or new research experiment.

## Create or open an ARM project

Launch the existing installed **FIRMAVEX Desktop** application. For a source
installation, the existing `firmavex-desktop` command opens the same application;
see [installation](install.md) and [the unified desktop guide](unified-desktop.md).

1. Choose **File → New project** or **New firmware project** on Welcome. The form
   now clears the previous project/result selection and prepares a fresh import.
   Unsaved editor changes require an explicit discard decision; **No** is the
   default. Saved project files and results are retained. New Project cannot reset
   the project while work is active.
2. Select an ELF and review the input, ready, completion and failure bindings.
   **Check selected ELF without running** uses the existing ELF validator in a
   background task. It checks the selected import image, with no tool probes,
   project creation or firmware execution. Editing the image/bindings invalidates
   the displayed check. This is static validation, not peripheral compatibility
   or evidence that the firmware runs correctly.
3. Choose a fresh project folder and **Import into new project**. When a project
   is already open, Save and Run continue to use its pinned image. Choosing a
   different import ELF does not replace that image; create a separate project
   or use the existing new-build workflow.
4. **Open project…** and **Open selected recent project** retain the existing
   project-validation behavior. **Remove from recent list** removes one shortcut.
   **Clear recent shortcuts…** explicitly resets only shortcut preferences,
   including a damaged preference index. Its confirmation defaults to **No**;
   project directories and saved results are never deleted by this action.

The ARM boundary remains Cortex-M3, QEMU **mps2-an385**, ELF32 little-endian,
documented uint32 bindings and ready/completion synchronization. BIN files,
arbitrary MCU/peripheral images and physical hardware remain unsupported. The
original 4 MB Flash / 4 MB RAM example configuration is unchanged.

## Check the selected backend and follow execution state

Use **Backends → Processor and HDL workspace (save current ARM settings)…** for
the existing ARM, RV32 and Verilog workspace. The backend selector now has a
persistent **Runtime readiness** line and input-format guidance. Opening a new
configuration or changing the target resets the readiness display. Preparing an
example does not erase an earlier missing-tool/admission error.

**Check runtime readiness** reports availability only. The worker still checks
compatibility, exact admitted identities and trust before execution. No changed
version/hash gate or automatic approval is introduced. In particular, QEMU
11.1.3 remains production-rejected. Missing tools and failed admission have
specific next actions, without suggesting bypasses.

The workspace distinguishes an active operation, cancellation request, terminal
record and worker-idle state. Late progress cannot replace **Cancellation
requested**. If a completed record races cancellation, its actual outcome is
retained and the cancellation request remains disclosed. A missing/unknown
execution outcome is shown as stopped, not as a passing result. Another operation
cannot start until the worker is idle. Counts and outcome classifications remain
owned by the existing evaluator/backend.

Saved-run controls now scroll at smaller window sizes. Result tabs retain their
full labels with tab-scroll buttons. Opening history does not rerun a target.
This layout was checked with Linux offscreen Qt; it does not establish native
Windows DPI, keyboard, screen-reader or consumer usability acceptance.

## Export and inspect reports

Select a saved result, then use its existing export action to choose a parent for
a fresh export directory. Exports do not execute firmware or overwrite the source
archive. The UI confirms success only after the worker returns a successful
status, the requested destination and the required file/hash metadata.

| Workspace | Readable report | Evidence and integrity files |
|---|---|---|
| ARM project Results | `report.md` | `evidence.json`, `SHA256SUMS` |
| Processor and HDL workspace | `REPORT.md` | `result.json`, `checksums.json`, supported logs/artifacts |

ARM Results shows the confirmed destination and enables **Open exported folder**
only after confirmation. The folder is checked again and opened through the local
OS file manager only on explicit user action. If opening fails, the path stays
visible. Backend export feedback names `REPORT.md` and the checksum inventory;
the saved result stays selected.

A failed/cancelled/rejected export or malformed reply cannot retain an earlier
successful-export indication. Choose a fresh writable destination after inspecting
errors or partial output. GUI confirmation validates reply fields; the existing
export service owns file writes/hashes. Neither is independent proof of guest
execution. Review paths, diagnostics and other private administrative information
before publishing an export.

## Validation performed

Environment: Linux x86_64, kernel 6.18.57, Python 3.12.14, PySide6 6.11.1,
pytest 9.1.1; `QT_QPA_PLATFORM=offscreen`. Results below overlap and must not be
added together. No GitHub Actions workflow was dispatched for this batch.

| Selection/check | Actual result |
|---|---|
| Five new `tests/desktop/test_batch29_*.py` files | **143 passed**, zero skips/failures/errors/deselections |
| `tests/desktop tests/product/test_recents.py` | **389 passed, 16 skipped**, zero failures/errors/deselections |
| Unfiltered `tests/product tests/desktop tests/backends`, before the final layout-only addition | **2,079 passed, 106 skipped, 1 failed, 6 errors**, zero deselections |
| Final product/desktop/backend selection, explicit missing-tool exclusions below | **2,080 passed, 106 skipped, 6 deselected**, zero failures/errors; one integration test excluded at collection |
| Python syntax, ten implementation/test files | PASS |
| Build-input lock/version check | PASS |
| `actionlint -shellcheck=` on `product.yml` and `windows-runtime-candidate.yml` | PASS; ShellCheck unavailable, not run |
| Whitespace, including the five new test files | PASS |

The unfiltered failure and six setup errors all require `arm-none-eabi-gcc`, which
is absent here. QEMU, ARM-capable GDB, the RISC-V compiler and Icarus are also
unavailable. Existing tests were left intact. The final available-environment
selection explicitly excludes the one real-firmware integration test and
deselects six compiler-dependent runtime cases; it is not a complete-suite pass.
The 106 skips include missing compiler/runtime tools, native Windows/macOS cases,
explicit Windows-candidate workflow cases and one unavailable Linux namespace
admission check. The narrower desktop selection has 13 runtime skips, two native
path-identity skips and one Windows-candidate skip.

Commands, from the checkout using an environment with the documented dependencies:

```bash
QT_QPA_PLATFORM=offscreen python -B -m pytest -q \
  tests/desktop/test_batch29_diagnostics.py tests/desktop/test_batch29_exports.py \
  tests/desktop/test_batch29_projects.py tests/desktop/test_batch29_universal.py \
  tests/desktop/test_batch29_window.py
QT_QPA_PLATFORM=offscreen python -B -m pytest -q -ra tests/desktop tests/product/test_recents.py

# Unfiltered check: fails here because ARM GCC is unavailable.
QT_QPA_PLATFORM=offscreen python -B -m pytest -q tests/product tests/desktop tests/backends

# Explicit available-environment selection; these exclusions are NOT CI changes.
QT_QPA_PLATFORM=offscreen python -B -m pytest -q tests/product tests/desktop tests/backends \
  --ignore=tests/product/test_integration.py \
  --deselect=tests/product/test_runtime.py::test_actual_arm_firmware_input_after_startup \
  --deselect=tests/product/test_runtime.py::test_actual_missing_completion_is_failure_despite_trigger \
  --deselect=tests/product/test_runtime.py::test_actual_cancellation_charged_and_aborted
python -B -m tools.check_build_inputs
actionlint -shellcheck= .github/workflows/product.yml .github/workflows/windows-runtime-candidate.yml
```

Two new tests exercise real supervised worker transport/export and real Qt
widgets over **explicitly synthetic saved records**, checking output hashes and
unchanged source archives. They do not execute firmware or constitute native
runtime evidence. Other new tests cover invalid inputs, missing tools, busy/start
rejection, cancellation races, corrupt preferences, path/link rejection,
replacement/interruption failures and empty/malformed result handling.

## Remaining work

Run the unchanged runtime-required checks in an equipped native environment;
do not replace their evidence with synthetic tests. Native Windows verification
of these exact GUI changes, frozen/installed journeys, accessibility, enforced
offline operation, low-disk/recovery and consumer acceptance remain outstanding.
The macOS preview-only restriction, trusted-workload threat model and Batch 28
runtime provenance/qualification blockers remain in force. No new installer,
runtime approval, firmware result or research campaign is delivered by Batch 29.
