# ADR 0004: separate Windows candidate evidence from production admission

- **Status:** retrospective record of implemented admission/evidence separation;
  candidate promotion remains unresolved.
- **Evidence date:** 2026-11-07 (Asia/Karachi), isolated candidate workflow commit;
  subsequent evidence tooling is recorded through Batch 28.
- **Record prepared:** 2026-11-09 (Asia/Karachi).

## Context and documented decision

The [candidate source-stage record](../product/batch23-runtime-candidate.md)
documents MSYS2 QEMU 11.1.3 / GDB 18.1 as a new candidate while preserving the
existing Windows QEMU 11.1.2 production profile. A full publisher-signed rolling
transaction may acquire a candidate; it is not proof of immutable reproduction,
complete DLL closure, license/source delivery or product qualification.

The implemented decision is to collect isolated native candidate evidence and
assert production rejection before/after source probing. Candidate records retain
`candidate_only=true` and `production_qualified=false`. No changed production
hash, environment-variable admission bypass or fake tool identity is supplied.
Source, GUI, frozen and installed rejection/lifecycle observations are not positive
candidate application execution.

## Recorded basis and consequences

The source-stage document states that historical profile-specific qualification
does not qualify a new runtime identity. The [Batch 28 positive qualification
proposal](../product/batch28-positive-qualification-proposal.md) records the
remaining decision: authentic recovery of the already qualified runtime can test
the unchanged application, while any new profile/lab policy requires separate
authorization. Neither option is silently selected by a passing candidate run.

The immutable signing/package, archive-to-installed ownership, native DLL and
license requirements remain open until actual original evidence closes them.
Administrative metadata consistency, static PE imports and source-stage test
success cannot authenticate missing archives or promote a profile.

## Implementation and validation references

- [Original historical Windows admission commit 32515ba](https://github.com/mtalhak003/FIRMAVEX/commit/32515bad177dfecbb02987e3608e46ea45b3fc5e).
- [Isolated candidate stage 4d13cde](https://github.com/mtalhak003/FIRMAVEX/commit/4d13cdea75df0cf6ca272430f412bcce7dbacac3).
- [Batch 28 tooling 66fba9b](https://github.com/mtalhak003/FIRMAVEX/commit/66fba9b9a339b300a57df0974487d675bdc9ea8c).
- [Admission regressions](../../tests/product/test_platform_support.py),
  [candidate runtime checks](../../tests/product/test_windows_runtime_candidate.py)
  and [installed candidate lifecycle checks](../../tests/product/test_windows_candidate_installed.py).
- [Current progress and evidence classifications](../product/development-progress.md)
  distinguish CI observations, user-reported ZIP verification and unproven work.

## Remaining work

Close authentic package/trust, original artifact, native dependency and legal/source
evidence; independently qualify positive product paths and consumer acceptance;
then obtain a separately authorized profile decision. The latest user-reported
artifact verification does not itself close these production-release requirements.
