# Product regression diagnostics

`tools/product_ci_tests.py` runs the complete supplied selection without retries
or deselection. It writes complete output directly to a retained file and publishes a bounded
64-KiB tail after process cleanup. Test liveness does not require a console
forwarding thread or inherited-pipe EOF. The explicit `--ci-watchdog`
mode used by the platform-neutral product step loads the CI-only
`tools.product_ci_diagnostics` pytest plugin. Each test prints its node ID before
setup and its elapsed wall time after teardown. The default 120-second per-test
limit covers setup, call, and teardown together. A stalled test emits a bounded
public error annotation containing Python thread stacks and exits with status
124. It does not become a skip or a successful partial selection. Ordinary
assertion failures preserve pytest's exit status and JUnit diagnostics. Collection
and interpreter shutdown also have 120-second guards; public lifecycle notices
distinguish these from individual-test execution.

In this opt-in mode the launcher limits each selection wait to 240 seconds, independently of the
unchanged 20-minute product matrix job limit. Its test child waits for admission
before importing pytest: Windows Job Object ownership is established first;
POSIX uses an owned process group. The tree is terminated on completion or
failure, including watchdog exit. These are CI cleanup controls, not sandbox
isolation. The watchdog's `--firmavex-test-timeout` option exists for regression
checks of the watchdog itself; product CI uses the default unchanged.

`FIRMAVEX_CI_DIAGNOSTICS` optionally retains the transcript and any completed
JUnit report. Product workflow jobs upload these as `product-diagnostics-*`
artifacts, including on failure. An interrupted run may have no complete JUnit
report. Do not interpret missing reports as a passed selection. Python stacks
identify Python waits; further native process diagnostics may still be needed
for a kernel or debugger stall.

To run all seven jobs manually, open **Actions → Product desktop and engine →
Run workflow**, select `product/desktop-batch7`, then **Run workflow**. Alternatively:

```sh
gh workflow run product.yml --repo mtalhak003/FIRMAVEX --ref product/desktop-batch7
gh run list --repo mtalhak003/FIRMAVEX --workflow product.yml --branch product/desktop-batch7
# Substitute the returned run ID:
gh run watch RUN_ID --repo mtalhak003/FIRMAVEX --exit-status
gh run download RUN_ID --repo mtalhak003/FIRMAVEX --pattern 'platform-neutral-diagnostics-*'
# Completed jobs also retain product-diagnostics-* with later regression logs.
```

A Git push to the product branch also starts the complete workflow. A green
product matrix is host/product regression evidence; Windows and Linux native
backend qualification is a separate workflow. macOS remains preview-only and
its native resource-admission failure must not be bypassed.

On Windows the launcher also arms CPython's native faulthandler watchdog for
300 seconds before child startup and keeps it armed through cleanup. It writes
thread stacks directly to `launcher-stacks.log`, independently of the stdout
streaming lock, then exits unsuccessfully. The admitted pytest process tree is
owned by the kill-on-close Windows Job Object. Loss of admission is rejected
before pytest runs. POSIX does not use this parent-exit mechanism: its existing
process-group cleanup and bounded waits remain responsible for termination.

Configured diagnostic directories are written directly from the start, so a
forced launcher exit cannot lose evidence waiting for a final copy operation.
`launcher-state.log` records the last launcher phase. The always-run
`--report-diagnostics` step publishes bounded file tails as failure annotations;
the complete retained files are uploaded separately. A native launcher timeout
is a failed diagnostic run, never evidence that the tests passed.

Without `--ci-watchdog`, the shared wrapper does not install the per-test,
collection, shutdown, or native launcher watchdogs. Native firmware and GUI
qualification retain their own existing test deadlines and the existing
900-second selection wait. No application execution/resource limit is changed.

The platform-neutral Actions step has an independent six-minute step deadline;
the existing twenty-minute job deadline is unchanged. Diagnostics are published
and uploaded immediately after that step with `always()`, before later checks.
This prevents a later job cancellation from discarding an already captured
platform-neutral record. Step timeouts remain failures. Launcher state notices
are administrative phase information, not a substitute for JUnit/test outcomes.

The malformed-frame regression keeps its full 1,048,577-byte input but uses
explicit short parameter IDs. Previously pytest generated a 1,048,659-character
node ID and copied it into `PYTEST_CURRENT_TEST`, exceeding Windows environment
variable limits. The failed CI annotation identified this oversized-frame case;
GitHub also rejected the resulting 1,069 KiB step summary. Collection regression
tests now enforce bounded IDs for all six malformed-frame cases. Published JUnit
failure labels are capped at 512 characters plus a SHA-256 identity suffix;
complete labels remain in the retained JUnit artifact. No payload, assertion,
application resource control, or test deadline was relaxed.
CPython's Windows `win32_putenv` rejects strings exceeding `_MAX_ENV` before
calling the CRT; see [CPython 3.12 `posixmodule.c`](https://github.com/python/cpython/blob/3.12/Modules/posixmodule.c).
The original raw Windows exception is not recoverable from the truncated public
annotation, so native CI is required to verify the repair end to end.
