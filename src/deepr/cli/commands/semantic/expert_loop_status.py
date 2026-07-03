"""Expert loop status command."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click
from rich.markup import escape

from deepr.cli.colors import console, print_error, print_header, print_success
from deepr.cli.commands.semantic.experts import expert


def _print_capacity_outlook(outlook: dict[str, Any]) -> None:
    """Render the non-probing $0/prepaid capacity outlook per maintenance task class.

    Model and backend identifiers come from the admission ledger (operator data),
    so they are escaped before printing to a markup-enabled console: an unusual
    tag must never be swallowed as Rich markup or crash the human-readable view.
    """
    task_classes = outlook.get("task_classes") or {}
    if not task_classes:
        return
    console.print("[dim]Next-run capacity (admitted, not a live probe):[/dim]")
    for task_class, entry in task_classes.items():
        rungs = []
        if entry.get("local_capacity_admitted"):
            rungs.append(f"$0 local ({escape(', '.join(entry.get('admitted_local_models') or []))})")
        if entry.get("plan_capacity_admitted"):
            rungs.append(f"prepaid plan ({escape(', '.join(entry.get('admitted_plan_backends') or []))})")
        summary = ", ".join(rungs) if rungs else "metered budget (no cheap capacity admitted)"
        console.print(f"  [bold]{escape(task_class)}[/bold]: {summary}")


@expert.command(name="loop-status")
@click.argument("name")
@click.option("--limit", type=click.IntRange(min=1), default=5, show_default=True, help="Maximum loop runs to show")
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
    from deepr.experts.loop_status_rollup import build_loop_status_rollup
    from deepr.experts.profile import ExpertStore

    profile = ExpertStore().load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    payload = build_loop_status_rollup(profile.name, limit=limit)
    runs = payload["runs"]
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_header(f"Loop status: {profile.name}")
    _print_capacity_outlook(payload.get("next_run_outlook") or {})
    if not runs:
        print_success("No loop runs recorded yet.")
        return

    for run in runs:
        stop_reason = run.get("stop_reason")
        stop = f", stop: {stop_reason}" if stop_reason else ""
        console.print(
            f"  [bold]{run['loop_type']}[/bold] {run['status']} "
            f"[dim]({run['run_id']}, updated {run['updated_at']}{stop})[/dim]"
        )
        console.print(f"    {run['goal']}")
        next_action = run.get("next_action") or {}
        if next_action:
            title = next_action.get("title") or next_action.get("status") or "next action"
            console.print(f"    [white]{title}[/white]")
