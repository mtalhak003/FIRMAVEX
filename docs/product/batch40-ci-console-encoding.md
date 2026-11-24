# Batch 40 — Windows CI console encoding reliability

**Date:** November 24, 2026, Asia/Karachi.
**Starting revision:**
[`4d6aef91b1ad28a848d70a3c928d27d932e0d5c6`](https://github.com/mtalhak003/FIRMAVEX/commit/4d6aef91b1ad28a848d70a3c928d27d932e0d5c6).
**Tracking:** [Issue #7](https://github.com/mtalhak003/FIRMAVEX/issues/7).
This is a CI console-rendering repair, not Windows firmware qualification or a
change to application execution, resource policy or release status.
**Implementation commit:**
[`205404bebd1ce5e23cf715a613b46d1443b3970e`](https://github.com/mtalhak003/FIRMAVEX/commit/205404bebd1ce5e23cf715a613b46d1443b3970e).

## Evidence and starting state

The approved worktree was clean outside deliberately excluded evidence paths at
the expected revision. Remote `product/desktop-batch11` matched it. The worktree
remained detached; no other checkout, unfinished work or branch was overwritten.

The public [Batch 39 product run](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45268795232)
and [Windows Python 3.12 job](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45268795232/job/138022742697)
identify that exact revision. The Windows job failed in **Exercise desktop with
synthetic workers**. Its public retained phase reports `completed: pytest status=1`;
the six other jobs display success, including Ubuntu real-product testing. These
are independently observed public CI statuses, not verification of an original
artifact ZIP or its JUnit accounting.

The precise traceback, U+FFFD offset 62525 and preceding selection's reported
four passes are recorded in the issue's prior investigation comment and the
user's confirmed failure report. Full job logs require sign-in and the GitHub CLI
issue request returned `Forbidden`; those raw logs were not independently retrieved
here. The source at the pinned revision confirms the affected operation:

```python
print(process.stdout, end='', flush=True)
```

`run_tests()` has already captured the original child output to a file, completed
ownership cleanup, and decoded its bounded tail with UTF-8 `errors='replace'`.
A strict CP1252 output stream cannot encode the resulting U+FFFD. The character
can reflect invalid bytes or a tail starting inside a multibyte sequence; its
presence alone does not establish the original bytes or a firmware error.

**The nonzero desktop selection remains important.** Fixing the relay must reveal
its underlying failure rather than imply the original desktop tests passed.
Without the original transcript/JUnit or a subsequent run, its exact cause remains
unresolved. The issue's earlier note that the relay error alone does not establish
a desktop failure is retained alongside this separately observed nonzero status.

## Minimal implementation and invariants

The [launcher](../../tools/product_ci_tests.py) uses one `console_print()` helper
for all six console emission sites: admission notice, transcript tail, process
failure annotation, JUnit failure annotation, retained state and timeout details.
It obtains the current output stream and, when an encoding is declared, encodes
the text using that encoding with `backslashreplace`, then decodes it using the
same encoding before printing and flushing.

For CP1252, `café €` stays representable while U+FFFD becomes the visible ASCII
sequence `\ufffd`; other unsupported characters use Python's corresponding
backslash escapes. A UTF-8 console keeps those Unicode characters. In-memory
streams without a declared encoding retain the original text. Conversion happens
before writing, avoiding a retry after a possibly partial console write. No
global output reconfiguration or silent `ignore`/replacement-character dropping
was introduced. Escapes can make the displayed preview longer than its source
tail; the underlying capture and existing annotation slicing limits are unchanged.

The implementation does not catch write, flush, encoding-metadata or unknown-codec
errors. Broken pipes, I/O failures and `KeyboardInterrupt`, `SystemExit` or other
control-flow exceptions still propagate. A failed console is not relabelled as a
passing test run. Supported status, error, timeout and signal return codes remain
unchanged when reporting completes normally.

Unchanged boundaries include:

- Original transcript **bytes**, including invalid UTF-8 bytes; only the existing
  preview is decoded with replacement. No evidence file is repaired or rewritten.
- JUnit identities, failure details and UTF-8 step-summary content.
- Existing percent/newline annotation escaping and failure classifications.
- Child admission, Job Object/process-group ownership, cleanup and deadlines.
- Complete supplied test selection, assertions, production runtime identities,
  signatures, admission, frozen research and main.

Existing private raw diagnostics can still contain paths. Console compatibility
does not make the retained archive sanitized or authorize publishing private logs.

## Actual validation and failed attempts

The original print operation was reproduced against a real Python
`TextIOWrapper(BytesIO(), encoding='cp1252', errors='strict')` on Linux. It raised
`UnicodeEncodeError`. After the repair, supported characters stayed intact and
the unsupported characters appeared as escapes. This intentionally failing
reproducer is not a native Windows result or a failed project regression suite.

An initial three-test existing-launcher selection passed in **0.68 seconds**.
The first new focused selection passed **31 tests, 20 deselected**, **0.96 seconds**.
Three additional unknown-codec/encoding-metadata cases were then added; the final
focused selection passed **34 tests, 20 deselected**, **0.97 seconds**, with zero
failures/errors/skips. These overlapping counts must not be summed.

```bash
PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider tests/product/test_ci_diagnostics.py -k 'console or encoding or retained_diagnostics_render or real_pytest_cp1252'
```

The [initial 33 added regression cases](../../tests/product/test_ci_diagnostics.py) cover
CP1252 and UTF-8, supported/unsupported Unicode, U+FFFD, empty/long output, unknown
codecs and stream metadata, write/flush failures and control flow. Selection
fixtures retain statuses `0`, `1`, `2`, `124` and `-9`, original bytes/JUnit,
failure annotations and UTF-8 summaries. Two genuine local pytest child processes
use `PYTHONIOENCODING=cp1252:strict`, one passing and one intentionally failing;
their expected outcomes are assertions in passing outer regression tests. They
execute invented trusted Python tests, not firmware or original research evidence.

The wider relevant selection ran with Linux offscreen Qt:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /workspace/firmavex-batch7-venv/bin/python -B -m pytest -q -ra -p no:cacheprovider \
  tests/product/test_ci_diagnostics.py tests/product/test_supervisor.py \
  tests/product/test_windows_job.py tests/product/test_worker.py \
  tests/product/test_protocol.py tests/product/test_build_inputs.py \
  tests/product/test_versioned_install_ci.py tests/desktop -k 'not real_desktop'
```

**628 passed, 25 skipped, 4 deselected**, zero failures/errors, **44.81 seconds**.
The four deselections use the unchanged existing CI desktop selector; no test was
disabled to repair this failure. All 54 launcher tests are included in this wider
selection. The 25 skips are 13 native-Windows prerequisites, one actual macOS
path-alias test and 11 missing ARM/RV32/Icarus prerequisites:

- `test_supervisor.py:226`, `test_windows_job.py:64`/`:230`: five Windows ownership
  cases.
- `test_path_identity.py:41`/`:61`: one Windows and one macOS path case.
- `test_real_builtin.py:134` and `test_real_universal.py:20`: 11 runtime-dependent
  cases, retaining their missing-tool guards.
- `test_windows_candidate_rejection.py:12`: one explicit native candidate case.
- `test_windows_desktop_paths.py:137`/`:155`/`:217`/`:238`: six actual Windows file
  sharing/attributes/locking cases.

These are overlapping focused/wider selections, not a full repository suite.
Initial prepublication static validation passed two Python AST parses, all six intended files'
newline/trailing-whitespace checks, 167 local documentation links including 23
heading anchors, and 106 unique locally resolved commit references.
`git diff --check` passed. No workflow was modified or manually dispatched.

## Native CI follow-up and newline-fixture repair

The normal fast-forward publication at
[`0a6894027f1b99ee38eac6ed915b0d4eac203a37`](https://github.com/mtalhak003/FIRMAVEX/commit/0a6894027f1b99ee38eac6ed915b0d4eac203a37)
automatically started [product run 45388541130](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45388541130).
The [Windows Python 3.11 job](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45388541130/job/138425791487)
and [Windows Python 3.12 job](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45388541130/job/138425791483)
failed in **Exercise platform-neutral product behavior**. Public annotations show
the new byte assertions receiving CRLF instead of LF; exact native pytest totals
were not independently recovered. Annotation counts are not test counts. These
jobs did not reach the original later desktop failure.

This was a portability defect in the new tests, not permission to change console
newline behavior or remove assertions. Their `TextIOWrapper` fixtures used the
default `newline=None`, which translates LF to the Windows line separator. The
three byte-exact fixtures now explicitly use `newline=''`. A separate added case
uses `newline='\r\n'` and requires exact CRLF bytes, supported accented text and
the visible U+FFFD escape on every host. A local explicit-CRLF probe reproduced
the difference. Production `console_print()` and all assertions are preserved.

After that repair, the focused command above reported **35 passed, 20 deselected**,
zero failures/errors/skips, **1.11 seconds**. There are now 34 added cases and
55 launcher cases overall. The failed native attempt is retained as evidence of
the fixture defect; the repaired revision still requires its own Windows result.
The unchanged wider command then reported **629 passed, 25 skipped, 4 deselected**,
zero failures/errors, **43.92 seconds**. All 55 launcher cases are included;
the skip/exclusion reasons above are unchanged. Earlier counts remain historical.
Final repair checks passed two ASTs, six-file whitespace, 167 local links/23
anchors, 107 locally resolved commit references and `git diff --check`.

The authorized Issue #7 update was attempted through both `gh issue comment`
(GraphQL) and the REST comments endpoint. Both returned `Forbidden`; no update is
claimed. The factual draft was retained outside the repository for later posting
with authorized issue-write access. Git transport remained available.

## Native Windows and remaining blockers

The local execution host is Linux/Python 3.12.14. Native Windows CI first exposed
the fixture failure above. After the test repair, native Windows Python 3.12
regression validation **PASSED** at
[`2ab543003681f06f666c19792402a4e378f9591a`](https://github.com/mtalhak003/FIRMAVEX/commit/2ab543003681f06f666c19792402a4e378f9591a),
[run 45389653686, job 138429664158](https://github.com/mtalhak003/FIRMAVEX/actions/runs/45389653686/job/138429664158),
in **2 minutes 50 seconds**, as independently observed on the public job page.
Both platform-neutral and synthetic-desktop selections report pytest status `0`;
all four retained completed-selection statuses are `0`. No original artifact/JUnit
totals were independently recovered, so no exact native per-test count is claimed.
The prior underlying desktop failure did not recur; its original cause is not
retroactively established by this successful run.
All six Windows/Ubuntu/macOS Python matrix jobs displayed success; Windows 3.11
completed in 3 minutes 34 seconds. The separate Ubuntu real-product job was still
running at inspection, so the entire seven-job workflow is not claimed green.

This is native host pytest/offscreen-Qt regression evidence, not a manual consumer
trial, Windows Batch 35 preflight completion, firmware-runtime qualification,
frozen installer acceptance or a release. The subsequent documentation update
records this exact tested revision; it does not extend the result to future code.
The existing product matrix selects the new cases without workflow changes or
manual dispatch. Match later conclusions to their actual revision and attempt.

The [Batch 39 report](batch39-ci-reliability.md) retains the separate unresolved
Linux namespace denial and Windows admitted-runtime acquisition blockers. This
repair changes neither. Current QEMU/GDB identity mismatches require actual
retained diagnostics; historical candidate identities are not substituted.
No runtime, firmware, installer, signer, host-policy change or release promotion
is part of this batch.

Recommended Batch 41: inspect the newly visible Windows desktop failure/JUnit,
reproduce its exact failing test if evidence supports it, and repair it separately.
Continue authorized collection of runtime identity and exact-run isolation audit
evidence without weakening gates or assuming a new production qualification.
