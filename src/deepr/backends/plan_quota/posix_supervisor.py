"""Linux child-subreaper wrapper for plan-quota CLI ownership.

A process group cannot contain a descendant that deliberately creates a new
session. This wrapper stays above the vendor process as a Linux child subreaper,
so orphaned descendants are adopted and terminated before the wrapper exits.
It forwards standard streams directly and never interprets or buffers payloads.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

_PR_SET_CHILD_SUBREAPER = 36
_CLEANUP_DEADLINE_S = 0.75
_EMPTY_OBSERVATIONS_REQUIRED = 2
_MAX_DESCENDANTS_PER_PASS = 4096
_LINUX_SIGKILL = 9
_POSIX_WNOHANG = 1
LAUNCH_ERROR_STATUS = "launch_error"
CLEANUP_ERROR_STATUS = "cleanup_error"
TERMINATED_STATUS = "terminated"
VENDOR_EXIT_STATUS = "vendor_exit"
RUNTIME_ERROR_STATUS = "runtime_error"


class _TerminationRequested(BaseException):
    def __init__(self, signum: int) -> None:
        self.signum = signum


class _ChildEnumerationError(RuntimeError):
    """The supervisor could not prove which adopted children remain."""


def _request_termination(signum: int, _frame: object) -> None:
    _block_termination_signals()
    raise _TerminationRequested(signum)


def _block_termination_signals() -> None:
    """Atomically prevent a second termination from escaping cleanup."""
    block_signals = getattr(signal, "pthread_sigmask", None)
    sig_block = getattr(signal, "SIG_BLOCK", None)
    if callable(block_signals) and isinstance(sig_block, int):
        block_signals(sig_block, {signal.SIGTERM, signal.SIGINT})
        return
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _become_subreaper() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
    prctl.restype = ctypes.c_int
    if prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, "PR_SET_CHILD_SUBREAPER failed")


def _direct_child_pids(pid: int | None = None) -> tuple[int, ...]:
    resolved_pid = os.getpid() if pid is None else pid
    children_path = Path(f"/proc/{resolved_pid}/task/{resolved_pid}/children")
    try:
        text = children_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        if pid is not None:
            return ()
        raise _ChildEnumerationError("Linux child ownership enumeration failed") from None
    except OSError as error:
        raise _ChildEnumerationError("Linux child ownership enumeration failed") from error
    values = text.split()
    if any(not value.isdecimal() for value in values):
        raise _ChildEnumerationError("Linux child ownership enumeration was malformed")
    return tuple(int(value) for value in values)


def _descendant_pids() -> tuple[int, ...]:
    """Enumerate a bounded complete descendant batch, deepest processes first."""
    pending = deque(_direct_child_pids())
    seen: set[int] = set()
    ordered: list[int] = []
    while pending and len(ordered) < _MAX_DESCENDANTS_PER_PASS:
        pid = pending.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        ordered.append(pid)
        remaining_capacity = _MAX_DESCENDANTS_PER_PASS - len(ordered) - len(pending)
        if remaining_capacity > 0:
            pending.extend(_direct_child_pids(pid)[:remaining_capacity])
    ordered.reverse()
    return tuple(ordered)


def _reap_exited_children() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, _POSIX_WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _terminate_owned_children() -> bool:
    deadline = time.monotonic() + _CLEANUP_DEADLINE_S
    empty_observations = 0
    try:
        while time.monotonic() < deadline:
            pids = _descendant_pids()
            for pid in pids:
                try:
                    os.kill(pid, _LINUX_SIGKILL)
                except ProcessLookupError:
                    continue
            _reap_exited_children()
            remaining = _descendant_pids()
            if remaining:
                empty_observations = 0
            else:
                empty_observations += 1
                if empty_observations >= _EMPTY_OBSERVATIONS_REQUIRED:
                    return True
            time.sleep(0.01)
        return not _descendant_pids()
    except _ChildEnumerationError:
        return False


def _normalized_returncode(returncode: int) -> int:
    return 128 + abs(returncode) if returncode < 0 else returncode


def _emit_control_status(control_fd: int | None, status: str) -> None:
    if control_fd is None:
        return
    try:
        os.write(control_fd, f"{status}\n".encode("ascii"))
    except OSError:
        return


def _parse_invocation(argv: list[str]) -> tuple[list[str], int | None]:
    arguments = list(argv)
    control_fd = None
    if arguments[:1] == ["--control-fd"]:
        if len(arguments) < 2 or not arguments[1].isdecimal():
            return [], None
        control_fd = int(arguments[1])
        arguments = arguments[2:]
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    return arguments, control_fd


def main(argv: list[str] | None = None) -> int:
    arguments, control_fd = _parse_invocation(list(sys.argv[1:] if argv is None else argv))
    try:
        return _run_supervisor(arguments, control_fd)
    finally:
        if control_fd is not None:
            with contextlib.suppress(OSError):
                os.close(control_fd)


def _run_supervisor(arguments: list[str], control_fd: int | None) -> int:
    if not arguments:
        _emit_control_status(control_fd, LAUNCH_ERROR_STATUS)
        return 125
    try:
        _become_subreaper()
    except OSError:
        _emit_control_status(control_fd, LAUNCH_ERROR_STATUS)
        return 125

    signal.signal(signal.SIGTERM, _request_termination)
    signal.signal(signal.SIGINT, _request_termination)
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is already explicit and shell-free
            arguments,
            close_fds=True,
        )
        returncode = process.wait()
        _block_termination_signals()
    except _TerminationRequested as request:
        _block_termination_signals()
        if not _terminate_owned_children():
            _emit_control_status(control_fd, CLEANUP_ERROR_STATUS)
            return 125
        _emit_control_status(control_fd, TERMINATED_STATUS)
        return 128 + request.signum
    except OSError:
        if process is None:
            _emit_control_status(control_fd, LAUNCH_ERROR_STATUS)
            return 125
        _block_termination_signals()
        if not _terminate_owned_children():
            _emit_control_status(control_fd, CLEANUP_ERROR_STATUS)
            return 125
        _emit_control_status(control_fd, RUNTIME_ERROR_STATUS)
        return 125
    if not _terminate_owned_children():
        _emit_control_status(control_fd, CLEANUP_ERROR_STATUS)
        return 125
    _emit_control_status(control_fd, VENDOR_EXIT_STATUS)
    return _normalized_returncode(returncode)


if __name__ == "__main__":
    raise SystemExit(main())
