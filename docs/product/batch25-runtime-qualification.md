# Batch 25: candidate verification and product-boundary checks

**Not production-qualified. No runtime admission or executable/signature policy
has changed. No workflow was dispatched in this batch.** Baseline:
`0942b199b9a8162854953ed29d47456e5bb59dca`; review date 2026-11-09
(Asia/Karachi). This matrix extends the [Batch 24 report](batch24-qualification-gaps.md).

## Implemented, with bounded claims

- `tools.windows_candidate_evidence` reviews a downloaded ZIP **without extraction
  or execution**. It requires an independently obtained ZIP SHA-256, source SHA
  and run ID. It checks safe member names/types, byte/count bounds, duplicate
  names/JSON fields, candidate tool/package/signature-policy records, vendor
  inventory linkage, the approved bundled image identity, all 19 source receipts,
  accounting, cleanup/resource records and required native JUnit cases. Encoded
  XML/declarations, contradictory classifications and missing/failed/skipped
  critical tests fail closed. Additional product records are explicitly not
  reviewed by this source-stage validator. Matching records establish internal
  consistency, not independent guest or publisher authenticity.
- `tools.windows_candidate_product` exercises the **unchanged** public product
  CLI and owned worker. With the candidate runtime, both must reject admission
  with the exact observed identities before creating a run archive. Source/frozen
  executable origins and hashes are distinguished; a caller-supplied executable
  is not proof of installation or build provenance. Failed probes keep accounting
  unknown rather than inventing zero attempts. Native GUI checks require visible
  rejection, idle worker state, no receipts/results and no reproduction action.
- The manual candidate workflow adds source CLI/worker/GUI rejection and a
  PyInstaller build followed by frozen CLI/worker rejection. It keeps the pinned
  Python, ownership/watchdogs, exact candidate identities, trusted signatures and
  complete vendor inventory checks. The 225-second product-test limit remains
  below the existing 240-second selection watchdog; full prefix scans and tool
  probes are included. A timeout fails rather than retries or relaxes admission.
  Frozen binaries are not uploaded as release artifacts or labelled signed.
- `tools.windows_candidate_packages` verifies a **listed offline package set**.
  It requires an externally SHA-pinned manifest, independent public keyring/trust
  database, publisher fingerprint allowlist and independently pinned GPG, bsdtar
  and vercmp executables. It verifies detached signatures before bounded
  `.PKGINFO` reads, rejects weak/untrusted/expired/revoked signatures, and resolves
  mandatory versioned dependencies/provides/conflicts with native `vercmp`.
  Archives, signatures and tools are size-bounded and checked for observable
  changes. Its lock output never installs, downloads or approves a runtime.
  Archive executable payloads are not yet bound to the installed native
  executable hashes; that still requires a separate installation/identity check.

All new tools live outside product packages and frozen entry points. They use
private temporary working directories, not recursive scans of the checkout or
user archives. They are administrative consistency checks, not a hostile-input
sandbox, an atomic snapshot, legal clearance or a complete dynamic DLL audit.

## Qualification matrix

PASS is limited to the evidence named in the last column. New synthetic test
fixtures are never substituted for native results or the missing original ZIP.

| Requirement | Status | Evidence and limit |
|---|---|---|
| Prior native Windows source-stage assertions | PASS | Public run [42505041359](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42505041359), job 128805746981; Batch 24's public-step evidence remains the basis. |
| Original artifact independently downloaded/recounted | NOT PROVEN | Artifact 13626708755 requests still returned `Forbidden`, including escalated access. No archive or missing receipt was reconstructed. |
| Source-stage ZIP validator and negative-input regressions | PASS | Local automated tests; not a validation of the inaccessible original ZIP. |
| Owned real host CLI/worker error propagation | PASS | Local subprocess tests use the approved source, private working directories and existing ownership cleanup; no firmware execution. |
| Candidate-native source CLI/worker/GUI rejection | NOT PROVEN | Tests and workflow are prepared, not dispatched; Linux mocks do not qualify Windows. |
| Candidate frozen build and frozen CLI/worker rejection | NOT PROVEN | Native workflow prepared; no new Windows binary/build result exists yet. |
| Positive product firmware execution/reproduction/export with candidate | NOT PROVEN | Strict existing production gate intentionally blocks it. No gate override, injected executor labelled real, or candidate production profile was introduced. |
| Installed application and distinct-version upgrade/rollback/uninstall | NOT PROVEN | An `installed` command label always retains `installation_verified=false`; no installer-origin or lifecycle evidence was manufactured. |
| Offline package signature/closure verifier | PASS | Local metadata/resource/failure tests and a real GnuPG test with an ephemeral synthetic key; not a publisher-package verification. |
| Authentic complete immutable vendor package set | NOT PROVEN | No approved archives, independent publisher keyring/tool pins or complete lock inputs were supplied; bsdtar/vercmp are unavailable locally. |
| Dynamic DLL closure, corresponding source and redistribution rights | NOT PROVEN | Mandatory signed metadata dependencies/license declarations alone cannot establish these. |
| Current QEMU 11.1.3 membership in production profile | FAIL | Intentional unchanged version/hash mismatch; production rejection remains required. |
| Standard-user/offline/low-disk/accessibility/public-beta acceptance | NOT PROVEN | No new consumer-machine, signing or installation trial was performed. |

## Review the original archive locally

Obtain the original ZIP through an authorized GitHub account. Preserve it and its
displayed digest; do not repackage before checking. From this reviewed checkout:

```sh
python -m tools.windows_candidate_evidence /path/to/original-candidate.zip \
  --sha256 8e1b9f67b7f8f13de6c5b5b205e4f19ffa6414cc19a74e174e3147a810b5d9ae \
  --revision 237e9f64352d1aac7105f7461db5d76dacf57612 --run-id 42505041359
```

Failure returns nonzero and bounded error codes. Success still records
`production_qualified=false` and lists authenticity/release limitations. Extra
future product reports require separate review; a passed source-stage check does
not silently certify them. The firmware anchor is this checkout's approved
bundled-image manifest, so use a reviewed matching image when auditing an old run.

## Freeze a package set without a partial rolling downgrade

1. On a disposable native Windows acquisition host, retain the signed full
   transaction, `pacman -Q`, `pacman -Qi`, effective signature policy and bootstrap
   identity. Preserve the complete package archives and detached publisher
   signatures, including every mandatory dependency. A package listing alone is
   insufficient. Recover missing archives/signatures from authenticated publisher
   sources or stop; do not fill an old set with new rolling dependencies.
2. Independently review and pin the archive/signature hashes in a UTF-8 manifest:

   ```json
   {"schema_version":1,"packages":[{"archive":"ACTUAL-NAME.pkg.tar.zst","sha256":"ACTUAL_ARCHIVE_SHA256","signature_sha256":"ACTUAL_SIGNATURE_SHA256"}]}
   ```

   The names/hashes above are placeholders, not usable package identities. Include
   QEMU `11.1.3-1`, GDB `18.1-3` and their compatible closure. Supply a separate
   public keyring directory with `pubring.gpg` or `pubring.kbx` and `trustdb.gpg`;
   do not import keys or ownertrust supplied by the package payload. Independently
   review publisher fingerprints and verification-tool identities.
3. Run the verifier with those real trusted inputs. This is a template, not a
   claim that the required inputs have been obtained:

   ```sh
   python -m tools.windows_candidate_packages \
     --bundle /path/to/archives --manifest /path/to/reviewed-manifest.json \
     --expected-manifest-sha256 ACTUAL_MANIFEST_SHA256 \
     --keyring /path/to/independent-public-keyring --signer ACTUAL_TRUSTED_FINGERPRINT \
     --gpg /path/to/gpg --gpg-sha256 ACTUAL_GPG_SHA256 \
     --bsdtar /path/to/bsdtar --bsdtar-sha256 ACTUAL_BSDTAR_SHA256 \
     --vercmp /path/to/vercmp --vercmp-sha256 ACTUAL_VERCMP_SHA256
   ```

   Save successful stdout as a **new administrative lock record**, keep the
   manifest/archives/signatures/key provenance immutable, and review notices,
   source obligations and dynamic DLL resolution separately. No production
   installer consumes this lock automatically. Missing/ambiguous dependencies or
   unverifiable signatures are failures, not warnings to ignore.

## Next decisions

The smallest next action is authorized retrieval and local validation of the old
ZIP, followed by an explicitly approved dispatch of the reviewed candidate
workflow. Its new native results can establish rejection paths and frozen startup
compatibility, not positive candidate product execution. A positive product-path
lab design and any subsequent versioned production profile require separate
review; do not patch admission or mark synthetic injection as real execution.
Actual package-set capture and legal/source review remain separate prerequisites
for reproducible runtime distribution. Public-beta readiness is not established.

## Local validation

Focused selection: **259 passed, 5 native Windows skips**. Broader selection:
**1,037 passed, 21 skipped, 27 deselected**. The skips concern native-only checks
or missing ARM/RV32/HDL tools; the broader selection excludes `actual_`-named cases.
The real GnuPG synthetic-key fixture passed in the focused suite. No result here
is a new native Windows measurement. Commands:

```sh
QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_windows_candidate_evidence.py tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_product.py tests/desktop/test_windows_candidate_rejection.py \
  tests/product/test_windows_runtime_candidate.py tests/product/test_platform_support.py

QT_QPA_PLATFORM=offscreen /workspace/firmavex-batch7-venv/bin/python -m pytest -q -ra \
  tests/product/test_windows_candidate_evidence.py tests/product/test_windows_candidate_packages.py \
  tests/product/test_windows_candidate_product.py tests/product/test_windows_runtime_candidate.py \
  tests/product/test_platform_support.py tests/product/test_ci_diagnostics.py \
  tests/product/test_runtime_setup.py tests/product/test_runtime_pack.py tests/product/test_tools.py \
  tests/product/test_worker.py tests/product/test_protocol.py tests/product/test_supervisor.py \
  tests/product/test_runtime.py tests/product/test_services.py tests/product/test_store.py \
  tests/product/test_arm_reproduction_summary.py tests/product/test_packaging.py \
  tests/product/test_packaging_universal.py tests/backends/test_records_security.py \
  tests/backends/test_process_security.py tests/desktop -k 'not actual_'
```

Workflow validation passed using publisher-checksum-verified actionlint 1.7.7
(`actionlint -shellcheck= .github/workflows/windows-runtime-candidate.yml`).
ShellCheck/PowerShell were unavailable; shell behavior has bounded fixture tests,
and native PowerShell execution remains pending. Python syntax, documentation
references, all new-file whitespace, and `git diff --check` also passed.
