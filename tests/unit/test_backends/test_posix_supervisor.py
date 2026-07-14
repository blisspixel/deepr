"""Unit tests for Linux plan-process subreaper supervision."""

from __future__ import annotations

import os
import signal

from deepr.backends.plan_quota import posix_supervisor


class _Process:
    def __init__(self, *, pid: int = 42, returncode: int = 0, wait_error: BaseException | None = None) -> None:
        self.pid = pid
        self.returncode = returncode
        self.wait_error = wait_error

    def wait(self) -> int:
        if self.wait_error is not None:
            raise self.wait_error
        return self.returncode


def _patch_process_runtime(monkeypatch, process: _Process, cleanup_result: bool = True):
    cleanup_calls = []
    monkeypatch.setattr(posix_supervisor, "_become_subreaper", lambda: None)
    monkeypatch.setattr(posix_supervisor.signal, "signal", lambda *args: None)
    monkeypatch.setattr(posix_supervisor, "_block_termination_signals", lambda: None)
    monkeypatch.setattr(posix_supervisor.subprocess, "Popen", lambda arguments, **_kwargs: process)

    def cleanup():
        cleanup_calls.append(True)
        return cleanup_result

    monkeypatch.setattr(posix_supervisor, "_terminate_owned_children", cleanup)
    return cleanup_calls


def test_normal_exit_preserves_code_after_descendant_cleanup(monkeypatch):
    cleanup_calls = _patch_process_runtime(monkeypatch, _Process(returncode=7))

    returncode, status = _run_with_control(["--", "vendor-cli"])

    assert returncode == 7
    assert status == posix_supervisor.VENDOR_EXIT_STATUS
    assert cleanup_calls == [True]


def test_normal_exit_fails_closed_when_cleanup_is_unconfirmed(monkeypatch):
    _patch_process_runtime(monkeypatch, _Process(), cleanup_result=False)

    returncode, status = _run_with_control(["--", "vendor-cli"])

    assert returncode == 125
    assert status == posix_supervisor.CLEANUP_ERROR_STATUS


def test_termination_after_vendor_exit_still_cleans_owned_descendants(monkeypatch):
    cleanup_calls = _patch_process_runtime(monkeypatch, _Process(returncode=0))
    block_calls = 0

    def interrupt_transition():
        nonlocal block_calls
        block_calls += 1
        if block_calls == 1:
            raise posix_supervisor._TerminationRequested(int(signal.SIGTERM))

    monkeypatch.setattr(posix_supervisor, "_block_termination_signals", interrupt_transition)

    returncode, status = _run_with_control(["--", "vendor-cli"])

    assert returncode == 128 + int(signal.SIGTERM)
    assert status == posix_supervisor.TERMINATED_STATUS
    assert cleanup_calls == [True]
    assert block_calls == 2


def test_termination_signal_kills_owned_primary_before_exit(monkeypatch):
    request = posix_supervisor._TerminationRequested(int(signal.SIGTERM))
    cleanup_calls = _patch_process_runtime(monkeypatch, _Process(pid=77, wait_error=request))

    assert posix_supervisor.main(["--", "vendor-cli"]) == 128 + int(signal.SIGTERM)
    assert cleanup_calls == [True]


def test_cleanup_kills_only_currently_owned_children(monkeypatch):
    observations = iter(((9, 10), (20,), (20,), (), (), ()))
    killed = []
    monkeypatch.setattr(posix_supervisor, "_direct_child_pids", lambda: next(observations))
    monkeypatch.setattr(posix_supervisor, "_reap_exited_children", lambda: None)
    monkeypatch.setattr(posix_supervisor.os, "kill", lambda pid, signum: killed.append((pid, signum)))
    monkeypatch.setattr(posix_supervisor.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(posix_supervisor.time, "monotonic", lambda: 0.0)

    assert posix_supervisor._terminate_owned_children() is True
    assert killed == [(9, 9), (10, 9), (20, 9)]


def test_child_enumeration_failure_fails_cleanup_closed(monkeypatch):
    def fail_enumeration():
        raise posix_supervisor._ChildEnumerationError("fixture enumeration failure")

    monkeypatch.setattr(posix_supervisor, "_direct_child_pids", fail_enumeration)

    assert posix_supervisor._terminate_owned_children() is False


def test_vendor_launch_failure_emits_control_status(monkeypatch):
    monkeypatch.setattr(posix_supervisor, "_become_subreaper", lambda: None)
    monkeypatch.setattr(posix_supervisor.signal, "signal", lambda *args: None)

    def fail_launch(_arguments, **_kwargs):
        raise FileNotFoundError(2, "fixture missing executable")

    monkeypatch.setattr(posix_supervisor.subprocess, "Popen", fail_launch)

    returncode, status = _run_with_control(["--", "vendor-cli"])

    assert returncode == 125
    assert status == posix_supervisor.LAUNCH_ERROR_STATUS


def test_vendor_wait_failure_is_post_dispatch_and_reaps_process(monkeypatch):
    cleanup_calls = _patch_process_runtime(monkeypatch, _Process(wait_error=OSError("fixture wait failure")))

    returncode, status = _run_with_control(["--", "vendor-cli"])

    assert returncode == 125
    assert status == posix_supervisor.RUNTIME_ERROR_STATUS
    assert cleanup_calls == [True]


def test_missing_vendor_command_fails_before_ownership_setup(monkeypatch):
    calls = []
    monkeypatch.setattr(posix_supervisor, "_become_subreaper", lambda: calls.append("subreaper"))

    assert posix_supervisor.main(["--"]) == 125
    assert calls == []


def _run_with_control(arguments):
    read_fd, write_fd = os.pipe()
    returncode = posix_supervisor.main(["--control-fd", str(write_fd), *arguments])
    status = os.read(read_fd, 256).decode("ascii").strip()
    os.close(read_fd)
    return returncode, status
