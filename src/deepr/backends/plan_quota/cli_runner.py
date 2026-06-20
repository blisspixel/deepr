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
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

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
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> CliResult:
    """Run ``argv`` to completion and return a structured result. Never raises."""
    start = time.perf_counter()
    run_cwd = cwd if cwd is not None else _scratch_dir()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=run_cwd,
        )
    except (OSError, ValueError) as e:
        return CliResult(None, "", "", False, f"failed to launch {argv[0]!r}: {e}", _ms(start))

    input_bytes = stdin.encode("utf-8") if stdin is not None else None
    try:
        out, err = await asyncio.wait_for(proc.communicate(input_bytes), timeout=timeout)
    except TimeoutError:
        proc.kill()
        # Reap the killed process so it leaves no zombie / unawaited warning;
        # it is already being reported as a timeout, so drain errors are moot.
        with contextlib.suppress(Exception):
            await proc.communicate()
        return CliResult(None, "", "", True, "", _ms(start))

    return CliResult(
        proc.returncode,
        out.decode("utf-8", errors="replace") if out else "",
        err.decode("utf-8", errors="replace") if err else "",
        False,
        "",
        _ms(start),
    )


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
