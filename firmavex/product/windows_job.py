"""Windows-owned process trees, independent of firmware platform qualification.

An assigned worker cannot dispatch a product command before job ownership is
established. Child processes inherit the job; closing its sole owned handle
terminates the entire tree. This module does not establish ARM tool support.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

from .errors import ProductError


# Explicit Windows-width integers also make synthetic layout tests meaningful
# on LP64 hosts, where ctypes.c_ulong has a different width from Windows DWORD.
DWORD = ctypes.c_uint32
BOOL = ctypes.c_int32
HANDLE = ctypes.c_void_p
SIZE_T = ctypes.c_size_t
ULONG_PTR = ctypes.c_size_t
LARGE_INTEGER = ctypes.c_int64
ULONGLONG = ctypes.c_uint64
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


class BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", LARGE_INTEGER),
        ("PerJobUserTimeLimit", LARGE_INTEGER),
        ("LimitFlags", DWORD),
        ("MinimumWorkingSetSize", SIZE_T),
        ("MaximumWorkingSetSize", SIZE_T),
        ("ActiveProcessLimit", DWORD),
        ("Affinity", ULONG_PTR),
        ("PriorityClass", DWORD),
        ("SchedulingClass", DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ULONGLONG),
        ("WriteOperationCount", ULONGLONG),
        ("OtherOperationCount", ULONGLONG),
        ("ReadTransferCount", ULONGLONG),
        ("WriteTransferCount", ULONGLONG),
        ("OtherTransferCount", ULONGLONG),
    ]


class ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimitInformation),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", SIZE_T),
        ("JobMemoryLimit", SIZE_T),
        ("PeakProcessMemoryUsed", SIZE_T),
        ("PeakJobMemoryUsed", SIZE_T),
    ]


class _Kernel32:
    """Only the actual Windows loader binds native process APIs."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise ProductError("unsupported_platform", "Windows process ownership requires a native Windows host.")
        library = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, ctypes.c_wchar_p], HANDLE),
            "SetInformationJobObject": ([HANDLE, ctypes.c_int32, ctypes.c_void_p, DWORD], BOOL),
            "AssignProcessToJobObject": ([HANDLE, HANDLE], BOOL),
            "TerminateJobObject": ([HANDLE, DWORD], BOOL),
            "CloseHandle": ([HANDLE], BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes = arguments
            function.restype = result
            setattr(self, name, function)

    @staticmethod
    def last_error() -> int:
        return ctypes.get_last_error()


class WindowsJob:
    """Own one kill-on-close job handle; injected APIs are test seams only."""

    def __init__(self, *, _api: Any | None = None) -> None:
        self._api = _Kernel32() if _api is None else _api
        self._handle: int | None = None
        handle = self._api.CreateJobObjectW(None, None)
        if not handle:
            raise self._failure("CreateJobObjectW")
        self._handle = int(handle)
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not self._api.SetInformationJobObject(
                self._handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits), ctypes.sizeof(limits),
            ):
                raise self._failure("SetInformationJobObject")
        except BaseException as original:
            try:
                self.close()
            except BaseException as cleanup:
                self._attach_cleanup(original, cleanup)
            raise

    def _failure(self, operation: str) -> ProductError:
        return ProductError(
            "process_ownership_failure", "Cannot establish or maintain the owned Windows process tree.",
            {"operation": operation, "winerror": self._api.last_error()},
        )

    @staticmethod
    def _attach_cleanup(original: BaseException, cleanup: BaseException) -> None:
        if isinstance(original, ProductError):
            original.details["ownership_cleanup_error"] = str(cleanup)
        elif hasattr(original, "add_note"):
            original.add_note(f"Windows ownership cleanup also failed: {cleanup}")

    def assign(self, process_handle: int) -> None:
        if self._handle is None:
            raise ProductError("process_ownership_failure", "Cannot assign a process to a closed Windows job.")
        if isinstance(process_handle, bool) or not isinstance(process_handle, int) or process_handle <= 0:
            raise ProductError("process_ownership_failure", "A valid owned process handle is required.")
        if not self._api.AssignProcessToJobObject(self._handle, process_handle):
            raise self._failure("AssignProcessToJobObject")

    def terminate(self) -> None:
        if self._handle is not None and not self._api.TerminateJobObject(self._handle, 1):
            raise self._failure("TerminateJobObject")

    def close(self) -> None:
        if self._handle is not None:
            if not self._api.CloseHandle(self._handle):
                raise self._failure("CloseHandle")
            self._handle = None

    def __enter__(self) -> WindowsJob:
        return self

    def __exit__(self, exception_type: Any, exception: BaseException | None, traceback: Any) -> None:
        try:
            self.close()
        except BaseException as cleanup:
            if exception is None:
                raise
            self._attach_cleanup(exception, cleanup)
