"""Scheduler wait and owned-capacity dispatch helpers for expert reflection."""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_warning

SCHEDULED_REFLECTION_WAIT_KIND = "deepr.expert.scheduled_reflection_wait"
SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION = "deepr-scheduled-reflection-wait-v1"
SCHEDULED_REFLECTION_RUN_KIND = "deepr.expert.scheduled_reflection_run"
SCHEDULED_REFLECTION_RUN_SCHEMA_VERSION = "deepr-scheduled-reflection-run-v1"


@dataclass(frozen=True)
class ScheduledReflectionCapacity:
    """Owned/prepaid evaluator capacity resolved from the maintenance waterfall."""

    use_local: bool = False
    local_model: str | None = None
    use_plan: bool = False
    plan_backend_id: str | None = None
    note: str = ""

    @property
    def owned_or_prepaid(self) -> bool:
        return self.use_local or self.use_plan

    @property
    def capacity_source(self) -> str:
        if self.use_local:
            return "local"
        if self.use_plan and self.plan_backend_id:
            return f"plan_quota:{self.plan_backend_id}"
        return "api_metered"


def resolve_scheduled_reflection_capacity() -> ScheduledReflectionCapacity:
    """Ask the waterfall for admitted `reflect` capacity; never selects metered.

    The plan rung is returned only when the existing waterfall gate holds: an
    admitted backend with a trusted, non-exhausted quota observation. Anything
    else resolves to "not owned/prepaid" and scheduled reflection waits.
    """
    from deepr.backends.admission import TASK_CLASS_REFLECT
    from deepr.backends.waterfall import choose_maintenance_backend

    choice = choose_maintenance_backend(TASK_CLASS_REFLECT)
    if choice.is_local and choice.model:
        return ScheduledReflectionCapacity(use_local=True, local_model=choice.model, note=choice.reason)
    if choice.is_plan_quota and choice.plan_backend_id:
        return ScheduledReflectionCapacity(use_plan=True, plan_backend_id=choice.plan_backend_id, note=choice.reason)
    return ScheduledReflectionCapacity(note=choice.reason)


def build_scheduled_reflection_engine(capacity: ScheduledReflectionCapacity) -> Any:
    """Build a ReflectionEngine on the resolved owned/prepaid client.

    Raises ``ValueError`` when the capacity is not owned/prepaid or the plan
    adapter is unknown; there is no metered fallback on this path.
    """
    from deepr.experts.reflection import ReflectionEngine

    if capacity.use_local and capacity.local_model:
        from deepr.backends.local import ollama_chat_client

        return ReflectionEngine(client=ollama_chat_client(), model=capacity.local_model)
    if capacity.use_plan and capacity.plan_backend_id:
        from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter

        adapter = get_adapter(capacity.plan_backend_id)
        if adapter is None:
            raise ValueError(f"unknown plan-quota backend: {capacity.plan_backend_id}")
        client = PlanQuotaChatClient(adapter, operation="plan_quota_reflection")
        return ReflectionEngine(client=client, model=adapter.backend_id)
    raise ValueError("scheduled reflection requires owned/prepaid capacity; there is no metered fallback")


def _quote_cli_arg(value: str) -> str:
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def _scheduled_reflection_contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "stability": "experimental",
        "compatibility": {
            "additive_fields": True,
            "breaking_changes_require_new_schema_version": True,
            "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
        },
    }


def _reflect_command(
    expert_name: str,
    report_id: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
) -> str:
    depth_flag = "" if depth == 1 else f" --depth {depth}"
    followup_flags = f" --execute-followups --budget {budget:.2f} -y" if execute_followups else ""
    return f"deepr expert reflect {_quote_cli_arg(expert_name)} {_quote_cli_arg(report_id)}{depth_flag}{followup_flags}"


def scheduled_reflection_wait_payload(
    expert_name: str,
    report_id: str,
    question: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
) -> dict[str, Any]:
    detail = "scheduled reflection is waiting for owned/prepaid evaluator capacity instead of making a metered call"
    pending = ["reflection_evaluation"]
    if execute_followups:
        pending.append("followup_research")
    payload = {
        "schema_version": SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION,
        "kind": SCHEDULED_REFLECTION_WAIT_KIND,
        "contract": _scheduled_reflection_contract(),
        "status": "waiting_for_capacity",
        "expert_name": expert_name,
        "report_id": report_id,
        "question": question,
        "detail": detail,
        "scheduled": True,
        "depth": depth,
        "execute_followups": execute_followups,
        "followup_budget_ceiling": round(budget, 4) if execute_followups else 0.0,
        "pending_work": pending,
        "next_actions": [
            {
                "status": "wait",
                "title": "Wait for cheap evaluator capacity",
                "detail": (
                    "Rerun the scheduled job when a local or plan-quota reflection backend exists. "
                    "Scheduled mode does not start metered reflection or follow-up research."
                ),
            },
            {
                "status": "run_once",
                "title": "Run explicitly with the normal budget gates",
                "detail": "Remove --scheduled only when this one-off evaluation and any follow-ups may use metered capacity.",
                "command": _reflect_command(
                    expert_name,
                    report_id,
                    depth=depth,
                    execute_followups=execute_followups,
                    budget=budget,
                ),
            },
        ],
    }
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    loop_run = record_loop_run(
        expert_name=expert_name,
        loop_type="reflection_followups",
        goal=f"Reflect on report {report_id} and run follow-ups",
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        next_action=payload["next_actions"][0],
        budget_limit=budget if execute_followups else None,
        capacity_source="owned/prepaid",
    )
    payload["loop_run"] = loop_run.to_dict()
    return payload


def _resolve_scheduled_followup_backend(profile: Any, json_output: bool) -> tuple[Any, str] | None:
    """Resolve owned/prepaid gap-fill capacity for scheduled follow-ups.

    Returns ``None`` when the waterfall offers no local or admitted plan
    capacity for the ``gap_fill`` task class; scheduled follow-ups then wait
    instead of falling through to metered research.
    """
    from deepr.backends.admission import TASK_CLASS_GAP_FILL
    from deepr.backends.waterfall import choose_maintenance_backend
    from deepr.cli.commands.semantic.expert_gap_routes import _build_gap_fill_engine

    choice = choose_maintenance_backend(TASK_CLASS_GAP_FILL)
    if not ((choice.is_local and choice.model) or (choice.is_plan_quota and choice.plan_backend_id)):
        return None
    return _build_gap_fill_engine(
        profile,
        use_local=choice.is_local,
        local_model=choice.model,
        use_plan=choice.is_plan_quota,
        plan_backend_id=choice.plan_backend_id,
        plan_model=None,
        selection_note=choice.reason,
        json_output=json_output,
    )


def dispatch_scheduled_reflection(
    profile: Any,
    fallback_name: str,
    report_id: str,
    question: str,
    report_text: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
    json_output: bool,
) -> None:
    """Run scheduled reflection on admitted owned/prepaid capacity or wait.

    This is the single scheduled entry point: it consults the waterfall for
    `reflect`-class capacity, runs on local or trusted-quota plan capacity when
    admitted, and otherwise emits the unchanged wait payload. Metered
    evaluation is never dispatched from scheduled mode.
    """
    capacity = resolve_scheduled_reflection_capacity()
    if capacity.owned_or_prepaid:
        run_scheduled_reflection(
            profile,
            report_id,
            question,
            report_text,
            capacity,
            depth=depth,
            execute_followups=execute_followups,
            budget=budget,
            json_output=json_output,
        )
        return
    profile_name = profile.name if isinstance(getattr(profile, "name", None), str) and profile.name else fallback_name
    emit_scheduled_reflection_wait(
        profile_name,
        report_id,
        question,
        depth=depth,
        execute_followups=execute_followups,
        budget=budget,
        json_output=json_output,
    )


def scheduled_reflection_run_payload(
    report: Any,
    capacity: ScheduledReflectionCapacity,
    followups_section: dict[str, Any],
    loop_run: Any,
) -> dict[str, Any]:
    """Build the published run payload for a scheduled owned-capacity reflection."""
    return {
        "schema_version": SCHEDULED_REFLECTION_RUN_SCHEMA_VERSION,
        "kind": SCHEDULED_REFLECTION_RUN_KIND,
        "scheduled": True,
        "capacity_source": capacity.capacity_source,
        "capacity_note": capacity.note,
        "report": report.to_dict(),
        "followups": followups_section,
        "loop_run": loop_run.to_dict(),
    }


def run_scheduled_reflection(
    profile: Any,
    report_id: str,
    question: str,
    report_text: str,
    capacity: ScheduledReflectionCapacity,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
    json_output: bool,
) -> None:
    """Run scheduled reflection on already-resolved owned/prepaid capacity.

    The evaluator runs on the resolved local or plan client. Follow-ups run
    only when the ``gap_fill`` waterfall rung also resolves to owned/prepaid
    capacity; otherwise they are recorded as waiting. No metered research or
    evaluation is dispatched from this path.
    """
    import asyncio
    import sys

    from deepr.cli.commands.semantic.expert_reflection_loop import record_completed_reflection_loop
    from deepr.experts.reflection import ReflectionError

    try:
        engine = build_scheduled_reflection_engine(capacity)
        report = asyncio.run(
            engine.reflect(question, report_text, domain=getattr(profile, "domain", "") or "", depth=depth)
        )
    except (ReflectionError, ValueError) as exc:
        print_error(f"Scheduled reflection failed on {capacity.capacity_source}: {exc}")
        sys.exit(2)
    except Exception as exc:
        # Plan CLI failures (RuntimeError subclasses) and local transport
        # errors must exit cleanly like the manual path, not as tracebacks.
        print_error(f"Scheduled reflection failed on {capacity.capacity_source}: {exc}")
        sys.exit(1)

    followups_section: dict[str, Any] = {"requested": execute_followups, "status": "not_requested"}
    fill_result = None
    if execute_followups and report.followups:
        from deepr.experts.loop_lock import expert_verb_lock

        # Lock before any gap-fill engine or client construction (the same
        # skip-before-mutation pattern as every other scheduled verb).
        with expert_verb_lock(profile.name, "reflect") as acquired:
            if not acquired:
                from deepr.cli.commands.semantic.expert_reflection_loop import record_reflection_overlap_loop

                overlap_run = record_reflection_overlap_loop(
                    profile.name,
                    report_id,
                    budget=budget,
                    scheduled=True,
                    capacity_source=capacity.capacity_source,
                )
                followups_section = {
                    "requested": True,
                    "status": "waiting_for_overlap",
                    "detail": "another reflection follow-up run holds the overlap guard",
                    "loop_run_id": overlap_run.run_id,
                }
                payload = scheduled_reflection_run_payload(report, capacity, followups_section, overlap_run)
                _emit_scheduled_reflection_run(payload, report, capacity, followups_section, json_output)
                return

            followup_backend = _resolve_scheduled_followup_backend(profile, json_output)
            if followup_backend is None:
                followups_section = {
                    "requested": True,
                    "status": "waiting_for_capacity",
                    "detail": (
                        "no owned/prepaid gap-fill capacity is admitted; scheduled follow-ups wait "
                        "instead of using metered research"
                    ),
                    "followup_count": len(report.followups),
                }
            else:
                from deepr.experts.gap_fill import routes_from_queries

                fill_engine, fill_capacity = followup_backend
                routes = routes_from_queries(report.followups)
                fill_result = asyncio.run(fill_engine.execute(routes, budget=budget, top=len(routes)))
                if getattr(fill_result, "knowledge_observed_at", None) is not None:
                    from deepr.experts.profile import ExpertStore

                    ExpertStore().save(profile)
                followups_section = {
                    "requested": True,
                    "status": "executed",
                    "capacity_source": fill_capacity,
                    "total_cost": round(float(getattr(fill_result, "total_cost", 0.0) or 0.0), 4),
                    "outcomes": [
                        {"topic": o.topic, "status": o.status, "cost": round(float(o.cost or 0.0), 4)}
                        for o in getattr(fill_result, "outcomes", []) or []
                    ],
                }
    elif execute_followups:
        followups_section = {"requested": True, "status": "none_emitted"}

    loop_run = record_completed_reflection_loop(
        profile.name,
        report_id,
        report,
        budget=budget,
        execute_followups=execute_followups,
        fill_result=fill_result,
        capacity_source=capacity.capacity_source,
        scheduled=True,
    )
    payload = scheduled_reflection_run_payload(report, capacity, followups_section, loop_run)
    _emit_scheduled_reflection_run(payload, report, capacity, followups_section, json_output)


def _emit_scheduled_reflection_run(
    payload: dict[str, Any],
    report: Any,
    capacity: ScheduledReflectionCapacity,
    followups_section: dict[str, Any],
    json_output: bool,
) -> None:
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return
    console.print(f"[dim]Scheduled reflection ran on {capacity.capacity_source}: {capacity.note}[/dim]")
    console.print(f"Verdict: {report.verdict} (overall {report.overall_score:.0%}, model {report.model})")
    if followups_section.get("status") == "executed":
        console.print(f"Follow-ups executed on {followups_section['capacity_source']}.")
    elif followups_section.get("status") == "waiting_for_capacity":
        print_warning("Follow-ups are waiting for owned/prepaid gap-fill capacity.")
    elif followups_section.get("status") == "waiting_for_overlap":
        print_warning("Follow-ups are waiting for the reflection overlap guard.")


def emit_scheduled_reflection_wait(
    expert_name: str,
    report_id: str,
    question: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
    json_output: bool,
) -> None:
    payload = scheduled_reflection_wait_payload(
        expert_name,
        report_id,
        question,
        depth=depth,
        execute_followups=execute_followups,
        budget=budget,
    )
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_warning("Scheduled reflection is waiting for cheap evaluator capacity.")
    console.print(f"[dim]{payload['detail']}.[/dim]")
    for action in payload["next_actions"]:
        console.print(f"  {action['status']}: {action['title']}")
        if action.get("detail"):
            console.print(f"      [dim]{action['detail']}[/dim]")
        if action.get("command"):
            console.print(f"      [dim]{action['command']}[/dim]")
