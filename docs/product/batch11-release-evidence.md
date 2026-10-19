# Batch 11 release evidence

Work continues on `product/desktop-batch11` from
`d9e3877fbe71489a60640855ce9994c41e852b35`, with no pre-existing working-tree
changes. Main and frozen research inputs are outside this batch.

## Component and license evidence

The component SBOM now retains exact byte-verified TOC inputs even for files
whose registered owner is unknown. Generated executables, Python ZIP archives,
and vendor runtime DLLs are not assigned a component simply because their build
input or filename is known. Those inputs are rehashed during final capture
validation, including unresolved inputs. Component ownership and build lineage
remain separate claims.

The release gate verifies every retained Base64 license notice against its
recorded SHA-256 and byte count, and reports components with no notices. A missing
notice blocks the evidence gate. A matching notice does not establish license
compatibility, delivery compliance, relinking rights or corresponding-source
availability. Those require independent review.

The starting-commit Linux diagnostic found four unresolved collected files: the
two generated executables, `base_library.zip`, and CPython's `xxsubtype` extension.
Windows additionally included runtime DLLs collected from the build interpreter
and a Java installation. MacOS reported 124 unresolved files out of 275. These
observations are from hosted run
[39054464142](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39054464142),
not new-commit qualification. Full diagnostics remain in uploaded artifacts;
exceeding the optional public annotation budget no longer fails artifact capture.

## Secure review attestations

`firmavex.product.release_attestation` accepts an offline Ed25519-signed review
bound to the SHA-256 and size of the exact `release-manifest.json`. Verification
uses the existing domain-separated artifact-signature framing. A separately
provisioned trust policy authorizes particular review checks for a pinned public
key and named reviewer. Unknown/revoked keys, unauthorized checks, missing evidence
identities, future/expired reviews, changed manifests and signature tampering fail
closed. No production trust policy or private signing key is shipped.

The signed JSON has exactly these fields:

```json
{
  "schema_version": 1,
  "kind": "firmavex_release_review_attestation",
  "subject": {"sha256": "<release manifest SHA-256>", "size_bytes": 123},
  "reviewer": "<independently authorized reviewer>",
  "key_sha256": "<trusted public key DER SHA-256>",
  "issued_at": "2026-10-19T00:00:00Z",
  "expires_at": "2026-10-20T00:00:00Z",
  "checks": ["component_license_and_corresponding_source_review"],
  "evidence": {
    "component_license_and_corresponding_source_review": {
      "sha256": "<review evidence SHA-256>", "size_bytes": 456
    }
  }
}
```

Evidence hashes identify the review documents; this verifier does not independently
validate their substantive conclusions. Preserve and review those documents.
The administrative trust policy is:

```json
{
  "schema_version": 1,
  "keys": {
    "<trusted public key DER SHA-256>": {
      "reviewer": "<independently authorized reviewer>",
      "checks": ["component_license_and_corresponding_source_review"]
    }
  }
}
```

The other authorized review categories are
`embedded_executable_and_installer_composition`, `physical_consumer_acceptance`
and `versioned_installer_lifecycle`. No review can override collected ownership,
notice integrity, clean-source checks or authentic installer signing. Signing a
review does not sign an installer. Revocation removes the key from the independent
policy. The verifier requires a trusted clock for validity checks.

Use the existing `artifact_signature message` command and offline signing process
on the review JSON, then supply the review to the release gate:

```sh
python -m firmavex.product.release_approval \
  --sbom dist/component-sbom.json --bundle dist/release-sidecars \
  --artifact-dir dist --output approval.json --require-approved \
  --attestation review.json --signature review.sig --public-key reviewer.pem \
  --trust-policy /INDEPENDENT/review-trust-policy.json
```

Never use a policy supplied by the candidate as the source of trust. No external
review or publisher credential has been supplied for this batch. Mandatory release
gates continue to block unsigned candidates with missing review evidence.

## Linux diagnostics and Windows qualification

The root namespace diagnostic previously stopped before writing evidence because
`sudo` removed `GITHUB_ACTIONS`. Its disposable CI invocation now explicitly
passes that non-secret marker. It does not relax namespace, AppArmor, cgroup or
network policy. Fixed probes remain diagnostics, and untrusted execution stays
disabled. MacOS annotation capacity is handled independently of evidence capture.

Batch 11 pushes now run the aggregate isolation, versioned installer, distribution,
beta and unified desktop workflows in addition to product and evidence jobs.
Windows qualification retains the owned Inno descendant-tree waiter and bounded
failure logs. Candidate reinstall now checks the installed revision/executable
identity and GUI startup before reopening saved results and final uninstall.
Actual native CI success is required before claiming platform qualification.
Standard-user tokens, Windows low-disk installation, independently enforced offline
Windows networking and physical consumer acceptance remain external requirements.

## Local validation

On the current Linux host with Python 3.14, the product regression suite passed
**750 tests, 4 skipped** after installing the project and test/build dependencies.
An additional focused run covering the final unresolved-input consistency and
namespace-cleanup cases plus attestation checks passed **31 tests**. These runs
exercise real OpenSSL signatures with disposable test keys. They do not replace
Windows/macOS native CI or the locked Python 3.12 release build environment.

## Hosted follow-up and Python 3.14 regression

Implementation commit `7965ac72907054130ca0e31fa56fdcdf71819744` passed
[all three native component captures and the namespace diagnostic](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862810).
The diagnostic retained AppArmor audit events showing `unprivileged_userns`
capability denials for `setpcap` and `net_admin` during the fixed Bubblewrap
reproducer. This is direct evidence of a host policy restriction. No host policy
was weakened to obtain a passing isolation verdict.

The [aggregate assessment](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862786)
again passed CPU throttling, process-count denial and kernel memory OOM checks,
but failed at `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`.
All recorded units reported verified cleanup. Aggregate sandbox qualification
remains blocked. The macOS unified workflow still fails its documented native
`RLIMIT_AS` admission; the limit is enforced without a bypass.

The broader local backend/research regression run passed 1,558 tests and skipped
27, exposing one file-size test issue on Python 3.14. Its bare buffered `write`
could defer the file-size error to an ignored destructor exception and exit zero.
The test now explicitly closes the stream through a context manager, preserving
the actual file-size and process-reaping assertions. Production resource limits
and frozen research data are unchanged.
