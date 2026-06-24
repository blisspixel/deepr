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
from pathlib import Path

import click

from deepr.cli.colors import console, print_error, print_success, print_warning
from deepr.experts.fleet_schedule import ScheduleSpec, render_recipe, resolve_platform
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


def _render_recipe_to_stdout(recipe) -> None:
    for filename, content in recipe.files.items():
        console.print(f"[bold]# {filename}[/bold]")
        click.echo(content)
    if recipe.inline:
        console.print("[bold]# crontab line[/bold]")
        click.echo(recipe.inline)
    console.print("\n[bold]Install[/bold]")
    console.print(recipe.instructions)


@fleet.command(name="install-schedule")
@click.option(
    "--platform",
    type=click.Choice(["auto", "windows", "cron", "systemd"]),
    default="auto",
    show_default=True,
    help="Host scheduler to target (auto detects this OS).",
)
@click.option(
    "--command",
    default="deepr fleet status",
    show_default=True,
    help="The deepr command to run on the schedule.",
)
@click.option("--cadence", type=click.Choice(["hourly", "daily"]), default="daily", show_default=True)
@click.option("--at", default="03:00", show_default=True, help="HH:MM local time (daily cadence).")
@click.option("--name", default="deepr-fleet", show_default=True, help="Scheduled task/unit name.")
@click.option(
    "--jitter-minutes",
    type=int,
    default=15,
    show_default=True,
    help="Random start spread so a roster does not stampede a rate-limited backend.",
)
@click.option(
    "--output",
    type=click.Path(file_okay=False),
    default=None,
    help="Write recipe files to this directory instead of printing them.",
)
def install_schedule(
    platform: str,
    command: str,
    cadence: str,
    at: str,
    name: str,
    jitter_minutes: int,
    output: str | None,
) -> None:
    """Emit a host-scheduler recipe to run a deepr command on a cadence.

    This does not install anything - registering a scheduled task is a
    privileged, host-specific step you run yourself. It prints (or with --output
    writes) the recipe plus the exact install command. The recipe is tuned for
    catch-up, not punctuality: a laptop asleep at the scheduled time runs the
    job on its next wake, and Deepr's verbs are idempotent so nothing
    double-spends.

    EXAMPLES:
      deepr fleet install-schedule
      deepr fleet install-schedule --command "deepr expert sync 'AI Policy Expert' --scheduled -y"
      deepr fleet install-schedule --platform systemd --cadence daily --at 02:30 --output ./schedule
    """
    try:
        target = resolve_platform(platform, system=sys.platform)
        spec = ScheduleSpec(command=command, cadence=cadence, at=at, name=name, jitter_minutes=jitter_minutes)
        recipe = render_recipe(target, spec)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    if output:
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for filename, content in recipe.files.items():
            (out_dir / filename).write_text(content, encoding="utf-8")
            written.append(filename)
        if recipe.inline:
            (out_dir / f"{name}.cron").write_text(recipe.inline + "\n", encoding="utf-8")
            written.append(f"{name}.cron")
        print_success(f"Wrote {', '.join(written)} to {out_dir}")
        console.print(recipe.instructions)
        return

    _render_recipe_to_stdout(recipe)
