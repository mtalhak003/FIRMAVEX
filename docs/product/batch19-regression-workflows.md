# Batch 19: explicit regression sets and provenance

## Desktop workflow

1. In **Configurations**, save or open an immutable RV32 or single-file Verilog
   configuration. Use **Import new revision** for a new build; old definitions,
   copied inputs and runs remain intact.
2. Open **Regression test sets**, enter a name and **Add selected configuration**.
   Each row has a stable entry ID. Edit names and RV32 values (two uint32 values,
   separated by commas; hexadecimal `0x` notation is supported). HDL rows have
   no vector values. Add configurations for additional inputs or backends. Use
   **Replace configuration**, **Remove**, **Move up** or **Move down** as needed.
3. **Save new revision** validates every entry and pins its configuration revision
   and input SHA-256. Editing a saved set creates a new revision with a timestamp
   and parent link; it preserves the set ID and retained entry IDs. **List saved
   sets** and **Open listed set** reopen named revisions. **Open test set…** can
   select another local revision folder. None of these actions executes a target.
4. Review all inputs and native runtime tools, check the test-set trust box, then
   **Run saved test set**. Consent is specific to this submission and clears on
   edits, selection changes and submission. Static preflight validates and
   captures every entry before the first target is admitted. Entries execute in
   order through the existing supervised backend services, each with its own
   resource limits and fresh evidence directory. Runtime admission remains
   mandatory; static preflight alone does not establish compatibility.
5. **Cancel and clean up** cancels the active worker and supported backend stages.
   Completed observations remain recorded; remaining entries stay `not_run`.
   No entries retry or resume automatically. A firmware predicate or HDL assertion
   failure is recorded and execution continues. An infrastructure error, rejected
   compilation/input/output, or unverified cleanup stops further dispatch.
6. Results show set/revision/run identities and passed, failed, cancelled,
   infrastructure-error, not-run and unavailable counts. Double-click an entry
   to open its ordinary backend evidence in the existing diagnosis/history UI.
   Paths are references, not integrity or authenticity claims. **Open results…**
   inspects another regression run without executing it.
7. **Select previous run…** explicitly chooses a parent for the next full rerun;
   **Clear previous run** returns to an original run. The parent must belong to
   the same set. **Compare with previous** matches stable set/entry IDs and exact
   configuration/input/vector/backend identities. It distinguishes same recorded
   outcomes, different outcomes, unavailable observations and incomparable entry
   definitions; removed entry IDs are also shown. A comparison neither executes
   targets nor establishes reproducibility. Use the existing saved-run comparison
   for detailed runtime and environment differences between individual entries.

Saving configuration snapshots already provided immutable revision hashes,
creation timestamps and parent links in Batch 17. Batch 19 reuses that format;
it does not replace prior configuration definitions or migrate archives. A set
references those local configuration folders. Moving/importing it does not copy
or resolve dependencies automatically; missing or changed references are rejected.
A new revision must be selected explicitly rather than repairing a damaged one.

## Bounds and partial results

A set contains 1–16 entries. Names are 1–80 printable characters; entry IDs are
32 lowercase hexadecimal characters and revision/input hashes are 64. Manifests
are capped at 32 KiB, configuration metadata at the existing 16 KiB, and aggregate
captured inputs at 64 MiB, including repeated references. Each entry retains its
existing execution wall-clock, memory, log and artifact limits. The set has no
extra retry budget. The maximum set execution time is the sum of the selected
per-entry limits, subject to cancellation and supervisor cleanup.

Listing examines at most 200 folders and does not verify every referenced input;
opening performs full bounded validation. Reads reuse existing regular-file,
symlink/reparse-point, hardlink and observable-change rejection. A newly owned
run's summary is updated atomically; earlier run directories and configuration
manifests are never rewritten. Summary reads are capped at 128 KiB and entry
summaries at 1,024 characters; full diagnostic logs remain in backend evidence.

`regression.json` is an administrative summary, not a replacement for backend
admission/results or scientific accounting. An abruptly interrupted entry can
remain `running` with category `unavailable`, meaning execution/cleanup is
unknown. This is a recorded state, not a claim that the process is still alive.
Unstarted entries remain `not_run`. Cooperative cancellation retains partial
counts; no missing record becomes a passing observation. A summary inspection
validates its bounded structure but does not hash-verify every linked backend
artifact. Existing verification/export services apply to individual backend runs.

## Provenance and guarantees

New shared-backend admissions record schema-versioned software assumptions:
backend/target contract, host OS and architecture, Python version, and references
to retained input/tool identities and version observations. Saved-configuration
runs add the selected revision, creation time and input hash. Test-set entries
also add set/revision/entry/run IDs and, for an explicitly selected rerun, the
original regression run ID. Ordinary supported replay records the originating
backend attempt identity. No historical record is rewritten or populated by
inference. Older or unrecorded provenance remains unavailable in Batch 18
comparison; new fields integrate with its diagnostics and comparisons, including
separate environment assumptions and rerun relationships.

These are recorded declarations and software observations. Matching hashes do
not prove authentic execution, and runtime executable identities may identify
wrappers rather than every binary/library they invoke. Tool versions appear
only when existing backend probes retained them. Host metadata does not capture
all environmental dependencies. Reruns are new observations, not hardware
validation, physical FPGA validation or complete reproducibility.

ARM retains its existing search and reproduction workflow; it is not a Batch 19
test-set backend. RV32 retains its exact two-input symbol contract. Verilog
retains the existing constrained ASCII single-file, fixed-top/result-marker
boundary: no includes, arbitrary multi-file builds, extra system tasks, remote
execution, imported-code auto-execution or HDL trust-boundary expansion is added.
macOS RLIMIT_AS admission, Linux isolation qualification and distribution-evidence
gates remain unchanged and separate from local regression results. No release
approval is established.

## Validation and remaining work

Baseline commit `ca8a30ca566043352e5d14ecde27760c36be6081` matched the clean
tracked development branch. Batch 18's product workflow
[40003710619](https://github.com/mtalhak003/FIRMAVEX/actions/runs/40003710619)
completed successfully across all seven jobs before delivery of Batch 19.
No unexplained baseline divergence or new baseline regression was found.

Local Linux validation completed with:

- Product and desktop regressions with available native tools: **1,215 passed,
  7 skipped**, zero failures (223.77 seconds).
- Backend regressions: **215 passed, 9 skipped**, zero failures (41.31 seconds).
- Final focused storage, provenance, worker, diagnosis, comparison and Qt tests:
  **256 passed**, zero failures.
- Native RV32/Verilog sets through the real supervisor, explicit reruns,
  input/provenance identity checks and Verilog in-flight cancellation: **3 passed**.

Native RV32 required local debugger sockets outside the Codex shell sandbox.
Ubuntu QEMU 10.2.1 and Icarus 12.0 packages were extracted to temporary user-owned
storage; matching QEMU modules resolved a host/package build mismatch. Icarus
used an explicit support-directory wrapper. These are local software observations,
not publisher/runtime-bundle qualification or distribution evidence. Tool discovery
isolation tests required putting these tools on PATH rather than using a global
runtime-directory override; no tests or production policies were weakened.

The diff was reviewed for input/metadata bounds, immutable revision/evidence
handling, cancellation, process cleanup and compatibility. `git diff --check`
passed. Product CI now includes focused storage/provenance tests on its platform
matrix, and unified native CI includes the new representative regression-set
tests. Results for the Batch 19 commit must be checked separately.

Remaining limits include local absolute configuration references, no automatic
archive relocation/migration, no complete host/dependency capture, no aggregate
artifact verification/export bundle, and no automatic cross-project run index.
Unknown or malformed optional provenance versions are unavailable in diagnostics
and comparisons. Proposed Batch 20: bounded aggregate regression evidence review
and export, plus a clear dashboard for set revisions and past runs, reusing the
existing per-run verifier and preserving explicit execution consent.
