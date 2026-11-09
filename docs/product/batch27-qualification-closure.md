# Batch 27: Windows evidence review and installed-product checks

**Production qualification remains unapproved.** Starting revision:
`43f932a2f8fa1c34762ae8088a427b328ee6fc54`. Review date: 2026-11-09 UTC.
No runtime profile, executable pin, signature policy, package acquisition source,
shared security validation or research data is changed. No workflow is dispatched
by this batch.

## Exact native run and artifact

The public [run page][run], its explicit [attempt 1 page][attempt], and the
[job page][job] were retrieved successfully. Their embedded navigation identifies
`attempt=1`, job **129140770535**, source revision
`43f932a2f8fa1c34762ae8088a427b328ee6fc54`, and the following artifact:

| Field | Publicly observed value |
|---|---|
| Run | 42611492697, attempt 1 |
| Artifact ID | **13670768664** |
| Name | `Windows-UNQUALIFIED-runtime-candidate-43f932a2f8fa1c34762ae8088a427b328ee6fc54` |
| Displayed SHA-256 | `882b9bcbaf574f600af447b9f05ae9fc35ed0c9da856701d1a46aa271a251c61` |
| Displayed duration | 11 minutes 15 seconds |

This association comes from this exact run/attempt, not the older Batch 25/26
artifact listings. The public job records every listed step as successful,
including signed vendor acquisition, inventory/production rejection, real ARM
regressions, ownership/resource checks, source probe, source CLI/worker rejection,
GUI rejection/revalidation, frozen build and frozen CLI/worker rejection.

**The original ZIP was not retrieved.** Authenticated Actions API requests returned
`Forbidden`, including an escalated attempt. The public artifact download and a
public step-log endpoint returned HTTP 404. These responses do not establish
expiry or absence. The displayed digest is metadata, not an independently
computed digest of downloaded bytes. No receipts, original JUnit counts, inventory
entries, signatures or missing records were reconstructed or substituted.

The existing verifier can review this artifact after authorized retrieval:

```sh
python -m tools.windows_candidate_evidence /outside/repository/original-candidate.zip \
  --sha256 882b9bcbaf574f600af447b9f05ae9fc35ed0c9da856701d1a46aa271a251c61 \
  --revision 43f932a2f8fa1c34762ae8088a427b328ee6fc54 \
  --run-id 42611492697 --require-product-paths
```

Use the original GitHub ZIP; do not extract and repackage it before checking.
This command has **not** been run against the inaccessible original. It checks
19 ordered source receipts, eight accounting cases, exact executable pins,
installed-package inventory, effective signature policy, vendor-file inventory,
trusted bundled image, cleanup, and required native JUnit cases. Source/GUI/frozen
rejection records must agree with the source/run and corresponding passed tests.
Successful consistency verification would still not authenticate the runner,
independently verify publisher signatures or authorize production admission.

## Installed-product checks prepared in this batch

The manual-only candidate workflow now builds the existing unsigned per-user
`packaging/windows.iss` installer and invokes a separately owned native installed
lifecycle check. Candidate tools remain outside application packages and frozen
entry points. The installer itself and shared security controls are unchanged.

The check is restricted to the exact native Windows candidate CI context. It
refuses an existing registered FIRMAVEX installation, uses a fresh destination
under `RUNNER_TEMP`, disables shortcut creation, and does not accept a supplied
`installed` label as proof of installation. It compares installed console and GUI
identities with the frozen build, exercises installed CLI/worker rejection and
GUI startup, checks same-package reinstall, and waits for the owned uninstaller
tree. External sentinel bytes must survive, and installed executables must be
absent afterward. Failure and interruption retain a failed lifecycle record;
cleanup failures cannot produce a successful report.

Installer phase logs are retained under the owned working directory and are
subject to its existing artifact-size and process-time bounds. They may contain
temporary runner paths; review these administrative logs before wider publication.

The separate lifecycle record links installer identity, executable identities,
process outcomes and cleanup to the installed admission report. Its native JUnit
case must pass. Optional present installation claims are checked rather than
silently promoted. A future authorized run can require this additional scope with
`--require-installed-path`. Do **not** require it for run 42611492697, which
predates these checks. The existing admission report's
`installation_verified=false` remains unchanged; installation assertions belong
to the separate lifecycle record.

These are **prepared checks, not new Windows measurements**. GUI startup is not a
human usability or accessibility trial. Same-package reinstall is not a
distinct-version upgrade, rollback or interrupted-install recovery test. A
disposable hosted runner does not establish a standard-user consumer machine,
network-enforced offline operation, Smart App Control compatibility, low-disk
handling, signing or public-beta readiness.

The identity comparison covers the two application executables, not the complete
installed DLL/data tree. The preservation sample is newly created external
sentinel bytes, not a pre-existing authoritative result archive. An interruption
before Inno creates an uninstaller may leave partial application files on the
disposable runner; this is recorded as failed cleanup, preserves the original
interruption, and cannot produce a passing report. It is not a rollback claim.
The ZIP verifier links the console identity to the earlier frozen report.
Installer and GUI digests are retained producer declarations, without independent
build-origin anchors or corresponding binary payloads in the evidence ZIP.
Consistency checks neither authenticate those builds nor provide atomic snapshots
of files controlled by another writer.

## Positive execution and vendor trust boundaries

Production admission intentionally rejects the candidate QEMU. No fake tool
identity, gate monkeypatch, injected executor or candidate profile is used to
enable positive product execution. Positive execution, reproduction and result
exports through the source, frozen and installed product remain **NOT PROVEN**.
The earlier low-level ARM source probe is separate evidence and cannot close
this product-path requirement. A separately reviewed, explicitly authorized
qualification design or profile promotion is required before that work.

The known candidate pins are QEMU 11.1.3,
`f7e69cf3c284bad6a3b1c4159d2a88001f285c28f890dd2f8e56186682840cc7`,
and GDB 18.1,
`f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236`.
The production QEMU pin remains 11.1.2,
`1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244`.
Public preflight success is indirect evidence that its assertions passed; the
observed identity records themselves still require ZIP retrieval and verification.

Authentic QEMU archive/signature probes at `repo.msys2.org/mingw/ucrt64/` still
failed at the proxy CONNECT boundary with HTTP 403. No authentic complete archive
set or trusted signing inputs were obtained. The pinned official source recipes
and license declarations documented in [Batch 26](batch26-promotion-readiness.md)
remain limited source evidence. They do not authenticate binaries or clear
corresponding-source/distribution obligations.

Future acquisition evidence additionally retains `pacman -Qi` output for installed
package versions, validation declarations and license metadata. This is
supplementary package-manager metadata, not detached-signature verification.
Retain the complete compatible archives, actual publisher signatures,
independently trusted keyring/fingerprints, manifest and verification-tool pins;
then use `tools.windows_candidate_packages` as documented in Batch 25. Installed
metadata alone does not prove dependency closure, archive-to-installed executable
binding, dynamic DLL closure, source completeness or redistribution rights.

## Qualification matrix

| Requirement | Status | Evidence and limit |
|---|---|---|
| Exact run/attempt/source/artifact metadata | PASS | Fresh public pages above; original archive bytes unavailable. |
| Native ARM, resource/ownership, source/GUI/frozen rejection assertions | PASS, limited | Public successful job steps at the baseline; no independent original log/JUnit recount. |
| ZIP identities, receipts, accounting and JUnit consistency | NOT PROVEN | Original ZIP download blocked; verifier fixtures cannot substitute. |
| Installed lifecycle/linked-evidence regression contracts | PASS, local | Synthetic positive/negative fixtures and real host packaging/helper checks; no native installer execution. |
| Strict rejection of candidate in current production profile | PASS, containment | Successful public rejection steps; qualification constants unchanged. |
| Candidate membership in current production profile | FAIL, expected | QEMU version and digest differ. No promotion authorized. |
| Installed lifecycle/rejection evidence | NOT PROVEN, native | New checks prepared; no dispatch or native run of this batch. |
| Positive source/frozen/installed execution, replay and exports | NOT PROVEN | Correctly blocked by production admission. |
| Signed immutable package set and compatible closure | NOT PROVEN | No original package/signature set and independently trusted inputs. |
| Binary/source/license and dynamic DLL closure review | NOT PROVEN | Recipe/license declarations and installed metadata are insufficient. |
| Consumer acceptance and signed public release | NOT PROVEN | Real standard-user/offline/low-disk/accessibility/signing trials remain. |

## Next actions, requiring separate authorization where applicable

1. Retrieve artifact 13670768664 through an authorized GitHub account; preserve
   its metadata and original bytes, and run the exact verifier command above.
2. Review this batch and explicitly authorize a native candidate workflow run at
   its new commit. Retrieve its own exact attempt/artifact and require installed
   scope. Do not reuse this batch's artifact ID or digest for a new run.
3. Obtain and verify authentic signed package closure and legal/source evidence;
   separately review the positive product-path qualification decision and
   consumer acceptance plan. None of these prerequisites is waived by green CI.

## Local validation

The pre-change focused selection passed **303 tests**, with **5 native Windows
skips**. Final focused validation passed **385 tests**, with **6 native Windows
skips**, in 2.59 seconds. The broader selection passed **1,163 tests**, with
**22 skipped and 27 deselected**, in 47.15 seconds. There were no failures or
errors. A separate packaging/installer-helper run passed **35 tests**. These
overlapping selections are not additive and are not a full repository-suite run.

Broader skips cover six candidate-native checks, one Windows supervisor test,
Windows/macOS path APIs, and thirteen missing-tool ARM/RV32/HDL desktop cases.
The `not actual_` expression intentionally excludes 27 named cases; the focused
selection separately passed the actual GnuPG test using an ephemeral synthetic
key, which does not establish vendor trust. No local result establishes native
Windows execution. Commands from the approved checkout:

```sh
QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_windows_candidate_evidence.py tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_product.py tests/product/test_windows_candidate_installed.py \
  tests/desktop/test_windows_candidate_rejection.py tests/product/test_windows_runtime_candidate.py \
  tests/product/test_platform_support.py tests/product/test_versioned_install_ci.py

QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_windows_candidate_evidence.py tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_product.py tests/product/test_windows_candidate_installed.py \
  tests/product/test_windows_runtime_candidate.py tests/product/test_platform_support.py \
  tests/product/test_ci_diagnostics.py tests/product/test_runtime_setup.py \
  tests/product/test_runtime_pack.py tests/product/test_tools.py tests/product/test_worker.py \
  tests/product/test_protocol.py tests/product/test_supervisor.py tests/product/test_runtime.py \
  tests/product/test_services.py tests/product/test_store.py tests/product/test_arm_reproduction_summary.py \
  tests/product/test_packaging.py tests/product/test_packaging_universal.py \
  tests/product/test_versioned_install_ci.py tests/backends/test_records_security.py \
  tests/backends/test_process_security.py tests/desktop -k 'not actual_'

QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_packaging.py tests/product/test_packaging_universal.py \
  tests/product/test_versioned_install_ci.py
```

Actionlint 1.7.7 (`actionlint -shellcheck= .github/workflows/windows-runtime-candidate.yml`),
Python syntax for all five affected Python files, locked build-input checks and
whitespace checks passed. ShellCheck, native PowerShell/Inno validation and a
native Windows execution environment were unavailable. Production, research,
firmware and packaging inputs compare unchanged against the starting revision;
the preserved Batch 23C investigation document also retains its prior digest.

[run]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42611492697
[attempt]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42611492697/attempts/1
[job]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42611492697/job/129140770535
