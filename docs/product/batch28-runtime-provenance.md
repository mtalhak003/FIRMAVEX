# Batch 28: reproducible MSYS2 runtime provenance workflow

**Candidate-only procedure; not a completed acquisition or release approval.**
Review date: 2026-11-09 (Asia/Karachi). The current production profile is unchanged.
QEMU 11.1.3 must still be rejected by that profile. No runtime is installed,
redistributed, executed or promoted merely by running the read-only tools below.

## Evidence ownership and required gates

Maintain a private, immutable administrative bundle outside the checkout. Use
actual files, original metadata, independently reviewed trust inputs and retained
failures. Separate declared inputs, cryptographically verified package metadata,
static-file observations, native loaded-module observations and legal review.
No boolean supplied by a caller counts as proof of a missing stage.

| Stage | Required evidence | Stop condition |
|---|---|---|
| Acquisition identity | Exact native host/architecture, source SHA, run/attempt, pinned setup action/bootstrap digest, actual repository/signature policy and complete transaction | Missing transaction, partial rolling upgrade or unreviewed source |
| Publisher trust | Independently authenticated public keyring, ownertrust and signer-fingerprint allowlist; pinned verifier binaries | Payload-supplied keys, missing trust, revoked/expired/weak signature or unknown verifier identity |
| Immutable archives | Complete compatible original package archives and detached publisher signatures, with independently reviewed archive/signature manifest hashes | Missing archive/signature or mixing rolling generations to fill an old set |
| Package closure | Signature-verified `.PKGINFO`, exact root versions and all mandatory versioned dependencies/providers/conflicts | Missing or incompatible provider, unknown metadata or changed root |
| Installed ownership | Archive-member to installed-file binding, package ownership, paths and full retained runtime inventory | Unowned/replaced file, unsafe archive path/link, missing DLL/data/plugin or unexplained install transformation |
| DLL closure | Static import graph plus actual native loader/API-set/forwarder/dynamic-load observations for the declared execution scope | Unresolved or unpinned dependency, unexplained search path/module, incomplete native scope |
| License/source delivery | Actual notices, license texts, source tarballs/patches/build recipe identities and corresponding-source delivery plan | Declaration-only evidence or incomplete redistribution/source obligations |
| Reproduction | Native reinstallation from the frozen inputs, exact executable/file identities and scoped product tests | Native identity drift, missing inputs or failed functional/resource checks |

Every stage must close before calling the runtime reproducible and complete for
distribution. Existing tools implement only the limited checks named below.
Missing stages remain **NOT PROVEN**, even if another stage passes.

## 1. Acquire one compatible, signed package generation

Use a disposable native Windows acquisition host and the existing manual
candidate workflow's trusted bootstrap/full `pacman -Syu` transaction. Preserve
its pinned action and bootstrap identities, the effective `PackageRequired` and
`PackageTrustedOnly` policy, transaction logs, `pacman -Q`, `pacman -Qi`, and
the complete installed UCRT64 file inventory. Current exact candidate roots are:

- `mingw-w64-ucrt-x86_64-qemu` **11.1.3-1**;
- `mingw-w64-ucrt-x86_64-gdb-multiarch` **18.1-3**.

A rolling repository may no longer supply these versions. If the consistent
generation cannot be authenticated and recovered, stop. Do not combine an old
QEMU archive with arbitrary current dependencies, weaken signatures, or silently
substitute a new root/version/hash. Do not treat a cache filename or `Validated
By` text as independent signature proof.

Retain every package archive needed for the declared runtime scope and compatible
mandatory dependency closure, including exact detached signatures. Inventory
cached files before deleting an acquisition host. Obtain missing files only from
authenticated publisher sources or a separately authenticated immutable archive.
Record which source delivered each original. A successful download is not yet
publisher verification. No complete authentic archive set was obtained in this
Batch 28 environment; publisher archive/signature probes remain blocked.

## 2. Verify authentic archives with independent signing inputs

Use `tools.windows_candidate_packages` and the procedure in
[Batch 25](batch25-runtime-qualification.md#freeze-a-package-set-without-a-partial-rolling-downgrade).
Its manifest contains original archive and detached-signature SHA-256 hashes.
Supply the keyring/trust database and signer allowlist through an independently
reviewed channel, never from an archive's own payload. Pin actual GPG, bsdtar and
vercmp executable digests independently. The verifier executes no firmware and
performs no package installation.

The verifier checks signatures before reading `.PKGINFO`, strong hash/trust and
allowlist status, exact candidate root versions, mandatory dependency/provider
constraints and conflicts. Archive, signature and verifier identities are checked
for observable changes. Retain its successful lock record and exact input files
together; its synthetic-key tests are not publisher trust.

This lock covers listed archives and mandatory metadata dependencies only.
It does not establish native extraction, payload-to-installed ownership, optional
modules used by the application, dynamic Windows DLL resolution, legal clearance
or an atomic snapshot. Include additional dependencies actually needed by the
advertised scope. Do not release on this lock result alone.

## 3. Bind original payloads to the actual installed runtime

This is a required **future native audit**, not implemented proof in Batch 28.
Use a reviewed, pinned archive reader and fresh owned staging directories. Before
any extraction, reject absolute/traversal paths, case collisions and unsafe
links/reparse points/special entries; retain bounded inventories and cleanup.
Do not weaken shared path validation to accommodate a vendor layout. Any special
case needs its own reviewed identity and ownership rules.

Map each installed runtime executable, DLL, data/plugin and notice to its actual
signed archive member and exact bytes. Account explicitly for legitimate package
installation transformations rather than accepting unexplained differences.
Record complete ownership and archive/member/file hashes. `pacman -Qo`, package
receipts or caller-supplied ownership labels are supporting observations, not
authentication of archive-to-file binding. Windows system files need separate OS
provenance and servicing/build identities; do not call them MSYS2-owned.

The existing candidate file inventory supports only its reviewed closed vendor
hardlink groups. It does not authorize archive extraction or relax shared
security validation. No general untrusted-workload sandbox is claimed.

## 4. Audit ordinary PE imports, then close native loader gaps

The new `tools.windows_candidate_closure` is a bounded, read-only **ordinary
PE32+ x64 static import-graph auditor**. It reads actual files from explicit vendor
and system directories, requires independently reviewed immutable file pins,
rejects missing/ambiguous imports and unsupported delay imports, and detects
observable file/directory changes. It does not execute PE images or read `PATH`
to invent a loader search order. It is not a full PE validity or Windows loader
implementation.

Shared path checks still reject hardlinked files. Direct analysis of native
System32 files, often linked to servicing storage, and large system directories
is not qualified here. Stable independently pinned regular-file copies can be
reviewed for static analysis, but their copy origins and relationship to actual
loaded native modules still require evidence. Do not relax shared checks or
claim a copied directory reproduces Windows loader behavior.

Construct a UTF-8 manifest from independently reviewed actual files:

```json
{"schema_version":1,"roots":["qemu-system-arm.exe","gdb-multiarch.exe"],"vendor":{"qemu-system-arm.exe":{"sha256":"ACTUAL_SHA256","size_bytes":123}},"system":{"kernel32.dll":{"sha256":"ACTUAL_SHA256","size_bytes":456}}}
```

This schema illustration is incomplete and **not a usable trust manifest**.
Replace every placeholder with actual independently reviewed identities and
include every reachable supported import. Do not create empty DLLs, invented
system-file pins or fake API-set files to make an audit pass.

```sh
python -B -m tools.windows_candidate_closure \
  --vendor-bin /outside/repository/ucrt64/bin \
  --system-directory /outside/repository/reviewed-system-files \
  --manifest /outside/repository/import-manifest.json \
  --expected-manifest-sha256 INDEPENDENTLY_REVIEWED_MANIFEST_SHA256
```

Success remains `production_qualified=false`,
`package_ownership_authenticated=false`,
`complete_dynamic_dll_closure_verified=false` and `atomic_snapshot=false`.
Manifest pins are integrity inputs, not proof of their origins. A fail-closed
unsupported import must remain unresolved until independently implemented and
qualified; do not widen the manifest with guesses.

A separately authorized native audit must capture actual loaded modules and
their OS/package identities using reviewed, independently pinned tools across
the declared startup, firmware, replay, cancellation and error paths. Resolve
API-set mappings, forwarded exports, delay/dynamic loads, plugins, architecture,
search policy and system servicing dependencies explicitly. Compare before and
after inventories and reject unexpected modules or writable search directories.
A single `--version` probe cannot establish the dependencies of firmware runs.
Neither static import coverage nor a finite native test scope proves every
possible QEMU feature's dynamic closure. Keep the advertised target scope bounded.

## 5. License/source and immutable release inputs

Inventory actual distributed notices and license texts with hashes and package
owners. Review corresponding upstream source versions, vendor patches, build
recipes/flags, generated components and source-delivery/offer requirements.
The official QEMU/GDB recipe declarations recorded in Batch 26 remain source
references, not binary authentication or redistribution clearance. Include all
distributed dependencies and transformations, not only the two root executables.

An immutable administrative release-input manifest should bind the original
archives/signatures, trust-input provenance/digests, verification-tool identities,
package lock, full archive/member/installed ownership, static and native DLL
audits, notices/source-delivery inventory, exact OS scope and native test evidence.
Store it separately from application user data and candidate test results.
Retain failed checks and unknowns. Review sensitive paths/metadata before any
publication and keep original private records unchanged.

No production installer consumes this proposed release-input manifest yet.
Do not infer production approval from a caller-supplied JSON field or a green
workflow. Positive product qualification and any versioned profile decision
require the separately reviewed [proposal](batch28-positive-qualification-proposal.md).
