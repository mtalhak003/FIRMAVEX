# Local execution and future isolated workers — Batch 8

## Current boundary

FIRMAVEX is an offline-first desktop and local stdio application for **trusted
projects, examples and host tools**. Compatible firmware may be defective; it
must not be intentionally hostile. The ARM, RV32 and Icarus tool processes parse
complex executable/HDL input and can contain exploitable defects. Firmware
emulation does not isolate the parser from the host. Verilog includes, simulator
plugins and tool configuration are especially sensitive. Existing path checks,
trust declarations, process ownership and quotas are defense in depth, **not a
hostile-input sandbox**. Untrusted requests remain rejected. No remote listener,
account, telemetry or public execution service is added.

Assets include projects/results, host files, credentials, other jobs, executable
identities, outcome/accounting receipts and availability. Attackers may control a
future uploaded project, image, HDL, filenames, process output and artifacts.
Administrators must trust the OS, hypervisor, runtime publisher, installer and
worker implementation. An administrator/kernel compromise is outside this model.
Physical MCU/FPGA hardware and arbitrary boards are unsupported.

## Enforced local controls and limits

- Versioned command/capability records, immutable execution contracts and explicit
  target compatibility; existing ARM accounting is unchanged.
- No shell interpolation of workload arguments. Owned process groups on Linux
  and kill-on-close Job Objects on Windows; bounded output, wall time and artifact
  handling. POSIX per-process address-space, CPU and file-size limits do not
  constitute aggregate job/process/storage quotas.
- Strict project/artifact paths and fresh output directories; input, tool and
  receipt identities; generation integrity and transactional runtime activation.
  Observable race detection is not an atomic filesystem snapshot.
- Cancellation must preserve original control-flow exceptions and cleanup
  diagnostics. A missing terminal receipt is incomplete, never safe or passed.
  No automatic rerun guesses missing evaluator accounting.
- Exports and logs can contain paths, source fragments and debugger information.
  Review/redact before publication; use per-user access controls and explicit
  operator retention. There is no new centralized retention/deletion service.

Windows/Ubuntu native qualification is limited to the recorded examples and
runtime identities. Windows Job Objects do not isolate network/filesystems.
Ubuntu process limits do not establish a sandbox. macOS Apple Silicon remains a
GUI preview: unified execution fails closed at the documented RLIMIT_AS admission
blocker. No controls are enlarged/disabled to admit macOS.

## Bounded Linux feasibility diagnostic

`python -m tools.isolation_feasibility --output /new/path/assessment.json` runs
only a fixed, repository-owned diagnostic, **not user firmware, HDL or an arbitrary
command**. It uses Bubblewrap user/mount/PID/network namespaces, drops capabilities,
disables nested user namespaces, clears inherited environment/secrets, exposes a
read-only `/usr` runtime and explicit read-only input, creates private `/proc`,
minimal `/dev`, and size-limited `/tmp` and `/work` tmpfs mounts. No home, repository,
SSH directory, host socket, `/sys`, host `/etc` or Docker socket is mounted.
The permitted `/usr` tree is the host's trusted OS runtime, not a curated minimal
worker image. This diagnostic is intentionally not an installed execution backend.

The guest tests negative writes, hidden host marker and host PID, namespace
identities, loopback-only interfaces and inability to connect to an actual parent
listener. The existing owner enforces an 8-second wall deadline, 512 MiB
per-process address space, 9 CPU seconds (existing ceil(timeout)+1 policy),
1 MiB file size and 32 KiB logs. Guest allocation and storage-overflow checks
exercise denial. A deliberately lingering guest descendant must disappear when
namespace init exits; the parent checks owned marker processes and reaps its
launcher. Timeout/cancellation paths are tested too. This does **not** test every
possible socket family, kernel escape, fork bomb or race.

Exit zero means the feasibility assessment was recorded as blocked or its fixed
mechanism checks passed. Boundary failures, malformed results, timeouts, cancellation
and cleanup/inspection failures return nonzero, with evidence retained. Inspect
`status`, `checks`, cleanup and diagnostics; `blocked` is not a successful mechanism check. A successful
assessment is `mechanism_checks_passed_not_qualified`, always with
`untrusted_execution_authorized=false`. Missing tools, namespace denial, errors
and cleanup failures remain explicit. CI may lack Bubblewrap or disallow user
namespaces; that is recorded rather than replaced with mocks. No `/dev/kvm` or
writable cgroup delegation is available in the current cloud environment.

## Required future worker boundary (not implemented)

Prefer a dedicated disposable VM per tenant/job with a minimal signed/pinned
image. A reviewed Linux sandbox is an alternative only after independent
adversarial qualification. Before any untrusted admission, require:

1. Delegated cgroup v2 memory.max, pids.max and CPU quotas, isolated UID ownership,
   aggregate storage/inode quotas and bounded artifact/log retention; test denial
   and crash recovery, not merely configuration strings.
2. A minimal read-only runtime image, private writable scratch, no host mounts or
   secrets, network denied outside specifically authorized job-local channels,
   restricted device/syscall access and a maintained kernel/VM boundary.
3. Artifact extraction by a separate trusted process after worker termination:
   no symlinks/hardlinks/devices/path traversal, bounded count/bytes, hash-bound
   receipts and transactional fresh output. Never execute extracted content.
4. Authenticated encrypted transport, per-user/tenant authorization and quotas,
   replay-resistant job identifiers, signed worker identity, revocation, and
   explicit separation of administrative diagnostics from client feedback.
   Local stdio version 1 is not network authentication; do not expose it as TCP.
5. Durable admission/start/terminal records; uncertain work after crashes stays
   unknown/interrupted. Kill the complete VM/cgroup, verify resource reclamation,
   and require explicit authorization for a fresh attempt. Preserve charged
   accounting and original evidence. Never synthesize execution receipts.
6. Independent security review and escape/abuse tests on each supported boundary.

A namespace probe cannot satisfy these gates. Hostile workloads and public remote
execution remain disabled until this work is independently verified.
