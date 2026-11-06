# Batch 23D: Windows runtime candidate source stage

**Prepared, not natively executed or qualified.** The isolated workspace baseline
is `88ef1e1f9f6dbb773f43dc30918fa6f9a16d16ef`. The existing Batch 23C acquisition
investigation remains unchanged. No production admission policy, runtime catalog,
package provider, firmware, frozen application or installer is modified here.

## Historical evidence and new candidate

`firmavex/product/platform_support.py` cites historical Actions run
[38278936642](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38278936642)
for six actual ARM runtime tests on the existing QEMU 11.1.2/GDB 18.1 profile.
Later workflows add supervised search/reproduction, native desktop journeys,
frozen/installed application execution, cancellation and saved-data preservation.
Those are historical profile-specific observations, not results for this candidate.

The candidate harness requires the operator-verified QEMU package `11.1.3-1`
and GDB package `18.1-3`, plus these independently checked executable identities:

| Tool | Version string | SHA-256 |
|---|---|---|
| QEMU | `QEMU emulator version 11.1.3` | `f7e69cf3c284bad6a3b1c4159d2a88001f285c28f890dd2f8e56186682840cc7` |
| GDB | `GNU gdb (GDB) 18.1` | `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` |

A changed package version, executable version or digest fails preflight rather
than silently testing or admitting another runtime. Production still accepts only
its original QEMU 11.1.2 profile. The candidate explicitly checks that production
rejects it before and after source probing. No admission monkeypatch, environment
backdoor, altered expected production hash or candidate support catalog is added.

## Isolated CI acquisition and evidence

The new `windows-runtime-candidate.yml` is **workflow_dispatch only** on native
Windows x64. A required full source SHA must equal the workflow's `GITHUB_SHA`
and checked-out HEAD. The harness also requires the exact repository/workflow
identity and an Actions run ID. These checks prevent accidental use; they are
not a security sandbox against the runner's owner.

Pinned actions install a private MSYS2 UCRT64 environment and perform a full
signed package transaction for QEMU, GDB and ARM GCC. `PackageRequired` and
`PackageTrustedOnly` must remain effective. No partial downgrade, ignored package,
signature bypass or old/new DLL mixture is constructed. All installed package
versions and the effective signature policy are retained. Acquisition is still
rolling: this prepares an evidence-producing candidate run, not the immutable
acquisition repair that Batch 23C could not establish.

Preflight hashes the **entire UCRT64 prefix**, including libraries, modules, data,
compiler files and license notices. Relative names, sizes and hashes are recorded;
the source probe compares the full inventory again before and after execution.
This is an observed file set, not a proven minimal dependency closure or atomic
snapshot. Administrative bounds are 100,000 entries, 8 GiB total input bytes,
512 MiB per file, 32 MiB per JSON record and 128 MiB of top-level metadata/log
retention. These do not enlarge any firmware/worker resource limit. Links, reparse
points, hardlinked files and exceeded bounds fail closed; a native run may expose
such a blocker and must report it rather than relax the checks.

Evidence is isolated under the runner temporary directory. The upload includes
only acquisition logs/inventory, candidate JSON/receipts, the product-owned
example and test diagnostics. It does not redistribute QEMU/GDB binaries, scan
user archives or collect any repository `evidence/` directory. License file hashes
are retained; publisher provenance, source obligations and redistribution still
require independent review. Review CI logs/paths before public publication.

## Required qualification matrix

| Requirement | This candidate stage | Evidence still required before a new profile is considered qualified |
|---|---|---|
| Publisher acquisition, selected identities, full file/package inventory | Prepared in preflight; no native result yet | Actual Windows installation logs, matching identities, consistent inventory |
| ARM reset/startup, input-ready and completion lifecycle | Existing actual runtime tests plus bundled-image source probe | All selected native cases must pass with real QEMU/GDB |
| Positive `(2,1)`, negative `(2,0)`, initialized data | Four fresh source-probe executions | Correct observations and original bundled image identity |
| Search and bounded reproduction | Existing evaluator/runner; 10 search and 3 replay attempts | Exact vector `[2,1]`, authoritative accounting, three triggering replays |
| Cancellation, timeout, abort and cleanup | Two fresh executions; cancellation follows injection | Charged failure, abort, no later dispatch, actual process cleanup |
| Ownership and resource behavior | Existing native Job/supervisor/process checks; new 128 MiB host allocation denial case | Actual native results; host allocation denial is not aggregate QEMU memory/CPU qualification |
| GUI, worker/CLI, history, reports and exports | **Pending** | Candidate-only native desktop/supervised journeys without changing production admission |
| Frozen application and installed application | **Pending** | A separately reviewed isolated candidate build/test path; production remains gated |
| Upgrade, rollback, interruption, uninstall and retained data | **Pending** | Distinct-version native lifecycle evidence and unchanged saved results |
| Standard user, offline, low disk and accessibility | **Pending** | Appropriate native/interactive acceptance; hosted source tests cannot replace it |
| Dependency review and profile promotion | **Not automatic** | Independent review, complete native matrix, explicit versioned policy decision |

The low-level `FirmwareExecutor` is an existing test facility. The probe calls it
directly and never modifies `require_native_support` or the supervised product
services. Each execution uses the normal bounded startup/debugger flow and cleanup.
An outer owned pytest process tree applies the existing CI watchdog. Actual
source-probe attempts total 19 when all cases complete: 17 successful observations,
one timeout and one cancelled execution. Failed/cancelled receipts and partial
accounting remain distinct from successful completions. No research campaign runs.

Every candidate JSON envelope has `candidate_only=true` and
`production_qualified=false`. `candidate_preflight_only` and
`candidate_source_probe_passed` describe those limited stages, never the full
qualification matrix. JUnit/CI failures and skips remain authoritative; a passed
source report does not override a later resource-test failure or pending stages.
Candidate tools are outside the application packages and frozen entry points.

## Running after review

This workspace is intentionally uncommitted. The workflow cannot run remotely
until a separate approved publication puts it on the development branch. Then
select **Windows runtime candidate ONLY - no production approval**, choose
`product/desktop-batch11`, and supply that exact reviewed commit SHA. Do not use
the old baseline SHA for code that contains this newly added workflow.
GitHub workflow registration/dispatch permissions must also be verified. If the
branch-only workflow is unavailable, stop and request an approved registration
path; do not modify main or substitute a production workflow/admission bypass.

Retrieve `Windows-UNQUALIFIED-runtime-candidate-<SHA>` and assess all job steps,
JSON status/pending fields, receipts, inventory stability, and JUnit outcomes.
No source result authorizes installation through the production runtime provider
or approval of QEMU 11.1.3. Linux unit tests use explicitly synthetic fixtures;
the native source/resource tests skip unless this Windows workflow is requested.
