# Batch 28: proposal for positive Windows product qualification

**Proposal only; no execution or admission change is authorized by this document.**
Baseline: `c42cdd000dbd117dee558fd346aa8b653ac7bf3f`.
Review date: 2026-11-09 (Asia/Karachi).

The current candidate is MSYS2 UCRT64 QEMU 11.1.3 / GDB 18.1. It is not a member
of the existing Windows production profile. This proposal does not approve it,
create a candidate profile, supply a gate override or authorize a workflow run.

## Existing boundary and the unresolved decision

`firmavex/product/services.py::_execute_project()` discovers and validates tools,
then calls `platform_support.require_native_support()` before creating a real
execution session. Its `_executor_factory` seam changes the measurement mode to
`synthetic_test`; using that seam with a real executor would not establish real
positive product qualification and is not an acceptable workaround.

The unchanged production profile in `firmavex/product/platform_support.py` is:

| Tool | Required version | Required executable SHA-256 |
|---|---|---|
| QEMU | `QEMU emulator version 11.1.2` | `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` |
| GDB | `GNU gdb (GDB) 18.1` | `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` |

Source, frozen console/worker and installed application paths ultimately share
this decision. Therefore **positive execution with QEMU 11.1.3 through the
unchanged production application is blocked by design**. Passing rejection tests
or running the existing low-level candidate source probe does not close that gap.

There are two distinct future decisions:

1. **Exercise the unchanged product with its existing qualified runtime.** Obtain
   a genuinely authenticated, compatible and immutable QEMU 11.1.2 package set
   without mixing rolling dependencies. If that set cannot be verified, stop.
   Such testing would qualify that runtime/application combination, not 11.1.3.
2. **Review a new runtime qualification policy after independent evidence review.**
   Before any policy implementation, obtain explicit approval for its trust
   inputs, complete package/DLL closure, legal evidence and required tests. A
   separately reviewed lab-only application build could then be considered, but
   it would be a different build/policy: its results must never be described as
   positive execution by the unchanged production build. A production profile
   change would require a separate authorization and review.

Neither decision is taken in Batch 28. Do not edit pins, forge tool identities,
monkeypatch admission, add environment-variable bypasses, or relabel injected
observations as `real_firmware` to make the matrix green.

## Preconditions for a separately authorized run

- Bind source revision, workflow revision, exact run attempt, build inputs,
  installer and application hashes, native Windows build/CPU, account token and
  frozen runtime closure before execution. Retain original immutable inputs.
- Independently verify actual publisher package signatures using separately
  trusted signing inputs. Record complete package ownership, imports/DLL
  resolution, hashes, notices, corresponding source and unresolved dependencies.
  A `pacman -Q` list, package-manager validation declaration, license string or
  executable pair alone is insufficient.
- Use a disposable native Windows x64 host and trusted bundled example only.
  Preserve operating-system protections. Keep application installs, projects,
  results and administrative evidence in separate owned locations.
- Predeclare finite cases, budgets, cancellation stages, timeouts and pass/fail
  rules. Keep this engineering plan separate from frozen research protocols and
  historical campaign archives; no comparative campaign is required.
- Capture per-test native JUnit, process ownership/cleanup, authoritative result
  records and executable/firmware evidence. Missing evidence is NOT PROVEN, even
  when a CI step has exit status zero.

## Required source, frozen and installed matrix

Each row must run through the named product entry point. Repeat the required
journeys separately for source, frozen and installed distributions; direct
`FirmwareExecutor` calls cannot substitute for those paths.

| Journey | Required observations and pass criteria |
|---|---|
| Readiness and validation | Correct supported target and actual runtime identities; the compiler-free image retains its bundled manifest digest. An unsupported runtime still fails before dispatch. |
| Bounded search | Normal supervised `run` or built-in demonstration finds the trusted example's exact vector `[2, 1]`; saved result, attempt records, failure symbol and cleanup agree. |
| Ordinary completion without configured failure | Use a separately declared supported project configuration whose admitted search domain excludes the trigger; retain completion/readback evidence and truthful non-discovery classification. Do not invent a direct-vector ARM backend API. |
| Positive and negative runtime observations | Independently check `(2, 1)` produces failure flag 1 and `(2, 0)` produces 0, with initialized data and synchronization evidence. Existing low-level probes supply this runtime-level coverage; they are supplementary to product-path search. |
| Reproduction | `reproduce` uses the saved exact trigger in fresh output, with three requested fresh observations all matching. Match firmware/tools to the original run. A changed environment must be rejected as non-equivalent. |
| GUI | Use actual controller/worker execution, visible progress and terminal result; verify exact vector, bounded replay, history/reopening and exports. A startup smoke test alone is insufficient. |
| Cancellation and timeout | Interrupt at declared pre-dispatch and post-admission stages. Preserve charged attempts, abort classification and original interruption; no later trigger may mask an infrastructure failure. |
| Cleanup | Independently verify owned QEMU/GDB/worker handles/trees terminate and are reaped after success, error, cancellation and timeout. Do not rely on process-name matching alone. |
| Persistence and recovery | Reopen valid terminal records; distinguish interrupted work from completion. Explicit recovery must not run firmware. Explicit restart creates a new linked search and discloses repeated abandoned work. |
| Reports and export | Check authoritative accounting, firmware/tool identity, exact input and evidence classification; verify exported `evidence.json`, `report.md` and `SHA256SUMS`. Export must not dispatch firmware or alter the original archive. |
| Installation lifecycle | Link installed console/GUI files and runtime closure to the reviewed build; exercise installer, reinstall and uninstall with preserved independent projects/results. Distinct-version upgrade/rollback needs its own declared version pair. |

Existing commands are implemented in `firmavex/product/cli.py`; frozen console
dispatch uses `--firmavex-cli`. The GUI uses supervised workers. This proposal
does not supply a command that can make the unqualified candidate pass admission.

## Result ownership and promotion decision

The run's administrator owns raw diagnostics and provenance. Strategy feedback
and public result semantics must remain unchanged. Validate actual attempt
records against authoritative evaluator accounting, separating charged attempts
from independently verified physical guest executions. A successful simulator
observation does not establish hardware behavior, sandbox isolation or broad MCU
compatibility.

Use PASS / FAIL / NOT PROVEN per matrix row and distribution, with evidence
digests and exact native tests. CI observations, independently reviewed archive
contents and consumer-machine acceptance are different evidence levels. Do not
collapse them into one "qualified" flag. No runtime promotion follows
automatically; record the separately authorized decision and its scope.

This document was prepared by source inspection only. No positive candidate
application execution, native Windows trial or new qualification run was
performed while writing it. Current artifact verification and release status
belong in the Batch 28 release-readiness report.
