"""Expert maintenance commands: absorb (report -> knowledge) and sync (freshness).

Extracted from experts.py (Phase Q3 decomposition) so these commands can evolve
without pushing the legacy experts module past its file-size ceiling. Registered
on the `expert` group; experts.py imports this module at its bottom so the
decorators run.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

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
from deepr.cli.commands.semantic.expert_sync_support import (
    SYNC_CAPACITY_GATE_KIND,
    SYNC_CAPACITY_GATE_SCHEMA_VERSION,
    _build_sync_capacity_payload,
    _emit_capacity_block,
    _emit_scheduled_capacity_wait,
    _record_completed_sync_loop,
    _run_sync_with_loop_guard,
    _sync_context_builder,
    _sync_context_mode,
)
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.grounding_support import (
    PLAN_BACKEND_CHOICES,
    absorber_kwargs,
    build_grounding_checker,
    validate_grounding_flags,
)

__all__ = [
    "SYNC_CAPACITY_GATE_KIND",
    "SYNC_CAPACITY_GATE_SCHEMA_VERSION",
    "_build_sync_capacity_payload",
    "_record_completed_sync_loop",
]


async def _refresh_absorb_belief_embeddings(
    absorber: Any,
    *,
    name: str,
    model: str | None,
    budget_usd: float,
    estimated_cost_per_belief: float,
    cost_per_1k_tokens: float,
    max_beliefs: int | None,
) -> Any:
    import os

    from openai import AsyncOpenAI

    from deepr.experts.belief_embedding_api import DEFAULT_OPENAI_BELIEF_EMBEDDING_MODEL, OpenAIEmbeddingBatcher
    from deepr.experts.belief_embedding_refresh import refresh_missing_belief_embeddings
    from deepr.experts.cost_safety import get_cost_safety_manager

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for --refresh-belief-embeddings")

    embedding_model = model or DEFAULT_OPENAI_BELIEF_EMBEDDING_MODEL
    batcher = OpenAIEmbeddingBatcher(
        AsyncOpenAI(api_key=api_key),
        model=embedding_model,
        cost_safety=get_cost_safety_manager(),
        session_id=f"absorb:{name}:belief-embedding-refresh",
        budget_usd=budget_usd,
        cost_per_1k_tokens=cost_per_1k_tokens,
    )
    return await refresh_missing_belief_embeddings(
        absorber.belief_store,
        batcher,
        model=embedding_model,
        budget_usd=budget_usd,
        estimated_cost_per_belief=estimated_cost_per_belief,
        max_beliefs=max_beliefs,
        metadata={"source": "expert_absorb", "expert_name": name},
    )


@expert.command(name="absorb")
@click.argument("name")
@click.argument("report_id", required=False)
@click.option(
    "--file",
    "doc_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Absorb a local document instead of a report id (provenance = the filename). $0 with --local.",
)
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
@click.option(
    "--plan",
    "plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Run extraction on a plan-quota CLI backend (prepaid subscription capacity). See: deepr capacity",
)
@click.option("--plan-model", "plan_model", default=None, help="Model to pass to the plan-quota CLI")
@click.option("--check-grounding", is_flag=True, help="Check absorbed claims with a fresh-context verifier")
@click.option(
    "--checker-plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Use this plan-quota CLI as the grounding checker",
)
@click.option("--checker-plan-model", default=None, help="Model to pass to the checker plan CLI")
@click.option(
    "--refresh-belief-embeddings",
    is_flag=True,
    help="After a successful API absorb, refresh missing belief recall embeddings inside the supplied embedding budget",
)
@click.option("--embedding-model", default=None, help="Embedding model for --refresh-belief-embeddings")
@click.option(
    "--embedding-budget",
    type=float,
    default=0.05,
    show_default=True,
    help="Maximum embedding spend for --refresh-belief-embeddings",
)
@click.option(
    "--embedding-estimate-per-belief",
    type=float,
    default=0.00002,
    show_default=True,
    help="Preflight estimate per belief before embedding refresh calls the provider",
)
@click.option(
    "--embedding-cost-per-1k-tokens",
    type=float,
    default=0.00002,
    show_default=True,
    help="Cost estimate used to reserve and settle embedding refresh token spend",
)
@click.option(
    "--embedding-max-beliefs",
    type=int,
    default=None,
    help="Maximum missing or stale beliefs to refresh in one absorb run",
)
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.option("--json", "json_output", is_flag=True, help="Emit the structured absorption result as JSON")
def absorb_report(
    name: str,
    report_id: str | None,
    doc_file: str | None,
    min_confidence: float,
    model: str | None,
    dry_run: bool,
    local: bool,
    api: bool,
    plan: str | None,
    plan_model: str | None,
    check_grounding: bool,
    checker_plan: str | None,
    checker_plan_model: str | None,
    refresh_belief_embeddings: bool,
    embedding_model: str | None,
    embedding_budget: float,
    embedding_estimate_per_belief: float,
    embedding_cost_per_1k_tokens: float,
    embedding_max_beliefs: int | None,
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
      deepr expert absorb "MCP Expert" --file docs/design/mcp.md --local -y
    """
    import json as _json
    import sys

    if sum(bool(x) for x in (local, api, plan)) > 1:
        print_error("Use only one of --local, --api, or --plan.")
        sys.exit(2)
    if refresh_belief_embeddings and dry_run:
        print_error("--refresh-belief-embeddings cannot be combined with --dry-run.")
        sys.exit(2)
    if refresh_belief_embeddings and embedding_budget < 0:
        print_error("--embedding-budget must be non-negative.")
        sys.exit(2)
    if refresh_belief_embeddings and embedding_estimate_per_belief < 0:
        print_error("--embedding-estimate-per-belief must be non-negative.")
        sys.exit(2)
    if refresh_belief_embeddings and embedding_cost_per_1k_tokens < 0:
        print_error("--embedding-cost-per-1k-tokens must be non-negative.")
        sys.exit(2)
    if refresh_belief_embeddings and embedding_max_beliefs is not None and embedding_max_beliefs < 1:
        print_error("--embedding-max-beliefs must be at least 1.")
        sys.exit(2)
    try:
        validate_grounding_flags(
            check_grounding=check_grounding,
            checker_plan=checker_plan,
            checker_plan_model=checker_plan_model,
        )
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    if bool(report_id) == bool(doc_file):
        print_error("Provide exactly one of REPORT_ID or --file.")
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

    # Resolve the source text. A local file (--file) is the $0 way to seed an
    # expert from repo docs or papers with no web research; otherwise resolve a
    # report/job id to its full text via the context index. Provenance is the
    # filename ("file:<name>") or the report id, so absorbed beliefs stay traceable.
    if doc_file:
        from pathlib import Path as _Path

        report_text = _Path(doc_file).read_text(encoding="utf-8", errors="replace")[:100000]
        report_id = f"file:{_Path(doc_file).name}"
        if not report_text.strip():
            print_error(f"File is empty: {doc_file}")
            sys.exit(2)
    else:
        report_id = report_id or ""
        report_text = ContextIndex().get_report_content(report_id, max_chars=100000)
        if not report_text:
            print_error(f"No report found for id: {report_id}")
            click.echo("Find report/job IDs with: deepr search")
            sys.exit(2)

    run_grounding_checks = check_grounding and not dry_run

    # Pick the backend (capacity waterfall): owned local capacity before metered
    # API. --local forces local (no admission needed); --api or an explicit
    # --model forces the metered path; otherwise an admitted+available local
    # model is used automatically, else metered. Why is always printed below.
    use_local = local
    use_plan = False
    plan_backend_id: str | None = plan
    selection_note = ""
    if plan:
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(plan)
        if not choice.is_plan_quota:
            print_error(choice.reason)
            sys.exit(2)
        use_plan = True
        plan_backend_id = choice.plan_backend_id
        selection_note = choice.reason
    elif not local and not api and model is None:
        from deepr.backends.admission import TASK_CLASS_ABSORB
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_ABSORB)
        use_local = choice.is_local
        use_plan = choice.is_plan_quota
        plan_backend_id = choice.plan_backend_id
        if use_local:
            model = choice.model
            selection_note = choice.reason
        elif use_plan:
            selection_note = choice.reason

    if refresh_belief_embeddings and (use_local or use_plan):
        print_error("--refresh-belief-embeddings currently requires the metered API embedding path; use --api.")
        sys.exit(2)

    if use_local:
        from deepr.backends.local import default_local_model, ollama_chat_client

        local_model = model or default_local_model()
        if not local_model:
            print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
            sys.exit(2)
        local_client = ollama_chat_client()
        try:
            grounding_checker = build_grounding_checker(
                enabled=run_grounding_checks,
                checker_plan=checker_plan,
                checker_plan_model=checker_plan_model,
                maker_vendor="local",
                default_client=local_client,
                default_vendor="local",
                default_model=local_model,
            )
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)
        absorber = ReportAbsorber(
            profile,
            **absorber_kwargs(
                model=local_model,
                client=local_client,
                grounding_checker=grounding_checker,
                estimated_cost=0.0,
            ),
        )
        cost_note = f"$0 (local model {local_model})"
        if selection_note and not json_output:
            console.print(f"[dim]{selection_note}[/dim]")
    elif use_plan:
        from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter

        plan_adapter = get_adapter(plan_backend_id or "")
        client = PlanQuotaChatClient(plan_adapter, model=plan_model)
        try:
            grounding_checker = build_grounding_checker(
                enabled=run_grounding_checks,
                checker_plan=checker_plan,
                checker_plan_model=checker_plan_model,
                maker_vendor=plan_adapter.backend_id,
                default_client=client,
                default_vendor=plan_adapter.backend_id,
                default_model=plan_model or plan_adapter.backend_id,
            )
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)
        absorber = ReportAbsorber(
            profile,
            **absorber_kwargs(
                model=plan_model or plan_adapter.backend_id,
                client=client,
                grounding_checker=grounding_checker,
                estimated_cost=0.0,
            ),
        )
        cost_note = "billed per use" if plan_adapter.metered_at_margin else "$0 at the margin (prepaid plan)"
        if selection_note and not json_output:
            console.print(f"[dim]{selection_note}[/dim]")
        if plan_adapter.tos_note and not json_output:
            print_warning(plan_adapter.tos_note)
    else:
        try:
            grounding_checker = build_grounding_checker(
                enabled=run_grounding_checks,
                checker_plan=checker_plan,
                checker_plan_model=checker_plan_model,
                maker_vendor="api_metered",
            )
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)
        absorber = ReportAbsorber(
            profile,
            **absorber_kwargs(model=model or "gpt-5-mini", grounding_checker=grounding_checker),
        )
        cost_note = f"~${ESTIMATED_EXTRACTION_COST:.2f}"

    # Confirm before the extraction call (cost is incurred whether or not we
    # write, so gate it even for --dry-run; local is $0 but still confirmed).
    if not yes:
        intent = "preview (writes nothing)" if dry_run else f"absorb into '{name}'"
        extras = []
        if run_grounding_checks:
            extras.append("grounding checks")
        if refresh_belief_embeddings:
            extras.append(f"belief embedding refresh <= ${embedding_budget:.2f}")
        check_note = f" + {' + '.join(extras)}" if extras else ""
        if not click.confirm(f"Run extraction{check_note} ({cost_note}) and {intent}?", default=False):
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

    embedding_refresh = None
    if refresh_belief_embeddings and not result.dry_run:
        try:
            embedding_refresh = asyncio.run(
                _refresh_absorb_belief_embeddings(
                    absorber,
                    name=name,
                    model=embedding_model,
                    budget_usd=embedding_budget,
                    estimated_cost_per_belief=embedding_estimate_per_belief,
                    cost_per_1k_tokens=embedding_cost_per_1k_tokens,
                    max_beliefs=embedding_max_beliefs,
                )
            )
        except ValueError as e:
            print_error(str(e))
            sys.exit(2)
        except Exception as e:
            print_error(f"Belief embedding refresh failed: {e}")
            sys.exit(1)

    if not result.dry_run:
        # Record the spend + refresh timestamp on the profile, then persist.
        profile.total_research_cost += result.estimated_cost
        profile.last_knowledge_refresh = datetime.now(UTC)
        store.save(profile)

    if json_output:
        payload = result.to_dict()
        if embedding_refresh is not None:
            payload["belief_embedding_refresh"] = embedding_refresh.to_dict()
        click.echo(_json.dumps(payload, indent=2))
        return

    print_header(f"Absorb report into {result.expert_name}")
    if result.dry_run:
        console.print("[yellow]DRY RUN[/yellow] - nothing written")
    if embedding_refresh is not None:
        if embedding_refresh.status == "indexed":
            print_success(
                f"Belief embeddings refreshed: {embedding_refresh.indexed_count}/{embedding_refresh.requested_count}"
            )
        elif embedding_refresh.status == "up_to_date":
            console.print("[dim]Belief embeddings already up to date.[/dim]")
        else:
            print_warning(
                f"Belief embedding refresh {embedding_refresh.status}: {embedding_refresh.blocked_reason or embedding_refresh.errors}"
            )
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
    "--plan",
    "plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Run sync on a plan-quota CLI backend (prepaid subscription capacity). See: deepr capacity",
)
@click.option(
    "--plan-model",
    "plan_model",
    default=None,
    help="Model to pass to the plan-quota CLI (e.g. anthropic/claude-sonnet-4-6 for --plan opencode)",
)
@click.option("--check-grounding", is_flag=True, help="Check absorbed claims with a fresh-context verifier")
@click.option(
    "--compile-claims",
    is_flag=True,
    help="Compile, verify, and apply source-note claim graph commits",
)
@click.option(
    "--stage-compiled-claims",
    is_flag=True,
    help="With --compile-claims, write compiler sidecars without applying graph commits",
)
@click.option(
    "--apply-compiled-claims",
    is_flag=True,
    help="Compatibility alias for the default --compile-claims apply behavior",
)
@click.option(
    "--checker-plan",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Use this plan-quota CLI as the grounding checker",
)
@click.option("--checker-plan-model", default=None, help="Model to pass to the checker plan CLI")
@click.option(
    "--fresh-context",
    is_flag=True,
    help="For local/plan sync, retrieve free web context before calling the model",
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
@click.option(
    "--jitter",
    type=float,
    default=0.0,
    show_default=True,
    help="Maximum startup jitter in seconds before a non-dry sync run",
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
    plan: str | None,
    plan_model: str | None,
    check_grounding: bool,
    compile_claims: bool,
    stage_compiled_claims: bool,
    apply_compiled_claims: bool,
    checker_plan: str | None,
    checker_plan_model: str | None,
    fresh_context: bool,
    deep_context: bool,
    scheduled: bool,
    jitter: float,
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

    if sum(bool(x) for x in (local, api, plan)) > 1:
        print_error("Use only one of --local, --api, or --plan.")
        sys.exit(2)
    try:
        validate_grounding_flags(
            check_grounding=check_grounding,
            checker_plan=checker_plan,
            checker_plan_model=checker_plan_model,
        )
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)
    if fresh_context and api:
        print_error("--fresh-context is only supported for local or plan sync.")
        sys.exit(2)
    if deep_context and api:
        print_error("--deep-context is only supported for local or plan sync.")
        sys.exit(2)
    if jitter < 0:
        print_error("--jitter must be non-negative.")
        sys.exit(2)
    if apply_compiled_claims and not compile_claims:
        print_error("--apply-compiled-claims requires --compile-claims.")
        sys.exit(2)
    if apply_compiled_claims and dry_run:
        print_error("--apply-compiled-claims cannot be combined with --dry-run.")
        sys.exit(2)
    if stage_compiled_claims and not compile_claims:
        print_error("--stage-compiled-claims requires --compile-claims.")
        sys.exit(2)
    if stage_compiled_claims and apply_compiled_claims:
        print_error("--stage-compiled-claims cannot be combined with --apply-compiled-claims.")
        sys.exit(2)
    apply_compiled_graph_commits = compile_claims and not stage_compiled_claims

    from deepr.experts.profile import ExpertStore
    from deepr.experts.sync import SubscriptionStore

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

    # Pick the backend (capacity waterfall): owned local then prepaid plan-quota
    # before metered API. --local/--api/--plan force a rung; otherwise the
    # waterfall auto-selects (local if admitted+available, else metered; plan is
    # auto-routed only with an observed quota window - see choose_maintenance_backend).
    use_local = local
    use_plan = False
    plan_backend_id: str | None = plan
    selection_note = ""
    if plan:
        from deepr.backends.waterfall import choose_plan_quota_backend

        choice = choose_plan_quota_backend(plan)
        if not choice.is_plan_quota:
            print_error(choice.reason)
            sys.exit(2)
        use_plan = True
        plan_backend_id = choice.plan_backend_id
        selection_note = choice.reason
    elif not local and not api:
        from deepr.backends.admission import TASK_CLASS_SYNC
        from deepr.backends.waterfall import choose_maintenance_backend

        choice = choose_maintenance_backend(TASK_CLASS_SYNC)
        use_local = choice.is_local
        use_plan = choice.is_plan_quota
        plan_backend_id = choice.plan_backend_id
        if use_local or use_plan:
            selection_note = choice.reason

    owned_or_prepaid = use_local or use_plan
    context_mode = _sync_context_mode(fresh_context=fresh_context, deep_context=deep_context)
    if scheduled and not api and not owned_or_prepaid:
        _emit_scheduled_capacity_wait(
            name,
            context_mode=context_mode,
            json_output=json_output,
            detail="scheduled sync is waiting for owned/prepaid capacity instead of using metered API",
            profile=profile,
        )
        return

    if (fresh_context or deep_context) and not owned_or_prepaid:
        _emit_capacity_block(
            name,
            context_mode=context_mode,
            json_output=json_output,
            detail="fresh/deep context requires a local or plan-quota sync backend",
            profile=profile,
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
                    profile=profile,
                )
                return
            print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
            sys.exit(2)

    plan_adapter = None
    if use_plan:
        from deepr.backends.plan_quota import get_adapter

        plan_adapter = get_adapter(plan_backend_id or "")

    grounding_checker = None
    run_grounding_checks = check_grounding and not dry_run
    if run_grounding_checks:
        try:
            if use_local:
                from deepr.backends.local import ollama_chat_client

                default_checker_client = None if checker_plan else ollama_chat_client()
                grounding_checker = build_grounding_checker(
                    enabled=True,
                    checker_plan=checker_plan,
                    checker_plan_model=checker_plan_model,
                    maker_vendor="local",
                    default_client=default_checker_client,
                    default_vendor="local",
                    default_model=local_model,
                )
            elif use_plan and plan_adapter is not None:
                from deepr.backends.plan_quota import PlanQuotaChatClient

                default_checker_client = (
                    None
                    if checker_plan
                    else PlanQuotaChatClient(plan_adapter, model=plan_model, operation="plan_quota_grounding_check")
                )
                grounding_checker = build_grounding_checker(
                    enabled=True,
                    checker_plan=checker_plan,
                    checker_plan_model=checker_plan_model,
                    maker_vendor=plan_adapter.backend_id,
                    default_client=default_checker_client,
                    default_vendor=plan_adapter.backend_id,
                    default_model=plan_model or plan_adapter.backend_id,
                )
            else:
                grounding_checker = build_grounding_checker(
                    enabled=True,
                    checker_plan=checker_plan,
                    checker_plan_model=checker_plan_model,
                    maker_vendor="api_metered",
                )
        except ValueError as exc:
            print_error(str(exc))
            sys.exit(2)

    if not dry_run and not yes:
        extras = []
        if run_grounding_checks:
            extras.append("grounding checks")
        if compile_claims:
            extras.append("claim compilation")
        if apply_compiled_graph_commits:
            extras.append("graph commit apply")
        check_note = f" with {' and '.join(extras)}" if extras else ""
        if use_local:
            prompt = f"Sync {len(targets)} topic(s){check_note} on the local model at $0?"
        elif use_plan and plan_adapter is not None:
            if plan_adapter.metered_at_margin:
                cost_desc = f"billed per use, budget ceiling ${budget:.2f}"
                if compile_claims:
                    from deepr.experts.claim_verification import ESTIMATED_VERIFICATION_COST
                    from deepr.experts.report_absorber import ESTIMATED_EXTRACTION_COST

                    claim_est = len(targets) * (ESTIMATED_EXTRACTION_COST + ESTIMATED_VERIFICATION_COST)
                    cost_desc += f", claim compilation estimate ${claim_est:.2f}"
            else:
                cost_desc = "$0 at the margin (prepaid plan)"
            prompt = f"Sync {len(targets)} topic(s){check_note} via {plan_adapter.display_name} ({cost_desc})?"
        else:
            from deepr.experts.report_absorber import ESTIMATED_EXTRACTION_COST

            est = sum(min(s.budget, budget) for s in targets)
            if compile_claims:
                from deepr.experts.claim_verification import ESTIMATED_VERIFICATION_COST

                est += len(targets) * ESTIMATED_EXTRACTION_COST
                est += len(targets) * ESTIMATED_VERIFICATION_COST
            prompt = f"Sync {len(targets)} topic(s){check_note}, estimated up to ${min(est, budget):.2f}?"
        if not click.confirm(prompt, default=False):
            print_warning("Cancelled.")
            return

    if (use_local or use_plan) and selection_note and not json_output:
        console.print(f"[dim]{selection_note}[/dim]")
    if use_plan and plan_adapter is not None and plan_adapter.tos_note and not json_output:
        print_warning(plan_adapter.tos_note)
    context_builder = (
        _sync_context_builder(fresh_context=fresh_context, deep_context=deep_context, json_output=json_output)
        if (use_local or use_plan)
        else None
    )
    result, loop_run, _ = _run_sync_with_loop_guard(
        profile,
        name=name,
        budget=budget,
        sync_all=sync_all,
        dry_run=dry_run,
        scheduled=scheduled,
        jitter=jitter,
        use_local=use_local,
        local_model=local_model,
        use_plan=use_plan,
        plan_adapter=plan_adapter,
        plan_model=plan_model,
        context_builder=context_builder,
        grounding_checker=grounding_checker,
        compile_claims=compile_claims,
        apply_graph_commits=apply_compiled_graph_commits,
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
            if o.graph_commit_apply_status:
                line += f"  [dim](graph apply {o.graph_commit_apply_status}, {o.absorbed} writes, ${o.cost:.3f})[/dim]"
            else:
                line += f"  [dim](+{o.absorbed} beliefs, {o.flagged} contested, ${o.cost:.3f})[/dim]"
        elif o.detail:
            line += f"  [dim]{o.detail[:90]}[/dim]"
        if o.source_pack_artifact:
            line += f"  [dim](sources {o.source_count}; {o.source_pack_artifact})[/dim]"
        if o.claim_extraction_artifact:
            line += f"  [dim](claims {o.claim_extraction_artifact})[/dim]"
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


def run_learn_web_pipeline(**kwargs) -> None:
    """Compatibility wrapper for `expert learn` and existing tests."""
    from deepr.cli.commands.semantic.expert_learn_web import run_learn_web_pipeline as _run_learn_web_pipeline

    _run_learn_web_pipeline(**kwargs)


# Register the sibling `expert sync-all` maintenance command. It lives in its own
# module (kept lean) but registers here rather than in experts.py, which is at
# its grandfathered file-size cap (the registry line would trip the ratchet).
from deepr.cli.commands.semantic import expert_graph_commit as _expert_graph_commit  # noqa: F401
from deepr.cli.commands.semantic import expert_learn_web as _expert_learn_web  # noqa: F401
from deepr.cli.commands.semantic import expert_sync_all as _expert_sync_all  # noqa: F401
