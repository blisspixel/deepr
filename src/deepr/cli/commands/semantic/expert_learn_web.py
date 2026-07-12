"""Replayable live-web topic learning for domain experts."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_header, print_list_item, print_warning
from deepr.cli.commands.semantic.experts import expert


def _emit_retrieval_failures(research: dict[str, Any], *, json_output: bool, source_pack_artifact: str) -> None:
    """Show bounded, secret-free targets for failed page fetches."""
    if json_output:
        return
    source_pack = research.get("source_pack")
    candidates = source_pack.get("retrieval_candidates") if isinstance(source_pack, dict) else None
    if not isinstance(candidates, list):
        return
    failed = [candidate for candidate in candidates if isinstance(candidate, dict) and candidate.get("error")]
    if not failed:
        return
    print_warning(f"{len(failed)} source fetch(es) failed:")
    for candidate in failed[:8]:
        label = str(candidate.get("diagnostic_label", "source") or "source")[:24]
        target = str(candidate.get("diagnostic_target", label) or label)[:240]
        console.print(f"  {label}: {target} (fetch failed)")
    if len(failed) > 8:
        console.print(f"  ... and {len(failed) - 8} more; inspect {source_pack_artifact}")


def _emit_absorb_result(
    result: Any,
    name: str,
    json_output: bool,
    *,
    learn_web_artifacts: dict[str, object] | None = None,
) -> None:
    """Render an absorption result plus its durable retrieval artifacts."""
    if json_output:
        payload = result.to_dict()
        if learn_web_artifacts:
            payload["learn_web_artifacts"] = learn_web_artifacts
        click.echo(json.dumps(payload, indent=2))
        return
    if result.dry_run:
        console.print("[yellow]DRY RUN[/yellow] - nothing written")
    console.print(
        f"Candidates: {result.total_candidates}  Absorbed: {len(result.absorbed)} "
        f"(added {result.added_count}, merged {result.merged_count})  Rejected: {len(result.rejected)}"
    )
    for absorbed in result.absorbed:
        print_list_item(f"{absorbed.statement}  [dim](conf {absorbed.confidence:.2f}, {absorbed.outcome})[/dim]")
    rejection_counts = Counter(str(getattr(rejected, "reason", "unknown") or "unknown") for rejected in result.rejected)
    if rejection_counts:
        grouped = ", ".join(f"{reason}: {count}" for reason, count in sorted(rejection_counts.items()))
        console.print(f"Rejected by reason: {grouped}")
    if learn_web_artifacts:
        console.print(f"Source pack: {learn_web_artifacts['source_pack']}")
        console.print(f"Report: {learn_web_artifacts['report']}")
    console.print(f"\nAudit anytime: deepr expert health-check '{name}'")


def _plan_backend(plan: str, plan_model: str | None, json_output: bool) -> tuple[str, Any, str]:
    from deepr.backends.plan_quota import PlanQuotaChatClient, get_adapter
    from deepr.backends.waterfall import choose_plan_quota_backend

    choice = choose_plan_quota_backend(plan)
    if not choice.is_plan_quota:
        print_error(choice.reason)
        raise click.exceptions.Exit(2)
    adapter = get_adapter(choice.plan_backend_id or "")
    if adapter is None:
        print_error(f"Unknown plan-quota backend: {plan}")
        raise click.exceptions.Exit(2)
    client = PlanQuotaChatClient(adapter, model=plan_model, operation="plan_quota_learn_web")
    selected_model = plan_model or adapter.backend_id
    cost_desc = "billed per use" if adapter.metered_at_margin else "$0 at the margin (prepaid plan)"
    if adapter.tos_note and not json_output:
        print_warning(adapter.tos_note)
    return selected_model, client, f"{adapter.display_name}: {selected_model}  ({cost_desc})"


def _local_backend(model: str | None, profile: Any) -> tuple[str, Any, str]:
    from deepr.backends.local import ollama_chat_client, resolve_local_maintenance_model

    selected_model = resolve_local_maintenance_model(profile, explicit_model=model)
    if not selected_model:
        print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
        raise click.exceptions.Exit(2)
    return selected_model, ollama_chat_client(), f"Local model: {selected_model}  ($0, owned hardware)"


def _backend(
    model: str | None,
    plan: str | None,
    plan_model: str | None,
    json_output: bool,
    profile: Any,
) -> tuple[str, Any, str]:
    if model and plan:
        print_error("Use only one of --model or --plan.")
        raise click.exceptions.Exit(2)
    if plan:
        return _plan_backend(plan, plan_model, json_output)
    return _local_backend(model, profile)


def _load_expert_state_or_exit(name: str) -> tuple[Any, Any, Path]:
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)
    expert_root = store.find_existing_dir(name)
    if expert_root is None:
        print_error(f"Expert storage directory not found: {name}")
        sys.exit(2)
    return store, profile, expert_root


def run_learn_web_pipeline(
    *,
    name: str,
    topic: str,
    model: str | None,
    plan: str | None,
    plan_model: str | None,
    num_results: int,
    max_pages: int,
    min_confidence: float,
    save_path: str | None,
    dry_run: bool,
    yes: bool,
    json_output: bool,
    title: str,
) -> None:
    """Research a topic with free web retrieval, then absorb verified beliefs."""
    from deepr.experts.learn_web_artifacts import LearnWebArtifactError, persist_learn_web_artifacts
    from deepr.experts.local_research import research_web_local
    from deepr.experts.report_absorber import ReportAbsorber, ReportAbsorberError

    store, profile, expert_root = _load_expert_state_or_exit(name)

    model, client, run_label = _backend(model, plan, plan_model, json_output, profile)

    print_header(title)
    console.print(f"  Topic: {topic}")
    console.print(f"  {run_label}")
    if not yes and not click.confirm("\nSearch the live web and absorb findings?", default=True):
        print_warning("Cancelled.")
        sys.exit(0)

    console.print("[dim]Searching the web, fetching pages, and synthesizing without metered spend...[/dim]")
    started_at = datetime.now(UTC)
    research = asyncio.run(
        research_web_local(topic, model=model, client=client, num_results=num_results, max_pages=max_pages)
    )
    try:
        artifacts = persist_learn_web_artifacts(
            expert_root=expert_root,
            expert_name=profile.name,
            topic=topic,
            research=research,
            started_at=started_at,
        )
    except LearnWebArtifactError as exc:
        print_error(str(exc))
        sys.exit(1)

    _emit_retrieval_failures(research, json_output=json_output, source_pack_artifact=artifacts.source_pack)

    report = research.get("answer") or ""
    if not report:
        print_error(f"Web research produced no report: {research.get('error', 'empty')}")
        console.print(f"[dim]Attempt source pack: {artifacts.source_pack}[/dim]")
        sys.exit(1)
    if not artifacts.source_ref_catalog:
        print_error("Web research report has no replayable source-note provenance; beliefs were not changed.")
        sys.exit(1)
    console.print(
        f"[dim]Synthesized a report from {len(research.get('sources', []))} content-addressed live source(s).[/dim]"
    )
    if save_path:
        Path(save_path).write_text(report, encoding="utf-8")
        console.print(f"[dim]Report saved: {save_path}[/dim]")

    absorber = ReportAbsorber(profile, model=model, client=client, estimated_cost=0.0)
    try:
        result = asyncio.run(
            absorber.absorb(
                artifacts.report_id,
                report,
                min_confidence=min_confidence,
                dry_run=dry_run,
                source_ref_catalog=artifacts.source_ref_catalog,
            )
        )
    except ReportAbsorberError as exc:
        print_error(str(exc))
        sys.exit(2)

    from deepr.experts.knowledge_freshness import advance_from_absorption

    knowledge_changed = advance_from_absorption(profile, result)
    if knowledge_changed:
        store.save(profile)
    elif not result.dry_run:
        print_warning("No beliefs or contested signals were accepted; knowledge freshness was not advanced.")

    _emit_absorb_result(
        result,
        name,
        json_output,
        learn_web_artifacts={
            "source_pack": artifacts.source_pack,
            "source_pack_manifest": artifacts.source_pack_manifest,
            "source_notes": artifacts.source_notes,
            "report": artifacts.report,
        },
    )


@expert.command(name="learn-web")
@click.argument("name")
@click.argument("topic")
@click.option(
    "--model",
    default=None,
    help="Local Ollama model for synthesis + extraction. Pick for quality; runtime does not matter.",
)
@click.option(
    "--plan",
    "plan",
    default=None,
    help="Use a plan-quota CLI backend for synthesis + extraction. See: deepr capacity",
)
@click.option("--plan-model", "plan_model", default=None, help="Model to pass to the plan-quota CLI")
@click.option(
    "--num-results",
    type=click.IntRange(min=1, max=20),
    default=8,
    show_default=True,
    help="Web results to retrieve",
)
@click.option(
    "--max-pages",
    type=click.IntRange(min=1, max=8),
    default=5,
    show_default=True,
    help="Top results to fetch in full",
)
@click.option("--min-confidence", type=float, default=0.6, show_default=True, help="Drop weaker claims")
@click.option("--save", "save_path", type=click.Path(), default=None, help="Also save the report markdown here")
@click.option("--dry-run", is_flag=True, help="Research + preview claims; write no beliefs")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.option("--json", "json_output", is_flag=True, help="Emit the absorption result as JSON")
def learn_web(
    name: str,
    topic: str,
    model: str | None,
    plan: str | None,
    plan_model: str | None,
    num_results: int,
    max_pages: int,
    min_confidence: float,
    save_path: str | None,
    dry_run: bool,
    yes: bool,
    json_output: bool,
) -> None:
    """Research a TOPIC on the LIVE web, then absorb the findings.

    The default pipeline runs at $0 on owned hardware: free web search
    (DuckDuckGo) plus the built-in scraper fetch CURRENT sources, the local model
    synthesizes a cited report, and the report is absorbed into the expert's
    belief store with candidate-specific content-addressed source-note
    provenance. Search snippets and failed fetches stay diagnostic-only; sparse
    retrieval fails before model generation. ``--plan`` uses an explicit
    plan-quota CLI backend instead, still with free web retrieval and no silent
    metered API fallback.

    EXAMPLES:
      deepr expert learn-web "TKG Expert" "latest temporal knowledge graph research 2026"
      deepr expert learn-web "MCP Expert" "Model Context Protocol updates" --model qwen3.6:27b
      deepr expert learn-web "CI Expert" "GitHub Actions reliability 2026" --plan codex
    """
    run_learn_web_pipeline(
        name=name,
        topic=topic,
        model=model,
        plan=plan,
        plan_model=plan_model,
        num_results=num_results,
        max_pages=max_pages,
        min_confidence=min_confidence,
        save_path=save_path,
        dry_run=dry_run,
        yes=yes,
        json_output=json_output,
        title=f"Learn from the web: {name}",
    )
