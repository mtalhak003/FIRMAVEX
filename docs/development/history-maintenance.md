# Maintaining engineering history

The [development progress log](../product/development-progress.md) is the primary
chronological account. Detailed batch reports, commit records, CI runs and
[engineering decision records](../decisions/README.md) provide supporting evidence;
they are not interchangeable proof. Use the [milestone template](milestone-template.md)
for future entries. This procedure does not authorize implementation, a workflow
dispatch, publication of private records or a release.
Use the [documentation index](../README.md) to keep these routes discoverable.
The [source register](history-sources.md) declares the latest expanded audit
cutoff and links the research, troubleshooting, validation and commit-catalogue
companions. Keep those routes aligned with the primary history.

## Record evidence before writing conclusions

1. Confirm the approved worktree, current SHA, intended remote branch and permitted
   working-tree status. Preserve unrelated changes. If a worktree is detached,
   record that fact; do not quietly switch or update a stale branch belonging to
   another checkout. Never inspect the original checkout or the protected private
   evidence directory to fill documentation gaps.
2. Inspect the relevant commit diff, source/tests and contemporary documents.
   A commit proves recorded content and metadata, not a successful execution.
   Commit timestamps do not establish when work started, time spent or authorship
   beyond the identities actually recorded by Git.
3. Resolve CI by exact run, attempt, job and source SHA. A successful older run is
   historical evidence for its tested revision, not verification of the current
   commit. Distinguish a visible successful step from original logs/JUnit files
   that were retrieved and independently reviewed.
4. Bind an original artifact to its exact ID/name, run/source context and original
   digest. State whether the digest was displayed, supplied or independently
   computed. Do not repackage, fabricate or reconstruct missing execution evidence.
   An inaccessible artifact is an evidence gap, not proof of a failed execution.
5. Record exact test commands, flags, counts, skipped reasons and exclusions when
   retained. Do not infer passing counts from the presence of tests. Keep failures
   and their subsequent fixes visible, with separate repair and validation links.
6. When extending a complete-history audit, declare its exact cutoff and compare
   the commit catalogue with `git log --reverse --topo-order` at that SHA. Retain
   original timestamps/parents/subjects and verify date conversions and routes.
   Grouping maintenance commits is navigation, not proof of new implementation.
   Preserve prior audit snapshots; add supported troubleshooting/validation detail
   instead of copying the whole timeline into another document.

## Use two independent labels

The result answers whether a requirement passed within its scope: **PASS**, **FAIL**
or **NOT PROVEN**. The evidence class answers how that claim is known:

| Evidence class | Meaning and boundary |
|---|---|
| Git/source | Recorded commit metadata, file contents or inspected implementation. Does not establish test execution. |
| CI observation | An authorized GitHub record shows a conclusion or step result for a specific run/attempt/revision. State when original artifacts were not reviewed. |
| Historical record | A versioned report retains a validation claim or count. Attribute it to that report; do not relabel it as a fresh rerun or independently reviewed original evidence. |
| User report | A person reported the result. Preserve the attribution and whether original output/bytes were independently available. |
| Not proven | Evidence is absent, inaccessible, contradictory, outside scope or has not been evaluated. Name the action needed to close the gap. |

For independently performed checks, state what was actually inspected or run,
with its output and identity. These labels can coexist for different claims in one
entry. A user-reported verifier pass must not silently turn into an independently
verified pass. A candidate rejection test can pass while positive product
execution and production qualification remain NOT PROVEN.

## Append and correct without rewriting results

- Keep the primary history oldest-to-newest. Group related repair commits when
  useful, but retain their dates, failure context and exact references. For a
  retrospective entry use the recorded source date, explicitly identify its date
  basis/timezone, and distinguish it from the later review date. If the actual
  event date is unknown, say so rather than assigning a commit date to the event.
  This repository's retrospective Git timeline uses recorded **committer**
  timestamps converted to **Asia/Karachi**. Do not silently mix author dates,
  committer dates, CI timestamps and report dates; retain the original records.
- Preserve original batch reports and their historical scope. New evidence should
  receive a dated follow-up or an explicitly labelled correction, with a source
  link explaining what changed. Do not erase earlier failures or recast a proposal
  as completed work. Do not backdate commits or rewrite Git history to improve the
  apparent activity record.
- Add a decision record only when a source supports the decision. A retrospective
  record must identify its supporting commit/document and unavailable rationale;
  do not invent alternatives, approvals or reasoning. Prefer linking an existing
  architecture decision over duplicating it.
- Update navigation and the current readiness reference when a new entry changes
  the documented state. Preserve the distinction between shipped production
  profiles, candidate testing, synthetic regressions and consumer acceptance.
  The November 2026 candidate results do not by themselves approve QEMU 11.1.3.
- Keep administrative archives private and outside the repository. Review paths,
  filenames, diagnostics and supplied metadata before publishing derivatives.
  No history-maintenance step permits access to `evidence/windows-sandbox/`.

## Documentation-only validation and publication

Review the changed Markdown, supported claims, commit references and relative
links. Check local link targets without following symlinks or walking protected
directories. Verify that newly referenced SHAs exist in the approved repository.
If an external source is unavailable, retain that limitation rather than silently
substituting a similarly named run or artifact.

From the approved worktree, these are read-only review commands:

```sh
git diff --check -- README.md docs
git diff --stat -- README.md docs
git diff -- README.md docs
```

`git diff` omits untracked additions. Review each intended new document directly
and check its whitespace and links separately. Search only the intended document
paths; do not recursively scan private evidence or unrelated checkouts. A
documentation-only change normally needs content/link/whitespace checks rather
than firmware execution; explicitly state which tests were not run and why.

Stage, commit and push only with task authorization. Check the remote SHA again
before a normal fast-forward push; if it advanced unexpectedly, stop and report.
Do not merge into the default branch or dispatch CI merely to document progress.
Use the configured identity and normal commit timestamps. Report the changed
files, checks, commit/remote SHAs and remaining evidence gaps.
