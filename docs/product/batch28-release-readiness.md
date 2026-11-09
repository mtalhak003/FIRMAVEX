# Batch 28: runtime qualification and release readiness

**Release status: NOT READY. No runtime promotion is authorized.**
Baseline: `c42cdd000dbd117dee558fd346aa8b653ac7bf3f`.
Review date: 2026-11-09 (Asia/Karachi). Work was restricted to the approved
Batch 23 worktree. The original checkout and protected private Windows evidence
were not accessed. No firmware, installer, research campaign or CI dispatch was
executed by this batch.

## Evidence from the existing Windows run

Fresh HTTP 200 reads of [run 42618949135][run], its [attempt 1][attempt] and
[job 129165814000][job] identify source
`c42cdd000dbd117dee558fd346aa8b653ac7bf3f`, successful status and duration
**16 minutes 19 seconds**. The public job page records success for signed vendor
acquisition, inventory/rejection, actual ARM regressions, ownership/resource
checks, source probe, source CLI/worker rejection, GUI rejection, frozen build
and rejection, unsigned installer build, installed lifecycle/rejection and
evidence upload. These are **CI observations at the baseline**, not new Batch 28
native measurements or independently recounted receipts.

The artifact listed for this exact run/attempt is **13675538108**, named
`Windows-UNQUALIFIED-runtime-candidate-c42cdd000dbd117dee558fd346aa8b653ac7bf3f`.
Its publicly displayed digest matches the supplied original ZIP SHA-256:
`f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`.
It is not an independently computed digest of downloaded bytes.

**Original artifact retrieval remains blocked.** The artifact metadata and
authenticated ZIP API requests returned `Forbidden`, including escalated ZIP
access. Public download returned HTTP 404. These results do not establish
expiration or nonexistence. No original ZIP, receipts, JUnit files or authentic
vendor archives were reconstructed. Verification with
`--require-product-paths --require-installed-path` was **NOT RUN against the
original** because its bytes were unavailable. That is a retrieval blocker,
not a reported verifier pass or failure.

## Completed engineering work

- [Artifact acquisition/verification procedure](batch28-artifact-verification.md):
  exact run/attempt/artifact tuple, original-byte checksum, authorized browser/API
  paths, no-clobber external storage and both required verification scopes.
- `tools/windows_candidate_artifact.py`: bounded strict metadata-to-ZIP binding,
  source/repository/run/attempt/digest/time consistency, post-review metadata
  rereads and existing read-only ZIP verification. It downloads nothing and
  explicitly does not authenticate metadata or artifact origin.
- `tools/windows_candidate_closure.py`: bounded actual-byte PE32+ x64 ordinary
  import graph checks with reviewed file pins, explicit resolution roots,
  missing/ambiguous-import rejection, resource limits and observed-change checks.
  It executes/extracts nothing and never claims complete dynamic DLL closure,
  package ownership, publisher authentication or qualification.
- [Fail-closed runtime provenance workflow](batch28-runtime-provenance.md):
  authentic archives, independent signing inputs, compatible package closure,
  archive-to-installed binding, native DLL audits, actual notices/source delivery
  and immutable reproduction inputs. Missing stages remain blockers.
- [Positive product-path proposal](batch28-positive-qualification-proposal.md):
  source, frozen, installed and GUI criteria, preserving the existing gate.
- [Consumer Windows checklist](batch28-consumer-windows-checklist.md):
  clean standard-user/offline/installation/GUI/export/recovery/accessibility and
  failure-handling journeys, all requiring separately retained native evidence.
- Meaningful regression tests and an extended candidate-tool isolation check.
  Candidate tools remain outside shipped product entry points and manifests.

## Qualification matrix

PASS always applies only to the evidence class and scope named here.

| Requirement | Status | Evidence class | Basis and remaining limit |
|---|---|---|---|
| Local/remote baseline and preserved production/research inputs | PASS | Independently inspected Git state | Approved SHA and remote matched; production, runtime pins, packaging and research inputs unchanged. |
| Exact existing run/attempt/source/artifact association | PASS | Public GitHub metadata | Fresh run/attempt/job pages and displayed digest, not downloaded ZIP bytes. |
| Existing native ARM/resource/cleanup assertions | PASS, limited | CI observation | Public successful steps at the baseline. Original receipts and JUnit recount unavailable. |
| Source CLI/worker, GUI and frozen admission rejection | PASS, limited | CI observation | Existing run's successful rejection steps; no positive product execution implied. |
| Installed lifecycle/rejection | PASS, limited | CI observation | Existing unsigned installation/reinstall/GUI-startup/uninstall assertions. Sentinel data is not an authoritative saved-results archive. |
| Original artifact digest, receipts, package inventories and JUnit consistency | NOT PROVEN | Original bytes unavailable | Both required-scope checks remain unexecuted against the original ZIP. |
| Artifact-binding and static import-audit contracts | PASS, local | Automated regression evidence | Synthetic/malformed input tests and bounded real-byte file reads; no vendor/native qualification. |
| Authentic signed archives and trusted signing inputs | NOT PROVEN | Missing originals/trust inputs | No complete actual package/signature set or independently approved keyring/tool pins supplied. |
| Compatible mandatory package closure | NOT PROVEN, actual set | Existing verifier prepared | Must run against authentic signed `.PKGINFO`; synthetic-key regressions are insufficient. |
| Archive-to-installed ownership and complete native DLL closure | NOT PROVEN | Native/payload audit outstanding | New static graph support does not establish Windows loader/API-set/forwarder/dynamic behavior or package origins. |
| License notices, corresponding source and distribution clearance | NOT PROVEN | Review outstanding | Recipe declarations and `pacman -Qi` metadata cannot close legal/source delivery obligations. |
| Candidate membership in existing production profile | FAIL, expected | Unchanged version/hash gate | QEMU 11.1.3 differs from qualified 11.1.2; rejection remains required. |
| Positive source/frozen/installed execution, replay and export | NOT PROVEN | Blocked by unchanged policy | No bypass or profile promotion. A separate reviewed qualification decision is needed. |
| Consumer standard-user/offline/accessibility/low-disk/recovery acceptance | NOT PROVEN | Native consumer trial outstanding | Hosted CI and smoke tests do not establish these journeys. |
| Signed public installer and release approval | NOT PROVEN | Credentials/release review outstanding | Existing candidate installer remains unsigned; no signing or public-beta claim. |

## Exact remaining actions

1. Use authorized GitHub access to download the original artifact and metadata;
   follow the exact [verification procedure](batch28-artifact-verification.md).
   Preserve nonzero results and all original files. Do not relabel a synthetic
   fixture or repackaged directory as original evidence.
2. Obtain the authentic compatible signed package set and independently trusted
   signing/verifier inputs. Close package, archive/member/installed, native DLL,
   notice/source and immutable replay requirements in the provenance workflow.
   No automatic redistribution or installer integration is authorized here.
3. Review and separately authorize the positive product-path qualification
   decision. The current candidate cannot pass the unchanged production gate.
   Then run the declared native source/frozen/installed/GUI scope and consumer
   checklist, preserving failures and truthful evaluator accounting.
4. Review actual original evidence and release/signing decisions before any
   versioned production-profile update. Neither this matrix nor green CI is
   automatic approval. No new workflow run was dispatched in Batch 28.

## Local validation

New-tool tests passed **103 tests** with no skips. Final focused validation passed
**488 tests, 6 skipped**, in 3.21 seconds. Broader regression/security validation
passed **1,291 tests, 26 skipped, 31 deselected**, in 47.04 seconds. There were
**no failures or errors**. The selections overlap and are not additive or a full
repository-suite result. Broader skips cover six native candidate checks, five
Windows ownership/supervisor cases, two Windows/macOS path APIs and thirteen
missing ARM/RV32/HDL desktop-tool cases. The broader `not actual_` expression
excludes 31 named cases; focused tests separately passed the real-code synthetic
ZIP composition and the ephemeral synthetic-key GnuPG regression.

Exact final commands from the approved checkout:

```sh
QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_windows_candidate_artifact.py tests/product/test_windows_candidate_closure.py \
  tests/product/test_windows_candidate_evidence.py tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_product.py tests/product/test_windows_candidate_installed.py \
  tests/desktop/test_windows_candidate_rejection.py tests/product/test_windows_runtime_candidate.py \
  tests/product/test_platform_support.py tests/product/test_versioned_install_ci.py

QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_windows_candidate_artifact.py tests/product/test_windows_candidate_closure.py \
  tests/product/test_windows_candidate_evidence.py tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_product.py tests/product/test_windows_candidate_installed.py \
  tests/product/test_windows_runtime_candidate.py tests/product/test_platform_support.py \
  tests/product/test_ci_diagnostics.py tests/product/test_runtime_setup.py \
  tests/product/test_runtime_pack.py tests/product/test_tools.py tests/product/test_worker.py \
  tests/product/test_protocol.py tests/product/test_supervisor.py tests/product/test_windows_job.py \
  tests/product/test_runtime.py tests/product/test_services.py tests/product/test_store.py \
  tests/product/test_arm_reproduction_summary.py tests/product/test_packaging.py \
  tests/product/test_packaging_universal.py tests/product/test_versioned_install_ci.py \
  tests/backends/test_records_security.py tests/backends/test_process_security.py \
  tests/desktop -k 'not actual_'
```

Actionlint 1.7.7 (`-shellcheck=`), Python syntax, Bash documentation syntax,
relative document links, locked build-input versions and whitespace checks
passed. ShellCheck and native PowerShell/installer validation were not available.
Production, research, firmware, packaging and workflows remain unchanged against
the baseline. No generated runtime binaries, downloads or evidence archives are
included in the changes.

No local Linux regression establishes native Windows execution. GnuPG is present;
bsdtar, vercmp, QEMU/GDB and native PowerShell were unavailable in this environment.
The original-archive verifier and real signed-package/PE audit were not run on
missing evidence. Synthetic fixtures are labelled and never substituted for it.

[run]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135
[attempt]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135/attempts/1
[job]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135/job/129165814000
