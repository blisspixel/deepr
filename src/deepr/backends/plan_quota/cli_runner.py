"""Safe async subprocess primitive for plan-quota CLI backends.

Plan-quota adapters drive a vendor's own coding/agent CLI (codex, claude,
opencode, ...) as a subprocess instead of calling a metered HTTP API. This is
the one shared, hardened invocation primitive every adapter uses:

- explicit ``argv`` (never ``shell=True``) so an untrusted prompt can never be
  re-interpreted as shell;
- a hard timeout that *kills* the process (a hung coding agent must not stall a
  scheduled maintenance run);
- stdout and stderr captured separately (most CLIs stream progress to stderr and
  print only the final answer to stdout, and the exhaustion signature usually
  lives in stderr);
- a scratch working directory by default so an agentic CLI cannot wander the
  user's repository.

Ordinary launch, timeout, and process failures return a structured ``CliResult``
for callers to decide. Task cancellation kills and reaps the process tree, then
propagates so orchestration can stop promptly.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Any

# Generous default: agentic CLIs reason for a while. Scheduled maintenance is
# time-flexible by design, but a hung process must still be reaped.
DEFAULT_TIMEOUT_S = 240.0
_PROCESS_CLEANUP_TIMEOUT_S = 1.0
_LAUNCH_CLEANUP_GRACE_S = 1.0
_BACKGROUND_CLEANUPS: set[asyncio.Task[None]] = set()


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

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.launch_error and not self.runtime_error


def _scratch_dir() -> str:
    """A stable scratch cwd so an agentic CLI does not default into the repo."""
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
    validated_timeout = validate_timeout(timeout)
    executable = str(argv[0]) if argv else "plan-cli"
    try:
        run_cwd = cwd if cwd is not None else _scratch_dir()
        run_argv = _clean_argv(argv)
        run_env = _clean_env(env)
        input_bytes = stdin.encode("utf-8") if stdin is not None else None
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
    if not run_argv:
        return CliResult(None, "", "", False, "failed to launch: empty argv", _ms(start))
    launch_task = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *run_argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=run_env,
            cwd=run_cwd,
            **_process_group_kwargs(),
        ),
        name="plan-quota-cli-launch",
    )
    try:
        proc = await asyncio.shield(launch_task)
    except asyncio.CancelledError:
        cleanup_task = asyncio.create_task(
            _cleanup_cancelled_launch(launch_task),
            name="plan-quota-cancelled-launch-cleanup",
        )
        _track_background_cleanup(cleanup_task)
        await _wait_for_launch_cleanup_grace(cleanup_task)
        raise
    except (OSError, ValueError) as e:
        return CliResult(
            None,
            "",
            "",
            False,
            _safe_launch_error(run_argv[0], e),
            _ms(start),
            launch_exception=e,
        )

    try:
        out, err = await asyncio.wait_for(proc.communicate(input_bytes), timeout=validated_timeout)
    except TimeoutError:
        cleanup_task = asyncio.create_task(
            _terminate_and_reap(proc),
            name="plan-quota-timeout-cleanup",
        )
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            await _finish_cleanup(cleanup_task)
            raise
        return CliResult(None, "", "", True, "", _ms(start))
    except asyncio.CancelledError:
        cleanup_task = asyncio.create_task(
            _terminate_and_reap(proc),
            name="plan-quota-process-cleanup",
        )
        await _finish_cleanup(cleanup_task)
        raise
    except Exception as error:
        cleanup_task = asyncio.create_task(
            _terminate_and_reap(proc),
            name="plan-quota-error-cleanup",
        )
        await _finish_cleanup(cleanup_task)
        return CliResult(
            proc.returncode,
            "",
            "",
            False,
            "",
            _ms(start),
            runtime_error=safe_runtime_error(error),
            runtime_exception=error,
        )

    return CliResult(
        proc.returncode,
        out.decode("utf-8", errors="replace") if out else "",
        err.decode("utf-8", errors="replace") if err else "",
        False,
        "",
        _ms(start),
    )


def _process_group_kwargs() -> dict[str, Any]:
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def _cleanup_cancelled_launch(
    launch_task: asyncio.Task[asyncio.subprocess.Process],
) -> None:
    """Own a shielded launch through completion and clean up any late process."""
    try:
        proc = await launch_task
    except (asyncio.CancelledError, OSError, ValueError):
        return
    await _terminate_and_reap(proc)


def _track_background_cleanup(cleanup_task: asyncio.Task[None]) -> None:
    """Keep ownership until a late launch has either failed or been reaped."""
    _BACKGROUND_CLEANUPS.add(cleanup_task)

    def discard_finished(task: asyncio.Task[None]) -> None:
        _BACKGROUND_CLEANUPS.discard(task)
        with contextlib.suppress(asyncio.CancelledError, Exception):
            task.result()

    cleanup_task.add_done_callback(discard_finished)


async def _wait_for_launch_cleanup_grace(cleanup_task: asyncio.Task[None]) -> None:
    """Give normal launches time to resolve without trapping cancellation."""
    try:
        await asyncio.wait(
            {cleanup_task},
            timeout=_LAUNCH_CLEANUP_GRACE_S,
        )
    except asyncio.CancelledError:
        # A repeated cancellation must not detach the tracked cleanup owner.
        return


async def _finish_cleanup(cleanup_task: asyncio.Task[None]) -> None:
    """Wait through repeated cancellation so cleanup is not abandoned."""
    while True:
        try:
            await asyncio.shield(cleanup_task)
            return
        except asyncio.CancelledError:
            if cleanup_task.done():
                return
        except Exception:
            return


async def _terminate_and_reap(proc: asyncio.subprocess.Process) -> None:
    """Best-effort process-tree termination with bounded cleanup waits."""
    await _kill_process_tree(proc)
    try:
        await asyncio.wait_for(
            proc.communicate(),
            timeout=_PROCESS_CLEANUP_TIMEOUT_S,
        )
    except (Exception, asyncio.CancelledError):
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                proc.wait(),
                timeout=_PROCESS_CLEANUP_TIMEOUT_S,
            )


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        with contextlib.suppress(Exception):
            killer = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(proc.pid),
                    "/T",
                    "/F",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
                timeout=_PROCESS_CLEANUP_TIMEOUT_S,
            )
            try:
                await asyncio.wait_for(
                    killer.wait(),
                    timeout=_PROCESS_CLEANUP_TIMEOUT_S,
                )
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    killer.kill()
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(
                        killer.wait(),
                        timeout=_PROCESS_CLEANUP_TIMEOUT_S,
                    )
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        return

    with contextlib.suppress(ProcessLookupError):
        import os

        kill_process_group = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", None)
        if callable(kill_process_group) and sigkill is not None:
            kill_process_group(proc.pid, sigkill)
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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


def _clean_argv(argv: list[str]) -> list[str]:
    """Normalize argv text so fetched web context cannot break process launch."""
    clean = [str(part).replace("\x00", " ") for part in argv]
    if not clean:
        return clean
    clean[0] = shutil.which(clean[0]) or clean[0]
    return clean


def _clean_env(env: Mapping[str, object] | None) -> dict[str, str] | None:
    """Drop env entries subprocess APIs cannot represent.

    Environment is operator-controlled and may include empty or cleared API-key
    overrides. Invalid entries should not make an otherwise safe plan-quota run
    fail before the vendor CLI starts.
    """
    if env is None:
        return None
    clean: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not key or "=" in key or "\x00" in key:
            continue
        if value is None:
            continue
        text = str(value)
        if "\x00" in text:
            continue
        clean[key] = text
    return clean
