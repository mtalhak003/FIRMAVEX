# Batch 41 — Qualification evidence and diagnostic reliability

**Date:** November 24, 2026, Asia/Karachi.
**Starting checkpoint:**
[`7b8dfd61a9fd64c550a74f9b9b29124d7e6e3995`](https://github.com/mtalhak003/FIRMAVEX/commit/7b8dfd61a9fd64c550a74f9b9b29124d7e6e3995).
**Qualification status:** NOT ESTABLISHED. Neither runtime admission nor isolation
policy is relaxed by this investigation.

**Implementation references:**
[`21bc0e83ff7f8f443cacd04a3cfde49bff2a1561`](https://github.com/mtalhak003/FIRMAVEX/commit/21bc0e83ff7f8f443cacd04a3cfde49bff2a1561)
preserves aggregate control flow;
[`2bfd66dfdb7fc455d3871280586f9fcef17bd632`](https://github.com/mtalhak003/FIRMAVEX/commit/2bfd66dfdb7fc455d3871280586f9fcef17bd632)
adds the failure-only Windows notice. Both are CI-tool reliability changes,
not production qualification changes.

## Scope, access and evidence classes

The approved worktree matched the remote development branch, with no scoped
working-tree changes. Its existing detached state was preserved; no original
checkout, protected evidence or historical campaign archive was accessed.
The README, release-readiness record, Batch 32 runtime plan, threat model and
current CI/tool/test contracts were reviewed before implementation.

The two requested public run/job pages identify the starting checkpoint:

| Run | Job | Independently observed public result |
|---|---|---|
| [Aggregate isolation 45390608611](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45390608611) | [138432973765](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45390608611/job/138432973765) | Fixed quota checks true; namespace boundary contract false, nested assessment blocked at loopback setup. |
| [Windows installer lifecycle 45390608438](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45390608438) | [138432973472](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45390608438/job/138432973472) | Runtime verification rejected the required Windows profile before installer lifecycle execution. |

Authenticated artifact-metadata requests for both exact runs returned `Forbidden`.
The Windows failed-log request also returned `Forbidden`; public job pages require
sign-in for complete logs. **No original diagnostic ZIP was downloaded, hashed,
verified, reconstructed or substituted.** Downloaded public pages were retained
only outside the repository. Public annotations are CI observations, not original
artifact verification or independent kernel/runtime measurements.

## Windows runtime: established rejection, unavailable identities

The unchanged [admission policy](../../firmavex/product/platform_support.py)
requires Windows x64 and these exact identities:

| Field | Required value | Observed in run 45390608438 |
|---|---|---|
| QEMU version | `QEMU emulator version 11.1.2` | NOT PROVEN |
| QEMU SHA-256 | `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` | NOT PROVEN |
| GDB version | `GNU gdb (GDB) 18.1` | NOT PROVEN |
| GDB SHA-256 | `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` | NOT PROVEN |
| Vendor package versions | Exact captured signed generation and dependency inventory required | NOT PROVEN |

Discovery separately requires `mps2-an385`, ARM support and GDB embedded Python /
`hashlib`. The generic rejection does not identify which version, hash or
architecture field failed. Historical QEMU 11.1.3 observations do not establish
this run's identities. No new executable is admitted or substituted.

The [existing workflow](../../.github/workflows/versioned-install.yml) upgrades a
rolling MSYS2 package set and installs unversioned package names. That is a known
availability/reproducibility conflict with the frozen profile, not proof of a
particular current mismatch. In the [lifecycle tool](../../tools/versioned_install_ci.py),
runtime snapshot/installation precedes the first application installer. Therefore
this rejection does not establish success or failure of upgrade, rollback,
uninstall, saved-result preservation or consumer acceptance.

The private lifecycle receipt already retains the allowlisted comparison from
Batch 39. The public CLI previously emitted only the generic exception message.
This source-level gap is reproducible with a synthetic gate exception and explains
why public annotations lack the otherwise retained comparison.

The narrow improvement publishes a failure-only notice containing a deterministic
ASCII JSON comparison rebuilt through that same existing projection. Its overall
admission status remains explicitly **rejected**, even if individual fields match.
Expected identities come from unchanged policy; missing observations remain null.
Unknown schemas, malformed values and private extra fields are not copied. No raw
environment, executable paths, package output or original receipt content is
published by this new notice. The existing generic error/private diagnostics still
need normal privacy review; this does not sanitize the entire archive.

Success and unrelated failures acquire no comparison. Optional projection errors
produce a fixed unavailable notice while preserving failure status; control-flow
exceptions in the new reporting helper propagate. No broader lifecycle cleanup
or persistence interruption guarantee is added. Original receipt persistence,
package acquisition, cleanup,
signatures and the strict gate remain unchanged. The Batch 40 console helper is
reused rather than duplicating encoding logic. Future notices are fresh CI
observations; they cannot recover this historical run or prove signed closure,
DLL compatibility, licensing, native firmware behavior or qualification.

## Aggregate isolation: environment blocker and independent control-flow defect

The public diagnostic reports:

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

CPU quota, process quota and aggregate-memory-kill checks were true, but
`filesystem_process_network_boundaries=false`. The nested assessment was
`status=blocked`, `return_code=1`, with only `namespace_descendants_absent=true`.
Namespace-unit readbacks reported CPU `50000 100000`, memory `268435456`, swap `0`
and PIDs `64`. Cleanup was recorded verified, with no owned-marker leftovers or
inspection errors. These are public CI readbacks, not independently rechecked
original kernel evidence.

The inner diagnostic's exit `0` honestly records a blocked assessment. The outer
gate additionally requires completed positive mechanism checks and correctly
rejects it. The failure occurs during namespace setup; guest filesystem/process/
network guarantees remain unestablished. It is not evidence of a guest escape.
Historical AppArmor `setpcap` / `net_admin` denials concern other runs/VMs and do
not establish this runner's exact LSM/kernel cause. No capability, namespace,
NoNewPrivileges, quota, AppArmor or host-security setting was changed.

Related current-host audit evidence was also available from the existing
namespace diagnostic in sibling release-evidence runs:

- [45390608628, job 138432973725](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45390608628/job/138432973725),
  at the original `7b8dfd61` source revision.
- [45418175761, job 138530037682](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418175761/job/138530037682),
  at the new `2bfd66df` source revision.

Both diagnostic jobs completed successfully in 34 seconds, despite the containing
release workflows being cancelled. Their public notices include AppArmor in the
LSM list, an audited `userns_create` transition from `unconfined` to
`unprivileged_userns`, and these denial fields:

```text
apparmor="DENIED" operation="capable" profile="unprivileged_userns" comm="bwrap" capability=8 capname="setpcap"
apparmor="DENIED" operation="capable" profile="unprivileged_userns" comm="bwrap" capability=12 capname="net_admin"
```

This establishes current AppArmor interference on those **separate diagnostic
VMs**, rather than relying only on historical reports. It does not prove that
their policy is the exact or sole cause on either aggregate-test VM. The notice
is a 3,500-character tail; complete host/sysctl records and individual comparison
case outcomes were not recovered and are not reconstructed. Successful diagnostic
completion is not successful namespace isolation. No new diagnostic workflow was
added or dispatched, and no host policy was altered.

A separate reproducible bug was found in the aggregate tool's exception handling:
if an ordinary probe error was pending, a new `KeyboardInterrupt` raised during
cleanup was recorded and suppressed, allowing `assess()` to return an ordinary
failed record. The analogous persistence handler had the same masking pattern.
Trusted Python stubs reproduced this without launching systemd or a guest. This
bug does not explain or fix the observed loopback denial.

The repair propagates a new control-flow exception after an ordinary failure,
retaining the earlier error in administrator-owned diagnostics. An already pending
control-flow exception keeps its original identity/priority and records secondary
failures. Ordinary secondary errors retain existing behavior. Failed/unknown
cleanup stays failed, later probes are not admitted and available failure evidence
is retained. Stop/readback deadlines, commands, quota tests, guest code, admission
and qualification verdicts remain unchanged. Cancellation is not proof that unit
cleanup completed; interrupted cleanup remains explicitly unverified.

## Actual local validation

The local host is Linux x86-64/Python 3.12.14, with bubblewrap and `systemd-run`
available but no running systemd, administrator authority, writable unprivileged
cgroup hierarchy or KVM device. It cannot reproduce the privileged hosted
contract. No root-supervised probe, policy change, runtime acquisition, installer,
signer, firmware campaign or manual CI dispatch was performed locally.

Before editing, the existing installer/aggregate/namespace selection passed
**57 tests**, zero failures/errors/skips/deselections, **0.21 seconds**:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_versioned_install_ci.py tests/product/test_aggregate_isolation_probe.py tests/product/test_namespace_diagnostics.py
```

Final combined focused validation used the same command and reported **120 passed**,
zero failures/errors/skips/deselections, **0.33 seconds**. There are 63 added cases:
36 aggregate exception-priority/admission/persistence cases and 27 synthetic
Windows CLI comparison/status/privacy/cancellation cases. Individual overlapping
selections reported **42 passed** in **0.13 seconds** for the aggregate file and
**71 passed** in **0.23 seconds** for the lifecycle file. These counts are not
additive.

The wider relevant selection was:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_versioned_install_ci.py tests/product/test_aggregate_isolation_probe.py \
  tests/product/test_namespace_diagnostics.py tests/product/test_isolation_feasibility.py \
  tests/product/test_platform_support.py tests/product/test_runtime_setup.py \
  tests/product/test_runtime_pack.py tests/product/test_ci_diagnostics.py \
  tests/product/test_build_inputs.py tests/product/test_supervisor.py \
  tests/product/test_windows_job.py tests/backends/test_process_security.py
```

**421 passed, 6 skipped**, zero failures/errors/deselections, **30.23 seconds**.
Five skips require native Windows ownership/handle behavior (`test_supervisor.py:226`,
`test_windows_job.py:64`/`:230`). The remaining namespace-timeout test
(`test_isolation_feasibility.py:56`) was skipped after local UID-map setup was
blocked with `Read-only file system`. That local error is distinct from the hosted
loopback denial and is not its cause. The existing unprivileged diagnostic was
allowed to record its blocker; no root-supervised probe or security relaxation
was attempted. No local project regression suite failed.

These are relevant overlapping selections, not the complete repository suite.
Synthetic tests do not stand in for missing original artifacts, Windows runtime
qualification or actual namespace enforcement. Four Python AST parses and scoped
whitespace checks passed. Documentation checks passed 170 local links, 23 heading
anchors and 111 unique local commit references; all seven intended files passed
newline/trailing-whitespace checks. Thirteen fixed guest/supervisor/lifecycle AST
contracts match the baseline. Production runtime setup/pack/admission and both
qualification workflows are unchanged. `git diff --check` passed. Independent
read-only review found no blocking defect.

## Fresh automatic CI observations

The code commits were pushed normally at `2bfd66dfdb7fc455d3871280586f9fcef17bd632`;
no manual workflow was dispatched. A fresh aggregate run
[45418176318, job 138530038693](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418176318/job/138530038693)
**failed** in **1 minute 1 second** at that exact source revision. Public
annotations again show passed fixed quota checks, blocked loopback setup with
`RTM_NEWADDR: Operation not permitted`, unchanged namespace limits and verified
cleanup/no owned-marker leftovers. This confirms the gate remained fail-closed;
it neither establishes the kernel-policy cause nor verifies an original archive.

The [fresh Windows lifecycle run 45418175773](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418175773)
and [product regression run 45418176180](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418176180)
were inspected against the same source revision. Native product-regression jobs
[Windows Python 3.11, 138530039405](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418176180/job/138530039405)
and [Windows Python 3.12, 138530039424](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418176180/job/138530039424)
displayed success. Their public platform-neutral and synthetic-desktop sessions
report pytest status `0`, as do all retained completed-selection phases. The entire
seven-job product workflow subsequently displayed **Success**. Exact native JUnit
counts were not independently verified. These are native host regression and CI
observations, not Windows firmware-runtime, installer or sandbox qualification.
Other results are recorded only when actually available; running/queued jobs are
not passing evidence.

The fresh Windows lifecycle job
[138530036955](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45418175773/job/138530036955)
subsequently **failed at runtime admission**, and the new notice was visible.
Its exact source is `2bfd66dfdb7fc455d3871280586f9fcef17bd632`, architecture
`x86_64`, profile version `1`, overall `admission=rejected`:

| Tool | CI-observed version | CI-observed SHA-256 | Version matches | Digest matches |
|---|---|---|---|---|
| QEMU | `QEMU emulator version 11.1.3` | `15368eeab939a3ffb29ffdf73572faa0ab180d76997d00d68ea077c938552c4c` | false | false |
| GDB | `GNU gdb (GDB) 18.1` | `4f9000b35fcd3f41e1fa6b6e530bb05e16e0c817b1b6ff19ad2a3647fbfb2efe` | true | false |

The published JSON was independently parsed from that job page, bound to its
source commit, and checked against unchanged local expected identities and
independently recomputed field comparisons. The existing generic error and
failure exit remained present. This validates native CI visibility of the new
notice, not qualification or independent hashing of downloaded executable bytes.

QEMU's version and digest fail the admitted profile, and GDB's digest also fails
despite its matching version. Neither historical digest can be substituted. The
workflow's rolling package acquisition explains why an exact old profile is not
guaranteed, but the particular package build/revision and reasons for changed
bytes still require original inventories/archives. Vendor package versions,
signed dependency closure and publisher/license evidence remain unverified.
These are **new-run observations**: they do not fill the unavailable identity
fields for historical run `45390608438`, nor replace an original artifact ZIP.
No version/hash pin was changed and no installer lifecycle pass is inferred.

## Remaining evidence and Batch 42 gates

1. Obtain authorized original artifacts for the exact run/attempt: configured
   `FIRMAVEX-windows-latest-versioned-installer-evidence` and
   `FIRMAVEX-ubuntu-aggregate-isolation-assessment`. Resolve actual artifact IDs
   from authenticated metadata; do not guess IDs or reuse a prior archive.
   Store originals privately outside the repository, record their original-byte
   SHA-256 and inspect them read-only. See the
   [artifact verification procedure](batch28-artifact-verification.md).
2. Review the actual Windows receipt comparison and vendor package inventory.
   A new public notice can narrow the failed fields, but does not authenticate
   the complete original package/dependency/license set. Follow the
   [Batch 32 decision gates](batch32-windows-runtime-packaging-plan.md): recover
   an authenticated immutable admitted generation, or separately authorize a
   fully captured candidate and native qualification. No executable-only downgrade
   or automatic promotion is safe.
3. Obtain correlated same-host unit/kernel/LSM audit evidence for a failed
   aggregate assessment in an approved disposable environment. The sibling
   diagnostics establish their own AppArmor denials but cannot bind them to
   another VM. Keep namespace/cgroup checks fail-closed; review policy proposals
   separately. Existing isolation findings and hostile-input restrictions remain.
4. Match future automatic CI observations to the exact published revision and
   attempt. Blocked workflows, unavailable evidence and unknown causes remain
   explicit. No issue is closed and no production release/qualification follows.
