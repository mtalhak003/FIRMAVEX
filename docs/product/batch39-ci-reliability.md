# Batch 39 — CI reliability and failure investigation

**Report date:** November 24, 2026, Asia/Karachi, using the client review date.
This date is not a development-hours claim or an instruction to change Git dates.
**Starting checkpoint:** [`7c9d5bdb29a59ce5283ec08cf577860eecb17b13`](https://github.com/mtalhak003/FIRMAVEX/commit/7c9d5bdb29a59ce5283ec08cf577860eecb17b13).
**Scope:** a cleanup-test race repair, failure-only installer diagnostic retention,
and evidence-based classification of the remaining CI blockers. No release or
native Windows runtime qualification is granted.

**Implementation references:**
[`207a9bced85738d65ec4f523e6c25e1fb2db37b9`](https://github.com/mtalhak003/FIRMAVEX/commit/207a9bced85738d65ec4f523e6c25e1fb2db37b9)
repairs the test observation race;
[`79c6be8a899dcce548effb4631e1be334decb53a`](https://github.com/mtalhak003/FIRMAVEX/commit/79c6be8a899dcce548effb4631e1be334decb53a)
retains failed runtime comparisons. Their separate commit boundaries distinguish
test reliability from diagnostic retention; neither changes runtime policy.

## Evidence access and classification

The approved worktree was inspected at the expected checkpoint with no scoped
changes; it remained detached rather than switching another checkout's branch.
Remote `product/desktop-batch11` matched that checkpoint before implementation.
Existing work was preserved.

The four public run pages and the specific failed-job pages below were retrieved.
Their links identify the Batch 38 source checkpoint. The visible annotations
independently exposed the cleanup traceback, nested isolation diagnostic and
Windows qualification rejection. These are **CI observations from public pages**,
not independently verified original evidence archives.

Authenticated GitHub CLI/API requests for failed logs and artifact metadata
returned `Forbidden`. The public job pages also said **Sign in to view logs**.
Consequently, full raw job logs, original uploaded artifacts and their checksums
were not available here. Missing data was not reconstructed or substituted with
synthetic evidence. Local regression fixtures are separately labelled as invented.

| Run and failed job | Independently observed evidence | Classification and current conclusion |
|---|---|---|
| [Product desktop and engine, 45208490945](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490945), [job 137810619409](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490945/job/137810619409) | `test_owned_descendant_cleanup` reached its procfs assertion, then `read_text()` raised `FileNotFoundError` for `/proc/9255/stat` after the existence check. | Confirmed test observation race. The traceback does not demonstrate a live descendant or a production cleanup regression. Repaired locally; a later CI result must establish the repair on its own revision. |
| [Independent aggregate isolation, 45208490104](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490104), [job 137810613200](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490104/job/137810613200) | Fixed CPU/process/memory checks true; boundary check false; nested namespace assessment blocked with the netlink denial below. | Current runner/probe combination did not establish the isolation contract. Fail-closed behavior is retained; the exact host policy responsible is not proven. |
| [Desktop beta setup, 45208490071](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490071), [job 137810615550](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490071/job/137810615550) | Vendor installation reached verification and returned the checksum-qualified QEMU 11.1.2 / GDB 18.1 rejection. | Runtime admission blocker. Current observed executable/package identities remain unproven without the original installation diagnostic. |
| [Distinct-version installer, 45208490068](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490068), [job 137810612787](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45208490068/job/137810612787) | Lifecycle qualification stopped at the same required runtime gate. | Qualification cannot continue; this does not establish that installation, upgrade or uninstall behavior itself failed. A diagnostic-retention gap was repaired. |

Batch 38 did not change the process-cleanup implementation, isolation probe/gate,
Windows runtime pins/provider, or installer qualification logic. Source comparison
supports treating these as the existing test race and unresolved environmental /
qualification limitations, rather than attributing them to RV32 diagnostic code.

## Linux descendant cleanup: repair without weakening the assertion

The old test did this after `Processes.close()`:

```python
assert not state.exists() or state.read_text().split()[2] == "Z"
```

A process can be reaped between those two operations. Its disappearance is
consistent with termination, but the old expression raises an exception instead
of recognizing it. A separate parsing problem is that `/proc/<pid>/stat` field 2,
`comm`, can contain spaces and parentheses; whitespace field index 2 is not always
the process state.

The [test-only repair](../../tests/backends/test_backends.py) reads the owned PID's
stat file directly and accepts only `FileNotFoundError` / `ProcessLookupError`
(ENOENT / ESRCH) as disappearance. If a record remains, it validates the expected
positive PID, parses after the final `") "` delimiter, requires numeric structure
at least through field 22 (`starttime`), and still requires zombie state `Z`.

The original timeout expectation, actual `Processes.close()` call, parent-reaping
assertion and platform guard remain unchanged. No production process handling,
signalling, resource admission, containment or timeout value was changed. Permission
errors, other I/O failures, malformed records, live/non-zombie states and control-flow
exceptions cannot become cleanup successes. A live process that reuses the PID is
conservatively rejected; this test is not a new general process-identity service.

Regressions use invented procfs records for exit-during-read, ESRCH, unusual names,
live states, malformed/truncated data, permission errors and cancellation. The real
owned-Python descendant test also runs; synthetic parser fixtures are not its
substitute. A deterministic patched-Path experiment reproduced the old expression's
`FileNotFoundError` and demonstrated the new direct-read behavior without reading
an actual procfs file in that forced-race experiment.

## Aggregate isolation: failure retained, not bypassed

The public annotation contains:

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

Its nested assessment reports `status=blocked`, `return_code=1`, and only
`namespace_descendants_absent=true`; owned-marker leftovers and process-inspection
errors were empty. Namespace-unit cleanup was recorded as verified. The outer
fixed CPU quota, process quota and aggregate-memory-kill checks were true, while
`filesystem_process_network_boundaries=false`.

The namespace **unit** returned `0` because the inner diagnostic command treats an
honestly blocked assessment as a completed assessment. That is not an isolation
pass. The [aggregate gate](../../tools/aggregate_isolation_probe.py) additionally
requires nested status `mechanism_checks_passed_not_qualified`, all nested checks
true and `untrusted_execution_authorized=false`. It correctly rejected this record.

The failure occurred while preparing loopback in the namespace. The fixed guest
filesystem/process/network checks were not established; this is neither proof of
successful containment nor evidence that a guest escaped. No loopback or namespace
check was removed, and no capability, NoNewPrivileges setting, cgroup quota,
AppArmor rule or host protection was relaxed.

The [existing Linux isolation review](../security/linux-isolation-review/README.md)
records earlier `RTM_NEWADDR` failures and AppArmor audit denials. Those are
historical corroboration, **not the missing audit evidence for this exact runner**.
Current attribution to AppArmor, another LSM, a kernel capability constraint or
another host configuration remains NOT PROVEN. The draft policy is still inactive
and unapproved, with its previously documented high-severity findings unresolved.

A local read-only admission check found Linux/Python 3.12.14 and bubblewrap, but
`systemd_running=false`, `administrator=false`, and an unprivileged non-writable
cgroup hierarchy. This environment cannot reproduce the root-supervised hosted
contract. No privileged aggregate probe or host-policy change was performed.

## Windows: preserve the admitted profile and expose the failed comparison

The current [production admission policy](../../firmavex/product/platform_support.py)
requires Windows x64 and these exact executable identities:

| Tool | Required version string | Required SHA-256 |
|---|---|---|
| QEMU | `QEMU emulator version 11.1.2` | `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` |
| GDB | `GNU gdb (GDB) 18.1` | `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` |

Discovery additionally checks the supported board/architecture and GDB embedded
Python/`hashlib` capabilities. The current public rejection does not disclose
which identity or architecture field failed. **Actual versions, hashes and package
versions acquired in these two runs are NOT PROVEN here.** Earlier QEMU 11.1.3
observations must not be relabelled as observations from these new runs.

Both existing Windows acquisition routes resolve rolling signed MSYS2 packages,
while production admission expects a frozen generation. This is a known
reproducibility/availability conflict, not permission to mix an old executable
with arbitrary current DLLs, replace hashes, approve a candidate or bypass the
gate. Acquisition, publisher-signature requirements, runtime pins and admission
were not modified.

The desktop provider already retains sanitized comparisons before private vendor
cleanup, via the [Batch 23 diagnostic mechanism](batch23-runtime-diagnostics.md).
The [versioned lifecycle tool](../../tools/versioned_install_ci.py) previously saved
only the exception type/message, dropping the gate's structured comparison.

The small CI-tool enhancement now optionally retains
`failure.runtime_qualification` for the exact supported `ProductError` category,
known schema/profile and profile version. It reuses `_qualification_details` to
rebuild expected versions/hashes and match booleans from the unchanged policy,
copying only sanitized observed QEMU/GDB identities and allowlisted architecture.
Caller-supplied expected/match values, paths, environment fields and unknown
metadata are not copied. Missing identity values remain null, not matches.
Unsupported contracts are omitted rather than interpreted as current qualification.

Success, unrelated failure and cancellation paths do not acquire this runtime
claim. The original failed gate remains raised with `passed=false`; a failure in
optional projection retains the original exception and records the fixed
`runtime_qualification_status=projection_unavailable`. New control-flow exceptions
propagate. Existing persistence and cleanup paths remain in place. This is
failure-diagnostic retention, not new installer behavior or native execution proof.
Only the new comparison is allowlisted. The established private
`failure.diagnostic` field still retains its original exception text and may
contain paths; this change does not make the entire lifecycle receipt suitable
for unreviewed publication.

## CI coverage and original evidence still needed

The existing [product workflow](../../.github/workflows/product.yml) discovers the
backend tests in its Linux regression selection and already includes
`test_versioned_install_ci.py` in its platform-neutral selection. No workflow,
required assertion, platform gate or security check was skipped or weakened.
No manual workflow dispatch is required to obtain coverage of the added cases.

With separately authorized GitHub access, retain the original run artifacts in a
fresh private directory outside the repository:

- Run `45208490104`: `FIRMAVEX-ubuntu-aggregate-isolation-assessment`, including
  `assessment.json`, `guest/namespace.json`, unit logs and kernel/supervisor/cleanup
  readbacks. Obtain exact-run audit diagnostics before attributing the netlink
  denial to a specific host policy.
- Run `45208490071`: `Windows-runtime-installation-diagnostics`, retaining the
  recorded expected/observed identities and package projection before cleanup.
- Run `45208490068`: `FIRMAVEX-windows-latest-versioned-installer-evidence`, including
  lifecycle JSON, vendor inventory and logs. New runs can retain the added identity
  comparison; historical missing fields must not be reconstructed.

These names come from workflow definitions, not independent confirmation that an
original artifact ZIP was downloaded or verified. Review raw diagnostics for
private paths before publication. Do not copy protected or original evidence to
make a test fixture, and do not download or install substitute runtime binaries.

## Actual local validation

The cleanup-focused selection ran on Linux:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/backends/test_backends.py -k 'proc_stopped or owned_descendant_cleanup'
```

It reported **29 passed, 70 deselected**, zero failures/errors/skips, **0.77 seconds**.
The real owned-Python descendant test was additionally run in five fresh bounded
pytest processes: all five reported one pass (0.57–0.60 seconds each). These are
bounded reliability observations, not proof that every possible process race is
eliminated.

The final installer-receipt selection used synthetic lifecycle fixtures only:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_versioned_install_ci.py
```

**44 passed**, zero failures/errors/skips/deselections, **0.14 seconds**. No installer
or Windows runtime was executed.

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/backends/test_backends.py tests/backends/test_records_security.py \
  tests/product/test_versioned_install_ci.py tests/product/test_aggregate_isolation_probe.py \
  tests/product/test_isolation_feasibility.py tests/product/test_namespace_diagnostics.py \
  tests/product/test_platform_support.py tests/product/test_runtime_setup.py \
  tests/product/test_runtime_pack.py tests/product/test_ci_diagnostics.py \
  tests/product/test_supervisor.py tests/product/test_build_inputs.py
```

**405 passed, 23 skipped**, zero failures/errors/deselections, **30.30 seconds**.
These overlapping selections are not additive and are not the complete repository
suite. The 23 skips comprise 21 missing ARM/RV32/Icarus-tool prerequisites, one
unavailable local namespace-admission test and one native Windows process-tree
test. More precisely: `test_backends.py:24` accounts for 11 Icarus, 3 RV32 runtime,
1 ARM runtime and 1 RV32 compiler skips; `test_backends.py:144`/`:158` account for
3/1 RV32 skips; `test_records_security.py:517` accounts for 1 ARM-tool skip;
`test_isolation_feasibility.py:56` and `test_supervisor.py:226` account for the two
environment/platform skips. None is presented as a passing native check.

The wider selection additionally attempted the existing fixed **unprivileged**
namespace integration test. It was skipped after the local diagnostic reported
`bwrap: setting up uid map: Read-only file system`; this is not the hosted run's
loopback/netlink error and must not be substituted for its cause. No privileged
root/systemd aggregate probe was executed. Missing-tool and native-Windows-only
skips also remain explicit in the final wider record; no guard was relaxed to
avoid them.

Final static checks passed: Python AST parsing for the three changed Python
files; newline/trailing-whitespace checks for all six intended files; 167 local
documentation links, including 23 heading anchors; and 104 unique commit
references resolved as local commits. `git diff --check` passed. `actionlint`
was unavailable; no workflow file was changed, so workflow linting is not claimed.

Post-publication GitHub Actions conclusions must be checked against the actual
published SHA and exact run/attempt. Passing local tests or a queued workflow are
not passing CI. This report does not claim native Windows validation, a signed
installer, a qualified sandbox or a release.

## Remaining work and proposed Batch 40

1. Independently obtain and review the original diagnostic artifacts with authorized
   access; preserve unknown identities and missing raw-log evidence as unknown.
2. Review the exact runner's kernel/LSM/audit evidence in an approved disposable
   qualification environment. Preserve all namespace and aggregate-quota checks;
   review any policy proposal separately instead of granting capabilities to
   obtain green CI. Existing Linux isolation findings remain unresolved.
3. Recover an authenticated immutable qualified runtime/dependency set, or request
   separate authorization for a consistent new candidate and its full native
   qualification matrix. Do not downgrade one executable or promote QEMU 11.1.3
   merely because a newer package is available.
4. Inspect the new revision's automatic CI results, including the actual descendant
   cleanup test and richer failed Windows receipts. Keep blocked qualification
   workflows visible; no claim that all CI is green follows from this repair.

Main, frozen research, production admission, runtime hashes, signing requirements
and protected evidence remain untouched. No force-push, artificial contribution,
manual CI dispatch, runtime substitution or release promotion is part of Batch 39.
