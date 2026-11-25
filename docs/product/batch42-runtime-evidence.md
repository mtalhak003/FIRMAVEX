# Batch 42 — Runtime evidence and read-only consistency checks

**Investigation started:** November 24, 2026, Asia/Karachi.
**Recovered review and final validation:** November 25, 2026, Asia/Karachi.
**Starting checkpoint:**
[`408ea67a901c4053d2a7c4ac4c3053c05ba0d4a6`](https://github.com/mtalhak003/FIRMAVEX/commit/408ea67a901c4053d2a7c4ac4c3053c05ba0d4a6).
**Tracking:** [Issue #8](https://github.com/mtalhak003/FIRMAVEX/issues/8).
Runtime qualification and hostile-workload isolation remain **NOT ESTABLISHED**.

**Implementation commits:**
[`9d5c4c57f2b7a08c79887573627214cac28e1597`](https://github.com/mtalhak003/FIRMAVEX/commit/9d5c4c57f2b7a08c79887573627214cac28e1597)
adds strict namespace-result verification;
[`69cbf9281ef17093b295ff138fe1bcde4d940aa1`](https://github.com/mtalhak003/FIRMAVEX/commit/69cbf9281ef17093b295ff138fe1bcde4d940aa1)
adds supplied runtime-record checks and the corresponding CI selection.

## Evidence update and attribution

The approved detached worktree and remote development branch matched the starting
checkpoint, with no scoped modifications. Existing work was preserved. The
[Batch 41 investigation](batch41-qualification-evidence.md), unchanged admission
policy, acquisition workflow and existing verification tools were inspected.

The latest [Issue #8 comment](https://github.com/mtalhak003/FIRMAVEX/issues/8#issuecomment-7137019684)
reports successful original-artifact retrieval and read-only inspection through
the connected GitHub API in another execution environment. Its identifiers and
original ZIP digests are:

| Artifact | Run / artifact ID | Reported original ZIP SHA-256 |
|---|---|---|
| Windows lifecycle | `45420108864` / `14933359923` | `4670b91748d2db8eaa4dc80070854784d302718ea7ce7ad2d58cc9de68cbdef2` |
| Aggregate Linux | `45420108955` / `14933782277` | `59915a96921c889964073ae32b5a95096ee4c06e163fa6bd5354d308e3b052df` |

The comment reports matches to the same-job uploaded ZIP digests and successful
ZIP CRC checks. These are **issue-reported original-artifact checks**, distinct
from Batch 41's public annotations and from independently repeated checks here.
The current checkout's authenticated GitHub requests still return `Forbidden`,
including direct ZIP requests for both exact artifact IDs after recovery;
it did not acquire, hash, extract or execute those original ZIPs. No missing
artifact was reconstructed. This preserves both the historical access failure and
the later reported evidence-access improvement.

## What the reported originals establish

The Windows receipt reportedly binds its candidate revision to the starting
checkpoint, with `passed=false` and `phases=[]`. No installer transition is
recorded; that is not proof that no runtime-discovery subprocess ran. It does not
establish Windows install, rollback, uninstall or consumer acceptance.

The captured package declarations now identify:

| Package | Reported `pacman -Q` version |
|---|---|
| `mingw-w64-ucrt-x86_64-qemu` | `11.1.3-2` |
| `mingw-w64-ucrt-x86_64-qemu-common` | `11.1.3-2` |
| `mingw-w64-ucrt-x86_64-gdb` | `18.1-4` |
| `mingw-w64-ucrt-x86_64-gdb-multiarch` | `18.1-4` |

QEMU's acquired upstream version differs from admitted `11.1.2`. GDB's upstream
version matches `18.1`, while its executable digest differs. The receipt's
reported observations agree with the earlier CI notice:

- QEMU: `15368eeab939a3ffb29ffdf73572faa0ab180d76997d00d68ea077c938552c4c`.
- GDB: `4f9000b35fcd3f41e1fa6b6e530bb05e16e0c817b1b6ff19ad2a3647fbfb2efe`.

The exact [admission pins](../../firmavex/product/platform_support.py) remain
unchanged. A reported package build revision is additional provenance context,
not proof of the cause of changed executable bytes, ownership or publisher trust.

The Linux originals reportedly agree on outer/nested namespace data: CPU,
process and memory checks pass; namespace boundaries fail with bubblewrap's
loopback `RTM_NEWADDR: Operation not permitted`. All four unit cleanup flags are
recorded true. The archive contains no same-host kernel/AppArmor audit record.
It therefore establishes the recorded failed step and cleanup, not its exact
kernel/LSM cause. Separate-VM AppArmor denials must not be substituted.

## Remaining provenance and closure gaps

The [acquisition workflow](../../.github/workflows/versioned-install.yml) upgrades
rolling MSYS2 packages and installs unversioned roots. Recording `pacman -Q`
explains the selected declared package generation; it is not an immutable signed
package lock. The lifecycle artifact's retained paths omit `local-runtime.zip`
and the vendor runtime prefix. The receipt/inventory and unsigned application
installers therefore do not supply the actual QEMU/GDB/DLL bytes or authentic
publisher-package archives needed to close these gaps.

Existing [package verification](../../tools/windows_candidate_packages.py) requires
actual archives/signatures, independently trusted signing inputs and pinned
verification tools. Existing [PE import auditing](../../tools/windows_candidate_closure.py)
requires actual reviewed executable/DLL bytes and resolution manifests; its static
scope still cannot prove all dynamic loader behavior. Their historical candidate
pins are not relaxed to accept `11.1.3-2` / `18.1-4`.

The [provenance workflow](batch28-runtime-provenance.md) and
[Batch 32 decision gates](batch32-windows-runtime-packaging-plan.md) still require
compatible authenticated package closure, archive-to-installed ownership, native
loader/Python/plugin evidence and actual license/source-delivery inputs. ZIP
integrity and internally consistent receipts do not satisfy those requirements.
No unverified vendor download, installer execution or new profile promotion was
performed by this batch.

## Narrow verification improvements

The strict [`pacman -Q` syntax parser](../../tools/windows_runtime_candidate.py)
is separated from the historical candidate
pin check. Existing candidate admission keeps the exact same root/version pins;
the generic parser provides syntax validation only. This allows diagnostic use of
the newly reported package inventory without treating it as the old candidate.

A new [read-only assessor](../../tools/windows_runtime_inventory.py) checks
explicitly supplied lifecycle receipt and package inventory files against
separately supplied digests and expected source revision.
It reuses existing bounded stable-file reads, lexical/path restrictions, strict
JSON parsing and identity projection. It does not extract ZIPs, execute tools,
download packages, modify inputs or infer original-archive authenticity.
Package declarations and upstream-version agreement remain declarations, not
executable ownership or dependency closure. Receipt/revision agreement is not
authenticated Git origin; source authenticity is explicitly `not_assessed`.
Only the declared scope's receipt fields/projections are assessed; other
administrative metadata is not authenticated by a successful consistency result.
Output excludes private paths, raw
failure text and arbitrary inventory fields. Observable consistency checks are
not atomic snapshots or hostile-filesystem access isolation; the existing MEDIUM
concurrent parent-replacement limitation remains.

An independent malformed-record defect was also reproduced in the aggregate
verifier: the previous `all(nested['checks'].values())` accepted an empty dictionary
and truthy non-Boolean values. The new guard requires the existing complete check
set, exact Boolean passes and supported schema/status/security fields. This
strengthens record verification without changing guests, commands, quotas,
timeouts, production admission or host policy. It neither caused nor fixes the
observed loopback denial, and it does not authenticate guest-written evidence.

## Actual validation and operator usage

The local host is Linux x86-64/Python 3.12.14. Bubblewrap is present, but the host
has no running systemd, administrator authority, writable unprivileged cgroup
hierarchy or KVM device. Native Windows execution and the privileged hosted
isolation contract cannot be established locally. No original evidence installer,
signer or firmware campaign was executed.

The initial existing-suite selection on November 24 reported **234 passed,
2 skipped**, zero failures/errors/deselections, **1.93 seconds**. Both skips require
the explicit native Windows candidate workflow. The uncommitted drafts survived
the environment interruption at the unchanged checkpoint. Recovered focused
validation on November 25 reported **272 passed, 2 skipped**, **1.67 seconds**;
the initial wider selection reported **768 passed, 5 skipped**, **21.68 seconds**.
Three additional null-observation cases were then added to preserve unknown
identities explicitly; source authenticity is also labelled unassessed.

Initial implementation focused validation, before the native fixture follow-up:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_windows_runtime_inventory.py tests/product/test_windows_runtime_candidate.py tests/product/test_aggregate_isolation_probe.py
```

**275 passed, 2 skipped**, zero failures/errors/deselections, **1.84 seconds**.
The two skips still require the explicitly authorized native candidate workflow.
These counts overlap with prior selections and are not additive.

The wider relevant selection is:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_windows_runtime_inventory.py tests/product/test_windows_runtime_candidate.py \
  tests/product/test_aggregate_isolation_probe.py tests/product/test_windows_runtime_preflight.py \
  tests/product/test_windows_candidate_packages.py tests/product/test_windows_candidate_closure.py \
  tests/product/test_versioned_install_ci.py tests/product/test_platform_support.py \
  tests/product/test_isolation_feasibility.py tests/product/test_namespace_diagnostics.py \
  tests/product/test_file_state.py tests/product/test_build_inputs.py \
  tests/product/test_ci_diagnostics.py tests/backends/test_records_security.py
```

Initial implementation wider result: **771 passed, 5 skipped**, zero failures/errors/deselections,
**21.23 seconds**. Two skips require the native candidate workflow, one requires
actual NTFS change-time semantics, one requires ARM tools, and one follows the
local namespace UID-map denial (`Read-only file system`). That local denial is
distinct from the hosted loopback error and is not its cause. No local suite
failed. These overlapping selections are not a complete repository test run.
No local result is presented as original-artifact verification or qualification.

Independent read-only review found no blocking defect. Positive, negative,
malformed, byte-boundary, missing-identity, read-only, race and cancellation cases
are covered. The assessor's synthetic tests prohibit process/network dispatch,
directory enumeration and file writes. The aggregate tests simulate the supervisor
and do not establish actual namespace enforcement.
Two actual module-CLI smoke invocations against **invented** temporary records
returned `0` for consistent records and `2` for a wrong digest, leaving files
unchanged. No original artifact or executable was substituted. Nine fixed guest /
candidate-policy AST contracts matched the baseline, and the product workflow
diff was exactly one added test argument. Initial static checks passed six Python
AST parses, all ten intended files' whitespace, 176 local documentation links,
23 anchors and 114 locally resolved commit references. `git diff --check` passed.

### Operator command and exit meaning

Use only explicitly reviewed, stable record files outside protected evidence and
the original checkout. Independently retain their file digests during trusted
intake; the ZIP digest above is **not** either member's digest. No original-record
member digests were supplied in Issue #8, so none are invented here.

```bash
python -B -m tools.windows_runtime_inventory \
  --receipt /private/intake/versioned-lifecycle.json \
  --inventory /private/intake/versioned-vendor-packages.txt \
  --revision 408ea67a901c4053d2a7c4ac4c3053c05ba0d4a6 \
  --receipt-sha256 REVIEWED_RECEIPT_SHA256 \
  --inventory-sha256 REVIEWED_INVENTORY_SHA256
```

Replace the placeholders with actual reviewed lowercase SHA-256 values; unchanged
placeholders are rejected. JSON goes to stdout and a fixed summary to stderr.
Exit `0` means **consistent supplied records**, including recorded rejection;
it never means a runtime passed admission. Exit `2` means a blocked/malformed or
inconsistent assessment. Missing observed identities remain null, never matches.
No ZIP authenticity, publisher trust, binary ownership, dependency/license closure
or native capability is established. Interruption propagates instead of producing
an ordinary result. No report or evidence file is written by the command.

The existing product workflow gains only this test module in its supplied
platform-neutral selection; no check, timeout or security setting is removed.
`tools.check_build_inputs` passed. `actionlint` and a standalone YAML parser were
unavailable locally; neither is reported as run. Automatic CI must validate the
published workflow and its actual platform behavior.

## First automatic CI result and test-fixture repair

The code commits were pushed normally at `69cbf9281ef17093b295ff138fe1bcde4d940aa1`.
[Product run 45564176037](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45564176037)
accepted the workflow and ran the added module. The native
[Windows Python 3.12 job 139034810063](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45564176037/job/139034810063)
passed. The [Windows Python 3.11 job 139034810281](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45564176037/job/139034810281)
completed its platform-neutral selection successfully, then failed an existing
desktop test before its lock assertions ran:
`test_windows_other_process_writer_blocks_save_but_not_readonly_open_and_allows_retry`.

Its public traceback shows `ready.read_text(encoding='ascii') == 'locked'` receiving
an empty string after the parent observed file existence. The child used
`Path.write_text()` on the final readiness filename, exposing the empty created
file before writing completed. This is a fixture publication race, not evidence
that the application's project lock failed. Exact native pytest/JUnit totals were
not independently recovered from the public annotations.

The test-only correction publishes the complete marker after writing closes,
while retaining the real Windows lock operation, parent deadline/process checks,
exact marker assertion, application assertions and bounded cleanup. Portable
regressions test the controlled publication protocol; they do not simulate a
Windows lock and label it native. Production project locking is unchanged.
The failed attempt is retained; the repaired revision requires its own CI result.

The test-only repair is
[`3d40ca1b7a2362a7b52d97fb3f9a589bc77b89c3`](https://github.com/mtalhak003/FIRMAVEX/commit/3d40ca1b7a2362a7b52d97fb3f9a589bc77b89c3).
The same child script now writes/closes an exclusive pending marker and renames
it to the final readiness name while holding the lock. A fresh-marker precondition
prevents stale readiness. Five portable cases exercise partial publication,
write/rename failure with unlock, and stale marker rejection. This establishes
only the controlled fixture protocol, not general filesystem isolation.

The desktop file reported **10 passed, 6 skipped**, **0.69 seconds** on Linux.
All six skips require actual Windows. Final combined focused validation uses the
focused command above with `tests/desktop/test_windows_desktop_paths.py` added and
`QT_QPA_PLATFORM=offscreen`; it reported **285 passed, 8 skipped**, zero failures/
errors/deselections, **2.25 seconds**. Final wider validation uses the wider
command above with that same desktop file added: **781 passed, 11 skipped**, zero
failures/errors/deselections, **21.61 seconds**. The six additional skips are
unchanged native Windows sharing/attribute/locking cases. Earlier counts remain
historical; no assertions, test deadlines or application lock behavior were relaxed.
After that repair, final static checks passed seven Python AST parses, all eleven
intended files' whitespace, 176 local links/23 anchors and 115 commit references.
`git diff --check` passed. The repaired source was pushed normally at `3d40ca1b`;
its native CI result must be recorded separately from the initial failure.

The repaired source `3d40ca1b7a2362a7b52d97fb3f9a589bc77b89c3` subsequently passed
both native Windows product-regression jobs in
[run 45565508260](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45565508260):
[Python 3.11, job 139039185813](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45565508260/job/139039185813),
and [Python 3.12, job 139039186007](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45565508260/job/139039186007).
Their current job headers display successful completion and retained/session
pytest statuses are all `0`, including platform-neutral and synthetic-desktop
selections. Exact original JUnit totals were not independently verified.
All six Windows/Ubuntu/macOS matrix jobs displayed success. The overall workflow
was still running at inspection because the separate Linux real-product job
remained; whole-workflow success is not inferred from the matrix passes.

This is native host regression evidence for the checker and controlled marker
repair. It is not original-artifact assessment, consumer acceptance, vendor
authentication, actual Windows firmware qualification or sandbox qualification.
The subsequent documentation publication keeps the tested code unchanged.

The authorized Issue #8 update was attempted through `gh issue comment` and the
REST comments endpoint. Both returned `Forbidden`; no comment is claimed posted.
A factual draft was retained outside the repository for later authorized posting.
Git publication remained available, so this API limitation was not treated as a
reason to discard the implementation or fabricate an issue update.

Fresh aggregate [run 45564175941, job 139034809539](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45564175941/job/139034809539)
failed with the same recorded loopback denial, passed fixed quota checks and
verified cleanup. The new completeness guard did not turn the blocked contract
into a pass. No original artifact was independently verified here.

## Recommended Batch 43 gates

1. Make the original record files available to this checker through authorized
   read-only intake, with independently recorded member digests and original
   archive/run context. A ZIP digest is not the digest of an extracted receipt.
   Keep the issue-reported original verification distinct from any new local run.
2. Obtain authentic compatible package archives/signatures, independent trust
   inputs and exact runtime bytes before invoking the existing closure verifiers.
   Recover an admitted immutable generation, or separately authorize a new fully
   captured candidate. Never update hashes merely to accept the latest package.
3. Separately scope a bounded same-host audit collection plan tied to boot/time
   and owned process/cgroup context. A `bwrap` name match or sibling VM journal is
   insufficient; helper PIDs can differ from the recorded launcher PID. Review
   diagnostics for privacy and preserve all host protections.
4. Keep failed admission/isolation, missing evidence and native consumer/signing
   limitations visible. No qualification issue is closed and no release follows
   from record consistency or passing synthetic tests.
