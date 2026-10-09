# Experiment-boundary campaign recovery

Step 18C adds an opt-in durable runner around the existing experiment path.
It does not alter the frozen controlled protocol, strategies, guest execution,
feedback, execution budgets, evaluator accounting, or official result schemas.
No controlled campaign was run to develop this feature.

## Journal and lifecycle

`DurableCampaignRunner` executes a canonical `EvaluationProtocol` in its retained
expansion order using `ExperimentRunner`. Its administrator journal is separate
from official `ExperimentRecord` and `CampaignResult` serialization. Store the
journal outside the Git checkout so checkpoint writes do not change captured
repository provenance.

The version-1 snapshot envelope contains `schema_version`, `payload_sha256`, and
`payload`. The payload has kind `firmavex_campaign_journal` and retains:

- The complete frozen protocol and ordered experiment expansion, with a plan
  fingerprint, benchmark IDs, strategy configuration and seeds, and budgets.
- A stable administrative execution context and its fingerprint, plus the
  public input-space declaration.
- An ordered completed prefix, with each unchanged official experiment record.
- An ordered attempt history, interruption diagnostics, and available partial
  evaluator accounting.
- Campaign state (`planned`, `running`, `interrupted`, or `completed`), the last
  interruption point, and the explicit experiment-boundary restart policy.
- Administrative durability metadata retaining whether unsupported directory
  synchronization has been observed.

Fingerprints are SHA-256 of `b"firmavex-journal-v1\0"` followed by UTF-8 canonical
JSON: sorted keys, compact separators, and no nonfinite numbers. An experiment
ID derives from the full plan fingerprint and zero-based plan position. An
attempt ID additionally identifies its one-based attempt number. Names or seeds
alone cannot identify an experiment. Canonical serialization is deterministic;
the checksum detects damage, not malicious rewriting by somebody able to edit
the archive.

The runner writes the initial plan before dispatch, and writes a `running`
attempt before each experiment. It validates and durably checkpoints a completed
record before admitting the next experiment. A completed infrastructure-aborted
experiment remains an authoritative completed record with its original failure
classification; the campaign continues with independent experiments. Invalid
strategy output and censored non-discovery classifications also remain intact.
Campaign completion requires the entire validated prefix. Incomplete data never
produces a manufactured completed `CampaignResult`.

## Persistence and resource limits

Every snapshot is written completely to a temporary file in the journal's
directory. The writer flushes and `fsync`s the file, replaces the journal using
`os.replace`, and then synchronizes the containing directory where supported.
A failure before replacement preserves the previous valid snapshot and attempts
to remove the temporary file. A failure after replacement can leave the new
pathname visible even though crash durability is uncertain; it propagates and
the runner inspects the actual on-disk snapshot rather than trusting an older
in-memory copy. If directory synchronization is unsupported, the store exposes
`directory_sync_supported=False` and retains
`durability.directory_sync_unsupported_observed=True` in the journal and
recovery-history export instead of claiming full durability. A newly observed
unsupported synchronization causes at most one additional replacement to retain
that status; a failure of that write propagates. The cumulative flag is not
cleared by later writes. `False` means no unsupported observation is retained,
not that directory synchronization or crash durability is guaranteed.

A POSIX nonblocking advisory lock on the journal's `.lock` sibling provides a
single cooperative writer. Another runner using that lock is rejected.
Non-POSIX systems without `fcntl` fail clearly. Locks do not prevent somebody
from editing, unlinking, or copying the journal outside the runner, and the
persistent lock file is an administrative artifact rather than a result.

Atomic replacement depends on local filesystem support and a temporary file in
the same directory. File and directory synchronization cannot promise survival
against every filesystem, remote-storage, hardware, or power-loss behavior.
The lock helper may create missing parent directories. Only the journal's own
directory is synchronized after replacement; newly created ancestor directory
entries are not synchronized. For a long campaign, provision the archive
directory beforehand and ensure its ancestor entries are durably established.
The implementation does not lock the Git repository or firmware inputs. Keep
the plan, executable images, source archive, and tool environment fixed during
the campaign, use a reliable local filesystem, and archive independent backups.

## Recovery and interrupted attempts

Use the same journal path, protocol, registry, and a fresh compatible context
provider. Recovery rejects invalid JSON, duplicate keys, damaged checksums,
unknown schema versions, plan or ordering changes, duplicate/skipped completed
entries, invalid results, changed public input space, and incompatible execution
context. It does not repair or silently skip bad recovery data.

An ordinary restart of a completed boundary uses `resume=True`; completed
experiments are validated and loaded without executing them again. An existing
journal is never overwritten as a new campaign, and recovery cannot create a
missing journal.

An unfinished experiment requires both `resume=True` and
`restart_interrupted=True`. It restarts from its beginning with a fresh session
and a new attempt ID linked by `restart_of` to the interrupted attempt. A journal
left in `running` state after abrupt process loss is explicitly classified as a
lost interrupted attempt when this policy is applied. It is not a mid-experiment
resume. A `running` checkpoint cannot reveal how many guest executions occurred
since that checkpoint; unavailable accounting remains unavailable.

When interruption is observed, the runner preserves the exact experiment
position, the exception type and message, and available administrator-owned
partial evaluator counters and diagnostics. Capture failures are recorded
separately. Each attempt establishes fresh evaluator ownership before dispatch:
an interruption before evaluator creation cannot copy a previous attempt's
counters or diagnostics, including when restarting the same experiment. In
that case accounting remains unknown, rather than being fabricated as zero.
`KeyboardInterrupt`, `SystemExit`, cancellation, and ordinary errors propagate;
a failure while writing interruption details does not replace the original
exception. Runtime cleanup still attempts to terminate and reap QEMU and close
its resources. If cleanup also fails while an exception is propagating, the
original exception remains authoritative and the secondary failure is retained
as an exception note. Each journal close scope also tracks only its own
propagating exception; a caller's already-handled interruption cannot hide a new
cleanup failure. New cleanup cancellation takes precedence over an ordinary
error, retaining that error as its cause. Uncatchable termination may leave only
the previously durable `running` checkpoint.

Interrupted-attempt counts are neither added to nor removed from the restarted
experiment's authoritative execution count. For example, an interrupted attempt
with three charged executions followed by a successful restart with five
executions yields a completed experiment record containing five. The earlier
three remain only in that interrupted attempt's partial record. Total physical
work can exceed the planned completed-run budgets after explicit restarts; the
journal makes that additional work distinguishable, and never invents missing
measurements or reconstructed wall time.

## Provenance requirements

The constructor requires an administrator `context_provider(protocol)` callback.
It is invoked afresh before journal creation or recovery. Prefer
`capture_recovery_context(protocol, **manifest_kwargs)`, which calls the existing
Step 18B `capture_campaign_manifest` and projects its observed evidence. A
caller-created dictionary, preset name, or quality label alone does not establish
that a particular firmware image was executed. The callback is a trusted
administrative extension point, not a strategy-facing API or an attestation
boundary.

The projection retains actual Git revision, dirty status, tracked/index diff
digests, nonignored untracked-file identities, absolute repository location,
selected tool paths and version-probe status, Python version, host information,
ordered source and ELF paths/digests/sizes, supplied build metadata, and the
declared preset name. Capture timestamps and volatile inode/mtime/ctime metadata
are excluded from recovery equality; unchanged bytes and environment can be
recaptured later. Ordered artifact paths and all retained context values must
otherwise match exactly. A migrated machine or changed tool path is therefore
not silently treated as compatible.

Successful capture must carry `status="stable_observed"` and `atomic=False`.
Observable changes during Step 18B hashing or Git capture reject admission. Equal
endpoint checks still do not create an atomic snapshot or detect every
change-and-restore race. Sources and firmware can change after capture. The
administrator must ensure the supplied images and source/build declarations
refer to the actual registry images used by the runner and keep them stable.
Before a comparative campaign, independently compare the supplied image
mapping with the actual executing registry images, including resolved paths and
SHA-256 digests. A matching recovery context does not perform that binding check
or attest which image the executor loaded. Archive the check with the campaign's
administrative evidence.
Supplied build metadata retains `administrator_supplied_not_verified`; preset
names retain `administrator_declared_not_verified`. Neither is upgraded to a
verified claim. Tool unavailability and version-probe errors remain explicit
evidence; context validation does not relabel these as successful tools or as a
real-firmware measurement. Verify required compiler, QEMU, and GDB availability
before a real campaign.

The provider can be arranged as follows, after firmware has already been built
with the existing build framework and the administrator has collected exact
artifact paths and build commands:

```python
from src.firmavex.protocols.durable import DurableCampaignRunner
from src.firmavex.protocols.recovery_context import capture_recovery_context

def context_provider(protocol):
    return capture_recovery_context(protocol, **manifest_kwargs)

runner = DurableCampaignRunner(registry, "/private/campaign/journal.json", context_provider)
result = runner.run(protocol)  # New journal, frozen experiment order.
# On a later invocation with independently recaptured compatible context:
# result = runner.run(protocol, resume=True)
# A deliberate restart of an unfinished experiment additionally requires:
# result = runner.run(protocol, resume=True, restart_interrupted=True)
```

The manifest arguments are the unchanged Step 18B arguments: repository,
administrator-declared preset name, complete benchmark-to-image/source/build
maps, and an actual campaign start timestamp. The journal records checkpoints;
the provenance sidecar remains a separate administrative archive. Recovery data,
partition labels, diagnostics, and artifact identities never reach strategy
callbacks.

## Operational and publication guidance

Before a long campaign, verify the frozen plan, tool availability, stable image
digests, available disk space, local-directory synchronization support, private
archive permissions, and the explicit restart policy. Rehearse recovery with
small deterministic tests. Back up the journal and retain the original source,
ELF, tool/build evidence, and protocol. Do not remove a completed entry or edit a
seed or budget to make a damaged snapshot appear recoverable. Preserve a failed
journal for diagnosis and begin a separately declared campaign when compatibility
cannot be established.

Journals and raw provenance sidecars are private administrative archives. They
can contain absolute paths, filenames, host information, supplied metadata, and
raw debugger or interruption diagnostics. Review and redact these before public
research publication. Preserve private originals and disclose redactions;
published identifiers and digests can remain useful without exposing host paths.
Existing official result JSON is unchanged and does not inherit this private
administrative data.

Comparative research results must be accompanied by the deterministic
administrative recovery-history artifact derived from the validated journal.
`export_recovery_history(payload, protocol, context, space)` in
`firmavex.protocols.journal` validates the complete journal before returning a
detached JSON-compatible record with kind `firmavex_campaign_recovery_history`.
It retains the journal, plan, context, and completed-record digests, campaign
state, ordered attempt IDs and restart links, available accounting, interruption
details, retained durability limitations, and final completion status. The export
adds no capture timestamps, so the same validated journal produces the same
canonical JSON.

Its summary distinguishes recorded experiment attempts from firmware execution
counts. Known completed and abandoned firmware work are reported separately;
unknown partial accounting remains explicit and prevents an apparently exact
physical-execution total: `physical_firmware_executions` is `None` whenever an
attempt's accounting is unknown, while `known_physical_firmware_executions`
retains only observed counts. An interruption at an experiment boundary remains
in the history even when no unfinished firmware attempt exists. This is an
administrator artifact, not a strategy-facing record or an alternative evaluator
ledger.

Link the official results, recovery history, and archived plan using their
identifiers and digests. Preserve a private original and provide a reviewed or
redacted research artifact that still identifies interrupted and restarted
attempts, additional recovery attempts, unknown partial accounting, and final
completion status. An unchanged official `CampaignResult` alone cannot reveal
whether its completed experiments needed recovery.

Predeclare the restart policy and result-eligibility rules before execution,
including treatment of interrupted attempts and missing accounting. Completed
run metrics exclude abandoned-attempt work: they describe only the completed
experiment's authoritative ledger. Disclose that limitation beside metrics and
report known abandoned work separately without treating unknown counts as zero.
Selective restarts based on observations or apparent outcomes can introduce
selection and survivorship bias and additional execution opportunity. The
recovery feature does not supply a comparative retry policy or justify excluding
unsuccessful histories.

The Step 18A enumerative floor effect remains unchanged: the 256-execution preset
has zero enumerative discoveries across the eight current fixtures, whose
earliest enumerative discovery is execution 3,328. Recovery adds reliability,
not evidence of search effectiveness or a remedy for that experimental limit.
No performance campaign, runtime optimization, or search comparison is part of
this milestone.

## Development validation

The starting checkpoint was `24c53e2a917548b3bbb3b82191783adcc7fe1325`, with a
clean tree and **978 existing tests passing** before implementation. Before
review hardening, the four new focused suites passed **280 tests in 5.38 seconds**;
the complete `python -m pytest -q` passed **1,258 tests in 160.53 seconds**, without
failures or skips. New campaign tests use small explicitly synthetic sessions and
deterministic failure injection. They are not controlled-campaign measurements
or evidence of long-running crash reliability.

After integrity hardening, the eight targeted journal, codec, durable-runner,
context, monitor, runtime-integrity, and signature suites passed **514 tests in
9.21 seconds**. The final complete `python -m pytest -q` passed **1,365 tests in
161.56 seconds**, with no failures or skips. Regressions include repeated
interruption/restart ownership, valid and contradictory journal states,
deterministic recovery-history disclosure, retained directory-sync limitations,
and cancellation during runtime and journal cleanup. No controlled campaign or
new real-firmware pilot was run.
