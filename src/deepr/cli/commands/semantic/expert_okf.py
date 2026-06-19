"""Expert OKF export command."""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path

import click

from deepr.cli.colors import console, print_error, print_header, print_key_value, print_success
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
