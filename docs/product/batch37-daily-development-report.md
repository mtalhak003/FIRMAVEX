# Batch 37 — read-only daily development report

**Report date:** November 23, 2026, Asia/Karachi.
**Starting checkpoint:** `6efbd010fb31333dba26cbc8d0b13ac80ae0f13c`.
**Tracking record:** [Issue #6](https://github.com/mtalhak003/FIRMAVEX/issues/6).
**Scope:** offline administrative Git reporting and explicitly attributed status
observations. Native Windows validation remains **PENDING**.

## Prior attempt and evidence classification

Issue #6 records an earlier isolated draft prepared on November 23: a 149-line
reporter and an 89-line test file, with **7 passed in 0.19 seconds** reported in a
Python 3.13.5 Linux environment. It also records unavailable GitHub checkout/DNS
and approved-worktree access, with no integrated repository validation, commit or
source push. Those counts are a **historical issue report**, not independently
reproduced results for this implementation.

Neither external draft was present in the approved worktree. The Batch 37
implementation was developed from the written requirements and existing repository
conventions; it is equivalent work, not a claimed recovery of the unavailable
files. Authenticated GitHub API requests for Issue #6 returned `Forbidden`; the
public issue page was accessible and its body was reviewed. No issue, comment or
workflow was modified by the reporter.

The implementation is [the reporter](../../tools/daily_development_report.py),
with [regression tests](../../tests/product/test_daily_development_report.py).
It reuses the reviewed administrative path and Git-environment conventions from
[Batch 35](batch35-native-preflight-validation.md), and preserves the
[history-maintenance evidence distinctions](../development/history-maintenance.md).

## Usage

Use an existing trusted Python 3.11+ environment and an **explicit, trusted,
absolute Git executable**. The reporter does not search PATH as a fallback, install
Git, create an environment, modify a branch or acquire packages. Python's IANA
`Asia/Karachi` timezone data must already be available. If it is absent, reporting
is blocked rather than silently changing the reporting timezone.

From the repository root, with the trusted environment activated:

```bash
python -B -m tools.daily_development_report \
  --repo /absolute/path/to/FIRMAVEX \
  --git-executable /usr/bin/git \
  --date 2026-11-23
```

Omit `--date` to select the current day in Asia/Karachi. An optional
`--expected-head FULL_CURRENT_HEAD_SHA` refuses a different revision. Use the exact
current 40-character SHA for that argument; it is a check, not a checkout or reset.
The reporter works with a named branch or detached HEAD and reports that distinction.
Version 1 supports this project's SHA-1 Git repositories (40-character commit IDs).
An empty repository without a committed HEAD or an unsupported object format is
blocked rather than reported as a successful empty-history assessment.

A native PowerShell invocation, **not a native Windows validation claim**:

```powershell
& .\.venv\Scripts\python.exe -B -m tools.daily_development_report `
    --repo 'C:\Path\To\FIRMAVEX' `
    --git-executable 'C:\Program Files\Git\cmd\git.exe' `
    --date '2026-11-23'
$Code = $LASTEXITCODE
Write-Host "Reporter exit: $Code"
```

Replace both example paths with independently trusted local locations. If Windows
Application Control blocks a script, interpreter or Git binary, preserve the
failure and stop; no protection bypass is authorized. Native Windows, PowerShell
and Windows process-cleanup behavior are not established by Linux tests.

The tool prints deterministic JSON to stdout and a concise summary to stderr.
It does not create report files. To retain output, the operator may explicitly
redirect it to a **fresh private location outside the repository**, taking care
not to overwrite existing files or evidence. Redirection is the shell's operation,
not an overwrite protection supplied by this tool. Review generated reports before
publication: Git subjects, authors, filenames and supplied observations can contain
private project information.

| Exit | Meaning |
|---|---|
| `0` | A report was collected consistently within the supported scope. This does **not** mean tests passed or development completed. |
| `2` | Invalid input, unsupported configuration, Git failure, observed change or resource boundary blocked collection. The JSON contains a fixed diagnostic code. |
| interruption | KeyboardInterrupt, SystemExit and other control-flow exceptions propagate; interrupted output is not a completed report. |

A supplied failed or pending observation does not make collection itself fail.
Inspect the observation status and evidence attribution separately from the exit
code. No report is automatically committed, uploaded, attached to an issue or sent
to a cloud service.

## What the report measures

The selected day is a half-open Asia/Karachi interval: local midnight through,
but excluding, the following local midnight. **Committer timestamps** determine
membership. Author timestamps, time spent, actual development dates and GitHub
contribution dates are not inferred from them.

The collector walks the history reachable from a pinned HEAD, then filters the
recorded timestamps. It does not rely on Git `--since` pruning, which can omit
relevant descendants/ancestors when commit timestamps are nonmonotonic. The history
scan is bounded and refuses an over-limit history instead of silently reporting a
truncated day. Records are sorted by commit time and SHA; file records are sorted
by their recorded path.

Each selected commit includes its SHA, parents, recorded author name, subject,
Pakistan-time commit timestamp, changed paths and numstat data. Root commits are
compared with an empty tree; merge statistics use the first parent. Rename
detection is disabled, so renames appear as separate deletion/addition records.
Every reachable commit can appear, including one with no changes in the permitted
file scope; empty scoped statistics are not proof of an empty commit.

- Text additions/deletions are Git numstat counts. Aggregate committed counts sum
  per-commit changes, not the net difference between the day's endpoints. Unique
  path count is separate from repeated file-change count.
- Git's binary `-` counts remain JSON `null`, with a binary classification. They
  are not silently converted to zero. Numeric line totals cover known text changes.
- Staged, unstaged and untracked work remain separate. Untracked filenames are
  reported without opening their contents or inventing line counts.
- Unmerged paths retain conflict status. Their duplicate Git numstat records are
  handled only for paths independently identified as unmerged; their additions
  and deletions and binary classification remain unassessed (`null`), with an
  explicit unmerged count; unknown file kinds do not inflate known text counts.
- The working-tree section describes the **current** checkout at collection time,
  even when a past reporting date is selected. It is not a reconstruction of that
  historical day's working tree.
- Protected evidence paths are excluded from file queries and reports. Submodule
  working trees are not assessed. `clean_scoped` describes this explicit scope,
  not a complete audit of excluded data.

The reporter compares HEAD, branch, status, numstat and index visibility records
before and after collection. This detects observable metadata changes, not every
possible byte change. Equal line counts do not prove identical worktree bytes.
The report explicitly says `stable_observed_git_metadata_not_atomic`.

## Successful, failed, pending and untested work

Git proves recorded changes and metadata. It does not prove tests passed,
implementation is complete, a failed run was repaired, a runtime is qualified, or
a commit is eligible for GitHub's contribution graph. Consequently, the reporter's
own test, CI and contribution assessments remain `not_assessed`. The FIRMAVEX
native Windows status remains `pending`; it is not a new platform probe.

Optional `--observations /absolute/path/to/observations.json` incorporates explicit
operator declarations. They remain `supplied_not_independently_verified`, even
when they contain test counts. The file digest binds the declarations' bytes, not
their truth. With no file, verification is `not_supplied`, the item list is empty
and no successful result is invented.

The input is a bounded JSON object with exactly:

```json
{
  "schema_version": 1,
  "date": "2026-11-23",
  "timezone": "Asia/Karachi",
  "revision": "FULL_CURRENT_HEAD_SHA",
  "items": [
    {
      "id": "windows-preflight",
      "status": "pending",
      "summary": "Native Windows validation has not been executed."
    }
  ]
}
```

This is a template: replace the SHA placeholder with the actual reported HEAD
before use. The selected date, timezone and revision must match the collected
context. IDs must be unique lowercase letters/digits/underscores/hyphens, up to
48 characters. Status is exactly `successful`, `failed`, `pending` or `untested`.
Each item requires a printable summary, up to 2,048 characters; an optional
printable `command` is descriptive data, up to 4,096 characters, and is **never
executed**.

An optional `tests` object must contain exactly the nonnegative integer counters
`passed`, `failed`, `errors`, `skipped` and `deselected`. Booleans are rejected as
counts. Only successful/failed items may carry them: successful test declarations
require at least one pass and no failures/errors; failed declarations require a
failure or error. Skips/deselections remain explicit. Pending/untested work cannot
supply invented executed-test counters. Items are sorted by ID; observation counts
summarize declarations only.

The reporter neither runs those commands nor reads test logs to authenticate the
claims. Keep original evidence separately and retain historical, CI-observed and
user-reported attributions in the development history. No daily empty commit,
backdating, automatic scheduler, contribution promise or artificial activity is
introduced.

## Security review and bounds

The trusted absolute Git executable receives fixed argument arrays, without a
shell. The environment removes inherited `GIT_*` overrides and disables system
and global Git configuration, replacement objects, lazy fetching, optional locks
and prompts. Command arguments disable pagers, fsmonitor, hooks, external diff,
text conversion, rename detection, automatic maintenance and transport access.
Submodule working trees are ignored. Local filter/include configurations and
hidden index visibility flags are refused before worktree comparisons.

Repository root binding and lexical/static path checks are reused from existing
administrative utilities. Reported filenames use NUL-delimited Git formats and
remain data; they are never opened by the reporter or interpolated into commands.
Malformed records, duplicate ordinary numstat paths and ambiguous partial records
are rejected. JSON escapes unusual filenames/control characters. Human summary
output does not echo raw Git stderr, selected absolute host paths or untrusted
commit subjects.

| Boundary | Current limit |
|---|---|
| Reachable history records | 10,000; an excess blocks the report |
| Files per parsed set/commit | 4,096 |
| Selected committed change rows | 50,000 aggregate |
| Retained stdout per Git command | 4 MiB |
| Retained stderr per Git command | 64 KiB; not published |
| Successful Git stdout captures | 32 MiB aggregate |
| Git command timeout | 20 seconds, reduced to remaining collection time |
| Collection admission deadline | 60 seconds; bounded cleanup can extend wall-clock duration |
| Observation JSON | 1 MiB, at most 128 items; existing bounded-reader/JSON complexity checks |

The pipe readers stop retaining data at the limits and trigger failure rather
than passing truncated output to parsers. Timeout, overflow, reader failures and
cancellation attempt bounded Git termination/reaping and reader cleanup. POSIX
Git commands use an owned process group. Windows uses the owned direct process;
this administrative path does not qualify a hostile process tree or claim the
product runtime's isolation guarantees.

These checks require a stable developer-controlled checkout, trusted interpreter,
trusted Git and trusted repository metadata. They do not lock Git configuration,
provide an atomic filesystem snapshot, prevent every concurrent parent-replacement
race, or safely sandbox a malicious checkout/executable. Preserve the unresolved
MEDIUM parent-replacement limitation from the
[Batch 34 review](batch34-preflight-security-review.md). Neither checksum agreement
nor a clean scoped status authenticates the repository owner or supplied evidence.

No production admission, executable pin, release/signing rule, installer,
application backend or frozen research component is changed by this reporter.
No firmware, QEMU, GDB, installer, signer or CI dispatch is performed.

## Actual validation record

The earlier seven-test claim remains attributed to Issue #6 above. Actual tests
for this integrated implementation ran on Linux with Python 3.12.14 and Git
2.47.3, November 23, 2026, using the existing trusted environment:

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_daily_development_report.py
```

**92 passed**, zero failed/errored/skipped/deselected, **4.28 seconds**.

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_daily_development_report.py tests/product/test_windows_preflight_archive.py \
  tests/product/test_windows_preflight_validation.py tests/product/test_windows_runtime_preflight.py \
  tests/product/test_platform_support.py tests/product/test_file_state.py \
  tests/product/test_windows_candidate_closure.py \
  tests/backends/test_records_security.py::test_unsafe_path_spellings_rejected \
  tests/backends/test_records_security.py::test_source_and_parent_symlinks_are_rejected \
  tests/backends/test_records_security.py::test_special_file_rejected_without_blocking \
  tests/backends/test_records_security.py::test_mid_read_changes_fail_closed \
  tests/backends/test_records_security.py::test_same_size_rewrite_with_deferred_metadata_fails_closed
```

**565 passed, 1 skipped**, zero failed/errored/deselected, **10.56 seconds**.
The skip at `test_file_state.py:23` requires actual native NTFS change-time
semantics. Selections overlap and are not additive or a full project/runtime
suite. Synthetic Git histories and subprocess failures were created only in
isolated temporary test locations; their test-only dates/identities are not
project activity or real contribution evidence.

Early integration tests exposed two ordering assumptions in the test fixtures,
corrected to match deterministic sorting, and a legacy Git-admission exception
escaping the reporter's public error type, repaired without adding a PATH fallback.
Independent review then demonstrated a legitimate merge-conflict reporting failure
and identified missing aggregate resource caps plus reader-exception priority.
Unknown conflict counts, aggregate caps/deadlines and control-flow priority now
have passing regressions. Existing assertions and production security were not
weakened.

An actual read-only CLI smoke check against this approved repository was repeated
with identical output. For the recorded Batch 36 commit, it reproduced **five
files, 1,740 additions and zero deletions**; those are Git facts, not new execution
or test evidence. The initial current-day report at the unchanged baseline
correctly contained zero November 23 commits and disclosed uncommitted files.
No milestone or commit was invented to fill that gap.

Static checks passed: two Python AST parses, whitespace across all five changed
files, 162 local documentation links, 23 anchors and 100 existing commit references.
`git diff --check` passed, with new untracked files checked separately. Independent
source/security review found no remaining blocking implementation defect within
the stated trusted-checkout scope. Native Windows verification remains PENDING;
no PowerShell or Windows execution is established by these portable tests. No CI
was manually dispatched.

## Next use

Collect a report for the actual workday, review its Git facts and explicitly
attributed observations, and append a concise supported milestone to the
[development history](development-progress.md). Retain failed and untested work
rather than converting it to a successful contribution claim. Publication remains
a separate authorized Git operation after review and tests.
