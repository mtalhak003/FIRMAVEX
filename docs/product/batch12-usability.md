# Product batch 12: shared workspace usability

## Audit and scope

The ARM editor already provides project creation/opening, immutable configuration
versions, bounded search, reproduction, saved-run inspection and export. The shared
workspace already supports ARM, RV32 and Verilog execution, examples, runtime
checks, history, cancellation and export. This batch extends those components
rather than adding another project format or execution interface.

The shared workspace had no actionable explanation for a disabled Run button,
required a double-click to open history entries, showed only raw directory names
without filtering or empty-state guidance, and allowed administrative operation
output to replace the evidence pane while the previous result remained selected.

## Changes

1. Inline guidance explains input, runtime-readiness and trust requirements.
   RV32 vector errors disable Run immediately with a bounded explanation. The
   worker still owns file compatibility checks, admission and execution.
2. History has a run-name filter, Open selected action, counts and empty states.
   Refresh retains the selected path. Filtering never parses saved records;
   opening still uses supervised inspection and never dispatches a target.
3. A selectable result context identifies the displayed backend, outcome and
   saved directory independently of the current execution form. Unknown saved
   identity remains unknown rather than being inferred from the selected target.
4. Runtime checks, preparation and exports have a separate operation-details
   tab. Successful or failed administrative operations preserve the selected
   result, its explanation and raw evidence. Worker errors select their diagnostic
   tab, with bounded status and error messages.

No saved-run/export schemas, project consent rules, resource policies, process
cleanup or release gates change. History remains capped at 1000 entries and does
not yet provide cross-run comparisons or validated outcome indexing.

## Validation

Pure product tests cover all three request profiles, resource-policy preservation,
bounded vector/path errors and saved identity rendering. Qt tests cover workflow
guidance, filtering, selected-run opening, consent and preservation of saved
evidence across successful and failed administrative operations on all profiles.
Local GUI validation requires PySide6 and pytest-qt; CI runs the desktop suite
with offscreen Qt on Windows, Ubuntu and macOS. Native qualification remains
separate from synthetic GUI tests and from release approval.
