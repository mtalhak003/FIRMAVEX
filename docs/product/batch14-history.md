# Batch 14: advanced history and comparison

## Existing checks reused

Shared backend records already had bounded structural/admission inspection.
Their export path also verifies listed artifact SHA-256 digests and byte sizes,
with filename, collision, link and aggregate-byte checks. Standalone ARM archives
already have read-only SQLite inspection, registered artifact hashing, and receipt
and evaluator-accounting consistency checks. This batch reuses those checks; it
does not add an independent integrity or security mechanism.

## Desktop behavior

- Comparison accepts shared ARM/RV32/Verilog archives and supported standalone
  ARM `run.sqlite3` archives. Choose left folder / Compare folder makes archives
  outside shared history accessible. Neither action executes saved content.
  Standalone inspection reuses the ARM export inventory/byte preflight before
  calling its existing inspector. Ambiguous, malformed or unsupported archives
  remain unavailable. Exact recorded outcome vocabulary is retained across
  formats; similar words are not silently declared equivalent.
- A non-editable table presents left/right values with changed, unchanged or
  unavailable classifications. Paths are references only. Display values are
  limited to 300 characters, with tooltips capped at 1000. Missing fields are not
  equal. Unsupported standalone cleanup, request-vector and start-time fields
  remain unavailable rather than being inferred from a result verdict.
- History combines name search and last-inspected outcome categories, including
  unknown/incomplete/uninspected entries. Summary inspection still works when an
  outcome filter hides all rows: it inspects up to 50 matching **names**. Selection
  is retained, while hidden entries cannot be opened or used as the right run.
- Integrity state and scope appear in summaries and comparison. `verified` means
  an existing nonempty artifact inventory was actually hash/size checked.
  `unverified` means a supported check failed or was rejected; `unavailable` means
  no relevant check completed or no registered/listed artifacts were available.
  An intact result JSON or a recorded digest alone never yields `verified`.

## Limits

Checks are sequential observations, not atomic snapshots, authenticity/signature
checks, execution proof, hardware validation or release approval. Shared backend
verification covers listed files only; it does not verify an ARM wrapper's nested
receipt store. Standalone checks cover its registered artifacts and established
archive/accounting checks. The table keeps scopes separate rather than equating
these coverage sets. Existing 128 MiB export/inventory limits apply; cooperative
cancellation is checked between archive reviews, not inside existing hash loops.
No files are repaired, exported, rewritten or rerun during review.

Future work: explicit cancellable verification progress and narrower per-file
results, using a separately reviewed verification API instead of expanding the
meaning of the current integrity state.
