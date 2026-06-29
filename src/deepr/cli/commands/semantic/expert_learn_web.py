"""Expert web-learning command and shared topic-learning pipeline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import click

from deepr.cli.colors import console, print_error, print_header, print_list_item, print_warning
from deepr.cli.commands.semantic.experts import expert

__all__ = ["run_learn_web_pipeline"]


def _emit_absorb_result(result, name: str, json_output: bool) -> None:
    """Render an absorption result as JSON or a human summary."""
    if json_output:
        import json as _json

        click.echo(_json.dumps(result.to_dict(), indent=2))
        return
    if result.dry_run:
        console.print("[yellow]DRY RUN[/yellow] - nothing written")
    console.print(
        f"Candidates: {result.total_candidates}  Absorbed: {len(result.absorbed)} "
        f"(added {result.added_count}, merged {result.merged_count})  Rejected: {len(result.rejected)}"
    )
    for a in result.absorbed:
        print_list_item(f"{a.statement}  [dim](conf {a.confidence:.2f}, {a.outcome})[/dim]")
    console.print(f"\nAudit anytime: deepr expert health-check '{name}'")


def _learn_web_plan_backend(plan: str, plan_model: str | None, json_output: bool):
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


def _learn_web_local_backend(model: str | None):
    from deepr.backends.local import default_local_model, ollama_chat_client

    selected_model = model or default_local_model()
    if not selected_model:
        print_error("No local model available. Is Ollama running? Check: deepr capacity --probe")
        raise click.exceptions.Exit(2)
    return selected_model, ollama_chat_client(), f"Local model: {selected_model}  ($0, owned hardware)"


def _learn_web_backend(model: str | None, plan: str | None, plan_model: str | None, json_output: bool):
    if model and plan:
        print_error("Use only one of --model or --plan.")
        raise click.exceptions.Exit(2)
    if plan:
        return _learn_web_plan_backend(plan, plan_model, json_output)
    return _learn_web_local_backend(model)


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
    import sys
    from pathlib import Path

    from deepr.experts.local_research import research_web_local
    from deepr.experts.profile import ExpertStore
    from deepr.experts.report_absorber import ReportAbsorber, ReportAbsorberError

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    model, client, run_label = _learn_web_backend(model, plan, plan_model, json_output)

    print_header(title)
    console.print(f"  Topic: {topic}")
    console.print(f"  {run_label}")
    if not yes and not click.confirm("\nSearch the live web and absorb findings?", default=True):
        print_warning("Cancelled.")
        sys.exit(0)

    console.print("[dim]Searching the web, fetching pages, and synthesizing without metered spend...[/dim]")
    research = asyncio.run(
        research_web_local(topic, model=model, client=client, num_results=num_results, max_pages=max_pages)
    )
    report = research.get("answer") or ""
    if not report:
        print_error(f"Web research produced no report: {research.get('error', 'empty')}")
        sys.exit(1)
    console.print(f"[dim]Synthesized a report from {len(research.get('sources', []))} live source(s).[/dim]")
    if save_path:
        Path(save_path).write_text(report, encoding="utf-8")
        console.print(f"[dim]Report saved: {save_path}[/dim]")

    absorber = ReportAbsorber(
        profile,
        model=model,
        client=client,
        estimated_cost=0.0,
    )
    try:
        result = asyncio.run(absorber.absorb(f"web:{topic}", report, min_confidence=min_confidence, dry_run=dry_run))
    except ReportAbsorberError as e:
        print_error(str(e))
        sys.exit(2)

    if not result.dry_run:
        profile.last_knowledge_refresh = datetime.now(UTC)
        store.save(profile)

    _emit_absorb_result(result, name, json_output)


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
@click.option("--num-results", type=int, default=8, show_default=True, help="Web results to retrieve")
@click.option("--max-pages", type=int, default=5, show_default=True, help="Top results to fetch in full")
@click.option("--min-confidence", type=float, default=0.6, show_default=True, help="Drop weaker claims")
@click.option("--save", "save_path", type=click.Path(), default=None, help="Also save the report markdown here")
@click.option("--dry-run", is_flag=True, help="Research + preview claims; write no beliefs")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.option("--json", "json_output", is_flag=True, help="Emit the absorption result as JSON")
def learn_web(
    name,
    topic,
    model,
    plan,
    plan_model,
    num_results,
    max_pages,
    min_confidence,
    save_path,
    dry_run,
    yes,
    json_output,
):
    """Research a TOPIC on the LIVE web, then absorb the findings.

    The default pipeline runs at $0 on owned hardware: free web search
    (DuckDuckGo) plus the built-in scraper fetch CURRENT sources, the local model
    synthesizes a cited report, and the report is absorbed into the expert's
    belief store with real URL provenance. ``--plan`` uses an explicit
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
