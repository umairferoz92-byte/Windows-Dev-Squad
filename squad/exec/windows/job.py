"""Windows Job Objects via ctypes (standard library only, no pywin32).

A Job Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` guarantees that every
process in the job is terminated when the last handle to the job is closed —
including when the owning executor crashes. This is the "no orphaned processes"
mechanism on Windows.

Note: assignment happens immediately after the child process is created, so a
child spawned by the executor is in the job and its descendants inherit
membership. A theoretical race remains between process creation and assignment
for grandchildren spawned in that microsecond window; closing it fully requires
CREATE_SUSPENDED + ResumeThread and is a Phase 12 hardening item.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000

PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),  # ULONG_PTR
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE

_kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
]
_kernel32.SetInformationJobObject.restype = wintypes.BOOL

_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE

_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


class JobObject:
    """A Windows Job Object that kills all member processes when closed."""

    def __init__(self) -> None:
        self._handle = _kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _kernel32.SetInformationJobObject(
            self._handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            _kernel32.CloseHandle(self._handle)
            self._handle = None
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def assign(self, pid: int) -> None:
        if not self._handle:
            raise RuntimeError("job object is closed")
        hproc = _kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not hproc:
            raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")
        try:
            ok = _kernel32.AssignProcessToJobObject(self._handle, hproc)
            if not ok:
                raise OSError(ctypes.get_last_error(), f"AssignProcessToJobObject({pid}) failed")
        finally:
            _kernel32.CloseHandle(hproc)

    def close(self) -> None:
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> JobObject:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def is_process_alive(pid: int) -> bool:
    hproc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hproc:
        return False
    _kernel32.CloseHandle(hproc)
    return True
