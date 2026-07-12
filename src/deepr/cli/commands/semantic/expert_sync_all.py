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
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import click

from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityUnavailableReason
from deepr.cli.colors import console, print_error, print_header, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.grounding_support import PLAN_BACKEND_CHOICES

_STATUS_MARKERS = {
    "synced": "[green]synced[/green]",
    "no_changes": "[dim]no changes[/dim]",
    "not_due": "[dim]not due[/dim]",
    "skipped": "[yellow]skipped[/yellow]",
    "locked": "[yellow]locked[/yellow]",
    "failed": "[red]failed[/red]",
}


@dataclass(frozen=True)
class _PassBackend:
    use_local: bool = False
    local_model: str | None = None
    prefer_profile_model: bool = False
    use_plan: bool = False
    plan_adapter: Any | None = None
    plan_model: str | None = None
    note: str = ""

    @property
    def owned_or_prepaid(self) -> bool:
        if self.use_local:
            return self.local_model is not None
        if self.use_plan and self.plan_adapter is not None:
            return not bool(getattr(self.plan_adapter, "metered_at_margin", False))
        return False


def _plan_backend_choice(plan: str, plan_model: str | None, *, note: str | None = None) -> _PassBackend:
    from deepr.backends.plan_quota import get_adapter

    adapter = get_adapter(plan)
    if adapter is None:
        raise ValueError(f"Unknown plan-quota backend: {plan}")
    return _PassBackend(
        use_plan=True,
        plan_adapter=adapter,
        plan_model=plan_model,
        note=note or "",
    )


def _resolve_pass_backend(local: bool, api: bool, plan: str | None, plan_model: str | None) -> _PassBackend:
    """Resolve one backend for the whole pass.

    ``--api`` forces metered; ``--local`` forces local; ``--plan`` forces a
    non-metered plan CLI through the safety gate. Otherwise the capacity
    waterfall picks local when an admitted model is available, then an admitted
    plan backend only when trusted quota headroom has been observed, else
    metered.
    """
    if api:
        return _PassBackend()
    if plan:
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(plan)
        if not choice.is_plan_quota or choice.plan_backend_id is None:
            raise ValueError(choice.reason)
        return _plan_backend_choice(choice.plan_backend_id, plan_model, note=choice.reason)
    if local:
        from deepr.backends.local import default_local_model

        return _PassBackend(
            use_local=True,
            local_model=default_local_model(),
            prefer_profile_model=True,
        )

    note = ""
    local_model = None
    use_local = False
    use_plan = False
    plan_backend_id = None
    if not local:
        from deepr.backends.admission import TASK_CLASS_SYNC
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_SYNC)
        use_local = choice.is_local
        use_plan = getattr(choice, "is_plan_quota", False)
        plan_backend_id = getattr(choice, "plan_backend_id", None)
        if use_local or use_plan:
            note = choice.reason
        if use_local:
            local_model = choice.model
    if use_plan and plan_backend_id:
        return _plan_backend_choice(plan_backend_id, plan_model=None, note=note)
    if use_local:
        from deepr.backends.local import default_local_model

        return _PassBackend(use_local=True, local_model=local_model or default_local_model(), note=note)
    return _PassBackend(note=note)


def _pass_capacity_source(backend: _PassBackend) -> str:
    if backend.use_local:
        return "local"
    if backend.use_plan and backend.plan_adapter is not None:
        return f"plan_quota:{backend.plan_adapter.backend_id}"
    return "api_metered"


def _sync_all_retry_argv(
    *,
    budget: float,
    per_expert_budget: float,
    include_all: bool,
    local: bool,
    api: bool,
    plan: str | None,
    plan_model: str | None,
    yes: bool,
    json_output: bool,
) -> list[str]:
    argv = [
        "deepr",
        "expert",
        "sync-all",
        "--scheduled",
        "--budget",
        f"{budget:g}",
        "--per-expert-budget",
        f"{per_expert_budget:g}",
    ]
    if include_all:
        argv.append("--all")
    if local:
        argv.append("--local")
    elif api:
        argv.append("--api")
    elif plan:
        argv.extend(["--plan", plan])
    if plan_model:
        argv.extend(["--plan-model", plan_model])
    if yes:
        argv.append("--yes")
    if json_output:
        argv.append("--json")
    return argv


def _make_sync_one(*, backend: _PassBackend, include_all: bool, scheduled: bool):
    """Per-expert sync closure, kept module-level so its branches do not inflate
    the command's cyclomatic complexity (ruff rolls a nested function into its
    parent). Builds the engine the same way ``expert sync`` does and records the
    per-expert loop run so ``deepr fleet status`` sees the pass."""
    from deepr.cli.commands.semantic.expert_maintenance import _record_completed_sync_loop
    from deepr.cli.commands.semantic.expert_sync_support import (
        _record_failed_sync_execution,
        _record_running_sync_loop,
    )
    from deepr.experts.loop_runs import new_loop_run_id
    from deepr.experts.maintenance_engine import build_sync_engine
    from deepr.experts.profile import ExpertStore

    async def sync_one(name: str, expert_budget: float, dry_run: bool) -> tuple[Any, str]:
        profile = ExpertStore().load(name)
        if profile is None:
            raise ValueError(f"expert not found: {name}")
        local_model = backend.local_model
        if backend.use_local and backend.prefer_profile_model:
            from deepr.backends.local import resolve_local_maintenance_model

            local_model = resolve_local_maintenance_model(profile)
        capacity_source = _pass_capacity_source(backend)
        run_id = new_loop_run_id()
        started_at = datetime.now(UTC)
        if not dry_run:
            _record_running_sync_loop(
                name,
                run_id=run_id,
                started_at=started_at,
                budget=expert_budget,
                scheduled=scheduled,
                sync_all=include_all,
                capacity_source=capacity_source,
                profile=profile,
            )
        try:
            engine, capacity_source = build_sync_engine(
                profile,
                use_local=backend.use_local,
                local_model=local_model,
                use_plan=backend.use_plan,
                plan_adapter=backend.plan_adapter,
                plan_model=backend.plan_model,
            )
            result = await engine.sync(budget=expert_budget, only_due=not include_all, dry_run=dry_run)
        except Exception as exc:
            if not dry_run:
                _record_failed_sync_execution(
                    name,
                    run_id=run_id,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    budget=expert_budget,
                    scheduled=scheduled,
                    sync_all=include_all,
                    capacity_source=capacity_source,
                    exception=exc,
                    profile=profile,
                )
            raise
        if not dry_run:
            finished_at = datetime.now(UTC)
            _record_completed_sync_loop(
                name,
                result,
                budget=expert_budget,
                scheduled=scheduled,
                sync_all=include_all,
                capacity_source=capacity_source,
                profile=profile,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
            )
        return result, capacity_source

    return sync_one


def _emit_roster_wait(json_output: bool, detail: str) -> None:
    if json_output:
        click.echo(_json.dumps({"kind": "deepr.expert.sync_all", "status": "waiting_for_capacity", "detail": detail}))
        return
    print_warning("Scheduled sync-all is waiting for owned/prepaid capacity (no metered spend).")
    console.print(f"[dim]{detail}. Rerun without --scheduled to use the metered API.[/dim]")


def _experts_with_sync_work(expert_names: list[str], *, include_all: bool) -> list[str]:
    """Return roster members whose selected subscription set is non-empty."""
    from deepr.experts.sync import SubscriptionStore

    pending: list[str] = []
    for name in expert_names:
        subscriptions = SubscriptionStore(name)
        targets = subscriptions.subscriptions if include_all else subscriptions.due()
        if targets:
            pending.append(name)
    return pending


def _local_models_for_wait(expert_names: list[str], backend: _PassBackend) -> dict[str, str]:
    from deepr.backends.local import resolve_local_maintenance_model
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    resolved_models: dict[str, str] = {}
    for expert_name in expert_names:
        profile = store.load(expert_name)
        if profile is None:
            continue
        resolved = resolve_local_maintenance_model(profile) if backend.prefer_profile_model else backend.local_model
        if resolved:
            resolved_models[expert_name] = resolved
    return resolved_models


def _emit_roster_local_busy_wait(
    expert_names: list[str],
    *,
    observation: LocalCapacityObservation,
    per_expert_budget: float,
    json_output: bool,
    command_argv: list[str],
    local_models: dict[str, str],
) -> None:
    """Record one durable busy wait per expert without constructing an engine."""
    from deepr.experts.scheduled_local_capacity import record_scheduled_local_capacity_wait

    observed_at = datetime.now(UTC)
    waits = [
        record_scheduled_local_capacity_wait(
            expert_name=name,
            loop_type="sync",
            goal=f"Sync due subscriptions for {name}",
            observation=observation,
            command_argv=command_argv,
            budget_limit=per_expert_budget,
            now=observed_at,
            capacity_source="local",
            backend_profile_id=local_models.get(name, ""),
        )
        for name in expert_names
    ]
    earliest = min(waits, key=lambda wait: wait.retry_at)
    payload = {
        "kind": "deepr.expert.sync_all",
        "status": "waiting_for_capacity",
        "detail": "scheduled roster sync found meaningful local GPU contention",
        "capacity_unavailable_reason": LocalCapacityUnavailableReason.GPU_BUSY.value,
        "local_capacity": observation.to_dict(),
        "retry_after_seconds": earliest.retry_after_seconds,
        "retry_at": earliest.retry_at.isoformat(),
        "requested_operation": {
            "command_argv": list(command_argv),
            "capacity_source": "local",
            "backend_profile_id": "",
            "backend_profile_ids": dict(local_models),
        },
        "waiting_experts": [wait.to_dict() for wait in waits],
    }
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return
    print_warning("Scheduled sync-all is waiting because local GPU capacity is busy.")
    console.print(f"[dim]{observation.detail}.[/dim]")
    console.print(f"[dim]Try again at or after {earliest.retry_at.isoformat()}; no fallback was dispatched.[/dim]")


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


def _validate_sync_all_flags(*, local: bool, api: bool, plan: str | None, plan_model: str | None) -> None:
    if sum(bool(x) for x in (local, api, plan)) > 1:
        raise ValueError("Use only one of --local, --api, or --plan.")
    if plan_model and not plan:
        raise ValueError("Use --plan-model only with --plan.")


def _emit_backend_notes(backend: _PassBackend, *, json_output: bool) -> None:
    if json_output:
        return
    if backend.note:
        console.print(f"[dim]{backend.note}[/dim]")
    if backend.use_plan and backend.plan_adapter is not None and backend.plan_adapter.tos_note:
        print_warning(backend.plan_adapter.tos_note)


def _confirm_sync_all(*, backend: _PassBackend, budget: float, expert_count: int) -> bool:
    if backend.use_local:
        cost_desc = "on the local model at $0"
    elif backend.use_plan and backend.plan_adapter is not None:
        cost_desc = f"via {backend.plan_adapter.display_name} at $0 at the margin"
    else:
        cost_desc = f"up to ${budget:.2f} metered"
    return click.confirm(f"Sync up to {expert_count} expert(s) {cost_desc}?", default=False)


def _sync_all_cancelled(
    *,
    dry_run: bool,
    yes: bool,
    backend: _PassBackend,
    budget: float,
    expert_count: int,
) -> bool:
    if dry_run or yes:
        return False
    if _confirm_sync_all(backend=backend, budget=budget, expert_count=expert_count):
        return False
    print_warning("Cancelled.")
    return True


def _scheduled_local_busy_wait(
    names: list[str],
    *,
    scheduled: bool,
    dry_run: bool,
    include_all: bool,
    backend: _PassBackend,
    per_expert_budget: float,
    json_output: bool,
    command_argv: list[str],
) -> bool:
    from deepr.backends.local_capacity import LocalCapacityState, probe_local_gpu_occupancy

    if not scheduled or dry_run or not backend.use_local:
        return False
    pending_local_experts = _experts_with_sync_work(names, include_all=include_all)
    local_capacity = probe_local_gpu_occupancy() if pending_local_experts else None
    if local_capacity is None or local_capacity.state != LocalCapacityState.BUSY:
        return False
    _emit_roster_local_busy_wait(
        pending_local_experts,
        observation=local_capacity,
        per_expert_budget=per_expert_budget,
        json_output=json_output,
        command_argv=command_argv,
        local_models=_local_models_for_wait(pending_local_experts, backend),
    )
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
    "--plan",
    "plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Force a non-metered plan-quota CLI backend for every expert. See: deepr capacity",
)
@click.option("--plan-model", "plan_model", default=None, help="Model to pass to the plan-quota CLI.")
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
    plan: str | None,
    plan_model: str | None,
    scheduled: bool,
    yes: bool,
    json_output: bool,
) -> None:
    """Sync every due expert in one capacity-aware pass.

    Owned/prepaid capacity first, per-expert budgets within the total ceiling,
    skip-not-fail. Designed to run on a schedule (deepr fleet install-schedule)
    so the library self-maintains. On a --scheduled run, set DEEPR_HEARTBEAT_URL
    to ping a dead-man's-switch (healthchecks.io) so you are alerted if a
    scheduled pass ever silently does not run.

    EXAMPLES:
      deepr expert sync-all --dry-run
      deepr expert sync-all --local -y
      deepr expert sync-all --plan codex -y
      deepr expert sync-all --scheduled -y
    """
    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync_all import run_library_sync

    try:
        _validate_sync_all_flags(local=local, api=api, plan=plan, plan_model=plan_model)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    names = [profile.name for profile in ExpertStore().list_all()]
    if not names:
        print_success("No experts yet. Create one with `deepr expert make`.")
        return

    try:
        backend = _resolve_pass_backend(local, api, plan, plan_model)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    retry_command_argv = _sync_all_retry_argv(
        budget=budget,
        per_expert_budget=per_expert_budget,
        include_all=include_all,
        local=local,
        api=api,
        plan=plan,
        plan_model=plan_model,
        yes=yes,
        json_output=json_output,
    )

    if scheduled and not api and not backend.owned_or_prepaid:
        _emit_roster_wait(json_output, "no owned/prepaid capacity is available")
        return
    if backend.use_local and backend.local_model is None:
        print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
        sys.exit(2)
    if _scheduled_local_busy_wait(
        names,
        scheduled=scheduled,
        dry_run=dry_run,
        include_all=include_all,
        backend=backend,
        per_expert_budget=per_expert_budget,
        json_output=json_output,
        command_argv=retry_command_argv,
    ):
        return

    # Graceful degradation: an auto metered pass defers when the monthly pool is
    # drained (a dry run previews freely; an explicit --api overrides the soft
    # tier, the hard cap still applies).
    metered_auto = not backend.use_local and not backend.use_plan and not api
    if metered_auto and not dry_run and _metered_tier_defers(json_output):
        return

    _emit_backend_notes(backend, json_output=json_output)

    if _sync_all_cancelled(
        dry_run=dry_run,
        yes=yes,
        backend=backend,
        budget=budget,
        expert_count=len(names),
    ):
        return

    sync_one = _make_sync_one(backend=backend, include_all=include_all, scheduled=scheduled)
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
    if scheduled and not dry_run:
        # Off-box liveness: tell the dead-man's-switch the scheduled pass ran, so
        # the operator is alerted if it ever silently does not (the laptop never
        # woke up). Opt-in via DEEPR_HEARTBEAT_URL; best-effort, never fails here.
        from deepr.experts.heartbeat import send_heartbeat

        send_heartbeat(success=result.failed_experts == 0)
    _render_library_result(result, json_output)
