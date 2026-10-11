# Product foundation: Batch 1

FIRMAVEX Batch 1 provides a command-line frontend and a supervised execution
worker that can later be used by a PySide6 application. It does not provide the
complete desktop interface, native installers, runtime packs, or arbitrary
firmware compatibility.

The product example and outputs are independent of the frozen research corpus
and campaign. None of the commands below launches the research evaluation.

## Installation and one-command Ubuntu/WSL workflow

Python 3.11 or newer is required. Runtime execution requires `qemu-system-arm`
with `mps2-an385` and ARM-capable GDB with embedded Python and `hashlib`.
`arm-none-eabi-gcc` is needed to build the example, but not to execute a compatible
existing ELF. Native tool binaries are not bundled in Batch 1.

The product discovers `arm-none-eabi-gdb`, then `gdb-multiarch`; a compatibility
symlink is unnecessary for the product CLI. The research suite retains its
existing executable-name requirements.

After the development branch is available on GitHub, paste this block into
Ubuntu or WSL2. It installs system dependencies, clones into a fresh directory,
uses a separate virtual environment, and creates new example results under your
home directory. It never resets an existing checkout or overwrites an archive.

```bash
bash <<'FIRMAVEX_BATCH1'
set -euo pipefail
sudo apt update
sudo apt install --no-install-recommends -y \
  git python3 python3-venv python3-pip gcc-arm-none-eabi qemu-system-arm gdb-multiarch

FIRMAVEX_BATCH_ROOT=$(mktemp -d "$HOME/firmavex-desktop-batch1-XXXXXXXX")
git clone --branch product/desktop-batch1 --single-branch \
  https://github.com/mtalhak003/FIRMAVEX.git "$FIRMAVEX_BATCH_ROOT/source"
cd "$FIRMAVEX_BATCH_ROOT/source"
python3 -m venv "$FIRMAVEX_BATCH_ROOT/venv"
source "$FIRMAVEX_BATCH_ROOT/venv/bin/activate"
python -m pip install '.[dev]'
firmavex doctor
python -m pytest -q tests/product
firmavex demo --output-dir "$FIRMAVEX_BATCH_ROOT/demo"
firmavex inspect "$FIRMAVEX_BATCH_ROOT/demo/search"
printf '\nSource: %s\nResults: %s\n' \
  "$FIRMAVEX_BATCH_ROOT/source" "$FIRMAVEX_BATCH_ROOT/demo"
FIRMAVEX_BATCH1
```

The example's defined failure is input `[2, 1]`. Enumerative search visits it
at charged attempt 10 in the two-coordinate domain `0..3`. The demonstration
retains the exact vector, separately replays it three times, and exports its
recorded evidence and report. These are observations of a defined synthetic
condition in the declared emulator, not a security assessment.

## Supported firmware contract

Batch 1 accepts an ELF only after checking its format, ARMv7-M attributes,
load layout, reset vectors, symbols, and debug types. The supported profile is:

- ELF32, little-endian, ARM Cortex-M3 / ARMv7-M, linked for `mps2-an385`.
- Executable flash at `0x00000000..0x003fffff`, RAM at
  `0x20000000..0x203fffff`, compatible load segments and reset behavior.
- A valid Thumb reset entry and aligned initial stack pointer.
- Debug information describing unsigned 32-bit input and failure bindings.
- Writable, non-overlapping inputs: scalar C identifiers or one-dimensional
  array elements, such as `inputs[0]`.
- Distinct, plain C functions marking input readiness and completion.
- All inputs share one inclusive uint32 range, as required by the existing
  public input-space model.
- Failure observation is equality between the declared failure binding and
  the configured uint32 failure value at the completion point.

ELF inspection cannot prove peripheral or guest-runtime compatibility. Firmware
for a particular vendor MCU may pass some format checks but still require
unsupported peripherals or addresses. Raw BIN, stripped ELF without the required
debug types, other CPU families, arbitrary debugger expressions, hardware probes,
interactive peripheral input, and automatic vulnerability classification are
unsupported.

The product runtime uses this sequence for every fresh observation:

1. Start QEMU stopped and connect GDB using a selected localhost port.
2. Execute startup until the required input-ready function breakpoint.
3. Inject inputs and confirm their uint32 readback.
4. Collect the configured bounded runtime signature and require completion.
5. Read the failure value at completion.
6. Clean up and reap owned processes before accepting the observation.

The product example deliberately clears inputs during initialization. This
exercises injection after startup. The existing research monitor and signature
record semantics remain separate and unchanged.

## Project configuration

`build-example` writes a complete `project.json`. This minimal user project uses
the same supported profile:

```json
{
  "schema_version": 1,
  "firmware": "my-firmware.elf",
  "input_symbols": ["inputs[0]", "inputs[1]"],
  "input_min": 0,
  "input_max": 15,
  "ready_breakpoint": "input_ready",
  "completion_breakpoint": "test_complete",
  "failure_symbol": "failure_status",
  "failure_value": 1,
  "execution_budget": 64,
  "strategy": "enumerative",
  "seed": null,
  "timeout_seconds": 10.0,
  "startup_timeout_seconds": 5.0,
  "collect_signature": true,
  "guided_archive_size": 32,
  "guided_mutation_attempts": 8,
  "qemu": null,
  "gdb": null,
  "compiler": null
}
```

Relative firmware paths resolve from the configuration file's directory.
Input order is the order in `input_symbols`. Configuration rejects unknown and
duplicate fields, invalid types, duplicate bindings, and out-of-bounds values.
Ready and completion breakpoints are function names, not source-line expressions
or arbitrary GDB commands.

`strategy` is `enumerative`, `random`, or `guided`. Enumerative requires
`seed: null`; random and guided require an explicit integer seed. Guided uses
runtime feedback and requires `collect_signature: true`; it is not an AI model.
Signature collection introduces debugger-stepping overhead. Turning it off for
enumerative/random affects runtime cost and removes signature collection; it
does not change their proposal order.

Budgets range from 1 to 1,000,000 charged attempts. Timeout settings must be
finite positive numbers no greater than 3,600 seconds. Reproduction is separately
bounded to 1–100 attempts. Executable overrides select actual file paths;
tool identity and capability checks still apply.
Use absolute executable paths for overrides; relative overrides otherwise
depend on the worker's current directory. The generated example records the
selected compiler's resolved path.

## Commands

```bash
# Probe tools; do not run firmware.
firmavex doctor

# Validate format, bindings, settings, and tools; do not run firmware.
firmavex validate /path/to/project.json

# Build the independent example into a new directory; do not run firmware.
firmavex build-example --output-dir "$HOME/firmavex-example-build"

# Execute search; this launches real QEMU/GDB observations.
firmavex run /path/to/project.json --output-dir "$HOME/firmavex-run-001"

# Inspect existing records without execution or archive mutation.
firmavex inspect "$HOME/firmavex-run-001"

# Replay a retained trigger into a separate new directory.
firmavex reproduce "$HOME/firmavex-run-001" \
  --output-dir "$HOME/firmavex-replay-001" --attempts 3

# Export retained records/report into a new directory; do not execute firmware.
firmavex export "$HOME/firmavex-run-001" \
  --output-dir "$HOME/firmavex-export-001"
```

Commands return JSON on standard output. Execution progress appears as versioned
events on standard error. Exit code 0 means the requested operation completed;
an observation can complete without finding the declared failure. Structured
errors are nonzero; cancellation uses exit code 130. An inspection command's
success means inspection completed, not that the inspected run found a failure
or is execution-verified.

Worker/CLI diagnostics are previews: string stdout, stderr, and diagnostic fields
are bounded to 4,096 UTF-8 bytes, with explicit truncation metadata and the
original field's hash/length. Full saved administrative records are unchanged.
Counts and triggering vectors are never shortened to fit transport. If a record
still exceeds the 1 MiB message limit, the worker returns `protocol_error` and the
run-directory reference rather than an incomplete successful result. Inspect the
saved archive directly for full diagnostics.

`firmavex worker` exposes the internal JSON-line protocol for a future desktop
supervisor. It is not required for normal command-line use. The worker admits
one active job, enforces request identities and event sequence numbers, and
supports cooperative cancellation. No worker retry automatically repeats a job.

## Results, evidence, and classifications

Each run owns a fresh directory containing a SQLite archive, immutable registered
artifacts, imported firmware, resolved project configuration, per-attempt records,
and terminal `result.json`/`report.md`. A live writer prevents simultaneous
recovery. Read-only inspection does not turn a running record into completion.

Results retain exact triggering input vectors, tool executable hashes/versions,
firmware identity, process and debugger receipts, completion/input readback,
signatures where enabled, cleanup status, and authoritative evaluator counters.
Injected unit-test executors are explicitly `synthetic_test`; they cannot be
promoted to real-firmware reproduction by selecting a label.

| Outcome or state | Interpretation |
| --- | --- |
| `configured_failure_observed` | A completed observation matched the declared condition. |
| `reproduced_in_emulator` | Saved inputs matched the condition in every requested completed replay. |
| `reproduction_inconsistent` | Completed replays did not all match the condition. |
| `no_failure_within_budget` | No declared condition was observed within the charged budget. |
| `domain_exhausted` | The strategy exhausted the finite domain. |
| `infrastructure_failure` | Execution, observation, evidence, or cleanup failed; this is not a safe result. |
| `cancelled` / `interrupted` | Work ended without a normal completion guarantee. |
| `invalid_output` | The strategy returned an invalid candidate. |

Infrastructure/observation failure aborts further dispatch. A later observation
cannot repair an earlier infrastructure failure. Reproduction has a separate
budget/ledger and retains its relationship to the original trigger. An
infrastructure-failed replay is indeterminate; it does not disprove a recorded
discovery.

Errors identify categories such as `invalid_configuration`, `unsupported_firmware`,
`missing_dependency`, `dependency_probe_failed`, `persistence_error`,
`evidence_incomplete`, `protocol_error`, `worker_interrupted`, `cleanup_failure`,
and `unsupported_platform`. Detailed debugger diagnostics belong to the
administrative records; they are not search-strategy feedback.

Charged evaluator attempts must not be called independently verified physical
firmware executions. A completed QEMU/GDB receipt is evidence for the declared
emulator environment; it is not hardware validation. Matching signatures do not
establish coverage or full execution-path identity. Consistency checks detect
observable changes, without creating an atomic filesystem snapshot or defending
against every adversarial race.

## Cancellation, explicit recovery, and restart

Use Ctrl+C for cooperative cancellation and wait for cleanup. The worker does
not claim an active abandoned job completed when standard input closes. Linux
supervision also owns a process group so unexpected worker loss can terminate
remaining owned descendants. It does not kill unrelated QEMU/GDB processes.

After an unexpected interruption:

```bash
firmavex inspect "$HOME/firmavex-run-001"
# If the writer is gone and the archive is unfinished:
firmavex recover "$HOME/firmavex-run-001"
# Only after deciding to repeat abandoned search work:
firmavex restart "$HOME/firmavex-run-001" \
  --output-dir "$HOME/firmavex-restarted-001"
```

`recover` explicitly marks an abandoned archive interrupted and retains unknown
accounting where necessary. It dispatches no firmware. It refuses a live owner
and does not rerun a completed job.

`restart` creates a new full search with the original settings and a parent link.
It does **not** continue at the next candidate: strategy state checkpointing is
not implemented. Repeated/abandoned physical work must not be hidden or inferred
from evaluator counters. Completed jobs are not automatically rerun.

SQLite transactions and artifact files are not one atomic snapshot. Interrupted
artifact registration can leave an incomplete inventory, which inspection must
disclose rather than treating as verified evidence. Recovery is intended for
owned local filesystems; network/shared-filesystem durability is not qualified.

If a receipt write fails but the terminal evaluator result can still be saved,
inspection reports `incomplete_receipts`, the exact number of missing receipts,
and `execution_verification: failed`. The retained evaluator counters and any
known triggering vector remain administrative information; missing receipts are
never reconstructed. Explicit recovery leaves this failed/cancelled result
unchanged, and an authorized restart creates a separate full search. A result
artifact written before the terminal database commit is retained as an
`uncommitted_result_artifact`; recovery reports unknown accounting rather than
promoting that artifact to a completed run.

## Publication and privacy

Keep product results outside research archives and the repository. Exported
records are private administrative material by default. Review absolute paths,
filenames, input values, supplied settings, and stdout/stderr before publication.
Hashes establish retained byte identities, not permission to publish proprietary
firmware or proof of every execution claim.

Step 19 research results remain preliminary and journal-derived, with
`execution_verification = failed` and missing supplementary evidence at zero-based
position 7. This example neither repairs that evidence nor changes frozen
research protocols or outcomes.

## Platform status and tests

The Batch 1 Linux execution checks used ARM GCC 14.2.1, QEMU 10.0.13, and GDB
16.3. Six actual-firmware runtime cases passed: safe/triggering inputs with
signature collection enabled and disabled, missing completion despite a trigger,
and cancellation with a charged/aborted evaluator attempt. Cleanup receipts
confirmed owned processes were reaped in those cases. These are bounded
integration checks, not a long-running stability or cross-platform campaign.

- **Linux:** actual QEMU/GDB firmware execution is tested in the development
  environment. This does not certify every Linux distribution or tool version.
- **Ubuntu WSL2:** commands above use Linux tooling; native WSL execution has not
  been performed in this cloud batch.
- **Windows:** native firmware dispatch is explicitly blocked until Job Object
  or equivalent descendant supervision is implemented and tested. Pure Python
  tests and a future CI job do not remove this gate.
- **macOS:** native execution, packaged runtime compatibility, signing, and
  installation are unverified. POSIX abstractions alone do not establish support.

The workflow in `.github/workflows/product.yml` proposes unit jobs on Windows,
macOS, and Linux and real product integration on Ubuntu. Its presence is not a
claim that remote jobs have run. Linux-only `/proc` resource tests are explicitly
scoped to Linux. Real firmware tests must use actual compiler/QEMU/GDB tools;
synthetic observations are never substituted as real measurements.

```bash
# Product tests with the required real tools available:
python -m pytest -q tests/product
# Existing research regression suite; also needs native GCC and arm-none-eabi-gdb:
python -m pytest -q
git diff --check
```

## Next batch

Batch 2 should add the PySide6 workflow over these services, dependency setup and
repair, Windows process-tree ownership, native macOS qualification, installer
testing, and usability evaluation. BIN ingestion, hardware support, process
sandboxing, and durable partial-search continuation require separate designs and
must not be presented as completed features.
