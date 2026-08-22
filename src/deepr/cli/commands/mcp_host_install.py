"""CLI: wire Deepr MCP into local coding hosts (Claude Code, project .mcp.json)."""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.command("install-host")
@click.option(
    "--project",
    "project_dir",
    type=click.Path(file_okay=False, path_type=str),
    default=".",
    show_default=True,
    help="Project directory that should receive .mcp.json",
)
@click.option(
    "--name",
    "server_name",
    default="deepr",
    show_default=True,
    help="MCP server name as seen by the host",
)
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=str),
    default=None,
    help="DEEPR_DATA_DIR for the host child process (default: portable expert home)",
)
@click.option(
    "--deepr-command",
    type=click.Path(dir_okay=False, path_type=str),
    default=None,
    help="Absolute path to deepr (or python) used by the host",
)
@click.option(
    "--python-module",
    is_flag=True,
    help="Force python -m deepr.mcp.server instead of deepr mcp serve",
)
@click.option(
    "--no-merge",
    is_flag=True,
    help="Overwrite .mcp.json instead of merging mcpServers",
)
@click.option(
    "--skip-claude-cli",
    is_flag=True,
    help="Only write .mcp.json; do not run claude mcp add",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the plan; write nothing and run nothing",
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
@click.option(
    "--brief/--no-brief",
    default=True,
    show_default=True,
    help="Also print the host agent brief after install",
)
@click.option(
    "--expert",
    "experts",
    multiple=True,
    help="Expert names to name in the brief (repeatable)",
)
def install_host(
    project_dir: str,
    server_name: str,
    data_dir: str | None,
    deepr_command: str | None,
    python_module: bool,
    no_merge: bool,
    skip_claude_cli: bool,
    dry_run: bool,
    as_json: bool,
    brief: bool,
    experts: tuple[str, ...],
) -> None:
    """Install Deepr MCP into a coding-host project ($0, no network, no model).

    Writes project ``.mcp.json`` with DEEPR_DATA_DIR so the host child process
    sees the same experts as the operator CLI. When the Claude Code CLI is on
    PATH, also runs ``claude mcp add ... -s local`` unless --skip-claude-cli.

    Hosts load MCP tools at session start. Restart Claude Code (or the host)
    after this command, then verify tools like deepr_list_experts exist.

    EXAMPLES:

        deepr mcp install-host --project .

        deepr mcp install-host --project C:\\GitHub\\NephMesh \\
          --expert "Meshtastic LoRa Mesh Automation" --json
    """
    from deepr.mcp.host_install import (
        HostInstallError,
        build_host_brief,
        plan_host_install,
        run_claude_mcp_add,
        write_mcp_json,
    )

    plan = plan_host_install(
        project_dir=project_dir,
        server_name=server_name,
        deepr_command=deepr_command,
        data_dir=data_dir,
        use_python_module=True if python_module else None,
    )
    result: dict = {
        "schema_version": plan.schema_version,
        "kind": plan.kind,
        "dry_run": dry_run,
        "plan": plan.to_dict(),
        "wrote_mcp_json": False,
        "claude_register": None,
        "cost_usd": 0.0,
        "restart_required": True,
    }

    if not dry_run:
        try:
            path = write_mcp_json(plan, merge=not no_merge)
        except HostInstallError as exc:
            raise click.ClickException(str(exc)) from exc
        result["wrote_mcp_json"] = True
        result["mcp_json_path"] = str(path)
        if not skip_claude_cli:
            result["claude_register"] = run_claude_mcp_add(plan)
        else:
            result["claude_register"] = {
                "attempted": False,
                "ok": False,
                "error": "skipped",
                "cost_usd": 0.0,
            }

    brief_text = ""
    if brief:
        brief_text = build_host_brief(
            experts=list(experts) if experts else None,
            data_dir=plan.data_dir,
            server_name=server_name,
        )
        result["brief"] = brief_text

    if as_json:
        # Keep brief out of JSON by default when huge? Include path pointer only if dry
        payload = dict(result)
        if brief and "brief" in payload:
            payload["brief_chars"] = len(brief_text)
            # still include brief for operator copy; no secrets
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    click.echo("Deepr MCP host install")
    click.echo(f"  Project:     {plan.project_dir}")
    click.echo(f"  Data dir:    {plan.data_dir}")
    click.echo(f"  Command:     {plan.deepr_command}")
    click.echo(f"  .mcp.json:   {plan.mcp_json_path}")
    if dry_run:
        click.echo("  Mode:        dry-run (nothing written)")
        click.echo(json.dumps(plan.mcp_json, indent=2))
    else:
        click.echo(f"  Wrote:       {result.get('mcp_json_path')}")
        _echo_claude_register(result.get("claude_register") or {})
    click.echo("")
    click.echo("Next:")
    click.echo("  1. Restart the host session (Claude Code / Desktop / Cursor).")
    click.echo("  2. Confirm deepr tools (deepr_list_experts) appear.")
    click.echo("  3. If missing, run: claude mcp list   (expect deepr Connected)")
    click.echo('  4. CLI fallback: deepr expert consult "..." --local --budget 0 -y')
    for note in plan.notes:
        click.echo(f"  note: {note}")
    if brief and brief_text:
        click.echo("")
        click.echo(brief_text)


def _echo_claude_register(reg: dict) -> None:
    if reg.get("attempted"):
        status = "ok" if reg.get("ok") else f"failed rc={reg.get('returncode')}"
        click.echo(f"  claude add:  {status}")
        if not reg.get("ok") and reg.get("stderr"):
            click.echo(f"  claude err:  {str(reg.get('stderr'))[:300]}")
    elif reg.get("error") == "skipped":
        click.echo("  claude add:  skipped")
    else:
        click.echo("  claude add:  claude CLI not found (config file only)")


@click.command("host-brief")
@click.option("--expert", "experts", multiple=True, help="Expert names to list (repeatable)")
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=str),
    default=None,
    help="Data dir to document in the brief",
)
@click.option("--output", type=click.Path(dir_okay=False, path_type=str), default=None)
@click.option("--json", "as_json", is_flag=True)
def host_brief(
    experts: tuple[str, ...],
    data_dir: str | None,
    output: str | None,
    as_json: bool,
) -> None:
    """Print a copy-paste brief for coding agents using local Deepr MCP ($0)."""
    from deepr.mcp.host_install import HOST_BRIEF_SCHEMA, build_host_brief, resolve_data_dir

    text = build_host_brief(
        experts=list(experts) if experts else None,
        data_dir=data_dir,
    )
    if as_json:
        payload = {
            "schema_version": HOST_BRIEF_SCHEMA,
            "kind": "deepr.mcp.host_brief",
            "data_dir": resolve_data_dir(explicit=data_dir),
            "experts": list(experts),
            "brief": text,
            "cost_usd": 0.0,
        }
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if output:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"Wrote host brief: {output}")
        return
    click.echo(text, nl=False)


def register_host_install_commands(mcp_group: click.Group) -> None:
    """Attach install-host and host-brief to the mcp click group."""
    mcp_group.add_command(install_host)
    mcp_group.add_command(host_brief)
