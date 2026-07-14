"""Pure preparation helpers for plan-quota subprocess launch."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from deepr.backends.plan_quota.process_control import (
    SupervisorControlPipe,
    open_supervisor_control_pipe,
)


@dataclass(frozen=True)
class PreparedInvocation:
    run_argv: list[str]
    launch_argv: list[str]
    run_cwd: str
    run_env: dict[str, str] | None
    input_bytes: bytes | None
    posix_supervised: bool
    supervisor_control: SupervisorControlPipe | None


def prepare_invocation(
    argv: list[str],
    *,
    stdin: str | None,
    env: Mapping[str, object] | None,
    run_cwd: str,
) -> PreparedInvocation:
    run_argv = clean_argv(argv)
    run_env = clean_env(env)
    input_bytes = stdin.encode("utf-8") if stdin is not None else None
    supervisor_control = open_supervisor_control_pipe() if run_argv and sys.platform.startswith("linux") else None
    try:
        launch_argv, posix_supervised = owned_process_argv(
            run_argv,
            control_fd=supervisor_control.write_fd if supervisor_control is not None else None,
        )
    except BaseException:
        if supervisor_control is not None:
            supervisor_control.close()
        raise
    return PreparedInvocation(
        run_argv,
        launch_argv,
        run_cwd,
        run_env,
        input_bytes,
        posix_supervised,
        supervisor_control,
    )


def process_group_kwargs() -> dict[str, Any]:
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        from deepr.backends.plan_quota.windows_job import CREATE_SUSPENDED

        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED}
    return {"start_new_session": True}


def owned_process_argv(argv: list[str], *, control_fd: int | None = None) -> tuple[list[str], bool]:
    if sys.platform.startswith("linux") and argv:
        if control_fd is None:
            raise RuntimeError("Linux supervisor control channel is unavailable")
        return [
            sys.executable,
            "-m",
            "deepr.backends.plan_quota.posix_supervisor",
            "--control-fd",
            str(control_fd),
            "--",
            *argv,
        ], True
    if os.name == "posix" and argv:
        raise RuntimeError("plan-quota process-tree ownership is unavailable on this POSIX platform")
    return argv, False


def clean_argv(argv: list[str]) -> list[str]:
    """Normalize argv text so fetched web context cannot break process launch."""
    clean = [str(part).replace("\x00", " ") for part in argv]
    if clean:
        clean[0] = shutil.which(clean[0]) or clean[0]
    return clean


def clean_env(env: Mapping[str, object] | None) -> dict[str, str] | None:
    """Drop environment entries that subprocess APIs cannot represent."""
    if env is None:
        return None
    clean: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not key or "=" in key or "\x00" in key or value is None:
            continue
        text = str(value)
        if "\x00" not in text:
            clean[key] = text
    return clean
