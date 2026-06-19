"""Expert OKF export command."""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path

import click

from deepr.cli.colors import console, print_error, print_header, print_key_value, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert


@expert.command(name="export-okf")
@click.argument("name")
@click.argument("output", type=click.Path(file_okay=False))
@click.option("--force", is_flag=True, help="Overwrite files that lack the OKF derived-view marker")
@click.option("--llms/--no-llms", "include_llms", default=True, show_default=True, help="Emit llms.txt discovery file")
@click.option("--json", "json_output", is_flag=True, help="Emit the export result as JSON")
def export_okf(name: str, output: str, force: bool, include_llms: bool, json_output: bool):
    """Export an expert as a portable OKF Markdown bundle.

    The export is a regenerated derived view over the structured belief store,
    event log, typed edges, gaps, and contested claims. It never becomes the
    source of truth and never spends money.

    EXAMPLES:
      deepr expert export-okf "AI Strategy Expert" ./okf/ai-strategy
      deepr expert export-okf "AI Strategy Expert" ./okf/ai-strategy --json
    """
    from deepr.experts.beliefs import BeliefStore
    from deepr.experts.okf import build_okf_bundle, write_okf_bundle
    from deepr.experts.profile import ExpertStore

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    bundle = build_okf_bundle(
        profile,
        BeliefStore(profile.name),
        include_llms=include_llms,
    )
    try:
        result = write_okf_bundle(bundle, Path(output), force=force)
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2))
        return

    print_header(f"OKF export: {profile.name}")
    print_key_value("Output", str(result.output_dir))
    print_key_value("Concepts", str(result.concept_count))
    print_key_value("Gaps", str(result.gap_count))
    print_key_value("Events", str(result.event_count))
    print_key_value("Open contested claims", str(result.contested_count))
    print_key_value("Files", str(len(result.files)))
    print_success("OKF bundle written.")
    console.print("[dim]Derived view. Regenerate any time; the belief store stays canonical.[/dim]")


@expert.command(name="absorb-okf")
@click.argument("name")
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--min-confidence",
    type=float,
    default=0.6,
    show_default=True,
    help="Drop candidate claims the OKF source supports more weakly than this",
)
@click.option("--model", default=None, help="Override the extraction model")
@click.option("--dry-run", is_flag=True, help="Preview what would be absorbed; write nothing")
@click.option("--local", is_flag=True, help="Force extraction on the local Ollama model at $0")
@click.option("--api", is_flag=True, help="Force the metered API even if a local model is admitted")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.option("--json", "json_output", is_flag=True, help="Emit the structured absorption result as JSON")
def absorb_okf(
    name: str,
    path: str,
    min_confidence: float,
    model: str | None,
    dry_run: bool,
    local: bool,
    api: bool,
    yes: bool,
    json_output: bool,
):
    """Absorb an OKF bundle through Deepr's verified report absorber.

    Parses OKF concept Markdown and frontmatter into a synthetic source report,
    then routes that text through the same extraction, grounding, dedup, and
    contradiction gates used by `deepr expert absorb`. The bundle is never
    trusted as authoritative state.

    EXAMPLES:
      deepr expert absorb-okf "AI Strategy Expert" ./okf/ai-strategy --dry-run
      deepr expert absorb-okf "AI Strategy Expert" ./okf/ai-strategy --local -y
    """
    import asyncio
    from datetime import UTC, datetime

    if local and api:
        print_error("Use either --local or --api, not both.")
        sys.exit(2)

    from deepr.experts.okf import build_okf_ingestion_corpus
    from deepr.experts.profile import ExpertStore
    from deepr.experts.report_absorber import ESTIMATED_EXTRACTION_COST, ReportAbsorber, ReportAbsorberError

    store = ExpertStore()
    profile = store.load(name)
    if not profile:
        print_error(f"Expert not found: {name}")
        click.echo("List available experts: deepr expert list")
        sys.exit(2)

    try:
        corpus = build_okf_ingestion_corpus(Path(path))
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(2)

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

    if not yes:
        intent = "preview (writes nothing)" if dry_run else f"absorb OKF into '{name}'"
        if not click.confirm(f"Run extraction ({cost_note}) and {intent}?", default=False):
            print_warning("Cancelled.")
            sys.exit(0)

    try:
        result = asyncio.run(
            absorber.absorb(
                corpus.report_id,
                corpus.report_text,
                min_confidence=min_confidence,
                dry_run=dry_run,
            )
        )
    except ReportAbsorberError as exc:
        print_error(str(exc))
        sys.exit(2)
    except Exception as exc:
        print_error(f"OKF absorption failed: {exc}")
        sys.exit(1)

    if not result.dry_run:
        profile.total_research_cost += result.estimated_cost
        profile.last_knowledge_refresh = datetime.now(UTC)
        store.save(profile)

    payload = {"okf": corpus.to_dict(), "absorption": result.to_dict()}
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_header(f"Absorb OKF into {profile.name}")
    if result.dry_run:
        console.print("[yellow]DRY RUN[/yellow] - nothing written")
    print_key_value("OKF concepts", str(corpus.concept_count))
    print_key_value("Candidates", str(result.total_candidates))
    print_key_value("Absorbed", str(len(result.absorbed)))
    print_key_value("Flagged contradictions", str(len(result.flagged)))
    print_key_value("Report id", corpus.report_id)
    if not result.dry_run and (result.absorbed or result.flagged):
        print_success("OKF source passed through the verified absorb gate.")
    elif not result.absorbed and not result.flagged:
        print_warning("No OKF claims were absorbed.")
