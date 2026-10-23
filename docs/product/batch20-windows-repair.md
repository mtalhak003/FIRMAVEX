# Batch 20 Windows CI repair

Scope: repair the Batch 20 Windows baseline before Batch 21 usability work.
No Batch 21 product changes are included. Frozen main, execution policy,
resource admission, consent, cancellation and evidence formats are unchanged.

## Oversized pytest ID: test-harness defect

Original Product run: [40020210013](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40020210013).
The Windows Python 3.12 job `120642495316` finished with 839 passed, 3 skipped
and 2 setup/teardown errors for:

`tests/product/test_regression_review.py::test_malformed_sessions_rejected_without_repair`

The third parameter is `b'x' * (regression.SUMMARY_BYTES + 1)`: 131,073 bytes.
Without explicit IDs, pytest includes that value in the node ID. Pytest's
`_update_current_test_var` assigns `f'{item.nodeid} ({when})'` to
`PYTEST_CURRENT_TEST` during setup/call/teardown. Windows rejects that environment
value with `ValueError: the environment variable is longer than 32767 characters`.
The exception surfaced through the pytest-qt setup hook before the malformed
archive assertion ran; this is not an execution/resource-admission failure.

The correction supplies `empty-object`, `invalid-json`, and `over-byte-limit` as
short, stable IDs. The byte inputs, rejection assertions and immutability check
are unchanged. Collection now shows only those three IDs. The diagnostic repair
commit `c7050f40de2de36681cd4dc916fe5a4fe4a4752a` passed both Windows Python
3.11 and 3.12 jobs in [Product run 40022757709](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40022757709).

## RV32 native GUI failure: Windows working-directory handling

Original Native run: [40020210095](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40020210095).
The new `test_real_regression_dashboard_verify_and_text_report[riscv32-virt]`
failed its first execution assertion. The session summary recorded one
infrastructure error and one not-run entry; it did not fabricate a firmware
verdict or continue after the infrastructure error.

The original assertion displayed counts without the retained backend error.
A bounded diagnostic assertion helper now reads only the selected entries'
validated backend records on failure. It changes no pass/fail condition and does
not replace native execution.

In [diagnostic Native run 40022757696](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40022757696),
Windows job `120651210515` retained this RV32 error independently:

- Entry `58eda4d45548424886e64acc92849280`.
- `NotADirectoryError: [WinError 267] The directory name is invalid`.

The test-set session path was 245 characters; `/entries/<32-character-id>` made
the execution working directory 286 characters. The path is a valid directory
for Python file operations, but cannot be used as the native launcher cwd in
`CreateProcessW`. This occurs in the existing `Processes.spawn` launch path,
before the selected QEMU/GDB command can run. Native tool discovery/readiness and
shorter-path source/backend regression journeys had succeeded in the same job.

## Verilog native GUI failure: separately confirmed same OS restriction

The Verilog case failed the same first execution assertion in the original run.
It was not assumed to share RV32's cause. The diagnostic job independently retained:

- Entry `14b5eaecc0fe47cfa674efcfdef0ce92`.
- `NotADirectoryError: [WinError 267] The directory name is invalid`.

Its session/entry directory lengths were also 245/286 characters. The same owned
launcher path is used for Icarus capability/compilation/simulation subprocesses.
Icarus discovery and shorter-path native Verilog execution had passed. The two
failures expose a product Windows path-handling limitation through deeper GUI
storage fixtures; they are not fixed by skipping the new tests or changing
runtime qualification/CI consent.

## Minimal product correction and safeguards

For RV32 and Verilog, the existing engine now selects a native-compatible
spelling of the already created, owned output directory before snapshot and
native command paths are constructed. On Windows only, paths over 240 UTF-16
units use the volume's existing `GetShortPathNameW` spelling. The function checks
that the alias is absolute, short enough, passes existing symlink/reparse-point
checks, and refers to the same physical directory with `os.path.samefile`.
Both spellings are checked again before use. No link, junction, evidence copy,
archive rewrite, resource-policy change or process-admission exception is created.
Normal short paths, POSIX execution and the ARM adapter remain unchanged.

A volume that cannot provide a usable same-directory spelling fails closed with
instructions to use a shorter project/data directory. Its infrastructure record
is persisted and no backend is dispatched. This retains the existing supervisor,
Windows Job ownership, quotas, cleanup, trust and fail-closed behavior.

Unit tests cover unchanged short/POSIX paths, same-directory checks, invalid,
relative, unavailable and non-shortening aliases, retained reparse-point checks,
and persisted infrastructure failure before backend dispatch. These tests are
included in Product and Native CI. Existing real native GUI outcome, cleanup,
verification, export and evidence-immutability assertions remain in place.

## Local evidence and CI interpretation

Local Windows CPython 3.14.7 was available through WSL, but a full local Windows
RV32/Icarus test environment was not available. A harmless Python child reproduced
`WinError 267` at cwd lengths 259, 260, 300 and 450; a 200-character cwd worked.
A 317-character directory still failed with an extended-path prefix, while its
existing 78-character short spelling launched successfully and had the same
physical directory identity. The production helper separately passed at an
original length of 328 and native length of 78, again with `samefile == True`.
These probes are Windows path/launcher evidence, not firmware/HDL qualification.

Local Linux native GUI tests exercise both RV32 and Verilog with real tools;
they are distinct from the synthetic unit seams. Product/Native workflows on the
development branch provide the required Windows regression and full native
qualification results for the final correction. The final delivery report must
cite those actual outcomes rather than treating local probes as Windows native
end-to-end success. Existing macOS memory-admission, Linux isolation and
mandatory distribution/release evidence gates are not weakened or waived.

Local validation before the native-path correction commit: the combined available
Linux product, desktop and backend suite completed with **1,472 passed,
16 skipped**, zero failures (248.48 seconds). Focused path/aggregate/Qt tests
completed with **41 passed**. The native RV32 and Verilog Qt dashboard selection
completed with **2 passed**. The existing short-deadline test passed in this full
run without alteration. `git diff --check` passed. These local counts do not
substitute for the required post-correction Windows CI outcomes.
