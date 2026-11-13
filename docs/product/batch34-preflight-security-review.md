# Batch 34 — Windows preflight security review

**Review date:** November 13, 2026, Asia/Karachi.
**Baseline:** `1d419eba447a62cabd298ccf58bcf60c68f395f6`.
**Scope:** the administrative [preflight module](../../tools/windows_runtime_preflight.py),
its [synthetic tests](../../tests/product/test_windows_runtime_preflight.py),
and the relevant existing file-reader/import-parser contracts. Two independent
source-review passes covered paths/access and PE/receipts separately; fixes were
reviewed locally. This is not an external security certification or native
Windows qualification.

## Verdict and evidence scope

The demonstrated lexical-path and receipt-schema defects have been corrected.
**Controlled native Windows functional preflight validation may proceed** with
trusted synthetic fixtures or stable, developer-controlled local input copies.
Do not use it to inspect trees with concurrent untrusted writers. Prevention of
hostile path redirection is **not established**; unconditional protected-location
containment and general untrusted-filesystem acceptance remain blocked.

No runtime, firmware, installer or signer was launched, downloaded or approved.
No production pin, hash, admission rule, shared security implementation, frozen
research, workflow or release status was changed. No protected evidence or
original checkout was accessed. Synthetic path strings were intercepted before
access; the parent-race experiment used only temporary benign fixtures.

## Findings, ranked by severity

| ID / severity | Demonstrated baseline behavior | Resolution / remaining status |
|---|---|---|
| B34-01 — **MEDIUM**, lexical access policy | Mixed leading separators `\/server/share/file` and `/\server/share/file` escaped UNC-prefix refusal. Relative paths also inherited unchecked UNC, short-name or trailing-dot/space base spellings. Ordinary reserved-device checks missed `COM¹.exe`, `LPT².txt`, `COM1 .exe`, `NUL .dll`, `CONIN$` and `CONOUT$.txt`. | **Fixed in preflight only.** Normalize separators for prefix decisions and apply the same lexical policy to raw and joined absolute paths before filesystem checks. Extend reserved-device refusal without changing shared production path checks. |
| B34-02 — **LOW**, evidence-state correctness | Explicit `tools.qemu/gdb: null` became `missing`. With stale/unavailable subjects, a binding short-circuit hid malformed field types as `mismatch`/`blocked subject` instead of rejecting the malformed receipt. | **Fixed.** Distinguish absent keys from supplied null; validate all supplied row fields before subject binding. Missing fields remain missing, wrong valid values remain mismatches, and malformed schemas block the capture. No admission bypass existed. |
| B34-03 — **MEDIUM**, concurrent access containment | In a Linux temporary-fixture experiment, replacing an allowed parent directory with a symlink between checks and open caused an outside-selected fixture to be opened before final consistency checks rejected the capture. | **UNRESOLVED access-isolation limitation.** Detection is not prevention. Reports now explicitly set `concurrent_path_isolation=false`, retain `access_containment=not_assessed`, and warn in the summary. Require controlled stable staging; a separately designed, natively tested handle-relative/no-reparse traversal is needed for stronger claims. |
| B34-04 — **LOW**, test-guard coverage gap | The original activity guard did not cover writes through `io.open`/`Path.open` or directory enumeration. Source review found no such activity in the component. | **Test guard strengthened**, not a discovered write defect. Forbidden calls now include these APIs alongside process/network/write guards. |

B34-01 Windows behavior was modeled with `PureWindowsPath` and fail-fast
filesystem/network guards. This establishes lexical refusal, not native NTFS,
SMB, junction or Code Integrity behavior. Normal drive-path controls and
nonreserved `COM0`/`COM10` controls remain supported in the lexical model.

B34-03 is an inherited check/open race in the reused reader, not a runtime
qualification or code-execution bypass. This batch does not silently replace
shared production file handling with an unqualified Windows native reader.
Read-only mode prevents intentional writes; it does not create a sandbox or
guarantee that a hostile writer cannot redirect a read before rejection.

## Audited checks and regression evidence

| Area | Coverage / result boundary |
|---|---|
| Explicit file access | Traversal, protected/original path refusal, case variants, UNC/mixed separators, aliases in inherited bases, DOS-device variants and normal controls; no broad directory scan or PATH lookup |
| Links and filesystem entries | Static symlink/parent-link, hardlink, special-file and simulated reparse-attribute rejection; temporary parent replacement must not yield a nominally successful capture, but access isolation is not claimed |
| Receipts | Missing files/fields, null and malformed containers, duplicate JSON keys, exact types, stale subjects, wrong hashes, pinned malformed observation JSON, opaque malformed provenance bytes, actual 1 MiB+1 size rejection and mid-capture changes |
| Hashes / DLLs | Full-file comparisons to unchanged production constants, inability to override runtime hashes, declared companion identity/format checks and missing ordinary imports; complete native DLL closure remains unassessed |
| PE/certificate inspection | Header/section/file offsets, x86 installer versus x64 runtime, table alignment/length/count, unsupported revisions/types, mapped-section overlap and bounded malformed mutations; no signature authentication |
| Privacy | Fixed diagnostic codes, bounded version formats and explicit DLL basenames; no supplied paths, arbitrary receipt contents, raw exceptions or environment dump in JSON/summary |
| Read-only behavior | Tests forbid subprocesses, network calls, directory enumeration and write opens, including `io.open`; supplied bytes remain unchanged in ordinary preflight tests |
| Control flow | KeyboardInterrupt/SystemExit propagate unchanged; blocked captures do not retain earlier measured assertions |

The deterministic PE mutation regression uses seed **3401**, **2,622 invented
inputs** (122 truncations and 2,500 bounded field mutations), and no executable
code. The audit observed 151 limited-structure accepts and 2,471 ValueError
rejections with no unexpected exception. These are parser cases inside one test,
not 2,622 firmware executions or independently authenticated binaries. Acceptance
counts are observations, not a fixed safety threshold or full PE-validity claim.

An initial targeted baseline run produced **16 failed / 4 passed / 116
deselected** for receipt/UNC cases; a separate inherited-base selection produced
**5 failed / 1 passed / 136 deselected**. The failures demonstrated the repaired
behaviors. Subsequent Windows lexical controls were explicitly modeled as Windows
rather than relying on this Linux host's path rules. Existing assertions were
retained; no security check was disabled.

Exact final commands and counts belong to the dated
[development-history entry](development-progress.md#2026-11-13--batch-34-preflight-security-review).
Selections overlap and do not constitute a complete repository suite.

## Five evidence states remain distinct

- **verified:** only the named byte/digest/limited-structure or supplied-receipt
  consistency check passed. It never means authenticated, trusted or executable.
- **missing:** no descriptor/file/expected digest or genuinely absent observation.
- **mismatch:** a validly formed supplied identity/value disagrees with actual
  bytes or its declared expected contract.
- **blocked:** unsafe, unsupported, malformed, oversized or observably changing
  inputs prevent assessment; prior measured claims are discarded for capture races.
- **not_assessed:** native capability, publisher/Authenticode trust, full closure,
  legal completeness, concurrent access isolation and qualification remain unknown.

JSON is the report on stdout; the human summary is on stderr. Exit **2** means
blocked; exit **1** retains unresolved evidence. No qualification-success exit
was introduced. All execution/admission/qualification and atomic-snapshot flags
remain false. The new isolation flag is also false, including on blocked input.

## Static signing limitations and remaining Windows risks

A syntactically plausible `WIN_CERTIFICATE` container is not a verified
Authenticode signature. The preflight does not validate ASN.1/PKCS#7 signatures,
certificate chains, trusted RSA publishers, timestamps, revocation, SmartScreen
reputation or Smart App Control acceptance. Even a fully authenticated outer
installer would not establish the trust of every separate runtime EXE/DLL.
Signing can change full-file hashes; this review authorizes no pin replacement.

Other outstanding requirements:

1. Native Windows junction/reparse, sharing/locking and change-time behavior for
   the exact source/interpreter/filesystem. Simulated attributes are not evidence
   of all Windows path semantics.
2. Independently enforceable access containment against hostile concurrent
   writers, including ancestor replacement and native handle semantics. Post-read
   consistency checks, file read-only attributes or caller trust labels do not
   prove containment. Do not test attacks against protected or private directories.
3. Authentic immutable vendor archives and signing inputs, installed/DLL ownership,
   compatible closure, licenses/source delivery and actual GDB Python/hashlib/ARM
   or QEMU capability evidence. No runtime probe was performed here.
4. Byte/count bounds are I/O limits, not an OS memory, wall-clock or filesystem
   sandbox. Hostile/unresponsive/network filesystems are outside this administrative
   preflight's qualified scope. Interrupt rather than treating a partial report as
   completion; preserve failures and do not disable host protections.

## Subsequent manual native Windows validation

This is a future bounded **preflight-only** procedure, not permission to execute
firmware, acquire packages, sign, install or promote a runtime.

1. Use the reviewed Batch 34 revision from its delivery report in a native Windows
   verification checkout and its existing Python environment. Confirm the exact
   revision and preserve any changes; do not reset, pull over work or change
   security settings. Missing dependencies are a blocker, not an installation step
   authorized by this procedure.
2. Use only fresh synthetic fixtures or already reviewed local files in a stable,
   developer-controlled staging directory with no untrusted/concurrent writers.
   Keep it outside protected/private evidence and original archives. Do not use
   UNC, short-name aliases, linked/reparse trees or live mutable installations.
   A file's read-only attribute alone does not prevent parent replacement.
3. Run the synthetic suite, retaining actual counts and skip reasons:

   ```powershell
   & {
       $ErrorActionPreference = 'Stop'
       if (-not $IsWindows) { throw 'Use native Windows PowerShell 7.' }
       $Expected = Read-Host 'Paste the full reviewed Batch 34 commit SHA'
       if ($Expected -cnotmatch '^[0-9a-f]{40}$') { throw 'Expected a full commit SHA.' }
       $Head = (& git rev-parse HEAD).Trim()
       if ($LASTEXITCODE -ne 0 -or $Head -cne $Expected) { throw 'Revision mismatch; preserve the checkout and stop.' }
       $Status = @(& git status --short --untracked-files=all -- . ':(exclude)evidence/**')
       if ($LASTEXITCODE -ne 0 -or $Status.Count -ne 0) { throw 'Checkout changed; preserve all work and stop.' }
       $Python = (Resolve-Path '.venv\Scripts\python.exe').Path
       & $Python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_windows_runtime_preflight.py
       if ($LASTEXITCODE -ne 0) { throw 'Preflight regression failure; preserve diagnostics and stop.' }
   }
   ```

   A skipped symlink/FIFO test is unverified coverage, not proof of native support;
   do not enable privileges or disable protections to force it green.
4. Inspect a small explicitly supplied manifest following the
   [operator contract](batch33-runtime-preflight.md), using `python -B`. Retain JSON
   and summary in **new** private output files outside source/input archives if
   needed. Expect unresolved evidence and exits 1/2; never edit hashes/receipts to
   obtain a better classification. With no real binaries supplied, label the run
   synthetic and do not claim real runtime verification.
5. Check deterministic repetition, unchanged input bytes, safe errors for missing
   and malformed synthetic receipts and no tool/installer/network launch. Validate
   simple ordinary Windows paths and benign fixture-only links; never select,
   enumerate or redirect toward protected evidence. Stop on unexpected access,
   output disclosure, mutation, hanging I/O or any nominal trust/approval claim.

Native functional results should be recorded as a new evidence class with source,
Python/Windows versions and actual scope. They cannot close hostile-writer access
isolation, runtime execution, signing or release qualification by themselves.
