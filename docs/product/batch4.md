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

Linux x86-64, Python 3.12.14, PySide6 6.12.0, QEMU 10.0.13, GDB 16.3,
ARM GCC 14.2.1 (maintainer image build only), PyInstaller 6.16.0.
The compiler-free image SHA-256 is
`bdb370112a4fe834dae7127b75c3d38f7ffaf125af6dc4e02a6f24c4cae940ff`.
The actual frozen application found `[2, 1]` at attempt 10 and reproduced it
three times, with thirteen completed real guest receipts and verified cleanup.
The actual Qt compiler-free workflow also tested cancellation/export/responsiveness.
These are independent product runs, not frozen research campaign results.

The initial complete regression baseline was 1,967 passed, 4 Windows-only skipped.
Complete local regression: **2,013 passed, 4 Windows-only skipped**.
Focused integrity/setup/replay tests: **162 passed, 1 Windows-only skipped**.
The built Linux Debian package was inspected successfully; native CI is required
for installation/upgrade/removal and the new Windows provider.
Native Batch 4 CI status is separate from these local results.
No local Windows/macOS/WSL2 runtime or consumer-machine installation is claimed.

## Public-beta blockers

* Native vendor bootstrap/relocation must pass actual Windows CI. A rolling vendor
  feed is not a permanently pinned dependency closure; profile drift fails closed.
* macOS still needs a legally auditable automatic runtime provider. Intel macOS,
  Windows ARM64 and Linux ARM64 are not qualified.
* Signing, notarization, certificate reputation and Gatekeeper acceptance are not
  complete; development artifacts are unsigned/unnotarized.
* Real clean-machine/upgrade testing on ordinary graphical desktops and WSLg,
  usability/accessibility user evaluation, runtime bandwidth/disk requirements and
  publisher source-license maintenance are still necessary.
* No arbitrary MCU/peripheral/BIN/hardware support. Example success only establishes
  the narrow emulated profile and the actual tested tool/platform combination.
