# Engineering decision records

These records make established decisions traceable; they do not create new
runtime policy or authorize execution. Each numbered record is a **retrospective
summary** of cited commits and retained documentation. Its evidence dates are
Git committer dates converted to Asia/Karachi, not invented meeting dates or
proof of when work began. Unrecorded alternatives and motivations remain unknown.

| Record | Established decision | Evidence dates | Status |
|---|---|---|---|
| [ADR 0001](0001-supervised-local-execution.md) | Share versioned supervised services across product entry points | 2026-10-11 onward | Implemented architecture, with scoped platform evidence |
| [ADR 0002](0002-capability-aware-backends.md) | Represent different targets/methods through explicit backend capabilities | 2026-10-14 | Implemented architecture; trusted local execution only |
| [ADR 0003](0003-macos-memory-admission.md) | Keep macOS unified execution blocked when memory admission fails | 2026-10-14 | Recorded support restriction; alternative enforcement unqualified |
| [ADR 0004](0004-windows-candidate-separation.md) | Separate Windows candidate evidence from production admission | 2026-11-07 onward | Implemented restriction; candidate promotion unresolved |

An earlier, more detailed [Linux fixed-probe architecture assessment](../security/linux-isolation-review/architecture-decision.md)
is retained in its original location. It is a **proposal**, not an implemented
VM or hostile-workload isolation boundary. Do not silently convert that status
to accepted or create a duplicate ADR implying the design was deployed.

The [development progress log](../product/development-progress.md) supplies the
chronology. The [Batch 28 readiness matrix](../product/batch28-release-readiness.md)
supplies release limits; passing a decision's unit tests is not release approval.

For future decisions, record the actual date and objective, concrete alternatives
that were considered, the chosen behavior, source/commit references, consequences,
validation and unresolved risks. If reconstructing an older decision, label it
retrospective and cite the available evidence instead of assigning a fictional
approval date, author or rationale.
