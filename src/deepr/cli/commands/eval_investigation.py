"""Register the zero-cost evidence-first investigation evaluator."""

from __future__ import annotations

import json

import click

from deepr.cli.commands.eval import evaluate


@evaluate.command("investigation")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--save", is_flag=True, help="Save under the configured benchmarks directory.")
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=True,
    show_default=True,
    help="Exit non-zero if a structural investigation check fails.",
)
def eval_investigation(json_output: bool, save: bool, fail_on_regression: bool) -> None:
    """Run frozen investigation protocol checks at cost $0."""
    from deepr.evals.investigation import run_investigation_eval, write_investigation_eval_report

    report = run_investigation_eval()
    path = write_investigation_eval_report(report) if save else None
    if json_output:
        payload = report.to_dict()
        if path is not None:
            payload["saved_to"] = str(path)
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(
            f"Evidence-first investigation fixture eval (methodology v{report.to_dict()['methodology_version']})"
        )
        click.echo("Deepr metered cost: $0.00")
        click.echo("Semantic review: unreviewed")
        click.echo(f"Score: {report.score:.1%} ({report.passed_cases}/{report.total_cases})")
        for outcome in report.outcomes:
            status = "pass" if outcome.passed else "fail"
            click.echo(f"  - {outcome.case_id:42s} {status:4s} [{outcome.category}]")
        if path is not None:
            click.echo(f"Saved {path}")
    if fail_on_regression and report.failed_cases:
        raise click.ClickException(f"{report.failed_cases} investigation regression(s) failed.")


__all__ = ["eval_investigation"]
