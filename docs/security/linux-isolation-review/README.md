# Linux aggregate isolation security review

Review status: **incomplete; do not install or activate the draft**. Base revision:
`9fbada36f1428972e99a7a499680b03cf8c19e88`, branch `product/desktop-batch11`.
Only review documents are proposed. Existing execution code, workflow and security
tests remain unchanged. This package does not authorize infrastructure or costs.

Linux aggregate isolation remains **unqualified**. The AppArmor draft is incomplete,
inactive and not approved for installation. The disposable VM is a proposed
qualification environment, not an established security solution. Runtime security
enforcement, CI workflows and release gates are unchanged.

Read `architecture-decision.md` for the proposed direction and trust model, and
`qualification-procedure.md` for the future approval-gated exercise.

## Evidence and trust boundaries

Inspected `tools/isolation_feasibility.py`, `tools/aggregate_isolation_probe.py`,
`tools/namespace_diagnostics.py`, `.github/workflows/aggregate-isolation.yml` and
their tests. [Aggregate run 39484802793](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39484802793)
retained CPU/process/memory checks true, namespace boundaries false and cleanup
true for all four units. The namespace assessment reports `RTM_NEWADDR: Operation
not permitted`. [Diagnostic run 39484802794](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39484802794)
records the same failure in plain, NoNewPrivileges, protected-kernel and combined
cases. AppArmor audit events identify `unprivileged_userns` denials of `setpcap`
and `net_admin`. These establish a host-policy blocker, not an isolation pass.
The diagnostic runs on a separate VM, so it corroborates the mechanism rather
than proving every configuration detail of the aggregate VM.

The trusted root controller starts fixed systemd services as an unprivileged
account. Before releasing a root-owned admission marker it reads actual cgroup
limits: CPU 50%, memory 128 MiB (256 MiB namespace phase), swap zero, tasks 64
(8 in the process test). It retains NoNewPrivileges, ProtectControlGroups,
ProtectKernelTunables, RestrictSUIDSGID, RuntimeMaxSec and KillMode=control-group.
The outer controller must run immutable reviewed code: checking its own source
path is not source-integrity verification. Never run PR-controlled code as root.

The inner launcher applies AS 512 MiB, CPU 9 seconds and file-size 1 MiB, then
runs bubblewrap with unshare-all plus explicit unshare-user, cap-drop ALL,
disable-userns, clearenv, readonly runtime/input, private proc/dev, and bounded
tmpfs (64 KiB /tmp; 1 MiB /work). It dispatches only fixed Python probe code.
Neither a positive result nor this AppArmor draft creates a public sandbox API.

## Proposed policy and permission rationale

`firmavex-bwrap.apparmor.draft` is an executable-specific, default-deny review
skeleton. Missing permissions intentionally prevent it being a working policy.
It uses ABI 4.0 as a candidate for Ubuntu 24.04, not a compatibility claim.
AppArmor permissions allow kernel operations otherwise available to a process;
they do not themselves grant Linux capabilities. No setuid bit, file capability,
ambient capability, global sysctl exception, complain mode or unconfined fallback
is proposed.

| Rule | Why considered | Limitation / evidence required |
|---|---|---|
| U1 `userns` | Initial unprivileged namespace and bubblewrap's nested namespace used to disable further user namespaces. | AppArmor cannot express "exactly these two creations" here. Prove workload denial and unchanged host sysctls. |
| C1 `setpcap` | Actual audit denial; bubblewrap performs capability bounding-set drops. | The observed denial does not prove this is the only failing operation. No workload permission. |
| C2 `net_admin` | Actual audit denial and netlink loopback failure in a new network namespace. | Rule does not encode "loopback only". Prove non-root startup, new namespace ownership and zero initial-namespace capability sets. |
| C3 `sys_admin` | Bubblewrap source requires namespace/mount setup, readonly bind mounts, proc/tmpfs and root rearrangement. | Very broad Linux capability even though named individually. Do not approve without exact shipped-source review, mount rules and proof it is never usable in the initial namespace. |
| T1 stacked `px` | Candidate transition on Python or true pathnames; no `ix`, `pix` fallback or `ux`. | Neither attachment nor stacking under NNP is demonstrated. Lowercase px does not request environment scrubbing. An interpreter pathname does not constrain its code/argv or prove executable identity after namespace remapping. |
| D1 deny all capabilities | Intersects workload confinement with setup permissions; complements bubblewrap cap-drop ALL. | Independently read effective/permitted/inheritable/ambient/bounding sets; do not assume AppArmor denial clears bitmaps. |
| D2 deny userns | Prevent workload namespace recreation, complementing disable-userns. | Must allow setup nesting before exec yet reject workload unshare/clone/setns attempts. |

No generic `mount,`, `file,`, `network,`, `ptrace,`, `signal,`, `change_profile,`
or blanket capability allow is supplied. No setup-library/file rights are guessed.
The draft therefore does NOT establish successful namespace admission.
The source's additional required capabilities (`sys_chroot`, `setuid`, `setgid`,
`sys_ptrace`) are withheld pending exact non-setuid path review. In particular,
namespace symlink inspection is not justification for arbitrary host ptrace.
Additional denials must lead to review, not automatic aa-logprof acceptance.

Mount review must enumerate source/destination, propagation, recursive bind and
readonly remount flags, proc/tmpfs/device construction, pivot_root and teardown
under bubblewrap's actual intermediate paths. AppArmor is path-based and may see
paths differently after pivot_root. Do not guess those rules from final paths.
Workload rules must cover only fixed Python imports, namespace/limit inspection,
readonly marker input and /work writes; network permission, if needed for the
negative socket test, remains inside an independently verified private netns.

## Transitions and unresolved compatibility

The following is the intended sequence, NOT observed behavior of this draft:

1. Require independent verification that the trusted service starts without host
   effective/permitted/inheritable/ambient capabilities, with NoNewPrivileges=1,
   as the non-root probe account. Root launch and pre-existing host capabilities
   are outside the permitted design; AppArmor capability rules are not scoped to
   a particular namespace and do not enforce these caller prerequisites.
2. Require exec of root-owned `/usr/bin/bwrap` to attach the setup profile. No permission
   may be inferred from executable pathname alone: record digest, ownership,
   package provenance, file capabilities and mode. All callers share this profile.
3. Require proof that Bubblewrap creates private namespaces, configures loopback/mounts, creates the
   nested user namespace for disable-userns and removes workload capabilities.
4. Require fixed target exec to stack the workload profile with setup confinement.
   Only after observed stacking can the child capability/userns denials be relied
   upon. They do not clear capability bitmaps, prevent all namespace operations,
   constrain Python code, or revoke existing descriptors. Later exec must remain
   confined or fail; there is no later-exec allow rule in the child skeleton.

Executable attachment is not authorization of a trusted caller. Any process able
to exec /usr/bin/bwrap may request the setup profile, including inside an existing
user namespace. A root/pre-capable caller could use permitted capabilities in
the host namespace if other required access checks permit it. NNP only constrains
privilege acquisition across exec; it does not remove existing capabilities or
prevent gaining capabilities by creating a user namespace. A dedicated VM limits
the blast radius but does not prove these controls. Do not activate this draft
until unauthorized invocation, environment, alias and descriptor cases have been
resolved. A restricted invocation architecture may be necessary; none is designed
or implemented here.

Blocking questions before activation:

The five high-severity review findings remain unresolved: unauthorized bwrap
invocation, capability permissions without namespace scope, executable/code
identity, NNP-compatible AppArmor transitions, and inherited environment/file
descriptors. The questions below and the procedure's negative-test matrix retain
these findings; documenting them does not resolve or approve the design.

- Does the target kernel/parser support the proposed stacked `px` syntax under
  NNP both on initial bwrap attachment and final exec? Upstream uses stacked
  transitions but its broad profile and ABI 5.0 cannot be copied as proof for
  Ubuntu 24.04. Never clear NNP or add fallback execution to resolve a denial.
- Resolve `/bin` and versioned Python aliases. Which loader/library mappings
  must both profiles permit for a successful stacked exec?
- What prevents caller-controlled bwrap argv from replacing /usr/bin/python3 in
  the sandbox mount tree, selecting arbitrary Python -c code, or omitting the
  expected isolation flags? No existing rule authenticates the target inode or
  fixed guest code. Missing permissions currently block startup, not these attack
  classes in a future completed profile.
- How is the setup loader protected from LD_PRELOAD/LD_LIBRARY_PATH and writable
  runtime files before bwrap processes --clearenv? How are inherited file, socket,
  namespace and directory descriptors closed or rejected? No such guarantee is
  established by the draft. NNP and lowercase px do not sanitize the environment.
- How are processes sharing the runner UID prevented from editing guest-owned
  namespace evidence or interfering with the controller? The current fixed probe
  trusts reviewed code; its guest-written JSON is not independent adversarial
  attestation. Do not put runner credentials in an attacker-accessible UID domain.
- Which operations require the withheld capabilities on the exact packaged build?
  Are deny events before or after namespace creation? Audit alone does not prove
  namespace scope. Do not grant missing capabilities without independent review.
- Does nested setup remain allowed while workload namespace creation is denied?
  Do existing distro profiles stack, conflict, or win attachment selection?
- The current namespace probe compares mnt/pid/net/user, not IPC/UTS/cgroup.
  Bubblewrap unshare-all contains optional cgroup behavior; independently verify
  all required identities rather than treating the flag as proof.
- Existing memory/CPU quota probes use a single active allocator/busy process;
  add reviewed multi-process and thread qualification cases. Existing direct
  cgroup.procs cleanup is insufficient alone for arbitrary descendant cgroups.
- No seccomp filter or hostile-code security review is established by this
  fixed-probe package. Kernel attack surface and same-UID runner access remain
  risks; no production or arbitrary hostile-workload authorization follows.

## Primary references

- [Bubblewrap v0.9.0 setup, capability drops and NNP](https://github.com/containers/bubblewrap/blob/v0.9.0/bubblewrap.c)
  and [loopback setup](https://github.com/containers/bubblewrap/blob/v0.9.0/network.c).
  Reference version is illustrative; qualify the actual installed package/source.
- [Upstream AppArmor bwrap-userns-restrict](https://gitlab.com/apparmor/apparmor/-/blob/master/profiles/apparmor/profiles/extras/bwrap-userns-restrict):
  demonstrates stacked child confinement, but broadly allows setup permissions.
- [Ubuntu AppArmor syntax](https://manpages.ubuntu.com/manpages/noble/man5/apparmor.d.5.html)
  and [user-namespace restrictions](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/).
- [Linux cgroup v2](https://www.kernel.org/doc/html/v6.6/admin-guide/cgroup-v2.html)
  and [GitHub ephemeral runners](https://docs.github.com/en/actions/reference/runners/self-hosted-runners).
- [Linux NNP semantics](https://docs.kernel.org/userspace-api/no_new_privs.html):
  LSM exec transitions need separate validation; the flag is not general syscall
  or namespace confinement.

See `qualification-procedure.md` for the approval-gated future exercise.

## Local validation of this review package

On the Linux development host, AppArmor parser 5.0.2 compiled the skeleton with
exit zero using the installed ABI 4.0 feature description as an offline target:

```bash
apparmor_parser -Q -K --kernel-features /etc/apparmor.d/abi/4.0 \
  docs/security/linux-isolation-review/firmavex-bwrap.apparmor.draft
.venv/bin/python -m pytest -q \
  tests/product/test_aggregate_isolation_probe.py \
  tests/product/test_namespace_diagnostics.py \
  tests/product/test_isolation_feasibility.py \
  tests/backends/test_process_security.py -ra
```

`-Q` disables kernel loading and `-K` disables cache loading/writing. No profile
was installed or activated. This checks parser syntax only, NOT target parser
compatibility, profile attachment, enforcement, completeness or NNP semantics.
The unchanged tests reported **59 passed, zero skips**. Local namespace behavior
does not qualify the future VM or its policy. No privileged aggregate probe was
run. No infrastructure, workflow runs, commits, pushes or private evidence were
modified. Runtime implementation and security test requirements are unchanged.
