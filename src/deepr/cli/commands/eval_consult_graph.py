"""CLI rendering for the opt-in structured local consult evaluation."""

from __future__ import annotations

import json
from typing import Any

import click


@click.command("consult")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--save", is_flag=True, help="Save JSON artifact under the configured benchmarks directory.")
@click.option(
    "--structured-local",
    "structured_question",
    metavar="QUESTION",
    default=None,
    help="Run the eval-only graph on loopback Ollama with server cloud disabled by config.",
)
@click.option(
    "--expert",
    "structured_experts",
    multiple=True,
    help="Expert name for --structured-local. Repeat for a fixed roster; omit to route read-only.",
)
@click.option("--model", "structured_model", default=None, help="Ollama model for --structured-local.")
@click.option(
    "--max-experts",
    type=click.IntRange(1, 10),
    default=3,
    show_default=True,
    help="Maximum routed experts for --structured-local.",
)
@click.option(
    "--concurrency",
    type=click.IntRange(1, 4),
    default=1,
    show_default=True,
    help="Maximum simultaneous local generations for --structured-local.",
)
@click.option(
    "--max-elapsed-seconds",
    type=click.FloatRange(min=0.001, max=86_400.0),
    default=3_600.0,
    show_default=True,
    help="Whole-run wall-clock ceiling for --structured-local.",
)
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=True,
    show_default=True,
    help="Exit non-zero if a built-in consult regression fails.",
)
def eval_consult(
    json_output: bool,
    save: bool,
    structured_question: str | None,
    structured_experts: tuple[str, ...],
    structured_model: str | None,
    max_experts: int,
    concurrency: int,
    max_elapsed_seconds: float,
    fail_on_regression: bool,
) -> None:
    """Run the local consult harness regression suite (cost $0)."""
    if structured_question is not None:
        run_structured_consult_eval_command(
            question=structured_question,
            experts=structured_experts,
            model=structured_model,
            max_experts=max_experts,
            concurrency=concurrency,
            max_elapsed_seconds=max_elapsed_seconds,
            json_output=json_output,
            save=save,
            fail_on_regression=fail_on_regression,
        )
        return
    if structured_experts or structured_model:
        raise click.UsageError("--expert and --model require --structured-local QUESTION")
    _run_structural_consult_eval(
        json_output=json_output,
        save=save,
        fail_on_regression=fail_on_regression,
    )


def _run_structural_consult_eval(*, json_output: bool, save: bool, fail_on_regression: bool) -> None:
    from deepr.evals.consult import run_consult_eval, write_consult_eval_report

    report = run_consult_eval()
    path = write_consult_eval_report(report) if save else None
    if json_output:
        data = report.to_dict()
        if path:
            data["saved_to"] = str(path)
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Consult harness eval  (methodology v{report.methodology_version})")
        click.echo(f"Deepr metered cost: ${report.cost_usd:.2f}")
        click.echo(f"Score: {report.score:.1%} ({report.passed_cases}/{report.total_cases})")
        click.echo("")
        for outcome in report.outcomes:
            status = "pass" if outcome.passed else "fail"
            click.echo(f"  - {outcome.case_id:32s} {status:4s} [{outcome.category}]")
        if path:
            click.echo("")
            click.echo(f"Saved {path}")
    if fail_on_regression and report.failed_cases:
        raise click.ClickException(f"{report.failed_cases} consult regression(s) failed.")


def run_structured_consult_eval_command(
    *,
    question: str,
    experts: tuple[str, ...],
    model: str | None,
    max_experts: int,
    concurrency: int,
    max_elapsed_seconds: float,
    json_output: bool,
    save: bool,
    fail_on_regression: bool,
) -> None:
    """Execute and render one explicitly requested local graph eval."""
    from deepr.cli.async_runner import run_async_command
    from deepr.evals.consult_graph import run_local_structured_consult_graph, write_structured_consult_run

    try:
        report = run_async_command(
            run_local_structured_consult_graph(
                question=question,
                experts=experts,
                max_experts=max_experts,
                model=model,
                concurrency=concurrency,
                max_elapsed_seconds=max_elapsed_seconds,
            )
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    path = write_structured_consult_run(report) if save else None
    if json_output:
        payload = dict(report)
        if path:
            payload["saved_to"] = str(path)
        click.echo(json.dumps(payload, indent=2))
    else:
        _render_structured_consult_summary(report, saved_to=str(path) if path else "")
    if fail_on_regression and report["status"] != "completed":
        raise click.ClickException(f"Structured local consult stopped: {report['stop_reason']}")


def _render_structured_consult_summary(report: dict[str, Any], *, saved_to: str) -> None:
    counts = report["node_counts"]
    usage = report["usage"]
    capacity = report["capacity"]
    provenance = capacity["model_provenance"]
    click.echo("Structured local consult graph  (eval-only)")
    click.echo("Deepr metered cost: $0.00  (cloud-disabled, materialized local model)")
    click.echo(f"Status: {report['status']} ({report['stop_reason']})")
    click.echo(
        "Capacity proof: Ollama cloud disabled by config; "
        f"GGUF {provenance['size_bytes'] / (1024**3):.2f} GiB; digest {provenance['digest'][:12]}"
    )
    click.echo(
        f"Transport: native loopback; {capacity['preflight_http_requests']} preflight requests; "
        f"{capacity['sdk_retries']} retries; env credentials/proxies off; redirects off"
    )
    click.echo(f"Local residency: at most {capacity['model_keep_alive']}; cost-ledger dispatch markers required")
    click.echo(f"Nodes: {counts['completed']}/{counts['expected']} completed")
    click.echo(
        f"Local model calls: {usage['model_calls']}; transport attempts: {usage['transport_attempts']}; "
        f"ambiguous usage nodes: {usage['usage_ambiguous_nodes']}"
    )
    click.echo(f"Elapsed: {usage['elapsed_ms'] / 1000:.1f}s")
    if saved_to:
        click.echo("")
        click.echo(f"Saved {saved_to}")
