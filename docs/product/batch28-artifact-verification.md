# Batch 28: retrieve and verify original candidate evidence

Review date: 2026-11-09 (Asia/Karachi). This is an administrative, read-only
procedure. It does not dispatch CI, extract executables, execute firmware or
approve a runtime. Keep downloads and verification output outside the repository.

## Bound inputs for this review

| Input | Required value |
|---|---|
| Repository | `mtalhak003/FIRMAVEX` |
| Source branch | `product/desktop-batch11` |
| Source SHA | `c42cdd000dbd117dee558fd346aa8b653ac7bf3f` |
| Run / attempt | `42618949135` / `1` |
| Job | `129165814000` |
| Artifact ID | `13675538108` |
| Artifact name | `Windows-UNQUALIFIED-runtime-candidate-c42cdd000dbd117dee558fd346aa8b653ac7bf3f` |
| Original ZIP SHA-256 | `f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8` |

Fresh public run, attempt and job pages confirm these metadata associations.
Do not reuse IDs or digests from other runs. These values describe the existing
Batch 27 run, not any future run at the Batch 28 commit.

## Current retrieval result

The Actions metadata API returned `Forbidden`. The exact authenticated ZIP API
request also returned `Forbidden`, including escalated execution. Public run and
job pages returned HTTP 200; the public artifact URL returned HTTP 404.
**No original ZIP was retrieved. Neither required-scope verifier was run against
the original artifact.** This is a retrieval blocker, not an artifact-verifier
failure and not proof that the artifact has expired. Failed response bodies and
empty files were not renamed as ZIPs or substituted for evidence.

## Authorized browser download

1. Sign in to a GitHub account authorized to read Actions artifacts for this
   repository. Open [the exact attempt][attempt] and confirm the tuple above.
2. Download artifact 13675538108 from that run. Preserve the original ZIP bytes
   and accompanying displayed digest. Do not extract/repackage it before hashing.
3. Place the ZIP in a fresh private folder outside the checkout. Review with the
   exact verifier command below. Browser access must not require disabling host
   security controls or sharing credentials in a report.

## Reproducible API acquisition in Bash / WSL

Use an already authorized `gh` installation. `actions:read` access may be needed
for a private repository/token; a `Forbidden` response alone does not identify
whether the blocker is account permissions, a service policy or this environment's
network transport. Do not print tokens, paste credentials into scripts, or use
`gh auth token` in logs. The commands below are for **Bash**, not legacy
PowerShell, whose native binary redirection can alter ZIP bytes.

Run from a reviewed checkout containing the Batch 28 administrative tools:

```bash
(
  set -euo pipefail
  set -o noclobber
  umask 077
  ulimit -f 131072
  mkdir -p "$HOME/firmavex-qualification"
  review_dir=$(mktemp -d "$HOME/firmavex-qualification/batch28.XXXXXXXX")
  timeout --kill-after=5s 120s gh api repos/mtalhak003/FIRMAVEX/actions/artifacts/13675538108 \
    > "$review_dir/artifact-metadata.json"
  timeout --kill-after=5s 120s gh api repos/mtalhak003/FIRMAVEX/actions/runs/42618949135/attempts/1 \
    > "$review_dir/attempt-metadata.json"
  timeout --kill-after=5s 120s gh api repos/mtalhak003/FIRMAVEX/actions/artifacts/13675538108/zip \
    > "$review_dir/original-candidate.zip.partial"
  printf '%s  %s\n' \
    f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8 \
    "$review_dir/original-candidate.zip.partial" | sha256sum --check --strict -
  test ! -e "$review_dir/original-candidate.zip"
  mv -n "$review_dir/original-candidate.zip.partial" "$review_dir/original-candidate.zip"
  python -B -m tools.windows_candidate_artifact "$review_dir/original-candidate.zip" \
    --artifact-metadata "$review_dir/artifact-metadata.json" \
    --attempt-metadata "$review_dir/attempt-metadata.json" \
    --sha256 f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8 \
    --revision c42cdd000dbd117dee558fd346aa8b653ac7bf3f \
    --run-id 42618949135 --attempt 1 --artifact-id 13675538108 \
    > "$review_dir/verification.json"
  printf 'Review directory: %s\n' "$review_dir"
)
```

Any nonzero acquisition, checksum or verification result stops the procedure.
GNU `timeout` bounds each request; the subshell's file-size limit bounds failed
download output conservatively to at most 128 MiB. This Bash/WSL procedure needs
GNU coreutils and an existing suitable Python environment for the reviewed tool.
Retain a failed `.partial` only as a failed download, not original evidence.
The fresh directory and no-clobber redirection prevent routine overwrites; they
do not lock out a hostile concurrent writer or create an atomic filesystem
snapshot. No tools are installed by this procedure.

The wrapper checks strict bounded metadata, repository/run/source/artifact
identity, completed manual attempt, the declared digest and creation-time
consistency. It invokes the existing ZIP verifier with **both required scopes**.
Timestamp consistency does not authenticate artifact uploader identity or prove
the artifact's exact job of origin; retain independently reviewed GitHub context.
Downloaded JSON can be forged by a caller, so a successful wrapper result is
record consistency, not an authentication or attestation claim.
Metadata is reread after ZIP review; observable changes reject the capture.
Success reports stable observed consistency and `atomic_snapshot=false`.

For a ZIP obtained through the authorized browser, independently run:

```sh
python -B -m tools.windows_candidate_evidence /outside/repository/original-candidate.zip \
  --sha256 f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8 \
  --revision c42cdd000dbd117dee558fd346aa8b653ac7bf3f \
  --run-id 42618949135 --require-product-paths --require-installed-path
```

The verifier never extracts, runs or repairs archive contents. It checks the
19 ordered source receipts and eight accounting cases, actual ZIP digest,
runtime/package/file inventories, source/GUI/frozen rejection reports, installed
lifecycle and console identity links, required native JUnit cases, and cleanup.
Its output always retains `production_qualified=false`. Matching records cannot
replace runner authentication, publisher signatures, complete DLL closure or
independent build-origin review. The installer and GUI identities are retained
producer declarations; their binary payloads are not included for independent
rehashing in this evidence ZIP.

Archive original ZIP, API responses and verification output privately together.
Review paths, filenames, package metadata and diagnostics before publishing
redacted derivatives. Preserve the originals and describe any redaction rather
than changing their recorded digest. Do not fabricate or reconstruct missing
receipts. On failure, keep the original result and investigate its exact code.

[attempt]: https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135/attempts/1
