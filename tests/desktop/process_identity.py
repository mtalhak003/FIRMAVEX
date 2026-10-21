"""Strict native cleanup assertions using original Windows process identity."""
import json
import os
import pytest


def assert_process_not_running(child):
    pid = child['pid']
    if os.name != 'nt':
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        return
    from firmavex.product.windows_process import kernel, snapshot, classify
    import ctypes
    original = child['windows_identity']
    assert original and original['terminated'], child
    library = kernel()
    handle = library.OpenProcess(0x00100000 | 0x1000, False, pid)
    if not handle:
        assert ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: absent PID
        current = None
    else:
        try:
            current = snapshot(handle, library)
        finally:
            assert library.CloseHandle(handle)
    outcome = classify(original, current)
    # Fixed fields only: no paths, command lines, environment or process inventory.
    print('Windows process identity: ' + json.dumps(
        {'pid': pid, 'original': original, 'current': current, 'outcome': outcome}, sort_keys=True))
    assert outcome != 'original_running'
