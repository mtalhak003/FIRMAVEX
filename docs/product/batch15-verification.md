# Batch 15: responsive evidence verification

Batch 14's final product matrix, Windows/Ubuntu unified qualification, Desktop
beta and installer lifecycle passed. Its macOS RLIMIT_AS, Linux namespace/network
policy and mandatory release-gate failures remain separate qualification blockers.

## Desktop workflow

Verify selected evidence and Verify folder open a dedicated read-only verification
tab. Work runs in the existing supervised worker, never in Qt. Current result,
comparison, selection and trust state are preserved. Opening a folder never runs
saved projects or artifacts. Verification does not save a report into the archive.

The table shows pending/checking work followed by hash match, hash mismatch,
missing artifact, unavailable metadata or read error where supported. The existing
verifiers remain fail-fast: later files become not checked rather than silently
skipped. A failure in final inventory or metadata-consistency checks fails the
overall operation even if every individually observed artifact matched.

Cancel uses the existing worker cancellation channel. It is checked within both
1 MiB file capture passes, within chunked SHA-256 hashing, during inventory traversal
and between receipts/archive checks. File handles and SQLite connections close
before a terminal result is emitted. Completed rows remain visible; interrupted
work is cancelled/not checked and the overall result has success=false. A worker
error preserves streamed completed rows as partial observations without an overall
verification claim.

Progress is indeterminate before a bounded inventory is available. Once known,
counts describe finished artifact checks, not elapsed time or bytes remaining.
Progress events carry bounded inventory or row deltas; terminal events retain the
complete bounded result. No percentage is displayed for unknown totals.

## Guarantees and compatibility

The service reuses the backend export's artifact-name, digest, size, collision,
byte-limit and stable-read checks, and the ARM store's registered-artifact and
unregistered-file checks. Existing default callers retain strict behavior. Hashing
uses the same SHA-256 algorithm with cancellation checkpoints. ARM explicit checks
use the existing bounded double-read capture helper after the existing 128 MiB
archive preflight. No stored schema changes or recovery writes are introduced.

The desktop verifier rejects more than 256 registered ARM artifacts before checking
files; shared inventories retain the existing export limit. This is a bounded view,
not permission to verify a truncated inventory. Names are safely rendered at 160
characters, event/result counts are bounded, and diagnostics do not expose raw OS
errors or environment data.

Verification proves only the stated artifact/inventory checks at observation time.
It does not establish authenticity, receipt/accounting validity, nested ARM receipt
integrity for shared wrappers, physical execution, security isolation or release
approval. Existing full ARM archive review remains separate. SQLite snapshot/schema
checks and initial JSON parsing have coarse cancellation boundaries; interruption
is checked before the next file/receipt phase. Results are session-only, and
concurrent writers are not locked out by read-only verification.

Next: clearer verification-session provenance and copy/export of bounded verification
summaries outside original evidence, with explicit stale-result handling.
