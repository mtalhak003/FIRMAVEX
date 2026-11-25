# Batch 43 — Bounded artifact/member integrity

**Review date:** November 26, 2026, Asia/Karachi.
**Starting checkpoint:**
[`258ae57d7ecbd4f66c63ea1363bb3d80ed3cea70`](https://github.com/mtalhak003/FIRMAVEX/commit/258ae57d7ecbd4f66c63ea1363bb3d80ed3cea70).
**Tracking:** [Issue #9](https://github.com/mtalhak003/FIRMAVEX/issues/9).
Windows runtime qualification and Linux hostile-workload isolation remain
**NOT ESTABLISHED**. Archive integrity does not authenticate a vendor binary.

## Starting position and available evidence

The approved detached worktree and remote development branch matched the starting
checkpoint. Existing work was preserved. The original checkout and protected
evidence were excluded from inspection. No supplied prototype package, original
artifact ZIP or complete Windows/Linux member manifest was found in the available
attachment intake. No absent file was reconstructed or described as reviewed.

The public issue and existing repository tools were reviewed instead. The
[November 25 prototype comment](https://github.com/mtalhak003/FIRMAVEX/issues/9#issuecomment-7166900941)
reports ten passing standalone synthetic tests, twelve Windows member digests and
fourteen Linux member digests. These are **attributed historical observations**,
not repository tests or independently repeated original-artifact checks here.
The comment provides no downloadable prototype link. Its reported source/build
consistency does not establish source authentication, vendor authenticity,
installer execution or qualification.

Direct authorized original-ZIP API requests for both artifact IDs remain
**Forbidden** in this environment. No original ZIP was acquired, independently
hashed or executed. The reported identities are retained for future authorized
intake:

| Original artifact | Run / artifact ID | Issue-reported ZIP SHA-256 |
|---|---|---|
| Windows lifecycle | `45420108864` / `14933359923` | `4670b91748d2db8eaa4dc80070854784d302718ea7ce7ad2d58cc9de68cbdef2` |
| Linux aggregate | `45420108955` / `14933782277` | `59915a96921c889964073ae32b5a95096ee4c06e163fa6bd5354d308e3b052df` |

The [earlier issue comment](https://github.com/mtalhak003/FIRMAVEX/issues/9#issuecomment-7162974647)
reports these selected member hashes. They are reference observations, not a
complete manifest; actual sizes were not provided and must not be invented.

| Member | Issue-reported SHA-256 |
|---|---|
| `_temp/versioned-lifecycle/versioned-lifecycle.json` | `531dae3d72c815c2a7dd61c116c3eb9041fff2eba382d749db70d0723f3cf38b` |
| `_temp/versioned-vendor-packages.txt` | `2c952d2c5f4ccd2625de88aa6213bba78faa0b956ea3340b270dc161e79564a4` |
| `assessment.json` | `b6e3270e72b4272d7c25def37753b7f8085039edcf2dbd3ecf2fdbc30ad196ad` |
| `guest/namespace.json` | `ac0fc02502e6be8d4e66354041828102c801707f425c9018b1d670897e18c093` |

The reported Windows receipt remains rejected, with candidate revision
`408ea67a901c4053d2a7c4ac4c3053c05ba0d4a6` and no recorded installer phases.
The reported Linux records retain the loopback `RTM_NEWADDR: Operation not
permitted` failure and cleanup observations. No same-host kernel/audit decision
was supplied. A raw error alone cannot establish the responsible host policy.

## Useful integration without duplicating semantic verifiers

The new [artifact/member checker](../../tools/artifact_member_integrity.py)
fills the bounded integrity gap for explicitly supplied ZIPs and selected-member
manifests. It does not implement another candidate qualification schema.
Existing [Windows inventory consistency](../../tools/windows_runtime_inventory.py),
[candidate artifact verification](../../tools/windows_candidate_artifact.py),
[authentic package verification](../../tools/windows_candidate_packages.py) and
[static PE import auditing](../../tools/windows_candidate_closure.py) retain their
separate contracts. No semantic payload validation is added by this checker.

The manifest must be independently reviewed and pinned by its own mandatory
SHA-256. Its exact schema is:

```text
schema_version: exact integer 1
kind: "firmavex_artifact_member_manifest"
source:
  repository: "mtalhak003/FIRMAVEX"
  revision: lowercase 40-character Git SHA
  run_id: positive integer
  artifact_id: positive integer
archive:
  sha256: lowercase 64-character SHA-256
  size_bytes: actual positive byte count
members: nonempty list of {name, sha256, size_bytes}
complete_inventory: exact boolean
```

Unknown schema keys, duplicate JSON keys, type aliases such as boolean byte
counts, invalid identities and duplicate selected names are rejected. Source,
revision, run and artifact fields remain **supplied declarations**, not proof
of GitHub origin or source authenticity. A self-authored manifest proves no
independent origin merely because its digest is known.

The checker reads stable, explicitly selected regular files through existing
bounded file/path utilities. It validates every ZIP name and streams every member
through CRC and SHA-256 checks without extraction or execution. Absolute,
traversal, backslash, alternate-stream, reserved/aliased names, case collisions,
symlinks, reparse/special entries and conflicting file/directory layouts are
refused. ZIP64, multipart, self-extracting/appended layouts, encryption and
unsupported compression fail closed.
Only printable ASCII member names are supported. Local headers, compressed
extents and optional data descriptors must agree with the central directory;
padding and overlapping local records are unsupported.

Bounds are 1 MiB manifest, 128 MiB ZIP, 1,024 ZIP entries, 1 MiB central directory,
128 MiB per member, 512 MiB total uncompressed bytes, 200:1 compression ratio
and 64 selected manifest members. These are supported-tool limits, not evidence
that an unavailable original fits them. Final consistency reads reject observable
input changes. Cancellation and control-flow exceptions propagate.

Every selected member must match both size and digest. When
`complete_inventory=true`, the selected names must equal all regular-file names;
otherwise only the selected subset's expected identities are asserted. All
members still receive structural, bound and CRC checks. Directory entries are
validated but excluded from the reported regular-file count.

Successful output is `integrity_matched`, with `capture=stable_observed`,
`atomic_snapshot=false`, `concurrent_path_isolation=false` and
`production_qualified=false`. JSON omits input paths, member names and raw error
text; selected entries use manifest-order indices. Failed assessments expose
bounded fixed diagnostic codes. Exit 0 means this limited integrity check
matched; exit 2 means blocked. Neither value approves execution or qualification.

## Controlled usage

Use original files outside the repository and protected evidence paths. First
review and preserve an original manifest through an independent authorized
channel. Do not invent missing members, sizes, receipts or signatures.

```sh
python -B -m tools.artifact_member_integrity \
  --archive /authorized/private/original.zip \
  --manifest /authorized/private/reviewed-manifest.json \
  --manifest-sha256 INDEPENDENTLY_REVIEWED_MANIFEST_SHA256
```

This illustrative command is not an original-artifact validation result. The
operator must supply actual reviewed files and digest. Output may be archived
separately without replacing originals. Retain failures; a matched manifest is
not a substitute for the existing receipt, package, native or legal checks.

## Independently inspected publisher sources

Official repository documents and source recipes were fetched read-only on the
review date. Each pinned copy matched its observed current copy byte-for-byte.
Only text was fetched; no vendor executable, package archive or installer was
downloaded or executed.

| Pinned publisher source | Observed text SHA-256 | Limited observation |
|---|---|---|
| [MSYS2 updating](https://raw.githubusercontent.com/msys2/msys2.github.io/e4894993a64f0628b5247b3775b7e2db807818a8/web/docs/updating.md) | `7dc5d08a36c4723d961450ec234c75da1b110475a96f65e02523202d841f8816` | Rolling distribution supports full-system upgrades. |
| [MSYS2 package management](https://raw.githubusercontent.com/msys2/msys2.github.io/e4894993a64f0628b5247b3775b7e2db807818a8/web/docs/package-management.md) | `ad1b251a0aa435ed2cb71c6de16e3c8f2460f4172694c7d1ca5e04e6f7732e62` | Old package archives require recursively compatible dependency versions. |
| [QEMU recipe](https://raw.githubusercontent.com/msys2/MINGW-packages/b12a1be5a0d91c01b3da8168205ca95c6c865b76/mingw-w64-qemu/PKGBUILD) | `dd1af67adaca6ffce6c4b90879b2d8fc9a7cc188b879d65a07a83e78af179f6f` | Declares QEMU `11.1.3-2` and composite GPL/LGPL/BSD/MIT licensing. |
| [GDB recipe](https://raw.githubusercontent.com/msys2/MINGW-packages/b12a1be5a0d91c01b3da8168205ca95c6c865b76/mingw-w64-gdb/PKGBUILD) | `349e1de1c34531dc0d8f2744951db70925ee529934009f6c273dea28f29f88e8` | Declares GDB `18.1-4`, Python dependency and GPL-3.0-or-later. |

Agreement with reported package declarations does not bind observed executable
bytes to these recipes. Source-signature declarations in a recipe do not verify
MSYS2 binary-package signatures. No independently authenticated archive/signature
set, trusted signing inputs, installed-file ownership map, complete DLL closure
or license/source-delivery bundle was obtained. Existing historical candidate
pins remain unchanged; current rolling generations are not approved.

## Validation and publication record

Local validation used Linux and the existing Python **3.12.14** environment,
`/workspace/firmavex-batch7-venv/bin/python`. The `python` commands below denote
that interpreter. No dependencies were downloaded for validation.

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_artifact_member_integrity.py
```

Final new-module result: **173 passed**, zero failures, errors or skips,
**0.42 seconds**. Earlier results were 119 passed and then 158 passed while
coverage was being expanded. These overlapping counts are not additive.

**Adversarial draft defect and repair:** a separate crafted ZIP demonstrated
that `ZipExtFile` can truncate DEFLATE output to a forged smaller advertised
size while accepting a matching prefix CRC. It returned the digest of `a` for
compressed `abcde` after both headers were changed. The new tool now decodes
raw DEFLATE with bounded output chunks and checks actual EOF, full compressed
consumption, actual size and CRC. It rejects the reproduced case, trailing,
concatenated and truncated streams. Nine new tests cover these cases, chunking
and nonseekable-writer data descriptors. The historical 158-pass count predates
this demonstrated draft defect; neither result establishes original evidence.
The existing candidate verifier was not changed or requalified by this repair.
Independent review also found a LOW format-policy discrepancy: ZIP64 extra
fields could be interpreted despite a forged version below 45. Central and
local extra fields now reject ZIP64, duplicate fields and malformed lengths.
Five tests include that exact central-size-override case. The unsafe-name guard
now instruments the actual decoder after its replacement. The independent final
review selection reported **23 passed, 149 deselected**, **0.29 seconds**, with
no blocking findings. The earlier 167-pass new-module run preceded these five
tests and is retained as an intermediate observation.

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_artifact_member_integrity.py \
  tests/product/test_windows_runtime_inventory.py \
  tests/product/test_windows_candidate_artifact.py \
  tests/product/test_windows_candidate_evidence.py \
  tests/product/test_windows_preflight_archive.py \
  tests/product/test_file_state.py
```

Final focused result: **550 passed, 1 skipped**, zero failures, errors or
deselections, **7.63 seconds**. The skip requires actual NTFS change-time semantics.
The initial existing-verifier selection, before adding the new module, reported
**377 passed, 1 skipped**, **7.08 seconds**. An intermediate expanded selection
reported **512 passed, 1 skipped**, **7.12 seconds** before the final additions.
The first post-DEFLATE focused run reported **544 passed, 1 skipped**, **8.19
seconds**, before the five extra-field regressions.

```sh
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_artifact_member_integrity.py \
  tests/product/test_windows_runtime_inventory.py \
  tests/product/test_windows_runtime_candidate.py \
  tests/product/test_windows_runtime_preflight.py \
  tests/product/test_windows_candidate_artifact.py \
  tests/product/test_windows_candidate_evidence.py \
  tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_closure.py \
  tests/product/test_windows_preflight_archive.py \
  tests/product/test_windows_preflight_validation.py \
  tests/product/test_aggregate_isolation_probe.py \
  tests/product/test_namespace_diagnostics.py \
  tests/product/test_isolation_feasibility.py \
  tests/product/test_versioned_install_ci.py \
  tests/product/test_platform_support.py \
  tests/product/test_file_state.py \
  tests/product/test_build_inputs.py \
  tests/product/test_ci_diagnostics.py \
  tests/backends/test_records_security.py \
  tests/desktop/test_windows_desktop_paths.py
```

Final wider result: **1,367 passed, 11 skipped**, zero failures, errors or
deselections, **29.86 seconds**. The earlier post-DEFLATE wider run reported
**1,361 passed, 11 skipped**, **30.52 seconds**, before the extra-field regressions.
Skips: two explicit native candidate workflow
cases, six native Windows desktop sharing/attribute/locking cases, one NTFS case,
one absent ARM-tool case and one blocked namespace prerequisite. The latter
reported `bwrap: setting up uid map: Read-only file system`; it is not evidence
of this host sharing the CI loopback failure's cause. These are relevant
regressions, not a complete repository suite or native Windows qualification.

The test fixtures exercise success, bounds at and beyond limits, malformed
manifests/ZIPs, local/central inconsistencies, unsafe selected and unselected
names, special entries, full CRC, no extraction/execution/network/writes,
privacy, CLI statuses, cancellation and control-flow identity, input changes,
same-size rewrites with restored timestamps and same-byte file replacement.
`tools.check_build_inputs` passed. PyYAML **6.0.3** parsed the workflow and verified
the unchanged seven-job matrix plus one new test-module argument. `actionlint`
and PowerShell were unavailable; no such validation is claimed.
Two real module-CLI invocations against invented temporary ZIP/manifest fixtures
returned the expected **0** (`integrity_matched`) and **2** (`blocked`) statuses.
Input bytes remained unchanged; no original evidence or guest executed.
A supplementary standard-library source probe failed twice because it assumed
separator normalization appeared inline in `ZipInfo.__init__`. Direct inspection
located `_sanitize_filename` instead. The dedicated behavioral regression passes;
these were failed source-shape assumptions, not additional project-test failures.

**Original validation remains pending:** supplied prototype/manifests and original ZIP
bytes remain unavailable; issue-reported checks were not independently repeated.

## Publication and observed CI

Implementation commit
[`3c4ba13c784fb5f64e674d8ec9023fa57d199173`](https://github.com/mtalhak003/FIRMAVEX/commit/3c4ba13c784fb5f64e674d8ec9023fa57d199173)
was normally fast-forward pushed to the development branch and its remote SHA
verified. The configured author and committer are
`mtalhak003 <mtalhak003@gmail.com>`; no identity/date override was used.

The starting checkpoint's [product run 45566579906](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45566579906)
now displays success for all seven jobs. This is independently inspected historical
CI status for the starting revision, not passing evidence for the new checker.
The first new [product run 45691432972](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45691432972)
failed native Windows
[Python 3.11 job 139477611946](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45691432972/job/139477611946)
and [Python 3.12 job 139477611752](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45691432972/job/139477611752).
Both annotations identify the same crafted-backslash test. Windows `ZipInfo`
converted its `os.sep` backslash to `/` during fixture creation, so the ZIP
contained an ordinary safe name and the pre-decompression refusal guard fired.
This was a demonstrated fixture problem, not permission to accept unsafe names.

Test-only repair
[`7007cb9a2de2e13b29973630b3bdbb411e9d600d`](https://github.com/mtalhak003/FIRMAVEX/commit/7007cb9a2de2e13b29973630b3bdbb411e9d600d)
preserves exact crafted raw names and compression settings. An additional portable
test uses Windows constructor rules and checks both raw header names before
requiring rejection. No decoder, assertion, admission or production code was
weakened. Before this repair the new/focused/wider selections reported
**172 passed**, **549 passed/1 skipped** and **1,366 passed/11 skipped**,
respectively, on Linux; those counts did not establish native Windows correctness.
The final results above include the repair. Both failed Windows attempts are
preserved. New automatic
[product run 45692212087](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087)
tests the repaired source; results must be attributed to its exact revision.
At repaired source `7007cb9a`, all six product matrix jobs subsequently passed:

| Hosted job | Observed outcome |
|---|---|
| [Windows Python 3.11 / 139480319549](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087/job/139480319549) | **PASS**, 4m07s |
| [Windows Python 3.12 / 139480318460](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087/job/139480318460) | **PASS**, 4m26s |
| [Ubuntu Python 3.11 / 139480319016](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087/job/139480319016) | **PASS**, 1m42s |
| [Ubuntu Python 3.12 / 139480319337](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087/job/139480319337) | **PASS**, 2m20s |
| [macOS preview Python 3.11 / 139480319392](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087/job/139480319392) | **PASS**, 1m22s |
| [macOS preview Python 3.12 / 139480319603](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45692212087/job/139480319603) | **PASS**, 2m02s |

Both Windows jobs passed the new selection, debugger parsing, package build,
installed packaging, synthetic desktop checks, smoke test and retention. These
are public hosted-CI observations, not independently inspected original JUnit
totals or Windows firmware/runtime/consumer qualification. macOS remains preview.
The separate repaired-source Linux real-product/research job was still running
at this observation. The corresponding first-source
[Linux job 139477611515](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45691432972/job/139477611515)
passed all steps, including actual product tools/tests, research regressions and
installed CLI demonstration. It is scoped to first source `3c4ba13c`.

Fresh [aggregate run 45691433080, job 139477611997](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45691433080/job/139477611997)
failed in **27 seconds**. Public annotations retain bubblewrap's loopback
`RTM_NEWADDR: Operation not permitted`, nested `status=blocked`, return code 1,
`namespace_descendants_absent=true`, `untrusted_execution_authorized=false` and
`sandbox_qualification=not_established`. This is the recorded failed stage and
cleanup observation, not independent host-policy causality or qualification.

At the first new source, [Windows lifecycle job 139477612327](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45691432964/job/139477612327)
failed its unchanged runtime gate before installer transitions. Its public notice
reports QEMU **11.1.3**, SHA-256
`15368eeab939a3ffb29ffdf73572faa0ab180d76997d00d68ea077c938552c4c`
(version/hash mismatch), and GDB **18.1**, SHA-256
`4f9000b35fcd3f41e1fa6b6e530bb05e16e0c817b1b6ff19ad2a3647fbfb2efe`
(version matches/hash mismatch). These fresh CI observations agree with previous
reports but are not original-package authentication. The Linux lifecycle job
displayed success; it does not establish Windows acceptance.

The authorized Issue #9 update was attempted with `gh issue comment --body-file`
and then the direct REST comment endpoint. Both returned **Forbidden**. No update
was posted or issue closed. A factual draft is retained outside the repository;
posting remains blocked by this session's GitHub API authorization.

Python syntax and all intended files' whitespace passed. Documentation validation
checked **175 local links, 23 anchors and 115 local commit references**.
`git diff --check` passed. These counts are scoped to the index, progress history
and this report; they do not claim all external web links or original artifacts
were independently validated.

## Remaining risks and next actions

- **MEDIUM, inherited:** controlled stable paths are required. Observable
  consistency checks do not provide an atomic snapshot, locking or protection
  against hostile concurrent parent replacement. No containment claim is made.
- **Qualification blocked:** acquire original artifact bytes/manifests through
  authorized access, preserve transfer identities and run the new limited check.
  Then apply the existing semantic verifiers to appropriate actual inputs.
- **Publisher/closure blocked:** follow the separately scoped
  [runtime provenance gates](batch28-runtime-provenance.md); actual signed
  archives, independent trust, ownership, loader evidence and licensing inputs
  remain necessary. No safe executable-only rolling downgrade is proposed.
- **Linux isolation blocked:** retain fail-closed namespace behavior. Same-host
  boot/time/process-correlated audit evidence requires a separately authorized
  bounded collection; sibling-host records cannot prove causality.
- **Qualification pending:** hosted Windows regression coverage does not
  establish native runtime support, consumer acceptance, signing trust or
  production readiness. Controlled developer preflight evidence remains separate.
  Neither the checker nor local validation ran firmware or an installer;
  hosted CI execution is separately attributed above.

No production admission, runtime hashes, signing rules, main, frozen research or
protected originals are changed by this integrity tool.
