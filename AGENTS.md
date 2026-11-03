# FIRMAVEX agent instructions

## Purpose and architecture

FIRMAVEX is an offline-first, extensible firmware, embedded-system, and FPGA
testing platform. Keep claims within the implemented and tested target contracts;
simulation results do not establish physical hardware or FPGA qualification.

- Python 3.11+ provides the application, CLI, supervised workers, and test engine.
- `firmavex/desktop/` contains the PySide6 desktop application.
- `firmavex/product/` contains product configuration, ARM execution, services,
  persistence, reproduction, and reporting.
- `firmavex/backends/` provides shared backend interfaces and implementations:
  ARM Cortex-M3 on QEMU `mps2-an385` with an ARM-capable GDB, RISC-V RV32 firmware
  on QEMU with GDB, and Verilog compilation/simulation with Icarus Verilog
  (`iverilog` and `vvp`). These are bounded profiles, not arbitrary MCU or HDL
  support.
- `src/firmavex/` retains the research engine and its canonical imports. Preserve
  frozen protocols, benchmark predicates, ground truth, and campaign archives.
- Automated pytest suites live in `tests/product/`, `tests/desktop/`,
  `tests/backends/`, and the remaining research tests. Dependency and packaging
  configuration is in `pyproject.toml`; CI workflows are in `.github/workflows/`.

## Branch and work preservation

- Develop on `product/desktop-batch11`. Confirm the branch and Git status before
  working. Do not modify `main` or change branches without explicit user approval.
- Preserve all existing uncommitted changes and untracked files. Do not overwrite,
  discard, clean, reset, or delete work to simplify a task.
- Never access, inspect, modify, stage, or upload `evidence/windows-sandbox/`.
  Exclude it from searches, recursive scans, archives, and artifact collection.
  Do not enumerate its contents, including through scripts or tests.
- Make minimal, focused changes for the requested task. Avoid unrelated
  refactoring, formatting, dependency updates, or generated files.
- Never stage, commit, push, merge, or release without explicit user approval.
  A request to edit or test does not authorize those operations.

## Validation

- Read the relevant implementation, documentation, test configuration, and CI
  selections before changing behavior. Use the existing environment when possible.
- Run tests relevant to each change. Begin with focused cases, then broaden to
  affected suites when warranted. Documentation-only changes can use content and
  whitespace review; explain when runtime tests were not run.
- For actual ARM execution, set `FIRMAVEX_REQUIRE_RUNTIME=1` so missing runtime
  tools cannot silently become successful validation. Backend CI also uses
  `FIRMAVEX_REQUIRE_BACKENDS=1`; follow the applicable workflow and do not bypass
  runtime admission or qualification checks.
- Useful local commands, when `.venv` and the required tools are available:

  ```bash
  FIRMAVEX_REQUIRE_RUNTIME=1 .venv/bin/python -m pytest -q tests/product/test_runtime.py
  QT_QPA_PLATFORM=offscreen FIRMAVEX_REQUIRE_RUNTIME=1 .venv/bin/python -m pytest -q tests/product tests/desktop
  .venv/bin/python -m pytest -q tests/backends
  git diff --check
  ```

- Desktop tests require PySide6 and pytest-qt. Headless runs use
  `QT_QPA_PLATFORM=offscreen`. Missing GUI dependencies can prevent collection;
  do not report an uncollected desktop suite as passing.
- Distinguish actual test failures from sandbox permission errors such as
  `Operation not permitted`. Preserve the original outcome, identify the
  environment restriction, and request the necessary execution permission when
  required. Rerun the same relevant selection with approved permissions before
  concluding that the code is defective or the tests pass.
- Review the final diff and run `git diff --check`. Do not launch controlled
  research campaigns as a substitute for regression tests.

## Reporting and qualification

- Report the branch, exact commands and environment flags, exact passed, failed,
  errored, and skipped counts, and skipped-test reasons when available. State
  collection exclusions, missing dependencies, interrupted runs, and other limits.
- List files changed by the task separately from pre-existing modified or
  untracked work. State whether whitespace checks passed and identify unresolved
  problems. Do not claim tests ran when they were not run or completed.
- Never claim Windows qualification from Linux or WSL tests. Windows claims
  require relevant native Windows evidence for the specific runtime, application,
  and workflow. Likewise, synthetic tests, offscreen GUI checks, and simulator
  execution establish only the behavior they actually exercise.
