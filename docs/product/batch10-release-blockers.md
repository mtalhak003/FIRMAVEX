# Batch 10 release blockers and verification

This is an unsigned preview development branch, not public-beta approval. The
application version is **0.3.0.dev2**. The versioned installer comparison uses
actual Git commit **19cd45736337243c64a2298285781a27499981fa**, version
**0.3.0.dev1**, and the actual candidate commit. Main, research protocols and
historical campaign archives are not changed.

## Evidence-backed file ownership

`python -m firmavex.product.component_inventory APPLICATION --toc
build/desktop/COLLECT-00.toc --repo . --output OUTSIDE_APP/component-sbom.json`
compares collected bytes against build inputs. It records exact matches to
installed wheel RECORD SHA-256 entries, Git blobs, the executing CPython
installation, or OS package registration plus byte identity. Conflicting owners,
modified inputs and unmatched files remain unresolved. Package-manager hardlinks
are accepted only as read-only inputs, with two-pass hashing and handle/path
consistency checks; packaged artifact restrictions are unchanged.

**Verified build-input lineage is not verified upstream component composition,
publisher authenticity or legal clearance.** A Qt library mapped to a PySide6
wheel still needs Qt/subcomponent license review. The original Python-only SPDX
sidecar remains correctly scoped. The new machine-readable file/component SBOM
complements it; it does not silently relabel it as a complete native SPDX audit.

Notices are retained as byte-exact Base64 evidence, with SHA-256, original size,
source package/version and declared license metadata where available. These are
reviewable evidence, not conclusions about compatibility or corresponding-source
obligations. Installed notice coverage and replacement/relinking rights remain
review requirements. SBOM evidence is not a corresponding-source archive.

The audit checks observable Git, application, build-input, TOC and registered-owner
changes across capture. `atomic=false`: it does not lock the filesystem or defeat
all adversarial races. Use a controlled build environment. Supplied build records
are administrative inputs, not independent publisher attestations.

## Bounded payload inspection

ZIP, TAR, TAR.GZ, TAR.XZ and Debian ar/data/control payloads are inspected without
extracting members onto disk or executing them. Paths, duplicates, link escapes,
special files, PAX metadata, encryption, compressed expansion, per-member sizes,
counts and decoder memory are bounded. New Debian packages use XZ compression.
Unsupported formats fail closed or remain explicitly opaque. Windows Inno EXE,
macOS DMG and embedded PyInstaller CArchive/PYZ composition are **not fully
expanded**. Nested member ownership counts are reported separately from regular
collected files; do not hide unknown bytecode members in a top-level percentage.

Distribution artifacts include `component-sbom.json`, collected-file hashes,
build environment, OS package identities where available, notices, checksum lists
and integrity sidecars. The release manifest binds the exact SBOM bytes.

## Actual versioned installation

`versioned-install.yml` rebuilds both actual commits; checks source versions,
Git trees, clean checkout state, executable hashes and installer hashes; and runs
real installers on disposable Windows/Ubuntu hosted runners. The test driver
refuses ordinary local invocation. It must never be run on a personal machine.
No compiler or Python executable is on the installed application's child PATH.
The Python test driver is outside that PATH; hosted CI is not proof of a machine
with Python physically absent.

The baseline installer executes a real built-in ARM example and independently
validates receipts before any upgrade. Every subsequent transition verifies all
saved JSON, SQLite, firmware and evidence bytes. Application startup and read-only
reopening are exercised after upgrade, rollback and reinstall.

Windows: observe an actual Inno file-install entry and cancel the owned installer
tree; require that interruption to occur, rerun the candidate installer to repair,
then test uninstall-new/install-old rollback and candidate reinstall. A completed
installer that escaped cancellation is a **failure**, not an interruption pass.
This qualifies only the observed cancellation point, not arbitrary power loss.
Runtime is a locally generated signed-vendor snapshot with original licenses;
CI does not redistribute that runtime archive as an application artifact.
Windows networking, restricted standard-user tokens and low-disk installer
behavior remain separately unqualified by this driver.

Ubuntu: stop after real `dpkg --unpack`, confirm `install ok unpacked`, then
recover using `dpkg --configure`. This is a phase-boundary interruption, not a
mid-copy crash. An actual 16-KiB tmpfs over this disposable application's `/opt`
directory causes ENOSPC during package installation; it is unmounted and repaired.
The runner's root filesystem is never filled. Restricted output permission and
an actual network-namespace offline example are tested as the ordinary runner
user. Uninstall and rollback must preserve independently stored result archives.

**Check workflow results, not this design description, before claiming any of
these installer qualifications passed.** Failed transitions retain logs and a
`passed=false` receipt. Installer package-manager administrator rights do not
establish that the GUI requires administrator rights. Physical-machine standard
account acceptance remains mandatory and separate.

## Detached signatures and signing credentials

`firmavex.product.artifact_signature` verifies offline Ed25519 signatures using
OpenSSL and an explicitly pinned public-key DER SHA-256. It signs/verifies a
versioned domain-separated message containing the artifact SHA-256 and uint64
size. This authenticates an artifact identity under that key, **not** Windows
Authenticode, Apple Developer ID, notarization or legal approval.

On a trusted offline signing machine, outside the repository:

```sh
python -m firmavex.product.artifact_signature message INSTALLER --output artifact.message
openssl pkeyutl -sign -inkey /PRIVATE/KEY.pem -rawin -in artifact.message -out artifact.sig
openssl pkey -pubin -in publisher-public.pem -outform DER | sha256sum
python -m firmavex.product.artifact_signature verify INSTALLER \
  --signature artifact.sig --public-key publisher-public.pem \
  --trusted-key-sha256 TRUSTED_DER_SHA256
```

Provision the trusted fingerprint through a separately reviewed publisher
channel; a key and fingerprint downloaded together do not establish trust.
Private keys never enter the repository, logs, artifact inventory or ordinary CI.
Use protected signing environments, least-privilege credentials and reviewer
approval for production signing. No production signing credentials were supplied;
no product installer is claimed signed. Ephemeral test keys only verify the
cryptographic implementation and must never become publisher keys.

## Fail-closed approval

Separate mandatory release-gate jobs independently verify artifact/sidecar hashes,
SBOM binding and ownership accounting. They deliberately return nonzero while
ownership/composition, legal/source review, authentic signing, physical consumer
acceptance or installer evidence are missing. They never publish a GitHub Release.
Successful packaging/native jobs do not override a failed approval job.
The assessment currently has no mechanism to accept external approval
attestations; implementing and reviewing that authority boundary remains necessary
before it can approve a release. This limitation is explicit, not a passed gate.

## Isolation and platform limits

Neither fixed probe is a general worker or a qualified sandbox.
`aggregate-isolation.yml` attempts a root-authorized systemd supervisor on a
disposable Ubuntu runner. The root controller must use reviewed source on that
disposable host; it restricts the source directory and interpreter to its own
running checkout. It reads actual kernel control-group limits and grants an
explicit admission marker before the fixed payload begins. Its fixed code tests CPU quota, process-count denial,
forced page-touch memory OOM with swap disabled, and the existing namespace
filesystem/network/process checks. Effective limits and cleanup are read back by
the supervisor. A positive result is fixed-mechanism feasibility, not independent
sandbox validation. Unsupported admission or failed checks return nonzero and
retain evidence; no arbitrary guest command interface is added.

Hosted assessment [39049249940](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39049249940)
observed CPU throttling, process-count denial and a kernel memory OOM kill with
read-back cgroup limits. The combined namespace probe was blocked at Bubblewrap
loopback setup (`Failed RTM_NEWADDR: Operation not permitted`). All preceding
units and the failed namespace unit were cleaned up. This is partial positive
quota evidence and a retained boundary failure, not a passing sandbox assessment.
The exact host-policy cause of that netlink denial has not been established.

The local namespace probe alone does not establish those aggregate controls. This
cloud host has no writable delegated cgroup hierarchy or `/dev/kvm`. Aggregate
CPU/memory/process quotas remain unqualified; untrusted firmware/HDL and public
remote execution stay disabled. Namespace and per-process limit checks do not
establish aggregate quotas or independent isolation validation.

Windows x64 and Ubuntu x64 retain qualified declared ARM/RV32/Verilog workflows,
subject to actual new-commit CI. macOS Apple Silicon is desktop preview only;
unified native RLIMIT_AS admission remains unsupported and its failures remain
visible. Installers are unsigned; macOS packages are unnotarized. Physical testing,
complete corresponding-source review, secure signing and independent security
review remain external release requirements.
