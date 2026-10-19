# FIRMAVEX — Windows Sandbox Acceptance Test and Runtime Installer Bug Report

**Test date:** 2026-10-20 (Windows Sandbox local clock)
**Platform:** Windows 11 Pro host, Windows Sandbox guest
**Build:** Batch 11 Windows unsigned candidate, artifact `FIRMAVEX-windows-latest-unsigned-candidate`
**Executable:** `FIRMAVEX-Windows-unsigned.exe`
**Repository:** `mtalhak003/FIRMAVEX`, product branch `product/desktop-batch11`
**Branch HEAD previously recorded:** `72fe794ec391f85ca432ac75110c627a5e267289` (verify against the artifact before asserting binary provenance)

## Scope and limitations

Manual, first-time Windows Sandbox acceptance test. Screenshots were shared in the ChatGPT conversation but were not separately saved on the host. This report records observed UI outcomes; it is **not** a runtime log, traceback, or proof of the underlying root cause. The executable is unsigned, and a checksum match against the ZIP's bundled `SHA256SUMS` does not independently authenticate its publisher. No firmware was executed.

## Results

| Check | Observation | Status |
| --- | --- | --- |
| Archive checksum | PowerShell compared SHA-256 of `FIRMAVEX-Windows-unsigned.exe` to bundled `SHA256SUMS`; result `True` | Pass (internal consistency only) |
| Authenticode | `Get-AuthenticodeSignature` returned `Status: NotSigned` | Expected for unsigned development candidate |
| Windows Sandbox | Sandbox opened successfully on Windows 11 Pro | Pass |
| Application installation | User reported successful installation inside Sandbox | Pass (user-reported) |
| First application launch | FIRMAVEX Desktop GUI displayed | Pass |
| ARM runtime detection | `Required tool not found: qemu-system-arm (missing_dependency)` | Pass: missing dependency identified |
| Automatic runtime setup | After ticking consent checkbox and selecting `Install / repair runtime automatically`, UI displayed `Worker failure: Execution service raised an unexpected exception.` | **FAIL / BLOCKER** |
| Internet reachability | Official `https://www.msys2.org/` loaded in Edge inside Sandbox | Pass for website access; does not prove download endpoints work |
| Runtime inventory check | GUI showed `{ "firmware_executed": false, "generations": [], "success": true }` | Inventory check succeeded, **zero generations** |
| Application Event Viewer | Filtering Application log to Critical/Error showed one Security-SPP event 8198 concerning Windows license activation | No obvious FIRMAVEX crash event found; not conclusive |
| App local folder | `%LOCALAPPDATA%\FIRMAVEX` contained `runlogs` folder, reportedly empty | No run log found |
| Results & reproduction | `No run selected`, `No result available`, `Execution evidence: unavailable`; `Export report evidence` disabled; Evidence diagnostics tab empty | No run evidence to export |
| Firmware execution | Not attempted because QEMU runtime unavailable | Not tested |

## Reproduction steps

1. On Windows 11 Pro, enable and open Windows Sandbox.
2. Copy extracted Batch 11 unsigned candidate executable into Sandbox.
3. Install and launch FIRMAVEX Desktop.
4. Open first-launch setup and navigate to **2. Check or install the execution runtime**.
5. Check existing runtime; observe missing `qemu-system-arm`.
6. Tick **Download MSYS2 from its publisher and install signed QEMU (ARM/RV32), GDB and Icarus packages**.
7. Click **Install / repair runtime automatically**.
8. Observe: `Worker failure: Execution service raised an unexpected exception.` The main window status bar showed `worker_failure: Execution service raised an unexpected exception.`

**Expected:** Installer either downloads and verifies trusted runtime components, installs them and reports readiness, or provides an actionable error with a diagnostic record, without disabling signature checks.

**Actual:** Generic worker exception; no installed runtime generation was subsequently listed; QEMU remained unavailable. No traceback was surfaced in the screenshots.

## Codex investigation assignment

Investigate the Windows automatic runtime install/repair path on `product/desktop-batch11` **without modifying the frozen research `main` branch**. Treat this report as field evidence, not a root-cause diagnosis.

1. Trace GUI button → execution service/worker → MSYS2 bootstrap/download → signature/inventory verification → package install → runtime registration. Identify how an exception can be raised and why only the generic `worker_failure` message reaches the UI.
2. Attempt a controlled reproduction on Windows or Windows Sandbox if available; otherwise explicitly distinguish code-based hypotheses from a verified reproduction. Check proxy/TLS/network endpoints, subprocess invocation, Windows paths/permissions, temporary folders, packaged resource availability, and worker exception serialization, based on actual code evidence.
3. Improve **safe diagnostic capture** for failures occurring before a firmware run exists: actionable UI message, sanitized traceback/error classification, exportable installation diagnostic file in a documented user-writable location. Do not expose secrets, disable signature checks, or auto-trust downloaded executables.
4. Fix the verified cause if found, add focused regression tests for the failure path and diagnostic/export behavior, and run relevant Windows CI and installer tests.
5. Document changed files, tests and results, limitations, remaining approval gates, and precise steps to retest in a fresh Sandbox. Do not claim firmware execution, successful runtime installation, or public-beta readiness until verified.

## Release assessment

**Windows desktop install and first launch are promising; automatic runtime provisioning is blocked.** This manual test does not establish successful ARM, RV32, or HDL execution. Continue treating the build as an unsigned, non-public development candidate.
