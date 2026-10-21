# Batch 13: project navigation and read-only run review

The ARM editor already verified project imports/opening on its background task.
The shared workspace already listed run directories and inspected individual
records in the supervised worker. This batch reuses those paths rather than
introducing a project format, database migration or execution interface.

- The Welcome page lists up to ten recently verified/opened ARM desktop projects.
  Reopening is explicit and invokes the existing verifier. Missing/moved projects
  report the existing verification error; Open project can locate the new path.
  Removing a shortcut never deletes a project. The bounded atomic preference
  index is separate from project and evidence data. Invalid indexes are not
  silently overwritten. Concurrent desktop instances may replace this preference
  list; it is not an evidence ledger.
- Inspect summaries explicitly reviews up to 50 visible backend-history entries.
  Labels show backend, exact recorded status and inspection availability. Missing,
  legacy or malformed records remain unknown. Summaries are session-only, labelled
  last inspected, and cleared by Refresh. They do not establish execution validity.
- Set left run and Compare with left re-inspect both runs using the existing
  bounded saved-record inspector. The Compare tab shows backend, recorded status,
  measurement, cleanup, timestamp, request values and evidence-file references.
  Each field is changed, unchanged or unavailable; two missing values are never
  treated as equal. Comparison does not change the selected execution result or
  grant execution consent. Review cancellation leaves saved files unchanged.

Comparison is sequential saved metadata inspection, not an atomic snapshot,
replay, artifact/hash validation or physical firmware verification. It supports
the shared ARM/RV32/Verilog backend archive format; older standalone ARM archives
remain available through their existing ARM inspector, not guessed into the new
format. History remains capped at 1000 entries. Recent-project shortcuts cover
managed ARM desktop projects; standalone RV32/Verilog inputs retain their current
source-file workflow.

Product tests cover persisted records, malformed/legacy/incomplete/cancelled runs,
transport, cancellation, byte immutability and bounded recent preferences. Qt
tests cover explicit reopening, missing projects, shortcut removal, summary
lifetime and comparison navigation without execution. Native workflow and release
qualification remain separate from these presentation tests.
