"""Review consult trace candidates without exposing raw local trace files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.consult_traces import review_consult_traces


def _render(payload: dict[str, Any]) -> None:
    print_section_header("Consult Trace Candidates")
    print_key_value("Traces reviewed", str(payload["trace_count"]))
    print_key_value("Candidates", str(payload["candidate_count"]))
    print_key_value("Failed traces", str(payload["failed_trace_count"]))
    print_key_value("Failed checks", str(payload["failed_check_count"]))
    print_key_value("Low-context traces", str(payload["low_context_trace_count"]))
    print_key_value("Middle-context review", str(payload.get("middle_context_review_count", 0)))
    candidates = list(payload.get("candidates", []) or [])
    if not candidates:
        console.print("[dim]No failed, low-context, or middle-context review consult traces found.[/dim]")
        return

    for candidate in candidates[:10]:
        console.print(f"\n[bold]{candidate['reason']}[/bold] [dim]{candidate['trace_id']}[/dim]")
        console.print(f"  {candidate['question_preview']}")
        console.print(f"  Gap: {candidate['gap']['topic']}")
        checks = candidate.get("failed_checks") or candidate.get("warning_checks") or []
        if checks:
            console.print(f"  Checks: {', '.join(checks)}")


@expert.command(name="consult-traces")
@click.option(
    "--trace-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional local consult trace JSONL path. Defaults to Deepr's configured trace store.",
)
@click.option("--limit", type=int, default=50, show_default=True, help="Newest traces to review.")
@click.option("--max-candidates", type=int, default=20, show_default=True, help="Maximum candidates to return.")
@click.option(
    "--low-context-threshold",
    type=int,
    default=1,
    show_default=True,
    help="Minimum selected context packets before a trace is considered low-context.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_consult_traces(
    trace_path: Path | None,
    limit: int,
    max_candidates: int,
    low_context_threshold: int,
    json_output: bool,
) -> None:
    """Review failed, low-context, or middle-context consult traces as candidates."""
    payload = review_consult_traces(
        path=trace_path,
        limit=limit,
        max_candidates=max_candidates,
        low_context_threshold=low_context_threshold,
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    _render(payload)
