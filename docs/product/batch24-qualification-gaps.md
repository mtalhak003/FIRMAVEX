# Batch 24: Windows runtime qualification gaps

Review date: 2026-11-09 (Asia/Karachi). Reviewed source:
`237e9f64352d1aac7105f7461db5d76dacf57612`.

**Status: native source-stage candidate checks passed; production qualification
has not been approved.** QEMU 11.1.3 remains rejected by the existing profile.
This report updates the historical "not natively executed" statement in the
Batch 23D preparation document only for the source-stage evidence below.

## Evidence and access limits

- [Run 42505041359](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42505041359)
  and [Windows job 128805746981][job] publicly identify the reviewed commit.
  All qualification steps 2–12 have `success` conclusions, including ARM runtime
  regressions (9), ownership/resource tests (10), and the native source probe (11).
- The run lists artifact **13626708755**, approximately **1.9 MB**, named
  `Windows-UNQUALIFIED-runtime-candidate-237e9f64352d1aac7105f7461db5d76dacf57612`.
  GitHub displays digest
  `8e1b9f67b7f8f13de6c5b5b205e4f19ffa6414cc19a74e174e3147a810b5d9ae`.
  This is displayed metadata, **not a locally verified download digest**.
- Authenticated log/artifact requests returned `Forbidden`, including an
  escalated access attempt; the public artifact download returned HTTP 404.
  Raw receipts, package listings, vendor hashes and JUnit were not inspected.
- **PASS** below means the public job succeeded through the cited enforced
  assertions at this source revision. **NOT PROVEN** identifies absent or
  unreviewed evidence. Exact native pytest pass/skip totals remain NOT PROVEN;
  local Linux test totals must not be substituted for them.

## Identity comparison

These are the exact values enforced by the passing preflight, not a transcription
of independently retrieved observed records ([workflow][workflow], step 8;
[`verify_tools()` and `package_inventory()`][probe]).

| Subject | Candidate enforced value | Existing production requirement | Assessment |
|---|---|---|---|
| QEMU executable | `QEMU emulator version 11.1.3`; SHA-256 `f7e69cf3c284bad6a3b1c4159d2a88001f285c28f890dd2f8e56186682840cc7` | `QEMU emulator version 11.1.2`; SHA-256 `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` | Candidate pin check PASS; current production match FAIL, intentionally |
| GDB executable | `GNU gdb (GDB) 18.1`; SHA-256 `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` | Same version and digest | PASS |
| MSYS2 packages | `mingw-w64-ucrt-x86_64-qemu` = `11.1.3-1`; `mingw-w64-ucrt-x86_64-gdb-multiarch` = `18.1-3` | The executable gate does not pin a package/dependency closure | Candidate package pin check PASS; independent full-list review NOT PROVEN |

The Windows policy in [`platform_support.py`][policy] admits only native x64 and
the original exact executable identities. Its historical reference is run 38278936642, not evidence
for this candidate's GUI or packaged application. Broader product/release checks
are separate documented obligations, not extra predicates in `windows_profile()`.

## Requirement matrix

| Requirement | Status | Evidence and boundary |
|---|---|---|
| Manual candidate context, exact source and native Windows x64 | PASS | Steps 2/8/11; `context()` binds commit, run, workflow and host. Exact runner OS/build inventory was not retrieved. |
| Mandatory trusted publisher package signatures and consistent upgrade transaction | PASS | Step 6; resolved `PackageRequired`/`PackageTrustedOnly` checks precede one full `pacman -Syu` transaction. Individual package archives/signers were not independently inspected. |
| Full UCRT64 prefix inventory and observed stability | PASS | Steps 8/11; complete bounded prefix hashing, hardlink alias audit and pre/post comparisons. This is not an atomic snapshot, minimal DLL closure or audit of system DLL/load resolution. |
| Independently verified retained evidence and exact JUnit counts/skips | NOT PROVEN | Artifact exists, but download/content review was blocked. No claim of zero native skips. |
| ARM startup, input-ready/completion, positive `(2,1)`, negative `(2,0)`, initialized data, signature modes | PASS | Step 9 selects existing actual ARM regressions; step 11 probes the bundled image through the real executor. Emulation only; no hardware validation. |
| Source search and bounded reproduction | PASS | Step 11 requires enumerative discovery at attempt 10 with `[2,1]`, then three triggering replays. This does not qualify the supervised application reproduction path. |
| Cancellation, timeout, charged failures, abort and cleanup | PASS | Step 11 requires cancellation after injection, timeout, one charged infrastructure failure in each fault session, no later dispatch and verified process reaping. |
| Native ownership/resource regressions and host allocation denial | PASS | Steps 10/11; resource case requires a 256 MiB allocation to fail under a 128 MiB host-process limit and verifies cleanup. This is not aggregate QEMU/worker CPU/memory qualification or hostile-workload sandboxing. |
| Complete aggregate resource/security-boundary qualification | NOT PROVEN | Limited host probes cannot establish all process/resource bounds or isolation properties. |
| Production rejection before/after source probing | PASS | Steps 8/11 call the unchanged admission policy; candidate reports must retain `production_qualified=false`. |
| Membership in the existing production runtime profile | FAIL | QEMU version/hash differ deliberately. A green candidate job does not authorize admission changes. |
| Candidate product worker/CLI, GUI, history, report/export journeys | NOT PROVEN | This workflow uses the low-level executor/evaluator; no full candidate product journey is selected. |
| Frozen/installed application and distinct-version install/upgrade/rollback/uninstall with saved data | NOT PROVEN | Absent from this run; historical workflows do not establish these outcomes for the new runtime set. |
| Standard-user, offline, low-disk and accessibility acceptance | NOT PROVEN | Hosted source tests do not replace [consumer acceptance](consumer-acceptance.md). Public signing/release approval is separate from runtime adapter qualification. |
| Immutable acquisition, dependency relationships and redistribution/source-license clearance | NOT PROVEN | Rolling acquisition plus a prefix/file listing cannot recreate the exact signed package set or prove redistribution compliance. See [Batch 23C](batch23-acquisition-investigation.md). |
| Independent profile review and explicit promotion approval | NOT PROVEN | No new profile is approved or implemented by this report. |

The passing source probe requires **8 cases and 19 distinct attempt receipts**:
17 successful observations, one intentional timeout and one cancellation. This
describes its enforced contract, not an independent artifact recount or the
total executions across the entire job. Deliberate fault outcomes remain charged
infrastructure failures; they are not successful firmware completions.

## Smallest remaining action set

1. **Close the evidence-review gap.** Retrieve artifact 13626708755 through an
   authorized account; verify its displayed digest, reviewed revision/run IDs,
   `candidate-report.json`, package/signature records, `vendor-files.json` digest,
   all 19 receipts, resource record and every JUnit result/skip. Preserve the
   original archive and label omissions explicitly; do not reconstruct evidence.
2. **Validate the actual product delivery path.** Use a separately reviewed,
   candidate-isolated path for supervised/GUI, frozen and installed ARM execution,
   reproduction, cancellation, cleanup, history/export and saved-data lifecycle.
   Existing patterns are in [desktop-distribution.yml](../../.github/workflows/desktop-distribution.yml)
   and [versioned-install.yml](../../.github/workflows/versioned-install.yml).
   This requires separate authorization; do not override production admission.
3. **Freeze and review the runtime subject before promotion.** Preserve the
   compatible signed package archives, hashes, trusted signer evidence, dependency
   relationships, bootstrap/source recipes and license/source obligations.
   Independently review remaining resource/compatibility limits, then seek an
   explicit, narrowly scoped versioned-profile decision. A future runtime profile
   approval would still not establish public-beta or consumer acceptance.

## Validation of this report

Documentation-only change. The local policy/candidate selection passed **38 tests,
103 deselected, zero failures/errors/skips**, using:

```sh
QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra tests/product/test_platform_support.py tests/product/test_windows_runtime_candidate.py -k 'production_gate or explicit_context or required_trusted or candidate_workflow or platform'
```

Content/reference/whitespace checks were performed separately. No firmware tests,
campaign, CI dispatch, runtime policy change or artifact reconstruction was made
as part of this review.

[job]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42505041359/job/128805746981
[workflow]: ../../.github/workflows/windows-runtime-candidate.yml
[probe]: ../../tools/windows_runtime_candidate.py
[policy]: ../../firmavex/product/platform_support.py
