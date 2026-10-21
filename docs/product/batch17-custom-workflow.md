# Batch 17: repeatable custom inputs

## ARM project continuity and new builds

Opening the processor/HDL workspace from an open ARM project explicitly saves
current editor settings and freezes a command snapshot. The menu states that it
saves those settings. The workspace shows its path and configuration digest,
uses the originating project's runs directory, and clears readiness/consent.
Returning to the ARM editor reloads the selected snapshot, even if another active
configuration was saved meanwhile. Modified snapshots are rejected. A different
explicitly selected external ARM JSON opens its own configuration, without
silently retaining an unrelated managed project; import is required before using
managed-editor execution. Navigation never starts firmware.

Import new firmware build creates a fresh project using the current settings and
newly selected compatible ELF. Old imported images/configurations/runs remain
unchanged. It is a separate project, not an in-place image replacement or a build
system. Recent projects provide access to previous revisions. ARM revision groups
are not automatically merged.

## Named RV32 and Verilog snapshots

Open the Configurations tab, enter a name and use Save named snapshot.
Configuration controls use a two-column layout inside the existing tab area,
keeping the main execution form compact. The existing Request/Limit contract is
stored with a bounded copied input, original-path reference, timestamp and SHA-256
identity. Metadata is limited to 16 KiB. Each new folder is named by the manifest
hash; reopening validates that identity and the copied input hash before selection.
These hashes detect changes relative to the selected identity; they are not
publisher authenticity. Existing execution/run/export formats are unchanged.

List configurations examines at most 200 folders in the app-owned configuration
store. Invalid/unsupported entries are skipped without repair. Listing does not
hash all inputs; Open configuration performs full bounded input checks.
An original build may change or disappear: the selected imported snapshot remains
explicitly identified and is used instead. Modified/missing imported snapshots
are rejected. Original paths are not reopened automatically.

Import new revision explicitly selects a new file and creates a separate named
snapshot linked to its parent identity. Earlier inputs/configurations/evidence are
not replaced. A damaged parent cannot silently become a valid revision lineage.
Settings/source edits detach the saved selection and clear consent; saving again
is explicit. Use unsaved form returns to ordinary workspace history.
Opening/listing/preflight never execute targets or grant trust.

Run from a selected configuration captures verified bytes into an owned temporary
input before dispatch through existing execution services. Selected ARM handoffs
also pin and copy firmware bytes. Execution-time checks, native runtime gates,
resource policies and process cleanup remain mandatory. Temporary inputs are
removed after execution/cleanup. Cancellation is checked during reads, between
copy chunks and before publishing a new configuration. Only the new configuration
files are removed on cooperative save failure. Abrupt termination may leave an
incomplete new folder, which listing will not accept.

## Preflight and history

Check input compatibility performs static checks in the supervised worker and does
not invoke tools. ARM reuses the existing architecture/memory/symbol/debug-type
inspector. RV32 reuses existing ELF32, architecture, memory-map and symbol-presence
restrictions; instruction compatibility, debug types, completion and readback
still require execution checks. HDL reuses exactly the existing ASCII/system-task,
include and waveform restrictions. Top/marker findings are textual guidance, not
syntax/elaboration/simulation or assertion-correctness proof. No HDL execution
permission, include support, multiple-file scope or configurable top is added.

Selected configurations own an ordinary runs subfolder. ARM handoffs use the
project's existing runs subfolder. History/summary/comparison/verification/export
retain existing bounded read-only interfaces and legacy archive support. New
results do not rewrite older ones. Changing the execution form does not relabel
already displayed evidence. There is no recursive cross-project index or automatic
association of arbitrarily moved archives.

## Qualification and limitations

Windows x64 and Ubuntu x64 remain example-qualified for supported native runtime
identities; runtime availability is separate from qualification. macOS is a
preview and unified native execution remains blocked by RLIMIT_AS admission.
Linux namespace/network-boundary qualification and mandatory distribution release
evidence remain separate blockers. No hostile-input isolation, physical MCU/FPGA
support, signing/notarization or public release approval is established here.

Coverage includes pure storage/preflight/dispatch tests, real supervised worker
transport, Qt context/consent/history tests and native custom fixtures for all
three backends in the existing Windows/Ubuntu unified workflow. Synthetic dispatch
seams are labelled synthetic; only successful native runs establish their actual
execution evidence. The original Windows process-handle identity assertion is
shared by both ARM desktop tests; numeric PID/259 alone is not termination proof.

Next: Batch 18 should link execution stages, retained receipts/logs and bounded
artifact inspection, then compare supported input/configuration/runtime identities.
