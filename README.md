# FIRMAVEX

Firmware testing and configured-failure discovery with reproducible inputs.

The **product foundation** provides an installable Python command-line tool,
a supervised execution worker, user-firmware configuration, persistent results,
and bounded reproduction. It reuses the existing evaluator and enumerative,
random, and runtime-feedback-guided search strategies.

There is **no desktop GUI or native installer yet**. The guided strategy uses
runtime signatures, without an AI model. A test that finds no configured failure
within its budget does not establish that firmware is safe.

## Start with the product example

The initial execution target is symbolized **ARM Cortex-M3 ELF compatible with
QEMU `mps2-an385`**. Arbitrary MCU firmware, raw BIN images, and hardware execution
are not supported.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
firmavex doctor
firmavex demo --output-dir "$HOME/firmavex-product-demo-$(date -u +%Y%m%dT%H%M%SZ)"
```

Run these commands from an installed source checkout after installing ARM GCC,
QEMU, and an ARM-capable GDB with embedded Python. `doctor` checks the selected
tools; it does not execute firmware. `demo` builds and runs the independent
product example and reproduces its saved triggering vector. Every output
directory must be new.

See [Batch 1 usage, configuration, evidence, and recovery](docs/product/batch1.md)
and [installation details](docs/product/install.md). The Batch 1 guide includes
a complete Ubuntu/WSL command and a command reference.

## Current platform boundaries

- **Linux:** the product execution path is tested using actual ARM firmware in
  QEMU/GDB. This is emulator testing, not hardware validation.
- **Ubuntu WSL2:** the documented setup uses Linux tooling; this cloud batch is
  not a native WSL qualification run.
- **Windows:** native firmware execution is blocked until tested process-tree
  supervision is implemented. A Windows installer is not provided.
- **macOS:** native firmware execution and installation have not been verified.

Cross-platform unit CI is defined separately from real Linux firmware tests.
Creating that workflow does not establish that its jobs have passed on every
platform.

## Research preservation

Product code lives under `firmavex/product/`; the existing research engine retains
its canonical `src.firmavex` imports. The frozen research protocols, benchmark
predicates, ground truth, and original experimental data are not product defaults.
The product example does not execute research fixtures or the controlled campaign.

Research-paper preparation is paused. Existing Step 19 findings remain preliminary
and journal-derived, with execution verification failed and supplementary evidence
missing at zero-based position 7. They are not product-validation evidence.
