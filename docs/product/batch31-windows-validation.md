# Batch 31 — native Windows desktop validation

Batch 31 starts at `bd875f22cc2604a7e397166177cd82c6e81bc07f`.
Implementation and regressions:
[`31037ac904ed0affb1e3359781d40ebd546fc56d`](https://github.com/mtalhak003/FIRMAVEX/commit/31037ac904ed0affb1e3359781d40ebd546fc56d).
This procedure uses the user's **existing Windows verification checkout**, a
normal user account and fresh outputs outside that checkout. It does not run a
research campaign, repair missing research evidence or authorize a runtime
promotion. Run it in **native Windows PowerShell 7**, not WSL, to collect Windows
evidence. A Linux offscreen Qt pass is a different evidence class.

## Implemented corrections and coverage

New regressions reproduced two source-GUI defects before repair: Open/recent
project selection could discard unsaved edits without confirmation, and verified
project adoption could retain another project's result/export selection. The
desktop now shares the existing default-**No** discard confirmation across New,
Open/recent and both example entry points. A failed open/preparation retains the
current editor and selected result. Successful project adoption clears the
previous result/export/progress presentation; saved files and authoritative
execution accounting are retained.

This is a targeted transition fix. It does not introduce a universal unsaved-edit
guard for Quit or every separate backend-to-ARM configuration handoff. Check those
paths explicitly during consumer validation; do not assume they are covered by
the new confirmation tests.

The two new test files contain 28 cases: 17 failure/retry GUI journeys, five
portable filesystem/Qt checks, and six native-Windows cases. The native cases use
actual Win32 sharing/readonly attributes, a separate interpreter holding a Windows
project byte-range lock, and native case normalization. The Qt URL-routing test
captures a local URL without launching Explorer; the manual checklist must
establish actual shell/file-manager behavior. Readonly/sharing tests do not
establish all ACL or standard-user permission scenarios.

## What is covered and what is not yet established

| Scope | Existing coverage and Batch 31 action | Evidence boundary |
|---|---|---|
| Project/import/static checks, unsaved edits, recents, errors and export | Batch 29 tests plus Batch 31 workflow/path regressions below; real Qt and filesystem operations, with explicitly synthetic controller/archive cases where used | Host/UI behavior, not guest execution |
| Windows sharing/locking, path spelling and local file URLs | Native-only cases in `test_windows_desktop_paths.py`; skipped on other hosts | Only an actual Windows run can establish those observations |
| Real source ARM workflow | Existing compiler-free `test_real_builtin.py`, synchronization regression and strict production admission | Requires the exact qualified tools; missing/rejected tools must not become skips with the required-runtime flag |
| Frozen and installed application | Existing PyInstaller/entry points, compiler-free demo and receipt verifier | Must be repeated for the exact reviewed build; source tests do not establish these paths |
| Consumer experience | Manual checks below, including visible GUI, offline operation, Windows permissions and recovery | Hosted/offscreen Qt and installer smoke do not establish human usability or clean-machine acceptance |

Historical Windows native/installer results remain scoped to their old revisions.
Candidate QEMU **11.1.3 remains production-unqualified**. Original Batch 27 ZIP
verification is user-reported, not new Batch 31 execution evidence. See the
[evidence register](../development/history-sources.md) and
[Batch 29's exact Linux limitations](batch29-desktop-workflows.md#validation-performed).

The existing [product matrix](../../.github/workflows/product.yml) already selects
`tests/desktop` on native Windows Python 3.11/3.12. Its synthetic/host stage will
include the new test files automatically; no workflow edit or manual dispatch is
needed for that selection. The separate
[unified native workflow](../../.github/workflows/unified-desktop.yml) and
[distribution workflow](../../.github/workflows/desktop-distribution.yml) cover
different runtime/frozen/installed scopes. Their presence is not a current pass.

## 1. Verify the checkout and run host/UI regression tests

Open PowerShell 7 in the existing verification checkout. Paste the **full reviewed
Batch 31 commit SHA from the delivery report** when asked. This block does not
fetch, pull, reset, change branches or inspect private evidence. It stops on a
mismatched revision/branch. Adjust only the virtual-environment path if the
existing Windows environment has a different name.

```powershell
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Native Windows PowerShell 7 is required; WSL is not Windows validation.' }
$Repo = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Open PowerShell in the existing verification checkout.' }
if (-not [IO.Path]::GetFullPath((Get-Location).Path).Equals([IO.Path]::GetFullPath($Repo), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Open PowerShell at the verification checkout root before continuing.'
}
$ExpectedHead = Read-Host 'Paste the full reviewed Batch 31 commit SHA'
if ($ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { throw 'A full lowercase Git SHA is required.' }
$Head = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $Head -cne $ExpectedHead) { throw 'Wrong checkout revision; stop without altering it.' }
$Branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $Branch -cne 'product/desktop-batch11') { throw 'Use the existing development verification checkout.' }
$Status = @(& git status --short --untracked-files=all -- . ':(exclude)evidence/**')
if ($LASTEXITCODE -ne 0 -or $Status.Count -ne 0) { throw 'Checkout has changes; preserve them and stop.' }
$Python = (Resolve-Path '.venv\Scripts\python.exe').Path
$Out = Join-Path $env:LOCALAPPDATA ('FIRMAVEX-Batch31\' + (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N'))
$RepoRoot = [IO.Path]::GetFullPath($Repo).TrimEnd([IO.Path]::DirectorySeparatorChar)
$OutputRoot = [IO.Path]::GetFullPath($Out)
if ($OutputRoot.Equals($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $OutputRoot.StartsWith($RepoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Validation outputs must be outside the checkout; choose another verification location.'
}
New-Item -ItemType Directory -Path $Out | Out-Null
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE. Preserve $Out and inspect the output." }
}
$Head | Set-Content -Encoding utf8 (Join-Path $Out 'source-revision.txt')
Invoke-Checked $Python @('-B', '-m', 'tools.check_build_inputs')
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTEST_QT_API = 'pyside6'
$env:FIRMAVEX_CI_DIAGNOSTICS = Join-Path $Out 'host-diagnostics'
Start-Transcript -Path (Join-Path $Out 'host-console.txt') | Out-Null
try {
    Invoke-Checked $Python @('-B', '-m', 'tools.product_ci_tests', '--ci-watchdog', '-q',
        'tests/desktop/test_batch29_diagnostics.py', 'tests/desktop/test_batch29_exports.py',
        'tests/desktop/test_batch29_projects.py', 'tests/desktop/test_batch29_universal.py',
        'tests/desktop/test_batch29_window.py', 'tests/desktop/test_batch31_workflows.py',
        'tests/desktop/test_windows_desktop_paths.py')
} finally { Stop-Transcript | Out-Null }
Write-Host "Private validation output: $Out"
```

The existing test launcher retains bounded per-test diagnostics, a JUnit XML and
the complete child-test log under `$Out\host-diagnostics`; the console tail is not
the full transcript. Preserve actual PASS/FAIL/SKIP counts. Any native-only skip
means that specific behavior is not proven; optional symlink/8.3 availability is
not guaranteed by every Windows volume/account. A successful selection does not
make its synthetic observations real firmware results.

If the build-input check fails, stop and review the active environment. For a
deliberate dependency setup in that verification environment, use the same locked
installation as CI, then repeat the check and tests:

```powershell
Invoke-Checked $Python @('-m', 'pip', 'install', '--only-binary=:all:', '--require-hashes', '-r', 'packaging/build-requirements.lock')
Invoke-Checked $Python @('-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '.')
Invoke-Checked $Python @('-B', '-m', 'tools.check_build_inputs')
```

Internet/package-cache access is needed for dependency installation only. Do not
interpret these commands as evidence of offline execution or a Python-free install.

## 2. Run actual source ARM checks only with an admitted runtime

Keep the absolute `$Python` path from step 1; adding MSYS2 to PATH must not select
another Python interpreter. Required runtime components are the existing
checksum-qualified Windows x64 QEMU **11.1.2** / ARM-capable GDB **18.1** with their
compatible trusted dependencies. These commands do not acquire or downgrade
packages. A current rolling MSYS2 install may be rejected; do not change pins,
digests or candidate flags to make it pass.

```powershell
foreach ($Name in @('FIRMAVEX_QUALIFY_BACKENDS', 'FIRMAVEX_RUN_WINDOWS_CANDIDATE')) {
    if ([Environment]::GetEnvironmentVariable($Name)) { throw "Candidate-only environment is active: $Name. Stop and review it." }
}
Invoke-Checked $Python @('-B', '-c', 'import json; from firmavex.product.tools import discover; from firmavex.product.platform_support import require_native_support; tools=discover(); require_native_support(tools); print(json.dumps(tools.to_dict(),sort_keys=True))')
$env:FIRMAVEX_REQUIRE_RUNTIME = '1'
$env:FIRMAVEX_CI_DIAGNOSTICS = Join-Path $Out 'real-arm-diagnostics'
Start-Transcript -Path (Join-Path $Out 'real-arm-console.txt') | Out-Null
try {
    Invoke-Checked $Python @('-B', '-m', 'tools.product_ci_tests', '--ci-watchdog', '-q',
        '--firmavex-test-timeout=225', 'tests/desktop/test_real_builtin.py',
        'tests/product/test_runtime.py::test_actual_bundled_mps2_startup_and_behavior')
    Invoke-Checked $Python @('-B', '-m', 'tools.desktop_ci_demo', '--builtin', '--output-dir', (Join-Path $Out 'source-demo'))
    Invoke-Checked $Python @('-B', '-m', 'tools.desktop_native_evidence', (Join-Path $Out 'source-demo'))
} finally { Stop-Transcript | Out-Null }
```

Expected defined example: search trigger `[2, 1]` at **10 charged evaluator
attempts**, reproduction **3 matching observations**, zero infrastructure failures,
and verified per-attempt completion/cleanup receipts. The evidence helper rejects
synthetic labels, wrong vectors/counts or incomplete receipts. It checks this
specific example; it is not general hardware, sandbox or security qualification.
`test_real_builtin.py` separately exercises GUI import/open, bounded cancellation,
reproduction/export and persisted outcomes. No compiler is required for these
bundled-image checks. Source-building tests additionally need ARM GCC.

The exact current executable versions/digests are enforced by
[`platform_support.py`](../../firmavex/product/platform_support.py); successful
version probes alone do not qualify their full DLL/package closure. If admission
fails, retain its expected/observed diagnostics and mark actual product execution
**BLOCKED**, leaving the failure visible. Do not continue to positive execution.

For RV32/Verilog, only when their documented runtimes are already admitted, run
the existing `tests/desktop/test_real_universal.py` with both
`FIRMAVEX_REQUIRE_RUNTIME=1` and `FIRMAVEX_REQUIRE_BACKENDS=1`. Missing tools or a
rejected profile must fail visibly. Do not enable `FIRMAVEX_QUALIFY_BACKENDS`.
HDL testbench PASS/FAIL and waveforms are distinct from firmware search outcomes.

## 3. Frozen and installed paths are separate checks

First complete the admitted source path. A reviewed matching Windows build is
required; Linux binaries are not substitutes. The locked build dependencies
include PyInstaller. Build a **local unsigned candidate**, outside existing output
directories, without releasing or dispatching CI:

```powershell
Invoke-Checked $Python @('-m', 'PyInstaller', '--clean', '--noconfirm',
    '--workpath', (Join-Path $Out 'freeze-work'), '--distpath', (Join-Path $Out 'frozen'), 'packaging/desktop.spec')
$Frozen = Join-Path $Out 'frozen\FIRMAVEX'
$Gui = Join-Path $Frozen 'FIRMAVEX-Desktop.exe'
$Engine = Join-Path $Frozen 'FIRMAVEX.exe'
Get-FileHash -Algorithm SHA256 $Gui, $Engine | Format-Table
$Smoke = Start-Process -FilePath $Gui -ArgumentList '--smoke-test' -PassThru
if (-not $Smoke.WaitForExit(30000)) {
    $Smoke.Kill($true); $Smoke.WaitForExit(10000) | Out-Null
    throw 'Frozen startup timed out; preserve diagnostics and stop.'
}
if ($Smoke.ExitCode -ne 0) { throw "Frozen startup failed: $($Smoke.ExitCode)" }
Invoke-Checked $Engine @('--firmavex-cli', 'demo-builtin', '--output-dir', (Join-Path $Out 'frozen-demo'))
Invoke-Checked $Python @('-B', '-m', 'tools.desktop_native_evidence', (Join-Path $Out 'frozen-demo'))
```

The embedded engine/worker runs without a separate child Python installation;
the Python evidence helper remains an administrator-side validator. GUI smoke
does not test execution controls. Repeat the manual checklist below using the
frozen GUI with the ordinary graphical Qt platform, not offscreen mode.

For an **installed** path, use a separately approved matching installer/artifact
on a disposable Windows user/VM. It must pass host security policy; do not disable
Smart App Control, Defender or signature enforcement. The present installer is
unsigned. Inno Setup 6 is needed to build it, not to use a downloaded installer.
Review the package hashes/provenance and the intended destination before installing.
Do not automatically replace an existing personal FIRMAVEX installation.

After installation, explicitly select the installed path and confirm it is the
matching candidate before calling it:

```powershell
$Installed = Join-Path $env:LOCALAPPDATA 'Programs\FIRMAVEX'
$InstalledGui = Join-Path $Installed 'FIRMAVEX-Desktop.exe'
$InstalledEngine = Join-Path $Installed 'FIRMAVEX.exe'
foreach ($Pair in @(@($Gui, $InstalledGui), @($Engine, $InstalledEngine))) {
    if ((Get-FileHash $Pair[0] -Algorithm SHA256).Hash -cne (Get-FileHash $Pair[1] -Algorithm SHA256).Hash) {
        throw 'Installed executable differs from reviewed frozen candidate; stop.'
    }
}
$Smoke = Start-Process -FilePath $InstalledGui -ArgumentList '--smoke-test' -PassThru
if (-not $Smoke.WaitForExit(30000)) {
    $Smoke.Kill($true); $Smoke.WaitForExit(10000) | Out-Null
    throw 'Installed startup timed out; stop.'
}
if ($Smoke.ExitCode -ne 0) { throw "Installed startup failed: $($Smoke.ExitCode)" }
Invoke-Checked $InstalledEngine @('--firmavex-cli', 'demo-builtin', '--output-dir', (Join-Path $Out 'installed-demo'))
Invoke-Checked $Python @('-B', '-m', 'tools.desktop_native_evidence', (Join-Path $Out 'installed-demo'))
```

Executable equality is a narrow build check, not complete installed-file or
publisher authenticity verification. Preserve original build identities and
native receipt inventories. Existing CI-owned lifecycle scripts use temporary
installations and sentinels; do not blindly run
[`test_windows_install.ps1`](../../packaging/test_windows_install.ps1) against an
ordinary user's existing installation. Same-package reinstall is not a
distinct-version upgrade or rollback proof. The
[versioned-installer workflow](../../.github/workflows/versioned-install.yml) and
[consumer checklist](consumer-acceptance.md) retain those separate requirements.

## 4. Visible consumer-machine checklist

Remove only the offscreen setting used above before interactive launch:
`Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue`. Run the source GUI
with `& $Python -B -m firmavex.desktop.app`; run the frozen/installed GUI from its
reviewed shortcut/executable. Record tester, Windows build/architecture, standard
user identity class, scaling, source/build hashes and actual PASS/FAIL/BLOCKED:

1. Create/import a compiler-free example in a new folder with spaces/non-ASCII
   characters. Static check should finish responsively. Open/reopen that project;
   edit settings, then test New, Open/recent and both example actions. Reject then
   explicitly accept discard. A failed open must preserve edits and the old
   result; successful adoption must clear stale result/export/progress selection.
   Confirm original project/results remain unchanged. Separately record behavior
   on Quit and configuration handoff, without assuming a new guard there.
2. Use damaged recent preferences only in an isolated test data copy. Clear the
   shortcuts with confirmation; missing/locked/unwritable directories must give an
   actionable error and permit retry without deleting results.
3. Check missing/rejected tools. Preserve exact error categories and admission
   diagnostics. With the admitted runtime, run the example and inspect progress,
   exact trigger, charged accounting, saved history, reproduction and cancellation.
   A cancelled/incomplete result must never be presented as a passing execution.
4. Export to a fresh folder; check required report/evidence/checksum files. Select
   **Open exported folder** and observe the correct local Explorer directory.
   Exercise an invalid/unwritable destination and a sharing lock on disposable
   copies; failed export must not retain an earlier success indication. Reopen
   saved results after closing the application and compare hashes.
5. Test keyboard-only navigation, focus, tab scrolling and 100%/150%/200% scaling.
   Check long paths/messages, high contrast and a screen reader with a human.
   Offscreen assertions do not establish these acceptance results.
6. After dependencies are installed, enforce offline operation in the disposable
   environment and repeat local example/reproduction/export; record the actual
   network control. A product with no intentional network calls is not measured
   proof that the whole host was offline.
7. In a disposable installation only, exercise reinstall/uninstall while projects
   and real saved archives remain elsewhere. Independently compare their hashes.
   Keep distinct-version upgrades, low disk, interrupted installation and rollback
   separately marked UNTESTED until exercised with a declared recovery procedure.

Do not alter original archives or private Windows evidence to obtain a pass.
Logs and transcripts can contain local paths; keep them private pending review.
No Batch 31 step grants public-release readiness or approves a new runtime.

## Validation performed in this development environment

Report date: **November 11, 2026, Asia/Karachi**. The environment is Linux x86_64,
Python 3.12.14, PySide6 6.11.1 and pytest 9.1.1. Native Windows, PowerShell,
QEMU/GDB, ARM GCC, the RISC-V compiler and Icarus are unavailable. No actual guest
execution, Windows installer, frozen Windows application or Windows consumer
trial was run. PowerShell commands were reviewed against existing entry points;
they were not parsed or executed by a PowerShell interpreter here.

| Selection | Actual result | Boundary |
|---|---|---|
| Existing five Batch 29 test files, before changes | 143 passed; zero skipped/failed/errors/deselected | Baseline Linux offscreen regression |
| Initial targeted dirty-open/project-switch reproducer | 3 failed | Demonstrated the two GUI defects before repair; no guest execution |
| Two new Batch 31 test files | 22 passed, 6 skipped; zero failures/errors/deselections | Six native-Windows cases skipped honestly; synthetic controller feedback remains synthetic |
| Desktop and recent-project tests | 411 passed, 22 skipped; zero failures/errors/deselections | 13 missing-runtime cases, three pre-existing native/candidate cases, six new Windows cases skipped |
| Unfiltered product/desktop/backend suites | 2,102 passed, 112 skipped, 1 failed, 6 setup errors; zero deselections | Failure/errors require unavailable `arm-none-eabi-gcc`; existing tests unchanged |
| Explicit available-environment selection below | 2,102 passed, 112 skipped, 6 deselected; zero failures/errors | One real-firmware integration test excluded at collection; six compiler-dependent runtime cases deselected; not a full-suite pass |

Selections overlap and are not additive. The broader skips include missing real
compiler/runtime tools, Windows/macOS-only behavior, explicit candidate-workflow
checks and unavailable Linux namespace admission. Syntax/whitespace checks passed
for all three changed/new Python files, as did the locked build-input version
check. Actionlint passed on the existing product, distribution, unified and
candidate workflows with unavailable ShellCheck disabled. No workflow was edited
or dispatched; historical CI results do not validate this revision.

The actual pytest selections used `QT_QPA_PLATFORM=offscreen` and the existing
`/workspace/firmavex-batch7-venv/bin/python -B` interpreter:

```bash
QT_QPA_PLATFORM=offscreen python -B -m pytest -q -ra \
  tests/desktop/test_batch31_workflows.py tests/desktop/test_windows_desktop_paths.py
QT_QPA_PLATFORM=offscreen python -B -m pytest -q -ra tests/desktop tests/product/test_recents.py
QT_QPA_PLATFORM=offscreen python -B -m pytest -q tests/product tests/desktop tests/backends
QT_QPA_PLATFORM=offscreen python -B -m pytest -q tests/product tests/desktop tests/backends \
  --ignore=tests/product/test_integration.py \
  --deselect=tests/product/test_runtime.py::test_actual_arm_firmware_input_after_startup \
  --deselect=tests/product/test_runtime.py::test_actual_missing_completion_is_failure_despite_trigger \
  --deselect=tests/product/test_runtime.py::test_actual_cancellation_charged_and_aborted
python -B -m tools.check_build_inputs
```

The available-environment command is a local selection, not a change to CI or
the existing missing-tool failures. Run the unchanged required-runtime checks on
an equipped native host before claiming their success. Packaging, worker,
persistence and security regressions are included in the broader selection;
their host/synthetic scopes do not replace positive native product execution.
