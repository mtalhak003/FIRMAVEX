"""Bounded process identity and termination evidence from an owned handle."""
import ctypes


def kernel():
    library = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = ctypes.c_void_p
    dword = ctypes.c_uint32
    library.GetProcessTimes.argtypes = [handle] + [ctypes.POINTER(ctypes.c_uint64)] * 4
    library.GetProcessTimes.restype = ctypes.c_int32
    library.GetExitCodeProcess.argtypes = [handle, ctypes.POINTER(dword)]
    library.GetExitCodeProcess.restype = ctypes.c_int32
    library.WaitForSingleObject.argtypes = [handle, dword]
    library.WaitForSingleObject.restype = dword
    library.OpenProcess.argtypes = [dword, ctypes.c_int32, dword]
    library.OpenProcess.restype = handle
    library.CloseHandle.argtypes = [handle]
    library.CloseHandle.restype = ctypes.c_int32
    return library


def snapshot(handle, library=None):
    """A zero-time wait distinguishes termination even when the exit code is 259."""
    library = kernel() if library is None else library
    times = [ctypes.c_uint64() for _ in range(4)]
    if not library.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise OSError('GetProcessTimes failed')
    wait = library.WaitForSingleObject(handle, 0)
    if wait not in (0, 258):  # WAIT_OBJECT_0 / WAIT_TIMEOUT
        raise OSError(f'Process wait failed: {wait}')
    code = ctypes.c_uint32()
    if not library.GetExitCodeProcess(handle, ctypes.byref(code)):
        raise OSError('GetExitCodeProcess failed')
    return {'creation_time': times[0].value, 'wait_status': wait,
            'terminated': wait == 0, 'exit_code': code.value}


def classify(original, current):
    """Never let a subsequent PID lookup override an original-handle leak."""
    if not original['terminated']:
        return 'original_running'
    if current is None:
        return 'original_terminated_pid_absent'
    if current['creation_time'] != original['creation_time']:
        return 'pid_reused'
    if not current['terminated']:
        raise AssertionError('Same process identity became running after termination')
    return 'original_terminated'
