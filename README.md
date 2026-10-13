# FIRMAVEX Desktop

Firmware testing and configured-failure discovery with reproducible inputs.

FIRMAVEX provides a **PySide6 desktop application**, an installable command-line
tool, and a supervised firmware execution worker. The desktop supports project
creation, compatible ELF import, configuration, tool checks, bounded testing,
progress and cancellation, saved results, reproduction, and report export.

This is a **beta-readiness development candidate**. Unsigned Windows installers,
Linux portable/Debian packages and unnotarized macOS DMGs are built in native CI.
See [first launch and runtime setup](docs/product/beta-setup.md) for qualification
status, download instructions and remaining blockers.
The execution profile is symbolized ARM Cortex-M3 ELF compatible with QEMU
`mps2-an385`, with typed uint32 inputs and explicit input-ready/completion functions.
Arbitrary vendor MCU firmware, raw BIN, hardware execution, and automatic
vulnerability judgments are unsupported. The guided strategy uses runtime
signatures, without an AI model. No discovery within a budget is not a safety
assessment.

## Install and launch

On Ubuntu 24.04+/WSL2 with Python 3.11 or newer:

```bash
sudo apt update
sudo apt install python3-venv gcc-arm-none-eabi qemu-system-arm gdb-multiarch
python3 -m venv .venv-desktop
source .venv-desktop/bin/activate
python -m pip install '.[desktop]'
firmavex-desktop
```

Use a Linux graphical desktop or WSLg. In the application, **Check runtime tools**,
then **Try built-in example (no compiler)**. Review its configuration, choose **Run bounded
test**, and reproduce the saved triggering vector from Results. These operations
use an independent example, never the frozen research campaign.

The existing `firmavex` CLI remains available. `firmavex desktop` launches the same
application. [Desktop usage and installation](docs/product/desktop.md) contains
exact commands, supported firmware requirements, evidence limits, and platform
status. [Batch 1 documentation](docs/product/batch1.md) remains the historical
engine reference.

## Platform boundaries

- **Linux:** bounded actual QEMU/GDB execution and offscreen desktop integration
  are tested. This does not qualify every Linux distribution or tool version.
- **WSL2:** requires WSLg for the interactive GUI; this cloud batch is not native
  WSL qualification.
- **Windows x86-64:** actual ARM adapter, supervised CLI, GUI and frozen-executable
  example workflows passed native CI. Only the checksum-qualified MSYS2 UCRT64
  QEMU/GDB profile is admitted. An unsigned per-user installer candidate is available.
- **macOS Apple Silicon:** actual source and app-bundle example execution passed
  native CI. Intel macOS remains unqualified; the DMG is unnotarized.

These are development candidates, not a public beta. They do not yet include a
qualified one-click QEMU/GDB runtime distribution. See the [Batch 3 validation
record](docs/product/batch3-validation.md) for observed CI results and remaining
gates. The Batch 2 record remains historical.

## Research preservation

The desktop lives under `firmavex/desktop/` and reuses `firmavex/product/`.
The research engine retains its canonical `src.firmavex` imports. Frozen protocols,
benchmark predicates, ground truth, campaign archives, and original results are
not product defaults and remain unchanged.

Research-paper work is paused. Step 19 findings remain preliminary and
journal-derived: execution verification failed, with supplementary evidence
missing at zero-based position 7. They are not desktop-validation evidence.

Cross-platform distribution candidates and runtime-pack setup: [Batch 3](docs/product/batch3.md). Windows firmware execution is limited to the checksum-qualified native runtime profile.
