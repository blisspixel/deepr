"""Prepare unreviewed drafts and record operator-attested blueprints."""

from __future__ import annotations

import json
from pathlib import Path

import click
from pydantic import ValidationError

from deepr.cli.colors import print_info, print_success
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.blueprint import (
    BlueprintStorageError,
    ExpertBlueprint,
    ExpertBlueprintDraft,
    ExpertBlueprintStore,
    blueprint_template,
    build_blueprint_preflight,
    load_blueprint_draft,
)
from deepr.utils.atomic_io import atomic_write_json


def _json_dump(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _normalized_name(name: str) -> str:
    return " ".join(name.split())


def _validate_options(
    *,
    show_template: bool,
    source: Path | None,
    output: Path | None,
    apply_revision: bool,
    attested_by: str | None,
) -> None:
    if show_template and (source is not None or apply_revision or attested_by is not None):
        raise click.UsageError("--template cannot be combined with --from-file, --apply, or --attested-by")
    if output is not None and not show_template and source is None:
        raise click.UsageError("--output requires --template or --from-file")
    if output is not None and apply_revision:
        raise click.UsageError("--output is only for template or unreviewed preflight artifacts")
    if apply_revision and source is None:
        raise click.UsageError("--apply requires --from-file")
    if apply_revision and attested_by is None:
        raise click.UsageError("--apply requires --attested-by")
    if attested_by is not None and not apply_revision:
        raise click.UsageError("--attested-by is only valid with --apply")


def _validate_draft_name(name: str, draft: ExpertBlueprintDraft) -> None:
    if draft.expert_name != _normalized_name(name):
        raise click.ClickException(
            f"Blueprint expert_name '{draft.expert_name}' does not match command name '{_normalized_name(name)}'"
        )


def _print_blueprint_summary(blueprint: ExpertBlueprint) -> None:
    click.echo(f"Blueprint revision {blueprint.revision}")
    click.echo(f"Expert: {blueprint.expert_name}")
    click.echo(f"Mission: {blueprint.mission}")
    click.echo(f"Decision use cases: {len(blueprint.decision_use_cases)}")
    click.echo(f"Acceptance cases: {len(blueprint.acceptance_cases)}")
    click.echo(f"Operator attestation: {blueprint.attestation.attested_by}")
    click.echo("Reviewer identity independently verified: no")


def _print_draft_summary(draft: ExpertBlueprintDraft) -> None:
    click.echo("Validated blueprint draft")
    click.echo(f"Expert: {draft.expert_name}")
    click.echo(f"Mission: {draft.mission}")
    click.echo(f"Decision use cases: {len(draft.decision_use_cases)}")
    click.echo(f"Acceptance cases: {len(draft.acceptance_cases)}")
    print_info("Structurally valid but unreviewed. No human review is claimed.")
    print_info("This draft is non-authoritative and no canonical blueprint revision was written.")


def _emit_template(name: str, output: Path | None) -> None:
    payload = blueprint_template(name)
    if output is None:
        click.echo(_json_dump(payload))
        return
    try:
        atomic_write_json(output, payload, indent=2, fsync=True)
    except OSError as exc:
        raise click.ClickException(f"Could not write unreviewed blueprint draft template: {exc}") from exc
    print_success(f"Wrote unreviewed blueprint draft template: {output}")


def _read_draft(name: str, source: Path) -> ExpertBlueprintDraft:
    try:
        draft = load_blueprint_draft(source)
        _validate_draft_name(name, draft)
        return draft
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise click.ClickException(f"Invalid blueprint: {exc}") from exc


def _validate_preflight_output(source: Path, output: Path | None) -> None:
    if output is None:
        return
    try:
        resolved_source = source.resolve(strict=True)
        resolved_output = output.resolve(strict=False)
    except OSError as exc:
        raise click.ClickException(f"Could not validate blueprint preflight output path: {exc}") from exc
    if resolved_output == resolved_source:
        raise click.UsageError("--output must not overwrite the unreviewed blueprint draft")


def _handle_source(
    name: str,
    source: Path,
    *,
    apply_revision: bool,
    attested_by: str | None,
    output: Path | None,
    json_output: bool,
) -> None:
    if not apply_revision:
        _validate_preflight_output(source, output)
    draft = _read_draft(name, source)
    if not apply_revision:
        preflight = build_blueprint_preflight(draft)
        if output is not None:
            try:
                atomic_write_json(output, preflight, indent=2, fsync=True)
            except OSError as exc:
                raise click.ClickException(f"Could not write blueprint preflight: {exc}") from exc
        if json_output:
            click.echo(_json_dump(preflight))
        else:
            _print_draft_summary(draft)
            if output is not None:
                print_success(f"Wrote non-authoritative blueprint preflight: {output}")
        return

    try:
        result = ExpertBlueprintStore().apply(draft, attested_by=attested_by or "")
    except (BlueprintStorageError, ValidationError, ValueError) as exc:
        raise click.ClickException(f"Could not apply blueprint: {exc}") from exc
    if json_output:
        click.echo(_json_dump(result.blueprint.model_dump(mode="json")))
        return
    if result.appended:
        print_success(f"Applied operator-attested blueprint revision {result.blueprint.revision}.")
    else:
        print_info(f"Blueprint revision {result.blueprint.revision} already matches this file.")
    _print_blueprint_summary(result.blueprint)


def _show_current(name: str, *, json_output: bool) -> None:
    normalized_name = _normalized_name(name)
    try:
        current = ExpertBlueprintStore().load_latest(normalized_name)
    except BlueprintStorageError as exc:
        raise click.ClickException(f"Could not load blueprint: {exc}") from exc
    if current is None:
        raise click.ClickException(
            "No operator-attested blueprint exists. Start with an unreviewed draft: "
            f'deepr expert blueprint "{normalized_name}" --template --output expert-blueprint.json'
        )
    if json_output:
        click.echo(_json_dump(current.model_dump(mode="json")))
        return
    _print_blueprint_summary(current)


@expert.command(name="blueprint")
@click.argument("name")
@click.option(
    "--template",
    "show_template",
    is_flag=True,
    help="Emit an editable, explicitly unreviewed blueprint draft template.",
)
@click.option(
    "--from-file",
    "source",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Preflight an unreviewed draft or apply it with operator attestation.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write a template or non-authoritative preflight artifact atomically.",
)
@click.option("--apply", "apply_revision", is_flag=True, help="Append an operator-attested canonical revision.")
@click.option(
    "--attested-by",
    "attested_by",
    help="Operator identity attesting that scope and acceptance review is complete.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def expert_blueprint(
    name: str,
    show_template: bool,
    source: Path | None,
    output: Path | None,
    apply_revision: bool,
    attested_by: str | None,
    json_output: bool,
) -> None:
    """Prepare a draft or show an operator-attested purpose and acceptance contract.

    Templates and preflight artifacts are explicitly unreviewed and
    non-authoritative. Applying records an operator attestation through a local,
    append-only write with no model calls, spend, or knowledge mutation. Deepr
    does not verify reviewer identity or claim human authorship.
    """
    _validate_options(
        show_template=show_template,
        source=source,
        output=output,
        apply_revision=apply_revision,
        attested_by=attested_by,
    )

    if show_template:
        _emit_template(name, output)
        return
    if source is not None:
        _handle_source(
            name,
            source,
            apply_revision=apply_revision,
            attested_by=attested_by,
            output=output,
            json_output=json_output,
        )
        return
    _show_current(name, json_output=json_output)


__all__ = ["expert_blueprint"]
