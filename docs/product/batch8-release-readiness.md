# Batch 8 — preview release integrity and readiness

This is a development candidate, not a signed public beta. Research main,
protocols, corpus predicates, strategies, accounting and campaign data are not
modified. The Batch 7 local protocol and saved-result schema remain unchanged.

## Ordinary-user installation and recovery

Download the appropriate **unsigned candidate** artifact from the exact GitHub
Actions distribution run, and retain its sidecars. Hashes establish integrity
relative to those sidecars, not publisher authenticity. Do not bypass OS warnings
under an assertion that the build is signed. Release owners still need signing,
legal and consumer acceptance review.

- **Windows x64:** run the installer without Python or a developer toolchain.
  Open FIRMAVEX; the first-launch wizard explains compatibility. Authorize the
  direct publisher runtime installation, then Check existing runtime. No QEMU/GDB
  binary is newly hosted/bundled by FIRMAVEX. Publisher signature checks and the
  bootstrap checksum remain required. Repair or select a verified historical
  runtime generation after corruption; do not activate a failed inventory.
- **Ubuntu x64:** open the `.deb` in the system package installer. Its dependency
  list installs QEMU ARM/RV32, GDB Multiarch, Icarus and required Qt host libraries
  via the distribution. The portable archive does not install dependencies.
  Missing dependency repair belongs to the system software/package manager.
  Automatic runtime download inside the wizard remains Windows-only.
- **macOS Apple Silicon:** GUI preview only, unsigned/unnotarized. The known
  memory admission blocker prevents unified native execution. Installing a new
  runtime does not qualify or remove that restriction.

Complete setup, create the verified built-in ARM example, explicitly Start
testing, inspect the recorded triggering vector, reproduce, and export. No compiler
is needed. Use separate user-owned project/result directories, never the application
or runtime generation directory. The Backend workspace retains RV32 and Verilog
workflows; HDL simulation is not described as firmware fuzzing. Raw BIN, arbitrary
boards/peripherals and physical hardware are unsupported.

Keep the app, compatible runtime and project locally for offline use: no account,
telemetry or mandatory network service is required for execution. Initial publisher
installation requires internet; trusted offline packs are optional and subject to
existing inventory checks. Offline inspection/reopening never reruns a target.

Runtime rollback preserves verified generations. Application reinstall/upgrade and
uninstall must preserve independent saved receipts byte for byte. Distinct-version
application/database rollback is **not qualified** by reinstalling the same build;
retain backups and use only explicitly compatible installers. Never auto-rewrite
old results to make them appear compatible.

## Release bundle commands (offline)

```sh
firmavex-release bundle-create --repo /trusted/source \
  --artifact /build/FIRMAVEX.deb --output /new/release-sidecars
firmavex-release bundle-verify --bundle /new/release-sidecars --artifact-dir /build
```

These are release-administrator commands. Source: `python -m firmavex.product.release`.
The frozen console supports `FIRMAVEX --firmavex-release bundle-verify ...` without
Python installed. Bundle creation requires the original build Python environment;
a frozen app cannot reconstruct that environment and rejects bundle creation. Existing `create`/`verify` output and manifest version 1
remain unchanged. Bundle commands add:

- The original release manifest and SHA256SUMS (no new result schema).
- `build-environment.spdx.json`, SPDX 2.3 with actual visible Python package
  versions, declared-license metadata and stable hashes of available installed
  notice files. Identical duplicate metadata views merge; conflicting versions,
  license declarations or notice identities fail. Python package managers may
  hardlink notices; those are read-only hashed with observable consistency checks.
- `release-review.json`, explicitly unapproved, unsigned/unnotarized and requiring
  native dependency/corresponding-source audit.
- `bundle-index.json`, binding the four sidecars by SHA-256 and byte size. Verification
  checks every named sidecar, installer identity, checksum-list consistency and
  unsupported approval claims. Extra unnamed files are outside its scope.

Generation records actual source revision/dirty state. SPDX creation time is the
actual source commit timestamp, explicitly **not measured build time**; namespace
identity binds the revision, artifact identities and package inventory. Serialization
is deterministic for identical inputs/environment. Source/build outputs are checked
again across capture, with `atomic=false`; this is not a locked filesystem snapshot.
No absolute package installation paths or credentials are written to this inventory.
Package metadata and notice filenames still require publication review.

**Scope:** this is a build-environment Python SBOM, including build/test packages,
not proof that every listed package is shipped. Native Qt/OS libraries, plugins,
interpreter internals and publisher runtime packs need additional inventories and
legal review. License conclusions are `NOASSERTION`. A package metadata field,
notice link or successful checksum never grants legal clearance. See
`packaging/dependency-review.json` and `packaging/THIRD_PARTY_NOTICES.md`.

Pinned PySide6/PyInstaller versions, actual build dependency inventory, Git revision,
artifact hashes and existing application file inventories aid rebuilds. Transitive
resolver inputs and OS packages are not fully locked; bit-for-bit reproducibility
is **not established**. No signing credentials or fabricated attestation is added.

## Evidence and qualification matrix

| Platform | Current supported scope | Required retained evidence |
|---|---|---|
| Windows x64 | Qualified example workflows with matching runtimes | source/frozen/installed ARM/RV32/HDL, reproduction, cancellation, cleanup, exports, publisher setup |
| Ubuntu x64 | Qualified example workflows with matching runtimes | equivalent native workflows, `.deb` lifecycle, compiler-free demo |
| macOS Apple Silicon | Desktop preview; unified native unsupported | GUI/package checks plus retained failed resource-admission diagnostics |
| Other OS/CPU/boards | Not qualified | no inference from imports or version probes |

Fresh GitHub-hosted runners test isolated installation scenarios. They are **not
physical consumer machines** and contain developer tools. Batch 8 additionally
removes developer tools from the installed GUI's PATH, reopens a saved real result
after reinstall, and checks its hash after reinstall/uninstall. This demonstrates
those bounded properties, not a complete clean-room OS or application downgrade.
Windows lifecycle receipts and real execution archives are retained. Platform CI
also exercises runtime corruption/rollback regression tests. Unit tests explicitly
use synthetic runtime archives and are not native execution evidence.

The distribution workflow produces unsigned EXE/DEB/portable/DMG artifacts and the
complete release-sidecars directory. Product, native, distribution and beta workflows
all include this branch. Native macOS failure remains a failed check, not a skip.
The product workflow archives Linux isolation feasibility separately; a completed
assessment can be blocked, and never authorizes hostile execution.

## Release approval gates / Batch 9

- Independently review/sign off each component license and archive exact
  corresponding source; complete the native SBOM and rebuild dependency locks.
- Authenticode signing with trusted timestamps, post-sign verification and
  secrets in an approved signing service. macOS Developer ID, reviewed hardened
  runtime entitlements, notarization/stapling/Gatekeeper evidence remain absent.
- Physical/VM consumer installation and usability acceptance on supported Windows
  and Ubuntu versions, offline test with external network denied, accessibility,
  constrained disk and non-admin accounts; retain actual evidence.
- Qualify distinct-version upgrade/downgrade and migration without overwriting
  authoritative saved outcomes. Test crash/power-loss recovery and disk exhaustion.
- Independently validate a delegated-cgroup/VM worker and controlled extraction
  before enabling untrusted/remote workloads. See the execution threat model.
- Approve exact release revision/artifact identities, native/installer CI and
  failure evidence, known issues and release notes. No tool in this batch can
  convert preview records into an approved release by a caller-supplied label.

## Local validation evidence (pre-commit, 2026-10-17)

The Linux x64 cloud environment ran actual ARM/RV32/HDL source and frozen examples,
including safe/failure cases, reproduction, export and in-flight cancellation for
all three profiles. The fixed namespace assessment passed twelve boundary/cleanup
checks but remains unqualified for hostile inputs. The final frozen ARM example
also ran with external networking absent in a fresh user/network namespace (only
loopback enabled), and PATH containing only QEMU/GDB launchers, with no Python or
compiler entry. Search charged ten successful attempts and found `[2, 1]`;
reproduction recorded three matching attempts, zero infrastructure failures and
complete retained guest/cleanup receipts. These are bounded examples, not research
campaign results or arbitrary-firmware qualification. Cloud runtime identities
include the local administrative launchers and actual QEMU/GDB version outputs;
native CI separately records publisher/system binaries.

A real Linux `.deb` and five-file release bundle were generated. The frozen console
verified four sidecars and the named installer. Its SPDX document contained 21
Python package entries and 55 installed-notice identities in this environment.
Independent `spdx-tools==0.8.5` parsing/full-document validation reported zero issues.
This standards check does not establish completeness or legal clearance; counts
vary with the actual build environment. The validator is an administrative test
dependency in a separate environment, not bundled into FIRMAVEX.

Pre-commit source state is dirty by definition; these local records do not pretend
to be a clean release attestation. Release artifacts must be rebuilt and associated
with the actual pushed revision by the native/distribution workflows. Fresh CI
runner evidence must likewise not be described as physical consumer-machine proof.
