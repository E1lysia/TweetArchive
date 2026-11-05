"""Run one download command in a process tree owned by this wrapper.

Usage: ``python -u task_runner.py -- <program> <arguments...>``.

The GUI should terminate this wrapper, rather than an arbitrary PowerShell or
Python process. On Windows, its private job also terminates all descendants.
The wrapper never requests permission to break away from a parent job. If a
parent job prevents nesting, the command is not started.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import threading


RUNNER_ERROR = 125
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
HANDLE_FLAG_INHERIT = 0x00000001

# Keep this handle alive until the OS tears down the wrapper. Closing it while
# this process is still running would terminate this process too, since it is
# itself a member of the job. Kernel handles are not closed by Python GC.
_job_handle: int | None = None
_parent_handle: int | None = None


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


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
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


def _join_private_job() -> int:
    """Join a kill-on-close job; raise OSError without launching any child."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetHandleInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
    ]
    kernel.SetHandleInformation.restype = wintypes.BOOL
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    # A null SECURITY_ATTRIBUTES already means noninheritable. Explicitly clear
    # inheritance too: no downloader may keep the job alive after our exit.
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    assigned = False
    try:
        if not kernel.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(
            handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
        assigned = True
        return handle
    finally:
        # Before assignment it is safe to close a failed/unused job. After
        # assignment the process must retain the sole handle until it exits.
        if not assigned:
            kernel.CloseHandle(handle)


def _watch_parent() -> int:
    """Keep an exact parent-process handle and exit if that process dies."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.SetHandleInformation.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
    ]
    kernel.SetHandleInformation.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    parent_pid = os.getppid()
    if parent_pid <= 0:
        raise OSError("Parent process is unavailable")
    # QUERY_LIMITED_INFORMATION permits checking creation time too. A parent
    # that died before startup may have had its PID reused by another process.
    handle = kernel.OpenProcess(0x00101000, False, parent_pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not kernel.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        def creation_time(process_handle):
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(
                process_handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(kernel_time), ctypes.byref(user_time),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return (created.dwHighDateTime << 32) | created.dwLowDateTime

        if creation_time(handle) > creation_time(kernel.GetCurrentProcess()):
            raise OSError("Parent process identity is unavailable")
        # WAIT_TIMEOUT means that the parent is still alive. Do not launch a
        # downloader if the GUI already exited or this handle cannot be waited.
        if kernel.WaitForSingleObject(handle, 0) != 258:
            raise OSError("Parent process has exited")

        def parent_exited():
            kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            # Both a signaled handle and a failed wait must fail closed. The OS
            # releases our private job handle and kills the complete task tree.
            os._exit(RUNNER_ERROR)

        threading.Thread(
            target=parent_exited, name="task-parent-watch", daemon=True,
        ).start()
        return handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def main(argv: list[str] | None = None) -> int:
    global _job_handle, _parent_handle
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[0] != "--":
        print("Usage: task_runner.py -- <program> <arguments...>", file=sys.stderr)
        return RUNNER_ERROR
    if os.name != "nt":
        print("Task runner requires Windows process protection.", file=sys.stderr)
        return RUNNER_ERROR
    try:
        _job_handle = _join_private_job()
        _parent_handle = _watch_parent()
    except (OSError, RuntimeError) as exc:
        # Do not log the command, environment, paths, or possible credentials.
        error_code = getattr(exc, "winerror", None) or getattr(exc, "errno", None) or 0
        print(
            f"Task not started: process protection failed (Windows error {error_code}).",
            file=sys.stderr, flush=True,
        )
        return RUNNER_ERROR
    try:
        child = subprocess.Popen(
            args[1:], stdin=subprocess.DEVNULL, stdout=None, stderr=None,
            close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return child.wait()
    except OSError as exc:
        error_code = getattr(exc, "winerror", None) or getattr(exc, "errno", None) or 0
        print(
            f"Task could not start (Windows error {error_code}).",
            file=sys.stderr, flush=True,
        )
        return RUNNER_ERROR
    except KeyboardInterrupt:
        # Exiting releases our only job handle, terminating the whole task tree.
        return 130


if __name__ == "__main__":
    sys.exit(main())
