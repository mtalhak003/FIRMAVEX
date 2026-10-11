# Batch 1 validation and delivery record

The product branch is `product/desktop-batch1`, based on research checkpoint
`4cdedd23997aa3455585512f03bbe69b179ad887`. This is a working CLI/worker foundation
for a future desktop application. There is no GUI or native installer yet.

## Actual validation

All commands below ran in the Linux cloud environment with the real runtime
helpers on PATH, not on Windows, macOS, or native WSL2.

| Check | Actual result |
| --- | --- |
| Unchanged starting research suite | 1,365 passed, 162.13 seconds |
| Final product tests: `python -m pytest -q tests/product` | 397 passed, 12.55 seconds |
| Final complete suite: `python -m pytest -q` | 1,762 passed, 172.85 seconds; no failures or skips |
| `git diff --check`, including separate new-file whitespace checks | Passed |
| Wheel/source distribution build | Passed with isolated build backend |
| Fresh wheel installation outside the checkout, in a path with spaces | Passed; actual pyelftools dependency installed |
| Installed CLI/worker real-firmware demonstration | Passed |
| Installed product code compared with frozen checkout | Identical |

Tools: ARM GCC 14.2.1, QEMU 10.0.13, GDB Multiarch 16.3, Python 3.12.14,
pyelftools 0.33. The executable wrappers and versions are recorded. Their hashes
do not identify every underlying shared library or runtime component.

## Independent firmware evidence

The installed-wheel demonstration built its own Cortex-M3 firmware locally and
used QEMU `mps2-an385` plus GDB. It did not execute the research campaign.

- Search: nine safe completed observations followed by configured failure
  discovery at charged evaluator attempt 10, with exact input `[2, 1]`.
- Reproduction: three fresh completed observations of the same vector, all
  matching the declared condition.
- Total retained demonstration receipts: 13; nine safe and four triggering.
- Every receipt records dispatch, input injection/readback, required completion,
  tool/image identities, signature, and successful cleanup.
- All 26 recorded QEMU/GDB child processes were reaped and their PIDs were absent
  during the post-demonstration inspection.
- Demonstration ELF SHA-256:
  `17aaca7912b3a326c47469edefdccbf9c3bda30e6be02470c7a802f079106546`.

The private demonstration archive is outside Git at
`/workspace/firmavex installed demo batch1/`; it is not bundled as campaign data.
The product tests also exercise actual safe/triggering executions with signatures
on/off, missing completion despite a trigger, and charged cancellation. These
are bounded functional checks, not long-run stability or physical hardware tests.
Charged evaluator attempts must not be called independently verified physical
firmware executions.

## Architecture and safeguards

`firmavex.product` is the new product namespace. The unchanged engine retains
its single `src.firmavex` identity. The product reuses evaluator-owned accounting,
existing strategies, and the original signature collector. It has a strict
project schema/ELF validator, readiness-based fresh QEMU/GDB adapter, supervised
JSONL worker, exclusive SQLite run store, read-only inspection, explicit recovery,
bounded reproduction, and immutable artifact registration.

Infrastructure failure stops dispatch. Cancellation preserves charged attempts
and original control-flow exceptions inside the runtime/evaluator. Missing
receipts are disclosed, not reconstructed. Terminal results are cross-checked
against saved configuration, artifacts, inputs, feedback, and evaluator counters.
Transport diagnostic previews are labeled; full saved diagnostics remain intact.

No frozen protocol, strategy algorithm, evaluator accounting, runtime signature
semantics, corpus predicate, ground truth, campaign archive, or original research
result changed. The existing research tests remain unchanged. The README now
states actual capabilities rather than an unsupported AI description.

## Limitations and Batch 2 acceptance criteria

- Supported execution is symbolized ARMv7-M/Cortex-M3 ELF with compatible
  `mps2-an385` memory/peripherals, typed uint32 inputs, an input-ready function,
  completion function, and scalar equality failure condition. Raw BIN, arbitrary
  vendor MCU firmware, hardware probes, and automatic vulnerability judgments
  are unsupported.
- Linux actual execution is verified here. Windows native dispatch is blocked.
  macOS native execution and WSL qualification are unverified. Cross-platform
  CI is configured, but remote jobs have not been certified by this record.
- Recovery marks an abandoned run explicitly. Restart is a new full search,
  not partial strategy-state continuation, and may repeat abandoned work.
- SQLite and filesystem registration are not one atomic snapshot. Observable
  consistency checks do not cover every race, power-loss scenario, or network
  filesystem. Corrupt/unregistered artifacts require administrative handling.
- Signatures are bounded prefixes, not coverage or complete-path proof. No
  failure within a budget is not a safety guarantee. Imported ELF build-source
  provenance is not established merely by hashing the image.
- Example debug metadata includes build paths, so image hashes can differ across
  fresh output directories; each run archives the actual image used for replay.
- Native tools, signed installers, automatic updates, GUI, and portable runtime
  dependency packs remain to be implemented and platform-tested.

Batch 2 should add the PySide6 project/configuration workflow, tool setup checks,
progress/cancellation views, readable result/replay/export views, and native
Windows process-tree ownership. Acceptance requires installation and bounded
real-firmware tests on each claimed platform, responsiveness during cancellation,
truthful error/outcome displays, preserved evidence gaps, and no changes to frozen
research records. A GUI alone must not remove unsupported-platform gates.

## Exact changed files

- `.github/workflows/product.yml`
- `MANIFEST.in`
- `README.md`
- `docs/product/batch1.md`
- `docs/product/install.md`
- `docs/product/validation.md`
- `firmavex/__init__.py`
- `firmavex/__main__.py`
- `firmavex/product/__init__.py`
- `firmavex/product/cli.py`
- `firmavex/product/config.py`
- `firmavex/product/errors.py`
- `firmavex/product/example.py`
- `firmavex/product/firmware.py`
- `firmavex/product/protocol.py`
- `firmavex/product/resources/example/linker.ld`
- `firmavex/product/resources/example/main.c`
- `firmavex/product/resources/example/startup.c`
- `firmavex/product/runtime.py`
- `firmavex/product/services.py`
- `firmavex/product/store.py`
- `firmavex/product/supervisor.py`
- `firmavex/product/tools.py`
- `firmavex/product/worker.py`
- `pyproject.toml`
- `tests/product/test_cli.py`
- `tests/product/test_config.py`
- `tests/product/test_example.py`
- `tests/product/test_firmware.py`
- `tests/product/test_integration.py`
- `tests/product/test_packaging.py`
- `tests/product/test_protocol.py`
- `tests/product/test_runtime.py`
- `tests/product/test_services.py`
- `tests/product/test_store.py`
- `tests/product/test_supervisor.py`
- `tests/product/test_tools.py`
- `tests/product/test_worker.py`
