# Windows Sandbox runtime installation investigation

The complete `FIRMAVEX_WINDOWS_SANDBOX_ACCEPTANCE_REPORT.md` was read before
inspection. Work is on `product/desktop-batch11`; no commit, push, release
approval or change to frozen main is part of this investigation.

## Verified findings

The setup wizard sends `setup_runtime` through the controller/supervisor to
`Worker._execute`, then `services.setup_runtime` and
`runtime_setup.install_vendor_runtime`. The provider creates private storage,
downloads the pinned bootstrap, checks its digest and allowed final HTTPS
origin, extracts MSYS2, runs two vendor upgrades and signed package installation,
collects the package inventory, snapshots runtime files and licenses, and calls
`runtime_pack.install`. That validates the archive and inventory, probes native
capabilities and verifies integrity before activating a generation.

Previously, urllib failures, storage errors and process launch errors could
escape this path as ordinary exceptions. The worker emitted `worker_failure`
with the generic message observed in the report. Its details contained only
the exception type and string; the wizard displayed the message, while the
main window retained details. There was no installation diagnostic file.
Synthetic network and permission failures reproduce this reporting path.
This defect affects ordinary Windows as well as Sandbox.

The exception which triggered the reported Sandbox failure is **unknown**.
There is no original traceback, log, verified artifact provenance or Windows
host available in this Linux workspace. Website access in Edge does not test
Python TLS/proxy behavior or GitHub release asset access. Download failure,
permissions, process launch, vendor updates and packaged execution remain
hypotheses, not verified causes. No bootstrap pin, URL, package version or
security policy was changed on speculation.

## Proposed fix

The public provider now catches ordinary setup exceptions after private cleanup,
classifies network and storage/process failures, and raises an actionable
ProductError instead of the generic worker error. Vendor subprocess progress
identifies the individual command stage. Cancellation still propagates.

Failures save a copyable JSON file under
`%LOCALAPPDATA%\FIRMAVEX\installation-diagnostics\runtime-setup-<id>.json`
(default Windows data location). Both wizard and main-window messages identify
the file. Copy that file to export installation diagnostics; no run selection
or report evidence export is needed. A failed diagnostic write is explicitly
reported without replacing the original error classification.

Diagnostics allowlist stage, exception class, HTTP status, OS error numbers,
vendor return code and bounded traceback locations. They omit exception text,
source lines, locals, environment, URLs and vendor output, which may contain
credentials. This deliberately limits vendor package-error detail; the exact
failed stage and return code are retained. Existing signature, checksum,
license, inventory, native qualification and release approval gates remain.

## Fresh Sandbox retest

Build a new unsigned development candidate from the reviewed branch and record
its commit and artifact digest. In a fresh x86-64 Windows Sandbox, launch it,
check missing runtime, consent and install. If setup fails, copy the diagnostic
JSON from the displayed location before closing Sandbox. Record stage, class,
HTTP/OS/return codes and candidate provenance. Also retest on ordinary Windows.

If setup succeeds, check verified generation history and ARM/RV32/HDL readiness,
then separately perform approved execution acceptance tests. Installation alone
is not firmware execution evidence or public-beta approval. The existing
`desktop-beta.yml` Windows provider job runs the real private installer through
`tools.desktop_setup_ci`; it must be run on the reviewed candidate. Native
Windows CI and packaged installer acceptance cannot be executed here without
publishing changes or access to a Windows runner.

## Local validation

Python 3.14 on Linux: runtime setup, worker, runtime pack and runtime tests
(`-k 'not actual_'`): **135 passed, 6 deselected**. The first sandboxed run
failed only because socket creation was prohibited; the permitted rerun passed.
Regression coverage includes network/permission/unexpected exceptions, safe
persisted traceback locations, HTTP status redaction, diagnostic write failure,
worker error transport, existing cancellation/cleanup and integrity refusal.
`git diff --check` passed. Native Windows installation and GUI acceptance remain
unverified; the native execution tests were explicitly excluded.

## Final security review

The review replaced diagnostic use of the runtime replacement writer with
exclusive `mkstemp` creation (no rename or overwrite). Directory components are
checked with lstat; symlinks, Windows reparse points/junctions and traversal are
rejected. A hostile same-user process can still race ancestor-directory swaps;
this is not an isolation boundary against another process with the user's
filesystem privileges. Exclusive creation prevents existing-file overwrite even
in that case. POSIX files use private creation permissions; Windows inherits
permissions from the per-user application-data directory.

Cleanup progress no longer masks the failed installation stage. A validated
activated-generation identifier is preserved if activation succeeded before a
cleanup failure. Download guidance now uses Windows-facing language. Standard
library additions are compatible with the declared Python >=3.11 requirement;
`packaging/desktop.spec` collects the provider module. A native frozen Windows
build was not run here. Diagnostics intentionally omit raw vendor output and
exception messages, so some network/vendor failures still require native
investigation. Cancellation continues to propagate rather than being converted
to an installation error. No unrelated runtime or release-gate code changed.

Final review rerun: **142 passed, 6 native execution tests deselected** across
runtime setup, worker, runtime pack and runtime tests. `git diff --check` passed.
Recommendation: ready to commit as a diagnostic improvement, with native Windows
installation and frozen-build qualification still required before release.
