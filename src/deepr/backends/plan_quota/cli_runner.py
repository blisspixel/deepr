"""Safe async subprocess primitive for plan-quota CLI backends.

Plan-quota adapters drive vendor CLIs as subprocesses instead of calling a
metered HTTP API. This is the shared hardened invocation primitive:

- explicit ``argv`` (never ``shell=True``) so an untrusted prompt can never be
  re-interpreted as shell;
- a hard timeout that kills and reaps a hung process tree;
- stdout and stderr captured separately under fixed byte ceilings;
- a scratch working directory by default so an agentic CLI cannot wander the
  user's repository.

Failures return a structured ``CliResult``. Cancellation kills and reaps the
owned process tree before it propagates.
"""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
import tempfile
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Any

from deepr.backends.plan_quota import process_cleanup as _process_cleanup
from deepr.backends.plan_quota.process_cleanup import (
    ProcessCleanupError,
)
from deepr.backends.plan_quota.process_control import (
    SupervisorControlPipe,
)
from deepr.backends.plan_quota.process_launch import (
    PreparedInvocation as _PreparedInvocation,
)
from deepr.backends.plan_quota.process_launch import (
    clean_argv,
    clean_env,
)
from deepr.backends.plan_quota.process_launch import (
    prepare_invocation as _prepare_process_invocation,
)
from deepr.backends.plan_quota.process_launch import (
    process_group_kwargs as _process_group_kwargs,
)

# Agentic CLIs can reason for a while, but a hung process must still be reaped.
DEFAULT_TIMEOUT_S = 240.0
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_PROCESS_CLEANUP_TIMEOUT_S = 1.0
_LAUNCH_CLEANUP_GRACE_S = 1.0
_BACKGROUND_CLEANUPS: set[asyncio.Task[ProcessCleanupError | None]] = set()
_BACKGROUND_CLEANUP_FAILURES: deque[ProcessCleanupError] = deque(maxlen=32)


def _clean_argv(argv: list[str]) -> list[str]:
    """Compatibility seam for focused launch-sanitization tests."""
    return clean_argv(argv)


def _close_windows_job(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    return _process_cleanup.close_windows_job(proc)


def _terminate_windows_job(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    return _process_cleanup.terminate_windows_job(proc)


def _close_process_transport(proc: asyncio.subprocess.Process) -> None:
    _process_cleanup.close_process_transport(proc)


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    return await _process_cleanup.kill_process_tree(proc)


async def _kill_windows_process_tree(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    return await _process_cleanup.kill_windows_process_tree(proc)


def _clean_env(env: Mapping[str, object] | None) -> dict[str, str] | None:
    """Compatibility seam for callers that exercised the former local helper."""
    return clean_env(env)


class OutputLimitStream(StrEnum):
    """The bounded process stream that exceeded its raw-byte ceiling."""

    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True)
class CliResult:
    """The outcome of one CLI invocation. ``returncode is None`` means it never
    produced an exit status (launch failure or timeout kill)."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    launch_error: str
    duration_ms: int
    launch_exception: BaseException | None = field(default=None, repr=False, compare=False)
    runtime_error: str = ""
    runtime_exception: BaseException | None = field(default=None, repr=False, compare=False)
    output_limit_stream: OutputLimitStream | None = None
    cleanup_error: str = ""
    cleanup_exception: BaseException | None = field(default=None, repr=False, compare=False)
    secondary_runtime_error: str = ""
    secondary_runtime_exception: BaseException | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        return (
            self.returncode == 0
            and not self.timed_out
            and not self.launch_error
            and not self.runtime_error
            and not self.output_limit_exceeded
            and not self.cleanup_error
        )

    @property
    def output_limit_exceeded(self) -> bool:
        return self.output_limit_stream is not None

    @property
    def runtime_failure_outcome(self) -> str:
        if self.cleanup_error or isinstance(self.runtime_exception, ProcessCleanupError):
            return "cleanup_error"
        if self.output_limit_exceeded:
            return "output_limit_exceeded"
        return "runner_error"

    @property
    def runtime_failure_detail(self) -> str:
        if self.cleanup_error or isinstance(self.runtime_exception, ProcessCleanupError):
            return "CLI process ownership cleanup could not be confirmed; quota usage is unknown"
        if self.output_limit_exceeded:
            return "CLI output exceeded the per-stream capture limit; quota usage is unknown"
        return "CLI process failed after launch; quota usage is unknown"


@dataclass(frozen=True)
class _CapturedOutput:
    stdout: bytes
    stderr: bytes
    output_limit_stream: OutputLimitStream | None
    cleanup_error: ProcessCleanupError | None = None


def _scratch_dir() -> str:
    path = Path(tempfile.gettempdir()) / "deepr-plan-quota"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


async def run_cli(
    argv: list[str],
    *,
    stdin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    env: Mapping[str, object] | None = None,
    cwd: str | None = None,
) -> CliResult:
    """Return a structured process result, while propagating cancellation."""
    start = time.perf_counter()
    deadline = asyncio.get_running_loop().time() + validate_timeout(timeout)
    executable = str(argv[0]) if argv else "plan-cli"
    try:
        prepared = _prepare_invocation(argv, stdin=stdin, env=env, cwd=cwd)
    except Exception as error:
        return _launch_failure_result(executable, error, start=start)
    if not prepared.run_argv:
        return CliResult(None, "", "", False, "failed to launch: empty argv", _ms(start))
    launched = await _launch_owned_process(prepared, deadline=deadline, start=start)
    if isinstance(launched, CliResult):
        return launched
    return await _collect_owned_process(launched, prepared, deadline=deadline, start=start)


def _prepare_invocation(
    argv: list[str],
    *,
    stdin: str | None,
    env: Mapping[str, object] | None,
    cwd: str | None,
) -> _PreparedInvocation:
    return _prepare_process_invocation(
        argv,
        stdin=stdin,
        env=env,
        run_cwd=cwd if cwd is not None else _scratch_dir(),
    )


async def _launch_owned_process(
    prepared: _PreparedInvocation,
    *,
    deadline: float,
    start: float,
) -> asyncio.subprocess.Process | CliResult:
    process_kwargs = _process_group_kwargs()
    control = prepared.supervisor_control
    if control is not None and control.write_fd is not None:
        process_kwargs["pass_fds"] = (control.write_fd,)
    launch_task = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *prepared.launch_argv,
            stdin=asyncio.subprocess.PIPE if prepared.input_bytes is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=prepared.run_env,
            cwd=prepared.run_cwd,
            limit=_READ_CHUNK_BYTES,
            **process_kwargs,
        ),
        name="plan-quota-cli-launch",
    )
    if control is not None:
        launch_task.add_done_callback(lambda _task: control.close_write())
    launched = await _await_launch_task(
        launch_task,
        deadline=deadline,
        executable=prepared.run_argv[0],
        start=start,
        supervisor_control=control,
    )
    if isinstance(launched, CliResult):
        if control is not None and launch_task.done():
            control.close()
        return launched
    try:
        _claim_process_ownership(launched)
    except Exception as error:
        cleanup_task = asyncio.create_task(
            _abort_unowned_process(launched),
            name="plan-quota-unowned-process-cleanup",
        )
        try:
            cleanup_error = await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as cancellation_error:
            cleanup_error = await _finish_cleanup(cleanup_task)
            _attach_cleanup_failure(cancellation_error, cleanup_error)
            if control is not None:
                control.close()
            raise
        if control is not None:
            control.close()
        return _launch_failure_result(
            prepared.run_argv[0],
            error,
            start=start,
            cleanup_error=cleanup_error,
        )
    if prepared.posix_supervised and isinstance(launched, asyncio.subprocess.Process):
        launched._deepr_posix_supervisor = True  # type: ignore[attr-defined]
    return launched


async def _collect_owned_process(
    proc: asyncio.subprocess.Process,
    prepared: _PreparedInvocation,
    *,
    deadline: float,
    start: float,
) -> CliResult:
    control = prepared.supervisor_control
    try:
        remaining = _remaining_timeout(deadline)
        if remaining <= 0:
            return await _finish_elapsed_launch(proc, prepared.run_argv[0], control, start=start)
        result = await _collect_started_process(
            proc,
            input_bytes=prepared.input_bytes,
            timeout=remaining,
            start=start,
        )
        status = control.read_status() if control is not None else None
        classified = _classify_linux_supervisor_result(
            result,
            proc,
            executable=prepared.run_argv[0],
            supervisor_status=status,
        )
        release_task = asyncio.create_task(
            _release_completed_process(proc, classified),
            name="plan-quota-completed-process-release",
        )
        try:
            return await asyncio.shield(release_task)
        except asyncio.CancelledError as cancellation_error:
            released = await _finish_completed_release(release_task)
            cleanup_error = (
                released.cleanup_exception if isinstance(released.cleanup_exception, ProcessCleanupError) else None
            )
            _attach_cleanup_failure(cancellation_error, cleanup_error)
            raise
    finally:
        if control is not None:
            control.close()


async def _finish_elapsed_launch(
    proc: asyncio.subprocess.Process,
    executable: str,
    control: SupervisorControlPipe | None,
    *,
    start: float,
) -> CliResult:
    cleanup_task = asyncio.create_task(
        _terminate_and_reap(proc),
        name="plan-quota-elapsed-launch-cleanup",
    )
    try:
        cleanup_error = await asyncio.shield(cleanup_task)
    except asyncio.CancelledError as cancellation_error:
        cleanup_error = await _finish_cleanup(cleanup_task)
        _attach_cleanup_failure(cancellation_error, cleanup_error)
        raise
    result = CliResult(
        None,
        "",
        "",
        True,
        "",
        _ms(start),
        runtime_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
        runtime_exception=cleanup_error,
        cleanup_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
        cleanup_exception=cleanup_error,
    )
    status = control.read_status() if control is not None else None
    return _classify_linux_supervisor_result(
        result,
        proc,
        executable=executable,
        supervisor_status=status,
    )


async def _release_completed_process(proc: asyncio.subprocess.Process, result: CliResult) -> CliResult:
    if result.timed_out or result.runtime_error:
        return result
    try:
        cleanup_error = await _kill_process_tree(proc)
    except Exception as error:
        cleanup_error = ProcessCleanupError(f"completed process cleanup failed ({type(error).__name__})")
    if cleanup_error is None:
        return result
    return replace(
        result,
        runtime_error=safe_runtime_error(cleanup_error),
        runtime_exception=cleanup_error,
        cleanup_error=safe_runtime_error(cleanup_error),
        cleanup_exception=cleanup_error,
    )


async def _finish_completed_release(release_task: asyncio.Task[CliResult]) -> CliResult:
    """Own final process-handle release through repeated caller cancellation."""
    while True:
        try:
            return await asyncio.shield(release_task)
        except asyncio.CancelledError:
            if release_task.done():
                return release_task.result()


def _launch_failure_result(
    executable: str,
    error: BaseException,
    *,
    start: float,
    cleanup_error: ProcessCleanupError | None = None,
) -> CliResult:
    return CliResult(
        None,
        "",
        "",
        False,
        _safe_launch_error(executable, error),
        _ms(start),
        launch_exception=error,
        cleanup_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
        cleanup_exception=cleanup_error,
    )


async def _await_launch_task(
    launch_task: asyncio.Task[asyncio.subprocess.Process],
    *,
    deadline: float,
    executable: str,
    start: float,
    supervisor_control: SupervisorControlPipe | None,
) -> asyncio.subprocess.Process | CliResult:
    try:
        return await asyncio.wait_for(
            asyncio.shield(launch_task),
            timeout=_remaining_timeout(deadline),
        )
    except TimeoutError:
        cleanup_task = asyncio.create_task(
            _cleanup_cancelled_launch(launch_task, supervisor_control),
            name="plan-quota-timed-out-launch-cleanup",
        )
        _track_background_cleanup(cleanup_task)
        try:
            cleanup_error = await _wait_for_launch_cleanup_grace(cleanup_task)
        except asyncio.CancelledError as cancellation_error:
            _attach_cleanup_failure(
                cancellation_error,
                _completed_or_pending_launch_cleanup(cleanup_task),
            )
            raise
        return CliResult(
            None,
            "",
            "",
            True,
            "",
            _ms(start),
            runtime_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
            runtime_exception=cleanup_error,
            cleanup_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
            cleanup_exception=cleanup_error,
        )
    except asyncio.CancelledError as cancellation_error:
        cleanup_task = asyncio.create_task(
            _cleanup_cancelled_launch(launch_task, supervisor_control),
            name="plan-quota-cancelled-launch-cleanup",
        )
        _track_background_cleanup(cleanup_task)
        try:
            cleanup_error = await _wait_for_launch_cleanup_grace(cleanup_task)
        except asyncio.CancelledError:
            cleanup_error = _completed_or_pending_launch_cleanup(cleanup_task)
        _attach_cleanup_failure(cancellation_error, cleanup_error)
        raise cancellation_error
    except Exception as error:
        return CliResult(
            None,
            "",
            "",
            False,
            _safe_launch_error(executable, error),
            _ms(start),
            launch_exception=error,
        )


async def _collect_started_process(
    proc: asyncio.subprocess.Process,
    *,
    input_bytes: bytes | None,
    timeout: float,
    start: float,
) -> CliResult:
    try:
        captured = await asyncio.wait_for(_communicate_bounded(proc, input_bytes), timeout=timeout)
    except TimeoutError:
        cleanup_task = asyncio.create_task(
            _terminate_and_reap(proc),
            name="plan-quota-timeout-cleanup",
        )
        try:
            cleanup_error = await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as cancellation_error:
            cleanup_error = await _finish_cleanup(cleanup_task)
            _attach_cleanup_failure(cancellation_error, cleanup_error)
            raise
        return CliResult(
            None,
            "",
            "",
            True,
            "",
            _ms(start),
            runtime_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
            runtime_exception=cleanup_error,
            cleanup_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
            cleanup_exception=cleanup_error,
        )
    except asyncio.CancelledError as cancellation_error:
        cleanup_task = asyncio.create_task(
            _terminate_and_reap(proc, infer_supervisor_error=True),
            name="plan-quota-process-cleanup",
        )
        cleanup_error = await _finish_cleanup(cleanup_task)
        _attach_cleanup_failure(cancellation_error, cleanup_error)
        raise
    except Exception as error:
        cleanup_task = asyncio.create_task(
            _terminate_and_reap(proc),
            name="plan-quota-error-cleanup",
        )
        cleanup_error = await _finish_cleanup(cleanup_task)
        primary_runtime_error = safe_runtime_error(error)
        return CliResult(
            proc.returncode,
            "",
            "",
            False,
            "",
            _ms(start),
            runtime_error=(safe_runtime_error(cleanup_error) if cleanup_error is not None else primary_runtime_error),
            runtime_exception=cleanup_error if cleanup_error is not None else error,
            cleanup_error=safe_runtime_error(cleanup_error) if cleanup_error is not None else "",
            cleanup_exception=cleanup_error,
            secondary_runtime_error=primary_runtime_error if cleanup_error is not None else "",
            secondary_runtime_exception=error if cleanup_error is not None else None,
        )

    cleanup_runtime_error = safe_runtime_error(captured.cleanup_error) if captured.cleanup_error is not None else ""
    return CliResult(
        proc.returncode,
        captured.stdout.decode("utf-8", errors="replace") if captured.stdout else "",
        captured.stderr.decode("utf-8", errors="replace") if captured.stderr else "",
        False,
        "",
        _ms(start),
        runtime_error=(
            cleanup_runtime_error
            if captured.cleanup_error is not None
            else f"output limit exceeded on {captured.output_limit_stream}"
            if captured.output_limit_stream is not None
            else ""
        ),
        runtime_exception=captured.cleanup_error,
        output_limit_stream=captured.output_limit_stream,
        cleanup_error=safe_runtime_error(captured.cleanup_error) if captured.cleanup_error is not None else "",
        cleanup_exception=captured.cleanup_error,
        secondary_runtime_error=(
            f"output limit exceeded on {captured.output_limit_stream}"
            if captured.cleanup_error is not None and captured.output_limit_stream is not None
            else ""
        ),
    )


async def _communicate_bounded(
    proc: asyncio.subprocess.Process,
    input_bytes: bytes | None,
) -> _CapturedOutput:
    """Write stdin and drain both output pipes under independent byte caps.

    Real ``asyncio.subprocess.Process`` instances expose stream objects. The
    fallback preserves compatibility with narrow injected process doubles while
    production subprocesses always use the bounded path.
    """
    stdout_stream = getattr(proc, "stdout", None)
    stderr_stream = getattr(proc, "stderr", None)
    if stdout_stream is None or stderr_stream is None:
        stdout, stderr = await proc.communicate(input_bytes)
        return _CapturedOutput(stdout or b"", stderr or b"", None)

    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    overflow: asyncio.Future[OutputLimitStream] = asyncio.get_running_loop().create_future()
    stdout_task = asyncio.create_task(
        _read_bounded(stdout_stream, OutputLimitStream.STDOUT, stdout_buffer, overflow),
        name="plan-quota-stdout-drain",
    )
    stderr_task = asyncio.create_task(
        _read_bounded(stderr_stream, OutputLimitStream.STDERR, stderr_buffer, overflow),
        name="plan-quota-stderr-drain",
    )
    stdin_task = asyncio.create_task(
        _write_stdin(getattr(proc, "stdin", None), input_bytes),
        name="plan-quota-stdin-write",
    )
    wait_task = asyncio.create_task(_wait_for_process(proc), name="plan-quota-process-wait")
    overflow_task = asyncio.create_task(_wait_for_overflow(overflow), name="plan-quota-output-limit-wait")
    tasks: tuple[asyncio.Task[Any], ...] = (stdout_task, stderr_task, stdin_task, wait_task)
    try:
        output_limit_stream = await _wait_for_process_or_overflow(
            wait_task,
            overflow_task,
            io_tasks=(stdout_task, stderr_task, stdin_task),
        )
        if output_limit_stream is not None:
            cleanup_error = await _terminate_and_wait(proc)
            await _settle_output_tasks(tasks)
            _close_process_transport(proc)
        else:
            cleanup_error = None
        return _CapturedOutput(
            bytes(stdout_buffer),
            bytes(stderr_buffer),
            output_limit_stream,
            cleanup_error,
        )
    finally:
        for task in (*tasks, overflow_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, overflow_task, return_exceptions=True)


async def _wait_for_process(proc: asyncio.subprocess.Process) -> None:
    await proc.wait()


async def _wait_for_overflow(overflow: asyncio.Future[OutputLimitStream]) -> OutputLimitStream:
    return await overflow


async def _wait_for_process_or_overflow(
    wait_task: asyncio.Task[None],
    overflow_task: asyncio.Task[OutputLimitStream],
    *,
    io_tasks: tuple[asyncio.Task[Any], ...],
) -> OutputLimitStream | None:
    watched: set[asyncio.Task[Any]] = {wait_task, overflow_task, *io_tasks}
    process_finished = False
    while True:
        done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
        if overflow_task in done:
            return overflow_task.result()
        if wait_task in done:
            watched.discard(wait_task)
            wait_task.result()
            process_finished = True
        for task in done:
            if task is wait_task:
                continue
            watched.discard(task)
            task.result()
        if process_finished and all(task.done() for task in io_tasks):
            await asyncio.sleep(0)
            return overflow_task.result() if overflow_task.done() else None


async def _settle_output_tasks(tasks: tuple[asyncio.Task[Any], ...]) -> None:
    """Let killed-process pipes close, then abandon any inherited open pipe."""
    _, pending = await asyncio.wait(tasks, timeout=_PROCESS_CLEANUP_TIMEOUT_S)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _read_bounded(
    stream: asyncio.StreamReader,
    stream_name: OutputLimitStream,
    captured: bytearray,
    overflow: asyncio.Future[OutputLimitStream],
) -> None:
    limit_crossed = False
    while True:
        chunk = await stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            return
        if limit_crossed:
            continue
        remaining = MAX_CAPTURE_BYTES - len(captured)
        captured.extend(chunk[:remaining])
        if len(chunk) > remaining:
            limit_crossed = True
            if not overflow.done():
                overflow.set_result(stream_name)


async def _write_stdin(
    stream: asyncio.StreamWriter | None,
    input_bytes: bytes | None,
) -> None:
    if stream is None:
        return
    try:
        if input_bytes is not None:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                stream.write(input_bytes)
                await stream.drain()
    finally:
        stream.close()
        wait_closed = getattr(stream, "wait_closed", None)
        if callable(wait_closed):
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await wait_closed()


async def _terminate_and_wait(
    proc: asyncio.subprocess.Process,
    *,
    infer_supervisor_error: bool = False,
) -> ProcessCleanupError | None:
    """Kill and reap without asking ``communicate`` to re-own active pipes."""
    cleanup_error = await _kill_process_tree(proc)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_CLEANUP_TIMEOUT_S)
    except Exception as error:
        cleanup_error = cleanup_error or _forced_supervisor_termination_error(proc)
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=_PROCESS_CLEANUP_TIMEOUT_S)
        except Exception as final_error:
            cleanup_error = cleanup_error or ProcessCleanupError(f"process reap failed ({type(final_error).__name__})")
        if cleanup_error is None and proc.returncode is None:
            cleanup_error = ProcessCleanupError(f"process reap failed ({type(error).__name__})")
    finally:
        _close_process_transport(proc)
    return cleanup_error or (_linux_supervisor_error(proc) if infer_supervisor_error else None)


def _claim_process_ownership(proc: asyncio.subprocess.Process) -> None:
    """Resume a real Windows child only after a kill-tree job owns it."""
    if not hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") or not isinstance(proc, asyncio.subprocess.Process):
        return
    from deepr.backends.plan_quota.windows_job import attach_kill_job_and_resume

    job = attach_kill_job_and_resume(proc.pid)
    proc._deepr_windows_kill_job = job  # type: ignore[attr-defined]


async def _abort_unowned_process(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    """Terminate a suspended process whose Windows ownership setup failed."""
    cleanup_error = None
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            cleanup_error = None
        except Exception as error:
            cleanup_error = ProcessCleanupError(f"unowned process termination failed ({type(error).__name__})")
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_CLEANUP_TIMEOUT_S)
    except Exception as error:
        cleanup_error = cleanup_error or ProcessCleanupError(f"unowned process reap failed ({type(error).__name__})")
    if cleanup_error is None and proc.returncode is None:
        cleanup_error = ProcessCleanupError("unowned process reap did not produce an exit status")
    _close_process_transport(proc)
    return cleanup_error


async def _cleanup_cancelled_launch(
    launch_task: asyncio.Task[asyncio.subprocess.Process],
    supervisor_control: SupervisorControlPipe | None,
) -> ProcessCleanupError | None:
    """Own a shielded launch through completion and clean up any late process."""
    try:
        try:
            proc = await launch_task
        except (asyncio.CancelledError, Exception):
            return None
        if supervisor_control is not None and isinstance(proc, asyncio.subprocess.Process):
            proc._deepr_posix_supervisor = True  # type: ignore[attr-defined]
        return await _terminate_and_reap(proc, infer_supervisor_error=True)
    finally:
        if supervisor_control is not None:
            supervisor_control.close()


def _track_background_cleanup(cleanup_task: asyncio.Task[ProcessCleanupError | None]) -> None:
    """Keep ownership until a late launch has either failed or been reaped."""
    _BACKGROUND_CLEANUPS.add(cleanup_task)

    def discard_finished(task: asyncio.Task[ProcessCleanupError | None]) -> None:
        _BACKGROUND_CLEANUPS.discard(task)
        try:
            cleanup_error = task.result()
        except asyncio.CancelledError:
            cleanup_error = ProcessCleanupError("late process launch cleanup task was cancelled")
        except Exception:
            cleanup_error = ProcessCleanupError("late process launch cleanup task failed")
        if cleanup_error is not None:
            _BACKGROUND_CLEANUP_FAILURES.append(cleanup_error)

    cleanup_task.add_done_callback(discard_finished)


async def _wait_for_launch_cleanup_grace(
    cleanup_task: asyncio.Task[ProcessCleanupError | None],
) -> ProcessCleanupError | None:
    """Give normal launches time to resolve without trapping cancellation."""
    done, _pending = await asyncio.wait(
        {cleanup_task},
        timeout=_LAUNCH_CLEANUP_GRACE_S,
    )
    if done:
        return _completed_or_pending_launch_cleanup(cleanup_task)
    return _pending_launch_cleanup_error()


def _completed_or_pending_launch_cleanup(
    cleanup_task: asyncio.Task[ProcessCleanupError | None],
) -> ProcessCleanupError | None:
    if cleanup_task.done():
        try:
            return cleanup_task.result()
        except (asyncio.CancelledError, Exception):
            return ProcessCleanupError("late process launch cleanup task failed")
    return _pending_launch_cleanup_error()


def _pending_launch_cleanup_error() -> ProcessCleanupError:
    return ProcessCleanupError("late process launch cleanup remains pending under background ownership")


async def _finish_cleanup(
    cleanup_task: asyncio.Task[ProcessCleanupError | None],
) -> ProcessCleanupError | None:
    """Wait through repeated cancellation so cleanup is not abandoned."""
    while True:
        try:
            return await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            if cleanup_task.done():
                return _completed_or_pending_launch_cleanup(cleanup_task)
        except Exception:
            return ProcessCleanupError("process cleanup task failed")


def _attach_cleanup_failure(
    primary_error: BaseException,
    cleanup_error: ProcessCleanupError | None,
) -> None:
    if cleanup_error is None:
        return
    primary_error.__dict__["plan_quota_cleanup_error"] = cleanup_error
    primary_error.__dict__["cleanup_error"] = safe_runtime_error(cleanup_error)


async def _terminate_and_reap(
    proc: asyncio.subprocess.Process,
    *,
    infer_supervisor_error: bool = False,
) -> ProcessCleanupError | None:
    """Best-effort process-tree termination with bounded cleanup waits."""
    cleanup_error = await _kill_process_tree(proc)
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_CLEANUP_TIMEOUT_S)
    except (Exception, asyncio.CancelledError) as error:
        cleanup_error = cleanup_error or _forced_supervisor_termination_error(proc)
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        try:
            await asyncio.wait_for(
                proc.wait(),
                timeout=_PROCESS_CLEANUP_TIMEOUT_S,
            )
        except Exception as final_error:
            cleanup_error = cleanup_error or ProcessCleanupError(f"process reap failed ({type(final_error).__name__})")
        if cleanup_error is None and proc.returncode is None:
            cleanup_error = ProcessCleanupError(f"process reap failed ({type(error).__name__})")
    finally:
        _close_process_transport(proc)
    return cleanup_error or (_linux_supervisor_error(proc) if infer_supervisor_error else None)


def _linux_supervisor_error(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    if getattr(proc, "_deepr_posix_supervisor", False) and proc.returncode == 125:
        return ProcessCleanupError("Linux child-subreaper ownership or cleanup failed")
    return None


def _forced_supervisor_termination_error(proc: asyncio.subprocess.Process) -> ProcessCleanupError | None:
    if getattr(proc, "_deepr_posix_supervisor", False) and proc.returncode is None:
        return ProcessCleanupError("Linux child-subreaper cleanup exceeded its bounded shutdown deadline")
    return None


def _classify_linux_supervisor_result(
    result: CliResult,
    proc: asyncio.subprocess.Process,
    *,
    executable: str,
    supervisor_status: str | None,
) -> CliResult:
    """Translate private supervisor control records into runner outcomes."""
    if not getattr(proc, "_deepr_posix_supervisor", False):
        return result
    from deepr.backends.plan_quota.posix_supervisor import (
        CLEANUP_ERROR_STATUS,
        LAUNCH_ERROR_STATUS,
        RUNTIME_ERROR_STATUS,
        TERMINATED_STATUS,
        VENDOR_EXIT_STATUS,
    )

    if supervisor_status == VENDOR_EXIT_STATUS:
        return result
    if supervisor_status == TERMINATED_STATUS:
        return result
    if supervisor_status == LAUNCH_ERROR_STATUS:
        launch_exception = OSError("Linux supervisor could not launch the vendor executable")
        return replace(
            result,
            returncode=None,
            stdout="",
            launch_error=_safe_launch_error(executable, launch_exception),
            launch_exception=launch_exception,
            runtime_error="",
            runtime_exception=None,
            output_limit_stream=None,
            cleanup_error="",
            cleanup_exception=None,
            secondary_runtime_error="",
            secondary_runtime_exception=None,
        )
    if supervisor_status == RUNTIME_ERROR_STATUS:
        runtime_exception = RuntimeError("Linux supervisor could not obtain the vendor process exit status")
        return replace(
            result,
            runtime_error=safe_runtime_error(runtime_exception),
            runtime_exception=runtime_exception,
        )
    cleanup_detail = (
        "Linux child-subreaper ownership or cleanup failed"
        if supervisor_status == CLEANUP_ERROR_STATUS
        else "Linux child-subreaper control status was missing or invalid"
    )
    cleanup_exception = ProcessCleanupError(cleanup_detail)
    return replace(
        result,
        runtime_error=safe_runtime_error(cleanup_exception),
        runtime_exception=cleanup_exception,
        cleanup_error=safe_runtime_error(cleanup_exception),
        cleanup_exception=cleanup_exception,
    )


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _remaining_timeout(deadline: float) -> float:
    return max(0.0, deadline - asyncio.get_running_loop().time())


def _safe_launch_error(executable: str, error: BaseException) -> str:
    """Describe launch failure without exposing resolved paths or OS prose."""
    executable_name = executable.replace("\\", "/").rsplit("/", 1)[-1] or "plan-cli"
    errno = getattr(error, "errno", None)
    errno_detail = f", errno={errno}" if isinstance(errno, int) else ""
    return f"failed to launch {executable_name!r} ({type(error).__name__}{errno_detail})"


def safe_runtime_error(error: BaseException) -> str:
    """Describe a post-launch runner failure without rendering OS details."""
    errno = getattr(error, "errno", None)
    errno_detail = f", errno={errno}" if isinstance(errno, int) else ""
    return f"runner failed ({type(error).__name__}{errno_detail})"


def validate_timeout(timeout: object) -> float:
    """Return a finite positive hard timeout before any process can launch."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number")
    return float(timeout)
