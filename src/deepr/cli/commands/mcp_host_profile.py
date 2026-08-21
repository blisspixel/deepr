"""CLI for deterministic, offline MCP host-profile generation."""

from __future__ import annotations

from pathlib import Path

import click


@click.command("host-profile")
@click.argument("host")
@click.option("--host-version", help="Exact pinned host version. Defaults to the supported reference version.")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), help="Write canonical JSON here.")
@click.option("--force", is_flag=True, help="Replace an existing output file atomically.")
def host_profile(host: str, host_version: str | None, output: Path | None, force: bool) -> None:
    """Generate a reviewable local MCP profile without touching HOST."""
    from deepr.mcp.host_profile import build_host_profile, serialize_host_profile
    from deepr.utils.atomic_io import atomic_write_text

    try:
        payload = build_host_profile(host, host_version)
        text = serialize_host_profile(payload)
        if output is None:
            stream = click.get_binary_stream("stdout")
            stream.write(text.encode("utf-8"))
            stream.flush()
            return
        atomic_write_text(output, text, fsync=True, overwrite=force)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote MCP host profile: {output}")


def register_host_profile_command(mcp_group: click.Group) -> None:
    """Attach the host-profile command to the MCP command group."""
    mcp_group.add_command(host_profile)


__all__ = ["host_profile", "register_host_profile_command"]
