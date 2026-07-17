"""Register the operator-attested longitudinal expert-value evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from deepr.cli.commands.eval import evaluate
from deepr.experts.blueprint import BlueprintStorageError, ExpertBlueprint, ExpertBlueprintStore
from deepr.utils.atomic_io import atomic_write_json


def _normalized_name(name: str) -> str:
    return " ".join(name.split())


def _load_current_blueprint(name: str) -> ExpertBlueprint:
    normalized = _normalized_name(name)
    try:
        blueprint = ExpertBlueprintStore().load_latest(normalized)
    except BlueprintStorageError as exc:
        raise click.ClickException(f"Could not load blueprint: {exc}") from exc
    if blueprint is None:
        raise click.ClickException(
            "No operator-attested blueprint exists. Start with an unreviewed draft: "
            f'deepr expert blueprint "{normalized}" --template --output expert-blueprint.json'
        )
    return blueprint


def _validate_options(
    *,
    show_template: bool,
    source: Path | None,
    artifact_root: Path | None,
    json_output: bool,
) -> None:
    if show_template == (source is not None):
        raise click.UsageError("Choose exactly one of --template or --from-file")
    if show_template and json_output:
        raise click.UsageError("--template already emits JSON; omit --json")
    if show_template and artifact_root is not None:
        raise click.UsageError("--artifact-root is only valid with --from-file")


def _write_payload(path: Path, payload: dict[str, Any], *, label: str) -> None:
    try:
        atomic_write_json(path, payload, indent=2, fsync=True)
    except OSError as exc:
        raise click.ClickException(f"Could not write {label}: {exc}") from exc


def _validate_report_output(source: Path, output: Path | None, artifact_root: Path | None) -> None:
    if output is None:
        return
    try:
        resolved_source = source.resolve(strict=True)
        resolved_output = output.resolve(strict=False)
        resolved_root = artifact_root.resolve(strict=True) if artifact_root is not None else None
    except OSError as exc:
        raise click.ClickException(f"Could not validate report output path: {exc}") from exc
    if resolved_output == resolved_source:
        raise click.UsageError("--output must not overwrite the expert-value review input")
    if resolved_root is not None and resolved_output.is_relative_to(resolved_root):
        raise click.UsageError("--output must be outside --artifact-root so verified evidence remains read-only")


def _emit_template(blueprint: ExpertBlueprint, output: Path | None) -> None:
    from deepr.evals.expert_value import expert_value_review_template

    payload = expert_value_review_template(blueprint)
    if output is None:
        click.echo(json.dumps(payload, indent=2, ensure_ascii=True))
        return
    _write_payload(output, payload, label="expert-value review template")
    click.echo(f"Wrote incomplete expert-value review template: {output}")
    click.echo("Complete every source world, arm, trial, semantic review, and operator attestation before evaluation.")


def _score(result: dict[str, Any], dimension: str) -> str:
    value = result["dimensions"][dimension]["mean_score"]
    return "n/a" if value is None else f"{value:.2f}/4"


def _rate(result: dict[str, Any], field: str) -> str:
    summary = result[field]
    value = summary["rate"]
    return "n/a" if value is None else f"{value:.1%}"


def _render_report(report: dict[str, Any], output: Path | None) -> None:
    protocol = report["protocol"]
    click.echo(f"Longitudinal expert-value review: {report['expert']['name']}")
    click.echo(
        f"Blueprint revision {report['expert']['blueprint_revision']}; "
        f"{protocol['source_world_count']} source worlds; "
        f"{protocol['acceptance_case_count']} cases; {protocol['attested_trial_count']} trials"
    )
    click.echo(
        f"Review: {protocol['review_blinding']}; randomized order: "
        f"{'yes' if protocol['review_order_randomized'] else 'no'}"
    )
    verification = report["artifact_verification"]
    if verification["independently_verified"]:
        click.echo(
            "Artifact integrity: local SHA-256 verified "
            f"({verification['verified_reference_count']} references, "
            f"{verification['verified_file_count']} files)"
        )
    else:
        click.echo("Artifact integrity: operator attested; referenced files were not independently opened")
    click.echo("Evaluator calls: 0 models, 0 providers, 0 network; evaluator cost: $0.00")
    click.echo("")
    for result in report["arm_results"]:
        click.echo(
            f"  {result['arm']}: correctness {_score(result, 'correctness')}; "
            f"support {_score(result, 'factual_support')}; "
            f"false support {_rate(result, 'false_support')}; "
            f"stale reuse {_rate(result, 'invalidated_belief_reuse')}; "
            f"negative transfer {_rate(result, 'negative_transfer')}"
        )
        click.echo(
            f"    observed cost ${result['costs_usd']['total_observed']:.2f}; "
            f"reviewer effort {result['reviewer_effort_minutes']['total']:.1f} minutes"
        )
    missing = protocol["missing_evaluation_roles"]
    if missing:
        click.echo("")
        click.echo(f"Coverage note: no cases were labeled for {', '.join(missing)}.")
    click.echo("")
    click.echo("Descriptive evidence only. No arm was ranked, no winner was selected, and no default changed.")
    if output is not None:
        click.echo(f"Wrote report: {output}")


def _evaluate_review(
    blueprint: ExpertBlueprint,
    source: Path,
    *,
    artifact_root: Path | None,
    output: Path | None,
    json_output: bool,
) -> None:
    from deepr.evals.expert_value import build_expert_value_report, load_expert_value_review
    from deepr.evals.expert_value_artifacts import verify_expert_value_artifacts

    _validate_report_output(source, output, artifact_root)
    try:
        review = load_expert_value_review(source)
        verification = verify_expert_value_artifacts(review, artifact_root) if artifact_root is not None else None
        report = build_expert_value_report(review, blueprint, artifact_verification=verification)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise click.ClickException(f"Invalid expert-value review: {exc}") from exc
    if output is not None:
        _write_payload(output, report, label="expert-value report")
    if json_output:
        click.echo(json.dumps(report, indent=2, ensure_ascii=True))
        return
    _render_report(report, output)


@evaluate.command("expert-value")
@click.argument("name")
@click.option("--template", "show_template", is_flag=True, help="Emit an incomplete review workbook.")
@click.option(
    "--from-file",
    "source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Validate and aggregate a completed operator-attested workbook.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Explicit path for the template or report JSON. No file is written by default.",
)
@click.option(
    "--artifact-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Recompute every declared SHA-256 digest inside this root before reporting.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the completed report as JSON.")
def eval_expert_value(
    name: str,
    show_template: bool,
    source: Path | None,
    output: Path | None,
    artifact_root: Path | None,
    json_output: bool,
) -> None:
    """Prepare or aggregate a frozen four-arm expert value review at $0.

    This command never runs an arm or judges answer text. An operator supplies
    semantic attestations after the four arms run under frozen source worlds.
    Attester identities and semantic labels are recorded assertions, not
    independently verified facts or claims of human authorship.
    """
    _validate_options(
        show_template=show_template,
        source=source,
        artifact_root=artifact_root,
        json_output=json_output,
    )
    blueprint = _load_current_blueprint(name)
    if show_template:
        _emit_template(blueprint, output)
        return
    if source is None:  # Defensive narrowing after option validation.
        raise click.UsageError("--from-file is required")
    _evaluate_review(
        blueprint,
        source,
        artifact_root=artifact_root,
        output=output,
        json_output=json_output,
    )


__all__ = ["eval_expert_value"]
