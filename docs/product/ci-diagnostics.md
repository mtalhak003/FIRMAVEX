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

In this opt-in mode the launcher limits each selection wait to 540 seconds, independently of the
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
gh run download RUN_ID --repo mtalhak003/FIRMAVEX --pattern 'product-diagnostics-*'
```

A Git push to the product branch also starts the complete workflow. A green
product matrix is host/product regression evidence; Windows and Linux native
backend qualification is a separate workflow. macOS remains preview-only and
its native resource-admission failure must not be bypassed.

On Windows the launcher also arms CPython's native faulthandler watchdog for
600 seconds before child startup and keeps it armed through cleanup. It writes
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
