"""Expert gap routing command.

Extracted from experts.py so the oversized command module does not grow while
the route-gaps loop gains scheduler-aware capacity behavior.
"""

from __future__ import annotations

import asyncio
import json as _json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.grounding_support import PLAN_BACKEND_CHOICES

SCHEDULED_GAP_FILL_WAIT_KIND = "deepr.expert.scheduled_gap_fill_wait"
SCHEDULED_GAP_FILL_WAIT_SCHEMA_VERSION = "deepr-scheduled-gap-fill-wait-v1"


@dataclass(frozen=True)
class _GapFillBackend:
    use_local: bool = False
    local_model: str | None = None
    use_plan: bool = False
    plan_backend_id: str | None = None
    plan_model: str | None = None
    note: str = ""

    @property
    def owned_or_prepaid(self) -> bool:
        return self.use_local or self.use_plan


def _resolve_gap_fill_backend(local: bool, api: bool, plan: str | None, plan_model: str | None) -> _GapFillBackend:
    """Resolve the execution rung for route-gaps fills."""
    _validate_gap_fill_backend_flags(local=local, api=api, plan=plan, plan_model=plan_model)
    if api:
        return _GapFillBackend()
    if plan:
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(plan)
        if not choice.is_plan_quota or choice.plan_backend_id is None:
            raise ValueError(choice.reason)
        return _GapFillBackend(
            use_plan=True,
            plan_backend_id=choice.plan_backend_id,
            plan_model=plan_model,
            note=choice.reason,
        )
    if local:
        return _GapFillBackend(use_local=True)

    from deepr.backends.admission import TASK_CLASS_GAP_FILL
    from deepr.backends.waterfall import choose_maintenance_backend

    choice = choose_maintenance_backend(TASK_CLASS_GAP_FILL)
    if choice.is_plan_quota and choice.plan_backend_id:
        return _GapFillBackend(use_plan=True, plan_backend_id=choice.plan_backend_id, note=choice.reason)
    if choice.is_local:
        return _GapFillBackend(use_local=True, local_model=choice.model, note=choice.reason)
    return _GapFillBackend(note=choice.reason)


def _validate_gap_fill_backend_flags(*, local: bool, api: bool, plan: str | None, plan_model: str | None) -> None:
    """Validate flag combinations without touching profile or capacity state."""
    if sum(bool(x) for x in (local, api, plan)) > 1:
        raise ValueError("Use only one of --local, --api, or --plan.")
    if plan_model and not plan:
        raise ValueError("Use --plan-model with --plan.")


def _quote_cli_arg(value: str) -> str:
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def _scheduled_gap_fill_contract() -> dict[str, Any]:
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


def _scheduled_gap_fill_wait_payload(profile_name: str, routes: list[Any], *, budget: float, top_n: int) -> dict:
    research_routes = [r for r in routes if r.instrument == "research"]
    est = min(sum(max(r.estimated_cost, 0.05) for r in research_routes), budget)
    payload = {
        "schema_version": SCHEDULED_GAP_FILL_WAIT_SCHEMA_VERSION,
        "kind": SCHEDULED_GAP_FILL_WAIT_KIND,
        "contract": _scheduled_gap_fill_contract(),
        "status": "waiting_for_capacity",
        "expert_name": profile_name,
        "detail": "scheduled gap fill is waiting for owned/prepaid capacity instead of using metered research",
        "scheduled": True,
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
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    loop_run = record_loop_run(
        expert_name=profile_name,
        loop_type="gap_fill",
        goal=f"Fill routed knowledge gaps for {profile_name}",
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        next_action=payload["next_actions"][0],
        budget_limit=budget,
        capacity_source="owned/prepaid",
    )
    payload["loop_run"] = loop_run.to_dict()
    return payload


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


def _build_gap_fill_engine(
    profile: Any,
    *,
    use_local: bool,
    local_model: str | None,
    use_plan: bool,
    plan_backend_id: str | None,
    plan_model: str | None,
    selection_note: str,
    json_output: bool,
    spend_decision_fn: Any | None = None,
) -> tuple[Any, str]:
    """Build the gap-fill engine for the chosen rung; returns (engine, capacity_source).

    Owned local and prepaid plan both run research *and* verified extraction on
    the same $0/prepaid client (no silent metered call); the default is metered.
    """
    from deepr.experts.gap_fill import GapFillEngine

    if use_local:
        from deepr.backends.local import default_local_model, make_local_research_fn, ollama_chat_client
        from deepr.experts.report_absorber import ReportAbsorber

        local_model = local_model or default_local_model()
        if not local_model:
            print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
            sys.exit(2)
        if selection_note and not json_output:
            console.print(f"[dim]{selection_note}[/dim]")
        engine = GapFillEngine(
            profile,
            research_fn=make_local_research_fn(local_model),
            absorber=ReportAbsorber(profile, model=local_model, client=ollama_chat_client(), estimated_cost=0.0),
        )
        return engine, "local"

    if use_plan:
        from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter, make_plan_quota_research_fn
        from deepr.experts.report_absorber import ReportAbsorber

        adapter = get_adapter(plan_backend_id or "")
        if adapter is None:
            print_error(f"Unknown plan-quota backend: {plan_backend_id}")
            sys.exit(2)
        if selection_note and not json_output:
            console.print(f"[dim]{selection_note}[/dim]")
        if adapter.tos_note and not json_output:
            print_warning(adapter.tos_note)
        client = PlanQuotaChatClient(adapter, model=plan_model)
        engine = GapFillEngine(
            profile,
            research_fn=make_plan_quota_research_fn(adapter, model=plan_model, client=client),
            absorber=ReportAbsorber(profile, model=plan_model or adapter.backend_id, client=client, estimated_cost=0.0),
        )
        return engine, f"plan_quota:{adapter.backend_id}"

    return GapFillEngine(profile, spend_decision_fn=spend_decision_fn), "api_metered"


def _selected_gap_fill_capacity_source(backend: _GapFillBackend) -> str:
    if backend.use_local:
        return "local"
    if backend.use_plan and backend.plan_backend_id:
        return f"plan_quota:{backend.plan_backend_id}"
    return "api_metered"


def _automatic_gap_fill_spend_decider(profile_name: str, backend: _GapFillBackend, *, api: bool, dry_run: bool):
    if dry_run or api or backend.owned_or_prepaid:
        return None
    from deepr.experts.gap_spend_gate import build_gap_fill_spend_decider

    return build_gap_fill_spend_decider(expert_name=profile_name, capacity_source="api_metered")


def _gap_fill_overlap_result(profile_name: str):
    from deepr.experts.gap_fill import GapFillOutcome, GapFillResult

    return GapFillResult(
        expert_name=profile_name,
        started_at=datetime.now(UTC),
        outcomes=[
            GapFillOutcome(
                topic="route-gaps",
                status="skipped",
                detail="another route-gaps execution for this expert is already running",
            )
        ],
        total_cost=0.0,
    )


def _record_gap_fill_overlap_loop(profile_name: str, *, budget: float, scheduled: bool, capacity_source: str):
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    return record_loop_run(
        expert_name=profile_name,
        loop_type="gap_fill",
        goal=f"Fill routed knowledge gaps for {profile_name}",
        trigger="scheduled" if scheduled else "manual",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.OVERLAP_LOCKED,
        next_action={
            "status": "waiting_for_overlap",
            "title": "Another gap-fill run is already running",
            "detail": "This run skipped because the same expert route-gaps verb already holds the overlap lock.",
            "command": f'deepr expert route-gaps "{profile_name}" --execute --scheduled',
        },
        budget_limit=budget,
        budget_spent=0.0,
        capacity_source=capacity_source,
    )


def _record_completed_gap_fill_loop(
    profile_name: str, result: Any, *, budget: float, scheduled: bool, capacity_source: str
):
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    outcomes = list(getattr(result, "outcomes", []) or [])
    failed = [o for o in outcomes if getattr(o, "status", "") == "failed"]
    deferred = [o for o in outcomes if getattr(o, "status", "") == "deferred"]
    skipped = [o for o in outcomes if getattr(o, "status", "") == "skipped"]
    metered_deferred = [o for o in skipped if str(getattr(o, "detail", "") or "").startswith("metered deferred:")]
    accepted = sum(
        max(int(getattr(o, "absorbed", 0) or 0), 0) + max(int(getattr(o, "flagged", 0) or 0), 0) for o in outcomes
    )

    if failed:
        status = LoopRunStatus.FAILED
        stop_reason = LoopStopReason.TOOL_FAILURE
        next_action = {
            "status": "inspect",
            "title": "Inspect failed gap-fill outcomes",
            "detail": f"{len(failed)} routed gap(s) failed during fill execution.",
            "command": f'deepr expert route-gaps "{profile_name}" --execute --dry-run',
        }
        rejected = len(failed)
    elif deferred:
        status = LoopRunStatus.WAITING
        stop_reason = LoopStopReason.HUMAN_GATE_REQUIRED
        next_action = {
            "status": "human_gate_required",
            "title": "Run deferred specialist routes",
            "detail": f"{len(deferred)} routed gap(s) require approval-gated specialist instruments.",
        }
        rejected = 0
    elif metered_deferred:
        status = LoopRunStatus.WAITING
        stop_reason = LoopStopReason.CAPACITY_UNAVAILABLE
        next_action = {
            "status": "deferred_for_value",
            "title": "Wait for higher-value metered gap-fill work",
            "detail": f"{len(metered_deferred)} routed gap(s) deferred by the automatic metered spend gate.",
            "command": f'deepr expert route-gaps "{profile_name}" --execute --api --budget {budget:.2f}',
        }
        rejected = 0
    elif skipped:
        status = LoopRunStatus.WAITING
        stop_reason = LoopStopReason.BUDGET_EXHAUSTED
        next_action = {
            "status": "increase_budget",
            "title": "Rerun with enough budget",
            "detail": f"{len(skipped)} routed gap(s) were skipped after the run budget was exhausted.",
            "command": f'deepr expert route-gaps "{profile_name}" --execute --budget {budget:.2f}',
        }
        rejected = 0
    else:
        status = LoopRunStatus.COMPLETED
        stop_reason = LoopStopReason.VERIFIER_PASSED if accepted else LoopStopReason.NO_DUE_WORK
        next_action = {}
        rejected = 0

    return record_loop_run(
        expert_name=profile_name,
        loop_type="gap_fill",
        goal=f"Fill routed knowledge gaps for {profile_name}",
        trigger="scheduled" if scheduled else "manual",
        status=status,
        stop_reason=stop_reason,
        next_action=next_action,
        budget_limit=budget,
        budget_spent=float(getattr(result, "total_cost", 0.0) or 0.0),
        capacity_source=capacity_source,
        accepted_changes=accepted,
        rejected_changes=rejected,
    )


@expert.command(name="route-gaps")
@click.argument("name")
@click.option("--top", "-t", "top_n", type=int, default=5, show_default=True, help="How many top gaps to route")
@click.option("--json", "json_output", is_flag=True, help="Emit the structured routes as JSON")
@click.option("--execute", "execute_fills", is_flag=True, help="Execute the research-route fills (budget-bounded)")
@click.option("--budget", "-b", type=float, default=2.0, show_default=True, help="Run budget ceiling for --execute")
@click.option("--dry-run", is_flag=True, help="With --execute: show what would run; no spend")
@click.option("--scheduled", is_flag=True, help="With --execute: wait instead of spending on recurring gap fills")
@click.option(
    "--jitter",
    type=float,
    default=0.0,
    show_default=True,
    help="With --execute: maximum startup jitter in seconds before a non-dry gap-fill run",
)
@click.option("--local", is_flag=True, help="With --execute: run fills on the local Ollama model at $0")
@click.option("--api", is_flag=True, help="With --execute: force the metered API")
@click.option(
    "--plan",
    "plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="With --execute: run fills on a plan-quota CLI backend (prepaid). See: deepr capacity",
)
@click.option("--plan-model", "plan_model", default=None, help="Model to pass to the plan-quota CLI")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def route_gaps(
    name: str,
    top_n: int,
    json_output: bool,
    execute_fills: bool,
    budget: float,
    dry_run: bool,
    scheduled: bool,
    jitter: float,
    local: bool,
    api: bool,
    plan: str | None,
    plan_model: str | None,
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

    if execute_fills:
        try:
            _validate_gap_fill_backend_flags(local=local, api=api, plan=plan, plan_model=plan_model)
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)
        if jitter < 0:
            print_error("--jitter must be non-negative.")
            sys.exit(2)

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    gaps = profile.get_manifest().top_gaps(top_n)
    routes = GapRouter().route(gaps)

    if execute_fills:
        try:
            backend = _resolve_gap_fill_backend(local, api, plan, plan_model)
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)

        research_routes = [r for r in routes if r.instrument == "research"]
        if not routes:
            print_success("No open knowledge gaps to fill.")
            return

        # A scheduled recurring fill waits for cheap capacity instead of paying;
        # owned/prepaid (local or plan) proceeds because it is not metered spend.
        if scheduled and not dry_run and research_routes and not backend.owned_or_prepaid:
            if json_output:
                payload = _scheduled_gap_fill_wait_payload(profile.name, routes, budget=budget, top_n=top_n)
                click.echo(_json.dumps(payload, indent=2))
                return
            _emit_scheduled_gap_fill_wait(profile.name, routes, budget=budget, top_n=top_n)
            return
        if not dry_run and not yes:
            if backend.owned_or_prepaid:
                where = "the local model at $0" if backend.use_local else f"plan quota ({backend.plan_backend_id})"
                prompt = (
                    f"Execute up to {len(research_routes)} research fill(s) on {where}? Specialist routes are deferred."
                )
            else:
                est = min(sum(max(r.estimated_cost, 0.05) for r in research_routes), budget)
                prompt = (
                    f"Execute up to {len(research_routes)} research fill(s), estimated up to ${est:.2f} "
                    f"(ceiling ${budget:.2f})? Specialist routes are deferred."
                )
            if not click.confirm(prompt, default=False):
                print_warning("Cancelled.")
                return

        if dry_run:
            engine, capacity_source = _build_gap_fill_engine(
                profile,
                use_local=backend.use_local,
                local_model=backend.local_model,
                use_plan=backend.use_plan,
                plan_backend_id=backend.plan_backend_id,
                plan_model=backend.plan_model,
                selection_note=backend.note,
                json_output=json_output,
                spend_decision_fn=None,
            )
            result = asyncio.run(engine.execute(routes, budget=budget, top=top_n, dry_run=True))
            loop_run = None
        else:
            if jitter > 0:
                from deepr.experts.loop_lock import apply_startup_jitter

                apply_startup_jitter(profile.name, jitter)

            from deepr.experts.loop_lock import expert_verb_lock

            capacity_source = _selected_gap_fill_capacity_source(backend)
            spend_decision_fn = _automatic_gap_fill_spend_decider(
                profile.name,
                backend,
                api=api,
                dry_run=dry_run,
            )
            with expert_verb_lock(profile.name, "route-gaps") as acquired:
                if not acquired:
                    result = _gap_fill_overlap_result(profile.name)
                    loop_run = _record_gap_fill_overlap_loop(
                        profile.name,
                        budget=budget,
                        scheduled=scheduled,
                        capacity_source=capacity_source,
                    )
                else:
                    engine, capacity_source = _build_gap_fill_engine(
                        profile,
                        use_local=backend.use_local,
                        local_model=backend.local_model,
                        use_plan=backend.use_plan,
                        plan_backend_id=backend.plan_backend_id,
                        plan_model=backend.plan_model,
                        selection_note=backend.note,
                        json_output=json_output,
                        spend_decision_fn=spend_decision_fn,
                    )
                    result = asyncio.run(engine.execute(routes, budget=budget, top=top_n, dry_run=False))
                    loop_run = _record_completed_gap_fill_loop(
                        profile.name,
                        result,
                        budget=budget,
                        scheduled=scheduled,
                        capacity_source=capacity_source,
                    )

        if json_output:
            payload = result.to_dict()
            if loop_run is not None:
                payload["loop_run"] = loop_run.to_dict()
            click.echo(_json.dumps(payload, indent=2))
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
