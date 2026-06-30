"""Review consult quality cases and promote accepted candidates."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.profile import ExpertStore


def _parse_scores(score_pairs: tuple[str, ...]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for pair in score_pairs:
        dimension, sep, raw_score = pair.partition("=")
        if not sep:
            raise click.BadParameter("Scores must use dimension=value form.")
        dimension = dimension.strip()
        if not dimension:
            raise click.BadParameter("Score dimension cannot be empty.")
        try:
            score = float(raw_score)
        except ValueError as exc:
            raise click.BadParameter(f"Score for {dimension} must be numeric.") from exc
        scores[dimension] = score
    return scores


def _render(payload: dict[str, Any]) -> None:
    print_section_header("Consult Quality Review")
    print_key_value("Expert", payload["expert_name"])
    print_key_value("Trace", payload["trace_id"])
    print_key_value("Status", payload["review_status"])
    print_key_value("Mean score", f"{float(payload['mean_score']):.2f}")
    print_key_value("Decision", payload["decision"])
    print_key_value("Eligible", "yes" if payload["eligible_for_promotion"] else "no")

    for action in payload.get("actions", []) or []:
        console.print(f"\n[bold]{action['action']}[/bold]  [dim]{action['status']}[/dim]")
        if action.get("path"):
            console.print(f"  {action['path']}")
        elif action.get("would_write"):
            console.print(f"  would write: {action['would_write']}")
        elif action.get("reason"):
            console.print(f"  {action['reason']}")
    if not payload["applied"]:
        console.print("\n[dim]Preview only. Re-run with --apply after review to write artifacts.[/dim]")


def _render_trends(payload: dict[str, Any]) -> None:
    print_section_header("Consult Quality Trends")
    print_key_value("Expert", payload["expert_name"] or "all")
    print_key_value("Reviews", str(payload["review_count"]))
    print_key_value("Mean score", f"{float(payload['mean_score']):.2f}")
    print_key_value("Regression candidates", str(payload["regression_candidate_count"]))

    status_counts = payload.get("status_counts", {}) or {}
    if status_counts:
        console.print("\n[bold]Review status[/bold]")
        for status, count in status_counts.items():
            console.print(f"  {status}: {count}")

    dimension_scores = payload.get("dimension_scores", []) or []
    if dimension_scores:
        console.print("\n[bold]Dimensions[/bold]")
        for item in dimension_scores:
            console.print(
                f"  {item['dimension']}: mean {float(item['mean_score']):.2f} "
                f"min {float(item['min_score']):.2f} max {float(item['max_score']):.2f}"
            )

    candidates = payload.get("regression_candidates", []) or []
    if candidates:
        console.print("\n[bold]Regression candidates[/bold]")
        for candidate in candidates[:10]:
            console.print(
                f"  {candidate['source_trace_id']} "
                f"{candidate['review_status']} mean {float(candidate['mean_score']):.2f}"
            )
            console.print(f"    {candidate['question_preview']}")


@expert.command(name="review-consult-quality")
@click.argument("name")
@click.argument("trace_id")
@click.option(
    "--score",
    "score_pairs",
    multiple=True,
    required=True,
    help="Rubric score in dimension=value form. Provide every dimension from the quality case.",
)
@click.option("--reviewer", required=True, help="Human reviewer or calibrated judge id.")
@click.option(
    "--decision",
    type=click.Choice(["accept", "needs-improvement", "reject"]),
    required=True,
    help="Reviewer decision. Promotion requires accept plus policy pass.",
)
@click.option(
    "--judge-type",
    type=click.Choice(["human", "calibrated-model"]),
    default="human",
    show_default=True,
    help="Who produced the semantic score.",
)
@click.option(
    "--failure-label",
    "failure_labels",
    multiple=True,
    help="Reviewer-selected failure label from the quality case.",
)
@click.option("--notes", default="", help="Reviewer notes to store with the artifact.")
@click.option("--calibration-ref", default="", help="Optional calibration artifact id for calibrated-model judges.")
@click.option(
    "--target",
    type=click.Choice(["none", "gap", "eval", "both"]),
    default="none",
    show_default=True,
    help="Accepted review promotion target.",
)
@click.option("--apply", "apply_change", is_flag=True, help="Write the reviewed artifact and accepted promotions.")
@click.option(
    "--trace-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional local consult trace JSONL path.",
)
@click.option("--limit", type=int, default=50, show_default=True, help="Newest traces to inspect.")
@click.option("--max-candidates", type=int, default=20, show_default=True, help="Maximum trace candidates to rebuild.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Optional directory for review and eval artifacts.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_review_consult_quality(
    name: str,
    trace_id: str,
    score_pairs: tuple[str, ...],
    reviewer: str,
    decision: str,
    judge_type: str,
    failure_labels: tuple[str, ...],
    notes: str,
    calibration_ref: str,
    target: str,
    apply_change: bool,
    trace_path: Path | None,
    limit: int,
    max_candidates: int,
    output_dir: Path | None,
    json_output: bool,
) -> None:
    """Score a consult semantic-quality case and optionally promote it."""
    from deepr.experts.consult_quality import ConsultQualityReviewError, review_consult_quality_candidate

    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    try:
        payload = review_consult_quality_candidate(
            profile,
            trace_id,
            scores=_parse_scores(score_pairs),
            reviewer=reviewer,
            decision=decision.replace("-", "_"),
            judge_type=judge_type.replace("-", "_"),
            failure_labels=list(failure_labels),
            notes=notes,
            calibration_ref=calibration_ref,
            target=target,
            apply=apply_change,
            trace_path=trace_path,
            limit=limit,
            max_candidates=max_candidates,
            output_dir=output_dir,
        )
    except (ConsultQualityReviewError, click.BadParameter) as exc:
        print_error(str(exc))
        raise click.Abort() from exc

    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render(payload)


@expert.command(name="judge-consult-quality")
@click.argument("name")
@click.argument("trace_id")
@click.option("--local-judge-model", required=True, help="Installed local Ollama model used as calibrated judge.")
@click.option("--calibration-ref", default="", help="Optional calibration artifact id for this local judge.")
@click.option(
    "--target",
    type=click.Choice(["none", "gap", "eval", "both"]),
    default="none",
    show_default=True,
    help="Accepted review promotion target.",
)
@click.option("--apply", "apply_change", is_flag=True, help="Write the reviewed artifact and accepted promotions.")
@click.option(
    "--trace-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional local consult trace JSONL path.",
)
@click.option("--limit", type=int, default=50, show_default=True, help="Newest traces to inspect.")
@click.option("--max-candidates", type=int, default=20, show_default=True, help="Maximum trace candidates to rebuild.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Optional directory for review and eval artifacts.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_judge_consult_quality(
    name: str,
    trace_id: str,
    local_judge_model: str,
    calibration_ref: str,
    target: str,
    apply_change: bool,
    trace_path: Path | None,
    limit: int,
    max_candidates: int,
    output_dir: Path | None,
    json_output: bool,
) -> None:
    """Score a consult semantic-quality case with an explicit local judge."""
    from deepr.backends.capacity import available_local_models
    from deepr.experts.consult_quality import (
        ConsultQualityReviewError,
        review_consult_quality_candidate_with_local_judge,
    )

    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    installed = available_local_models()
    if not installed:
        print_error("No local Ollama models available. Check `deepr capacity --probe`.")
        raise click.Abort()
    if local_judge_model not in installed:
        print_error(f"Local judge model is not installed: {local_judge_model}")
        raise click.Abort()

    try:
        payload = asyncio.run(
            review_consult_quality_candidate_with_local_judge(
                profile,
                trace_id,
                judge_model=local_judge_model,
                calibration_ref=calibration_ref,
                target=target,
                apply=apply_change,
                trace_path=trace_path,
                limit=limit,
                max_candidates=max_candidates,
                output_dir=output_dir,
            )
        )
    except ConsultQualityReviewError as exc:
        print_error(str(exc))
        raise click.Abort() from exc

    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render(payload)


@expert.command(name="consult-quality-trends")
@click.argument("name")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Optional directory containing consult-quality review artifacts.",
)
@click.option("--limit", type=int, default=200, show_default=True, help="Newest review artifacts to inspect.")
@click.option(
    "--regression-limit",
    type=int,
    default=10,
    show_default=True,
    help="Maximum deterministic prompt-regression candidates to return.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_consult_quality_trends(
    name: str,
    output_dir: Path | None,
    limit: int,
    regression_limit: int,
    json_output: bool,
) -> None:
    """Summarize reviewed consult quality and select regression candidates."""
    from deepr.experts.consult_quality import build_consult_quality_trend_report

    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    payload = build_consult_quality_trend_report(
        expert_name=profile.name,
        output_dir=output_dir,
        limit=limit,
        regression_limit=regression_limit,
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render_trends(payload)
