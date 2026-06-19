"""Expert gap routing command.

Extracted from experts.py so the oversized command module does not grow while
the route-gaps loop gains scheduler-aware capacity behavior.
"""

from __future__ import annotations

import asyncio
import json as _json
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert


def _quote_cli_arg(value: str) -> str:
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def _scheduled_gap_fill_wait_payload(profile_name: str, routes: list[Any], *, budget: float, top_n: int) -> dict:
    research_routes = [r for r in routes if r.instrument == "research"]
    est = min(sum(max(r.estimated_cost, 0.05) for r in research_routes), budget)
    return {
        "status": "waiting_for_capacity",
        "expert_name": profile_name,
        "detail": "scheduled gap fill is waiting for owned/prepaid capacity instead of using metered research",
        "estimated_metered_cost": round(est, 4),
        "routes": [r.to_dict() for r in routes],
        "next_actions": [
            {
                "status": "wait",
                "title": "Wait for cheap capacity",
                "detail": (
                    "Run without --scheduled to execute now behind the normal budget gate, "
                    "or rerun the scheduled job when a local or plan-quota gap-fill backend exists."
                ),
            },
            {
                "status": "dry_run",
                "title": "Preview without spend",
                "command": (
                    f"deepr expert route-gaps {_quote_cli_arg(profile_name)} --execute --dry-run --top {top_n}"
                ),
            },
        ],
    }


def _emit_scheduled_gap_fill_wait(profile_name: str, routes: list[Any], *, budget: float, top_n: int) -> None:
    payload = _scheduled_gap_fill_wait_payload(profile_name, routes, budget=budget, top_n=top_n)
    print_warning("Scheduled gap fill is waiting for cheap capacity.")
    console.print(f"[dim]{payload['detail']}.[/dim]")
    for action in payload["next_actions"]:
        console.print(f"  {action['status']}: {action['title']}")
        if action.get("detail"):
            console.print(f"      [dim]{action['detail']}[/dim]")
        if action.get("command"):
            console.print(f"      [dim]{action['command']}[/dim]")


@expert.command(name="route-gaps")
@click.argument("name")
@click.option("--top", "-t", "top_n", type=int, default=5, show_default=True, help="How many top gaps to route")
@click.option("--json", "json_output", is_flag=True, help="Emit the structured routes as JSON")
@click.option("--execute", "execute_fills", is_flag=True, help="Execute the research-route fills (budget-bounded)")
@click.option("--budget", "-b", type=float, default=2.0, show_default=True, help="Run budget ceiling for --execute")
@click.option("--dry-run", is_flag=True, help="With --execute: show what would run; no spend")
@click.option("--scheduled", is_flag=True, help="With --execute: wait instead of spending on recurring gap fills")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def route_gaps(
    name: str,
    top_n: int,
    json_output: bool,
    execute_fills: bool,
    budget: float,
    dry_run: bool,
    scheduled: bool,
    yes: bool,
):
    """Route an expert's knowledge gaps to the best instrument to fill each.

    Advisory by default (read-only, $0): maps each gap to recon
    (infrastructure), distillr (academic), primr (strategic), or general
    research, with availability and cost estimates.

    With --execute, the loop closes: the highest-value research-route
    fills actually run (ordered by value-per-dollar), findings absorb
    through the verification-gated pipeline, and budgets bound the sweep
    (per-gap inside a run ceiling, skip-not-fail). Specialist-instrument
    routes are deliberately DEFERRED with their command printed - paid
    multi-minute jobs must not start as a side effect of a sweep.

    EXAMPLES:
      deepr expert route-gaps "AI Strategy Expert"
      deepr expert route-gaps "AI Strategy Expert" --execute --dry-run
      deepr expert route-gaps "AI Strategy Expert" --execute --budget 1 -y
      deepr expert route-gaps "AI Strategy Expert" --execute --scheduled --json
    """
    from deepr.experts.gap_router import GapRouter
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    gaps = profile.get_manifest().top_gaps(top_n)
    routes = GapRouter().route(gaps)

    if execute_fills:
        from deepr.experts.gap_fill import GapFillEngine

        research_routes = [r for r in routes if r.instrument == "research"]
        if not routes:
            print_success("No open knowledge gaps to fill.")
            return
        if scheduled and not dry_run and research_routes:
            if json_output:
                payload = _scheduled_gap_fill_wait_payload(profile.name, routes, budget=budget, top_n=top_n)
                click.echo(_json.dumps(payload, indent=2))
                return
            _emit_scheduled_gap_fill_wait(profile.name, routes, budget=budget, top_n=top_n)
            return
        if not dry_run and not yes:
            est = min(sum(max(r.estimated_cost, 0.05) for r in research_routes), budget)
            if not click.confirm(
                f"Execute up to {len(research_routes)} research fill(s), estimated up to ${est:.2f} "
                f"(ceiling ${budget:.2f})? Specialist routes are deferred.",
                default=False,
            ):
                print_warning("Cancelled.")
                return

        engine = GapFillEngine(profile)
        result = asyncio.run(engine.execute(routes, budget=budget, top=top_n, dry_run=dry_run))

        if json_output:
            click.echo(_json.dumps(result.to_dict(), indent=2))
            return

        print_header(f"Gap fill: {name}")
        marker = {
            "filled": "[green]filled[/green]",
            "deferred": "[yellow]deferred[/yellow]",
            "would_fill": "[yellow]would fill[/yellow]",
            "skipped": "[yellow]skipped[/yellow]",
            "failed": "[red]failed[/red]",
        }
        for outcome in result.outcomes:
            line = f"  {marker.get(outcome.status, outcome.status)}  {outcome.topic}"
            if outcome.status == "filled":
                line += f"  [dim](+{outcome.absorbed} beliefs, {outcome.flagged} contested, ${outcome.cost:.3f})[/dim]"
            elif outcome.detail:
                line += f"  [dim]{outcome.detail[:100]}[/dim]"
            console.print(line)
        if not dry_run:
            console.print(f"\nTotal cost: ${result.total_cost:.3f}")
            if any(outcome.flagged for outcome in result.outcomes):
                print_warning(f"Contested beliefs recorded. Review: deepr expert contested '{name}'")
        return

    if json_output:
        click.echo(_json.dumps({"expert_name": profile.name, "routes": [r.to_dict() for r in routes]}, indent=2))
        return

    print_header(f"Gap routing: {profile.name}")
    if not routes:
        print_success("No open knowledge gaps to route.")
        return

    color = {"recon": "cyan", "distillr": "magenta", "primr": "yellow", "research": "white"}
    for route in routes:
        avail = "" if route.available else " [red](not installed)[/red]"
        inst = color.get(route.instrument, "white")
        console.print(
            f"[bold {inst}]{route.instrument}[/bold {inst}]{avail}  "
            f"~${route.estimated_cost:.2f}  [dim]{route.topic}[/dim]"
        )
        console.print(f"    {route.rationale}")
        console.print(f"    [white]{route.suggestion}[/white]")
        console.print()
