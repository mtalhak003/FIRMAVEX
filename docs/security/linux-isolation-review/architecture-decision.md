# Architecture assessment: Linux fixed-probe qualification

Status: proposed decision, not implementation or qualification. Base code is
`9fbada3` on `product/desktop-batch11`. Keep the incomplete AppArmor draft frozen.
Recommend a dedicated disposable VM for reviewed fixed probes only; retain the
product rejection of untrusted workloads. Do not add a privileged host launcher.
This decision does not authorize provisioning, policy activation or costs.

Linux aggregate isolation remains **unqualified**. The AppArmor draft is
incomplete, inactive and not approved for installation. The disposable VM is a
proposed qualification environment, not an established security solution. The
five high-severity findings documented in README remain unresolved; no runtime
behavior, security enforcement, CI workflow or release gate is changed here.

## Established execution paths

Source inspection, not assumptions about desktop isolation:

| Path | Actual behavior / trust boundary |
|---|---|
| Product supervisor -> worker | `firmavex/product/supervisor.py:execute` starts worker_argv with pipes and a POSIX new session. It does not change UID, supply a sanitized environment, enter namespaces or invoke bwrap. |
| Worker -> backend services | `worker.py:_execute` dispatches backend_execute/reproduce with caller-supplied trust. `backend_services.py:execute` rejects modes other than trusted_example/trusted_project. `engine.py:execute_trusted` invokes validate_trust, snapshots/revalidates inputs, then dispatches adapters; records sandboxed=false. |
| Native adapters | `implementations.py` uses Processes for RV32/HDL; ARM delegates existing product services/runtime. Neither path calls bwrap. `runtime.py:_spawn` inherits environment by default with PYTHONDONTWRITEBYTECODE added. These are trusted-project execution paths, not hostile-code containment. |
| Trusted library / legacy product paths | `engine.py:execute` preserves a trusted-caller API without the explicit trust argument; worker also exposes legacy run/reproduce services. Trust labels are local application policy, not OS authorization against a malicious caller. No universal hostile-input admission boundary is established by these APIs. |
| Product CI diagnostic | product.yml invokes `python -m tools.isolation_feasibility` as the runner account. It dispatches only embedded fixed Python code, not firmware or user-selected commands. No independent root cgroup supervisor in this path. |
| Aggregate CI diagnostic | aggregate-isolation.yml invokes Python via sudo as root. aggregate_isolation_probe creates root-supervised systemd units with User set to the invoking CI username. /usr/bin/python3 bootstrap waits for a root-owned marker; namespace phase execs the selected interpreter with `-m tools.isolation_feasibility`. The fixed inner probe invokes bwrap through Processes. |
| Namespace policy diagnostic | release-evidence.yml invokes namespace_diagnostics as root. It resolves bwrap with shutil.which, then systemd-run directly executes it with User=runner and fixed /bin/true. The four property variants are administrative comparisons; only combined retains all listed hardening. |

`tools/isolation_feasibility.py:assess` uses `shutil.which('bwrap')`; the resulting
path is normally /usr/bin/bwrap but the code does not require it. Processes uses
sys.executable plus `-m firmavex.backends.launcher` (or frozen console sibling),
passes bounded JSON over stdin, then launcher applies POSIX rlimits and calls
os.execv on the validated absolute path. Validation requires an existing file,
not a digest, immutable inode or root ownership. Source Python module lookup is
also part of the trust boundary. The fixed bwrap target is /usr/bin/python3 -I
-c GUEST; diagnostics use /bin/true. No shell interpretation is used for payloads.

### Actual credentials, environment and descriptors

- Direct diagnostic: real/effective UID/GID and supplementary groups are inherited
  from its caller. There is no explicit identity or capability reset by Processes.
- Aggregate: root controller is separate from systemd User=account units. Actual
  numeric UID/GID/groups follow that VM's account database and systemd settings;
  source does not fix numeric IDs or prove capability sets. Units request NNP,
  quota and kernel/cgroup protection properties. No explicit CapabilityBoundingSet
  or group allowlist is configured. Do not infer zero bitmaps from User alone.
- Direct policy diagnostic: User is set similarly; the plain case does not request
  NNP at service launch, although bwrap sets NNP internally in the reference source.
- Processes.Popen supplies no env, user, group or pass_fds. Python's default
  close_fds behavior closes nonstandard descriptors at this subprocess boundary;
  stdin/stdout/stderr are explicit pipes. This is a real mitigation, not an
  exhaustive audited descriptor policy across bootstrap/systemd/frozen paths.
  Launcher exec inherits remaining descriptors and environment.
- Environment at direct Popen is inherited. Aggregate unit environment comes
  from the systemd system manager/unit defaults, not necessarily the sudo shell's
  environment. Neither path declares a complete minimal environment. PATH controls
  shutil.which. --clearenv takes effect inside bwrap, after Python and bwrap loader
  startup. Do not claim it prevents earlier LD_*/PYTHON* injection.
- Reference bwrap sets NNP, creates user/private namespaces and drops capabilities
  for final execution. Observed failure happened before successful final guest
  entry. The actual installed binary, capabilities, labels and all transitions
  still require target-VM evidence. Local source cannot recover an unrecorded
  historical environment, UID number, supplementary groups or capability bitmap.

## Inputs and adversary model

Currently accepted project inputs include firmware/HDL/configuration, limits,
vectors, output paths and, where trusted configuration permits, runtime tool
selection. Trusted-example paths validate known content; trusted-project mode is
an explicit caller decision. A malicious library caller can call trusted APIs;
the trust string is not authentication. No product promise covers hostile projects.

Fixed probes accept administrative source/interpreter/account/output paths, not
user guest programs. Root path self-consistency checks do not authenticate source
bytes. CI revision, PATH, Python installation/import paths, account database,
environment and writable checkout are part of their trusted setup assumptions.
A same-UID attacker may race writable files or alter guest-owned evidence. A
future escaped workload could control those channels; that threat is not handled
merely by JSON validation or fixed argv construction.

For the recommended exercise trust the external VM controller/hypervisor, reviewed
image, pinned probe revision and administrative operator. Treat guest workload
processes, their output/artifacts and attempted namespace/capability operations as
potentially malicious. Protect the management host, credentials, other tenants,
external network, evidence receiver and spending budget. Do not assume the guest
kernel remains trustworthy after a hypothetical escape. Hypervisor compromise
remains a residual risk, not a tested impossibility.

## Candidate mechanisms (not implemented)

| Threat | Restricted trusted launcher on shared host | Dedicated disposable VM, one attempt |
|---|---|---|
| Unauthorized invocation | Requires authenticated peer identity, protected service endpoint, fixed operations, concurrency limits and separate worker UID. An executable pathname/profile alone is insufficient. | External controller alone selects image/revision and starts fixed job; no public job API. Guest cannot authorize another VM. Unrelated bwrap invocation inside the VM remains a policy qualification test, not solved by VM disposal. |
| Host-namespace capabilities | Requires bounded trusted setup privileges, verified namespace ownership/order and irrevocable drops before attacker input. AppArmor capability allows cannot express namespace scope. | No guest authority over hypervisor/management host; guest capabilities apply to guest kernel. Guest-initial-namespace effects are still qualification failures; VM is containment for the experiment, not permission to accept them. |
| Executable substitution | Needs protected immutable runtime/mount source, fixed argv, code identity verification without pathname races, no attacker-selected mount destinations. | Immutable versioned image and reviewed code staged before probes, no writable shared host mounts; independently verify hashes outside guest. Attacker-controlled guest results cannot attest their own runtime identity. |
| Loader/environment injection | Supervisor must construct minimal environment before first exec, protect interpreter/loader/dependencies and cwd, and reject injected runtime/module paths. | External controller fixes boot/init configuration; guest bootstrap needs the same minimal-environment discipline. VM isolation protects the management host even if guest setup is compromised; it does not prove probe validity. |
| Inherited descriptors | Explicit close-all-except protocol with authenticated bounded handles, no namespace/directory/management sockets or SCM_RIGHTS access. | No hypervisor filesystem/socket/credential FDs exposed; minimal bounded data channel, no device passthrough/shared mounts. Audit guest bootstrap descriptors independently. |
| Workload escape/resource abuse | Requires complete namespace, cgroup, AppArmor and syscall boundary plus independent audit; an escape exposes shared host kernel. | Guest escape contains to disposable VM unless virtualization boundary fails; external RAM/vCPU/disk/runtime/network limits bound blast radius. Preserve existing inner CPU/process/memory/network requirements unchanged. |

A restricted launcher introduces a privileged protocol/parser, authorization,
credential lifecycle and failure-recovery service that does not exist today.
It is not the smallest safe fix for a fixed diagnostic. A VM needs an external
lifecycle controller and a reviewed in-guest bootstrap, but avoids adding a
privileged service to developer/production hosts. A bare ephemeral Actions runner
inside the attacker domain is insufficient: it retains job credentials and
control channels. Prefer external orchestration with no Actions agent inside the
workload VM; if an agent is used for trusted fixed probes, do not promote that
arrangement to hostile-workload support. One-job registration is not VM erasure.

## NNP and AppArmor

Keep NNP for guest execution and all existing systemd hardening. NNP restricts
exec privilege acquisition, not existing capabilities or userns creation. A
privileged-launcher design cannot rely on setuid/file-cap exec after NNP; it would
need an already authorized supervisor outside the workload domain. Any setup
privileges increase the trusted code base and require explicit review.

Both candidates still need target-kernel tests of initial profile attachment,
NNP-compatible stacked setup-to-workload exec, missing-profile failure, realpath/
FD execution and nested userns denial. The VM boundary removes reliance on these
unqualified transitions for management-host containment; it does not waive them
for a passing Linux namespace qualification. Do not complete/activate the draft,
clear NNP, add inherit/unconfined fallback or accept unsupported controls.

## Explicit acceptance criteria and proof limits

1. Independent review freezes the image, reviewed bootstrap, code/dependencies,
   threat model, policy and allowed invocation. Caller-supplied paths/argv cannot
   select privileged setup behavior. Unknown identity/state fails admission.
2. Before execution, independent observation records UID/GID/groups, all capability
   sets, labels, NNP, executable identity, environment allowlist and FD inventory.
   No credentials/management reachability exist in the workload trust domain.
3. All existing fixed boundary/quota tests pass with no skipped/blocked cases;
   verify every required namespace, cgroup limits before admission and workload
   capability removal. Host-namespace changes fail qualification.
4. The expanded negative matrix in qualification-procedure.md is implemented in
   bounded reviewed harnesses and passes: unauthorized caller/argv, executable
   aliases/substitution, loader injection, descriptor attacks, profile changes,
   nesting, multi-process quotas, evidence forgery and interrupted cleanup.
5. Evidence observation begins before tools reset failed units. Guest assertions
   are corroborated externally; parsing output alone is not adversarial proof.
   Recursive cgroup emptiness, process identities, mounts, namespace references
   and sockets are checked; uncertainty stops further admissions.
6. External enforcement caps VM resources/lifetime and blocks management/metadata
   networking. Evidence export accepts bounded inert data, never guest commands.
   Destroy VM/disks, revoke job credentials and retain external teardown receipts
   after every attempt, including observation/export failure.
7. A positive exercise remains fixed-mechanism evidence. Any future hostile
   workload support needs a separate architecture/admission/review decision;
   current product rejection must remain until that decision is qualified.

Local source inspection and unchanged unit tests establish call construction,
validation/rejection paths and modeled fail-closed behavior. Offline parser checks
establish syntax only. Actual credentials, policy attachment/stacking, userns and
LSM behavior, cgroup enforcement under attacks, VM containment and teardown need
the approved native environment and independent observers. No privileged test or
infrastructure exercise was performed for this assessment.

Local validation: 69 tests passed, zero skips, across process security, backend
services, aggregate orchestration, namespace diagnostics and isolation feasibility.
The first command-sandbox attempt denied loopback sockets (6 failures, 1 error);
the same selection passed outside that command sandbox. Offline parser compilation
used -Q -K with ABI 4.0 feature input and passed without policy loading/cache writes.
Whitespace checks passed. These results do not establish any VM acceptance criterion.

References: [NNP kernel semantics](https://docs.kernel.org/userspace-api/no_new_privs.html),
[AppArmor upstream bwrap example](https://gitlab.com/apparmor/apparmor/-/blob/master/profiles/apparmor/profiles/extras/bwrap-userns-restrict),
[GitHub ephemeral runner lifecycle](https://docs.github.com/en/actions/reference/runners/self-hosted-runners).
