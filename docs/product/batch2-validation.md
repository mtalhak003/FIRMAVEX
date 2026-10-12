# Batch 2 desktop delivery validation

Development branch: `product/desktop-batch2`, based on Batch 1 commit
`d0a42c79fd20172184135d1ccf6d2ab8907a7c69`. Main is not merged or rewritten.
The distribution version is `0.2.0.dev1` (alpha).

## Actual Linux checks

| Check | Observed result |
| --- | --- |
| Starting Batch 1 complete suite | 1,762 passed |
| Final desktop/product selection | 546 passed, 4 native-Windows checks skipped |
| Final complete suite | 1,911 passed, 4 native-Windows checks skipped; 194.82 seconds |
| Fresh Python 3.11 selected product/GUI checks | 440 passed, 3 native-Windows checks skipped |
| Fresh Python 3.11 packaging/startup/window checks | 31 passed |
| Original Batch 1 Ubuntu 3.11 CI selection reproduced from its Git archive | 251 passed |
| Wheel/source build | Passed with isolated build backend |
| Fresh wheel and real desktop dependencies installed outside checkout | Passed |
| Installed console desktop smoke/startup outside checkout | Passed; no firmware dispatch |
| Source and new-file whitespace checks | Passed |
| CI summary helper | Preserves passing and intentionally failing exit statuses |

The final three added configuration-snapshot regressions are included in the
546/1,911 results. Python 3.11 selections precede those three regressions and are
reported separately rather than added together as one suite count.

Local tools: Python 3.12.14, PySide6 6.12.0, ARM GCC 14.2.1, QEMU 10.0.13,
GDB Multiarch 16.3, pyelftools 0.33. The separate interpreter was Python 3.11.16.
These checks do not establish native Windows/macOS ARM execution or WSLg usability.

## Actual desktop firmware workflow

The offscreen Qt integration test uses the real controller, worker, compiler,
QEMU, GDB, evaluator, and independent product example. It builds/imports a project,
searches, reproduces, exports, and cancels a fresh admitted execution. A GUI timer
continues firing throughout; cancellation/shutdown do not block the event loop.

- Search observes the declared `[2, 1]` trigger at charged attempt 10: nine
  ordinary completions plus one triggering completion, with no infrastructure error.
- Bounded reproduction records three matching completed observations.
- A separate execution with an unreachable completion point is explicitly
  cancelled after admission: one charged attempt, one infrastructure failure,
  zero completed observations, and an aborted evaluator. It is not safe firmware.
- All completed receipts retain dispatch/input readback/completion/image/tool
  identities and cleanup. Their 26 QEMU/GDB child PIDs are reaped/absent when checked.
- Export and screenshot capture do not dispatch firmware or alter source archives.

These are 14 charged attempts across three independent jobs, not independently
verified physical hardware executions. They are not a performance campaign.

The result screenshot uses an actual completed archive copied from a desktop
integration test; original receipt/provenance contents remain unchanged. Its ELF
SHA-256 is `4bce823cd0242e06df7a00f1c1cdcc21b473d328799ebf61069f10c474ab3ed4`.
Private copy context/evidence are outside Git at
`/workspace/firmavex-batch2-demo-evidence/`; they are not research results.

## Implemented safeguards and remaining limits

The GUI exposes import, versioned configuration, runtime checks, actual worker
execution, live recent observations, cancellation, result/report views, bounded
reproduction, read-only inspection/export, and explicit recovery/restart.
Filesystem-heavy project operations use background tasks. Runs use immutable
command configurations so later edits by another window cannot alter admission.

Windows Job Objects use kill-on-close descendant ownership before the first
worker command. Four native Windows checks (host process ownership and precise file metadata)
are skipped on Linux. They run on native Windows in the verified CI matrix. Firmware dispatch
remains blocked on Windows until native ARM qualification. macOS execution and
standalone installers remain unverified. No signed Windows/macOS installer or
bundled QEMU/GDB/ARM toolchain is delivered.

Other limits: supported compatible Cortex-M3 ELF only; no BIN or hardware;
no partial strategy-state continuation; no atomic filesystem/database snapshot;
no qualification of power loss/network filesystems; wrappers do not inventory
all dependent libraries; imported ELF hashes do not establish source/build provenance;
bounded signatures are not coverage or complete-path proof. GUI simulations remain
explicitly synthetic and cannot claim real firmware evidence.

## GitHub Actions evidence

Batch 1 run `38166140242` was observed as failed through GitHub's public HTML.
Public annotations show exit-code failures, but detailed logs require sign-in;
REST/gh API reads returned Forbidden. A fresh local 3.11 reproduction passing
251 tests does not erase that failure or prove its cause.

Batch 2 improves declared build dependencies, installed GUI/package checks,
native host supervision tests, and public JUnit-based failure summaries. Remote Batch 2 run [38255127322](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38255127322)
completed successfully for code commit `84c0561f7798ffc45096a9df6da40cd6129dd3e8`: all six
Windows/macOS/Linux Python 3.11/3.12 matrix jobs and the actual Ubuntu firmware
regression job passed. Native host-process ownership, precise file metadata,
Qt tests, package installation, and desktop smoke checks passed in that matrix.
This does not qualify Windows/macOS ARM firmware execution or native installers.
The initial failed Windows checks revealed mismatched stat/fstat metadata,
UTF-8 test decoding, and inappropriate reads of an OS-locked control byte.
Native Win32 path/handle queries now use the same precise metadata source;
data-file comparison and UTF-8 checks remain strict.
No main/research campaign is launched to obtain these checks.

## Research preservation

No changes to `src/firmavex`, research firmware, ground truth, frozen protocols,
archives, or original result files. The canonical research import namespace remains
`src.firmavex`. CLI behavior is regression-tested; the new desktop/build commands
and optional cancellation support are additive product functionality.

## Exact changed files

- `.github/workflows/product.yml`
- `MANIFEST.in`
- `README.md`
- `docs/product/batch2-validation.md`
- `docs/product/desktop.md`
- `docs/product/screenshots/actual-example-result.png`
- `docs/product/screenshots/welcome.png`
- `firmavex/__init__.py`
- `firmavex/desktop/__init__.py`
- `firmavex/desktop/app.py`
- `firmavex/desktop/controller.py`
- `firmavex/desktop/projects.py`
- `firmavex/desktop/window.py`
- `firmavex/product/cli.py`
- `firmavex/product/example.py`
- `firmavex/product/file_state.py`
- `firmavex/product/firmware.py`
- `firmavex/product/protocol.py`
- `firmavex/product/services.py`
- `firmavex/product/store.py`
- `firmavex/product/supervisor.py`
- `firmavex/product/tools.py`
- `firmavex/product/windows_job.py`
- `firmavex/product/worker.py`
- `pyproject.toml`
- `tests/desktop/conftest.py`
- `tests/desktop/test_app.py`
- `tests/desktop/test_controller.py`
- `tests/desktop/test_projects.py`
- `tests/desktop/test_real_firmware.py`
- `tests/desktop/test_window.py`
- `tests/product/test_desktop_jobs.py`
- `tests/product/test_file_state.py`
- `tests/product/test_packaging.py`
- `tests/product/test_store.py`
- `tests/product/test_supervisor.py`
- `tests/product/test_windows_job.py`
- `tools/product_ci_tests.py`
