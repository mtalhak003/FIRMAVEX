# Batch 16: verification observations, freshness and reporting

Batch 15's final product matrix, Windows source/frozen/installed native
qualification, Desktop beta and distinct-version installer lifecycle passed.
The macOS RLIMIT_AS admission, Linux network-boundary policy and mandatory
release-evidence failures remain qualification blockers, not release approval.

The Verify evidence tab now retains UTC session start/end times, archive path,
verification scope, completion state and whether completed hash checks are only
partial results. Worker interruption retains streamed rows with failed/partial
provenance and unknown freshness. Verification observations remain session-only;
opening projects or saved records does not execute them or start verification.

Check for changes explicitly performs bounded metadata queries in the supervised
worker. The baseline is captured before artifact hashing for listed/registered
files and the relevant archive record files, using existing platform-specific
file identity, size and write/change timestamps. A changed available identity or
metadata tuple is stale. Missing, rejected, malformed, cross-platform or unavailable
observations yield unknown unless another supported observation establishes a
change. Unchanged supported tuples mean only **no observed metadata changes** at
the displayed check time. They do not establish unchanged contents. Metadata-only
checks never rehash artifacts or replace the historical hash outcomes. Newly
added unlisted files, SQLite sidecars and adversarial metadata restoration are
outside this change check; rerun full verification for current integrity checks.
The observation is not an atomic snapshot or a live monitor.

Export verification report explicitly chooses a parent directory and creates a
new uniquely named directory outside the original archive. The supervised worker
rejects source/destination overlap, symlinks/reparse paths and existing destination
directories. A plain UTF-8 text report is created exclusively, never overwriting a
saved run or evidence file. Existing archive and export formats are unchanged.
Reports include provenance, partial/completion state, per-artifact observations,
a new timestamped metadata check and scope limitations. Names/messages are
sanitized and bounded; up to 256 rows and 256 KiB of output are allowed. Display
names can be truncated; row numbers distinguish them. Session transport is bounded
and validated separately. No environment details or raw OS diagnostics are added.

Hash observations do not establish authenticity, execution, isolation, receipt
validity or release approval. Reports are unsigned observations, not authenticity
certificates. Cancellation is checked between metadata queries and before report
creation. The bounded final write is a single commit point; a worker/write failure
can leave an incomplete new report directory, but cannot overwrite original
storage. Progress, cancellation, existing results/comparison/logs and evidence
bytes remain independent of metadata review and export.

Recommended Batch 17: report failure/cleanup UX and richer archive inventory change
visibility, with explicit unsupported states and no automatic rehashing.
