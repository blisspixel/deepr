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

It never raises: callers get a structured ``CliResult`` and decide. That keeps
the ``research_fn`` seam contract (report, do not raise) intact end to end.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Generous default: agentic CLIs reason for a while. Scheduled maintenance is
# time-flexible by design, but a hung process must still be reaped.
DEFAULT_TIMEOUT_S = 240.0


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

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.launch_error


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
    """Run ``argv`` to completion and return a structured result. Never raises."""
    start = time.perf_counter()
    run_cwd = cwd if cwd is not None else _scratch_dir()
    run_argv = _clean_argv(argv)
    run_env = _clean_env(env)
    if not run_argv:
        return CliResult(None, "", "", False, "failed to launch: empty argv", _ms(start))
    try:
        proc = await asyncio.create_subprocess_exec(
            *run_argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=run_env,
            cwd=run_cwd,
            **_process_group_kwargs(),
        )
    except (OSError, ValueError) as e:
        return CliResult(None, "", "", False, f"failed to launch {run_argv[0]!r}: {e}", _ms(start))

    input_bytes = stdin.encode("utf-8") if stdin is not None else None
    try:
        out, err = await asyncio.wait_for(proc.communicate(input_bytes), timeout=timeout)
    except TimeoutError:
        await _kill_process_tree(proc)
        # Reap the killed process so it leaves no zombie / unawaited warning;
        # it is already being reported as a timeout, so drain errors are moot.
        with contextlib.suppress(Exception):
            await proc.communicate()
        return CliResult(None, "", "", True, "", _ms(start))
    except asyncio.CancelledError:
        await _kill_process_tree(proc)
        with contextlib.suppress(Exception):
            await proc.communicate()
        raise

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


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        with contextlib.suppress(Exception):
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await killer.wait()
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        return

    with contextlib.suppress(ProcessLookupError):
        import os

        os.killpg(proc.pid, signal.SIGKILL)
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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
