"""Register the zero-cost correction-survival diagnostic."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from deepr.cli.commands.eval import evaluate


def _code_identity() -> str:
    """The installed version. The run's recipe hash binds the exact selection and packing bytes."""
    from deepr import __version__

    return f"deepr {__version__}"


@evaluate.command("correction-survival")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="New directory for the run. Defaults under the configured benchmarks directory.",
)
@click.option(
    "--distractors",
    type=click.IntRange(0, 500),
    default=0,
    show_default=True,
    help="On-topic filler sources per world, so retrieval and packing bounds are exercised.",
)
@click.option(
    "--local-model",
    default=None,
    help="Answer through this installed Ollama model with the production consult prompt ($0). Default: mock.",
)
@click.option(
    "--model-digest",
    default="",
    help="Refuse to run unless the local model's installed digest matches this value.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the report as JSON.")
def eval_correction_survival(
    output_dir: Path | None, distractors: int, local_model: str | None, model_digest: str, json_output: bool
) -> None:
    """Trace frozen correction cases through study, brief, retrieval and prompt (cost $0).

    By default answers are a fixed mock and no model is called. With
    --local-model each answer is one owned local Ollama call through the
    production consult prompt, pinned to the model digest. The run records
    which stage kept or lost each obligation's evidence; whether an answer
    used it well needs a bound reviewer label.
    """
    from deepr.evals.correction_survival import build_report, mock_completion, render_report, run_diagnostic

    completion: Any = mock_completion
    model_identity = "mock:no-inference"
    if model_digest and not local_model:
        raise click.UsageError("--model-digest requires --local-model.")
    if local_model:
        from deepr.evals.correction_survival_local import LocalAnswerer

        answerer = LocalAnswerer(local_model, digest=model_digest)
        try:
            asyncio.run(answerer.attest())
        except Exception as exc:
            raise click.ClickException(f"Local model refused before any answer: {exc}") from exc
        completion, model_identity = answerer, answerer.identity
        click.echo(f"Answering with {model_identity}; no paid capacity is used.", err=True)

    def progress(attempt: dict[str, Any], done: int, total: int) -> None:
        if local_model:
            click.echo(f"[{done}/{total}] {attempt['attempt_id']}: {attempt['status']}", err=True)

    if output_dir is None:
        from deepr.config import runtime_data_path

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = runtime_data_path("benchmarks", "correction-survival", stamp)
    if output_dir.exists():
        raise click.ClickException(f"{output_dir} already exists; a run directory is never reused.")
    run = asyncio.run(
        run_diagnostic(
            output_dir,
            completion=completion,
            code_identity=_code_identity(),
            model_identity=model_identity,
            distractors=distractors,
            on_attempt=progress,
        )
    )
    report = build_report(run)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rendered = render_report(report)
    (output_dir / "report.md").write_text(rendered, encoding="utf-8")
    if json_output:
        click.echo(json.dumps({**report, "saved_to": str(output_dir)}, indent=2, sort_keys=True))
    else:
        click.echo(rendered)
        click.echo(f"Saved {output_dir}")
