# Batch 22: verification consistency

Individual desktop verification now offers an unchecked-by-default **Include
retained RV32/Verilog input** choice. It applies to both the selected history run
and a manually chosen folder. Enable it before starting verification; the choice
is disabled while a job is active. The saved archive determines the backend,
independently of the current execution-profile selector.

The supervised `backend_verify` command accepts optional `include_input`, strictly
a JSON boolean. Omission and `false` retain the existing listed-artifact behavior.
`true` uses the existing input-inclusive verifier already used by regression
verification. No archive or protocol schema version changes are required.

| Archive/action | Hash-check scope |
|---|---|
| RV32, default | Listed output artifacts; ordinary empty inventories remain unavailable |
| RV32, input included | Retained `firmware.elf` against recorded size/SHA-256, plus listed outputs |
| Verilog, default | Listed outputs such as VCD; not retained source |
| Verilog, input included | Retained `testbench.v` against recorded size/SHA-256, plus listed outputs |
| ARM wrapper | Listed artifacts only; no automatic nested traversal, even with the choice enabled |
| Manually selected ARM `arm-run` archive | Registered artifacts, SQLite structural/state consistency and inventory checks; unchanged |
| Regression session | Existing retained-input/output checks plus recorded entry associations and summary stability; unchanged |

For ARM, explicitly choose the nested `arm-run` folder using **Verify folder**.
Registered artifact checks do not reconcile product receipt/accounting records.
Neither wrapper nor artifact verification establishes authentic execution.

Missing or malformed input identities, missing inputs and size/hash mismatches
cannot produce an input-inclusive verified result. Old archives are not migrated
or repaired. Default verification remains available with its narrower scope; it
must not be represented as verifying the retained input. Existing count, byte,
path/link and read limits remain in force, including when adding an input row.

Verification only reads source evidence, retains partial observations on
cancellation, and never dispatches firmware or HDL. Input-inclusive diagnostics
name the additional check. An overall `verified` status refers only to the named
scope relative to recorded identities, not publisher authenticity, physical
hardware correctness, complete archive integrity or release readiness.

**Check for changes** remains metadata-only and does not rehash contents.
Individual verification-report export retains saved observations plus a metadata
freshness observation. Regression report export continues to verify freshly.
These are sequential observations, not atomic filesystem snapshots. Referenced
configuration/set manifests are not independently reverified by this feature.

Focused tests cover worker defaults/type validation, retained firmware/testbench,
missing/corrupted identities and bytes, cancellation, desktop opt-in transport,
source preservation and zero workload dispatch. Synthetic archives and offscreen
desktop tests do not qualify native Windows or hardware execution.

## Local validation

On `product/desktop-batch11`, the focused selection completed with **138 passed,
0 failed, 0 errors, 1 skipped** in 9.89 seconds:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -ra tests/product/test_verification.py tests/product/test_regression_review.py tests/desktop/test_universal.py tests/desktop/test_regression_workflow.py
```

The broader selection completed outside the agent sandbox with approved execution
permissions: **1,293 passed, 0 failed, 0 errors, 17 skipped** in 278.35 seconds:

```sh
QT_QPA_PLATFORM=offscreen FIRMAVEX_REQUIRE_RUNTIME=1 .venv/bin/python -m pytest -q -ra -p no:cacheprovider tests/product tests/desktop --tb=short
```

The focused skip requires Windows short-path aliases. Broader skips comprise
eight Windows-only checks, one macOS path-alias check, five Verilog native checks
missing Icarus, and three RV32 native checks missing QEMU RV32. Thus native
RV32/Verilog desktop journeys were not freshly qualified by this run; synthetic
input checks and real supervised file-verification transport passed separately.
No test failure or sandbox permission error occurred in these selections.
