"""Cross-platform process-handle and process-tree cleanup primitives."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess


class ProcessCleanupError(RuntimeError):
    """The runner could not prove that subprocess ownership was released."""


def close_windows_job(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    job = getattr(proc, "_deepr_windows_kill_job", None)
    if job is None:
        return None
    from deepr.backends.plan_quota.windows_job import retain_failed_job

    try:
        closed = bool(job.close())
    except Exception as error:
        if getattr(job, "_handle", None) is not None:
            retain_failed_job(job)
        return ProcessCleanupError(f"Windows Job Object close failed ({type(error).__name__})")
    if not closed:
        if getattr(job, "_handle", None) is not None:
            retain_failed_job(job)
        return ProcessCleanupError("Windows Job Object close failed")
    proc._deepr_windows_kill_job = None  # type: ignore[attr-defined]
    return None


def terminate_windows_job(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    job = getattr(proc, "_deepr_windows_kill_job", None)
    if job is None:
        return None
    termination_error: ProcessCleanupError | None = None
    try:
        if not bool(job.terminate()):
            termination_error = ProcessCleanupError("Windows Job Object termination failed")
    except Exception as error:
        termination_error = ProcessCleanupError(f"Windows Job Object termination failed ({type(error).__name__})")
    close_error = close_windows_job(proc)
    return termination_error or close_error


def close_process_transport(proc: asyncio.subprocess.Process) -> None:
    """Close asyncio's private owner because Process has no public close API."""
    transport = getattr(proc, "_transport", None)
    close = getattr(transport, "close", None)
    if callable(close):
        with contextlib.suppress(Exception):
            close()


async def kill_process_tree(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        return await kill_windows_process_tree(proc)
    return kill_posix_process_tree(proc)


async def kill_windows_process_tree(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    cleanup_error = terminate_windows_job(proc)
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
    return cleanup_error


def kill_posix_process_tree(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    if getattr(proc, "_deepr_posix_supervisor", False):
        if proc.returncode is not None:
            return None
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return None
        except Exception as error:
            return ProcessCleanupError(f"Linux supervisor termination failed ({type(error).__name__})")
        return None

    cleanup_error = None
    try:
        kill_process_group = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", None)
        if callable(kill_process_group) and sigkill is not None:
            kill_process_group(proc.pid, sigkill)
    except ProcessLookupError:
        cleanup_error = None
    except Exception as error:
        cleanup_error = ProcessCleanupError(f"POSIX process-group termination failed ({type(error).__name__})")
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
    return cleanup_error
