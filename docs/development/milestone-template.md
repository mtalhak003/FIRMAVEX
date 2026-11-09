# Milestone entry template

Copy the block below into the [primary development history](../product/development-progress.md).
Keep entries in chronological order. Replace placeholders with supported facts;
use **NOT PROVEN** or "not retained" instead of filling gaps with assumptions.
Follow the [maintenance procedure](history-maintenance.md) before publication.
The [documentation index](../README.md) links the history, decisions and evidence.

```markdown
## YYYY-MM-DD — Milestone or batch title

**Date basis:** [Execution timestamp / recorded commit date / report date],
[timezone]. Source: [original record or commit]. This date does not establish
work duration. For a retrospective entry, state its review date separately.

**Objective:** [The problem or intended outcome supported by the task or record.]

**Changes:** [Implemented behavior and affected components. Distinguish working
functionality, prepared checks and proposals. Include compatibility boundaries.]

**Decisions and reasoning:** [Only reasoning retained in a cited source. Link an
existing decision record where relevant. If rationale is unavailable, say so;
do not invent rejected alternatives or a contemporaneous decision meeting.]

**Commit references:** [Full SHA and stable commit link for each relevant change;
include the baseline and follow-up repair where material. A commit message alone
does not prove that functionality passed its tests.]

**Validation:**

| Claim | Result | Evidence class | Source and exact scope |
|---|---|---|---|
| [Behavior/test scope] | PASS / FAIL / NOT PROVEN | Git/source / CI observation / historical record / user report / not proven | [Original evidence, source SHA, limitations] |

- Command and flags: [Exact command, selection/exclusions, timeout/runtime flags.]
- Environment: [Actual OS/architecture, Python/runtime/tool identities where retained.]
- Counts: [Passed, failed, errors, skipped and deselected; explain skipped cases.]
- CI: [Workflow/run URL, attempt, job, tested source SHA and observed conclusion.]
- Artifact: [Exact ID/name, original SHA-256 and whether original bytes were read.]
- Verification: [Verifier version/source SHA, required scope, exact result and
  whether it was independently run or reported by someone else.]
- Not run or unavailable: [Missing tools, inaccessible logs/artifacts or untested paths.]

**Failures and resolutions:** [Observed failure, evidence, confirmed cause versus
hypothesis, repair commit, and the later validation that supports resolution.
Retain unresolved failures. Distinguish infrastructure failure from test failure.]

**Limitations and blockers:** [Unproven platforms, acceptance/provenance gaps,
unsupported targets and remaining security/research qualifications.]

**Next steps:** [Concrete remaining action and any separate authorization needed.
Do not present intended work or a proposed test as completed.]

**Approval/traceability:** [Decision or reviewer reference if one actually exists;
otherwise "not recorded". State whether release/profile promotion was authorized.
Link the detailed readiness report and any supporting decision record.]
```

Keep the narrative short and link detailed test matrices or investigations.
Overlapping test selections are not additive. Charged evaluator attempts are not
automatically independently verified physical guest executions. A simulator result
does not establish hardware qualification, sandbox isolation or public-release
readiness. Preserve candidate-only and user-reported labels wherever they apply.
