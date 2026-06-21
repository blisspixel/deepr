"""`deepr fleet` - roster-wide expert health (read-only, $0).

One glance at the whole expert fleet: which experts failed their last loop run,
which are waiting on capacity/confirmation, which have knowledge refresh due, and
what each cost on which capacity. Folds the per-expert ``loop_runs.jsonl`` and
``subscriptions.json`` already on disk - it runs no loop and spends nothing.

This is the agent-run health view; ``deepr capacity fleet`` is the separate
plan-quota CLI-backend view. Design: docs/design/expert-fleet.md.
"""

from __future__ import annotations

import json as _json
import sys

import click

from deepr.cli.colors import console, print_success, print_warning
from deepr.experts.fleet_status import build_fleet_status_rollup, fleet_needs_attention


@click.group(name="fleet")
def fleet() -> None:
    """Roster-wide expert fleet health (read-only, $0)."""


def _row_tag(row: dict) -> str:
    if row["attention"]:
        return "[red]FAILED[/red]"
    if row["waiting"]:
        return "[yellow]waiting[/yellow]"
    if row["refresh_due"]:
        return "[cyan]refresh due[/cyan]"
    if not row["has_runs"]:
        return "[dim]never run[/dim]"
    return "[green]ok[/green]"


def _row_detail(row: dict) -> str:
    last = row["last_run"]
    if not last:
        return "no runs recorded"
    return (
        f"{last['loop_type']} {last['status']} "
        f"(+{last['accepted_changes']}/-{last['rejected_changes']}, "
        f"${last['budget_spent']:.2f} {last['capacity_source']})"
    )


def _print_row_extras(row: dict) -> None:
    if row["refresh_due"]:
        topics = ", ".join(row["due_topics"][:5])
        more = "..." if row["refresh_due"] > 5 else ""
        console.print(f"      [cyan]refresh due:[/cyan] {row['refresh_due']} topic(s) - {topics}{more}")
    if row["waiting_next_action"]:
        console.print(f"      [yellow]waiting:[/yellow] {row['waiting_next_action'].get('title', '')}")
    if row["attention"] and row["last_failure"]:
        reason = row["last_failure"].get("failure_reason") or row["last_failure"].get("stop_reason") or ""
        console.print(f"      [red]last failure:[/red] {reason}")


def _render_human(payload: dict) -> None:
    summary = payload["summary"]
    rows = payload["experts"]

    if not rows:
        print_warning("No experts yet. Create one with `deepr expert make`.")
        return

    for row in rows:
        console.print(f"  {_row_tag(row)}  [bold]{row['expert']}[/bold]  [dim]{_row_detail(row)}[/dim]")
        _print_row_extras(row)

    console.print(
        f"\n[bold]{summary['experts']} experts[/bold] · "
        f"{summary['attention']} failed · {summary['waiting']} waiting · "
        f"{summary['refresh_due']} refresh-due · {summary['never_run']} never-run · "
        f"${summary['budget_spent_window_total']:.2f} spent (window)"
    )


@fleet.command(name="status")
@click.option("--json", "json_output", is_flag=True, help="Emit the versioned machine-readable payload.")
@click.option("--limit", default=20, show_default=True, help="Loop runs to summarize per expert.")
def status(json_output: bool, limit: int) -> None:
    """Show fleet health across all experts.

    Read-only and $0: folds each expert's loop-run history and refresh cadence.
    Exits non-zero when any expert's latest run failed, so a scheduler can run
    this as a cheap watchdog.

    EXAMPLES:
      deepr fleet status
      deepr fleet status --json
    """
    if limit < 1:
        print_warning("--limit must be positive.")
        sys.exit(2)

    payload = build_fleet_status_rollup(limit=limit)

    if json_output:
        click.echo(_json.dumps(payload, indent=2))
    else:
        _render_human(payload)
        if not fleet_needs_attention(payload) and payload["experts"]:
            print_success("No experts need attention.")

    if fleet_needs_attention(payload):
        sys.exit(1)
