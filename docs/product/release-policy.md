# Preview releases and verification

`product/desktop-batch7` is a product development branch. It is not research main
and is not automatically a qualified public release. No integration branch or
merge into main is necessary for this batch.

Windows x64 and Ubuntu x64 have native **example** qualification. That is scoped
to the recorded tools, machine contracts and source/frozen/installed workflows;
it does not qualify arbitrary firmware or every consumer machine. macOS Apple
Silicon is a desktop preview; native unified execution remains unsupported.
Required failed native checks and their evidence remain published, not skipped.

A qualified release additionally needs clean source revision, matching artifact
identities, full native/security/installation results, legal review, documented
upgrade/removal, signing/notarization decisions and an explicit release approval.
The new tooling only creates **preview** sidecars; it cannot upgrade a build to
qualified by accepting a caller-supplied label.

## Create and verify sidecars offline

```sh
firmavex-release create --repo /path/to/trusted/FIRMAVEX \
  --artifact /path/to/build/FIRMAVEX.deb --output /path/outside/repo/new-sidecars
firmavex-release verify --manifest /path/outside/repo/new-sidecars/release-manifest.json \
  --artifact-dir /path/to/build
```

Source equivalents use `python -m firmavex.product.release`. Frozen consoles use
`FIRMAVEX --firmavex-release create|verify ...`. Output must be fresh. Existing
artifacts are never modified/extracted/executed by the sidecar tool.

Versioned release-manifest.json records actual Git revision/dirty state and tracked-diff digest, host and
application versions, selected installed build dependencies and declared license
metadata, stable observed artifact SHA-256/size identities, unverified signing and
notarization, and `atomic=false`. SHA256SUMS covers the named artifacts. Stable
captures use bounded two-pass hashes, metadata comparisons and a second inventory
check; detected file/Git changes fail. These checks do not lock a filesystem or
provide an atomic/adversary-proof snapshot. Build outputs belong outside the
checkout; ignore rules do not prove a build is reproducible.

Verification establishes named file integrity relative to the supplied manifest,
not its authenticity, signatures, a complete dirty/untracked source snapshot, reproducible bit-for-bit builds, correct license
clearance or execution qualification. Extra unlisted files are outside its scope.
Publish checksums through an authenticated release channel and independently
verify signatures where available. No signed/notarized claim is made here.

## Licensing and packaging audit scope

FIRMAVEX-owned code/examples remain MIT. QEMU, GDB and Icarus runtimes are not
silently bundled by the application or sidecar tool; publisher installation and
license/source obligations remain separate. PySide6/Qt, Shiboken, PyInstaller and
pyelftools versions/licenses must be reviewed against packaging/THIRD_PARTY_NOTICES.md
and packaging/licenses. Declared distribution metadata is an inventory aid, not
legal advice or redistribution permission. Preserve existing notice files.

Existing OS installers and native workflows still exercise reinstallation,
removal and preservation of independent project/result directories. Runtime
repair/rollback retains its verified-generation behavior. Application downgrade
and arbitrary cross-version migration are **not** newly qualified. A rollback
must use a known compatible installer and retain untouched user archives; no tool
here rewrites SQLite or saved receipts.

Signing/notarization credentials and consumer SmartScreen/Gatekeeper qualification
remain beta blockers. Source and frozen tests are not clean-machine consumer
installation proof. Release owners should retain native logs, manifests, dependency
inventories and failed-platform evidence alongside the exact installer artifacts.

The Windows RV32/HDL public compatibility catalog now records the exact executable
hashes from Batch 6's successful source/frozen/installed native job. This removes
the need for an administrator candidate override for **those matching tools**.
Different versions remain gated pending native evidence. Batch 7's local-interface
source/frozen qualification explicitly unsets the candidate override to exercise
that public path; the gate itself is unchanged. No macOS entry is added.

Batch 8 adds opt-in hash-bound release bundles and an SPDX build-environment
inventory, without changing the original preview manifest schema. See
[Batch 8 release readiness](batch8-release-readiness.md) for commands, SBOM scope,
installer evidence and outstanding approval gates, and the
[execution threat model](../security/execution-threat-model.md) for the fixed Linux
namespace diagnostic and explicit limits on isolation claims.
