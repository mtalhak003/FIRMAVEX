"""Read-only reporting regressions using invented local Git history only."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

from tools import daily_development_report as reporter


GIT = '/usr/bin/git' if Path('/usr/bin/git').is_file() else shutil.which('git')
DAY = '2026-11-23'
STAMP = '2026-11-23T10:00:00+00:00'


def git(repo, *args, stamp=None, expected=0):
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1')
    if stamp:
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    result = subprocess.run([GIT, '-c', 'core.hooksPath=' + os.devnull,
                             '-c', 'commit.gpgSign=false', '-C', str(repo), *args],
                            stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=15)
    assert result.returncode == expected, result.stderr.decode('utf-8', errors='replace')
    return result.stdout


def commit(repo, message='Invented implementation, not validated behavior', stamp=STAMP):
    git(repo, 'add', '--', '.')
    git(repo, 'commit', '-m', message, stamp=stamp)
    return git(repo, 'rev-parse', 'HEAD').decode().strip()


@pytest.fixture
def repo(tmp_path):
    if not GIT:
        pytest.skip('An existing trusted Git executable is required for synthetic repository tests')
    root = tmp_path / 'invented repository with spaces'
    root.mkdir()
    git(root, 'init', '-b', 'product/desktop-batch11')
    git(root, 'config', '--local', 'user.name', 'Synthetic Developer')
    git(root, 'config', '--local', 'user.email', 'synthetic@example.invalid')
    git(root, 'config', '--local', 'core.autocrlf', 'false')
    (root / 'a.txt').write_bytes(b'first\nsecond\n')
    commit(root)
    return root


def collect(repo, **options):
    return reporter.collect_report(repo, day=DAY, git_executable=GIT, **options)


def observation_file(repo, tmp_path, items=None):
    path = tmp_path / 'invented declarations.json'
    data = {'schema_version': 1, 'date': DAY, 'timezone': 'Asia/Karachi',
            'revision': git(repo, 'rev-parse', 'HEAD').decode().strip(),
            'items': [] if items is None else items}
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


def test_root_commit_counts_are_actual_git_facts_without_inferred_test_passes(repo):
    report = collect(repo)
    assert report['schema_version'] == 1 and report['status'] == 'collected'
    assert report['date'] == DAY and report['timezone'] == 'Asia/Karachi'
    assert report['source']['head'] == git(repo, 'rev-parse', 'HEAD').decode().strip()
    assert report['source']['branch'] == 'product/desktop-batch11'
    assert report['source']['detached'] is False
    assert report['source']['history_scope'] == 'reachable_from_head'
    assert report['source']['commit_date_basis'] == 'committer'
    assert len(report['commits']) == 1
    row = report['commits'][0]
    assert row['author'] == 'Synthetic Developer' and row['parents'] == []
    assert row['committed_at'].endswith('+05:00')
    assert row['files'] == [{'path': 'a.txt', 'added': 2, 'deleted': 0, 'binary': False}]
    assert report['totals']['added'] == 2 and report['totals']['deleted'] == 0
    assert report['working_tree']['clean_scoped'] is True
    assert report['validation'] == {'tests': 'not_assessed', 'ci': 'not_assessed',
                                    'github_contributions': 'not_assessed', 'native_windows': 'pending'}
    assert report['observations']['items'] == []
    assert report['observations']['counts'] == dict.fromkeys(('successful', 'failed', 'pending', 'untested'), 0)


def test_pakistan_midnight_window_includes_start_and_excludes_next_day(tmp_path):
    root = tmp_path / 'boundary repo'
    root.mkdir()
    git(root, 'init', '-b', 'synthetic')
    git(root, 'config', '--local', 'user.name', 'Synthetic Developer')
    git(root, 'config', '--local', 'user.email', 'synthetic@example.invalid')
    stamps = ['2026-11-22T18:59:59+00:00', '2026-11-22T19:00:00+00:00',
              '2026-11-23T18:59:59+00:00', '2026-11-23T19:00:00+00:00']
    hashes = []
    for index, stamp in enumerate(stamps):
        (root / 'change.txt').write_text('line\n' * (index + 1))
        hashes.append(commit(root, stamp=stamp))
    report = collect(root)
    assert [row['sha'] for row in report['commits']] == hashes[1:3]
    assert [row['committed_at'] for row in report['commits']] == [
        '2026-11-23T00:00:00+05:00', '2026-11-23T23:59:59+05:00']
    assert report['source']['head'] == hashes[-1]


def test_nonmonotonic_commit_timestamps_do_not_hide_earlier_matching_ancestor(repo):
    first = git(repo, 'rev-parse', 'HEAD').decode().strip()
    (repo / 'a.txt').write_text('yesterday child\n')
    commit(repo, stamp='2026-11-22T10:00:00+00:00')
    (repo / 'a.txt').write_text('today grandchild\n')
    last = commit(repo, stamp='2026-11-23T11:00:00+00:00')
    assert [row['sha'] for row in collect(repo)['commits']] == [first, last]


def test_no_matching_daily_commits_does_not_invent_development(repo):
    report = reporter.collect_report(repo, day='2026-11-20', git_executable=GIT)
    assert report['commits'] == [] and report['totals']['commits'] == 0
    assert report['totals']['added'] == 0 and report['totals']['deleted'] == 0
    assert report['validation']['tests'] == 'not_assessed'


def test_line_changes_and_unique_files_are_separate_from_commit_count(repo):
    (repo / 'a.txt').write_bytes(b'first\nreplacement\nthird\n')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    report = collect(repo)
    assert report['totals']['commits'] == 2
    assert report['totals']['file_changes'] == 2
    assert report['totals']['unique_files'] == 1
    assert report['totals']['added'] == 4
    assert report['totals']['deleted'] == 1


def test_binary_changes_are_not_fabricated_as_zero_text_lines(repo):
    (repo / 'binary.bin').write_bytes(b'\x00invented bytes\xff')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    report = collect(repo)
    row = report['commits'][-1]['files'][0]
    assert row == {'path': 'binary.bin', 'added': None, 'deleted': None, 'binary': True}
    assert report['totals']['binary_file_changes'] == 1
    assert report['commits'][-1]['totals']['binary_files'] == 1


def test_staged_unstaged_and_untracked_work_remain_separate(repo):
    (repo / 'a.txt').write_bytes(b'first\nsecond\nstaged\n')
    git(repo, 'add', '--', 'a.txt')
    (repo / 'a.txt').write_bytes(b'first\nsecond\nstaged\nunstaged\n')
    (repo / 'new file.txt').write_bytes(b'Untracked lines must not be fabricated as diff statistics.\n')
    report = collect(repo)
    working = report['working_tree']
    assert working['clean_scoped'] is False
    assert working['staged']['files'] == [{'path': 'a.txt', 'added': 1, 'deleted': 0, 'binary': False}]
    assert working['unstaged']['files'] == [{'path': 'a.txt', 'added': 1, 'deleted': 0, 'binary': False}]
    assert working['untracked'] == ['new file.txt']
    assert working['submodule_worktrees'] == 'not_assessed'
    entry = next(row for row in working['status'] if row['path'] == 'a.txt')
    assert entry['index'] == 'M' and entry['worktree'] == 'M'
    assert report['totals']['added'] == 2


def test_detached_head_is_reported_without_checkout_or_branch_mutation(repo):
    git(repo, 'checkout', '--detach')
    head_before = (repo / '.git/HEAD').read_bytes()
    report = collect(repo)
    assert report['source']['branch'] is None and report['source']['detached'] is True
    assert (repo / '.git/HEAD').read_bytes() == head_before


def test_merge_statistics_use_first_parent_once(repo):
    git(repo, 'checkout', '-b', 'side')
    (repo / 'side.txt').write_text('side contribution\n')
    commit(repo, stamp='2026-11-22T11:00:00+00:00')
    git(repo, 'checkout', 'product/desktop-batch11')
    (repo / 'main.txt').write_text('main contribution\n')
    commit(repo, stamp='2026-11-22T12:00:00+00:00')
    git(repo, 'merge', '--no-ff', 'side', '-m', 'Invented merge', stamp='2026-11-23T12:00:00+00:00')
    merge = collect(repo)['commits'][-1]
    assert len(merge['parents']) == 2
    assert merge['files'] == [{'path': 'side.txt', 'added': 1, 'deleted': 0, 'binary': False}]


@pytest.mark.parametrize('name', ['tab\tname.txt', 'newline\nname.txt', 'with space.txt', 'quote"name.txt'],
                         ids=['tab', 'newline', 'space', 'quote'])
def test_unusual_git_filenames_are_data_not_line_delimiters(repo, name):
    if os.name == 'nt' and any(character in name for character in '\t\n"'):
        pytest.skip('Windows filename restrictions do not allow this synthetic filename')
    (repo / name).write_bytes(b'one\n')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    report = collect(repo)
    assert report['commits'][-1]['files'][0]['path'] == name
    encoded = json.dumps(report, sort_keys=True)
    assert json.loads(encoded)['commits'][-1]['files'][0]['path'] == name


def test_numstat_parser_preserves_tabs_newlines_and_binary_unknown_counts():
    rows = reporter._parse_numstat(b'2\t1\todd\tname\n.txt\0-\t-\tbinary.bin\0')
    records = {row['path']: row for row in rows}
    assert records['odd\tname\n.txt']['added'] == 2
    assert records['binary.bin']['added'] is None and records['binary.bin']['binary'] is True


@pytest.mark.parametrize('payload', [b'1\t0\tfile', b'x\t0\tfile\0', b'-1\t0\tfile\0',
    b'-\t0\tfile\0', b'1\t0\tx\0' * 2, b'1\t0\t../escape\0',
    b'1\t0\t/absolute\0', b'1\t0\tevidence/windows-sandbox/never-open\0'],
    ids=['unterminated', 'nonnumeric', 'negative', 'half-binary', 'duplicate', 'traversal', 'absolute', 'protected'])
def test_malformed_or_unsafe_numstat_fails_closed(payload):
    with pytest.raises(reporter.ReportError):
        reporter._parse_numstat(payload)


def test_status_parser_uses_nul_boundaries():
    rows = reporter._parse_status(b' M ordinary.txt\0?? odd\tname\n.txt\0')
    assert rows == sorted([{'index': ' ', 'worktree': 'M', 'path': 'ordinary.txt'},
                           {'index': '?', 'worktree': '?', 'path': 'odd\tname\n.txt'}], key=lambda row: row['path'])


@pytest.mark.parametrize('payload', [b' M no-terminator', b'X wrong\0', b'ZZ wrong\0',
                                   b'?? ../escape\0', b'?? /absolute\0', b'?? dup\0?? dup\0'],
                         ids=['unterminated', 'short', 'invalid-state', 'traversal', 'absolute', 'duplicate'])
def test_malformed_status_is_not_reported_as_clean(payload):
    with pytest.raises(reporter.ReportError):
        reporter._parse_status(payload)


def test_report_is_deterministic_and_never_writes_repository_or_runs_network(repo, monkeypatch):
    tracked = [repo / 'a.txt', repo / '.git/HEAD', repo / '.git/index']
    before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked}
    original = reporter.Git.run
    calls = []
    def observed(self, *args):
        calls.append(args)
        assert args[0] in {'rev-parse', 'config', 'ls-files', 'status', 'log', 'diff', 'diff-tree', 'branch'}
        return original(self, *args)
    def forbidden(*args, **kwargs):
        raise AssertionError('Reporter attempted Python network access')
    monkeypatch.setattr(reporter.Git, 'run', observed)
    monkeypatch.setattr(socket, 'socket', forbidden)
    first, second = collect(repo), collect(repo)
    assert first == second and calls
    assert before == {str(path): (path.read_bytes(), path.stat().st_mtime_ns) for path in tracked}


def test_poisoned_git_environment_cannot_redirect_repository(repo, monkeypatch):
    monkeypatch.setenv('GIT_DIR', '/never-inspect-poisoned-repository')
    monkeypatch.setenv('GIT_WORK_TREE', '/never-inspect-poisoned-worktree')
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'core.fsmonitor')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'NEVER_EXECUTE')
    assert collect(repo)['source']['head'] == git(repo, 'rev-parse', 'HEAD').decode().strip()


@pytest.mark.parametrize('key', ['filter.synthetic.clean', 'include.path', 'includeIf.gitdir:*/.path'],
                         ids=['filter', 'include', 'conditional-include'])
def test_unsupported_local_helper_configuration_is_refused_before_status(repo, monkeypatch, key):
    git(repo, 'config', '--local', key, 'NEVER_EXECUTE_OR_READ')
    original = reporter.Git.run
    def no_worktree(self, *args):
        assert args[0] not in {'status', 'diff', 'diff-tree'}, 'Unsafe configuration reached worktree commands'
        return original(self, *args)
    monkeypatch.setattr(reporter.Git, 'run', no_worktree)
    with pytest.raises(reporter.ReportError):
        collect(repo)


@pytest.mark.parametrize('flag', ['--assume-unchanged', '--skip-worktree'], ids=['assume-unchanged', 'skip-worktree'])
def test_hidden_index_visibility_flags_are_not_misreported_as_clean(repo, flag):
    git(repo, 'update-index', flag, '--', 'a.txt')
    with pytest.raises(reporter.ReportError):
        collect(repo)


def test_observable_worktree_change_during_collection_is_rejected(repo, monkeypatch):
    original = reporter.Git.run
    seen = 0
    def changing(self, *args):
        nonlocal seen
        data = original(self, *args)
        if args[0] == 'status':
            seen += 1
            if seen == 1:
                (repo / 'a.txt').write_bytes(b'changed after initial observation\n')
        return data
    monkeypatch.setattr(reporter.Git, 'run', changing)
    with pytest.raises(reporter.ReportError):
        collect(repo)


def test_observable_head_change_during_collection_is_rejected(repo, monkeypatch):
    original = reporter.Git.run
    changed = False
    def changing(self, *args):
        nonlocal changed
        data = original(self, *args)
        if args[0] == 'log' and not changed:
            changed = True
            (repo / 'a.txt').write_bytes(b'new revision during observation\n')
            commit(repo, stamp='2026-11-23T12:00:00+00:00')
        return data
    monkeypatch.setattr(reporter.Git, 'run', changing)
    with pytest.raises(reporter.ReportError):
        collect(repo)


@pytest.mark.parametrize('control', [KeyboardInterrupt('synthetic'), SystemExit(23), BaseException('synthetic')],
                         ids=['interrupt', 'exit', 'base'])
def test_control_flow_propagates_as_original_object(repo, monkeypatch, control):
    def interrupt(self, *args):
        raise control
    monkeypatch.setattr(reporter.Git, 'run', interrupt)
    with pytest.raises(type(control)) as caught:
        collect(repo)
    assert caught.value is control


def test_explicit_success_failure_pending_untested_are_supplied_not_inferred(repo, tmp_path):
    counters = dict(passed=3, failed=0, errors=0, skipped=1, deselected=0)
    items = [dict(id='focused', status='successful', summary='Synthetic declared result', tests=counters),
             dict(id='failure', status='failed', summary='Synthetic declared failure',
                  tests={**counters, 'passed': 0, 'failed': 1}),
             dict(id='native', status='pending', summary='Native Windows remains pending'),
             dict(id='future', status='untested', summary='No test claim supplied')]
    path = observation_file(repo, tmp_path, items)
    before = path.read_bytes(), path.stat().st_mtime_ns
    report = collect(repo, observations=path)
    assert report['observations']['items'] == sorted(items, key=lambda row: row['id'])
    assert report['observations']['counts'] == dict.fromkeys(('successful', 'failed', 'pending', 'untested'), 1)
    assert report['observations']['verification'] == 'supplied_not_independently_verified'
    assert report['observations']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report['validation']['tests'] == 'not_assessed'
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize('change', ['wrong-date', 'wrong-revision', 'wrong-timezone', 'bool-schema',
    'unknown-state', 'duplicate-id', 'bad-counter', 'success-has-failure', 'pending-has-tests',
    'unknown-field', 'control-character', 'oversized-summary'], ids=lambda value: value)
def test_invalid_observations_fail_without_inventing_result(repo, tmp_path, change):
    item = dict(id='synthetic', status='successful', summary='Invented declaration',
                tests=dict(passed=1, failed=0, errors=0, skipped=0, deselected=0))
    path = observation_file(repo, tmp_path, [item])
    data = json.loads(path.read_text())
    if change == 'wrong-date': data['date'] = '2026-11-22'
    elif change == 'wrong-revision': data['revision'] = '0' * 40
    elif change == 'wrong-timezone': data['timezone'] = 'UTC'
    elif change == 'bool-schema': data['schema_version'] = True
    elif change == 'unknown-state': data['items'][0]['status'] = 'approved'
    elif change == 'duplicate-id': data['items'].append(dict(item))
    elif change == 'bad-counter': data['items'][0]['tests']['passed'] = True
    elif change == 'success-has-failure': data['items'][0]['tests']['failed'] = 1
    elif change == 'pending-has-tests': data['items'][0]['status'] = 'pending'
    elif change == 'unknown-field': data['secrets'] = 'Do not echo raw metadata'
    elif change == 'control-character': data['items'][0]['summary'] = 'private\x1b[31m'
    else: data['items'][0]['summary'] = 'x' * 2049
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(reporter.ReportError):
        collect(repo, observations=path)


@pytest.mark.parametrize('payload', [b'{broken', b'{"schema_version":1,"schema_version":1}', b'[' * 100 + b'0' + b']' * 100],
                         ids=['malformed', 'duplicate-key', 'nesting'])
def test_malformed_observation_bytes_are_rejected(repo, tmp_path, payload):
    path = tmp_path / 'invented malformed.json'
    path.write_bytes(payload)
    with pytest.raises(reporter.ReportError):
        collect(repo, observations=path)


def test_declared_command_is_data_and_never_executed(repo, tmp_path, monkeypatch):
    command = 'DO_NOT_EXECUTE ; echo fabricated-proof'
    path = observation_file(repo, tmp_path, [dict(id='manual', status='untested', summary='Only a declaration', command=command)])
    original = subprocess.Popen
    def observed(args, *rest, **kwargs):
        assert isinstance(args, list) and command not in args
        assert not kwargs.get('shell', False)
        return original(args, *rest, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', observed)
    report = collect(repo, observations=path)
    assert report['observations']['items'][0]['command'] == command


@pytest.mark.parametrize('day', ['not-a-date', '2026-11-31', '2026-1-1', '', '20261123'],
                         ids=['text', 'impossible', 'short', 'empty', 'compact'])
def test_invalid_explicit_day_is_rejected(repo, day):
    with pytest.raises(reporter.ReportError):
        reporter.collect_report(repo, day=day, git_executable=GIT)


def test_relative_git_executable_has_no_path_fallback(repo):
    with pytest.raises(reporter.ReportError):
        reporter.collect_report(repo, day=DAY, git_executable='git')


def test_git_command_arrays_use_explicit_executable_and_disabled_helpers(repo, monkeypatch):
    original = subprocess.Popen
    calls = []
    def observed(args, *rest, **kwargs):
        calls.append((args, kwargs))
        assert Path(args[0]).is_absolute()
        assert not kwargs.get('shell', False)
        assert '--no-optional-locks' in args and '--no-pager' in args
        assert 'core.fsmonitor=false' in args and 'protocol.allow=never' in args
        env = kwargs['env']
        assert env.get('GIT_NO_LAZY_FETCH') == '1' and env.get('GIT_NO_REPLACE_OBJECTS') == '1'
        return original(args, *rest, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', observed)
    collect(repo)
    assert calls
    for args, _ in calls:
        if 'diff' in args or 'diff-tree' in args:
            assert '--no-ext-diff' in args and '--no-textconv' in args and '--no-renames' in args
            assert ':(exclude)evidence/**' in args
        if 'status' in args:
            assert ':(exclude)evidence/**' in args


def test_cli_valid_report_has_sanitized_summary_and_no_write_option(repo, capsys):
    code = reporter.main(['--repo', str(repo), '--git-executable', GIT, '--date', DAY])
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert code == 0 and report['status'] == 'collected'
    assert str(repo) not in captured.out + captured.err
    assert captured.err.strip()


def test_cli_blocked_arguments_do_not_echo_private_values(capsys):
    private = 'PRIVATE-CREDENTIAL-DO-NOT-ECHO'
    code = reporter.main(['--unknown-' + private])
    captured = capsys.readouterr()
    assert code == 2
    assert private not in captured.out + captured.err
    assert json.loads(captured.out)['status'] == 'blocked'


def test_failed_supplied_observation_does_not_make_report_generation_a_test_failure(repo, tmp_path, capsys):
    path = observation_file(repo, tmp_path, [dict(id='failed', status='failed', summary='Invented historical failure')])
    code = reporter.main(['--repo', str(repo), '--git-executable', GIT, '--date', DAY, '--observations', str(path)])
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report['observations']['counts']['failed'] == 1
    assert report['validation']['tests'] == 'not_assessed'


def test_history_bound_refuses_silent_truncation(repo, monkeypatch):
    (repo / 'a.txt').write_text('second synthetic commit\n')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    monkeypatch.setattr(reporter, 'MAX_COMMITS', 1)
    with pytest.raises(reporter.ReportError):
        collect(repo)


def test_file_count_bound_rejects_partial_statistics(repo, monkeypatch):
    (repo / 'second.txt').write_text('second file\n')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    monkeypatch.setattr(reporter, 'MAX_FILES', 1)
    with pytest.raises(reporter.ReportError):
        collect(repo)


def test_bounded_capture_rejects_overflow_and_reaps_owned_process(monkeypatch):
    monkeypatch.setattr(reporter, 'MAX_OUTPUT', 64)
    original = subprocess.Popen
    processes = []
    def observe(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', observe)
    with pytest.raises(reporter.ReportError, match='git_output_bound'):
        reporter._capture([sys.executable, '-B', '-c', "print('x' * 16384)"], dict(os.environ))
    assert len(processes) == 1 and processes[0].poll() is not None


def test_bounded_capture_timeout_reaps_owned_process(monkeypatch):
    monkeypatch.setattr(reporter, 'TIMEOUT', 0.05)
    original = subprocess.Popen
    processes = []
    def observe(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', observe)
    with pytest.raises(reporter.ReportError, match='git_timeout'):
        reporter._capture([sys.executable, '-B', '-c', 'import time; time.sleep(5)'], dict(os.environ))
    assert len(processes) == 1 and processes[0].poll() is not None


@pytest.mark.parametrize('control', [KeyboardInterrupt('synthetic'), SystemExit(31), BaseException('synthetic')],
                         ids=['keyboard', 'exit', 'base'])
def test_capture_control_flow_preserves_original_and_reaps_process(monkeypatch, control):
    original_popen = subprocess.Popen
    original_clock = reporter.clock.monotonic
    processes = []
    first = True
    def observe(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process
    def interrupt_once():
        nonlocal first
        if first:
            first = False
            raise control
        return original_clock()
    monkeypatch.setattr(subprocess, 'Popen', observe)
    monkeypatch.setattr(reporter.clock, 'monotonic', interrupt_once)
    with pytest.raises(type(control)) as caught:
        reporter._capture([sys.executable, '-B', '-c', 'import time; time.sleep(5)'], dict(os.environ))
    assert caught.value is control
    assert len(processes) == 1 and processes[0].poll() is not None


def test_capture_nonzero_command_does_not_expose_stderr():
    private = 'PRIVATE-DIAGNOSTIC-DO-NOT-PRINT'
    with pytest.raises(reporter.ReportError, match='git_command_failed') as caught:
        reporter._capture([sys.executable, '-B', '-c',
                           f"import sys; sys.stderr.write({private!r}); raise SystemExit(7)"], dict(os.environ))
    assert private not in str(caught.value)


def test_explicit_wrong_head_is_rejected(repo):
    with pytest.raises(reporter.ReportError, match='revision_mismatch'):
        reporter.collect_report(repo, day=DAY, git_executable=GIT, expected_head='0' * 40)


def test_observations_cannot_change_between_reads(repo, tmp_path, monkeypatch):
    path = observation_file(repo, tmp_path)
    original = reporter.read_bytes
    seen = False
    def change(selected, maximum, **kwargs):
        nonlocal seen
        data = original(selected, maximum, **kwargs)
        if Path(selected) == path and not seen:
            seen = True
            record = json.loads(data)
            record['items'] = [dict(id='changed', status='untested', summary='Changed during collection')]
            path.write_text(json.dumps(record))
        return data
    monkeypatch.setattr(reporter, 'read_bytes', change)
    with pytest.raises(reporter.ReportError, match='observations_changed'):
        collect(repo, observations=path)


def test_missing_timezone_database_fails_explicitly(repo, monkeypatch):
    def unavailable(name):
        raise reporter.ZoneInfoNotFoundError('Synthetic missing IANA database')
    monkeypatch.setattr(reporter, 'ZoneInfo', unavailable)
    with pytest.raises(reporter.ReportError, match='timezone_data_unavailable'):
        collect(repo)


def wrapped_cleanup_process(monkeypatch, error):
    original = subprocess.Popen
    owned = []
    class WithCleanupFailure:
        def __init__(self, process):
            self.process = process
        def __getattr__(self, name):
            return getattr(self.process, name)
        def wait(self, timeout=None):
            result = self.process.wait(timeout=timeout)
            if timeout == 2:
                raise error
            return result
    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        owned.append(process)
        return WithCleanupFailure(process)
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    return owned


@pytest.mark.parametrize('control', [KeyboardInterrupt('cleanup'), SystemExit(47), BaseException('cleanup')],
                         ids=['keyboard', 'exit', 'base'])
def test_cleanup_only_control_flow_is_not_masked_by_successful_capture(monkeypatch, control):
    owned = wrapped_cleanup_process(monkeypatch, control)
    with pytest.raises(type(control)) as caught:
        reporter._capture([sys.executable, '-B', '-c', "print('invented output')"], dict(os.environ))
    assert caught.value is control
    assert len(owned) == 1 and owned[0].poll() is not None


def test_cleanup_control_supersedes_ordinary_primary_failure(monkeypatch):
    control = SystemExit(49)
    owned = wrapped_cleanup_process(monkeypatch, control)
    with pytest.raises(SystemExit) as caught:
        reporter._capture([sys.executable, '-B', '-c', 'raise SystemExit(7)'], dict(os.environ))
    assert caught.value is control and owned[0].poll() is not None


def test_existing_primary_control_retains_priority_over_cleanup_control(monkeypatch):
    primary, cleanup = KeyboardInterrupt('original cancellation'), SystemExit(51)
    owned = wrapped_cleanup_process(monkeypatch, cleanup)
    original_clock = reporter.clock.monotonic
    first = True
    def interrupt_once():
        nonlocal first
        if first:
            first = False
            raise primary
        return original_clock()
    monkeypatch.setattr(reporter.clock, 'monotonic', interrupt_once)
    with pytest.raises(KeyboardInterrupt) as caught:
        reporter._capture([sys.executable, '-B', '-c', 'import time; time.sleep(5)'], dict(os.environ))
    assert caught.value is primary and owned[0].poll() is not None


def test_ordinary_cleanup_failure_prevents_success_report(monkeypatch):
    owned = wrapped_cleanup_process(monkeypatch, OSError('Synthetic private cleanup detail'))
    with pytest.raises(reporter.ReportError, match='git_cleanup_failed'):
        reporter._capture([sys.executable, '-B', '-c', "print('invented output')"], dict(os.environ))
    assert len(owned) == 1 and owned[0].poll() is not None


def test_reader_thread_start_failure_reaps_process_and_preserves_error(monkeypatch):
    original = subprocess.Popen
    owned = []
    error = RuntimeError('Synthetic thread setup failure')
    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        owned.append(process)
        return process
    def fail_start(self):
        raise error
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    monkeypatch.setattr(reporter.threading.Thread, 'start', fail_start)
    with pytest.raises(RuntimeError) as caught:
        reporter._capture([sys.executable, '-B', '-c', 'import time; time.sleep(5)'], dict(os.environ))
    assert caught.value is error and len(owned) == 1 and owned[0].poll() is not None


def test_real_synthetic_merge_conflict_preserves_unknown_line_accounting(repo):
    git(repo, 'checkout', '-b', 'conflicting-side')
    (repo / 'a.txt').write_text('side replacement\n')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    git(repo, 'checkout', 'product/desktop-batch11')
    (repo / 'a.txt').write_text('main replacement\n')
    commit(repo, stamp='2026-11-23T12:00:00+00:00')
    git(repo, 'merge', '--no-ff', 'conflicting-side', '-m', 'Invented conflict',
        stamp='2026-11-23T13:00:00+00:00', expected=1)
    report = collect(repo)
    working = report['working_tree']
    assert working['clean_scoped'] is False and working['unmerged'] == ['a.txt']
    entry = next(row for row in working['status'] if row['path'] == 'a.txt')
    assert entry['index'] == entry['worktree'] == 'U'
    for phase in ('staged', 'unstaged'):
        row = next(row for row in working[phase]['files'] if row['path'] == 'a.txt')
        assert row['unmerged'] is True and row['binary'] is None
        assert row['added'] is None and row['deleted'] is None
        assert working[phase]['totals']['unmerged_files'] == 1
        assert working[phase]['totals']['added'] == 0 and working[phase]['totals']['deleted'] == 0


def test_aggregate_capture_limit_applies_across_individually_valid_commands(repo, monkeypatch):
    monkeypatch.setattr(reporter, 'MAX_CAPTURE_BYTES', 81)
    selected = reporter.Git(repo, GIT)
    assert len(selected.run('rev-parse', 'HEAD')) == 41
    with pytest.raises(reporter.ReportError, match='aggregate_capture_bound'):
        selected.run('rev-parse', 'HEAD')


def test_aggregate_change_limit_does_not_silently_drop_later_file_changes(repo, monkeypatch):
    (repo / 'a.txt').write_text('second committed change\n')
    commit(repo, stamp='2026-11-23T11:00:00+00:00')
    monkeypatch.setattr(reporter, 'MAX_CHANGES', 1)
    with pytest.raises(reporter.ReportError, match='aggregate_change_bound'):
        collect(repo)


def test_expired_collection_deadline_refuses_dispatch(repo, monkeypatch):
    selected = reporter.Git(repo, GIT)
    selected.deadline = reporter.clock.monotonic() - 1
    def forbidden(*args, **kwargs):
        raise AssertionError('Expired collection dispatched another process')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    with pytest.raises(reporter.ReportError, match='collection_timeout'):
        selected.run('rev-parse', 'HEAD')


def test_collection_deadline_is_checked_after_command_completion(repo, monkeypatch):
    selected = reporter.Git(repo, GIT)
    def finish_late(command, environment, *, timeout=None):
        assert timeout is not None and 0 < timeout <= reporter.TIMEOUT
        selected.deadline = reporter.clock.monotonic() - 1
        return b'Invented command result returned after the collection deadline'
    monkeypatch.setattr(reporter, '_capture', finish_late)
    with pytest.raises(reporter.ReportError, match='collection_timeout'):
        selected.run('rev-parse', 'HEAD')


def test_reader_control_flow_supersedes_ordinary_reader_error_without_masking(monkeypatch):
    # Synthetic pipe/process objects only; this test dispatches no OS process.
    primary = OSError('Invented ordinary reader failure')
    control = SystemExit(73)
    observed_first = reporter.threading.Event()
    class Stream:
        def __init__(self, first): self.first = first
        def read(self, count):
            if self.first:
                observed_first.set()
                raise primary
            assert observed_first.wait(timeout=2)
            raise control
        def close(self): pass
    class Process:
        pid = 12345
        returncode = 0
        stdout, stderr = Stream(True), Stream(False)
        def poll(self): return 0
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: Process())
    if os.name == 'posix':
        monkeypatch.setattr(reporter.os, 'killpg', lambda *args: None)
    with pytest.raises(SystemExit) as caught:
        reporter._capture(['/unused/synthetic-git'], {})
    assert caught.value is control
