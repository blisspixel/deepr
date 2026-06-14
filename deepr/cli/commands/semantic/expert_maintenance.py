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
        if selection_note:
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
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def sync_cmd(
    name: str, budget: float, sync_all: bool, dry_run: bool, local: bool, api: bool, yes: bool, json_output: bool
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
    """
    import json as _json
    import sys

    if local and api:
        print_error("Use either --local or --api, not both.")
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
        from deepr.backends.local import default_local_model, make_local_research_fn

        local_model = default_local_model()
        if not local_model:
            print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
            sys.exit(2)
        if selection_note:
            console.print(f"[dim]{selection_note}[/dim]")
        engine = ExpertSyncEngine(profile, research_fn=make_local_research_fn(local_model))
    else:
        engine = ExpertSyncEngine(profile)
    result = asyncio.run(engine.sync(budget=budget, only_due=not sync_all, dry_run=dry_run))

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
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
