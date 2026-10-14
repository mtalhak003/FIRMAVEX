# Local worker interface v1

Batch 7 adds an asynchronous local client facade while preserving worker wire v1,
backend receipts, SQLite, research protocols and evaluator accounting.

The desktop continues using its existing controller and Supervisor. `LocalSession`
uses that **same Supervisor, worker and backend services**, with a bounded job
registry and no alternative execution path. Python clients need no Qt. A frozen
console includes both the existing worker and the new gateway.

## Transports and boundaries

- Installed: `firmavex-local` or `python -m firmavex.product.local_stdio`.
- Frozen: `FIRMAVEX --firmavex-local` (Windows: `FIRMAVEX.exe`).
- One UTF-8 JSON object per line, at most 1 MiB, depth 32; duplicate keys,
  nonfinite values and unsupported envelope/version fields are rejected.
- Versioned private stdin/stdout pipes, **no socket or network listener**. The
  client owns the spawned process/handles; local filesystem permissions and OS
  user privileges are the access boundary. No token authenticates another user.
  Same-user malware/debugging and administrators are not isolated.
- JSON stdout is protocol only. Diagnostics are administrator-owned. No account,
  telemetry or mandatory external service is involved. QEMU/GDB still communicate
  over their existing dynamically selected localhost debugger port.

Request (each request ID is unique within a connection):

```json
{"interface_version":1,"request_id":"hello","operation":"negotiate","payload":{}}
```

Response:

```json
{"interface_version":1,"request_id":"hello","ok":true,"payload":{"interface_version":1,"commands":["..."],"policy":{"...":"..."}}}
```

The example response abbreviates the descriptive capabilities. Availability and
current-host qualification are explicitly **not** established by negotiation.
Version mismatch fails closed. New fields/operations require explicit negotiation;
no implicit downgrade dispatches a job. Existing worker v1 gains only the additive
`capabilities` command, with unchanged old envelopes/commands.

## Operations

| Operation | Payload | Result |
|---|---|---|
| negotiate | `{}` | Commands, profiles, support and resource/trust policy |
| submit | command, payload, optional timeout_seconds | Random opaque session job_id |
| status | job_id | Running/cancellation_requested/finished/failed, last 64 bounded progress summaries |
| cancel | job_id | Cancellation request state, not a completion claim |
| result | job_id | Terminal result or structured error; rejected while active |
| forget | job_id | Removes terminal session metadata; never deletes saved files |

Allowed commands: capabilities, doctor, backend_check, backend_prepare,
backend_execute, backend_inspect, backend_reproduce and backend_export. Their
payloads are the existing worker command payloads. Runtime installation, arbitrary
executables, legacy unchecked execution and worker shutdown are not tunneled.
Execution/reproduction require explicit `trusted_example` or `trusted_project`.
No label makes unknown or hostile projects sandboxed. File/path/artifact checks,
backend resource caps and evaluator ownership remain in existing services.

One active job and at most 32 retained jobs per session; forget terminal metadata
to release capacity. Connection lifetime is at most 65536 request frames. Worker
deadlines are finite (default 3600 seconds; allowed 0.1–86400). Backend limits are
additional, not replaced by this deadline. Multiple independent sessions do not
provide a host-wide quota or scheduling policy.

`finished` means the worker returned a terminal response **after supervision**;
it does not mean the test passed. Read the result's outcome, measurement mode,
completion, cleanup and accounting fields. Errors use category/message/details.
Transport previews retain their existing truncation metadata; full archives stay
authoritative. An oversized response returns transport_limit instead of inventing
missing evidence. No automatic retry/restart occurs.

EOF or normal session close requests cancellation and waits for bounded worker
cleanup. A process/host crash can leave unknown interrupted accounting: reopen
its persisted run using backend_inspect and the existing ownership/receipt rules.
The session registry is **ephemeral**, not a durable queue. Session IDs cannot be
recovered on reconnect and are not remote credentials. Never recreate absent
physical execution evidence or infer charges from progress events.

## Python example

```python
from firmavex.product.local import LocalSession
with LocalSession() as client:
    job = client.submit("capabilities", {})
    # Poll client.status(job) until terminal, then client.result(job).
```

Archives and diagnostic exports may contain source paths, inputs, logs and host
metadata. Keep them private by default; review/redact copies for publication.
Retention is explicit: forgetting a job does not remove archive data. Existing
report export verifies artifacts before creating a fresh directory.

## Future remote boundary — design only

A browser/API broker must not expose this trusted-local pipe interface directly.
A future implementation requires authenticated users and independently enrolled
workers (for example mutually authenticated TLS with rotating worker identities),
per-project authorization and principal-bound jobs/artifacts, replay protection,
protocol negotiation and revocation. A job UUID alone is not authorization.

Workers must advertise supported targets and independently verified isolation
policies, accept bounded content-addressed artifacts rather than client filesystem
paths, reject traversal/link/size/hash violations, and enforce tenant/worker quotas
before admission. Hostile inputs require a separately verified VM/container/OS
isolation policy; today's trusted execution is insufficient.

A remote scheduler needs durable admission leases, monotonic attempt identities,
worker-loss accounting, cancellation acknowledgment, expiration and audit logs.
It must preserve completed receipts, distinguish unknown work from charged/verified
work, and require explicit restart authorization. Network retries must never imply
firmware retries. Logs need access control, redaction and retention policies.
None of worker registration, remote authentication, multi-tenant isolation,
persistent scheduling, remote artifact transfer or a public endpoint is implemented.
