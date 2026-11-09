# FIRMAVEX engineering history

FIRMAVEX's development history is documented with dated milestones, commits, technical decisions, CI evidence, failures, and outstanding qualification gaps. The product is **under development**; Windows candidate evidence does not constitute production approval.

- [Chronological engineering timeline, September 14–November 9, 2026](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/product/development-progress.md)
- [Full documentation index](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/README.md)
- [Four retrospective engineering decisions](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/decisions/README.md)
- [History audit and evidence gaps](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/development/history-audit.md)
- [Milestone template](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/development/milestone-template.md)
- [History maintenance procedure](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/development/history-maintenance.md)
- [Windows qualification and release-readiness matrix](https://github.com/mtalhak003/FIRMAVEX/blob/677bb7e94097ed9512be200ffb544350b4c4523e/docs/product/batch28-release-readiness.md)

The links above are pinned to the reviewed documentation commit `677bb7e` on the development branch so they remain usable from the minimal default branch. For later work, consult [the active development branch](https://github.com/mtalhak003/FIRMAVEX/tree/product/desktop-batch11).

## November 9, 2026 milestone

Windows candidate CI [run 42618949135](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135) passed native ARM, source/GUI/frozen rejection and installer lifecycle checks. Batch 28 added provenance/qualification review tooling. The original evidence ZIP's full required-scope verifier **passed when run locally by the user**, reporting 19 receipts, 97 JUnit passed, 10 skipped and zero JUnit failures/errors. This is a user-reported verification result, not independent publisher authentication or positive production execution.

**Not proven:** authentic publisher/signature trust and complete package/DLL/license provenance, positive production product-path execution, clean consumer Windows acceptance, or release authorization. The history is retrospective; dates and links are evidence-based, not claims of unrecorded working hours or decisions.

**Publication scope:** This default-branch entry point is documentation only. No application code, runtime admission, CI workflows, packages or release artifacts are merged.
