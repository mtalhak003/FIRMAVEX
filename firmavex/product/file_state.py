"""Comparable path/handle identities, including precise Windows metadata.

Windows Python stat/fstat fields differ across versions. Querying both through
native file information avoids comparing CRT timestamps with Win32 timestamps.
Observable consistency is not an atomic snapshot or an adversarial-race guarantee.
"""
import ctypes
import os
from pathlib import Path
import sys


def _stat_state(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _windows_state(handle):
    DWORD=ctypes.c_uint32
    class FileTime(ctypes.Structure):
        _fields_=[('low',DWORD),('high',DWORD)]
    class Information(ctypes.Structure):
        _fields_=[('attributes',DWORD),('creation',FileTime),('access',FileTime),('write',FileTime),
                  ('volume',DWORD),('size_high',DWORD),('size_low',DWORD),('links',DWORD),
                  ('index_high',DWORD),('index_low',DWORD)]
    class Basic(ctypes.Structure):
        _fields_=[('creation',ctypes.c_int64),('access',ctypes.c_int64),('write',ctypes.c_int64),
                  ('change',ctypes.c_int64),('attributes',DWORD)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetFileInformationByHandle.argtypes=[ctypes.c_void_p,ctypes.POINTER(Information)]
    api.GetFileInformationByHandle.restype=ctypes.c_int32
    api.GetFileInformationByHandleEx.argtypes=[ctypes.c_void_p,ctypes.c_int32,ctypes.c_void_p,DWORD]
    api.GetFileInformationByHandleEx.restype=ctypes.c_int32
    info,basic=Information(),Basic()
    if not api.GetFileInformationByHandle(handle,ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not api.GetFileInformationByHandleEx(handle,0,ctypes.byref(basic),ctypes.sizeof(basic)):
        raise ctypes.WinError(ctypes.get_last_error())
    return info.volume,(info.index_high<<32)|info.index_low,(info.size_high<<32)|info.size_low,basic.write,basic.change


def path_state(path, stat=None):
    if sys.platform!='win32':
        return _stat_state(stat if stat is not None else Path(path).stat())
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,
                             ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    api.CreateFileW.restype=ctypes.c_void_p
    api.CloseHandle.argtypes=[ctypes.c_void_p];api.CloseHandle.restype=ctypes.c_int32
    handle=api.CreateFileW(str(Path(path)),0x80,7,None,3,0,None)
    if handle is None or handle==ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    primary=None
    try:
        return _windows_state(handle)
    except BaseException as exc:
        primary=exc
        raise
    finally:
        if not api.CloseHandle(handle):
            error=ctypes.WinError(ctypes.get_last_error())
            if primary is None: raise error
            primary.add_note('File-state handle cleanup failed: '+str(error))


def handle_state(fd, stat=None):
    if sys.platform!='win32':
        return _stat_state(stat if stat is not None else os.fstat(fd))
    import msvcrt
    return _windows_state(msvcrt.get_osfhandle(fd))
