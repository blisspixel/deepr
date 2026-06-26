"""Support helpers for the ``expert sync`` CLI command.

This module keeps the command registration file under the file-size ratchet
while preserving one shared implementation for capacity waits, loop records,
context builders, and overlap locking.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_warning

SYNC_CAPACITY_GATE_KIND = "deepr.expert.sync_capacity_gate"
SYNC_CAPACITY_GATE_SCHEMA_VERSION = "deepr-sync-capacity-gate-v1"


def _self_model_context(expert_name: str, *, profile: Any | None = None) -> dict[str, Any]:
    from deepr.experts.self_model import (
        build_expert_self_model_context,
        build_expert_self_model_context_from_profile,
    )

    if profile is not None:
        return build_expert_self_model_context_from_profile(profile, focus_limit=3)
    return build_expert_self_model_context(expert_name, focus_limit=3)


def _self_model_run_context(expert_name: str, *, profile: Any | None = None) -> dict[str, Any]:
    self_model = _self_model_context(expert_name, profile=profile)
    context = {"self_model": self_model} if self_model else {}
    from deepr.experts.self_model_updates import build_self_model_update_context

    update_context = build_self_model_update_context(expert_name)
    if update_context.get("accepted_record_count"):
        context["self_model_updates"] = update_context
    return context


def _sync_context_mode(*, fresh_context: bool, deep_context: bool) -> str:
    if deep_context:
        return "deep"
    if fresh_context:
        return "fresh"
    return "none"


def _build_sync_capacity_payload(
    expert_name: str,
    *,
    context_mode: str,
    scheduled: bool,
    status: str,
    detail: str,
    profile: Any | None = None,
) -> dict[str, Any]:
    from deepr.backends.admission import TASK_CLASS_SYNC
    from deepr.backends.capacity_actions import (
        CapacityJobContext,
        build_capacity_next_actions,
        build_capacity_next_payload,
    )

    job_context = CapacityJobContext(
        task_class=TASK_CLASS_SYNC,
        expert_name=expert_name,
        context_mode=context_mode,
        scheduled=scheduled,
    )
    actions = build_capacity_next_actions(task_class=TASK_CLASS_SYNC, job_context=job_context)
    payload = {
        "schema_version": SYNC_CAPACITY_GATE_SCHEMA_VERSION,
        "kind": SYNC_CAPACITY_GATE_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "stability": "experimental",
            "compatibility": {
                "additive_fields": True,
                "breaking_changes_require_new_schema_version": True,
                "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
            },
        },
        "status": status,
        "expert_name": expert_name,
        "detail": detail,
        "capacity_next": build_capacity_next_payload(job_context, actions),
    }
    self_model = _self_model_context(expert_name, profile=profile)
    if self_model:
        payload["self_model"] = self_model
    return payload


def _print_capacity_payload(payload: dict[str, Any]) -> None:
    for action in payload["capacity_next"]["actions"]:
        console.print(f"  [{action['rank']}] {action['status']}: {action['title']}")
        if action.get("detail"):
            console.print(f"      [dim]{action['detail']}[/dim]")
        if action.get("command"):
            console.print(f"      [dim]{action['command']}[/dim]")


def _emit_scheduled_capacity_wait(
    expert_name: str,
    *,
    context_mode: str,
    json_output: bool,
    detail: str,
    profile: Any | None = None,
) -> None:
    payload = _build_sync_capacity_payload(
        expert_name,
        context_mode=context_mode,
        scheduled=True,
        status="waiting_for_capacity",
        detail=detail,
        profile=profile,
    )
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    loop_run = record_loop_run(
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync due subscriptions for {expert_name}",
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        next_action=(payload["capacity_next"]["actions"][0] if payload["capacity_next"]["actions"] else {}),
        run_context=_self_model_run_context(expert_name, profile=profile),
        capacity_source="owned/prepaid",
    )
    payload["loop_run"] = loop_run.to_dict()
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    print_warning("Scheduled sync is waiting for cheap capacity.")
    console.print(f"[dim]{detail}.[/dim]")
    _print_capacity_payload(payload)


def _emit_capacity_block(
    expert_name: str,
    *,
    context_mode: str,
    json_output: bool,
    detail: str,
    profile: Any | None = None,
) -> None:
    payload = _build_sync_capacity_payload(
        expert_name,
        context_mode=context_mode,
        scheduled=False,
        status="capacity_blocked",
        detail=detail,
        profile=profile,
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    print_error(f"{detail}. Use --local or admit a local model first.")
    _print_capacity_payload(payload)


def _record_completed_sync_loop(
    expert_name: str,
    result: Any,
    *,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    capacity_source: str,
    profile: Any | None = None,
) -> Any:
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    outcomes = list(getattr(result, "outcomes", []) or [])
    failed = [o for o in outcomes if getattr(o, "status", "") == "failed"]
    accepted = sum(
        max(int(getattr(o, "absorbed", 0) or 0), 0) + max(int(getattr(o, "flagged", 0) or 0), 0) for o in outcomes
    )
    if failed:
        status = LoopRunStatus.FAILED
        stop_reason = LoopStopReason.TOOL_FAILURE
        next_action = {
            "status": "inspect",
            "title": "Inspect failed sync outcomes",
            "detail": f"{len(failed)} topic(s) failed during sync.",
            "command": f'deepr expert sync "{expert_name}" --dry-run',
        }
    else:
        status = LoopRunStatus.COMPLETED
        stop_reason = LoopStopReason.VERIFIER_PASSED if accepted else LoopStopReason.NO_DUE_WORK
        next_action = {}

    return record_loop_run(
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync {'all' if sync_all else 'due'} subscriptions for {expert_name}",
        trigger="scheduled" if scheduled else "manual",
        status=status,
        stop_reason=stop_reason,
        next_action=next_action,
        run_context=_self_model_run_context(expert_name, profile=profile),
        budget_limit=budget,
        budget_spent=float(getattr(result, "total_cost", 0.0) or 0.0),
        capacity_source=capacity_source,
        accepted_changes=accepted,
        rejected_changes=len(failed),
    )


def _record_sync_overlap_loop(
    expert_name: str,
    *,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    capacity_source: str,
    profile: Any | None = None,
) -> Any:
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    return record_loop_run(
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync {'all' if sync_all else 'due'} subscriptions for {expert_name}",
        trigger="scheduled" if scheduled else "manual",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.OVERLAP_LOCKED,
        next_action={
            "status": "waiting_for_overlap",
            "title": "Another sync is already running",
            "detail": "This run skipped because the same expert sync verb already holds the overlap lock.",
            "command": f'deepr expert sync "{expert_name}" --scheduled',
        },
        run_context=_self_model_run_context(expert_name, profile=profile),
        budget_limit=budget,
        budget_spent=0.0,
        capacity_source=capacity_source,
    )


def _selected_sync_capacity_source(*, use_local: bool, use_plan: bool, plan_adapter: Any) -> str:
    if use_local:
        return "local"
    if use_plan and plan_adapter is not None:
        return f"plan_quota:{plan_adapter.backend_id}"
    return "api_metered"


def _sync_overlap_result(expert_name: str) -> Any:
    from deepr.experts.sync import SyncOutcome, SyncResult

    return SyncResult(
        expert_name=expert_name,
        started_at=datetime.now(UTC),
        outcomes=[
            SyncOutcome(
                topic="sync",
                status="skipped",
                detail="another sync for this expert is already running",
            )
        ],
    )


def _run_sync_with_loop_guard(
    profile: Any,
    *,
    name: str,
    budget: float,
    sync_all: bool,
    dry_run: bool,
    scheduled: bool,
    jitter: float,
    use_local: bool,
    local_model: str | None,
    use_plan: bool,
    plan_adapter: Any,
    plan_model: str | None,
    context_builder: Any,
    grounding_checker: Any | None = None,
) -> tuple[Any, Any | None, str]:
    from deepr.experts.maintenance_engine import build_sync_engine

    def run_once() -> tuple[Any, str]:
        engine, capacity_source = build_sync_engine(
            profile,
            use_local=use_local,
            local_model=local_model,
            use_plan=use_plan,
            plan_adapter=plan_adapter,
            plan_model=plan_model,
            context_builder=context_builder,
            grounding_checker=grounding_checker,
        )
        result = asyncio.run(engine.sync(budget=budget, only_due=not sync_all, dry_run=dry_run))
        return result, capacity_source

    if dry_run:
        result, capacity_source = run_once()
        return result, None, capacity_source

    if jitter > 0:
        from deepr.experts.loop_lock import apply_startup_jitter

        apply_startup_jitter(name, jitter)

    from deepr.experts.loop_lock import expert_verb_lock

    capacity_source = _selected_sync_capacity_source(
        use_local=use_local,
        use_plan=use_plan,
        plan_adapter=plan_adapter,
    )
    with expert_verb_lock(name, "sync") as acquired:
        if not acquired:
            result = _sync_overlap_result(name)
            loop_run = _record_sync_overlap_loop(
                name,
                budget=budget,
                scheduled=scheduled,
                sync_all=sync_all,
                capacity_source=capacity_source,
                profile=profile,
            )
            return result, loop_run, capacity_source
        result, capacity_source = run_once()
        loop_run = _record_completed_sync_loop(
            name,
            result,
            budget=budget,
            scheduled=scheduled,
            sync_all=sync_all,
            capacity_source=capacity_source,
            profile=profile,
        )
        return result, loop_run, capacity_source


def _sync_context_builder(*, fresh_context: bool, deep_context: bool, json_output: bool) -> Any | None:
    """Build the optional free-only retrieval context builder for local/plan sync."""
    if deep_context:
        from deepr.backends.fresh_context import make_free_deep_context_builder

        if not json_output:
            console.print(
                "[dim]Deep context enabled: multi-query free-only web retrieval; "
                "API-key search providers are not used.[/dim]"
            )
        return make_free_deep_context_builder()
    if fresh_context:
        from deepr.backends.fresh_context import make_free_fresh_context_builder

        if not json_output:
            console.print(
                "[dim]Fresh context enabled: free-only web retrieval; API-key search providers are not used.[/dim]"
            )
        return make_free_fresh_context_builder()
    return None
