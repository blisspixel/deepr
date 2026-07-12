"""Review consult quality cases and promote accepted candidates."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import console, print_error, print_key_value, print_section_header
from deepr.cli.commands.semantic.experts import expert
from deepr.cli.commands.semantic.grounding_support import PLAN_BACKEND_CHOICES
from deepr.experts.profile import ExpertStore


@dataclass(frozen=True)
class _JudgeRunOptions:
    calibration_ref: str
    target: str
    apply_change: bool
    trace_path: Path | None
    limit: int
    max_candidates: int
    output_dir: Path | None


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


def _validate_judge_backend_choice(
    *,
    local_judge_model: str,
    plan_backend: str | None,
    plan_model: str | None,
    api_provider: str | None,
    api_model: str | None,
) -> None:
    if plan_model and not plan_backend:
        print_error("Use --plan-model with --plan.")
        raise click.Abort()
    if api_model and not api_provider:
        print_error("Use --api-model with --api-provider.")
        raise click.Abort()
    backend_count = sum(1 for value in (local_judge_model, plan_backend, api_provider) if bool(value))
    if backend_count != 1:
        print_error("Use exactly one of --local-judge-model, --plan, or --api-provider.")
        raise click.Abort()


def _run_api_consult_quality_judge(
    profile: Any,
    trace_id: str,
    *,
    api_provider: str,
    api_model: str | None,
    budget_usd: float,
    confirm_metered_cost: bool,
    json_output: bool,
    options: _JudgeRunOptions,
) -> dict[str, Any]:
    from deepr.experts.consult_quality import (
        ConsultQualityReviewError,
        estimate_consult_quality_api_judge_cost,
        review_consult_quality_candidate_with_api_judge,
    )

    if not api_model:
        raise ConsultQualityReviewError("An API judge model is required with --api-provider.")
    estimated_cost = estimate_consult_quality_api_judge_cost(api_model)
    if not json_output:
        print_key_value("API judge estimate", f"~${estimated_cost:.4f} via {api_provider}/{api_model}")
    if budget_usd <= 0:
        raise ConsultQualityReviewError("A positive --budget is required for metered API judging.")
    if not confirm_metered_cost:
        raise ConsultQualityReviewError(
            "Metered API consult-quality judging requires --confirm-metered-cost after reviewing the estimate."
        )
    return asyncio.run(
        review_consult_quality_candidate_with_api_judge(
            profile,
            trace_id,
            api_provider=api_provider,
            judge_model=api_model,
            budget_usd=budget_usd,
            confirm_metered_cost=confirm_metered_cost,
            calibration_ref=options.calibration_ref,
            target=options.target,
            apply=options.apply_change,
            trace_path=options.trace_path,
            limit=options.limit,
            max_candidates=options.max_candidates,
            output_dir=options.output_dir,
        )
    )


def _run_plan_consult_quality_judge(
    profile: Any,
    trace_id: str,
    *,
    plan_backend: str,
    plan_model: str | None,
    options: _JudgeRunOptions,
) -> dict[str, Any]:
    from deepr.backends.waterfall import choose_plan_quota_backend
    from deepr.experts.consult_quality import (
        ConsultQualityReviewError,
        review_consult_quality_candidate_with_plan_judge,
    )

    choice = choose_plan_quota_backend(plan_backend)
    if not choice.is_plan_quota or choice.plan_backend_id is None:
        raise ConsultQualityReviewError(choice.reason)
    return asyncio.run(
        review_consult_quality_candidate_with_plan_judge(
            profile,
            trace_id,
            plan_backend_id=choice.plan_backend_id,
            judge_model=plan_model,
            calibration_ref=options.calibration_ref,
            target=options.target,
            apply=options.apply_change,
            trace_path=options.trace_path,
            limit=options.limit,
            max_candidates=options.max_candidates,
            output_dir=options.output_dir,
        )
    )


def _run_local_consult_quality_judge(
    profile: Any,
    trace_id: str,
    *,
    local_judge_model: str,
    options: _JudgeRunOptions,
) -> dict[str, Any]:
    from deepr.backends.capacity import available_local_models
    from deepr.experts.consult_quality import (
        ConsultQualityReviewError,
        review_consult_quality_candidate_with_local_judge,
    )

    installed = available_local_models()
    if not installed:
        raise ConsultQualityReviewError("No local Ollama models available. Check `deepr capacity --probe`.")
    if local_judge_model not in installed:
        raise ConsultQualityReviewError(f"Local judge model is not installed: {local_judge_model}")
    return asyncio.run(
        review_consult_quality_candidate_with_local_judge(
            profile,
            trace_id,
            judge_model=local_judge_model,
            calibration_ref=options.calibration_ref,
            target=options.target,
            apply=options.apply_change,
            trace_path=options.trace_path,
            limit=options.limit,
            max_candidates=options.max_candidates,
            output_dir=options.output_dir,
        )
    )


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
@click.option("--local-judge-model", default="", help="Installed local Ollama model used as calibrated judge.")
@click.option(
    "--plan",
    "plan_backend",
    type=click.Choice(PLAN_BACKEND_CHOICES),
    default=None,
    help="Use an explicit plan-quota CLI as calibrated judge.",
)
@click.option("--plan-model", default=None, help="Optional model hint for the plan-quota CLI judge.")
@click.option(
    "--api-provider",
    type=click.Choice(["openai", "xai"]),
    default=None,
    help="Use an explicit metered API provider as calibrated judge.",
)
@click.option("--api-model", default=None, help="Required model for --api-provider.")
@click.option(
    "--budget",
    "budget_usd",
    type=float,
    default=0.0,
    show_default=True,
    help="Maximum metered API judge spend for this run.",
)
@click.option(
    "--confirm-metered-cost",
    is_flag=True,
    help="Confirm the displayed metered API judge estimate before dispatch.",
)
@click.option("--calibration-ref", default="", help="Optional calibration artifact id for this calibrated judge.")
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
    plan_backend: str | None,
    plan_model: str | None,
    api_provider: str | None,
    api_model: str | None,
    budget_usd: float,
    confirm_metered_cost: bool,
    calibration_ref: str,
    target: str,
    apply_change: bool,
    trace_path: Path | None,
    limit: int,
    max_candidates: int,
    output_dir: Path | None,
    json_output: bool,
) -> None:
    """Score a consult semantic-quality case with an explicit calibrated judge."""
    from deepr.experts.consult_quality import ConsultQualityReviewError

    _validate_judge_backend_choice(
        local_judge_model=local_judge_model,
        plan_backend=plan_backend,
        plan_model=plan_model,
        api_provider=api_provider,
        api_model=api_model,
    )

    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    options = _JudgeRunOptions(
        calibration_ref=calibration_ref,
        target=target,
        apply_change=apply_change,
        trace_path=trace_path,
        limit=limit,
        max_candidates=max_candidates,
        output_dir=output_dir,
    )
    try:
        if api_provider:
            from deepr.experts.metered_mutation_gate import (
                MeteredExpertMutationDisabledError,
                require_metered_expert_mutation,
            )

            try:
                require_metered_expert_mutation(
                    "api_consult_quality_judge",
                    safe_alternative="use --local-judge-model or --plan for a non-metered judge",
                )
            except MeteredExpertMutationDisabledError as exc:
                raise click.ClickException(str(exc)) from exc
            payload = _run_api_consult_quality_judge(
                profile,
                trace_id,
                api_provider=api_provider,
                api_model=api_model,
                budget_usd=budget_usd,
                confirm_metered_cost=confirm_metered_cost,
                json_output=json_output,
                options=options,
            )
        elif plan_backend:
            payload = _run_plan_consult_quality_judge(
                profile,
                trace_id,
                plan_backend=plan_backend,
                plan_model=plan_model,
                options=options,
            )
        else:
            payload = _run_local_consult_quality_judge(
                profile,
                trace_id,
                local_judge_model=local_judge_model,
                options=options,
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
@click.option(
    "--gate-untrusted-judges",
    is_flag=True,
    help="Exclude calibrated-model reviews from judges not measured-trusted (judge-calibration) from regression selection.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_consult_quality_trends(
    name: str,
    output_dir: Path | None,
    limit: int,
    regression_limit: int,
    gate_untrusted_judges: bool,
    json_output: bool,
) -> None:
    """Summarize reviewed consult quality and select regression candidates."""
    from deepr.experts.consult_quality import build_consult_quality_trend_report, load_consult_quality_reviews

    store = ExpertStore()
    profile = store.load(name)
    if profile is None:
        print_error(f"Expert '{name}' not found")
        raise click.Abort()

    trusted_reviewers = None
    if gate_untrusted_judges:
        from deepr.evals.judge_calibration import build_judge_calibration_report, trusted_model_reviewers

        reviews = load_consult_quality_reviews(expert_name=profile.name, output_dir=output_dir, limit=limit)
        calibration = build_judge_calibration_report(reviews, expert_name=profile.name)
        trusted_reviewers = trusted_model_reviewers(calibration)

    payload = build_consult_quality_trend_report(
        expert_name=profile.name,
        output_dir=output_dir,
        limit=limit,
        regression_limit=regression_limit,
        trusted_model_reviewers=trusted_reviewers,
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    _render_trends(payload)
