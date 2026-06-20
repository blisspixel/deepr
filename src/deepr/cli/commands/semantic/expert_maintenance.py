"""Expert maintenance commands: absorb (report -> knowledge) and sync (freshness).

Extracted from experts.py (Phase Q3 decomposition) so that over-ceiling file
stops growing and these commands can gain the --local flag, which runs them on
a local Ollama model at $0 (capacity release, v2.16) - the affordable path for
background expert maintenance. Registered on the `expert` group; experts.py
imports this module at its bottom so the decorators run.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import click

from deepr.cli.colors import (
    console,
    print_error,
    print_header,
    print_list_item,
    print_section_header,
    print_success,
    print_warning,
)
from deepr.cli.commands.semantic.experts import expert

SYNC_CAPACITY_GATE_KIND = "deepr.expert.sync_capacity_gate"
SYNC_CAPACITY_GATE_SCHEMA_VERSION = "deepr-sync-capacity-gate-v1"


@expert.command(name="absorb")
@click.argument("name")
@click.argument("report_id")
@click.option(
    "--min-confidence",
    type=float,
    default=0.6,
    show_default=True,
    help="Drop candidate claims the report supports more weakly than this",
)
@click.option("--model", default=None, help="Override the extraction model (default: gpt-5-mini)")
@click.option("--dry-run", is_flag=True, help="Preview what would be absorbed; write nothing (still runs extraction)")
@click.option(
    "--local",
    is_flag=True,
    help="Force extraction on the local Ollama model at $0 (no admission needed)",
)
@click.option("--api", is_flag=True, help="Force the metered API even if a local model is admitted")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.option("--json", "json_output", is_flag=True, help="Emit the structured absorption result as JSON")
def absorb_report(
    name: str,
    report_id: str,
    min_confidence: float,
    model: str | None,
    dry_run: bool,
    local: bool,
    api: bool,
    yes: bool,
    json_output: bool,
):
    """Promote a completed research report into an expert's permanent knowledge.

    Extracts report-grounded claims, gates them (drops weak claims and any that
    contradict the expert's existing beliefs), then integrates the survivors as
    beliefs with the report id recorded as provenance. Deduped against existing
    beliefs, so re-absorbing only adds the delta.

    Costs one small extraction call (~$0.03), or $0 on a local model - forced
    with --local, or automatically when one is admitted for absorb (see
    `deepr capacity admit`). Use --dry-run to preview claims without writing.

    REPORT_ID is the job id of a completed report (the same id you pass to
    `deepr research --context`; find it with `deepr search`). A job-id prefix
    also resolves.

    EXAMPLES:
      deepr expert absorb "AI Strategy Expert" <job_id>
      deepr expert absorb "AI Strategy Expert" <job_id> --dry-run
      deepr expert absorb "AI Strategy Expert" <job_id> --local -y
    """
    import json as _json
    import sys

    if local and api:
        print_error("Use either --local or --api, not both.")
        sys.exit(2)

    from deepr.experts.profile import ExpertStore
    from deepr.experts.report_absorber import ESTIMATED_EXTRACTION_COST, ReportAbsorber, ReportAbsorberError
    from deepr.services.context_index import ContextIndex

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    # Resolve the report id (or job id) to its full text via the context index.
    index = ContextIndex()
    report_text = index.get_report_content(report_id, max_chars=100000)
    if not report_text:
        print_error(f"No report found for id: {report_id}")
        click.echo("Find report/job IDs with: deepr search")
        sys.exit(2)

    # Pick the backend (capacity waterfall): owned local capacity before metered
    # API. --local forces local (no admission needed); --api or an explicit
    # --model forces the metered path; otherwise an admitted+available local
    # model is used automatically, else metered. Why is always printed below.
    use_local = local
    selection_note = ""
    if not local and not api and model is None:
        from deepr.backends.admission import TASK_CLASS_ABSORB
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_ABSORB)
        use_local = choice.is_local
        if use_local:
            model = choice.model
            selection_note = choice.reason

    if use_local:
        from deepr.backends.local import default_local_model, ollama_chat_client

        local_model = model or default_local_model()
        if not local_model:
            print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
            sys.exit(2)
        absorber = ReportAbsorber(profile, model=local_model, client=ollama_chat_client())
        cost_note = f"$0 (local model {local_model})"
        if selection_note and not json_output:
            console.print(f"[dim]{selection_note}[/dim]")
    else:
        absorber = ReportAbsorber(profile, model=model or "gpt-5-mini")
        cost_note = f"~${ESTIMATED_EXTRACTION_COST:.2f}"

    # Confirm before the extraction call (cost is incurred whether or not we
    # write, so gate it even for --dry-run; local is $0 but still confirmed).
    if not yes:
        intent = "preview (writes nothing)" if dry_run else f"absorb into '{name}'"
        if not click.confirm(f"Run extraction ({cost_note}) and {intent}?", default=False):
            print_warning("Cancelled.")
            sys.exit(0)

    try:
        result = asyncio.run(absorber.absorb(report_id, report_text, min_confidence=min_confidence, dry_run=dry_run))
    except ReportAbsorberError as e:
        print_error(str(e))
        sys.exit(2)
    except Exception as e:
        print_error(f"Absorption failed: {e}")
        sys.exit(1)

    if not result.dry_run:
        # Record the spend + refresh timestamp on the profile, then persist.
        profile.total_research_cost += result.estimated_cost
        profile.last_knowledge_refresh = datetime.now(UTC)
        store.save(profile)

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
        return

    print_header(f"Absorb report into {result.expert_name}")
    if result.dry_run:
        console.print("[yellow]DRY RUN[/yellow] - nothing written")
    console.print(
        f"Candidates: {result.total_candidates}  "
        f"Absorbed: {len(result.absorbed)} (added {result.added_count}, merged {result.merged_count})  "
        f"Insufficient: {len(result.insufficient)}  "
        f"Rejected: {len(result.rejected)}  Flagged: {len(result.flagged)}"
    )
    if result.contradictions_refuted or result.merges_blocked:
        console.print(
            f"[dim]Model verdicts caught {result.contradictions_refuted} false contradiction(s) "
            f"and {result.merges_blocked} false merge(s) the word-overlap heuristic flagged.[/dim]"
        )

    if result.absorbed:
        console.print()
        print_section_header("Would absorb" if result.dry_run else "Absorbed")
        for a in result.absorbed:
            print_list_item(f"{a.statement}  [dim](conf {a.confidence:.2f}, {a.outcome})[/dim]")

    if result.flagged:
        console.print()
        print_section_header("Flagged contradictions (recorded as contested, existing beliefs untouched)")
        for f in result.flagged:
            tag = " unverified" if f.verification == "lexical_unverified" and not f.resolution else ""
            console.print(f"  [yellow]![/yellow] {f.statement}  [dim](conf {f.confidence:.2f}, {f.outcome}{tag})[/dim]")
            console.print(
                f"    [dim]contradicts {f.conflicts_with_id}: {f.conflicts_with_claim} "
                f"(conf {f.conflicts_with_confidence:.2f}; better sourced: {f.better_sourced})[/dim]"
            )
            if f.resolution:
                console.print(f"    [dim]adjudication: {f.resolution} - {f.resolution_explanation}[/dim]")
        if any(f.verification == "lexical_unverified" and not f.resolution for f in result.flagged):
            console.print(
                "  [dim]'unverified' = flagged by the free lexical heuristic (high-recall router), "
                "not a confirmed semantic contradiction. Adjudicate to get a model verdict.[/dim]"
            )

    if result.insufficient:
        console.print()
        print_section_header("Insufficient grounding (abstained - not refuted)")
        console.print(
            "  [dim]This report does not support these strongly enough to absorb; "
            "they may still be true. Natural re-research targets.[/dim]"
        )
        for i in result.insufficient:
            console.print(f"  [dim]?[/dim] {i.statement}  [dim](report support {i.confidence:.2f})[/dim]")

    if result.rejected:
        console.print()
        print_section_header("Rejected")
        for r in result.rejected:
            console.print(f"  [dim]-[/dim] {r.statement}")
            console.print(f"    [dim]{r.reason}: {r.detail}[/dim]")

    if not result.absorbed and not result.rejected and not result.flagged and not result.insufficient:
        print_warning("No claims extracted from the report.")
    elif not result.dry_run and (result.absorbed or result.flagged):
        if result.absorbed:
            print_success(
                f"Integrated {len(result.absorbed)} belief(s). Audit anytime: deepr expert health-check '{name}'"
            )
        if result.flagged:
            print_warning(
                f"{len(result.flagged)} contradiction(s) recorded as contested. "
                f"Review with: deepr expert resolve-conflicts '{name}'"
            )


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
) -> dict:
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
    return {
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


def _print_capacity_payload(payload: dict) -> None:
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
) -> None:
    import json as _json

    payload = _build_sync_capacity_payload(
        expert_name,
        context_mode=context_mode,
        scheduled=True,
        status="waiting_for_capacity",
        detail=detail,
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
        capacity_source="owned/prepaid",
    )
    payload["loop_run"] = loop_run.to_dict()
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
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
) -> None:
    import json as _json

    payload = _build_sync_capacity_payload(
        expert_name,
        context_mode=context_mode,
        scheduled=False,
        status="capacity_blocked",
        detail=detail,
    )
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_error(f"{detail}. Use --local or admit a local model first.")
    _print_capacity_payload(payload)


def _record_completed_sync_loop(
    expert_name: str,
    result,
    *,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    use_local: bool,
):
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
        budget_limit=budget,
        budget_spent=float(getattr(result, "total_cost", 0.0) or 0.0),
        capacity_source="local" if use_local else "api_metered",
        accepted_changes=accepted,
        rejected_changes=len(failed),
    )


@expert.command(name="sync")
@click.argument("name")
@click.option("--budget", "-b", type=float, default=2.0, show_default=True, help="Total budget ceiling for this run")
@click.option("--all", "sync_all", is_flag=True, help="Sync every subscription, not just due ones")
@click.option("--dry-run", is_flag=True, help="Show what would sync; no research, no spend")
@click.option(
    "--local",
    is_flag=True,
    help="Force sync research on the local Ollama model at $0 (no admission needed)",
)
@click.option("--api", is_flag=True, help="Force the metered API even if a local model is admitted")
@click.option(
    "--fresh-context",
    is_flag=True,
    help="For local sync, retrieve free web context before calling the local model",
)
@click.option(
    "--deep-context",
    is_flag=True,
    help="For local sync, run multi-query free retrieval before calling the local model",
)
@click.option(
    "--scheduled",
    is_flag=True,
    help="For recurring jobs, wait for cheap capacity instead of falling through to metered API",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def sync_cmd(
    name: str,
    budget: float,
    sync_all: bool,
    dry_run: bool,
    local: bool,
    api: bool,
    fresh_context: bool,
    deep_context: bool,
    scheduled: bool,
    yes: bool,
    json_output: bool,
):
    """Pull deltas for NAME's due subscriptions and integrate what changed.

    For each due topic: researches only what changed since the last sync,
    absorbs the delta through the verification-gated pipeline (dedup +
    contradiction flagging), then reports the perspective delta. Designed
    to run on a schedule - only due subscriptions spend money, or $0 on a local
    model (forced with --local, or automatically when one is admitted for sync
    via `deepr capacity admit`) for background maintenance on owned hardware.

    EXAMPLES:
      deepr expert sync "MCP Interop Expert"
      deepr expert sync "AI Policy Expert" --dry-run
      deepr expert sync "AI Policy Expert" --local -y
      deepr expert sync "AI Policy Expert" --local --fresh-context -y
      deepr expert sync "AI Policy Expert" --local --deep-context -y
      deepr expert sync "AI Policy Expert" --scheduled --fresh-context -y
    """
    import json as _json
    import sys

    if local and api:
        print_error("Use either --local or --api, not both.")
        sys.exit(2)
    if fresh_context and api:
        print_error("--fresh-context is only supported for local sync.")
        sys.exit(2)
    if deep_context and api:
        print_error("--deep-context is only supported for local sync.")
        sys.exit(2)

    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync import ExpertSyncEngine, SubscriptionStore

    profile = ExpertStore().load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        sys.exit(2)

    subs = SubscriptionStore(name)
    targets = subs.subscriptions if sync_all else subs.due()
    if not targets:
        print_success("Nothing to sync - no subscriptions are due.")
        console.print(f"Subscriptions: deepr expert subscriptions '{name}'")
        return

    # Pick the backend (capacity waterfall): owned local capacity before metered
    # API. --local forces local; --api forces metered; otherwise an admitted +
    # available local model is used automatically, else metered.
    use_local = local
    selection_note = ""
    if not local and not api:
        from deepr.backends.admission import TASK_CLASS_SYNC
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_SYNC)
        use_local = choice.is_local
        if use_local:
            selection_note = choice.reason

    context_mode = _sync_context_mode(fresh_context=fresh_context, deep_context=deep_context)
    if scheduled and not api and not use_local:
        _emit_scheduled_capacity_wait(
            name,
            context_mode=context_mode,
            json_output=json_output,
            detail="scheduled sync is waiting for owned/prepaid capacity instead of using metered API",
        )
        return

    if (fresh_context or deep_context) and not use_local:
        _emit_capacity_block(
            name,
            context_mode=context_mode,
            json_output=json_output,
            detail="fresh/deep context requires a local sync backend",
        )
        sys.exit(2)

    local_model = None
    if use_local:
        from deepr.backends.local import default_local_model

        local_model = default_local_model()
        if not local_model:
            if scheduled:
                _emit_scheduled_capacity_wait(
                    name,
                    context_mode=context_mode,
                    json_output=json_output,
                    detail="scheduled local sync is waiting for a running local model",
                )
                return
            print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
            sys.exit(2)

    if not dry_run and not yes:
        if use_local:
            prompt = f"Sync {len(targets)} topic(s) on the local model at $0?"
        else:
            est = sum(min(s.budget, budget) for s in targets)
            prompt = f"Sync {len(targets)} topic(s), estimated up to ${min(est, budget):.2f}?"
        if not click.confirm(prompt, default=False):
            print_warning("Cancelled.")
            return

    if use_local:
        from deepr.backends.local import make_local_research_fn, ollama_chat_client
        from deepr.experts.report_absorber import ReportAbsorber

        if selection_note and not json_output:
            console.print(f"[dim]{selection_note}[/dim]")
        context_builder = None
        if deep_context:
            from deepr.backends.fresh_context import make_free_deep_context_builder

            context_builder = make_free_deep_context_builder()
            console.print(
                "[dim]Deep context enabled: multi-query free-only web retrieval; "
                "API-key search providers are not used.[/dim]"
            )
        elif fresh_context:
            from deepr.backends.fresh_context import make_free_fresh_context_builder

            context_builder = make_free_fresh_context_builder()
            console.print(
                "[dim]Fresh context enabled: free-only web retrieval; API-key search providers are not used.[/dim]"
            )
        absorber = ReportAbsorber(profile, model=local_model, client=ollama_chat_client())
        engine = ExpertSyncEngine(
            profile,
            research_fn=make_local_research_fn(local_model, context_builder=context_builder),
            absorber=absorber,
        )
    else:
        engine = ExpertSyncEngine(profile)
    result = asyncio.run(engine.sync(budget=budget, only_due=not sync_all, dry_run=dry_run))
    loop_run = (
        None
        if dry_run
        else _record_completed_sync_loop(
            name,
            result,
            budget=budget,
            scheduled=scheduled,
            sync_all=sync_all,
            use_local=use_local,
        )
    )

    if json_output:
        payload = result.to_dict()
        if loop_run is not None:
            payload["loop_run"] = loop_run.to_dict()
        click.echo(_json.dumps(payload, indent=2))
        return

    print_header(f"Sync: {name}")
    for o in result.outcomes:
        marker = {
            "synced": "[green]synced[/green]",
            "no_changes": "[dim]no changes[/dim]",
            "would_sync": "[yellow]would sync[/yellow]",
            "skipped": "[yellow]skipped[/yellow]",
            "failed": "[red]failed[/red]",
        }.get(o.status, o.status)
        line = f"  {marker}  {o.topic}"
        if o.status == "synced":
            line += f"  [dim](+{o.absorbed} beliefs, {o.flagged} contested, ${o.cost:.3f})[/dim]"
        elif o.detail:
            line += f"  [dim]{o.detail[:90]}[/dim]"
        if o.source_pack_artifact:
            line += f"  [dim](sources {o.source_count}; {o.source_pack_artifact})[/dim]"
        console.print(line)

    if not dry_run:
        console.print(f"\nTotal cost: ${result.total_cost:.3f}")
        delta = result.delta or {}
        if delta.get("total_changes"):
            console.print(
                f"Perspective delta: {len(delta.get('added', []))} added, "
                f"{len(delta.get('contested', []))} contested, {len(delta.get('revised', []))} revised"
            )
            console.print(f"Inspect: deepr expert what-changed '{name}' --since 1h")
        if any(o.flagged for o in result.outcomes):
            print_warning(f"Contested beliefs recorded. Review: deepr expert contested '{name}'")
