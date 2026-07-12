"""Register the zero-cost frozen deliberation evaluator."""

from __future__ import annotations

import json

import click

from deepr.cli.commands.eval import evaluate


@evaluate.command("deliberation")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--save", is_flag=True, help="Save JSON artifact under the configured benchmarks directory.")
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=True,
    show_default=True,
    help="Exit non-zero if a built-in deliberation protocol check fails.",
)
def eval_deliberation(json_output: bool, save: bool, fail_on_regression: bool) -> None:
    """Run the frozen bounded-deliberation fixture suite (cost $0)."""
    from deepr.evals.deliberation import run_deliberation_eval, write_deliberation_eval_report

    report = run_deliberation_eval()
    path = write_deliberation_eval_report(report) if save else None

    if json_output:
        data = report.to_dict()
        if path:
            data["saved_to"] = str(path)
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Bounded deliberation fixture eval  (methodology v{report.methodology_version})")
        click.echo(f"Deepr metered cost: ${report.cost_usd:.2f}")
        click.echo(f"Semantic review: {report.semantic_review_status}")
        click.echo(f"Score: {report.score:.1%} ({report.passed_cases}/{report.total_cases})")
        click.echo("")
        for outcome in report.outcomes:
            status = "pass" if outcome.passed else "fail"
            click.echo(f"  - {outcome.case_id:44s} {status:4s} [{outcome.category}]")
        if path:
            click.echo("")
            click.echo(f"Saved {path}")

    if fail_on_regression and report.failed_cases:
        raise click.ClickException(f"{report.failed_cases} deliberation regression(s) failed.")
