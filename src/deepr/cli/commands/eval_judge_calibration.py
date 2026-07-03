"""`deepr eval judge-calibration` - $0 judge-vs-human agreement report.

Registered on the `eval` group; cli/main.py imports this module for its
registration side effect, so importing eval.py alone does not expose it.
"""

from __future__ import annotations

import json

import click

from deepr.cli.commands.eval import evaluate


@evaluate.command("judge-calibration")
@click.option("--expert", "expert_name", default=None, help="Only reviews for this expert.")
@click.option(
    "--tolerance",
    type=click.FloatRange(min=0.0),
    default=1.0,
    show_default=True,
    help="Score gap counted as agreement (within-tolerance rate).",
)
@click.option("--limit", type=click.IntRange(min=1, max=2000), default=200, show_default=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--save", is_flag=True, help="Save JSON artifact under the configured benchmarks directory.")
def eval_judge_calibration(
    expert_name: str | None,
    tolerance: float,
    limit: int,
    json_output: bool,
    save: bool,
):
    """Measure calibrated-model-judge vs human agreement (cost $0).

    Pairs a human review and a calibrated-model review of the same consult
    trace and reports their per-dimension agreement - mean absolute error,
    directional bias, exact- and within-tolerance-agreement - plus decision
    agreement. Every number is a deterministic statistic over already-recorded
    scores; agreement is not correctness, only measured visibility for gating
    trust in a judge before its scores become a product metric.
    """
    from deepr.evals.judge_calibration import build_judge_calibration_report
    from deepr.experts.consult_quality import load_consult_quality_reviews

    reviews = load_consult_quality_reviews(expert_name=expert_name, limit=limit)
    report = build_judge_calibration_report(reviews, expert_name=expert_name or "", agreement_tolerance=tolerance)

    path = None
    if save:
        from deepr.config import runtime_data_path
        from deepr.utils.atomic_io import atomic_write_json

        root = runtime_data_path("benchmarks")
        root.mkdir(parents=True, exist_ok=True)
        from datetime import UTC, datetime

        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        path = root / f"judge_calibration_{stamp}.json"
        atomic_write_json(path, report)

    if json_output:
        payload = {**report, "saved_to": str(path)} if path else report
        click.echo(json.dumps(payload, indent=2))
        return

    summary = report["summary"]
    overall = report["overall_agreement"]
    click.echo(
        f"Judge calibration ({summary['paired_trace_count']} paired trace(s), {overall['pair_count']} scored pair(s))"
    )
    if not summary["sufficient_data"]:
        click.echo(
            f"  Insufficient data: need {summary['min_paired_traces_for_signal']}+ paired traces before trusting these numbers."
        )
    click.echo(
        f"  Overall  MAE {overall['mean_absolute_error']:.2f}  bias {overall['mean_signed_error']:+.2f}  "
        f"exact {overall['exact_agreement_rate']:.0%}  within {report['request']['agreement_tolerance']:g} "
        f"{overall['within_tolerance_rate']:.0%}"
    )
    for dimension, metrics in report["per_dimension_agreement"].items():
        click.echo(
            f"  - {dimension:26s}  MAE {metrics['mean_absolute_error']:.2f}  bias {metrics['mean_signed_error']:+.2f}  "
            f"exact {metrics['exact_agreement_rate']:.0%}  (n={metrics['pair_count']})"
        )
    decision = report["decision_agreement"]
    click.echo(
        f"  Decision agreement {decision['agreement_rate']:.0%} over {decision['comparable_trace_count']} trace(s)"
    )
    per_reviewer = report.get("per_reviewer_agreement", {})
    if per_reviewer:
        click.echo(
            f"  Per-reviewer trust ({summary.get('trusted_model_reviewer_count', 0)}/"
            f"{summary.get('model_reviewer_count', 0)} trusted):"
        )
        for reviewer, metrics in per_reviewer.items():
            mark = "trusted  " if metrics["trusted"] else "untrusted"
            click.echo(
                f"    {mark}  {reviewer}  MAE {metrics['overall_agreement']['mean_absolute_error']:.2f}  "
                f"within {metrics['overall_agreement']['within_tolerance_rate']:.0%}  "
                f"(n={metrics['paired_trace_count']})"
            )
    click.echo("  Agreement is not correctness; this measures a judge against a human anchor.")
    if path:
        click.echo(f"\nSaved {path}")
