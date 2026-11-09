# ADR 0001: versioned, supervised local execution

- **Status:** retrospective record of implemented architecture.
- **Evidence date:** 2026-10-11 (Asia/Karachi), earliest product-foundation commit;
  later GUI/local-interface behavior is documented separately below.
- **Record prepared:** 2026-11-09 (Asia/Karachi).

## Context and documented decision

The [Batch 1 record](../product/batch1.md) describes a CLI and supervised execution
worker intended to support a later PySide6 application. The [Batch 2 desktop
record](../product/desktop.md) states that firmware execution uses the same
supervised worker and evaluator accounting. The [local interface v1
record](../product/local-worker-interface.md) later documents a local client using
the same Supervisor, worker and backend services, rather than a second execution
path.

The implemented decision is to keep product execution in supervised services
behind bounded, versioned commands/events, shared by CLI, desktop and the local
interface. One worker admits one active job. Cancellation is explicit; recovery
and inspection do not automatically rerun firmware or guess missing accounting.

## Recorded basis and consequences

The sources above establish service reuse and preservation of evaluator counts,
SQLite records and worker wire compatibility. They also document bounded protocol
messages, administrator-owned diagnostics, process ownership and cleanup. This
record does not claim that a particular framework comparison or alternatives
meeting occurred; no such decision transcript is retained in these sources.

The local stdio facade is a versioned local contract, not a public network
service or remote authentication system. Current filesystem/user permissions are part of its trust
boundary. Process supervision and resource controls do not establish hostile-code
isolation. Windows and POSIX ownership implementations need their own native
evidence; later platform support cannot be inferred from Batch 1 alone.

## Implementation and validation references

- [Product foundation commit d0a42c7](https://github.com/mtalhak003/FIRMAVEX/commit/d0a42c79fd20172184135d1ccf6d2ab8907a7c69).
- [Responsive desktop commit 406dfe0](https://github.com/mtalhak003/FIRMAVEX/commit/406dfe0f3e1e26689869951e69b4b01ba486b119).
- [Local job-interface commit 9b51918](https://github.com/mtalhak003/FIRMAVEX/commit/9b51918452eeb6f7e84585cb2fac6dea4c7bb2eb).
- Existing [protocol](../../tests/product/test_protocol.py),
  [worker](../../tests/product/test_worker.py) and
  [supervisor](../../tests/product/test_supervisor.py) regressions exercise those
  contracts. Test presence is not a fresh test result; historical results belong
  to their dated validation records.

## Remaining work

Any remote transport needs a separately designed authentication, upload,
authorization, worker-loss accounting and independently qualified isolation
boundary. Preserve the existing local contract until such changes are explicitly
reviewed. This retrospective record adds no implementation or qualification.
