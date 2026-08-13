"""`deepr expert sync-all` - capacity-aware roster maintenance.

The domain loop lives in ``experts/sync_all.py``. This adapter resolves one
backend, keeps previews read-only, and records each executed expert pass.
"""

from __future__ import annotations

import asyncio
import json as _json
import math
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import click
from rich.markup import escape

from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityUnavailableReason
from deepr.cli.colors import console, print_error, print_header, print_success, print_warning
from deepr.cli.commands.semantic.expert_sync_heartbeat import (
    heartbeat_evidence as _heartbeat_evidence,
)
from deepr.cli.commands.semantic.expert_sync_heartbeat import (
    render_heartbeat_evidence as _render_heartbeat_evidence,
)
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.grounding_support import PLAN_BACKEND_CHOICES
from deepr.experts.metered_mutation_gate import (
    MeteredExpertMutationDisabledError,
    require_metered_expert_mutation,
)
from deepr.experts.sync_all import ExpertSyncSummary, LibrarySyncResult, run_library_sync

_STATUS_MARKERS = {
    "synced": "[green]synced[/green]",
    "partial_failure": "[red]partial failure[/red]",
    "would_sync": "[cyan]would sync[/cyan]",
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


@dataclass(frozen=True)
class _RosterPreflight:
    names: tuple[str, ...]
    pending_names: tuple[str, ...]
    subscription_stores: dict[str, Any]
    profile_errors: int = 0
    subscription_errors: int = 0

    @property
    def has_storage_errors(self) -> bool:
        return bool(self.profile_errors or self.subscription_errors)


def _terminal_safe_text(value: str) -> str:
    """Make stored text single-line and literal before passing it to Rich."""
    visible = "".join(character if character.isprintable() else ascii(character)[1:-1] for character in value)
    return escape(visible)


def _cli_library_payload(result: LibrarySyncResult) -> dict[str, Any]:
    payload = result.to_dict()
    if result.dry_run:
        payload["state_changes"] = 0
    return payload


def _terminal_payload(
    *,
    started_at: datetime,
    status: str,
    exit_code: int,
    expert_count: int,
    detail: str,
    heartbeat: dict[str, Any],
    dry_run: bool,
    **extra: Any,
) -> dict[str, Any]:
    """Build one additive terminal envelope from the public library contract."""
    payload = _cli_library_payload(LibrarySyncResult(started_at=started_at, dry_run=dry_run))
    payload.update(
        status=status,
        exit_code=exit_code,
        roster_experts=expert_count,
        detail=detail,
        heartbeat=heartbeat,
        **extra,
    )
    return payload


def _inspect_roster(*, include_all: bool, now: datetime) -> _RosterPreflight:
    """Read roster and subscription state without creating or migrating storage."""
    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync import SubscriptionStore

    try:
        profiles = ExpertStore(create=False).list_all()
    except (OSError, ValueError):
        return _RosterPreflight((), (), {}, profile_errors=1)

    names = tuple(profile.name for profile in profiles)
    profile_errors = len(getattr(profiles, "errors", ()))
    pending: list[str] = []
    stores: dict[str, Any] = {}
    subscription_errors = 0
    for name in names:
        try:
            subscriptions = SubscriptionStore(name)
            if getattr(subscriptions, "load_failed", False):
                subscription_errors += 1
                continue
            targets = subscriptions.subscriptions if include_all else subscriptions.due(now)
        except (OSError, OverflowError, TypeError, ValueError):
            subscription_errors += 1
            continue
        stores[name] = subscriptions
        if targets:
            pending.append(name)
    return _RosterPreflight(names, tuple(pending), stores, profile_errors, subscription_errors)


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
    scheduled: bool,
    yes: bool,
    json_output: bool,
) -> list[str]:
    argv = [
        "deepr",
        "expert",
        "sync-all",
        "--budget",
        f"{budget:g}",
        "--per-expert-budget",
        f"{per_expert_budget:g}",
    ]
    if scheduled:
        argv.append("--scheduled")
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


def _make_sync_one(
    *,
    backend: _PassBackend,
    preflight: _RosterPreflight,
    include_all: bool,
    scheduled: bool,
    snapshot_at: datetime,
) -> Callable[[str, float, bool], Awaitable[tuple[Any, str]]]:
    """Build pure previews or recorded executions from the requested mode."""
    from deepr.cli.commands.semantic.expert_maintenance import _record_completed_sync_loop
    from deepr.cli.commands.semantic.expert_sync_support import (
        _record_failed_sync_execution,
        _record_running_sync_loop,
    )
    from deepr.experts.loop_runs import new_loop_run_id
    from deepr.experts.maintenance_engine import build_sync_engine
    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync_support import build_sync_preview

    async def sync_one(name: str, expert_budget: float, dry_run: bool) -> tuple[Any, str]:
        capacity_source = _pass_capacity_source(backend)
        if dry_run:
            result = build_sync_preview(
                name,
                preflight.subscription_stores[name],
                budget=expert_budget,
                only_due=not include_all,
                now=snapshot_at,
            )
            return result, capacity_source
        profile = ExpertStore().load(name)
        if profile is None:
            raise ValueError(f"expert not found: {name}")
        local_model = backend.local_model
        if backend.use_local and backend.prefer_profile_model:
            from deepr.backends.local import resolve_local_maintenance_model

            local_model = resolve_local_maintenance_model(profile)
        run_id = new_loop_run_id()
        started_at = datetime.now(UTC)
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


def _emit_roster_wait(
    json_output: bool,
    detail: str,
    *,
    started_at: datetime,
    expert_count: int,
    scheduled: bool,
    dry_run: bool,
) -> None:
    heartbeat = _heartbeat_evidence(scheduled=scheduled, dry_run=dry_run, success=False)
    if json_output:
        payload = _terminal_payload(
            started_at=started_at,
            status="waiting_for_capacity",
            exit_code=0,
            expert_count=expert_count,
            detail=detail,
            heartbeat=heartbeat,
            dry_run=dry_run,
            next_action={"kind": "inspect_capacity", "command_argv": ["deepr", "capacity", "next"]},
        )
        click.echo(_json.dumps(payload, indent=2))
        return
    print_header("Library sync preview" if dry_run else "Library sync")
    print_warning("Scheduled sync-all is waiting for owned/prepaid capacity (no metered spend).")
    preview_note = " Preview only: no research, spend, or expert files changed." if dry_run else ""
    console.print(f"[dim]{detail}. Inspect current options with: deepr capacity next.{preview_note}[/dim]")
    _render_heartbeat_evidence(heartbeat, json_output=json_output)


def _local_models_for_wait(expert_names: list[str], backend: _PassBackend) -> dict[str, str]:
    from deepr.backends.local import resolve_local_maintenance_model
    from deepr.experts.profile import ExpertStore

    store = ExpertStore(create=False)
    resolved_models: dict[str, str] = {}
    for expert_name in expert_names:
        profile = store.load(expert_name, persist_migration=False)
        if profile is None:
            continue
        resolved = resolve_local_maintenance_model(profile) if backend.prefer_profile_model else backend.local_model
        if resolved:
            resolved_models[expert_name] = resolved
    return resolved_models


def _emit_roster_local_busy_wait(
    expert_names: list[str],
    *,
    started_at: datetime,
    expert_count: int,
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
    detail = "scheduled roster sync found meaningful local GPU contention"
    heartbeat = _heartbeat_evidence(scheduled=True, dry_run=False, success=False)
    payload = _terminal_payload(
        started_at=started_at,
        status="waiting_for_capacity",
        exit_code=0,
        expert_count=expert_count,
        detail=detail,
        heartbeat=heartbeat,
        dry_run=False,
        capacity_unavailable_reason=LocalCapacityUnavailableReason.GPU_BUSY.value,
        local_capacity=observation.to_dict(),
        retry_after_seconds=earliest.retry_after_seconds,
        retry_at=earliest.retry_at.isoformat(),
        requested_operation={
            "command_argv": list(command_argv),
            "capacity_source": "local",
            "backend_profile_id": "",
            "backend_profile_ids": dict(local_models),
        },
        waiting_experts=[wait.to_dict() for wait in waits],
    )
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return
    print_warning("Scheduled sync-all is waiting because local GPU capacity is busy.")
    console.print(f"[dim]{observation.detail}.[/dim]")
    console.print(f"[dim]Try again at or after {earliest.retry_at.isoformat()}; no fallback was dispatched.[/dim]")
    _render_heartbeat_evidence(heartbeat, json_output=json_output)


def _metered_tier_defers(
    json_output: bool,
    *,
    started_at: datetime,
    expert_count: int,
    scheduled: bool,
    dry_run: bool,
) -> bool:
    """Defer an auto metered pass when the monthly pool is drained.

    When the budget tier is LOCAL_ONLY/PAUSE_METERED, a roster pass that fell
    through to metered (no local capacity, no explicit --api) defers instead of
    spending - graceful degradation that protects the monthly pool. Returns True
    when it deferred (the caller should stop). Metered expert mutation remains
    independently gated for both automatic and explicit API selection. See
    docs/design/budget-degradation.md.
    """
    from deepr.experts.cost_safety import get_cost_safety_manager
    from deepr.experts.spend_policy import METERED_OFF_TIERS, describe_tier, tier_from_manager

    manager = get_cost_safety_manager()
    if tier_from_manager(manager) not in METERED_OFF_TIERS:
        return False
    snapshot = describe_tier(manager)
    heartbeat = _heartbeat_evidence(scheduled=scheduled, dry_run=dry_run, success=False)
    if json_output:
        payload = _terminal_payload(
            started_at=started_at,
            status="metered_deferred",
            exit_code=0,
            expert_count=expert_count,
            detail="metered roster sync is disabled by the current budget tier",
            heartbeat=heartbeat,
            dry_run=dry_run,
            next_action={"kind": "inspect_capacity", "command_argv": ["deepr", "capacity", "next"]},
            **snapshot,
        )
        click.echo(_json.dumps(payload, indent=2))
        return True
    print_warning(
        f"Budget tier {snapshot['tier']} ({snapshot['drain_percent']}% of the monthly pool used): "
        "metered roster sync is off."
    )
    console.print("[dim]Use --local, inspect deepr capacity next, or wait for the monthly reset.[/dim]")
    _render_heartbeat_evidence(heartbeat, json_output=json_output)
    return True


def _validate_sync_all_flags(
    *,
    budget: float,
    per_expert_budget: float,
    local: bool,
    api: bool,
    scheduled: bool,
    plan: str | None,
    plan_model: str | None,
) -> None:
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("--budget must be finite and non-negative.")
    if not math.isfinite(per_expert_budget) or per_expert_budget < 0:
        raise ValueError("--per-expert-budget must be finite and non-negative.")
    if sum(bool(x) for x in (local, api, plan)) > 1:
        raise ValueError("Use only one of --local, --api, or --plan.")
    if scheduled and api:
        raise ValueError("--scheduled cannot use --api; local wallet credits are only for attended work.")
    if plan_model and not plan:
        raise ValueError("Use --plan-model only with --plan.")


def _gate_metered_sync_all(*, backend: _PassBackend, dry_run: bool) -> None:
    """Fail closed before any resolved metered roster backend can dispatch."""
    if dry_run or backend.owned_or_prepaid:
        return
    try:
        require_metered_expert_mutation(
            "api_expert_sync_all",
            safe_alternative="deepr expert sync-all --local --scheduled --yes",
        )
    except MeteredExpertMutationDisabledError as exc:
        print_error(str(exc))
        sys.exit(2)


def _emit_backend_notes(backend: _PassBackend, *, json_output: bool) -> None:
    if json_output:
        return
    if backend.note:
        console.print(f"[dim]{backend.note}[/dim]")
    if backend.use_plan and backend.plan_adapter is not None and backend.plan_adapter.tos_note:
        print_warning(backend.plan_adapter.tos_note)


def _confirm_sync_all(*, backend: _PassBackend, expert_count: int, json_output: bool) -> bool:
    if backend.use_local:
        cost_desc = "on the local model at $0"
    elif backend.use_plan and backend.plan_adapter is not None:
        cost_desc = f"via {backend.plan_adapter.display_name} at $0 at the margin"
    else:
        raise RuntimeError("metered backend reached owned/prepaid confirmation")
    prompt = f"Sync up to {expert_count} expert(s) {cost_desc}?"
    if json_output:
        click.echo(f"{prompt} [y/N]: ", nl=False, err=True)
        response = click.getchar(echo=False)
        click.echo(err=True)
        return response.lower() == "y"
    return click.confirm(
        prompt,
        default=False,
    )


def _sync_all_cancelled(
    *,
    dry_run: bool,
    yes: bool,
    backend: _PassBackend,
    pending_expert_count: int,
    roster_expert_count: int,
    started_at: datetime,
    scheduled: bool,
    json_output: bool,
    retry_command_argv: list[str],
) -> bool:
    if dry_run or yes:
        return False
    if _confirm_sync_all(backend=backend, expert_count=pending_expert_count, json_output=json_output):
        return False
    heartbeat = _heartbeat_evidence(scheduled=scheduled, dry_run=dry_run, success=False)
    if json_output:
        payload = _terminal_payload(
            started_at=started_at,
            status="cancelled",
            exit_code=0,
            expert_count=roster_expert_count,
            detail="roster sync was cancelled before dispatch",
            heartbeat=heartbeat,
            dry_run=dry_run,
            next_action={"kind": "retry_sync_all", "command_argv": list(retry_command_argv)},
        )
        click.echo(_json.dumps(payload, indent=2))
    else:
        print_warning("Cancelled.")
        _render_heartbeat_evidence(heartbeat, json_output=json_output)
    return True


def _scheduled_local_busy_wait(
    pending_names: tuple[str, ...],
    *,
    started_at: datetime,
    expert_count: int,
    scheduled: bool,
    dry_run: bool,
    backend: _PassBackend,
    per_expert_budget: float,
    json_output: bool,
    command_argv: list[str],
) -> bool:
    from deepr.backends.local_capacity import LocalCapacityState, probe_local_gpu_occupancy

    if not scheduled or dry_run or not backend.use_local:
        return False
    local_capacity = probe_local_gpu_occupancy() if pending_names else None
    if local_capacity is None or local_capacity.state != LocalCapacityState.BUSY:
        return False
    _emit_roster_local_busy_wait(
        list(pending_names),
        started_at=started_at,
        expert_count=expert_count,
        observation=local_capacity,
        per_expert_budget=per_expert_budget,
        json_output=json_output,
        command_argv=command_argv,
        local_models=_local_models_for_wait(list(pending_names), backend),
    )
    return True


def _render_library_result(result: Any, json_output: bool, *, heartbeat: dict[str, Any]) -> None:
    if json_output:
        payload = _cli_library_payload(result)
        payload["roster_experts"] = len(result.summaries)
        payload["heartbeat"] = heartbeat
        click.echo(_json.dumps(payload, indent=2))
        return
    print_header("Library sync preview" if result.dry_run else "Library sync")
    for summary in result.summaries:
        line = f"  {_STATUS_MARKERS.get(summary.status, summary.status)}  [bold]{_terminal_safe_text(summary.expert)}[/bold]"
        if summary.status == "synced":
            line += (
                f"  [dim](+{summary.absorbed} beliefs, {summary.flagged} contested, "
                f"${summary.cost:.3f} {summary.capacity_source})[/dim]"
            )
        elif summary.status == "partial_failure":
            topic_label = "topic" if summary.topics_synced == 1 else "topics"
            line += (
                f"  [dim]({summary.topics_synced} {topic_label} synced, {summary.failed_topics} failed, "
                f"+{summary.absorbed} beliefs, {summary.flagged} contested, "
                f"${summary.cost:.3f} {summary.capacity_source})[/dim]"
            )
        elif summary.detail:
            line += f"  [dim]{summary.detail[:90]}[/dim]"
        console.print(line)
    expert_count = len(result.summaries)
    expert_label = "expert" if expert_count == 1 else "experts"
    if result.dry_run:
        console.print(
            f"\n[bold]{expert_count} {expert_label} reviewed[/bold] · "
            f"{result.would_sync_experts} would sync · {result.failed_experts} failed"
        )
        console.print("[dim]Preview only: no research, spend, or expert files changed.[/dim]")
    else:
        console.print(
            f"\n[bold]{expert_count} {expert_label}[/bold] · {result.synced_experts} synced · "
            f"{result.failed_experts} failed · ${result.total_cost:.3f} spent"
        )
    if result.failed_experts:
        print_error("Roster sync completed with failures.")
        console.print("[dim]Inspect each failed expert: deepr expert loop-status NAME --json[/dim]")
    _render_heartbeat_evidence(heartbeat, json_output=json_output)


def _finish_library_result(result: Any, json_output: bool, *, heartbeat: dict[str, Any]) -> None:
    """Render the completed pass before returning its automation status."""
    _render_library_result(result, json_output, heartbeat=heartbeat)
    if result.exit_code:
        sys.exit(result.exit_code)


def _emit_empty_roster(
    json_output: bool,
    *,
    started_at: datetime,
    scheduled: bool,
    dry_run: bool,
) -> None:
    heartbeat = _heartbeat_evidence(scheduled=scheduled, dry_run=dry_run, success=True)
    if not json_output:
        prefix = "Preview complete: " if dry_run else ""
        print_success(f"{prefix}No experts yet. Create one with: deepr expert make NAME --local")
        _render_heartbeat_evidence(heartbeat, json_output=json_output)
        return
    payload = _cli_library_payload(LibrarySyncResult(started_at=started_at, dry_run=dry_run))
    payload["roster_experts"] = 0
    payload["heartbeat"] = heartbeat
    payload["next_action"] = {
        "kind": "create_expert",
        "command_argv": ["deepr", "expert", "make", "NAME", "--local"],
        "requires_user_input": ["NAME"],
    }
    click.echo(_json.dumps(payload, indent=2))


def _emit_storage_state_error(
    preflight: _RosterPreflight,
    *,
    started_at: datetime,
    scheduled: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    detail = "Expert storage could not be read safely; no roster work was dispatched."
    heartbeat = _heartbeat_evidence(scheduled=scheduled, dry_run=dry_run, success=False)
    if json_output:
        payload = _terminal_payload(
            started_at=started_at,
            status="blocked_storage_state",
            exit_code=1,
            expert_count=len(preflight.names),
            detail=detail,
            heartbeat=heartbeat,
            dry_run=dry_run,
            state_errors={
                "profiles": preflight.profile_errors,
                "subscriptions": preflight.subscription_errors,
            },
            next_action={"kind": "inspect_local_logs", "requires_manual_repair": True},
        )
        click.echo(_json.dumps(payload, indent=2))
    else:
        print_error(detail)
        console.print("[dim]Inspect local logs, repair the unreadable profile or subscription file, then retry.[/dim]")
        _render_heartbeat_evidence(heartbeat, json_output=json_output)


def _finish_no_work(
    preflight: _RosterPreflight,
    *,
    include_all: bool,
    started_at: datetime,
    scheduled: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    status = "no_changes" if include_all else "not_due"
    result = LibrarySyncResult(
        started_at=started_at,
        summaries=[ExpertSyncSummary(name, status) for name in preflight.names],
        dry_run=dry_run,
    )
    heartbeat = _heartbeat_evidence(scheduled=scheduled, dry_run=dry_run, success=True)
    _finish_library_result(result, json_output, heartbeat=heartbeat)


def _finish_preflight_terminal(
    preflight: _RosterPreflight,
    *,
    include_all: bool,
    started_at: datetime,
    scheduled: bool,
    dry_run: bool,
    json_output: bool,
) -> bool:
    """Finish storage-error, empty, or no-work snapshots before capacity lookup."""
    if preflight.has_storage_errors:
        _emit_storage_state_error(
            preflight,
            started_at=started_at,
            scheduled=scheduled,
            dry_run=dry_run,
            json_output=json_output,
        )
        sys.exit(1)
    if not preflight.names:
        _emit_empty_roster(
            json_output,
            started_at=started_at,
            scheduled=scheduled,
            dry_run=dry_run,
        )
        return True
    if preflight.pending_names:
        return False
    _finish_no_work(
        preflight,
        include_all=include_all,
        started_at=started_at,
        scheduled=scheduled,
        dry_run=dry_run,
        json_output=json_output,
    )
    return True


@expert.command(name="sync-all")
@click.option("--budget", "-b", type=float, default=5.0, show_default=True, help="Total ceiling for the roster pass.")
@click.option(
    "--per-expert-budget", type=float, default=0.50, show_default=True, help="Max spend per expert within the ceiling."
)
@click.option("--all", "include_all", is_flag=True, help="Sync every subscription regardless of cadence.")
@click.option("--dry-run", is_flag=True, help="Show what would sync without research, spend, or expert-state writes.")
@click.option("--local", is_flag=True, help="Force the local model for every expert.")
@click.option(
    "--api",
    is_flag=True,
    help="Preview the metered API with --dry-run; execution is currently gated.",
)
@click.option(
    "--plan",
    "plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Request a plan-quota backend; every dispatch remains safety-gated. See: deepr capacity fleet",
)
@click.option("--plan-model", "plan_model", default=None, help="Model to pass to the plan-quota CLI.")
@click.option("--scheduled", is_flag=True, help="Emit a wait state when no owned/prepaid capacity is available.")
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

    Owned/prepaid capacity first, per-expert budgets within the total ceiling.
    The pass continues after individual failures, then exits 1 if any expert
    failed. Designed to run on a schedule (deepr fleet install-schedule) so the
    library self-maintains. On a --scheduled run, set DEEPR_HEARTBEAT_URL to a
    public HTTPS Healthchecks-compatible endpoint so expected terminal outcomes
    report success or failure and dead-man's-switch silence remains observable.
    A scheduled --dry-run validates local endpoint form without sending a
    request.

    \b
    EXAMPLES:
      deepr expert sync-all --dry-run
      deepr expert sync-all --local -y
      deepr expert sync-all --plan claude -y
      deepr expert sync-all --scheduled -y
    """
    try:
        _validate_sync_all_flags(
            budget=budget,
            per_expert_budget=per_expert_budget,
            local=local,
            api=api,
            scheduled=scheduled,
            plan=plan,
            plan_model=plan_model,
        )
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    started_at = datetime.now(UTC)
    preflight = _inspect_roster(include_all=include_all, now=started_at)
    if _finish_preflight_terminal(
        preflight,
        include_all=include_all,
        started_at=started_at,
        scheduled=scheduled,
        dry_run=dry_run,
        json_output=json_output,
    ):
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
        scheduled=scheduled,
        yes=yes,
        json_output=json_output,
    )

    if backend.use_local and backend.local_model is None:
        print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
        sys.exit(2)
    if scheduled and not api and not backend.owned_or_prepaid:
        _emit_roster_wait(
            json_output,
            "no owned/prepaid capacity is available",
            started_at=started_at,
            expert_count=len(preflight.names),
            scheduled=scheduled,
            dry_run=dry_run,
        )
        return
    if not api and not backend.owned_or_prepaid:
        print_error(
            f"No owned or prepaid sync capacity is available: {backend.note}. "
            "Pass --api only when metered capacity is intentionally authorized."
        )
        sys.exit(2)
    if _scheduled_local_busy_wait(
        preflight.pending_names,
        started_at=started_at,
        expert_count=len(preflight.names),
        scheduled=scheduled,
        dry_run=dry_run,
        backend=backend,
        per_expert_budget=per_expert_budget,
        json_output=json_output,
        command_argv=retry_command_argv,
    ):
        return

    # Explicit API execution either defers under a drained monthly tier or
    # reaches the shared disabled mutation gate.
    metered_auto = not backend.use_local and not backend.use_plan and not api
    if (
        metered_auto
        and not dry_run
        and _metered_tier_defers(
            json_output,
            started_at=started_at,
            expert_count=len(preflight.names),
            scheduled=scheduled,
            dry_run=dry_run,
        )
    ):
        return

    _gate_metered_sync_all(backend=backend, dry_run=dry_run)

    _emit_backend_notes(backend, json_output=json_output)

    if _sync_all_cancelled(
        dry_run=dry_run,
        yes=yes,
        backend=backend,
        pending_expert_count=len(preflight.pending_names),
        roster_expert_count=len(preflight.names),
        started_at=started_at,
        scheduled=scheduled,
        json_output=json_output,
        retry_command_argv=retry_command_argv,
    ):
        return

    sync_one = _make_sync_one(
        backend=backend,
        preflight=preflight,
        include_all=include_all,
        scheduled=scheduled,
        snapshot_at=started_at,
    )
    result = asyncio.run(
        run_library_sync(
            sync_one=sync_one,
            expert_names=list(preflight.names),
            budget=budget,
            per_expert_budget=per_expert_budget,
            only_due=not include_all,
            dry_run=dry_run,
            now=started_at,
            subscription_store_factory=preflight.subscription_stores.__getitem__ if dry_run else None,
        )
    )
    heartbeat = _heartbeat_evidence(
        scheduled=scheduled,
        dry_run=dry_run,
        success=result.exit_code == 0,
    )
    _finish_library_result(result, json_output, heartbeat=heartbeat)
