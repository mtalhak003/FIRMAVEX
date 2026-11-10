# FIRMAVEX documentation

This index separates current product boundaries, chronological engineering
history, historical evidence and frozen research methodology. A document or
passing test is evidence only for its stated revision and scope.

## Start here

| Reader goal | Route |
|---|---|
| Understand the project and supported methods | [Project overview](../README.md), [unified desktop guide](product/unified-desktop.md), [backend contracts](product/universal-backends.md) |
| Review how the project developed | [Primary chronological history](product/development-progress.md) |
| Understand supported architectural decisions | [Retrospective engineering decision records](decisions/README.md) |
| Evaluate evidence quality and historical coverage | [History audit and evidence gaps](development/history-audit.md) |
| Assess release readiness | [Batch 28 readiness snapshot](product/batch28-release-readiness.md), [release policy](product/release-policy.md), [latest history follow-up](product/development-progress.md#november-9-2026--windows-candidate-evidence-and-release-preparation) |
| Add the next milestone | [Entry template](development/milestone-template.md), [maintenance and verification procedure](development/history-maintenance.md) |
| Use the latest desktop workflow improvements | [Batch 29 operator and validation guide](product/batch29-desktop-workflows.md), [dated implementation entry](product/development-progress.md#2026-11-10--batch-29-desktop-project-readiness-and-export-workflows) |

The latest original Batch 27 ZIP pass is **user-reported**, not independently
verified in this environment: 19 receipts, 97 JUnit passed, 10 skipped and zero
failures/errors. That update does not approve the candidate runtime or erase
earlier artifact-access limitations. The primary history retains both scopes.

## Product operation and architecture

| Area | Implemented boundary and references |
|---|---|
| Installation and first launch | [Installation](product/install.md), [desktop usage](product/desktop.md), [beta setup](product/beta-setup.md). Unsigned/unnotarized development candidates are not public-release approval. |
| Desktop and supervised services | `firmavex/desktop/` and `firmavex/product/`; [Batch 1 contract](product/batch1.md), [local worker interface](product/local-worker-interface.md), [ADR 0001](decisions/0001-supervised-local-execution.md) |
| Desktop project and export usability | [Batch 29 workflows and actual validation](product/batch29-desktop-workflows.md): fresh forms, selected-ELF checks, shortcut recovery, persistent states and confirmed exports; native Windows validation remains outstanding. |
| ARM, RV32 and HDL execution | `firmavex/backends/`; [bounded profiles](product/universal-backends.md), [unified GUI](product/unified-desktop.md), [custom projects](product/batch17-custom-workflow.md), [ADR 0002](decisions/0002-capability-aware-backends.md) |
| Evidence, saved results and reports | [History/review](product/batch14-history.md), [scoped verification](product/batch15-verification.md), [verification reports](product/batch16-verification-reporting.md), [regression dashboards](product/batch20-regression-review.md), [retained-input consistency](product/batch22-verification-consistency.md) |
| Execution trust and isolation limits | [Threat model](security/execution-threat-model.md), [Linux isolation assessment](security/linux-isolation-review/README.md). Trusted workloads only; no independently qualified hostile-input sandbox. |
| macOS support restriction | [Measured memory-admission investigation](product/macos-memory-admission.md), [ADR 0003](decisions/0003-macos-memory-admission.md). Current unified native execution is unsupported; historical ARM-only passes are narrower evidence. |
| Windows runtime admission | [Failure diagnostics](product/batch23-runtime-diagnostics.md), [candidate harness](product/batch23-runtime-candidate.md), [candidate separation decision](decisions/0004-windows-candidate-separation.md). QEMU 11.1.3 remains production-rejected. |

Early `docs/architecture/` pages are empty research scaffolding, not completed
design records. The implemented boundaries above and evidence-backed decisions
are the supported architecture references; missing historical rationale remains
explicit rather than reconstructed as a fictional design discussion.

## Testing and qualification evidence

- [Research testing setup](development/testing.md), [product validation](product/validation.md)
  and [CI failure diagnostics](product/ci-diagnostics.md) describe different test
  scopes. Test presence does not establish that a run passed.
- [Batch 3 native record](product/batch3-validation.md),
  [Batch 11 evidence](product/batch11-release-evidence.md) and
  [Batch 21 acceptance](product/batch21-acceptance.md) retain historical passes,
  failures and their platform limits. Newer candidate results do not replace
  the exact runtime identities tested there.
- [Artifact acquisition and original-ZIP verification](product/batch28-artifact-verification.md),
  [runtime provenance workflow](product/batch28-runtime-provenance.md), and
  [positive-execution proposal](product/batch28-positive-qualification-proposal.md)
  separate record consistency from publisher trust, complete dependency closure
  and explicit production promotion.
- [Consumer acceptance](product/consumer-acceptance.md) and the
  [clean Windows checklist](product/batch28-consumer-windows-checklist.md)
  require native/human evidence that hosted CI and GUI smoke tests cannot supply.

## Preserved research

The canonical research engine remains under `src/firmavex/`. These documents
describe frozen research contracts, not product defaults or completed campaigns:

- [Opaque evaluation](development/evaluation.md), [strategy interface/baselines](development/strategies.md),
  [runtime signatures](development/runtime-signature.md) and [feedback-guided search](development/guided-search.md).
- [Experiment records](development/experiments.md), [standard baseline protocol](development/evaluation-protocol.md)
  and [controlled protocol](experiments/controlled-evaluation-v1.md).
- [Runtime feasibility](experiments/runtime-feasibility.md) and
  [durable campaign recovery](experiments/campaign-recovery.md).

Research Step 19 and desktop Batch 19 are different milestones. Step 19 analysis
remains preliminary and journal-derived, with user-reported failed execution
verification and missing supplementary evidence at zero-based position 7.
It is unrelated to the later user-reported passed Batch 27 Windows ZIP.
No held-out, hardware, AI-guidance or general-superiority claim follows.

Historical reports retain their original dates, partial scopes and statuses.
Follow the chronological history for later evidence instead of silently treating
an old preparation document as current approval.
