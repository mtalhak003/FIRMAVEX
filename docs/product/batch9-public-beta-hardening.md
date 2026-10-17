# Batch 9 public beta hardening — preview, not release approval

## Implemented controls

All workflows use immutable commits catalogued in `packaging/action-pins.json`.
The catalog records upstream tag resolutions observed on 2026-10-17. This is
identity pinning, not a complete security audit of action source. Updates require
review of upstream release notes and commit diff, tag resolution, catalog and
workflow changes together, and the complete product/native/distribution/beta
matrix. Do not replace a SHA merely because a movable tag changed.

`packaging/build-requirements.lock` locks build/test dependencies, including
platform-specific PyInstaller dependencies, to existing environment versions.
Published wheel SHA-256 hashes are retained; source builds are forbidden by CI.
CI installs this lock with `--require-hashes --only-binary=:all:`, then installs
the project with `--no-deps --no-build-isolation`. The build backend is therefore
also locked. `python -m tools.check_build_inputs` rejects expected-version drift.
It does not retroactively prove installed bytes match wheel hashes. Pip's
installation verification is a separate required step. Python setup downloads,
OS package feeds, hosted runner images and compiler toolchains are not fully
content-locked. Reproducible inputs are improved; byte-identical builds are not
established. Do not use this CI lock as a promise of all Python/OS support.

Distribution jobs archive `collected-files.json`, `python-environment.json`,
`python-environment.txt`, Linux `os-packages.txt`, installers and existing review
sidecars. The release manifest binds the new inventory/environment files as
artifacts. Inventory output must remain outside the inventoried directory to
avoid self-reference.

## Actual collected-file inventory

Run with the original build environment, without executing application binaries:

```sh
python -m firmavex.product.frozen_inventory dist/FIRMAVEX \
  --installer dist/FIRMAVEX-Linux-amd64.deb --output /tmp/collected-files.json
```

Every observed regular file is hashed twice per identity check and rechecked at
the end. Directory membership and internal symlink targets are checked before
and after capture. External/broken links, special files, excessive size/count,
observable modifications and duplicate installer names fail closed. Internal
macOS framework links are recorded, not followed into an external tree.
Capture is `stable_observed`, `atomic=false`; it does not lock files or guarantee
against every adversarial race. Outputs are exclusive-create and never overwrite.

ELF magic, PE/Mach-O candidate magic and archive suffixes classify bytes without
loading executable code. Path-based component hints are explicitly unverified.
All regular files retain `ownership=unverified`, `license_concluded=NOASSERTION`
and `corresponding_source=not_verified`. Unknown paths are retained. The
collected-file map complements, rather than relabels, the existing Python-only
SPDX build-environment document. Neither is a completed component-level native
SBOM. Embedded executable/PYZ/ZIP members and installer payloads are not expanded;
installer identities do not prove payload correspondence. The inventory is
useful audit input, not completion of the legal or native dependency review.

Local retained Batch 8 frozen Linux application inspected during Batch 9:
330 entries, 305 regular files, 25 internal links, 206,307,155 regular-file bytes;
168 ELF files and one unexpanded archive. All 305 file ownership conclusions
remain unverified. This is a retained precommit build, not the newly pushed
commit's release artifact. CI captures each actual new host build separately.

## Qualification matrix and unresolved gates

| Area | State / scope |
|---|---|
| Windows x64 and Ubuntu x64 ARM/RV32/Verilog | Previously qualified example workflows; rerun matrix required for new commit |
| macOS Apple Silicon | Desktop preview only; unified native RLIMIT_AS admission remains blocked |
| Consumer installation | Existing fresh hosted-runner startup, compiler-free examples, persistence, same-build reinstall/uninstall checks retained |
| Physical consumer machines / restricted standard-user installs | Untested; hosted CI does not establish this |
| Distinct-version upgrade and rollback | Blocked/not implemented; product version remains 0.3.0.dev1; do not relabel same-build reinstall |
| Interrupted installer recovery, low disk and restricted ACL lifecycle | Not qualified by this batch |
| Complete native SBOM and corresponding-source archive | Incomplete; explicit public redistribution blocker |
| Signing / notarization | Not configured, not performed |
| Hostile workload isolation | Not established; untrusted workloads remain rejected |
| Automatic GitHub Release | Not performed |

No genuine distinct-version installer qualification can be claimed from two
renamed 0.3.0.dev1 packages. A release version/migration policy and actual baseline
installer must precede this test. Preserve source revision, executable identities,
result JSON and SQLite hashes across supported upgrade and deliberate downgrade
rejection tests. Do not infer authoritative outcomes from a GUI opening.

## Linux isolation assessment

The existing fixed Bubblewrap probe was rerun, not promoted to a general worker.
Its 12 filesystem/network/process/limit/cleanup checks passed locally, including
host listener denial, memory allocation denial, bounded writes and descendant
cleanup. Per-process CPU/address-space limits are not aggregate quotas. The
cgroup hierarchy is not writable/delegated and `/dev/kvm` is unavailable in this
cloud environment. A bounded hostile-workload worker with independently enforced
aggregate memory/CPU/process quotas therefore remains blocked. No arbitrary
workload launch path is added. Probe success never authorizes untrusted work.

## Release and next-batch gates

Before public beta approval: complete actual native/component ownership and
license mapping, corresponding-source/replacement-rights review, expanded payload
verification, signing preparation and independent consumer-machine acceptance.
Build genuinely distinct versioned installers and prove upgrade/downgrade/crash
behavior without changing authoritative outcomes. Obtain delegated quotas or an
independently reviewed VM isolation boundary before considering untrusted work.
Keep macOS preview-only until native resource admission is defensible. Archive
all failed checks and distinguish blocked assessment from successful enforcement.
Research protocols, benchmarks, archives, accounting and main are unchanged.

Raw `pip inspect` output may contain absolute build paths and direct-install
metadata. Treat it as administrative provenance: review before publication.
Redacted public copies must have new identities and must not be presented as
byte-identical private build records. Never add credentials to these artifacts.

## Local validation evidence

Hash-enforced wheel downloads and installed-version checks passed. A fresh Linux
PyInstaller application passed real ARM/RV32/HDL execution, reproduction, exports,
all three in-flight cancellation/cleanup cases, and frozen GUI startup with
`PATH=/nonexistent`. These are bounded example checks, not hostile-workload or
hardware qualification. New inventory/build-input tests and existing release /
packaging checks pass (44 focused tests). All four Linux-host native-Windows-only
skips are reported separately in complete-suite output. GitHub results must be
checked against the pushed commit; local success cannot substitute for them.
The lock was additionally installed into a new virtual environment from the
hash-verified wheel directory with network indexes disabled; dependency and
version checks passed. A wheel built and installed without build isolation or
additional dependency resolution imported the new inventory module successfully
outside the source checkout.

Windows qualification exposed two portability defects during this batch. The
inventory test's external-link fixture now uses native path separators; invalid
and cyclic links remain structured failures, and directory reparse points are
rejected before traversal. No link check was skipped or relaxed. Build metadata
capture uses explicit UTF-8 subprocess output: `pip inspect` under CP1252 was
independently reproduced exiting 2 on Unicode package metadata, whereas UTF-8
capture parsed successfully. Failure diagnostics are bounded in CI annotations;
raw authenticated GitHub logs were unavailable in the cloud Git proxy context.
