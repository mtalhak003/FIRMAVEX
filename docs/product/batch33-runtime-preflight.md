# Batch 33 — read-only Windows runtime provenance preflight

Implementation review date: **2026-11-13, Asia/Karachi**. Development baseline:
`19f9eb0254fd0162db601e5ed82055baa92e7a5d`.

This implements the first diagnostic milestone of the
[Batch 32 plan](batch32-windows-runtime-packaging-plan.md), not runtime recovery,
qualification, installation or signing. The administrative module
[`tools.windows_runtime_preflight`](../../tools/windows_runtime_preflight.py)
reads explicitly supplied files, returns a sanitized deterministic JSON report
and prints a human-readable summary. It is not a shipped GUI feature or a new
production admission path. QEMU 11.1.3 remains production-unqualified.

## What is checked

| Check | Independently observed here | Still not established |
|---|---|---|
| QEMU/GDB identity | Bounded actual-byte SHA-256 comparison against the unchanged Windows production constants | Publisher origin, host acceptance, compatibility of the complete installation |
| Version | Exact admitted digest permits a **profile-version association**; supplied version observations can be compared to the expected version and bound to measured bytes | No executable version command or PE version-resource extraction is performed; a mismatching binary's version cannot be established without separate evidence |
| Companion DLLs | Caller-declared DLL files, pinned hashes and ordinary PE32+ x64 import references, including transitive references among supplied files | Complete inventory, actual Windows loader, system/API-set resolution, delay/dynamic imports or full compatible closure |
| Embedded GDB Python/hashlib, ARM and QEMU machine | Consistency of supplied, digest-bound observations against the discovery contract | Whether those observations are authentic or the supplied installation actually works; no GDB or QEMU is launched |
| Package, publisher, dependency and legal receipts | Presence and actual-byte integrity against supplied receipt hashes | Publisher signatures, trusted signing inputs, archive/member ownership, complete dependency resolution or legal clearance |
| Application, worker, installer, uninstaller and supplied runtime DLLs | File/hash observations, limited PE headers and `WIN_CERTIFICATE` table structure/absence | PKCS#7 validity, trusted RSA chain, signer, timestamp/revocation, Smart App Control acceptance or exhaustive signing coverage |

The tool reuses the existing bounded file reader, file-state observations and
ordinary PE import parser. It does **not** invoke the package verifier's GPG,
archive or version-comparison subprocesses, discovery probes, native execution,
admission, directory inventory walkers or signature verification services.

## Input contract

Run from a development checkout with its existing Python environment:

```powershell
python -B -m tools.windows_runtime_preflight --manifest 'C:\FIRMAVEX-admin\preflight.json'
```

This launches only the Python diagnostic, not supplied runtime/application files.
Keep `-B` (or set `PYTHONDONTWRITEBYTECODE=1`) so interpreter imports do not create
bytecode caches. The module does not mutate global interpreter settings.
There are no output-file arguments: JSON goes to stdout and the summary to
stderr. If capturing either stream, choose **new files outside** the checkout,
runtime generation and original evidence. The tool creates no files/directories.

A minimal valid manifest, which reports missing evidence, is:

```json
{"schema_version":1,"artifacts":{}}
```

The exact root fields are `schema_version`, `artifacts`, optional `companions`
and optional `receipts`. Unknown fields and duplicate JSON keys are rejected.

- `artifacts` maps any of `qemu`, `gdb`, `application` (GUI), `worker` (console
  sidecar), `installer`, `uninstaller` to descriptors. Every absent role is
  reported missing, not inferred from another file.
- A descriptor is `{"path":"relative/or/absolute/file","sha256":"..."}`.
  `path` is required. An optional `sha256` must be exactly 64 lowercase hexadecimal
  characters and is compared to the actual bytes; absence means missing identity
  evidence. **QEMU/GDB descriptors permit only `path`**, because their expected
  hashes must come from production constants, never caller overrides.
- Relative paths are relative to the manifest's directory, not PATH or the shell
  working directory. Environment-variable expansion and automatic tool search
  are not supported. Supply ordinary native local paths.
- `companions` is an ordered array of descriptors for explicitly supplied DLLs.
  Basenames must be unique case-insensitively and simple ASCII `.dll` names.
  Generated report IDs such as `companion_001` preserve declaration order.
  Missing import names are reported even if they might be system/API-set DLLs;
  the tool does not invent a system resolution policy or scan for replacements.
- `receipts` maps any of `runtime_observations`, `package_manifest`,
  `publisher_authentication`, `dependency_closure`, `licensing`, `authenticode`
  to descriptors. Except for runtime observations, these are opaque evidence
  files: a matching hash proves integrity against the supplied pin only.
  Their labels or contents cannot turn trust/closure/legal checks into verified.

Optionally supply `--expected-manifest-sha256` with an independently reviewed
digest. A match establishes manifest integrity, not origin/authentication.
Without it the manifest digest is recorded but remains unpinned. An expected
manifest mismatch stops assessment. Never fill a missing hash or receipt with
invented values to obtain a better state.

### Optional runtime-observation receipt

This is a small **caller-supplied consistency envelope**, not a replacement for
original native logs or a converter/reconstructor of missing execution evidence.
It has exactly `schema_version: 1` and a `tools` object containing either or both:

- `qemu`: required `sha256`; optional `version` and exact-bool `mps2_an385`.
- `gdb`: required `sha256`; optional `version`, exact-bool `arm`, and
  `python_hashlib_marker` string.

Each subject digest must match the measured executable. Version text is limited
to the bounded numeric version formats used by failure diagnostics. The expected
marker is the existing discovery expression
`"FIRMAVEX_GDB_CAPABILITY_V1=" + hashlib.sha256(b"probe").hexdigest()`.
The preflight computes that constant locally; it never asks GDB to compute it.
Only supply values supported by retained observations. Missing fields remain
missing; false capabilities or wrong markers/versions are mismatches. Malformed
or unbound observations cannot establish capability evidence.

A matching envelope receives only `receipt_consistency_only` checks. Native
capabilities and receipt authenticity remain **not_assessed**, even when every
field matches. Existing original Batch 27 ZIP verification is a separate tool
and evidence scope; this envelope cannot substitute for its original bytes.

## Evidence states and exit status

| State | Exact interpretation |
|---|---|
| `verified` | The named limited check passed: bytes read, digest comparison, header/table structure, explicit static reference or supplied-receipt consistency. It is never a runtime approval. |
| `missing` | Required descriptor/file, digest, companion, receipt or observation field is unavailable. |
| `mismatch` | Actual bytes differ from their expected digest, or supplied observations disagree with their subject/profile/capability contract. |
| `blocked` | Unsafe/unreadable, malformed, oversized, unsupported or observably changing input prevents assessment. |
| `not_assessed` | Trust, native execution/capability, dynamic closure, signing/legal completeness or qualification was not independently assessed. |

Reports contain per-artifact/receipt checks, required import references, counts
and an overall status with precedence blocked, mismatch, missing, not_assessed.
`production_qualified`, `production_admission_evaluated`, `tools_executed`,
`firmware_executed` and `atomic_snapshot` remain **false**. There is no approval
flag, runtime repair, download or promotion action.

**Exit 2** means blocked assessment. **Exit 1** means a report retaining
missing/mismatching/unassessed evidence. This diagnostic deliberately offers
no successful qualification exit: even complete static inputs leave native trust
and execution unassessed. Normal `--help` exits independently of assessment.
Malformed CLI arguments also receive sanitized JSON/summary rather than raw
argument values. Interruptions such as KeyboardInterrupt are not swallowed.

## Safety, resource and consistency boundaries

- No subprocess, firmware, guest, installer, signer, network request or directory
  scan is initiated. No supplied file is opened for writing.
- Lexical checks precede filesystem access. Protected evidence paths and the
  original checkout are refused; UNC/device/ADS/traversal, ambiguous trailing
  dot/space, tilde/short-name and DOS-device spellings are refused. Existing
  helpers reject symlinks, reparse points, hardlinked/special files and unsafe
  parents. These restrictions can reject vendor layouts that need separate
  future review; they are not relaxed here.
- At most 64 supplied artifact/DLL descriptors, six receipts and one manifest.
  Artifacts are at most 64 MiB each; manifest/receipts at most 1 MiB each; logical
  input bytes including the manifest are capped at 128 MiB. Consistency rereads
  have a bounded aggregate allowance of 512 MiB plus one EOF-probe byte and a
  bounded read-call count. Static import references are capped at 4,096.
- Bounded reads check actual bytes and path/handle metadata, then all measured
  files are rechecked after processing. Observable changes/disappearances or a
  previously missing file appearing block the capture and discard prior measured
  assertions. This is not an atomic snapshot, a repository lock or a guarantee
  against adversarial filesystem aliases/races.
- Reports omit supplied paths, environments, raw exceptions, arbitrary receipt
  contents and private package output. They retain symbolic roles, bounded
  version text, hashes, sizes and validated **import DLL basenames** needed to
  identify missing companions. Review these identifiers/digests before publishing
  administrative reports; sanitization is not anonymity or legal clearance.

Signing or timestamping runtime files can change their full-file pinned digest.
Neither certificate-table presence nor a supplied “valid signature” receipt
authorizes transformed bytes. Preserve originals and the Batch 32 separation
between package trust, Authenticode, host policy and explicit profile approval.

## Validation and remaining work

Synthetic fixture tests live in
[`test_windows_runtime_preflight.py`](../../tests/product/test_windows_runtime_preflight.py).
They do not require native Windows binaries and are not native qualification.
The dated [development history](development-progress.md) records actual commands
and results; no test count is inferred from test existence.

Remaining gaps are authentic immutable vendor archives/signatures and independent
trust inputs, compatible archive/installed/native DLL closure, actual licenses
and source-delivery review, final signing coverage and native Windows/SAC consumer
acceptance. GDB embedded Python/hashlib, ARM, QEMU machine support, cleanup and
positive source/frozen/installed execution still need separately authorized
native evidence. This component acquires none of those inputs and changes no
production admission or frozen research behavior.
