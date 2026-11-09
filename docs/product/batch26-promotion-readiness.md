# Batch 26: evidence identity and promotion readiness

**Production qualification is not closed or approved.** Baseline:
`8c4a6fa7d8611a93eb717b3231b84a6a5ff79dfe`; review date 2026-11-09
(Asia/Karachi). Production admission, executable hashes, publisher signature
requirements and package acquisition remain unchanged. No CI was dispatched.

## Original evidence: identity must be resolved before verification

The requested artifact is **13614155038** from run **42505041359**. Its Actions
API metadata request returned `Forbidden`; a subsequent escalated metadata check
was interrupted. Public download URLs returned HTTP 404 for both this ID and
the previously listed ID. **No original ZIP was retrieved or verified.** These
responses do not prove that an artifact never existed or has expired.

A fresh HTTP 200 read of the [public run listing][run] instead exposes artifact
**13626708755**, with displayed SHA-256:
`8e1b9f67b7f8f13de6c5b5b205e4f19ffa6414cc19a74e174e3147a810b5d9ae`.
This confirms the prior Batch 24 metadata, not the archive bytes. The relationship
between the two IDs is NOT PROVEN. Do not attach that digest to 13614155038 without
authorized metadata establishing the association. No receipts or missing evidence
were reconstructed, and a failed HTTP response was not treated as a candidate ZIP.

After authorized retrieval, bind the actual ZIP to its independently obtained
digest, source SHA and run ID and run `tools.windows_candidate_evidence` as
documented in [Batch 25](batch25-runtime-qualification.md). The original
source-stage artifact does not contain the later product-path reports; do not
require those reports when auditing the original run.

## Automated checks improved

- The archive verifier now checks the original source report's complete
  production-rejection comparison, not just its profile ID.
- Known source CLI/worker, GUI and frozen rejection reports are verified whenever
  present. Source revision/run, native host, candidate labels, zero charged
  attempts, precise expected/observed identity comparisons, classification,
  executable record, event ordering, cleanup and matching passed native JUnit
  cases must agree. Contradictory records fail even in optional mode.
- New `--require-product-paths` requires all three implemented rejection paths
  and their native tests. It does not approve positive execution or installation.
  Older source-only ZIPs remain supported without that flag. Unrecognized
  installed-product records remain explicitly unreviewed and cannot satisfy the
  required scope. `production_qualified` always stays false.
- The producer rejects inconsistent diagnostic matrices, boolean exit codes and
  cleanup records inconsistent with the CLI's expected rejection exit status.
- The GUI native check revalidates the vendor context after rejection before
  recording a pass. Source and GUI checks now use separate owned CI selections,
  so repeated full-prefix scans do not accumulate under one selection watchdog.
  Existing per-test, selection and job limits are unchanged. New native results
  are still required; this change is not a measured Windows timing improvement.

For a **future** artifact containing the new native checks:

```sh
python -m tools.windows_candidate_evidence /path/to/actual-candidate.zip \
  --sha256 ACTUAL_GITHUB_ARTIFACT_SHA256 --revision ACTUAL_REVIEWED_SOURCE_SHA \
  --run-id ACTUAL_RUN_ID --require-product-paths
```

Placeholders require real independent inputs. The check establishes record
consistency and rejection evidence only, not native authenticity or release
approval. A matching JUnit result does not replace retained runtime evidence.

## Vendor archive, trust and license investigation

Official recipes were retrieved with HTTP 200 from MINGW-packages revision
`84cb81731a0cdd43e79f438370ee570617faa1fc`:

| Source | Observed declaration | Retrieved recipe SHA-256 |
|---|---|---|
| [QEMU recipe][qemu] | Base version 11.1.3, release 1; GPL-2.0-or-later AND LGPL-2.1-or-later AND BSD-2-Clause AND BSD-3-Clause AND MIT | `905771a8d3f3f612d6772cec74d4daa5ba574bdd9378453f513dff7e1019bf8f` |
| [GDB recipe][gdb] | Version 18.1, release 3; GPL-3.0-or-later | `0ebcd12224bce6604a91e8c6e7d855e72de4e74c721b2d0cd668bc2b64754b0c` |

Recipes are source/license-declaration evidence, not authentication of binary
archives, signing keys, corresponding-source completeness or redistribution rights.
Probes of the predicted QEMU 11.1.3-1 archive and `.sig` URLs and GDB-multiarch
18.1-3 archive URL under `repo.msys2.org/mingw/ucrt64/` failed at the CONNECT
tunnel with HTTP 403, including escalated execution. Upstream package availability
was not established; the URLs were probes, not verified acquisition inputs.

No complete authentic package set or independently trusted publisher keyring,
fingerprint allowlist and verification-tool pins was supplied. GnuPG is available;
bsdtar and vercmp are not available locally. The existing verifier therefore was
not run against real vendor packages. Its ephemeral synthetic-key regression is
not vendor trust. Do not import payload-provided keys, create replacement signer
identities, disable trust checks or mix an old package with rolling dependencies.
Follow Batch 25's fail-closed offline procedure once genuine inputs exist.

## Promotion-readiness matrix

| Requirement | Status | Evidence or remaining condition |
|---|---|---|
| Historical native source-stage assertions | PASS, limited | Prior public run 42505041359/job 128805746981, as scoped in Batch 24; no new native measurements here. |
| Requested artifact identity and actual ZIP contents | NOT PROVEN | Requested and publicly listed IDs differ; API access/downloads blocked. No receipt/JUnit recount. |
| Source and optional product evidence validation | PASS, local | Automated positive/negative unit fixtures; fixtures are explicitly synthetic. |
| Real publisher recipes and license declarations | PASS, limited | Retrieved pinned sources and hashes above; not binary/signature/legal clearance. |
| Authentic signed package archives and compatible closure | NOT PROVEN | No verified archive set, trusted signing inputs or actual signed-metadata closure. |
| Archive-to-installed executable binding/system DLL closure | NOT PROVEN | Existing package verifier does not establish these; requires an approved native installation/identity audit. |
| Source CLI/worker and GUI rejection checks | NOT PROVEN, native | Stronger checks prepared; no Windows run of these changes. |
| Frozen console rejection | NOT PROVEN | Tests prepared. No new frozen executable evidence or independently proven build origin. |
| Frozen windowed GUI and installed-product lifecycle | NOT PROVEN | No frozen GUI journey or actual installer/upgrade/rollback/uninstall coverage was added. An `installed` label remains unverified. |
| Positive candidate execution/reproduction/export | NOT PROVEN | Intentionally blocked by unchanged production admission; negative-path passes cannot substitute for positive qualification. |
| Standard-user/offline/low-disk/accessibility and signed public release | NOT PROVEN | Consumer-machine and distribution approval evidence remains outstanding. |
| Candidate membership in current production profile | FAIL, expected | QEMU 11.1.3 differs from the pinned QEMU 11.1.2 identity; rejection must remain enforced. |

## Exact next actions

1. Use an authorized account to resolve the artifact IDs and obtain the original
   bytes plus metadata; verify the source-only ZIP without requiring later reports.
2. Obtain approval for a native candidate workflow run at the reviewed new commit;
   inspect all native results and validate its ZIP with `--require-product-paths`.
   This still qualifies rejection paths only.
3. Supply the immutable compatible signed package set, independently trusted
   signing/tool inputs, actual notices and corresponding-source evidence; verify
   and audit native archive-to-executable binding. Separately review the positive
   product-path lab design, installed/frozen GUI coverage and consumer acceptance
   before considering an explicitly authorized versioned-profile promotion.

## Local validation

The focused and broader commands in [Batch 25's validation section](batch25-runtime-qualification.md#local-validation)
were rerun against this implementation: **303 passed, 5 native Windows skips**
for the focused selection, and **1,081 passed, 21 skipped, 27 deselected** for the
broader selection. There were no failures/errors. Broader skips concern native
platform APIs or absent ARM/RV32/HDL tools, and its `not actual_` expression leaves
actual-prefixed cases unexecuted. The real GnuPG synthetic-key fixture passed in
the focused suite; it does not establish publisher trust.

Actionlint 1.7.7 (`actionlint -shellcheck= .github/workflows/windows-runtime-candidate.yml`),
Python syntax, declared recipe hashes, report references/whitespace, build-input
checks and `git diff --check` passed. ShellCheck/PowerShell and a native Windows
execution environment were unavailable. These are selected regression results,
not a complete repository-suite result or new native qualification evidence.

[run]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42505041359
[qemu]: https://github.com/msys2/MINGW-packages/blob/84cb81731a0cdd43e79f438370ee570617faa1fc/mingw-w64-qemu/PKGBUILD
[gdb]: https://github.com/msys2/MINGW-packages/blob/84cb81731a0cdd43e79f438370ee570617faa1fc/mingw-w64-gdb/PKGBUILD
