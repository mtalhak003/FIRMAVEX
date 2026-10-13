# Desktop Batch 4 verification record

Starting checkpoint: `4a1b24f419b822d931f0f6deee516fe629d4bb63`.
Development branch: `product/desktop-batch4`; main is not modified.

Implemented: verified compiler-free MIT example; first-launch compatibility/runtime
wizard; explicit Windows vendor-install consent; private checksum-pinned bootstrap
and signed package acquisition; local inventoried runtime snapshot; cancellation
and cleanup; generation history, integrity verification and rollback; pinned run
tool paths; windowed desktop/console worker packaging; distro-dependent Debian
package; unsigned installer/unnotarized DMG automation; signing prerequisites.

## Actual local verification

Linux x86-64, Python 3.12.14, PySide6 6.11.1 (final pin), QEMU 10.0.13, GDB 16.3,
ARM GCC 14.2.1 (maintainer image build only), PyInstaller 6.16.0.
The compiler-free image SHA-256 is
`bdb370112a4fe834dae7127b75c3d38f7ffaf125af6dc4e02a6f24c4cae940ff`.
The actual frozen application found `[2, 1]` at attempt 10 and reproduced it
three times, with thirteen completed real guest receipts and verified cleanup.
The actual Qt compiler-free workflow also tested cancellation/export/responsiveness.
These are independent product runs, not frozen research campaign results.

The initial complete regression baseline was 1,967 passed, 4 Windows-only skipped.
Complete final local regression: **2,022 passed, 4 Windows-only skipped**.
Final metadata/tool/worker integrity selection: **123 passed, 2 Windows-only
skipped**. Shared-validation/setup/real GUI selection: **67 passed**.
CPython 3.11 synthetic GUI selection: **126 passed, 2 real-firmware tests
deselected**; the process exits normally with PySide6 6.11.1.
The built Linux Debian package was inspected successfully; native CI is required
for installation/upgrade/removal and the new Windows provider.
The final executable code checkpoint is
`11b93dcab5726e372b5ce3eb2c741a7f817cfc04`. All three native CI workflows
passed at that checkpoint:

* [Regression: seven OS/Python jobs](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414421922).
* [Distribution: three installer builds and two native qualification jobs](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414422195).
* [Beta setup: Windows provider and Linux/Apple Silicon compiler-free jobs](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38414422220).

Windows acquired the checksum-pinned bootstrap and signed packages, activated and
verified its local runtime, then ran compiler-free source/GUI/frozen/installed
application workflows. Search found `[2, 1]` at attempt 10, with three reproductions
per demonstration, actual completed guest receipts and cleanup. The native GUI
also tested cancellation and report export. Installer reinstall/upgrade/removal
preserved user data and the managed runtime. Linux passed distro package
installation/reinstallation/removal with data preservation; Apple Silicon passed
compiler-free GUI and frozen firmware workflows with Homebrew runtime tools.
These are hosted-runner qualification cases, not clean consumer machines or
hardware validation. Reinstallation tests do not establish every cross-version
upgrade or downgrade. WSL2/WSLg was not available for Batch 4 qualification.

Development failures were retained and fixed: Windows CRLF source hashes;
case-insensitive worker selection; MSYS2 snapshot size/file limits; private
read-only file/agent cleanup; Qt 6.12/CPython 3.11 shutdown abort; repeated Windows
ctypes ABI setup and redundant generation hashing; and preflight test bounds.
The missing-completion regression now allows five seconds for actual debugger
initialization while retaining every failure, injection, signature and cleanup
assertion. Administrative GUI bounds are separate from guest execution timeouts.
No failing tests were skipped or assertions removed to obtain these results.
No local Windows/macOS/WSL2 runtime or consumer-machine installation is claimed.

## Public-beta blockers

* Windows vendor bootstrap/relocation passed the linked native CI. The rolling
  feed is still not a permanently pinned dependency closure; executable profile
  drift fails closed, and future dependency closures need maintenance/qualification.
* macOS still needs a legally auditable automatic runtime provider. Intel macOS,
  Windows ARM64 and Linux ARM64 are not qualified.
* Signing, notarization, certificate reputation and Gatekeeper acceptance are not
  complete; development artifacts are unsigned/unnotarized.
* Real clean-machine/upgrade testing on ordinary graphical desktops and WSLg,
  usability/accessibility user evaluation, runtime bandwidth/disk requirements and
  publisher source-license maintenance are still necessary. Abrupt setup termination
  can leave locks/temp files needing support-assisted recovery; unknown ownership
  is never guessed. Complete the bundled application license/source inventory
  audit before a public release.
* No arbitrary MCU/peripheral/BIN/hardware support. Example success only establishes
  the narrow emulated profile and the actual tested tool/platform combination.
