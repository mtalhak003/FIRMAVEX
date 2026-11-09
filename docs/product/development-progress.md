# Development progress

## November 9, 2026 — Windows candidate evidence and release preparation

**CI observations.** Batch 27 native Windows [run 42618949135][run], attempt 1,
succeeded at `c42cdd000dbd117dee558fd346aa8b653ac7bf3f`. Successful checks included
ARM execution/resource behavior, source/GUI/frozen admission rejection, and the
installed-product lifecycle: installation, same-package reinstall, GUI startup,
external sentinel preservation and owned uninstall cleanup. These scoped checks
do not establish positive candidate product execution, distinct-version upgrades,
preservation of authoritative saved results or consumer-machine acceptance.

**User-reported artifact verification.** The user reports that the original
Batch 27 ZIP verifier **PASSED**, requiring both product-path and installed-path
checks: **19 receipts; 97 JUnit passed, 10 skipped, zero failures and zero errors**.
Artifact ID: `13675538108`. Original archive SHA-256:
`f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`.
This result is user-reported; the original bytes and verifier output were not
independently reviewed in this Codex environment. Earlier retrieval limitations
remain historical observations, not a claim that the user's verification failed.

**Batch 28 delivery.** Commit
`66fba9b9a339b300a57df0974487d675bdc9ea8c` added read-only artifact-metadata
binding, bounded static PE import auditing, fail-closed provenance procedures,
a positive product-path qualification proposal and a consumer-Windows checklist.
Local validation recorded 488 focused tests passed with 6 skips, and 1,291 broader
regression/security tests passed with 26 skips and 31 deselections; neither
selection establishes native Windows qualification. See the
[Batch 28 readiness matrix](batch28-release-readiness.md) for scope and limitations.

**Remaining requirements.** Production qualification still requires authentic,
immutable signed packages and independent trust inputs; package/archive-to-installed
and native DLL closure; license/corresponding-source review; and separately
authorized positive source, frozen and installed product execution/reproduction/
export testing. Consumer acceptance still requires standard-user and enforced
offline operation, accessibility, low-disk/failure/recovery handling, real saved-data
preservation and release-signing review. QEMU 11.1.3 remains production-rejected;
no runtime approval or public-release readiness is claimed. Batch 29 has not begun.

[run]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135
