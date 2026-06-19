"""Expert loop status command."""

from __future__ import annotations

import json as _json
import sys

import click

from deepr.cli.colors import console, print_error, print_header, print_success
from deepr.cli.commands.semantic.experts import expert


@expert.command(name="loop-status")
@click.argument("name")
@click.option("--limit", type=int, default=5, show_default=True, help="Maximum loop runs to show")
@click.option("--json", "json_output", is_flag=True, help="Emit loop status as JSON")
def loop_status(name: str, limit: int, json_output: bool):
    """Show durable loop-run status for an expert.

    Read-only and cost-$0. The records are append-only snapshots written by
    scheduled loop surfaces and future loop runners. A repeated run ID collapses
    to its latest snapshot.

    EXAMPLES:
      deepr expert loop-status "AI Strategy Expert"
      deepr expert loop-status "AI Strategy Expert" --json
    """
    from deepr.experts.loop_runs import ExpertLoopRunStore
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    runs = ExpertLoopRunStore(profile.name).list_runs(limit=limit)
    payload = {
        "expert_name": profile.name,
        "count": len(runs),
        "runs": [run.to_dict() for run in runs],
    }
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_header(f"Loop status: {profile.name}")
    if not runs:
        print_success("No loop runs recorded yet.")
        return

    for run in runs:
        stop = f", stop: {run.stop_reason.value}" if run.stop_reason else ""
        console.print(
            f"  [bold]{run.loop_type}[/bold] {run.status.value} "
            f"[dim]({run.run_id}, updated {run.updated_at.isoformat()}{stop})[/dim]"
        )
        console.print(f"    {run.goal}")
        if run.next_action:
            title = run.next_action.get("title") or run.next_action.get("status") or "next action"
            console.print(f"    [white]{title}[/white]")
