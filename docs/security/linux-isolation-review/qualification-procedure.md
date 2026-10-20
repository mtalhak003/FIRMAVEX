# Disposable Ubuntu VM qualification procedure

Status: future procedure, **not executed**. Do not provision, install/load the
draft policy or run privileged probes from this package. First resolve README
policy blockers, review a complete candidate and obtain explicit approval for
the VM, policy activation and privileged exercise. No automatic deployment script
is included. Passing fixed probes remains feasibility, not sandbox qualification.

Linux aggregate isolation remains **unqualified**. The incomplete AppArmor draft
is inactive and not approved for installation. This VM procedure describes a
proposed qualification environment, not an established security solution. Follow
the trust model and unresolved findings in `architecture-decision.md` and README.

## 1. Freeze the environment

Use a fresh Ubuntu 24.04 VM per attempt, dedicated to reviewed fixed probes.
Suggested initial capacity: 2 vCPU, 4 GiB RAM, 20 GiB disk; these are planning
values, not minimum security guarantees. Reserve supervisor headroom. Record image
digest, kernel and boot configuration, AppArmor/parser, systemd, bubblewrap and
Python package versions, source revision, lockfiles and hashes. Pin the completed
policy digest and source reference commits; mutable upstream URLs are not pins.

Require CONFIG_NAMESPACES, USER_NS, PID_NS, NET_NS, IPC_NS, UTS_NS, CGROUPS,
CGROUP_PIDS, MEMCG, CPU bandwidth control, tmpfs/procfs, and enforcing AppArmor
with userns mediation. Require unified cgroup v2 with cpu/memory/pids enabled
through ancestors and memory.swap.max available. Check actual effective unit
limits, not merely kernel build options. No numeric kernel version alone qualifies.
KVM is not required inside this VM; avoid nested virtualization as a prerequisite.

Keep `kernel.apparmor_restrict_unprivileged_userns=1`, and AppArmor enforcing.
Where available, unprivileged_userns_clone must allow the reviewed profile to
create namespaces; namespace quotas must permit setup's required nesting.
No global restriction removal, setuid bwrap, setcap, ambient capability grant,
privileged container, NNP removal or quota increase is allowed.

Use a root-owned, non-writable reviewed checkout at `/opt/firmavex` and a
root-owned Python 3.12 environment `/opt/firmavex-qualification`, populated using
the workflow's hash-locked requirements, no-dependency package install and
tools.check_build_inputs. The guest account `runner` must be non-root and cannot
write supervisor code, interpreter, policy, launcher or admission-marker directory.
Freeze the approved revision after these documentation changes; record how it
differs from base 9fbada3. Root must not import unreviewed checkout/sitecustomize
code. Resolve /usr/bin/python3 and bwrap paths and confirm trusted search paths.

No host mounts, Docker socket, instance-role credentials, private network routes,
private evidence or signing keys. Block guest access to metadata services and
management networks. Allow only required package/Actions/evidence destinations
during their phases, with no network bridge into the workload namespace.

For Actions use a dedicated runner group and one-job ephemeral/JIT registration,
read-only repository token, trusted workflow/revision restrictions and no PR jobs.
Destroy the VM after the job: deregistration is not erasure. Put registration,
VM administration, evidence retention and a hard lifetime watchdog outside it.

## 2. Establish baseline and policy identity

Collect boot ID, UTC time, VM ID, uname, kernel configuration, cgroup tree and
controller availability, sysctls, aa-status, loaded profile hashes, bwrap mode/
file capabilities/package provenance and /proc/self/status. Preserve kernel audit
logs with timestamps and complete systemd unit properties. Exclude tokens.

Run existing fixed diagnostics before any approved policy change to reproduce
the blocker. Retain the baseline independently. Compile the completed policy
offline with the TARGET parser and ABI first, treating warnings or missing
features as blockers. Activation is a separate approved operator step, not
authorized by this document. Record every loaded profile, including distro
profiles that attach to bwrap; do not silently replace or disable those profiles.

After activation, verify actual setup and workload labels, including stacked
labels, with parent-side observation and guest /proc/self/attr/current. Record
NoNewPrivs=1 and all capability bitmaps at pre-bwrap setup, namespace setup and
workload entry. If extra instrumentation is needed, review it before running;
do not infer successful transitions from the absence of an audit denial.

Do not equate a runnable policy with authorized invocation: executable attachment
does not restrict caller UID, namespace, argv or environment. Before activation,
resolve the unauthorized-invocation cases below and their expected outcomes.
The current skeleton does not supply an enforcement architecture for them.

## 3. Run unchanged fixed probes

The following are future commands for the approved disposable VM ONLY. Output
directories must not already exist; failure is retained and never overwritten.
Do not run them on the development host. The GITHUB_ACTIONS marker identifies
this authorized disposable diagnostic; it is not proof that a machine is safe.

```bash
cd /opt/firmavex
sudo env GITHUB_ACTIONS=true /usr/bin/python3 \
  -m tools.namespace_diagnostics --user runner \
  --output /var/tmp/firmavex-namespace-candidate
sudo /opt/firmavex-qualification/bin/python \
  -m tools.aggregate_isolation_probe \
  --source /opt/firmavex \
  --python /opt/firmavex-qualification/bin/python \
  --user runner --output /var/tmp/firmavex-aggregate-candidate
```

The namespace diagnostic returns successfully after recording blocked cases;
its exit code alone is NOT a pass. Inspect each result and cleanup. The aggregate
CLI must return zero AND show exactly five true checks, all units cleaned up,
and status fixed_checks_passed_not_qualified. Nested assessment must contain
all expected checks, including descendant absence, with no inspection errors.
Aggregate and nested assessments must retain untrusted_execution_authorized=false
and sandbox_qualification=not_established. Namespace diagnostic records instead
use security_qualification=false; validate each artifact's own schema and do not
invent absent fields. Missing results, blocked cases, skips and warnings are blockers.

Positive checks: input readable; input/runtime readonly; host marker and PID
absent; independent required namespaces; loopback only; host listener unreachable;
correct inherited limits; memory allocation refusal; bounded storage; CPU quota;
process-count denial; cgroup OOM with swap zero; verified cleanup.

## 4. Independent negative qualification matrix

These are test specifications, not supplied/validated new test executables.
Implement and review bounded fixed harnesses before expanding the experiment.
Each must have a supervising deadline and independent result/readback evidence.

| Attempt | Required observation |
|---|---|
| Same-UID ordinary application creates userns outside bwrap | Global policy still blocks it; the executable exception is not global. |
| Unrelated same/different UID invokes bwrap with arbitrary argv, omitted isolation flags or pre-created userns | Document whether setup policy attaches; no unauthorized namespace exception, setup privilege or host access may be accepted as a pass. This is unresolved and may require a different invocation architecture. |
| Root/pre-capable caller invokes the attachment path | Source/policy analysis must recognize that AppArmor allows are not namespace-scoped; a future approved bounded VM canary must expose initial-namespace effects. Do not run a general privileged payload. Treat a usable host-capability path as a design failure, not an authorized workaround. |
| Setup environment injects LD_PRELOAD/LD_LIBRARY_PATH; inherited host directory, namespace or connected socket FD | Reviewed canaries must not execute attacker code in setup or reach host resources. --clearenv after loader startup is insufficient. Verify descriptor inventory and closure independently. |
| Symlink/hardlink/copy/renamed bwrap, /proc/self/exe, execveat or fd execution | Record actual attachment and behavior; no alternate path may bypass required confinement or obtain setup exceptions. Reject unknown labels. |
| Caller bind-mounts a different inode at an allowed Python/true pathname; Python receives different -c code | Pathname permission is not code identity. Establish authorized invocation and trusted mounts/code before accepting any positive result. Do not infer payload authenticity from argv[0]. |
| Workload attempts profile/hat change, exec stacking removal or namespace nesting before/after final exec | Cannot remove denial layers or recover setup-only permissions. Correlate NNP, labels, namespace IDs and capability bitmaps; include missing-profile and failed-transition cases. |
| Workload unshare/clone userns, setns or mount/pivot/remount | Denied; no change to host or workload boundaries; capture errno/audit/namespace identities. |
| Workload obtains capabilities, executes setuid/file-cap target | No privilege gain; NNP stays set; capability sets remain zero and bounding set cannot increase. Use only fixed reviewed canaries. |
| Execute a target not in the fixed allowlist or missing child profile | Denied, without inherited/unconfined fallback. Test actual realpaths and aliases. |
| Read/write host marker, access host PID, write input/runtime | Denied/absent; independently verify host canaries unchanged. |
| IPv4/IPv6 host listener, external endpoint, management/metadata | Unreachable; verify host-side counters and private netns interfaces/routes. No external real service probing. |
| Multiple allocators/threads, mmap, shared memory, fork chain | Kernel-enforced aggregate limits hold; record memory.events, cpu.stat, pids.events and effective limits. Bound thread/fork counts. |
| Write quota values, migrate to sibling/ancestor cgroup | Denied; supervisor readback unchanged. |
| Write many small files across /tmp and /work | tmpfs aggregate bounds hold independently of per-file RLIMIT_FSIZE. |
| Timeout/cancellation, lingering descendant, namespace-init exit | Entire owned tree disappears and controller remains responsive. |
| Bad evidence, unavailable controller, quota mismatch, cleanup fault | No admission or no subsequent admission; nonzero outcome and retained diagnostics. Fault injection uses reviewed disposable harnesses. |
| Same-UID sibling forges guest namespace JSON, races symlinks or signals probe processes | Independent observer must detect/reject interference; do not treat guest-controlled JSON or marker-based process scans as adversarial proof. Review runner credential/UID separation before allowing attacker code. |

A syscall denied only by an incidental test environment does not prove the
intended mechanism. Correlate labels, kernel events, namespace IDs and readbacks.
Repeat fresh-boot runs with identical inputs and record timing/load variability.
Do not fix a denial by granting a wildcard permission or removing a hardening flag.

## 5. Evidence and teardown

Before resetting failed units, retain systemd status/show/journal; kernel audit,
cgroup limits/events/statistics, nested assessments, launcher hashes and labels.
Separate controller evidence from guest-authored assertions. Hash an inventory
with boot ID, revision, package/policy versions, timestamps and exit codes.
Transfer only sanitized qualification artifacts to access-controlled external
storage; checksums establish integrity, not independent trust or approval.

For every recorded unit, stop it and verify inactive/failed plus absent active
ControlGroup. Before disappearance, require recursive cgroup.events populated=0;
otherwise verify the recorded cgroup path and descendants are gone. Check direct
cgroup.procs and every descendant, owned PIDs, process-inspection errors,
namespace references, residual mounts and sockets/listeners against baseline.
Only then reset failed unit state. No observation available means cleanup
unverified; stop further probes and destroy the VM regardless.

The unchanged tools currently reset failed units internally, and the namespace
diagnostic cleans each case before returning. Therefore post-command collection
cannot satisfy every pre-reset observation above. Establish an independently
reviewed live observer or a separately reviewed retention change before the
exercise; no such instrumentation is included or validated in this package.
Track process identity using independent lifecycle evidence, including start time
or pidfds where available, rather than assuming a PID or cmdline token is unique.

Externally verify VM termination, disk deletion, runner deregistration and token
revocation; keep evidence and teardown receipts. If the job hangs or evidence
export fails, an external watchdog still destroys the VM. No instance reuse.

## Decision and cost gates

Before provisioning, approve a provider/region, runtime limit, spending ceiling,
storage retention and teardown owner. Costs include VM time, disk, logs/artifact
storage, egress and policy maintenance. No price estimate is claimed without a
chosen provider. Even after fixed checks pass, independent security review and
the expanded matrix must complete before revising support policy. No release
approval or hostile workload admission follows automatically.
