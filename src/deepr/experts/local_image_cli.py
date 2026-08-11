"""A local image generator that can actually prove it is local.

`DEEPR_LOCAL_IMAGE_URL` stays blocked, and correctly so: a loopback HTTP
endpoint is not evidence of local execution, because a proxy listening on
127.0.0.1 can hold cloud credentials and forward the request while looking
exactly like a local server. There is no way to tell from the client side.

A local *binary* is a different claim. There is no endpoint to impersonate: the
process runs on this machine against a model file on this disk, the tool
reports which model it resolved, and no request leaves the host. That is
attestable in the way the HTTP path is not, which is why this exists as a
separate transport rather than as another URL.

Costs nothing per image beyond electricity. No API key is read, no network
call is made, and nothing here can reach a metered provider even if one is
configured.

Opt in with `DEEPR_LOCAL_IMAGE_CLI=artomate`. Absent that, portrait generation
behaves exactly as before.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

LOCAL_IMAGE_CLI_ENV = "DEEPR_LOCAL_IMAGE_CLI"
LOCAL_IMAGE_MODEL_ENV = "DEEPR_LOCAL_IMAGE_CLI_MODEL"

_SUPPORTED = {"artomate"}
"""Tools whose invocation and output layout this module knows.

An allowlist rather than "run whatever the variable says": this takes a
model-authored string and puts it on a command line, so the executable must be
one of a known few rather than anything on PATH."""

_DEFAULT_MODEL = "flux2-klein"
_RENDER_TIMEOUT_S = 1800
"""Half an hour. A local diffusion pass runs for minutes, not seconds, and a
short timeout would kill work that was going to succeed."""


def configured_cli() -> str:
    """The local image tool to use, or "" when none is configured."""
    name = os.getenv(LOCAL_IMAGE_CLI_ENV, "").strip().lower()
    return name if name in _SUPPORTED else ""


def is_available() -> bool:
    """Whether the configured tool is present on this machine."""
    name = configured_cli()
    return bool(name) and shutil.which(name) is not None


def render(prompt: str) -> bytes:
    """Render one image locally and return its bytes.

    Raises RuntimeError rather than returning None, because the caller is a
    cost-gated dispatch path where "no image" and "silently nothing" must not
    look the same.
    """
    name = configured_cli()
    if not name:
        raise RuntimeError(f"{LOCAL_IMAGE_CLI_ENV} is not set to a supported local image tool")
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f"{name} is configured as the local image tool but is not on PATH")

    model = os.getenv(LOCAL_IMAGE_MODEL_ENV, "").strip() or _DEFAULT_MODEL

    # A fresh working directory per render: the tool writes `output/art-<hex>.png`
    # relative to the working directory and never overwrites, so "the file that
    # appeared" is unambiguous only when nothing was there before.
    #
    # ignore_cleanup_errors because the tool leaves a lock file inside its own
    # output directory, and Windows refuses to remove a directory holding an
    # open handle. Without it a successful render dies during cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        try:
            result = subprocess.run(  # noqa: S603 - executable is allowlisted and resolved
                [executable, "imagine", prompt, "model", model, "ratio", "1:1"],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=_RENDER_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{name} did not finish within {_RENDER_TIMEOUT_S}s") from exc

        produced = sorted((Path(work) / "output").glob("*.png"))
        if not produced:
            detail = (result.stderr or result.stdout or "").strip()[:300]
            raise RuntimeError(f"{name} produced no image: {detail or 'no output'}")
        return produced[0].read_bytes()
