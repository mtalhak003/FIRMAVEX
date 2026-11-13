# Batch 32 — Windows runtime and packaging qualification plan

**Documentation-only publication:** this snapshot preserves the Batch 32 plan
from the development line. Implementation/evidence links are pinned to
`19f9eb0254fd0162db601e5ed82055baa92e7a5d`; those files are not introduced
into `main` by this publication. No runtime or release approval follows.

**Status: research and proposal only; production qualification remains incomplete.**
Baseline: `2feb722349cbc3534c1ac614031f0404d477ac30` on the
`product/desktop-batch11` development line. Review/source-check date:
**2026-11-12 UTC / 2026-11-13 Asia/Karachi**. This date records this review,
not a new Windows test or a historical execution date.

## Executive recommendation and evidence classes

Prefer **Route B, a completely captured and separately qualified candidate**, as
the sustainable runtime path. First permit a bounded Route A recovery assessment
only after approval: recovering the exact admitted bytes and their compatible,
authenticated closure could avoid a profile change. Neither route is ready for
installation or distribution on the evidence currently available.

For the first distribution qualification, prefer the existing PyInstaller/Inno
architecture with **trusted RSA Authenticode coverage of the application and
installer lifecycle**, plus independently reviewed runtime trust. Investigate
Azure Artifact Signing Public Trust if the publisher is eligible; otherwise
evaluate a trusted CA's OV service/certificate and protected key custody. This
selects an investigation direction, not a purchase or signing authorization.
Microsoft Store MSIX is a useful second route, with free Store package signing,
but requires a new packaging/identity and runtime-delivery qualification.

Evidence labels throughout this plan:

- **Inspected source:** current repository code/configuration at the baseline,
  or the official documentation sources listed below; not execution evidence.
- **Historical CI observation:** retained reports of named runs at their old
  revisions; not a rerun or independently reverified artifact in Batch 32.
- **User report:** observations supplied by the operator, retaining their scope.
- **NOT PROVEN / proposal:** missing evidence or work requiring future approval.

No firmware, installer, runtime probe, package acquisition, signing, CI dispatch
or release was performed for this plan. Public documentation was read in memory;
no runtime/archive/SDK was downloaded. Existing research and private evidence
remain outside this review.

## Established baseline and unresolved host observations

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| [Production profile](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/firmavex/product/platform_support.py), [discovery](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/firmavex/product/tools.py) | Exact Windows x64 executable admission and capability probes described below | Complete dependency closure, host application-control acceptance or current product qualification |
| [Batch 23C investigation](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/batch23-acquisition-investigation.md) | Original compatible immutable runtime set was not authenticated; prior publisher requests were blocked | That old packages do not exist, or that a guessed package filename is genuine |
| [Batch 28 readiness](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/batch28-release-readiness.md); [run 42618949135](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135) at `c42cdd000dbd117dee558fd346aa8b653ac7bf3f` | Historical CI-observed low-level ARM/resource tests, source/GUI/frozen/installed **rejection**, narrow installer/reinstall/uninstall checks | Positive candidate product execution, complete DLL/license evidence, distinct-version upgrades or consumer acceptance |
| [Later user-reported original ZIP verification](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/development-progress.md#november-9-2026--windows-candidate-evidence-and-release-preparation) | Reported 19 receipts; 97 JUnit passed, 10 skipped, zero failures/errors | Independent inspection of original bytes here; production approval |
| [November 12 host/UI and manual GUI reports](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/batch31-windows-validation.md#user-provided-manual-windows-gui-checks) | Source-module GUI, static example inspection and save/reopen observations; separately reported 171-pass/1-skip host/UI selection at `f8efe1e109d608789a75f154a8516b8e053bc014` | Guest execution, accepted launcher, frozen/installed execution or release readiness |

The reported original Batch 27 ZIP SHA-256 remains
`f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`.
Original bytes were not acquired or reverified in this batch.

The user reported that the Python-module GUI launched, while the generated
`firmavex-desktop.exe` launcher and MSYS2 `msys-2.0.dll` during mintty startup
were blocked. Code Integrity Event **3077** named policy
`0283ac0f-fff1-49ae-ada1-8a933130cad6`; `CiTool --list-policies` reportedly showed
enforced **VerifiedAndReputableDesktop** (Smart App Control). This GUID is a
reported host observation, not a universal policy identifier. Original
event/file/time correlation, OS build, file signatures and hashes remain
unreviewed. A pip-generated launcher is not necessarily the PyInstaller EXE.

Separately, the user's QEMU was the **11.1.0 development build**
`v11.1.0-12130-ge470268ff4`, and GDB **16.3.90.20250906-git** reported
`--without-python`; its Python probe exited 1 despite successful version and
configuration commands. The manual Validate action reported
`dependency_probe_failed`; the earlier wizard's precise failure stage was not
established. These capability/version failures and host policy blocks are
independent blockers. Static ELF validation (`stable_observed`, `atomic=false`)
and empty execution/result controls do not prove firmware execution.

## A. Runtime identity, capabilities and recovery decision

The existing profile is `msys2-ucrt64-qemu11.1.2-gdb18.1-v1`, version 1,
Windows **x64** (`AMD64`/`x86_64`). Preserve these exact values:

| Tool | Expected first version line | Expected full-file SHA-256 |
|---|---|---|
| QEMU | `QEMU emulator version 11.1.2` | `1247e03f58f2e845ff516e0cc951b67d0ee5dd5d6bcbe89faedbec692641b244` |
| GDB | `GNU gdb (GDB) 18.1` | `f867205234b5c61ad53bbb70db25462566b1742b409eb345f7f0178fd388f236` |

Admission is necessary, not sufficient. Discovery also requires QEMU's exact
`mps2-an385` machine entry, GDB ARM architecture support, and working **embedded
Python plus `hashlib`** producing the expected SHA-256 capability marker.
Auto-loading is disabled for probes; identities are checked around discovery.
The runtime must contain matching Python/native modules, data, plugins and
DLLs, not merely a GDB EXE that prints the right version. The compiler-free
bundled example does not require installing GCC; compiler-based workflows are
a separate dependency scope.

### Runtime decision matrix

| Dimension | Route A — recover admitted 11.1.2 / 18.1 | Route B — separately qualify a captured candidate |
|---|---|---|
| Availability | **NOT PROVEN.** Actual original archives, signatures and compatible dependencies have not been recovered. The old QEMU `11.1.2-1` filename was a probe, not a verified package identity. | Historical candidate roots: QEMU `11.1.3-1`, GDB multiarch `18.1-3`. Their full immutable generation is also **NOT PROVEN** available now. |
| Security | Keep current admission; authenticate originals and all used dependencies. Existing host policy can still reject exact admitted bytes. | Keep production rejection. Signed pacman packages establish a different trust layer from PE Authenticode and SAC acceptance. Candidate tests cannot override admission. |
| Reproducibility | Reinstall exact recovered generation without resolving gaps from a rolling repository; match admitted EXE bytes. | Freeze one consistent, fully upgraded generation, all original signatures and installation inputs; reinstallation must reproduce final identities. |
| Engineering effort | Potentially shorter product-path validation if full originals survive; archive/closure recovery may fail. No safe executable-only downgrade. | More native testing and a separately reviewed profile decision; stronger long-term provenance process if all inputs are retained. |
| Existing native evidence | Historical production-profile ARM record, not current build or consumer acceptance. | Historical low-level native ARM/security passes and product rejection; positive source/frozen/installed journeys remain blocked by design. |
| Remaining decision | Approve bounded authenticated recovery, with explicit stop if originals/closure cannot be established. | Approve candidate scope/trust inputs and isolated positive qualification design; later, separately approve any production profile. |

Historical candidate QEMU 11.1.3 SHA-256:
`f7e69cf3c284bad6a3b1c4159d2a88001f285c28f890dd2f8e56186682840cc7`;
GDB's candidate digest matched the admitted GDB digest above. A package version
or historical hash is not proof of present availability. If that exact candidate
generation cannot be recovered, proposing a different generation requires a new
declared candidate and approval, not a silent substitution.

MSYS2 supports full system upgrades, not arbitrary partial rolling downgrades
[S15, S16]. Do not combine old QEMU with newly resolved rolling DLLs. Neither
a source tag nor an upstream source signature authenticates an MSYS2 binary
package or establishes its installed dependency closure.

### Immutable artifact and dependency requirements — both routes

Use the existing [Batch 28 provenance procedure](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/batch28-runtime-provenance.md).
Each stage is required; missing stages remain NOT PROVEN:

1. **Original inputs:** archive and detached-signature bytes, exact root and
   dependency versions, hashes, authenticated origins and acquisition transaction.
   Record setup/bootstrap/verifier versions, source SHA, Windows build and x64
   host scope. Cache names and a `pacman -Q` list are supporting records only.
2. **Independent publisher trust:** approved MSYS2 keyring, ownertrust and signer
   fingerprint allowlist obtained independently of payloads; pinned verifier
   tools. Preserve mandatory trusted signatures, strong digests and validity
   checks. Never substitute synthetic test signatures for vendor trust.
3. **Compatible closure:** signature-verified metadata, exact mandatory
   dependency/provider constraints and conflicts, plus optional components used
   by the advertised flows. Freeze installer/bootstrap dependencies separately
   from execution dependencies. Do not require mintty for execution merely
   because it was the first reported block; do not omit required MSYS DLLs either.
4. **Payload binding:** safe, bounded archive/member-to-installed-file ownership,
   all file hashes, installation transformations and permissions. Reject unsafe
   paths, links, reparse points, collisions, missing files and unexplained changes.
   Record Windows-system dependencies under their own OS provenance.
5. **Loader closure:** ordinary PE imports plus native API-set/forwarder,
   delay/dynamic load, plugin, Python stdlib/extension and search-directory
   observations across declared execution/error paths. The existing bounded
   static import tool is not a complete Windows loader audit. Reject unexplained
   dependencies and untrusted or uncontrolled writable module search locations.
   Per-user owned locations need declared access controls, reviewed file identities
   and native resolution evidence; they are not automatically unsafe or qualified.
6. **Legal evidence:** actual notices/license texts and ownership, corresponding
   source/patches/build recipes and source-delivery obligations for every
   distributed component. QEMU/GDB license labels and package signatures alone
   do not grant redistribution clearance. Include Qt/Python/application payloads.
7. **Replay:** fresh native installation from only the reviewed locked inputs;
   compare final runtime inventory, capability probes, module identities and
   product-path outcomes. Preserve originals, failures and unknowns outside user
   projects; redact private metadata before publication. Consistency checks are
   not an atomic filesystem snapshot or hostile-workload isolation.

The candidate package verifier intentionally checks its specific candidate roots;
do not relax it into an old-profile acceptance path. Route A needs a separately
reviewed verification scope if existing tooling cannot express its inputs.

## B. Smart App Control, signing and distribution

Smart App Control, SmartScreen reputation and enterprise App Control are related
but distinct mechanisms. Microsoft's SAC signing guidance specifies trusted
**RSA** certificates and says ECC signatures are unsupported [S1, S2]. A trusted
signature is not a universal policy override or proof that code is safe. Confirm
final files under the actual enforced host policy. Never disable SAC/Defender,
change Code Integrity policy or propose file/metadata manipulation as a bypass.

### Windows distribution decision matrix

| Route | Trust, cost and eligibility | Engineering implications and unresolved evidence |
|---|---|---|
| Existing PyInstaller + Inno, trusted CA OV Authenticode | Publicly trusted RSA chain, identity verification, approved protected key custody and timestamping. Microsoft gives an indicative **US$300–500/year** OV estimate [S3]; obtain current CA, token/HSM/service and renewal quotes. | Smallest packaging change. Sign/verify all required app PE payloads and installer lifecycle; independently establish runtime trust. No certificate/account exists in this work. Native SAC, clean-user and offline tests still required. |
| Same distribution, Azure **Artifact Signing Public Trust** | Managed signing, Entra/Azure prerequisites and eligibility below [S9–S13]. Microsoft MSIX guide estimates Basic at **about US$10/month** [S3]; live regional price, quotas, taxes and extra infrastructure were not verified. | Alternative signing provider, not a separate app format. Requires identity/profile/RBAC and compatible build integration. Public Trust Test or Private Trust does not supply equivalent default public trust. Actual final signature and policy acceptance must be tested. |
| **Microsoft Store MSIX** | Store re-signs MSIX/AppX after certification; no purchased CA certificate is required for that submission [S5]. Current new account onboarding describes no registration fee [S4]; identity/business/market eligibility and certification still apply. | New manifest/publisher identity, packaging and full native qualification. Must resolve full-trust workers, runtime delivery, process/resource behavior, read-only install location, redirected data, update/uninstall preservation and Store policy [S7, S8]. Store package signing does not prove acceptance of separately installed loose runtime DLLs. |
| Store listing of the existing **MSI/EXE** installer | Store does **not** re-sign these files. Installer and contained PE files require publisher Authenticode; versioned HTTPS, silent standalone installer requirements apply [S5, S6]. | Not a free signing shortcut or unchanged one-click runtime solution. Review the existing runtime downloader/provisioning flow against standalone installer and dependency disclosure policies before submission. |

These prices are documentation estimates, not quotes, purchase commitments or
eligibility findings. The official live pricing page could not be read here.
Signing does not confer third-party redistribution rights or Store approval.

### Azure and Store eligibility checks before selecting a provider

The dedicated Azure quickstart lists Public Trust organizations in the **US,
Canada, EU, UK, Australia, New Zealand, Japan, South Korea, Singapore,
Switzerland, Norway and Israel**; individuals are restricted to **US/Canada**
[S10]. Hosting a resource in an eligible region does not change the applicant's
legal eligibility. The user's legal entity, country and eligibility are unknown;
do not infer them from timezone, username or repository ownership.

Azure requires an Entra tenant, Azure subscription, `Microsoft.CodeSigning`
registration, account, approved identity validation and certificate profile.
Identity Verifier and Certificate Profile Signer are separate roles; subscription
ownership alone is insufficient [S10, S11]. Plan least-privilege build credentials,
auditability and protected signing authority. The integration also requires a
compatible pinned SignTool/SDK, client integration, .NET and VC++ prerequisites
[S12]; do not acquire them or create credentials in this milestone. The service
uses short-lived certificates, so approved timestamping and verification are
essential. Its FAQ also requires review of generated certificate subject names
against MSIX Publisher identity and warns that SmartScreen reputation needs
download history [S13]; do not promise instant reputation.

**Source conflict:** the MSIX overview [S3] lists narrower Azure geography and
an organization-history condition; the dedicated Azure quickstart [S10] lists
broader geography and does not state that condition in its eligibility guidance.
Prefer the dedicated service guide for planning, but resolve current eligibility
with Microsoft before enrollment or purchase; neither source establishes this
publisher's approval. The older SAC page's “Trusted Signing preview” wording is
also stale relative to the dedicated Artifact Signing documentation.

Store's new onboarding distinguishes Individual personal/noncommercial use from
Company business/professional use, requires identity/business verification and
says account type cannot simply be converted [S4]. Its no-fee new flow differs
from legacy/direct Partner Center paths. Confirm current market, legal account
type, publisher identity and actual onboarding terms before committing to MSIX.
Do not assume Store eligibility follows Azure eligibility, or vice versa.

### Signing coverage and order — exact implementation preconditions

Current [PyInstaller spec](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/packaging/desktop.spec) creates **two** EXEs,
`FIRMAVEX-Desktop` and console/worker `FIRMAVEX`, with collected Python/Qt native
payloads. It bundles no QEMU/GDB/Icarus runtime. The
[Inno script](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/packaging/windows.iss) is per-user, `PrivilegesRequired=lowest`,
currently unsigned, with no SignTool/SignedUninstaller configuration.
[Signing readiness](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/packaging/signing-readiness.json) explicitly records
missing credentials. Existing Ed25519 checksums/attestations are not Authenticode.

Before an authorized signing implementation:

- Inventory every shipped/loaded EXE, DLL, `.pyd`, Qt plugin, Python native
  component, helper/worker and runtime file. Classify ownership, existing
  signatures, redistribution rights and whether transformation is permitted.
  Do not blindly strip or replace vendor signatures.
- **Signing changes bytes.** The gate hashes the complete QEMU/GDB files. Adding,
  replacing or timestamping a signature can therefore change the pinned digest.
  A transformed runtime cannot be presented as unchanged Route A; final identities
  require a separately authorized candidate/profile review. Do not change hashing
  semantics to evade admission. Preserve vendor originals and transformation logs.
- For the app, sign reviewed payloads before composing the installer; configure
  Inno's signing lifecycle for Setup, Uninstall and temporary self-copies [S14].
  Merely signing the outer finished installer does not cover every child file.
  Upstream Inno documentation must be checked against the exact pinned compiler
  version before adding directives. Runtime packages installed later need their
  own reviewed trust path.
- Verify actual chain, RSA algorithm, publisher, timestamp, trust/revocation
  behavior and all final file identities. Generate final checksums, inventories
  and release attestations **after** signing. An outer installer/MSIX signature
  is not evidence that every separately provisioned runtime binary passes SAC.
- Signing/build access may require network services; the installed product must
  retain offline local operation after dependency installation. Define native
  offline first-launch, timestamp/revocation and policy acceptance tests instead
  of promising that signatures guarantee all disconnected-machine behavior.

## C. Implementation sequence and acceptance gates

The [Batch 28 positive-qualification proposal](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/batch28-positive-qualification-proposal.md)
remains the native execution contract. Candidate testing and production approval
are different decisions. The following is future work, not authorization.

| Phase | Deliverable after explicit scope approval | Acceptance / stop conditions |
|---|---|---|
| 1 — readiness preflight | Small read-only provenance/signing-coverage report composing existing inventories and identity tools; no acquisition, execution, signing or gate changes | Classify actual files and missing evidence, preserve originals, bounded inputs, no private-environment dumps; tests reject unsafe paths/malformed inputs and clearly label synthetic fixtures. Missing inputs remain NOT PROVEN. |
| 2 — bounded Route A intake | Authenticate a supplied original generation or perform separately approved publisher recovery | Exact admitted hashes plus complete compatible signed closure, legal inputs and final host trust. Stop on absent originals/signatures/trust, dependency mixing or changed bytes. If unavailable, retain failure and choose Route B explicitly. |
| 3 — candidate provenance and lab design | Freeze one reviewed generation and specify an isolated, identifiable candidate-only qualification build | All provenance stages close; no production bypass, forged identities or synthetic executor relabeled real. Unchanged production must reject 11.1.3. New candidate version or lab policy needs approval. |
| 4 — native qualification | Predeclared bounded source, frozen and installed/GUI matrix below on native Windows x64 | Original evidence, authoritative outcomes/accounting, actual runtime/module identities, failure/cancel/resource checks. Any missing journey stays NOT PROVEN; a green low-level run is insufficient. |
| 5 — signed packaging pilot | Separately approved provider/account/budget and final signed build or MSIX feasibility prototype | Legal authority, complete signing coverage, immutable final inventory and clean standard-user SAC/offline acceptance. Stop on blocked files; never weaken host controls. No public release implied. |
| 6 — promotion/release review | Independently review exact final runtime, app, installer and consumer evidence | Explicit separate production-profile and release authorization; no automatic promotion from candidate CI, this plan or a signing certificate. |

Phases can expose dependencies: if signing changes runtime bytes, freeze those
final signed identities **before** their corresponding native qualification.
Re-test changed artifacts; earlier unsigned or differently signed evidence does
not qualify them. MSIX feasibility may precede a provider purchase, but it cannot
be assumed to preserve current worker/resource or data-location behavior.

### Exact native checks required before qualification

Predeclare source SHA, build/installer/runtime hashes, Windows build/CPU,
standard-user token, protection state, finite inputs, budgets, timeouts and
cancellation stages. Keep private diagnostics separate from publishable reports.
Repeat applicable journeys independently for **source, frozen and installed**:

1. Exact runtime admission/capabilities and unchanged compiler-free image; reject
   missing, changed and unqualified tools before firmware dispatch.
2. Supported supervised search yields exact trigger `[2, 1]`; independent runtime
   tests check `(2, 1)` → flag 1 and `(2, 0)` → flag 0, initialized data and
   input-ready/completion synchronization. Use supported search settings for a
   non-discovery case; do not invent direct ARM `Request.values` injection.
3. Three fresh bounded replays of the saved trigger; changed image/runtime must
   not silently become an equivalent reproduction.
4. Actual GUI/controller/worker progress and terminal states, failures, timeout,
   pre-dispatch/post-admission cancellation, charged accounting and aborted-state
   integrity. Preserve original interruption and diagnostics; no later trigger
   can mask an infrastructure failure.
5. Independently check owned process handles/job trees and QEMU/GDB/worker reaping
   after success/error/cancel/timeout, plus resource-limit enforcement. A process
   name search alone is insufficient; no sandbox-isolation claim follows.
6. Saved results/reopen, interrupted-state recovery and explicit linked restart;
   truthful distinction between charged evaluator attempts and verified physical
   guest activity. Reports/export checksums must agree without rerunning firmware.
7. Final loaded-module provenance and search policy across the declared flows,
   including GDB Python/hashlib. Reject unaccounted DLLs/data and unsafe paths.
8. Clean standard-user installation, offline use after setup, reinstall/uninstall
   with user data preserved, and a separately declared distinct-version
   upgrade/rollback pair. Test visible GUI/accessibility, shell exports, low disk,
   locking and recovery on consumer Windows, not only hosted/offscreen CI.

Trusted bundled firmware only for this bounded qualification. ARM results do
not qualify RV32/HDL runtimes, arbitrary ELF/BIN, physical hardware or hostile
inputs. New runtime scope requires its own evidence. No controlled research
campaign or modification of frozen experiments is needed.

## D. Risks, approvals and unresolved evidence

| Priority | Risk | Required response |
|---|---|---|
| HIGH | Incomplete authentic package/DLL/legal closure, or unknown final host trust | Do not distribute or qualify; retain exact missing stages. |
| HIGH | Candidate positive execution confused with production approval; signing invalidates pins | Separate lab/build/evidence/profile decisions and final-byte qualification. Preserve production rejection. |
| HIGH | Unsupported claims from CI rejection, static GUI or user-reported results | Keep evidence labels, exact revision/scope and original failure chain. |
| MEDIUM | Signing-provider eligibility/cost conflicts or stale documentation | Verify current legal entity, terms and live quotes before any commitment. |
| MEDIUM | MSIX data redirection/full-trust worker or installer upgrade differences | Prototype and test explicitly; preserve independent user projects/results. |
| MEDIUM | Reputation, revocation/offline or host-policy behavior differs across machines | Final native consumer tests with protections enforced; no acceptance guarantee. |

Outstanding questions for **future user approval**, not decisions made here:

- May bounded Route A recovery/acquisition proceed; which authenticated original
  source or retained generation can the user supply?
- If it fails, which exact candidate generation, trust inputs and isolated lab
  build/policy may be evaluated? Who can authorize a later production profile?
- What is the publisher's legal account/entity type and eligible country, and
  what budget, signing authority and key-custody model are approved? No sensitive
  identity documents should be committed to the repository.
- Should the first packaging implementation retain Inno or fund an MSIX
  feasibility track? Which native Windows clean hosts and protected consumer
  machines are available for final-byte validation?
- Who will review redistribution/source obligations and approve publication of
  administrative evidence? Release and signing purchases require separate consent.

## E. Authoritative sources and verification limitations

All **official source** links below returned HTTP 200 and were read during this
review on **2026-11-12 UTC** (November 13 Asia/Karachi). They are publisher-owned
documentation repositories, not package/artifact authentication. Branch links are
mutable; a source page's `ms.date` is not our verification date. Canonical Learn,
Azure pricing and Inno help-site requests were blocked by proxy HTTP 403; those
live pages, live quotes and account eligibility were **not verified**. The
requested escalated documentation retry did not execute. No alternative package
download or security bypass was used.

| ID | Publisher documentation inspected | Supported conclusion / limitation |
|---|---|---|
| S1 | [Microsoft SAC code signing](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/develop/smart-app-control/code-signing-for-smart-app-control.md) | Trusted RSA, not ECC; old preview wording is not current service-status evidence. |
| S2 | [Microsoft SAC overview](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/develop/smart-app-control/overview.md) | Intelligence and code-integrity checks; unknown unsigned code can be blocked. |
| S3 | [Microsoft MSIX signing overview](https://raw.githubusercontent.com/MicrosoftDocs/msix-docs/main/msix-src/package/signing-package-overview.md) | Package signing, indicative costs and timestamping; Azure eligibility summary conflicts with S10. |
| S4 | [Microsoft developer account onboarding](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/publish/partner-center/open-a-developer-account.md) | New no-fee flow, account-type and verification prerequisites; legacy flows differ. |
| S5 | [Microsoft Store MSIX requirements](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/publish/publish-your-app/msix/app-package-requirements.md) | Store re-signs certified MSIX/AppX; not MSI/EXE. |
| S6 | [Microsoft Store MSI/EXE requirements](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/publish/publish-your-app/msi/app-package-requirements.md) | Trusted signatures for installer and PE files; silent standalone/versioned HTTPS distribution. |
| S7 | [Microsoft Store policies](https://raw.githubusercontent.com/MicrosoftDocs/windows-dev-docs/docs/hub/apps/publish/store-policies.md) | Security, dependencies and distribution review; not advance certification of this app. |
| S8 | [Microsoft desktop-to-MSIX preparation](https://raw.githubusercontent.com/MicrosoftDocs/msix-docs/main/msix-src/desktop/desktop-to-uwp-prepare.md) | Packaging/elevation/data-location constraints; confirm current SDK and app behavior natively. |
| S9 | [Microsoft Artifact Signing overview](https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/artifact-signing/overview.md) | Current product name, managed service; no publisher account approval. |
| S10 | [Microsoft Artifact Signing quickstart](https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/artifact-signing/quickstart.md) | Dedicated eligibility and subscription/identity prerequisites; resolve conflict before enrollment. |
| S11 | [Microsoft Artifact Signing resources/roles](https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/artifact-signing/concept-resources-roles.md) | Distinct trust profiles and least-privilege roles. |
| S12 | [Microsoft signing integrations](https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/artifact-signing/how-to-signing-integrations.md) | Toolchain/client/credential and timestamp prerequisites, not installed here. |
| S13 | [Microsoft Artifact Signing FAQ](https://raw.githubusercontent.com/MicrosoftDocs/azure-docs/main/articles/artifact-signing/faq.yml) | Subject identity, pricing pointer and SmartScreen reputation limitations. |
| S14 | [Inno Setup vendor help source](https://raw.githubusercontent.com/jrsoftware/issrc/main/ISHelp/isetup.xml) | `SignTool` / `SignedUninstaller` lifecycle including temporary copies; verify pinned Inno version. |
| S15 | [MSYS2 updating](https://raw.githubusercontent.com/msys2/msys2.github.io/master/web/docs/updating.md) | Only full-system rolling upgrades supported. |
| S16 | [MSYS2 package management](https://raw.githubusercontent.com/msys2/msys2.github.io/master/web/docs/package-management.md) | Older packages need compatible recursively selected dependencies; availability of this set remains unknown. |

Canonical reader entry points (navigation links, not separately verified pages):
[SAC signing](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control),
[MSIX signing](https://learn.microsoft.com/en-us/windows/msix/package/signing-package-overview),
[Artifact Signing eligibility](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart),
[live pricing](https://azure.microsoft.com/pricing/details/artifact-signing/),
[Inno signing](https://jrsoftware.org/ishelp/topic_setup_signtool.htm).
Revalidate terms, supported markets, pricing and policies at the implementation
decision; no documentation read constitutes Microsoft/vendor approval.
