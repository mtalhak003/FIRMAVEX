# Batch 18: failure diagnosis and comparison

The desktop Summary now adds the same read-only failure diagnosis for ARM,
RISC-V and Verilog. It labels recorded firmware/test failures, infrastructure
failures, cancellations, rejected input, invalid output and unavailable evidence
separately. It shows retained stage information, outcome, attempt/run identity,
expected/observed fields where present, sanitized retained log excerpts and an
investigation suggestion. A retained compiler phase is not proof of successful
compilation. Missing expected behavior, execution stages or logs remain
unavailable; no verdict is reconstructed from log text. Existing compiler and
ARM reproduction summaries remain available. Standalone ARM reports also include
the diagnosis. The original result and evidence are unchanged.

Use **Inspect diagnostic file…** in the unified desktop to select a retained
`.log`, `.txt`, `.out`, `.err` or `.vcd` file. This does not dispatch a worker or
execute a file. The established regular-file reader rejects symlinks, reparse
points, hardlinked files, unsafe paths, observable changes and files exceeding
1 MiB. Logs show at most 8,192 decoded characters plus a truncation notice;
nonprinting characters are replaced, with newlines and tabs retained. Inline
diagnosis streams are limited to 1,200 characters each. File selection does not
prove that the file belongs to a particular run, or verify its authenticity.

VCD inspection is metadata only: signal references, timescale and first/last
monotonic timestamps, with duration in timestamp units. Limits are 1 MiB, 20,000
lines, 128 signals, 512 characters per signal declaration, 160 displayed
characters per signal and 8,192 total displayed characters plus a truncation
notice. Missing metadata remains unavailable. Malformed or unsupported headers,
signal declarations and timestamps are rejected; unsupported VCD syntax may be
rejected. Signal scopes are not resolved, so repeated leaf names may appear.
There is no waveform rendering, signal-value validation, execution, or claim of
full VCD conformance. Oversized files are rejected rather than partially parsed.

The existing **Compare saved runs** interface now compares the metadata supported
by each archive: declared project/configuration, declared source path, input
SHA-256, backend/profile, execution limits, retained tool/runtime identity,
recorded outcome, failure classification and replay metadata, alongside the
existing measurement/cleanup/time/input fields. States are `same`, `different`,
`unavailable` and `not comparable`; backend-specific fields across different
backends are not comparable. Older worker comparison labels remain renderable.
A declared source path is only a reference, not a project or input content
identity. Empty, malformed or excessive optional comparison values are
unavailable (maximum depth 5, 128 nodes, 32 children per container, 4,096
characters per string and a 16,384-character string budget). Older archives are
not migrated. Named configuration IDs and host environment fields not persisted
by the run format cannot be recovered from temporary input paths. Standalone
ARM archives reuse existing metadata, configuration and artifact verification.

Equal hashes do not authenticate an execution. Integrity checks retain their
existing explicit scope; comparison is sequential, not an atomic snapshot.
Tool/runtime or profile differences are displayed only where recorded. No host
environment is inferred from the machine currently reviewing the archive.

ARM replay repeats saved inputs under the supported QEMU/GDB Cortex-M3 MPS2
configuration. Recorded completed and matching observations support the existing
reproduction result under its firmware, configuration, runtime and environment
assumptions. RISC-V replay reruns the retained RV32 firmware and values;
Verilog replay reruns the retained constrained Icarus testbench. Those two paths
do not establish the ARM repeated-reproduction verdict. None establishes
hardware equivalence, complete reproducibility or physical FPGA validation.

Execution isolation, resource admission, consent, cancellation, cleanup,
immutable evidence and distribution/release gates are unchanged. macOS
RLIMIT_AS admission, Linux AppArmor/network qualification and mandatory release
evidence remain separate qualification concerns; this batch approves no release.

## Local validation

On Linux, the combined available product and desktop regression run completed
with **1,153 passed, 13 skipped, zero failures** in 237.90 seconds. The final
focused diagnosis/comparison/services/compiler/reproduction and Qt presentation
run completed with **266 passed**. Regression execution required running outside
the Codex shell sandbox: sandboxed runs denied local sockets and caused real ARM
and isolation-probe failures. One old comparison-label assertion found during
the first run was updated to the new vocabulary. No execution policy was relaxed.
The final focused run additionally checks bounded optional comparison metadata,
configuration null/timeout fields and diagnostic Qt presentation.

`git diff --check` passed. Review covered bounded reads/parsing/display,
sanitization, cancellation propagation, legacy archive behavior, absent metadata
and evidence immutability. The existing macOS memory-admission, Linux isolation
qualification and mandatory distribution evidence gates are not waived by these
local results. CI results must be checked for the committed SHA separately.

Proposed Batch 19: versioned, bounded provenance capture for future runs (named
project/configuration revision IDs, declared environment assumptions and explicit
rerun parent identity), with compatibility tests. Older archives should continue
to show unavailable fields rather than receive inferred provenance.
