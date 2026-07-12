"""Self-update command backed by versioned GitHub release wheels."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import metadata as importlib_metadata

import click

from deepr import __version__
from deepr.cli.colors import print_error, print_success

PACKAGE = "deepr-research"
_RELEASE_API_URL = "https://api.github.com/repos/blisspixel/deepr/releases/latest"
_RELEASE_ASSET_PREFIX = "https://github.com/blisspixel/deepr/releases/download/"
_RELEASE_TIMEOUT = 8


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """Install-relevant fields from the latest public GitHub release."""

    version: str
    tag: str
    wheel_url: str | None


def _detect_origin() -> str:
    """Best-effort detection of how deepr was installed.

    Returns one of: "editable" (source checkout), "pipx", or "pip".
    """
    try:
        dist = importlib_metadata.distribution(PACKAGE)
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            direct_metadata = json.loads(direct_url)
            if isinstance(direct_metadata, dict):
                directory_info = direct_metadata.get("dir_info")
                if isinstance(directory_info, dict) and directory_info.get("editable") is True:
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


def _release_from_payload(payload: object) -> ReleaseInfo | None:
    """Validate and reduce a GitHub release response."""
    if not isinstance(payload, dict):
        return None

    tag_value = payload.get("tag_name")
    if not isinstance(tag_value, str) or not tag_value.strip():
        return None
    tag = tag_value.strip()
    version = tag.removeprefix("v")
    if not version:
        return None
    expected_wheel_name = f"deepr_research-{version}-py3-none-any.whl"

    wheel_url: str | None = None
    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = asset.get("name")
            url = asset.get("browser_download_url")
            if (
                isinstance(name, str)
                and name == expected_wheel_name
                and isinstance(url, str)
                and url.startswith(_RELEASE_ASSET_PREFIX)
            ):
                wheel_url = url
                break

    return ReleaseInfo(version=version, tag=tag, wheel_url=wheel_url)


def _fetch_latest_release() -> ReleaseInfo | None:
    """Return the latest GitHub release, or None when unavailable or invalid."""
    try:
        request = urllib.request.Request(
            _RELEASE_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "deepr-upgrade",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=_RELEASE_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _release_from_payload(payload)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _upgrade_command(origin: str, wheel_url: str) -> list[str] | None:
    """The argv to upgrade for a given install origin (None = manual steps)."""
    if origin == "pipx":
        return ["pipx", "install", "--force", wheel_url]
    if origin == "pip":
        return [sys.executable, "-m", "pip", "install", "--upgrade", wheel_url]
    return None  # editable: handled with guidance, never auto-run


def _release_for_command(ctx: click.Context, *, check: bool) -> ReleaseInfo | None:
    """Load release metadata and handle a safe network failure."""
    release = _fetch_latest_release()
    if release is not None:
        return release

    click.echo(
        "Could not read the latest GitHub release (offline, rate limited, or invalid response).",
    )
    if check:
        return None
    print_error("No changes were made. Try again when GitHub Releases is reachable.")
    ctx.exit(1)


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

    release = _release_for_command(ctx, check=check)
    if release is None:
        return

    latest = release.version
    if _version_tuple(latest) <= _version_tuple(current):
        print_success(f"Already up to date (latest GitHub release is {release.tag}).")
        return

    click.echo(f"A newer version is available: {release.tag}")

    if check:
        if release.wheel_url is None:
            click.echo("That release does not include a supported Deepr wheel asset.")
        return

    origin = _detect_origin()

    if origin == "editable":
        click.echo("")
        click.echo("deepr is installed from a source checkout (editable). To update:")
        click.echo("  git -C <your deepr checkout> pull")
        click.echo("  pipx install -e .   # or: pip install -e .")
        return

    if release.wheel_url is None:
        print_error(
            f"GitHub release {release.tag} has no supported Deepr wheel asset. No changes were made.",
        )
        ctx.exit(1)

    cmd = _upgrade_command(origin, release.wheel_url)
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
