"""CI-only per-test watchdog; a timeout fails the process, never skips a test.

The parent product_ci_tests launcher owns the test process tree. This plugin
must only be enabled by that launcher, not application/research execution.
"""
import faulthandler
import hashlib
import os
import sys
import threading
import time
import math
import traceback

import pytest

# Duplicate before pytest installs FD capture; watchdog diagnostics must survive
# a timeout inside capfd as well as ordinary global test capture.
_DIAGNOSTICS = os.fdopen(os.dup(sys.__stderr__.fileno()), 'w', encoding='utf-8', buffering=1)


def pytest_addoption(parser):
    parser.addoption('--firmavex-test-timeout', type=float, default=120,
                     help='CI per-test wall limit, including fixtures (default 120s).')


def pytest_configure(config):
    limit = config.getoption('--firmavex-test-timeout')
    if not math.isfinite(limit) or limit <= 0:
        raise pytest.UsageError('--firmavex-test-timeout must be positive and finite')


def _watch(label, limit):
    finished = threading.Event()
    def watchdog():
        if not finished.wait(limit):
            stacks = '\n'.join(f'Thread {identifier}:\n' + ''.join(traceback.format_stack(frame))
                               for identifier, frame in sys._current_frames().items())
            detail = stacks[-16000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print(f'\n::error title=CI lifecycle timeout::{label} exceeded {limit:g}s; {detail}',
                  file=_DIAGNOSTICS, flush=True)
            faulthandler.dump_traceback(file=_DIAGNOSTICS, all_threads=True)
            os._exit(124)
    thread = threading.Thread(target=watchdog, daemon=True, name='firmavex-ci-watchdog')
    thread.start()
    return finished, thread


def _stop(watch):
    watch[0].set()
    watch[1].join(timeout=1)


def pytest_sessionstart(session):
    session.config._firmavex_collection_watch = _watch(
        'test collection', session.config.getoption('--firmavex-test-timeout'))
    print('\n::notice title=FIRMAVEX pytest lifecycle::collection started', file=_DIAGNOSTICS, flush=True)


def pytest_collection_finish(session):
    _stop(session.config._firmavex_collection_watch)
    print(f'\n::notice title=FIRMAVEX pytest lifecycle::collection finished; {len(session.items)} tests',
          file=_DIAGNOSTICS, flush=True)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    _stop(session.config._firmavex_collection_watch)
    print(f'\n::notice title=FIRMAVEX pytest lifecycle::session finishing; pytest status={int(exitstatus)}',
          file=_DIAGNOSTICS, flush=True)
    # This daemon remains armed: leaked non-daemon threads can otherwise hang
    # interpreter shutdown after pytest prints an apparently passing summary.
    _watch('pytest session/interpreter shutdown', session.config.getoption('--firmavex-test-timeout'))
    yield


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    limit = item.config.getoption('--firmavex-test-timeout')
    started = time.monotonic()
    identifier = item.nodeid
    if len(identifier) > 512:
        identifier = identifier[:512] + '... [nodeid SHA256=' + hashlib.sha256(item.nodeid.encode()).hexdigest() + ']'
    node = identifier.replace('%', '%25').replace('\n', '%0A').replace('\r', '%0D')
    print(f'FIRMAVEX TEST START {node}', file=_DIAGNOSTICS, flush=True)
    watch = _watch('Per-test timeout: ' + node + ' (setup/call/teardown)', limit)
    try:
        yield
    finally:
        _stop(watch)
        print(f'FIRMAVEX TEST END {node} elapsed={time.monotonic()-started:.3f}s', file=_DIAGNOSTICS, flush=True)
