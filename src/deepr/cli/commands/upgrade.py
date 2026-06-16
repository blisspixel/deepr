"""Self-update command: `deepr upgrade`.

Modern CLI QOL (cf. claude / codex / grok CLIs): let the tool update itself
and tell the user when a newer version is available, regardless of how it
was installed (pipx, pip, or an editable source checkout).

No new dependencies: PyPI is queried via urllib (stdlib), the upgrade runs
the appropriate packaging tool via subprocess. All network access is
timeout-bounded and degrades gracefully offline.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from importlib import metadata as importlib_metadata

import click

from deepr import __version__
from deepr.cli.colors import print_error, print_success

PACKAGE = "deepr-research"
_PYPI_URL = f"https://pypi.org/pypi/{PACKAGE}/json"
_PYPI_TIMEOUT = 8  # seconds


def _detect_origin() -> str:
    """Best-effort detection of how deepr was installed.

    Returns one of: "editable" (source checkout), "pipx", or "pip".
    """
    try:
        dist = importlib_metadata.distribution(PACKAGE)
        direct_url = dist.read_text("direct_url.json")
        if direct_url and '"editable": true' in direct_url.replace(" ", ""):
            return "editable"
    except (importlib_metadata.PackageNotFoundError, OSError, ValueError):
        pass

    prefix = sys.prefix.replace("\\", "/").lower()
    if "/pipx/" in prefix or prefix.endswith("/pipx"):
        return "pipx"
    return "pip"


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a dotted version into an int tuple for comparison.

    Tolerant of pre-release suffixes (e.g. "2.15.0rc1") by keeping only the
    leading numeric run of each dotted segment; returns (0,) on garbage so
    comparison never raises.
    """
    parts: list[int] = []
    for segment in v.split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _fetch_latest_version() -> str | None:
    """Return the latest version on PyPI, or None if unavailable/offline."""
    try:
        req = urllib.request.Request(_PYPI_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_PYPI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        version = data.get("info", {}).get("version")
        return str(version) if version else None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _upgrade_command(origin: str) -> list[str] | None:
    """The argv to upgrade for a given install origin (None = manual steps)."""
    if origin == "pipx":
        return ["pipx", "upgrade", PACKAGE]
    if origin == "pip":
        return [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE]
    return None  # editable: handled with guidance, never auto-run


@click.command()
@click.option("--check", is_flag=True, help="Only check whether a newer version is available; do not install.")
@click.pass_context
def upgrade(ctx: click.Context, check: bool) -> None:
    """Update deepr to the latest released version.

    Detects how deepr was installed (pipx, pip, or an editable source
    checkout) and runs the right update. Use --check to see whether a newer
    version exists without installing anything.
    """
    current = __version__
    click.echo(f"deepr {current}")

    latest = _fetch_latest_version()
    if latest is None:
        click.echo(
            f"Could not reach PyPI to check for updates (offline, or {PACKAGE} is not published yet).",
        )
        if check:
            return
    elif _version_tuple(latest) <= _version_tuple(current):
        print_success(f"Already up to date (latest on PyPI is {latest}).")
        return
    else:
        click.echo(f"A newer version is available: {latest}")

    if check:
        return

    origin = _detect_origin()

    if origin == "editable":
        click.echo("")
        click.echo("deepr is installed from a source checkout (editable). To update:")
        click.echo("  git -C <your deepr checkout> pull")
        click.echo("  pipx install -e .   # or: pip install -e .")
        return

    cmd = _upgrade_command(origin)
    if cmd is None:  # pragma: no cover - defensive; origin is pipx/pip here
        print_error("Could not determine how to upgrade this installation.")
        ctx.exit(1)

    click.echo(f"==> Upgrading via: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=False)  # noqa: S603 - argv built from fixed parts
    except FileNotFoundError:
        print_error(f"Upgrade tool not found: {cmd[0]}. Install it or upgrade manually.")
        ctx.exit(1)

    if result.returncode != 0:
        print_error(f"Upgrade command exited with status {result.returncode}.")
        ctx.exit(result.returncode)

    print_success("Upgrade complete. Run 'deepr --version' in a new shell to confirm.")
