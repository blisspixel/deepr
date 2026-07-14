"""Windows process ownership for plan-quota command trees.

Windows process groups do not provide a reliable group-kill primitive after the
group leader exits. A kill-on-close Job Object does, but the process must enter
the job before it can create descendants. The shared runner therefore creates
the process suspended, calls :func:`attach_kill_job_and_resume`, and retains the
returned job until every output pipe has reached a terminal state.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import threading
from ctypes import wintypes
from dataclasses import dataclass

if os.name != "nt":
    raise RuntimeError("Windows Job Objects are only available on Windows")


CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_TH32CS_SNAPTHREAD = 0x00000004
_THREAD_SUSPEND_RESUME = 0x0002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_RESUME_FAILED = 0xFFFFFFFF
_CLOSE_ATTEMPTS = 3
_TERMINATE_ATTEMPTS = 3
_RETAINED_KILL_JOBS: dict[int, WindowsKillJob] = {}
_RETAINED_JOBS_LOCK = threading.Lock()


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.SetInformationJobObject.argtypes = (
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
)
_kernel32.SetInformationJobObject.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
_kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
_kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Thread32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32))
_kernel32.Thread32First.restype = wintypes.BOOL
_kernel32.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32))
_kernel32.Thread32Next.restype = wintypes.BOOL
_kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenThread.restype = wintypes.HANDLE
_kernel32.ResumeThread.argtypes = (wintypes.HANDLE,)
_kernel32.ResumeThread.restype = wintypes.DWORD
_kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
_kernel32.TerminateJobObject.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL


class WindowsProcessOwnershipError(OSError):
    """A suspended process could not be placed under kill-tree ownership."""


@dataclass
class WindowsKillJob:
    """Owned Job Object handle whose closure terminates every member process."""

    _handle: int | None

    def terminate(self) -> bool:
        """Terminate every process still owned by this job."""
        handle = self._handle
        if handle is None:
            return True
        return any(_terminate_job(handle) for _attempt in range(_TERMINATE_ATTEMPTS))

    def close(self) -> bool:
        """Close the handle with bounded retries, retaining failed ownership."""
        handle = self._handle
        if handle is None:
            return True
        for _attempt in range(_CLOSE_ATTEMPTS):
            if _close_handle(handle):
                self._handle = None
                return True
        return False


def _terminate_job(handle: int) -> bool:
    return bool(_kernel32.TerminateJobObject(handle, 1))


def _close_handle(handle: int) -> bool:
    return bool(_kernel32.CloseHandle(handle))


def retain_failed_job(job: WindowsKillJob) -> None:
    """Keep ownership of a native handle that Windows refused to close."""
    if job._handle is not None:
        with _RETAINED_JOBS_LOCK:
            _RETAINED_KILL_JOBS[id(job)] = job


def retry_retained_jobs() -> None:
    """Retry retained termination and closure during later plan launches."""
    with _RETAINED_JOBS_LOCK:
        for key, job in tuple(_RETAINED_KILL_JOBS.items()):
            job.terminate()
            if job.close():
                _RETAINED_KILL_JOBS.pop(key, None)
        if _RETAINED_KILL_JOBS:
            raise WindowsProcessOwnershipError(0, "prior Windows Job Object cleanup remains unresolved")


def attach_kill_job_and_resume(pid: int) -> WindowsKillJob:
    """Assign one suspended process to a kill-on-close job, then resume it."""
    retry_retained_jobs()
    job_handle = _create_kill_job()
    try:
        process_handle = _open_process(pid)
        try:
            _require(
                _kernel32.AssignProcessToJobObject(job_handle, process_handle),
                "AssignProcessToJobObject",
            )
        finally:
            _kernel32.CloseHandle(process_handle)
        thread_ids = _thread_ids(pid)
        if not thread_ids:
            raise _ownership_error("Thread32First/Thread32Next")
        for thread_id in thread_ids:
            _resume_thread(thread_id)
        return WindowsKillJob(int(job_handle))
    except BaseException:
        job = WindowsKillJob(int(job_handle))
        _rollback_job(job)
        raise


def _create_kill_job() -> int:
    job_handle = _kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise _ownership_error("CreateJobObjectW")
    information = _ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    try:
        _require(
            _kernel32.SetInformationJobObject(
                job_handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(information),
                ctypes.sizeof(information),
            ),
            "SetInformationJobObject",
        )
    except BaseException:
        job = WindowsKillJob(int(job_handle))
        _rollback_job(job)
        raise
    return int(job_handle)


def _open_process(pid: int) -> int:
    process_handle = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not process_handle:
        raise _ownership_error("OpenProcess")
    return int(process_handle)


def _rollback_job(job: WindowsKillJob) -> None:
    """Preserve a primary setup failure while retaining uncertain ownership."""
    with contextlib.suppress(BaseException):
        job.terminate()
    with contextlib.suppress(BaseException):
        job.close()
    if job._handle is not None:
        retain_failed_job(job)


def _thread_ids(pid: int) -> list[int]:
    snapshot = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
    if not snapshot or int(snapshot) == _INVALID_HANDLE_VALUE:
        raise _ownership_error("CreateToolhelp32Snapshot")
    try:
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        thread_ids: list[int] = []
        found = bool(_kernel32.Thread32First(snapshot, ctypes.byref(entry)))
        while found:
            if entry.th32OwnerProcessID == pid:
                thread_ids.append(int(entry.th32ThreadID))
            found = bool(_kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
        return thread_ids
    finally:
        _kernel32.CloseHandle(snapshot)


def _resume_thread(thread_id: int) -> None:
    thread_handle = _kernel32.OpenThread(_THREAD_SUSPEND_RESUME, False, thread_id)
    if not thread_handle:
        raise _ownership_error("OpenThread")
    try:
        resumed = int(_kernel32.ResumeThread(thread_handle))
        if resumed == _RESUME_FAILED:
            raise _ownership_error("ResumeThread")
    finally:
        _kernel32.CloseHandle(thread_handle)


def _require(result: object, operation: str) -> None:
    if not result:
        raise _ownership_error(operation)


def _ownership_error(operation: str) -> WindowsProcessOwnershipError:
    error_code = ctypes.get_last_error()
    return WindowsProcessOwnershipError(error_code, f"{operation} failed")
