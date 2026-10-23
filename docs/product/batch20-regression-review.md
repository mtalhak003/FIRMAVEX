# Batch 20: regression dashboard and evidence reports

## Review workflow

Use **Regression test sets → Refresh dashboard** to list saved set revisions,
recorded configuration/input pins and recent sessions. With a saved revision
selected, the session scan is limited to that revision; otherwise it scans the
bounded local set store. The search box filters saved-set names/revisions and
session names/run/revision identities. Counts and states are recorded summary
values, including completed, cancelled, stopped and partial sessions. Double-click
a session to re-inspect it, then double-click an entry to open the existing
backend diagnosis/evidence UI. Opening or listing never executes a target.

**Compare with previous** now displays a read-only table with same, changed,
missing, unavailable and not-comparable observations. Revision and entry-definition
changes are separate from outcome comparison. Outcomes are compared only when
set/entry IDs and backend/configuration/input/vector definitions match. Removed
and newly introduced entry IDs are explicitly missing from one side. Unknown
observations never become equality. Batch 19's comparison API retains its prior
labels; the new dashboard/report path uses the expanded presentation.

Use **Verify selected session** for explicit aggregate checks. Per-entry association
checks compare the retained backend record against recorded set/revision/run/entry,
configuration/input identity, vector, outcome and category. Missing legacy
provenance remains unavailable. Artifact checks reuse the existing verifier,
including the retained RV32 `firmware.elf` or Verilog `testbench.v` identity and
listed artifacts such as VCD files. The ordinary single-run verifier's default
scope is unchanged. No arbitrary binary is executed or interpreted as code.

The view preserves per-artifact and per-entry verified, changed, missing,
unavailable and unverified observations. Cancellation keeps completed hash
observations; remaining work stays unverified. An aggregate verified status
requires all selected entry checks to finish, supported association metadata to
match and no observed summary change. Unsafe archives and exceeded bounds fail
closed. Unlisted files and retained inline logs are not independently authenticated
by this operation. Hash matches establish correspondence to recorded digests,
not authentic execution, trustworthy assertions or physical hardware behavior.

## Portable reports

**Export text report…** selects a parent for a fresh report directory. Export
performs fresh aggregate verification; it never trusts cached UI observations.
The fixed `regression.txt` file includes supported identities, recorded outcomes
and counts, bounded environment/tool/provenance metadata, failure diagnoses,
per-entry/artifact verification observations and an optional previous-session
comparison. Missing previous comparison metadata is explicitly unavailable.

The UTF-8 plain-text format does not embed binary artifacts, active HTML, scripts,
archive contents or executable links. Nonprinting characters are replaced;
display-limited fields are labelled by truncation markers. This is a bounded
review report, not a complete evidence archive. Use existing per-run export when
the supported full artifact export is needed.

Export rejects original-session overlap in either direction, selected previous
session overlap, the containing original set revision, and available referenced
configuration folders. Existing canonical path/symlink/reparse-point protections
are reused. Reports use exclusive creation and never overwrite an existing
report or evidence. Cooperative write cancellation removes only the newly created
report files. Original run summaries and artifacts are never rewritten.

## Bounds and interpretation

- The dashboard lists at most 200 revision folders, 64 configuration pins and
  examines at most 200 session candidates; it displays the latest 50 within that
  scan using recorded timestamps. Its shared read budget is 128 MiB. This is not
  a recursive global history index or a guarantee that every stored session was
  scanned.
- A regression session retains Batch 19's maximum of 16 entries. Summary reads
  remain bounded to 128 KiB each. Aggregate review shares a 256 MiB actual-read
  budget (including the existing consistency rereads), at most 1,024 read calls,
  and at most 256 artifact inventory items. Existing per-file/archive limits
  remain mandatory. A pre-verification boundary scan rejects links, special files,
  hardlinks and archives over 128 MiB, with the existing 10,000 filesystem-entry
  traversal cap. The byte/read budget also applies if files change after scanning.
- Per-entry metadata fields exceeding 2,048 serialized characters become
  unavailable; diagnoses show at most 4,096 characters. Review responses exceeding
  750,000 encoded bytes are rejected. Reports are capped at 256 KiB; oversized
  reports are rejected before a destination is created. No fallback silently
  expands these bounds.
- Verification is sequential, not an atomic snapshot. Results include start/finish
  times and a summary observation. Concurrent changes or unknown association
  prevent an overall verified claim; already completed artifact observations keep
  their limited scope. A report can become stale after its checks finish.

ARM retains its existing search, reproduction, diagnosis, comparison, individual
artifact verification and report paths. Batch 20 does not introduce ARM test sets,
new execution semantics, archive migrations, inferred historical provenance,
automatic retries, multi-file HDL, hardware/FPGA validation or release approval.
The macOS RLIMIT_AS, Linux isolation and mandatory distribution-evidence gates
remain independent of dashboard/report functionality.

## Baseline and validation

The tracked development branch matched expected Batch 19 commit
`3d9ffcb5cc0ef1c9b91796d7cab9a0835d389ec3` before implementation.
[Product CI](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40011062002)
completed successfully. [Native CI](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40011061937)
passed on Ubuntu and Windows; the macOS resource-test failure showed RLIMIT_AS
admission rejection and dependent tests that could not start their child process.
This is the existing native memory blocker, not a Batch 19 regression.

Focused tests cover bounded dashboard listing, old/missing/malformed metadata,
artifact changes and disappearance, association mismatches, partial/cancelled
verification, shared reread budgets, unavailable comparisons, plain-text export,
path overlap, output limits, sanitization and evidence immutability. Worker tests
reject any program execution in administrative review actions. Qt tests exercise
search, selection, comparison, hash-state presentation, consent and export.
Representative RV32 and Verilog fixtures exercise the complete workflow through
both the real supervisor and the real Qt controller.

One local backend run hit the existing 300 ms total-deadline test during its first
command. The same failure reproduced against an isolated, unchanged Batch 19
snapshot; the current isolated test passed, followed by a full passing backend
run. The test and production deadline remain unchanged. This host-timing issue
is separate from the macOS, Linux-isolation and release-evidence gates.

Remaining limitations: recent lists cover the bounded scan rather than all
history; verification requires supported recorded inventories and associations;
results are not atomic snapshots; reports omit binaries and complete receipts;
missing historical provenance is unavailable; and no new platform qualification
or public release approval is established. A useful next milestone is explicit
saved-report/session provenance and cross-revision trend navigation, retaining
these bounds and the existing per-run evidence authority.

Final local Linux results:

- Product and desktop regressions with available native runtimes: **1,245 passed,
  7 skipped**, zero failures (243.37 seconds).
- Backend regressions: **215 passed, 9 skipped**, zero failures (33.55 seconds).
- Final focused product/verification/worker/Qt suite: **215 passed, 1 skipped**.
- Representative native supervisor workflows: **3 passed**; native Qt RV32 and
  Verilog dashboard/verification/report workflows: **2 passed** (also included in
  the full desktop run).

The focused suite was rerun after the final comparison-classification check.
`git diff --check` passed. Review covered backward-compatible archive handling,
bounded/cancellable reads, exclusive report creation and source overlap rejection,
retained evidence immutability and unchanged execution isolation/resource policies.
CI results for the Batch 20 commit must be checked separately; these local results
are not distribution or release approval.
