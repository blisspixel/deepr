"""Register the local four-arm operational rehearsal and its blinded review binding."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from deepr.cli.commands.eval import evaluate
from deepr.evals.expert_value_artifacts import ArtifactVerificationError
from deepr.evals.expert_value_blinding import bind_review_labels, build_blind_assignment, reviewer_criteria
from deepr.evals.expert_value_rehearsal import (
    RehearsalPlan,
    RehearsalPolicy,
    RehearsalRun,
    plan_from_blueprint,
    runtime_preflight,
    warmup_throughput,
)
from deepr.evals.expert_value_rehearsal_workbook import assemble_workbook
from deepr.evals.expert_value_sources import load_source_world_preparation
from deepr.experts.chat_backends import ExpertChatUnsupportedFeature

_FILE = click.Path(exists=True, dir_okay=False, path_type=Path)
_DIR = click.Path(exists=True, file_okay=False, path_type=Path)
_NEW = click.Path(dir_okay=False, path_type=Path)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Could not read {path.name}: {exc}") from exc


def _progress(total: int) -> Any:
    """One line per finished worker or terminal cell, so a multi-hour run is observable."""
    done = {"cells": 0}

    def show(record: dict[str, Any]) -> None:
        if record["event"] == "worker_finished":
            click.echo(f"  worker {record['worker_id']}: {record.get('status')}", err=True)
        elif record["event"] == "cell_terminal":
            done["cells"] += 1
            click.echo(
                f"[{done['cells']}/{total}] {record['case']} {record['arm']}: {record['status']}",
                err=True,
            )

    return show


def _require_new(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            raise click.ClickException(f"Refusing to overwrite {path}")


def _write_new(path: Path, payload: bytes) -> None:
    _require_new(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as handle:
        handle.write(payload)


def _normalized(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _key_is_separate(packet_out: Path, key_out: Path) -> bool:
    """The key's directory must be neither the packet's directory nor inside it."""
    packet_dir, key_dir = _normalized(packet_out.parent), _normalized(key_out.parent)
    return key_dir != packet_dir and not key_dir.startswith(packet_dir + os.sep)


@evaluate.group("expert-value-rehearsal")
def rehearsal() -> None:
    """Run and blind the local four-arm operational rehearsal ($0, unreviewed)."""


@rehearsal.command("plan")
@click.option("--blueprint", type=_FILE, required=True, help="Draft or accepted blueprint with acceptance cases.")
@click.option("--placement", type=_FILE, required=True, help="Organizer case placement mapping cases to worlds.")
@click.option("--output", type=_NEW, required=True, help="New question-only plan file.")
def plan_command(blueprint: Path, placement: Path, output: Path) -> None:
    """Extract a question-only case plan; criteria and roles are not copied."""
    try:
        plan = plan_from_blueprint(_read_json(blueprint), _read_json(placement))
    except (KeyError, ValidationError) as exc:
        raise click.ClickException(f"Invalid blueprint or placement: {exc}") from exc
    _write_new(output, (json.dumps(plan.model_dump(), indent=2, sort_keys=True) + "\n").encode("utf-8"))
    click.echo(f"Wrote {len(plan.cases)} question-only case(s) to {output}")


@rehearsal.command("run")
@click.option("--policy", "policy_path", type=_FILE, required=True, help="Frozen rehearsal policy JSON.")
@click.option("--plan", "plan_path", type=_FILE, required=True, help="Question-only plan JSON.")
@click.option("--from-file", "index_path", type=_FILE, required=True, help="Source-world preparation index.")
@click.option("--artifact-root", type=_DIR, required=True, help="Root containing the index and sources.")
@click.option("--run-root", type=click.Path(file_okay=False, path_type=Path), required=True, help="New run root.")
@click.option(
    "--min-tokens-per-second",
    type=click.FloatRange(min=0),
    default=5.0,
    show_default=True,
    help="Refuse to start when a short $0 warm-up generation is slower than this.",
)
@click.option(
    "--resume",
    is_flag=True,
    help="Continue an interrupted run root after verifying it; requires the same policy, plan and code.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the run summary as JSON.")
def run_command(
    policy_path: Path,
    plan_path: Path,
    index_path: Path,
    artifact_root: Path,
    run_root: Path,
    min_tokens_per_second: float,
    resume: bool,
    json_output: bool,
) -> None:
    """Execute all cells on the owned local model; local calls are recorded at $0.

    Every phase runs in its own worker process with a verified source copy and
    no inherited credentials. Answers are saved unreviewed; no score or
    winner is produced. Withhold the run root from reviewers: its file names
    identify arms.
    """
    import httpx

    try:
        policy = RehearsalPolicy.model_validate_json(policy_path.read_bytes())
        plan = RehearsalPlan.model_validate_json(plan_path.read_bytes())
        runtime = runtime_preflight(policy)
        runtime.update(warmup_throughput(policy, min_tokens_per_second=min_tokens_per_second))
        run = RehearsalRun(
            policy=policy,
            plan=plan,
            index_path=index_path,
            artifact_root=artifact_root,
            run_root=run_root,
            runtime=runtime,
            on_event=None if json_output else _progress(len(plan.cases) * 4),
            resume=resume,
        )
    except (
        OSError,
        ValidationError,
        ValueError,
        RuntimeError,
        ArtifactVerificationError,
        ExpertChatUnsupportedFeature,
        httpx.HTTPError,
    ) as exc:
        raise click.ClickException(f"Rehearsal refused before execution: {exc}") from exc
    summary = run.execute()
    if json_output:
        click.echo(json.dumps(summary, indent=2))
        return
    failed = ", ".join(summary["failed_checks"]) or "none"
    click.echo(
        f"{summary['status']}: {summary['terminal_cells']}/{summary['planned_cells']} terminal cells "
        f"({summary['answered']} answered, {summary['failed']} failed, {summary['blocked']} blocked); "
        f"failed checks: {failed}; API cost $0. Answers are unreviewed."
    )


@rehearsal.command("blind")
@click.option("--run-root", type=_DIR, required=True, help="Finished rehearsal run root.")
@click.option("--blueprint", type=_FILE, required=True, help="Blueprint supplying reviewer criteria.")
@click.option("--placement", type=_FILE, required=True, help="Organizer case placement.")
@click.option("--from-file", "index_path", type=_FILE, required=True, help="Source-world preparation index.")
@click.option("--artifact-root", type=_DIR, required=True, help="Root containing the index and sources.")
@click.option(
    "--world-claims",
    type=_FILE,
    default=None,
    help="Organizer world index with claim changes; adds each case's required label fields.",
)
@click.option("--rubric", type=_FILE, default=None, help="Optional reviewer rubric JSON.")
@click.option("--packet-out", type=_NEW, required=True, help="New reviewer packet (shareable).")
@click.option("--key-out", type=_NEW, required=True, help="New private assignment key (withhold).")
def blind_command(
    run_root: Path,
    blueprint: Path,
    placement: Path,
    index_path: Path,
    artifact_root: Path,
    world_claims: Path | None,
    rubric: Path | None,
    packet_out: Path,
    key_out: Path,
) -> None:
    """Write a blinded reviewer packet and a separate private assignment key."""
    if not _key_is_separate(packet_out, key_out):
        raise click.ClickException("Keep the private key outside the reviewer packet's directory")
    _require_new(packet_out, key_out)
    try:
        _, index, _, _, _ = load_source_world_preparation(index_path, artifact_root)
        cutoffs = {world.source_world_id: world.as_of for world in index.source_worlds}
        claims = _read_json(world_claims) if world_claims else None
        criteria = reviewer_criteria(_read_json(blueprint), _read_json(placement), cutoffs, claims)
        packet, key = build_blind_assignment(run_root, criteria, rubric=_read_json(rubric) if rubric else None)
    except (KeyError, ValueError, ArtifactVerificationError) as exc:
        raise click.ClickException(f"Blinding refused: {exc}") from exc
    _write_new(key_out, key)
    _write_new(packet_out, packet)
    parsed = json.loads(key)
    click.echo(
        f"Wrote a reviewer packet with {parsed['reviewable_cells']} of {parsed['planned_cells']} planned "
        f"answer(s); {parsed['answers_with_masked_markers']} had harness markers masked. "
        f"Keep {key_out.name} and the run root private."
    )


@rehearsal.command("bind-labels")
@click.option("--run-root", type=_DIR, required=True, help="Rehearsal run root holding the answers.")
@click.option("--key", "key_path", type=_FILE, required=True, help="Private assignment key.")
@click.option("--packet", "packet_path", type=_FILE, required=True, help="Reviewer packet the labels used.")
@click.option("--labels", "labels_path", type=_FILE, required=True, help="Frozen reviewer labels JSON.")
@click.option("--output", type=_NEW, required=True, help="New binding record.")
def bind_command(run_root: Path, key_path: Path, packet_path: Path, labels_path: Path, output: Path) -> None:
    """Join frozen labels to the key after one-to-one binding checks."""
    try:
        binding = bind_review_labels(
            run_root, key_path.read_bytes(), packet_path.read_bytes(), labels_path.read_bytes()
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"Label binding refused: {exc}") from exc
    _write_new(output, (json.dumps(binding, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    click.echo(f"Bound {len(binding['bound'])} label(s); reviewer identity and scores remain unverified.")


@rehearsal.command("workbook")
@click.option("--run-root", type=_DIR, required=True, help="Rehearsal run root; becomes the workbook artifact root.")
@click.option("--expert", "expert_name", required=True, help="Expert whose attested blueprint the cases must match.")
@click.option("--placement", type=_FILE, required=True, help="Organizer case placement with roles.")
@click.option("--world-claims", type=_FILE, required=True, help="Organizer world index with source counts and claims.")
@click.option("--key", "key_path", type=_FILE, required=True, help="Assignment key used for the labels.")
@click.option("--binding", "binding_path", type=_FILE, required=True, help="Output of bind-labels.")
@click.option("--review-set-id", required=True, help="Identifier for this review set.")
@click.option(
    "--protocol-attested-by",
    default=None,
    help="Your identity, attesting the protocol assertions. Omit to leave them for the operator.",
)
@click.option("--output", type=_NEW, required=True, help="New workbook JSON.")
def workbook_command(
    run_root: Path,
    expert_name: str,
    placement: Path,
    world_claims: Path,
    key_path: Path,
    binding_path: Path,
    review_set_id: str,
    protocol_attested_by: str | None,
    output: Path,
) -> None:
    """Assemble the strict expert-value workbook from recorded execution and bound labels.

    Validate the result with `deepr eval expert-value NAME --from-file OUTPUT
    --artifact-root RUN_ROOT`. Labels, reviewer identity and the protocol
    attestation are never generated by this command.
    """
    from deepr.cli.commands.eval_expert_value import _load_current_blueprint

    blueprint = _load_current_blueprint(expert_name)
    try:
        workbook = assemble_workbook(
            run_root,
            blueprint=blueprint,
            placement=_read_json(placement),
            world_claims=_read_json(world_claims),
            key_bytes=key_path.read_bytes(),
            binding=_read_json(binding_path),
            review_set_id=review_set_id,
            protocol_attested_by=protocol_attested_by,
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise click.ClickException(f"Workbook refused: {exc}") from exc
    _write_new(output, (json.dumps(workbook, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    state = "complete" if protocol_attested_by else "awaiting the operator's protocol attestation"
    click.echo(f"Wrote a workbook with {len(workbook['trials'])} trial(s), {state}.")


__all__ = ["rehearsal"]
