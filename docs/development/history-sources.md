# Engineering history: coverage and source register

Batch 30 review date: **November 10, 2026 (UTC)**.
Cutoff: `da22cc6853d21cfa45fd851aa77108357f62dd7e` on the development line
`product/desktop-batch11`. The approved worktree is detached; no branch switch,
history rewrite or change to main is needed to publish this documentation.

## How to read the history

| Question | Evidence-backed route |
|---|---|
| What happened, in what order? | [Primary chronological history](../product/development-progress.md) |
| How did source analysis become the controlled research engine? | [Research contract/evidence map](research-history.md) |
| How did automated testing, desktop workflows and platform evidence evolve? | [Validation history](validation-history.md) |
| What failed, what was repaired, and what remains unresolved? | [Troubleshooting and lessons](troubleshooting-history.md) |
| Which decisions have recorded support? | [Retrospective decision records](../decisions/README.md) |
| Which exact Git objects are included? | [Complete cutoff commit catalogue](history-commits.csv) |
| What was established by the earlier audit? | [Preserved November 9 audit](history-audit.md) |
| What should the next batch record? | [Milestone template](milestone-template.md), [maintenance procedure](history-maintenance.md) |

The new companion records add experimental contracts, test-scope distinctions,
failure-to-repair chains and remaining evidence requirements. They supplement the
existing grouped timeline rather than reproducing it as a second narrative.
The original November 9 audit remains dated and scoped to its **159-commit**
cutoff. This review extends coverage through the history-system commit and the
two actual Batch 29 commits: **162 reachable commits**, September 14–November 10,
2026 by recorded committer dates in Asia/Karachi.

## Complete Git coverage without invented milestones

[`history-commits.csv`](history-commits.csv) records every commit reachable from
the cutoff exactly once, including README maintenance and merge commits. Its
fields are:

- `topological_index`: parent-before-child reverse topological traversal order;
  this is not an effort measure or an inferred experiment sequence.
- `sha`, `parents`, `committer_iso8601`, `subject`: unmodified Git metadata.
- `date_asia_karachi`: deterministic conversion of the recorded committer instant.
  The original timezone/instant is retained in the preceding field.
- `milestone_group`, `history_route`: editorial navigation to the relevant
  timeline section, not a separate assertion that every commit adds engine code.

Group boundaries follow the implementation/report checkpoints in the primary
history. A repair or maintenance commit can be grouped with a larger phase;
documentation-only and merge subjects are retained as such. There is no
fabricated research Step 19 implementation commit or separate Batch 23B/23C
implementation commit: conversation-only validation and the preserved acquisition
investigation have the narrower evidence scopes described in the narrative.

| Catalogue segment | Commits | Narrative coverage |
|---|---:|---|
| Initial analysis and repository maintenance | 32 | Native-GCC/static-analysis origins, context-handling repairs, rename; no inferred execution transcript |
| Initial ARM runtime stages | 7 | Target, QEMU, debugger monitoring, detector, search, reproduction/minimization, reports |
| Research Steps 15–18 | 12 | Reproducible corpora, opaque evaluator, baselines, signatures/guidance, frozen protocol, pilot, provenance and durable recovery |
| Desktop Batches 1–11 and associated diagnostic repairs | 70 | Product/GUI, packaging/runtime management, ARM/RV32/HDL, ownership/resources, CI stalls and release limits |
| Desktop Batches 12–22 plus original MPS2 regression | 24 | Projects/history, verification, custom inputs, diagnosis, regression sets, acceptance and retained-input boundaries |
| Batches 23–28 | 13 | Failure diagnostics, isolated candidate repairs, evidence/provenance tooling and installed rejection/lifecycle checks |
| History documentation preceding Batch 29 | 2 | November 9 progress and original traceability system |
| Batch 29 | 2 | Desktop implementation `feb1fab8…` and documentation `da22cc68…` |
| **Total through cutoff** | **162** | Catalogue completeness is a metadata fact, not 162 validated product milestones |

The catalogue deliberately excludes the later commit publishing Batch 30. Future
updates must declare a new cutoff rather than quietly redefining this snapshot.
Reproduce the source list from the approved checkout with:

```bash
git log --reverse --topo-order \
  --format='%H%x09%P%x09%cI%x09%s' \
  da22cc6853d21cfa45fd851aa77108357f62dd7e
git rev-list --count da22cc6853d21cfa45fd851aa77108357f62dd7e
```

These commands inspect Git metadata; no private evidence paths or original
checkout are needed. Review relevant diffs using explicit permitted source,
test, workflow and documentation paths, never a recursive evidence scan.

## Evidence classes and fresh inspection scope

| Class | What this review can establish | What it cannot establish |
|---|---|---|
| Independently checked Git/source | Catalogue fields, reachable references, retained contracts/tests and selected changes | That tests passed, when an experiment occurred, development hours or unrecorded design rationale |
| Fresh CI-page observation | Displayed run/attempt/source/conclusion on the exact public page | Original JUnit/receipt bytes, complete logs, all native scenarios or qualification of another revision |
| Historical report | What a versioned report records for its named scope | A fresh rerun or independent authentication of its original measurements |
| User report | Explicit conversation results, including local Step 19 restrictions and original Batch 27 ZIP verification | Independent access to the user's WSL archives or missing supplementary evidence |
| NOT PROVEN | A named missing or out-of-scope requirement | Permission to fill a gap with reconstructed data or promote a runtime |

On November 10, six public run pages were independently retrieved (HTTP 200),
with full commit links and attempt-1 navigation visible. No workflow was
dispatched. These are page observations, not downloaded original artifacts:

| Run | Source | Displayed conclusion | Interpretation |
|---|---|---|---|
| [38282319967](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38282319967) | `bb77217d6d254d3c231723213f3b895a4ad4372c` | Success | Historical native regression at that revision |
| [38590752705](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38590752705) | `0d3011abbe2f6b9b1b758d067ad7bb566f81ac66` | Failure | Preserve the failing whole-run conclusion and Darwin limitation |
| [38601295586](https://github.com/mtalhak003/FIRMAVEX/actions/runs/38601295586) | `ac8e07233241eb294e2f6aa07216624b78ebb771` | Cancelled | Does not independently identify the original Windows stall cause |
| [39303862786](https://github.com/mtalhak003/FIRMAVEX/actions/runs/39303862786) | `7965ac72907054130ca0e31fa56fdcdf71819744` | Failure | Preserve unresolved aggregate isolation/namespace status |
| [42505041359](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42505041359) | `237e9f64352d1aac7105f7461db5d76dacf57612` | Success | Candidate source-stage evidence |
| [42618949135](https://github.com/mtalhak003/FIRMAVEX/actions/runs/42618949135) | `c42cdd000dbd117dee558fd346aa8b653ac7bf3f` | Success | Scoped candidate rejection/installed lifecycle, not promotion |

The read-only GitHub CLI request for run `42618949135` returned **Forbidden**
from the API in this environment. No original artifact was downloaded or
reconstructed. The original Batch 27 ZIP pass remains **user-reported**:
artifact `13675538108`, SHA-256
`f66dd8611f9c149793114eaf9d3156118d93846bd96299e5cb00c7a91c793fd8`,
19 receipts, 97 JUnit passed, 10 skipped, zero failures/errors.

## Gaps preserved rather than filled

- Early source stages and several desktop batches have retained tests but no
  exact aggregate transcript in the inspected records. No passing count is
  assigned from the number of tests or a commit subject.
- Conversation references to the old Step 15A/15B SHAs `17b3b219…` and
  `10c8117e…` precede a user-authorized authorship correction. Those objects are
  absent from the available local object store. Current canonical checkpoints
  are `e03ff47f…` and `944bdb52…`; old/new tree equivalence was not reverified
  here. This review does not change history or invent a second implementation.
- Local Step 19 preparation/analysis packages, archives, original figures and
  private machine observations were not independently inspected. Execution
  verification remains failed with missing supplementary evidence at zero-based
  position 7. The research record also discloses prior administrative held-out
  feasibility-pilot exposure; this is distinct from a held-out comparison run.
- Exact original causes of some CI stalls/inventory failures remain unknown;
  later defensive repairs and successful conclusions do not prove every earlier
  attempt had the same cause. See the chronological troubleshooting register.
- Native composition/trust, immutable package closure, positive candidate product
  paths, consumer Windows acceptance, signing, macOS resource admission and
  hostile-workload isolation remain open. No documentation update closes them.
- Batch 29's Linux offscreen and synthetic-record export checks leave native
  Windows and actual firmware validation of that revision outstanding. Its
  unfiltered missing-tool failures remain recorded alongside scoped passes.

## Batch 30 validation boundary

This documentation-only update validates local links/fragments, canonical commit
references, catalogue metadata/completeness/parent order, declared chronology,
scope statements and whitespace. It reads no private archive and runs no
firmware, pytest suite, installer, campaign or CI job. Exact validation counts
and publication SHA are reported with delivery; the commit containing this file
records the published document version. Production functionality, runtime pins,
security policy, workflows, frozen research and original results are untouched.
