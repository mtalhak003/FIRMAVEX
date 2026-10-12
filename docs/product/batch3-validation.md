# Batch 3 validation evidence

Starting checkpoint: `06e6c241252096d258ffbd627798928d72b6bdc4`.
All changes are confined to product, desktop, packaging, tests and documentation.
Main/research protocols, firmware fixtures, ground truth and campaign data are
unchanged. Native Windows firmware execution remains gated.

## Actual local environment

Linux x86-64 cloud host, Python 3.12.14, PySide6 6.12.0, PyInstaller 6.16.0.
QEMU 10.0.13, ARM GCC 14.2.1, GDB multiarch 16.3. Tool wrappers refer to separately
installed host libraries; their hashes do not independently cover those libraries.
Qt checks use offscreen rendering, not a human desktop/usability evaluation.

* Baseline: `1911 passed, 4 skipped` in 194.27 seconds.
* Targeted runtime-pack/tool/example/supervisor tests: `76 passed, 1 skipped`.
* Runtime-pack-only regressions: `38 passed`.
* Final complete suite: `1953 passed, 4 skipped` in 194.83 seconds.
* PyInstaller native Linux build succeeded; frozen GUI smoke succeeded.
* Frozen executable's real ARM example search observed `[2, 1]` at attempt 10.
* Separate reproduction completed 3/3 attempts with the configured condition.
* Both result records are completed, `measurement_mode=real_firmware`, with zero
  infrastructure failures; no research campaign was run.
* All 13 actual receipts retained input injection, completion and cleanup evidence.
  All 26 owned QEMU/GDB child PIDs were absent after completion.
* Example ELF SHA-256:
  `7bc486cec9c44187a2ce7cce8911528ac925c2e6baa85273803470a76660f3d6`.
* Frozen read-only inspection and evidence/report export succeeded.

A private host-bound wrapper pack was checksum-verified, installed and capability
probed successfully (QEMU 10.0.13/GDB 16.3). It was explicitly marked as a
validation fixture; it is not portable and is not distributed. Successful pack
installation does not qualify guest execution.

## CI and packaging boundaries

The distribution workflow builds native candidate applications on Ubuntu,
Windows and macOS. Windows additionally exercises silent install, same-version
upgrade, GUI smoke, uninstall, and preservation of an independent user-data
sentinel. The sentinel test is not a clean-VM or real-project migration test.
macOS additionally has a source-installed real ARM qualification job using
Homebrew QEMU/GDB/ARM GCC. The Linux candidate executes the frozen real example.
Only observed workflow outcomes establish passes; workflow definitions do not.

Application artifacts contain checksums, a schema-1 build/file inventory and
license notices. They do not bundle a qualified portable ARM runtime. Windows
installers are unsigned; macOS bundles are not Developer-ID signed/notarized.
No actual Windows ARM firmware, WSL2/WSLg or Intel macOS qualification was performed
on this Linux host. Public beta requires the additional gates in batch3.md.

## First native CI observation

Distribution run `38277517235` at commit `1bc188e` succeeded: three native
application packages, Windows installer checks and macOS actual example execution.
The six-platform regression matrix/Ubuntu suite run `38277517111` failed in the
pre-existing Linux descendant cleanup test: procfs returned ESRCH
(`ProcessLookupError`) while reading a vanished process. The correction accepts
only ENOENT/ESRCH as process disappearance; permission errors and live processes
still fail. No test was disabled. Subsequent verification is reported separately.
The macOS qualification summary is now emitted as a public notice to expose actual
host architecture, tool identities, image identity and receipt counts without raw
debugger diagnostics. Saved actual receipts remain in an Actions artifact.
