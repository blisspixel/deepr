"""`deepr expert sync-all` - library-wide maintenance in one capacity-aware pass.

Keeps the whole expert roster current as a fleet: each due expert is synced
under a per-expert budget within a total ceiling, on owned/prepaid capacity
first (the waterfall), skip-not-fail, holding the per-(expert, sync) overlap
lock so a roster pass never collides with a manual sync. The roster loop lives
in ``experts/sync_all.py``; this is the thin CLI wiring, reusing the same
backend construction and loop-run recording as ``expert sync``. Registered on
the ``expert`` group; experts.py imports this module at its bottom so the
decorator runs.
"""

from __future__ import annotations

import asyncio
import json as _json
import sys
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert

_STATUS_MARKERS = {
    "synced": "[green]synced[/green]",
    "no_changes": "[dim]no changes[/dim]",
    "not_due": "[dim]not due[/dim]",
    "skipped": "[yellow]skipped[/yellow]",
    "locked": "[yellow]locked[/yellow]",
    "failed": "[red]failed[/red]",
}


def _resolve_pass_backend(local: bool, api: bool) -> tuple[bool, str | None, str]:
    """Resolve one backend for the whole pass: ``(use_local, local_model, note)``.

    ``--api`` forces metered; ``--local`` forces local; otherwise the capacity
    waterfall picks local when an admitted model is available, else metered.
    Plan-quota auto-routing stays gated off (no trusted remaining-quota probe),
    so the auto result is local or metered.
    """
    if api:
        return False, None, ""
    use_local = local
    note = ""
    if not local:
        from deepr.backends.admission import TASK_CLASS_SYNC
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_SYNC)
        use_local = choice.is_local
        note = choice.reason if use_local else ""
    local_model = None
    if use_local:
        from deepr.backends.local import default_local_model

        local_model = default_local_model()
    return use_local, local_model, note


def _make_sync_one(*, use_local: bool, local_model: str | None, include_all: bool, scheduled: bool):
    """Per-expert sync closure, kept module-level so its branches do not inflate
    the command's cyclomatic complexity (ruff rolls a nested function into its
    parent). Builds the engine the same way ``expert sync`` does and records the
    per-expert loop run so ``deepr fleet status`` sees the pass."""
    from deepr.cli.commands.semantic.expert_maintenance import _record_completed_sync_loop
    from deepr.experts.maintenance_engine import build_sync_engine
    from deepr.experts.profile import ExpertStore

    async def sync_one(name: str, expert_budget: float, dry_run: bool) -> tuple[Any, str]:
        profile = ExpertStore().load(name)
        if profile is None:
            raise ValueError(f"expert not found: {name}")
        engine, capacity_source = build_sync_engine(profile, use_local=use_local, local_model=local_model)
        result = await engine.sync(budget=expert_budget, only_due=not include_all, dry_run=dry_run)
        if not dry_run:
            _record_completed_sync_loop(
                name,
                result,
                budget=expert_budget,
                scheduled=scheduled,
                sync_all=include_all,
                capacity_source=capacity_source,
            )
        return result, capacity_source

    return sync_one


def _emit_roster_wait(json_output: bool, detail: str) -> None:
    if json_output:
        click.echo(_json.dumps({"kind": "deepr.expert.sync_all", "status": "waiting_for_capacity", "detail": detail}))
        return
    print_warning("Scheduled sync-all is waiting for owned/prepaid capacity (no metered spend).")
    console.print(f"[dim]{detail}. Rerun without --scheduled to use the metered API.[/dim]")


def _metered_tier_defers(json_output: bool) -> bool:
    """Defer an auto metered pass when the monthly pool is drained.

    When the budget tier is LOCAL_ONLY/PAUSE_METERED, a roster pass that fell
    through to metered (no local capacity, no explicit --api) defers instead of
    spending - graceful degradation that protects the monthly pool. Returns True
    when it deferred (the caller should stop). The hard monthly cap in
    CostSafetyManager still backstops an explicit --api. See
    docs/design/budget-degradation.md.
    """
    from deepr.experts.cost_safety import get_cost_safety_manager
    from deepr.experts.spend_policy import METERED_OFF_TIERS, describe_tier, tier_from_manager

    manager = get_cost_safety_manager()
    if tier_from_manager(manager) not in METERED_OFF_TIERS:
        return False
    snapshot = describe_tier(manager)
    if json_output:
        click.echo(_json.dumps({"kind": "deepr.expert.sync_all", "status": "metered_deferred", **snapshot}))
        return True
    print_warning(
        f"Budget tier {snapshot['tier']} ({snapshot['drain_percent']}% of the monthly pool used): "
        "metered roster sync is off."
    )
    console.print("[dim]Use --local for $0 maintenance, wait for the monthly reset, or --api to override.[/dim]")
    return True


def _render_library_result(result: Any, json_output: bool) -> None:
    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
        return
    print_header("Library sync")
    for summary in result.summaries:
        line = f"  {_STATUS_MARKERS.get(summary.status, summary.status)}  [bold]{summary.expert}[/bold]"
        if summary.status == "synced":
            line += (
                f"  [dim](+{summary.absorbed} beliefs, {summary.flagged} contested, "
                f"${summary.cost:.3f} {summary.capacity_source})[/dim]"
            )
        elif summary.detail:
            line += f"  [dim]{summary.detail[:90]}[/dim]"
        console.print(line)
    console.print(
        f"\n[bold]{len(result.summaries)} experts[/bold] · {result.synced_experts} synced · "
        f"{result.failed_experts} failed · ${result.total_cost:.3f} spent"
    )


@expert.command(name="sync-all")
@click.option("--budget", "-b", type=float, default=5.0, show_default=True, help="Total ceiling for the roster pass.")
@click.option(
    "--per-expert-budget", type=float, default=0.50, show_default=True, help="Max spend per expert within the ceiling."
)
@click.option("--all", "include_all", is_flag=True, help="Include experts with no due subscriptions.")
@click.option("--dry-run", is_flag=True, help="Show what would sync; no research, no spend.")
@click.option("--local", is_flag=True, help="Force the local model for every expert.")
@click.option("--api", is_flag=True, help="Force the metered API (overrides the owned/prepaid waterfall).")
@click.option(
    "--scheduled", is_flag=True, help="Wait instead of spending metered when no owned/prepaid capacity exists."
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
@click.option("--json", "json_output", is_flag=True, help="Output JSON.")
def sync_all_cmd(
    budget: float,
    per_expert_budget: float,
    include_all: bool,
    dry_run: bool,
    local: bool,
    api: bool,
    scheduled: bool,
    yes: bool,
    json_output: bool,
) -> None:
    """Sync every due expert in one capacity-aware pass.

    Owned/prepaid capacity first, per-expert budgets within the total ceiling,
    skip-not-fail. Designed to run on a schedule (deepr fleet install-schedule)
    so the library self-maintains.

    EXAMPLES:
      deepr expert sync-all --dry-run
      deepr expert sync-all --local -y
      deepr expert sync-all --scheduled -y
    """
    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync_all import run_library_sync

    if local and api:
        print_error("Use only one of --local or --api.")
        sys.exit(2)

    names = [profile.name for profile in ExpertStore().list_all()]
    if not names:
        print_success("No experts yet. Create one with `deepr expert make`.")
        return

    use_local, local_model, selection_note = _resolve_pass_backend(local, api)
    owned_or_prepaid = use_local and local_model is not None

    if scheduled and not api and not owned_or_prepaid:
        _emit_roster_wait(json_output, "no owned/prepaid capacity is available")
        return
    if use_local and local_model is None:
        print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
        sys.exit(2)

    # Graceful degradation: an auto metered pass defers when the monthly pool is
    # drained (a dry run previews freely; an explicit --api overrides the soft
    # tier, the hard cap still applies).
    metered_auto = not use_local and not api
    if metered_auto and not dry_run and _metered_tier_defers(json_output):
        return

    if selection_note and not json_output:
        console.print(f"[dim]{selection_note}[/dim]")

    if not dry_run and not yes:
        cost_desc = "on the local model at $0" if use_local else f"up to ${budget:.2f} metered"
        if not click.confirm(f"Sync up to {len(names)} expert(s) {cost_desc}?", default=False):
            print_warning("Cancelled.")
            return

    sync_one = _make_sync_one(
        use_local=use_local, local_model=local_model, include_all=include_all, scheduled=scheduled
    )
    result = asyncio.run(
        run_library_sync(
            sync_one=sync_one,
            expert_names=names,
            budget=budget,
            per_expert_budget=per_expert_budget,
            only_due=not include_all,
            dry_run=dry_run,
        )
    )
    _render_library_result(result, json_output)
