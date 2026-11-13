# FIRMAVEX engineering history

FIRMAVEX's development history is documented with dated milestones, commits, technical decisions, CI evidence, failures, and outstanding qualification gaps. **Batch 30 extended the audited history to 162 commits through Batch 29 (September 14–November 10, 2026).** The product is **under development**; Windows candidate evidence does not constitute production approval.

- [Chronological engineering timeline, September 14–November 9, 2026](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/product/development-progress.md)
- [Full documentation index](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/README.md)
- [Four retrospective engineering decisions](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/decisions/README.md)
- [History audit and evidence gaps](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/development/history-audit.md)
- [Milestone template](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/development/milestone-template.md)
- [History maintenance procedure](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/development/history-maintenance.md)
- [Windows qualification and release-readiness matrix](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/product/batch28-release-readiness.md)

The links above are pinned to the reviewed documentation commit `677bb7e` on the development branch so they remain usable from the minimal default branch. For later work, consult [the active development branch](https://github.com/mtalhak003/FIRMAVEX/tree/product/desktop-batch11).


## Expanded Batch 30 historical archive (November 10, 2026)

The following are commit-pinned documentation sources reviewed in development-branch commit [`bd875f2`](https://github.com/mtalhak003/FIRMAVEX/commit/bd875f22cc2604a7e397166177cd82c6e81bc07f). Links go to the development branch's fixed historical snapshot and do **not** merge experimental product code into `main`.

- [Coverage and historical source register](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/history-sources.md): evidence basis, historical scope and gaps.
- [Complete 162-commit catalogue](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/history-commits.csv): Git-based chronology and parent ordering.
- [Expanded engineering timeline](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/product/development-progress.md): major milestones through Batch 29.
- [Research foundations and experimental contracts](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/research-history.md): research implementation and limits.
- [Chronological troubleshooting and lessons learned](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/troubleshooting-history.md): failures, fixes and unresolved matters.
- [Testing, CI and platform qualification history](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/validation-history.md): validation scope and evidence boundaries.
- [History audit and evidence gaps](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/history-audit.md): preserved cutoff distinctions and missing artifacts.
- [Maintaining the historical record](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/development/history-maintenance.md): evidence-first updating practice.
- [Batch 29 Windows validation outstanding](https://github.com/mtalhak003/FIRMAVEX/blob/bd875f22cc2604a7e397166177cd82c6e81bc07f/docs/product/batch29-desktop-workflows.md): workflow improvements verified in Linux offscreen Qt, not yet native Windows.

The source register reports document validation of 10 Markdown files, 423 links/routes, 107 referenced commits, 162 catalogue rows and 35 timeline ranges. These are **documentation checks**, not new firmware execution or production runtime qualification. Step 19's missing original evidence, publisher provenance, native Windows tests and consumer acceptance remain open.

## November 9, 2026 milestone

Windows candidate CI [run 42618949135](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135) passed native ARM, source/GUI/frozen rejection and installer lifecycle checks. Batch 28 added provenance/qualification review tooling. The original evidence ZIP's full required-scope verifier **passed when run locally by the user**, reporting 19 receipts, 97 JUnit passed, 10 skipped and zero JUnit failures/errors. This is a user-reported verification result, not independent publisher authentication or positive production execution.

**Not proven:** authentic publisher/signature trust and complete package/DLL/license provenance, positive production product-path execution, clean consumer Windows acceptance, or release authorization. The history is retrospective; dates and links are evidence-based, not claims of unrecorded working hours or decisions.

**Publication scope:** This default-branch entry point is documentation only. No application code, runtime admission, CI workflows, packages or release artifacts are merged.


## Batch 32 Windows runtime and packaging plan (November 13, 2026)

The [Batch 32 qualification plan](product/batch32-windows-runtime-packaging-plan.md)
compares recovery of the exact admitted QEMU 11.1.2 / GDB 18.1 profile with a
separately authorized candidate qualification. It defines package/signature,
dependency/DLL, licensing, native product-path and signing acceptance gates, and
compares existing Inno/Authenticode distribution with Microsoft Store MSIX.

The review date is November 13 Asia/Karachi (November 12 UTC), not a new Windows
execution date. Official documentation source checks, historical CI observations,
user reports and unproven requirements remain explicitly separated. No new
firmware or installer execution, production promotion, signing purchase or release
was authorized. Signing can change executable hashes; an outer installer signature
does not establish trust in every separately installed runtime DLL.

Development delivery:
[19f9eb0254fd0162db601e5ed82055baa92e7a5d](https://github.com/mtalhak003/FIRMAVEX/commit/19f9eb0254fd0162db601e5ed82055baa92e7a5d).
The [updated development history](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/development-progress.md)
and [scoped Windows user-report record](https://github.com/mtalhak003/FIRMAVEX/blob/19f9eb0254fd0162db601e5ed82055baa92e7a5d/docs/product/batch31-windows-validation.md)
remain pinned on the development line. This publication adds only the plan and
this index entry; it brings no experimental code, workflows, runtime policies,
packages or original evidence into `main`.
