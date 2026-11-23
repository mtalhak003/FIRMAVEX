"""Offline daily Git facts and explicitly attributed validation declarations.

No tests, Git writes, network requests or archive/firmware operations are run.
A collected report proves neither completed work nor GitHub contribution credit.
Use an operator-trusted Git executable and stable, developer-controlled checkout.
"""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time as clock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from firmavex.backends.security import checked_path, read_bytes
from tools import windows_preflight_validation as validation
from tools import windows_runtime_preflight as preflight

TIMEZONE = 'Asia/Karachi'
MAX_COMMITS = 10000
MAX_FILES = 4096
MAX_OUTPUT = 4 * 1024**2
MAX_CAPTURE_BYTES = 32 * 1024**2
MAX_CHANGES = 50000
MAX_COLLECTION_SECONDS = 60
TIMEOUT = 20
SCOPE = ('.', ':(exclude)evidence/**', ':(glob,exclude,icase)**/evidence/windows-sandbox/**')
STATES = ('successful', 'failed', 'pending', 'untested')
DIFF_FLAGS = ('--no-ext-diff', '--no-textconv', '--no-renames', '--ignore-submodules=all', '--numstat', '-z')


class ReportError(ValueError):
    """Fixed diagnostic codes; never echo raw Git stderr or host paths."""


def require(condition, code):
    if not condition:
        raise ReportError(code)


def _sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{40}', value) is not None


def _capture(command, environment, *, timeout=None):
    """Bound retained pipe data and time; stop and reap Git on overflow/cancellation."""
    process = None
    threads, errors, buffers = [], [], [bytearray(), bytearray()]
    overflow = threading.Event()
    primary = None
    def drain(index, stream, limit):
        try:
            while chunk := stream.read(8192):
                remaining = max(0, limit - len(buffers[index]))
                buffers[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
        except BaseException as error:
            errors.append(error)
    try:
        process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   **({'start_new_session': True} if os.name == 'posix' else {}))
        for index, stream in enumerate((process.stdout, process.stderr)):
            thread = threading.Thread(target=drain, args=(index, stream, MAX_OUTPUT if index == 0 else 65536), daemon=True)
            threads.append(thread)
            thread.start()
        deadline = clock.monotonic() + (TIMEOUT if timeout is None else timeout)
        while process.poll() is None or any(thread.is_alive() for thread in threads):
            require(not overflow.is_set(), 'git_output_bound')
            if errors:
                raise next((error for error in errors if not isinstance(error, Exception)), errors[0])
            require(clock.monotonic() < deadline, 'git_timeout')
            try:
                process.wait(timeout=0.02)
            except subprocess.TimeoutExpired:
                pass
            for thread in threads:
                thread.join(timeout=0.005)
        require(not overflow.is_set(), 'git_output_bound')
        if errors:
            raise next((error for error in errors if not isinstance(error, Exception)), errors[0])
        require(process.returncode == 0, 'git_command_failed')
        return bytes(buffers[0])
    except BaseException as error:
        primary = error
        raise
    finally:
        cleanup = []
        if process is not None:
            try:
                if os.name == 'posix':
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
            except BaseException as error:
                cleanup.append(error)
            for thread in threads:
                try:
                    if thread.ident is None:
                        continue
                    thread.join(timeout=2)
                    if thread.is_alive():
                        cleanup.append(ReportError('git_reader_cleanup_failed'))
                except BaseException as error:
                    cleanup.append(error)
            for stream in (process.stdout, process.stderr):
                if stream is not None and not any(thread.is_alive() for thread in threads):
                    try:
                        stream.close()
                    except BaseException as error:
                        cleanup.append(error)
        cleanup.extend(errors)
        if cleanup:
            controls = [error for error in cleanup if not isinstance(error, Exception)]
            if controls and (primary is None or isinstance(primary, Exception)):
                raise controls[0]
            if primary is None:
                raise ReportError('git_cleanup_failed') from cleanup[0]
            primary.add_note('Git cleanup was not fully verified.')


class Git:
    def __init__(self, repo, executable):
        try:
            self.repo = checked_path(preflight._lexical_path(os.fspath(repo), Path.cwd()), directory=True)
        except (OSError, ValueError, TypeError) as error:
            raise ReportError('unsafe_repository_path') from error
        try:
            self.executable = validation._validated_git(self.repo, executable)
        except (OSError, ValueError, TypeError) as error:
            raise ReportError('unsafe_git_executable') from error
        self.calls = 0
        self.captured_bytes = 0
        self.deadline = clock.monotonic() + MAX_COLLECTION_SECONDS

    def run(self, *args):
        require(args and args[0] in {'rev-parse', 'branch', 'config', 'ls-files', 'status', 'log', 'diff', 'diff-tree'},
                'unsupported_git_operation')
        self.calls += 1
        require(self.calls <= 2 * MAX_COMMITS + 64, 'git_command_count_bound')
        checked_path(self.repo, directory=True)
        checked_path(self.executable)
        environment = validation._git_environment()
        environment.update(GIT_OPTIONAL_LOCKS='0', LC_ALL='C', TZ='UTC')
        remaining = self.deadline - clock.monotonic()
        require(remaining > 0, 'collection_timeout')
        result = _capture([str(self.executable), '--no-optional-locks', '--no-pager',
                         '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + str(self.executable),
                         '-c', 'core.attributesFile=' + os.devnull, '-c', 'protocol.allow=never',
                         '-c', 'core.untrackedCache=false', '-c', 'status.renames=false',
                         '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', '-C', str(self.repo), *args],
                         environment, timeout=min(TIMEOUT, remaining))
        self.captured_bytes += len(result)
        require(self.captured_bytes <= MAX_CAPTURE_BYTES, 'aggregate_capture_bound')
        require(clock.monotonic() <= self.deadline, 'collection_timeout')
        return result


def _text(data):
    try:
        return data.decode('utf-8')
    except UnicodeError as error:
        raise ReportError('unsupported_git_encoding') from error


def _path(data):
    # Names are recorded as data only: never open them or interpolate in commands.
    value = data.decode('utf-8', errors='surrogateescape')
    parts = value.replace('\\', '/').casefold().split('/')
    require(bool(value) and not value.startswith('/') and '..' not in parts
            and not any(a == 'evidence' and b == 'windows-sandbox' for a, b in zip(parts, parts[1:]))
            and parts[0] != 'evidence', 'unsafe_or_excluded_git_path')
    return value


def _nul(data):
    require(not data or data.endswith(b'\0'), 'malformed_git_records')
    return data[:-1].split(b'\0') if data else []


def _parse_numstat(data):
    result = []
    for record in _nul(data):
        parts = record.split(b'\t', 2)
        require(len(parts) == 3, 'malformed_numstat')
        added, deleted, path = parts
        binary = added == deleted == b'-'
        require(binary or all(re.fullmatch(rb'0|[1-9][0-9]{0,11}', value) for value in (added, deleted)),
                'malformed_numstat')
        result.append({'path': _path(path), 'added': None if binary else int(added),
                       'deleted': None if binary else int(deleted), 'binary': binary})
        require(len(result) <= MAX_FILES, 'file_count_bound')
    require(len({row['path'] for row in result}) == len(result), 'duplicate_git_path')
    return sorted(result, key=lambda row: row['path'])


def _parse_status(data):
    result = []
    rows = iter(_nul(data))
    for row in rows:
        require(len(row) > 3 and row[2:3] == b' ', 'malformed_status')
        code = row[:2].decode('ascii')
        require(code == '??' or all(c in ' MADRCTU' for c in code) and code != '  ', 'malformed_status')
        item = {'index': code[0], 'worktree': code[1], 'path': _path(row[3:])}
        if 'R' in code or 'C' in code:
            previous = next(rows, None)
            require(previous is not None, 'malformed_status')
            item['original_path'] = _path(previous)
        result.append(item)
        require(len(result) <= MAX_FILES, 'file_count_bound')
    require(len({row['path'] for row in result}) == len(result), 'duplicate_git_path')
    return sorted(result, key=lambda row: row['path'])


def _totals(files):
    return {'files': len(files), 'text_files': sum(not row['binary'] and not row.get('unmerged', False) for row in files),
            'binary_files': sum(row['binary'] is True for row in files),
            'unmerged_files': sum(row.get('unmerged', False) for row in files),
            'added': sum(row['added'] for row in files if row['added'] is not None),
            'deleted': sum(row['deleted'] for row in files if row['deleted'] is not None)}


def _working_numstat(data, unmerged):
    if not unmerged:
        return _parse_numstat(data)
    ordinary, conflicted = [], set()
    records = _nul(data)
    require(len(records) <= 2 * MAX_FILES, 'file_count_bound')
    for raw in records:
        row = _parse_numstat(raw + b'\0')[0]
        if row['path'] in unmerged:
            conflicted.add(row['path'])
        else:
            ordinary.append(raw)
    rows = _parse_numstat(b'\0'.join(ordinary) + (b'\0' if ordinary else b''))
    rows.extend({'path': path, 'added': None, 'deleted': None, 'binary': None, 'unmerged': True}
                for path in conflicted)
    require(len(rows) <= MAX_FILES, 'file_count_bound')
    return sorted(rows, key=lambda row: row['path'])


def _snapshot(git):
    head = _text(git.run('rev-parse', '--verify', 'HEAD')).strip()
    require(_sha(head), 'invalid_revision')
    branch = _text(git.run('branch', '--show-current')).strip() or None
    status = git.run('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=all', '--', *SCOPE)
    staged = git.run('diff', '--cached', *DIFF_FLAGS, head, '--', *SCOPE)
    unstaged = git.run('diff', *DIFF_FLAGS, '--', *SCOPE)
    return head, branch, status, staged, unstaged


def _calendar(day):
    try:
        zone = ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError as error:
        raise ReportError('timezone_data_unavailable') from error
    if day is None:
        selected = datetime.now(zone).date()
    else:
        require(type(day) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', day), 'invalid_date')
        try:
            selected = date.fromisoformat(day)
        except ValueError as error:
            raise ReportError('invalid_date') from error
    try:
        start = datetime.combine(selected, time.min, zone)
        end = datetime.combine(selected + timedelta(days=1), time.min, zone)
    except (OverflowError, ValueError) as error:
        raise ReportError('invalid_date') from error
    return selected.isoformat(), zone, start, end


def _commits(git, head, zone, start, end):
    data = _nul(git.run('log', '-z', '--max-count=' + str(MAX_COMMITS + 1), '--no-decorate', '--no-notes',
                        '--no-show-signature', '--no-use-mailmap', '--encoding=UTF-8',
                        '--format=%H%x00%P%x00%ct%x00%an%x00%s', head, '--'))
    require(len(data) % 5 == 0, 'malformed_history')
    require(len(data) // 5 <= MAX_COMMITS, 'history_count_bound')
    result = []
    changes = 0
    seen = set()
    for index in range(0, len(data), 5):
        sha, parents, epoch, author, subject = map(_text, data[index:index + 5])
        parents = parents.split()
        require(_sha(sha) and sha not in seen and all(_sha(p) for p in parents)
                and re.fullmatch(r'-?[0-9]{1,12}', epoch), 'malformed_history')
        seen.add(sha)
        try:
            committed = datetime.fromtimestamp(int(epoch), timezone.utc).astimezone(zone)
        except (OverflowError, OSError, ValueError) as error:
            raise ReportError('invalid_commit_time') from error
        if not start <= committed < end:
            continue
        if parents:
            raw = git.run('diff', *DIFF_FLAGS, parents[0], sha, '--', *SCOPE)
        else:
            raw = git.run('diff-tree', '--root', '-r', '--no-commit-id', *DIFF_FLAGS, sha, '--', *SCOPE)
        files = _parse_numstat(raw)
        changes += len(files)
        require(changes <= MAX_CHANGES, 'aggregate_change_bound')
        result.append({'sha': sha, 'parents': parents, 'committed_at': committed.isoformat(),
                       'author': author, 'subject': subject, 'files': files, 'totals': _totals(files),
                       'test_evidence': 'not_assessed'})
    return sorted(result, key=lambda row: (datetime.fromisoformat(row['committed_at']).timestamp(), row['sha']))


def _observations(path, selected, head):
    result = {'verification': 'not_supplied', 'sha256': None, 'items': [],
              'counts': {state: 0 for state in STATES}}
    if path is None:
        return result, None
    path = checked_path(preflight._lexical_path(os.fspath(path), Path.cwd()))
    raw = read_bytes(path, 1024**2)
    try:
        value = preflight._json(raw.decode('utf-8'))
    except (ValueError, RecursionError, UnicodeError) as error:
        raise ReportError('invalid_observations') from error
    require(type(value) is dict and set(value) == {'schema_version', 'date', 'timezone', 'revision', 'items'}
            and type(value['schema_version']) is int and value['schema_version'] == 1
            and value['date'] == selected and value['timezone'] == TIMEZONE and value['revision'] == head
            and type(value['items']) is list and len(value['items']) <= 128, 'invalid_observations')
    ids = set()
    for item in value['items']:
        require(type(item) is dict and {'id', 'status', 'summary'} <= set(item)
                and set(item) <= {'id', 'status', 'summary', 'command', 'tests'}, 'invalid_observations')
        require(type(item['id']) is str and re.fullmatch('[a-z0-9_-]{1,48}', item['id'])
                and item['id'] not in ids and type(item['status']) is str and item['status'] in STATES,
                'invalid_observations')
        ids.add(item['id'])
        for key, maximum in (('summary', 2048), ('command', 4096)):
            if key in item:
                require(type(item[key]) is str and 0 < len(item[key]) <= maximum
                        and all(ord(char) >= 32 and ord(char) != 127 for char in item[key]), 'invalid_observations')
        if 'tests' in item:
            counts = item['tests']
            require(type(counts) is dict and set(counts) == {'passed', 'failed', 'errors', 'skipped', 'deselected'}
                    and all(type(count) is int and 0 <= count <= 10000000 for count in counts.values()),
                    'invalid_test_counts')
            require(item['status'] in {'successful', 'failed'}, 'unrun_test_counts')
            if item['status'] == 'successful':
                require(counts['passed'] > 0 and not counts['failed'] and not counts['errors'], 'contradictory_test_status')
            else:
                require(counts['failed'] + counts['errors'] > 0, 'contradictory_test_status')
        result['items'].append(item)
        result['counts'][item['status']] += 1
    result['items'].sort(key=lambda row: row['id'])
    result['verification'] = 'supplied_not_independently_verified'
    result['sha256'] = hashlib.sha256(raw).hexdigest()
    return result, (path, raw)


def collect_report(repo, *, day=None, git_executable, observations=None, expected_head=None):
    selected, zone, start, end = _calendar(day)
    git = Git(repo, git_executable)
    top = preflight._lexical_path(_text(git.run('rev-parse', '--show-toplevel')).strip(), Path.cwd())
    require(top == git.repo, 'repository_root_mismatch')
    config = _nul(git.run('config', '--no-includes', '--null', '--name-only', '--list'))
    require(not any(name.lower().startswith((b'filter.', b'include.', b'includeif.')) for name in config),
            'unsupported_git_configuration')
    entries = _nul(git.run('ls-files', '-v', '-z', '--', *SCOPE))
    require(len(entries) <= MAX_FILES, 'file_count_bound')
    require(all(row[:2] in {b'H ', b'M ', b'R ', b'C ', b'K '} for row in entries), 'hidden_index_flags')
    before = _snapshot(git)
    head, branch, status, staged, unstaged = before
    if expected_head is not None:
        require(_sha(expected_head) and head == expected_head, 'revision_mismatch')
    commits = _commits(git, head, zone, start, end)
    observations, observation_input = _observations(observations, selected, head)
    status = _parse_status(status)
    unmerged = {row['path'] for row in status if row['index'] + row['worktree']
                in {'DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU'}}
    staged, unstaged = _working_numstat(staged, unmerged), _working_numstat(unstaged, unmerged)
    if observation_input is not None:
        require(read_bytes(observation_input[0], 1024**2) == observation_input[1], 'observations_changed')
    require(_snapshot(git) == before, 'repository_changed')
    require(_nul(git.run('ls-files', '-v', '-z', '--', *SCOPE)) == entries, 'index_changed')
    files = [file for commit in commits for file in commit['files']]
    return {'schema_version': 1, 'status': 'collected', 'date': selected, 'timezone': TIMEZONE,
            'day_start': start.isoformat(), 'day_end_exclusive': end.isoformat(),
            'source': {'head': head, 'branch': branch, 'detached': branch is None,
                       'history_scope': 'reachable_from_head', 'commit_date_basis': 'committer',
                       'merge_statistics': 'first_parent', 'renames': 'separate_delete_add',
                       'evidence_paths': 'excluded', 'consistency': 'stable_observed_git_metadata_not_atomic'},
            'commits': commits,
            'totals': {'commits': len(commits), 'file_changes': len(files),
                       'unique_files': len({row['path'] for row in files}),
                       'added': _totals(files)['added'], 'deleted': _totals(files)['deleted'],
                       'binary_file_changes': _totals(files)['binary_files']},
            'working_tree': {'clean_scoped': not status, 'status': status,
                             'staged': {'files': staged, 'totals': _totals(staged)},
                             'unstaged': {'files': unstaged, 'totals': _totals(unstaged)},
                             'untracked': [row['path'] for row in status if row['index'] == row['worktree'] == '?'],
                             'unmerged': sorted(unmerged),
                             'submodule_worktrees': 'not_assessed'},
            'observations': observations,
            'validation': {'tests': 'not_assessed', 'ci': 'not_assessed', 'github_contributions': 'not_assessed',
                           'native_windows': 'pending'}, 'read_only': True}


def summary(report):
    return ('Daily development report: ' + report['date'] + ' (' + TIMEZONE + ')\n'
            + 'Recorded commits: ' + str(report['totals']['commits'])
            + '; scoped worktree: ' + ('clean' if report['working_tree']['clean_scoped'] else 'modified')
            + '\nTests/CI/contribution eligibility: NOT ASSESSED; native Windows: PENDING.\n'
            + 'Supplied validation declarations are not independently verified.\n')


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ReportError('invalid_arguments')
    parser = Parser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--git-executable', required=True)
    parser.add_argument('--date')
    parser.add_argument('--expected-head')
    parser.add_argument('--observations')
    try:
        args = parser.parse_args(argv)
        report = collect_report(args.repo, day=args.date, git_executable=args.git_executable,
                                observations=args.observations, expected_head=args.expected_head)
    except Exception as error:
        code = str(error) if type(error) is ReportError and re.fullmatch('[a-z_]{1,80}', str(error)) else 'report_blocked'
        print(json.dumps({'schema_version': 1, 'status': 'blocked', 'code': code,
                          'read_only': True, 'tests': 'not_assessed'}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    print(summary(report), file=sys.stderr, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
