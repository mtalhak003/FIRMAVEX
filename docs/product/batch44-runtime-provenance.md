# Batch 44 — Runtime provenance and verification consistency

**Review date:** November 28, 2026, Asia/Karachi.
**Starting checkpoint:**
[`611dcf71e1858f3efc96b945c388510e3de90a35`](https://github.com/mtalhak003/FIRMAVEX/commit/611dcf71e1858f3efc96b945c388510e3de90a35).
**Tracking:** [Issue #10](https://github.com/mtalhak003/FIRMAVEX/issues/10).
**Qualification:** Windows runtime and hostile-workload isolation remain
**NOT ESTABLISHED**. A useful verifier repair is not runtime approval.

## Scope and evidence classes

The approved detached worktree and remote development branch matched the starting
checkpoint with no changes in the inspected scope. Work preservation, configured
identity and normal Git dates were retained. The original checkout and protected
evidence were excluded. No runtime pin, production admission, signing, frozen
research or isolation contract was changed.

The [Batch 43 report](batch43-artifact-integrity.md), current acquisition and
qualification policy, existing package/PE verifiers, public Issue #10 and exact
hosted-job observations were reviewed. Evidence is classified as follows:

- **Inspected source/data:** repository code or independently retrieved official
  text/public-keyring bytes, with the limited provenance described below.
- **Hosted CI observation:** status or retained public annotation at an exact run,
  revision and job; not independent authentication of its original archive.
- **Attributed report:** original-artifact checks described by another environment
  or the user, without their original bytes acquired here.
- **Synthetic regression:** invented local inputs and controlled tool boundaries;
  not real vendor trust or native runtime qualification.
- **NOT PROVEN:** a required input or causal link remains unavailable.

## Frozen Windows identity and exact blocker

The existing [Windows profile](../../firmavex/product/platform_support.py) remains
`msys2-ucrt64-qemu11.1.2-gdb18.1-v1`, profile version 1, Windows x64.

| Tool | Required version line | Required executable SHA-256 |
|---|---|---|
| QEMU | `QEMU emulator version 11.1.2` | `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` |
| GDB | `GNU gdb (GDB) 18.1` | `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` |

Neither required executable was recovered or hashed from authenticated package
payloads in this batch. Version strings, source tags and package declarations
must not replace these full-file identities. Capability evidence must separately
cover QEMU `mps2-an385`, GDB ARM support, embedded Python and `hashlib`, plus
matching Python/native modules, plugins and other execution dependencies.

At the starting revision, [Windows job 139484180565](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45693328525/job/139484180565)
records the intended rejection before installer lifecycle transitions:

| Tool | Observed version | Observed executable SHA-256 | Version / digest match |
|---|---|---|---|
| QEMU | `11.1.3` | `15368eeab939a3ffb29ffdf73572faa0ab180d76997d00d68ea077c938552c4c` | false / false |
| GDB | `18.1` | `4f9000b35fcd3f41e1fa6b6e530bb05e16e0c817b1b6ff19ad2a3647fbfb2efe` | true / false |

These are hosted observations, not downloaded-binary authentication or successful
Windows installation. The earlier `11.1.2-1` archive filename was a historical
probe, not an established original package identity. Historical GDB package
`18.1-3` was reported to match the required executable hash; this does not recover
its complete compatible signed package generation or establish ownership.

## Retrieval attempts and official sources

The official UCRT64 package index, QEMU/GDB package pages and MSYS2 website
requests were rejected with HTTP 403 by this environment's CONNECT proxy.
The normal requests and the approved escalated retry remained blocked. This is
an access limitation, not evidence that the publisher removed an old package.
No package archive, detached binary-package signature, original vendor installer
or required QEMU/GDB executable was acquired or executed.

GitHub API issue/artifact requests returned `Forbidden`; public issue HTML and
official Git source endpoints remained accessible. Original artifact/manifest
checks previously reported by other environments were not independently repeated
or reconstructed. No missing original was replaced with synthetic evidence.
The guessed raw URL
`https://raw.githubusercontent.com/msys2/msys2.github.io/HEAD/web/docs/verifying-signatures.md`
returned HTTP 404 and was not used as an authoritative trust source; the
successfully retrieved sources are listed below.

Read-only official GitHub retrieval established these pinned source observations:

| Source | Pinned revision | Content SHA-256 / scope |
|---|---|---|
| [MSYS2 package management](https://raw.githubusercontent.com/msys2/msys2.github.io/e4894993a64f0628b5247b3775b7e2db807818a8/web/docs/package-management.md) | `e4894993a64f0628b5247b3775b7e2db807818a8` | `ad1b251a0aa435ed2cb71c6de16e3c8f2460f4172694c7d1ca5e04e6f7732e62` |
| [MSYS2 updating](https://raw.githubusercontent.com/msys2/msys2.github.io/e4894993a64f0628b5247b3775b7e2db807818a8/web/docs/updating.md) | same | `7dc5d08a36c4723d961450ec234c75da1b110475a96f65e02523202d841f8816` |
| [QEMU recipe](https://raw.githubusercontent.com/msys2/MINGW-packages/5ca6b4995560fcc6b4fe0f04dada7bd6760835a1/mingw-w64-qemu/PKGBUILD) | `5ca6b4995560fcc6b4fe0f04dada7bd6760835a1` | `dd1af67adaca6ffce6c4b90879b2d8fc9a7cc188b879d65a07a83e78af179f6f` |
| [GDB recipe](https://raw.githubusercontent.com/msys2/MINGW-packages/5ca6b4995560fcc6b4fe0f04dada7bd6760835a1/mingw-w64-gdb/PKGBUILD) | same | `349e1de1c34531dc0d8f2744951db70925ee529934009f6c273dea28f29f88e8` |

The recipes declare QEMU `11.1.3-2` and GDB `18.1-4`, unchanged in content from
the prior inspected generation. They identify composite GPL/LGPL/BSD/MIT and
GPL-3.0-or-later declarations respectively; GDB lists Python dependencies.
Source-signature `validpgpkeys` values concern upstream source archives, not
approval of MSYS2 binary-package signers. Recipe agreement cannot bind the
observed executable bytes, prove installed ownership or fulfill source delivery.

MSYS2 documents full rolling upgrades and recursively compatible dependencies
for older archives. It also explicitly says `pacman -Qo` compares file paths.
An ownership command's output is therefore supporting metadata, not a hash-bound
archive-to-installed ownership proof. No executable-only rolling downgrade is
recommended.

### Public keyring material is not activated trust

The official [MSYS2-keyring repository](https://github.com/msys2/MSYS2-keyring/tree/5d249077a0cfeec9dbf51515e5e01da413d28859)
was inspected at commit `5d249077a0cfeec9dbf51515e5e01da413d28859`.
Tag `20260814` advertises tag object
`0f6adc6d94a60b39260a00d66aea9dba3c8e8d84` and peels to that commit.
Its README describes signed release tags; this batch did **not** authenticate
that tag's signature or independently approve its signing roots.

Pinned public keyring data were saved outside the repository for inspection:

| Published file | Bytes | SHA-256 |
|---|---:|---|
| [`msys2.gpg`](https://raw.githubusercontent.com/msys2/MSYS2-keyring/5d249077a0cfeec9dbf51515e5e01da413d28859/msys2.gpg) | 54,878 | `1257d4ccc536c53333445a618039af4c3ea3f56b96601de9af89151ea529c19a` |
| [`msys2-trusted`](https://raw.githubusercontent.com/msys2/MSYS2-keyring/5d249077a0cfeec9dbf51515e5e01da413d28859/msys2-trusted) | 220 | `a8d39040a7b6cc14bf4394b5d9c838443925c32b00a7d34e8729c972392dca04` |
| [`msys2-revoked`](https://raw.githubusercontent.com/msys2/MSYS2-keyring/5d249077a0cfeec9dbf51515e5e01da413d28859/msys2-revoked) | 164 | `62b67ba0217745c7df189092a70d6b7a5781577f6428a5391dccd897edb5756a` |

These bytes were not imported, activated or designated trusted. A published
keyring plus its newly measured hash is not an independently approved GPG home,
trust database, signer allowlist or verification-tool identity. Synthetic signing
fixtures likewise cannot substitute for real vendor authentication.

## Evidence-supported verifier repair

The existing [candidate package verifier](../../tools/windows_candidate_packages.py)
already checks independently pinned archives/signatures, approved GPG/keyring
inputs, signed `.PKGINFO` and mandatory dependency constraints. Its specific
historical candidate roots remain unchanged. A new parallel signature checker or
silently generalized runtime-profile path would duplicate or weaken that scope.

Five newly added synthetic regressions first failed against the baseline,
demonstrating that whole-verification capture was incomplete. Previously checked
inputs could change while later packages were processed without a final
complete-set consistency check. The repair tracks the selected manifest,
verification tools, present and absent fixed keyring files, package archives and
detached signatures, and checks their metadata and content identities before
returning a successful lock record. Previously absent fixed keyring inputs cannot
silently appear. The existing file helpers and lexical exclusions are reused.

An optional `cancel_event` is propagated through polling, bounded hashing and
the existing supervised `Processes` owner. The existing overall deadline covers
capture and final rechecks, not merely child commands. `KeyboardInterrupt`,
`SystemExit` and other control-flow exceptions retain their semantics during
verification, process cleanup and temporary-directory cleanup. Ordinary cleanup
failure remains failure; a cleanup interruption is not converted to a lock.
Boundary/hash cancellation raises `KeyboardInterrupt`; in-flight process
supervision may raise its existing `Cancelled` exception. Both abort without a
lock. Polling does not interrupt a blocked kernel I/O operation or establish a
hard wall-clock isolation guarantee. Child timeouts and resource limits remain
unchanged.

This tool is read-only with respect to its supplied originals, but it is **not**
a zero-execution or zero-temporary-write API. It invokes independently pinned
GPG, bsdtar and vercmp under existing supervision and uses a private temporary
public-keyring copy. No runtime executable or firmware is launched by it.
No new acquisition, trust decision, package ownership proof, dynamic DLL
qualification or license clearance is introduced. Successful output remains
candidate-only with `production_qualified=false` and `atomic_snapshot=false`;
the existing result schema and pins are preserved.

The inherited MEDIUM concurrent-parent-replacement limitation remains. Detecting
observable changes does not lock out hostile writers, provide an atomic snapshot
or prove concurrent access containment. Stable developer-controlled inputs are
still required.

## Separate Linux namespace investigation

The exact starting-revision [aggregate job 139484179363](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45693328532/job/139484179363)
records passed CPU, process and OOM checks, failed namespace boundaries and nested
`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`. The recorded child
PID 2830 was reaped with code 1; the last unit reported cleanup, inactive state
and no remaining control group. These are hosted observations, not an audit of
the original kernel decision.

Official [bubblewrap network source](https://raw.githubusercontent.com/containers/bubblewrap/10041dc38b56305317862a0f69d61f8f2113f774/network.c),
SHA-256 `1cfe04fcc38d33d5197feb96fc503d3fd51d234fb9392699a00bf4780ed6e9f0`,
places that diagnostic at the loopback `127.0.0.1/8` `RTM_NEWADDR` stage before
`RTM_NEWLINK`. The inspected source was not bound to the actual CI executable.
Its reply-handling path does not assign `errno` from `NLMSG_ERROR`; a printed
error string therefore cannot independently prove an exact kernel/LSM cause.

The aggregate workflow retains its assessment. The existing namespace diagnostic
runs on a separate release-evidence VM, reads a ten-minute journal window and
retains up to thirty filtered rows with a bounded public tail. Those observations
lack the same-host boot/time/PID/unit/cgroup binding needed for causal attribution
to the aggregate failure. Sibling-host AppArmor denials must not be substituted.
No additional probe, privileged access, namespace/sysctl/policy change or weakened
isolation check was justified or performed.

## Readiness matrix and required original inputs

| Requirement | Status | Evidence or blocker |
|---|---|---|
| Frozen runtime policy preserved | **PASS**, source review | Exact existing versions, hashes, schemas and admission remain unchanged. |
| Baseline Windows runtime identity gate | **FAIL**, hosted observation | QEMU version/hash and GDB hash mismatch before lifecycle transitions. |
| Original admitted executable bytes | **NOT PROVEN** | No matching authenticated QEMU/GDB payload acquired. |
| Vendor signature and trusted package generation | **NOT PROVEN** | No original archive/signature set, independently approved trust and compatible lock available. |
| Package-to-executable byte ownership | **NOT PROVEN** | Path-only installed inventory is insufficient; actual authenticated member bytes are missing. |
| Mandatory and dynamic DLL closure | **NOT PROVEN** | Existing verifiers have distinct finite scopes; full native loader evidence is absent. |
| License/source-delivery closure | **NOT PROVEN** | Recipe declarations do not supply every actual distributed notice/source obligation. |
| Linux namespace boundaries | **FAIL**, hosted observation | Loopback setup failed; fail-closed behavior retained. |
| Same-host kernel/LSM causality | **NOT PROVEN** | No correlated original same-run audit decision. |
| Whole-set verifier consistency repair | **PASS**, portable regressions | Five baseline failures now rejected; final focused and wider checks passed. This is not vendor/native qualification. |

Next admissible work requires separately pinned original archives/signatures and
reviewed acquisition provenance; independently approved keyring/ownertrust and
signer policy; exact pinned verification tools; complete compatible package
constraints; safe archive-member-to-installed-file hashes, transformations and
collision records; static plus native loader/module observations across the
bounded target flows; and actual notice/source-delivery records. Reject missing
stages rather than fill them with guesses. Route A recovery must match the
frozen executable identities; a different candidate requires separate approval.

Linux audit collection separately needs explicit authorization and bounded
same-host boot/time/process/unit/cgroup correlation. The current batch grants no
extra privileges and does not change runner or host policy.

## Validation and publication record

**Baseline existing selection:** 162 passed, zero skips/failures, before changes.
**Intentional RED regressions:** five failed against the baseline to demonstrate
missing complete-set capture; this is not original vendor evidence.
**First new implementation selection:** 84 passed, 12 failed. The stale synthetic
temporary-directory double lacked `.name` and `.cleanup()` used by the actual
protocol. It was repaired to model that protocol rather than removing cleanup
checks. A subsequent intermediate run reported 96 passed. These are historical
development attempts, not final validation or native Windows execution.

The baseline command was the focused command below without the artifact-member
and file-state modules. The deliberate RED command added
`-k later_package_cannot_mask` to the package-module command: **5 failed,
41 deselected**, **0.14 seconds**. The early expanded failing run took **0.89
seconds**, and the 96-pass intermediate run took **0.59 seconds**. A documentation
filename lookup also initially used a nonexistent acquisition-guide name; review
continued with the actual `batch23-acquisition-investigation.md` history.

Local validation used Linux x86-64 and the existing Python **3.12.14** environment,
`/workspace/firmavex-batch7-venv/bin/python`. In the commands below, `python`
denotes that interpreter. No new test dependencies were installed.

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_windows_candidate_packages.py
```

Final package-module result: **123 passed**, zero failures/errors/skips or
deselections, **0.67 seconds**. This includes the existing real GnuPG test using
a locally generated **synthetic fixture key**, never vendor publisher evidence.
The new tests preserve the result schema, verify original-input immutability,
refuse unsafe paths before any input I/O, test late changes/removals and same-byte
replacements, exercise deadline/cancellation boundaries, preserve control-flow
exception identity through cleanup, and check sanitized CLI failures.

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_closure.py \
  tests/product/test_windows_runtime_inventory.py \
  tests/product/test_artifact_member_integrity.py \
  tests/product/test_namespace_diagnostics.py \
  tests/product/test_file_state.py
```

Final focused result: **420 passed, 1 skipped**, zero failures/errors/deselections,
**1.74 seconds**. The skip requires actual NTFS change-time behavior.

```sh
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_closure.py \
  tests/product/test_windows_candidate_artifact.py \
  tests/product/test_windows_candidate_evidence.py \
  tests/product/test_windows_runtime_candidate.py \
  tests/product/test_windows_runtime_inventory.py \
  tests/product/test_artifact_member_integrity.py \
  tests/product/test_windows_runtime_preflight.py \
  tests/product/test_windows_preflight_archive.py \
  tests/product/test_windows_preflight_validation.py \
  tests/product/test_aggregate_isolation_probe.py \
  tests/product/test_namespace_diagnostics.py \
  tests/product/test_isolation_feasibility.py \
  tests/product/test_versioned_install_ci.py \
  tests/product/test_platform_support.py \
  tests/product/test_file_state.py \
  tests/product/test_ci_diagnostics.py \
  tests/product/test_build_inputs.py \
  tests/backends/test_records_security.py \
  tests/desktop/test_windows_desktop_paths.py
```

Final wider result: **1,449 passed, 11 skipped**, zero failures/errors/deselections,
**29.97 seconds**. Skips: two explicit native candidate-workflow tests, six
native Windows desktop sharing/locking tests, one NTFS test, one missing ARM-tool
test and one namespace-admission prerequisite. The last reported
`bwrap: setting up uid map: Read-only file system`; it is not proof of the hosted
loopback failure's kernel cause. Counts overlap and are not a full repository
suite or native Windows package-verifier qualification.

Independent final review found no blocking issue. Its targeted synthetic
selection reported **61 passed, 62 deselected**, **0.32 seconds**. Source AST
comparison confirms unchanged metadata/signature/dependency algorithms and the
successful lock record, alongside unchanged product code, runtime/candidate pins,
packaging, workflows and research. `tools.check_build_inputs` passed. Python
syntax, whitespace and final documentation checks are part of publication;
actionlint and PowerShell are unavailable. No workflow was changed or dispatched.

## Publication and automatic CI

Implementation commit
[`d7b9420a2d66cb57e48e75c762cdd249947701c1`](https://github.com/mtalhak003/FIRMAVEX/commit/d7b9420a2d66cb57e48e75c762cdd249947701c1)
was normally fast-forward pushed to `product/desktop-batch11`; its remote SHA
matched. Author and committer use the existing configured identity
`mtalhak003 <mtalhak003@gmail.com>`, with no date or identity override.

New automatic [product run 46134066323](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323)
must be assessed at its exact revision. The existing Linux real-product job runs
all `tests/product`, including the updated package verifier tests. The unchanged
Windows platform-neutral selection does **not** select this package-verifier
module. A green Windows job therefore does not establish native package-set
verification. Installer admission and Linux isolation remain separate gates.
Final observed statuses and any API update limitations are recorded when known;
no pending workflow is represented as passing. No release is authorized.

At implementation source `d7b9420a`, all six host matrix jobs displayed success:

| Hosted job | Observed result |
|---|---|
| [Windows Python 3.11 / 140945346124](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945346124) | **PASS** |
| [Windows Python 3.12 / 140945346087](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945346087) | **PASS** |
| [Ubuntu Python 3.11 / 140945345975](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945345975) | **PASS** |
| [Ubuntu Python 3.12 / 140945346095](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945346095) | **PASS** |
| [macOS preview Python 3.11 / 140945346068](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945346068) | **PASS** |
| [macOS preview Python 3.12 / 140945346036](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945346036) | **PASS** |

Public headers and step annotations provide host-regression status, not exact
original JUnit totals or package/runtime qualification. The
[Linux real-product/research job 140945345831](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066323/job/140945345831)
subsequently completed successfully, including all-product tests, research
regressions, installed CLI demonstration and retention. The overall product
workflow displayed **SUCCESS**, all **seven jobs**, total duration **5m58s**.
The Linux installer lifecycle job displayed success. The fresh
[Windows lifecycle job 140945345880](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066333/job/140945345880)
subsequently failed admission before transitions: QEMU `11.1.3` with digest
`15368eeab939a3ffb29ffdf73572faa0ab180d76997d00d68ea077c938552c4c`
still mismatches version/hash; GDB `18.1` with digest
`4f9000b35fcd3f41e1fa6b6e530bb05e16e0c817b1b6ff19ad2a3647fbfb2efe`
still matches only the version. Required identities remain exactly those in the
frozen table above. This is a fresh hosted rejection, not successful Windows
installer acceptance or independently authenticated original package ownership.

New-source [aggregate job 140945346107](https://github.com/mtalhak003/FIRMAVEX/actions/runs/46134066330/job/140945346107)
failed in **34 seconds** (run duration 37 seconds). Its public annotation repeats
passed CPU/process/OOM checks and failed namespace boundaries with the loopback
denial. Child PID 2684 was recorded reaped with code 1; the last unit reported
cleanup verified, inactive and no control group. This preserves the failing gate
and recorded cleanup, not kernel-policy causality. No original ZIP was retrieved.

The authorized Issue #10 update was attempted through `gh issue comment` with a
body file and through the direct REST comment endpoint. Both returned
**Forbidden**. No comment was posted, issue closed or credential bypass attempted;
a factual draft remains outside the repository for later authorized publication.

Final documentation validation checked **174 local links, 23 anchors and 117
local commit references** in the index, chronological progress and this report.
Both modified Python files passed AST/whitespace checks; `git diff --check` passed.
No workflow, production, research, packaging or runtime-profile changes were
included in the implementation commit.
