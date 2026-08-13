"""A local image generator, on the operator's word rather than on proof.

`DEEPR_LOCAL_IMAGE_URL` stays blocked, and correctly so: a loopback HTTP
endpoint is not evidence of local execution, because a proxy listening on
127.0.0.1 can hold cloud credentials and forward the request while looking
exactly like a local server. There is no way to tell from the client side.

A local *binary* is a different claim, but a weaker one than it first appears
and worth stating precisely.

What Deepr can guarantee: it reads no API key for this transport, passes none
to the subprocess, and makes no network call of its own. What Deepr **cannot**
guarantee is the behaviour of a program it does not own. An external binary
could hold its own credentials and call a paid API, and nothing here would
know. The difference from the HTTP path is that a URL invites a proxy to sit in
front of a cloud provider as its normal mode of use, whereas a pinned local
model file is what this tool is for - but that is a difference of likelihood,
not of proof.

So this is an **operator attestation**, not a verification. Setting
`DEEPR_LOCAL_IMAGE_CLI` is the operator asserting that the named tool runs
locally and spends nothing; the exemption from the metered gate rests on that
assertion. Absent the variable, nothing changes and portrait generation behaves
exactly as before.

For reproducible Artomate SDXL rendering, an operator can also set
`DEEPR_LOCAL_IMAGE_CLI_MANIFEST` to an absolute path naming a reviewed,
hash-pinned JSON asset manifest. Deepr then invokes the manifest-native command,
passes the prompt over standard input, and derives a stable seed from that
prompt. The explicit manifest wins over a friendly model alias that may drift.

The allowlist below matters for the same reason: this puts a model-authored
string on a command line, so the executable must be one of a known few rather
than anything the variable happens to name.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

LOCAL_IMAGE_CLI_ENV = "DEEPR_LOCAL_IMAGE_CLI"
LOCAL_IMAGE_MODEL_ENV = "DEEPR_LOCAL_IMAGE_CLI_MODEL"
LOCAL_IMAGE_MANIFEST_ENV = "DEEPR_LOCAL_IMAGE_CLI_MANIFEST"

_SUPPORTED = {"artomate"}
"""Tools whose invocation and output layout this module knows.

An allowlist rather than "run whatever the variable says": this takes a
model-authored string and puts it on a command line, so the executable must be
one of a known few rather than anything on PATH."""

_DEFAULT_MODEL = "flux2-klein"
_MODEL_RATIOS = {"auto": "3:4", "epicrealism": "3:4"}
"""Artomate's audited SDXL manifest is portrait-native rather than square."""
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


def _configured_manifest() -> Path | None:
    """Return one explicit hash-pinned local manifest, if configured."""
    raw = os.getenv(LOCAL_IMAGE_MANIFEST_ENV, "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise RuntimeError(f"{LOCAL_IMAGE_MANIFEST_ENV} must be an absolute JSON file path")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"{LOCAL_IMAGE_MANIFEST_ENV} does not name a readable file") from exc
    if not resolved.is_file() or resolved.suffix.casefold() != ".json":
        raise RuntimeError(f"{LOCAL_IMAGE_MANIFEST_ENV} must name a readable JSON file")
    return resolved


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

    manifest = _configured_manifest()
    model = os.getenv(LOCAL_IMAGE_MODEL_ENV, "").strip() or _DEFAULT_MODEL
    ratio = _MODEL_RATIOS.get(model, "1:1")

    # A fresh working directory per render: the tool writes `output/art-<hex>.png`
    # relative to the working directory and never overwrites, so "the file that
    # appeared" is unambiguous only when nothing was there before.
    #
    # ignore_cleanup_errors because the tool leaves a lock file inside its own
    # output directory, and Windows refuses to remove a directory holding an
    # open handle. Without it a successful render dies during cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        work_path = Path(work)
        if manifest is not None:
            output = work_path / "output" / "portrait.png"
            output.parent.mkdir()
            seed = int.from_bytes(sha256(prompt.encode("utf-8")).digest()[:8], "big")
            command = [
                executable,
                "create-sdxl",
                "--assets",
                str(manifest),
                "--output",
                str(output),
                "--seed",
                str(seed),
            ]
        else:
            output = None
            command = [executable, "imagine", prompt, "model", model, "ratio", ratio]
        try:
            result = subprocess.run(  # noqa: S603 - executable is allowlisted and resolved
                command,
                cwd=work,
                capture_output=True,
                text=True,
                input=prompt if manifest is not None else None,
                timeout=_RENDER_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{name} did not finish within {_RENDER_TIMEOUT_S}s") from exc

        produced = [output] if output is not None and output.is_file() else sorted((work_path / "output").glob("*.png"))
        if not produced:
            detail = (result.stderr or result.stdout or "").strip()[:300]
            raise RuntimeError(f"{name} produced no image: {detail or 'no output'}")
        return produced[0].read_bytes()
