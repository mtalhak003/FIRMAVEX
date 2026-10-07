# Step 17A: runtime-derived execution signature

## Implemented

Step 17A adds one optional, immutable execution signature to the existing
strategy feedback. It provides a compact observation of actual Cortex-M
execution without giving a strategy raw debugger information. It adds no guided
strategy, AI/ML implementation, new benchmark family, or search registration.

The public records are:

```python
@dataclass(frozen=True)
class ExecutionSignature:
    digest: str
    truncated: bool = False

@dataclass(frozen=True)
class TrialFeedback:
    status: TrialStatus
    execution_index: int | None
    budget_remaining: int
    execution_signature: ExecutionSignature | None = None
```

The digest is exactly 64 lowercase hexadecimal characters representing a
SHA-256 value. `truncated` must be an exact boolean. Validation accepts the
canonical signature record rather than arbitrary objects carrying additional
state. The default `None` preserves helpers and synthetic executors that
construct feedback using the original three fields. A signature belongs only
to successful `safe` or `triggered` executions; failure, rejection, exhausted
budget, and already-aborted feedback contain no signature.

### Collection and canonicalization

The existing fresh-QEMU/GDB observation path remains responsible for input
injection and reading the failure symbol at its configured completion
breakpoint. Signature collection uses GDB's embedded Python support to
single-step guest instructions. It needs no additional benchmark symbols,
source annotations, predicate inspection, oracle, or ground truth.

After input injection, the collector samples the initially halted guest program
counter and subsequent instruction-stop PCs in order. Repeated PCs are retained
in the hash input. Collection stops at the existing completion breakpoint; the
completion PC itself is excluded. Stop detection requires a GDB
`BreakpointEvent` containing the exact configured completion breakpoint object,
rather than assuming its address is the function's entry address.

Version 1 starts with the exact bytes
`b"FIRMAVEX:guest-pc-sha256:v1\x00"`, followed by each PC encoded as an unsigned
32-bit integer in exactly four big-endian bytes. A terminal byte is appended:
`0x00` for an untruncated sequence and `0x01` for a truncated sequence.
SHA-256 is updated incrementally, and the public digest is its lowercase
hexadecimal representation. Python's process-dependent `hash()` is not used.
No trace count or PC is included as a public field.

The fixed collection bound is 4,096 PC samples per execution. If the bound is
reached before completion, collection stops and GDB continues normally to the
same completion breakpoint. Such a successful observation returns
`truncated=True`. Reaching the bound does not consume a second firmware
execution or create a second observation. Continuation must still complete
successfully before the signature can be published.

Registered corpus observations request collection for every execution.
Legacy direct calls to `observe_symbol()` retain their default behavior with
collection disabled. GDB Python support and its `hashlib` module are required
when collection is requested; unavailable support is an infrastructure failure,
not an automatic fallback to an apparently valid uninstrumented observation.

### Information boundary and accounting

Only the canonical digest and truncation flag reach strategy callbacks. Raw
PCs, resolved breakpoint locations, ELF/source paths, symbol names, GDB/QEMU
output, partition labels, and administrator diagnostics remain internal. The
signature is computed from runtime instruction locations. No candidate values,
failure flag, predicate source/constants, expected triggers, or oracle data are
included in the hash input. The existing
failure-symbol value determines the trial outcome independently of the hash.

Collection errors, missing or malformed required signatures, unexpected target
signals/exits, and timeouts invalidate the observation. A partially collected
hash is not published after failure. The evaluator charges the already-admitted
execution once, records an infrastructure failure, and aborts the session.
Subsequent requests do not dispatch firmware. Administrator-owned diagnostics
retain useful error text without exposing it through feedback.

`KeyboardInterrupt` and `SystemExit` retain their existing semantics: admitted
attempts are charged and recorded as aborted before the original exception is
re-raised. The signature collector does not introduce separate counters or
alter the execution-budget policy.

Enumerative and random baselines continue to ignore feedback in `observe()`.
Their proposal ordering, replay, seeds, uniqueness, exhaustion, and metadata
remain unchanged. The frozen standard baseline protocol and seed schedule are
unchanged. Existing experiment records retain their aggregate schema; they do
not start persisting raw traces or administrator diagnostics.

## Tested

The focused Step 17A suite passed: 46 tests in `test_execution_signature.py`
and 39 tests in `test_monitor_signature.py`, for 85 passed. These cover public
record immutability and validation, malformed/absent signals, diagnostics
separation, accounting, forged callback returns, baseline replay, and existing
serialization. Collector unit tests run the generated GDB Python script against
controlled GDB events to check exact hash input, ordering, cap handling, and
failure behavior. Timeout tests verify that available text or byte output stays
in administrator diagnostics rather than entering feedback.

`test_real_cortex_m_signature_replay_and_safe_behavior_difference_reaches_strategy`
performed exactly three fresh Cortex-M/QEMU/GDB executions through the registry,
evaluator, and strategy callback. It submitted the same safe candidate twice,
then a second safe candidate following a different controlled branch. The first
two signatures were equal and the third differed. All three were untruncated;
attempted and successful execution counts were both three, with zero
infrastructure failures. The synthetic instrumentation fixture is test-only and
is not part of the research corpus, oracle, or evaluation split. These results
establish replay and differentiation for that controlled fixture, not a benchmark
comparison or a discovery improvement.

The implementation report records broader regression and complete-suite results
after final validation. No performance campaign was run for this milestone.

## Planned

A future strategy may use the public signature through the existing
`SearchStrategy` lifecycle. Step 17A implements only the runtime signal; no
guided/heuristic strategy, AI model, final experiment comparison, or new
protocol participant is implemented here. Separate review is required before
adding a method or interpreting this signal as evidence of search effectiveness.

## Limitations

- The signature fingerprints a bounded ordered sequence of instruction-stop
  PCs. It is not a coverage metric, formal path identity, state digest, source
  distance, or estimate of proximity to failure.
- Identical control flow with different data can produce the same signature.
  Truncated executions can differ after the prefix and still share a digest.
  SHA-256 collisions are also possible; uniqueness is not guaranteed.
- Deterministic replay is expected for the same firmware image, input, build,
  and equivalent QEMU/GDB environment. Changed compiler options, instruction
  layout, tool versions, interrupts, or timing-sensitive firmware can change
  the sequence. Cross-build fingerprint equivalence is not promised.
- Instruction stepping adds substantial debugger overhead. Existing elapsed
  time measurements include this overhead; they are not native firmware
  execution timings. Fresh QEMU/GDB processes remain in use, without pooling,
  snapshots, or parallel execution.
- The fixed cap trades a bounded collection cost for incomplete observation of
  longer runs. A complete fingerprint can still fail to distinguish a useful
  behavior if its PC sequence is identical.
- Hashing suppresses raw trace fields in the public API. It is not a secrecy,
  non-reversibility, or security guarantee, particularly when a cooperating
  observer already knows the firmware or can enumerate candidate executions.
- The in-process Python boundary remains cooperative. These records do not
  provide isolation from malicious filesystem access, introspection, or frame
  inspection. Process/container isolation is separate future work.
- Collection is validated using FIRMAVEX-controlled synthetic Cortex-M
  firmware. This milestone establishes instrumentation correctness, not
  throughput or efficacy on external firmware or deployed hardware.
