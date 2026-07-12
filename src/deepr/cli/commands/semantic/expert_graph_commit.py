"""Graph commit apply CLI command."""

from __future__ import annotations

import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from deepr.cli.colors import print_error, print_info, print_success, print_warning
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.beliefs import BeliefStore
from deepr.experts.graph_commit_apply import (
    GRAPH_COMMIT_APPLY_KIND,
    GRAPH_COMMIT_APPLY_SCHEMA_VERSION,
    apply_graph_commit_envelope,
)
from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.profile import ExpertStore


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise click.ClickException(f"Expected a JSON object in {path}")
    return payload


def _load_profile_or_exit(name: str):
    profile = ExpertStore().load(name)
    if profile is None:
        raise click.ClickException(f"Expert not found: {name}")
    return profile


def _blocked_result(preview: dict[str, Any], reason: str) -> dict[str, Any]:
    result = copy.deepcopy(preview)
    result["contract"]["read_only"] = True
    result["contract"]["writes_graph"] = False
    result["contract"]["writes_expert_state"] = False
    result["summary"]["status"] = "blocked"
    failures = list(result["summary"].get("failure_reasons", []))
    if reason not in failures:
        failures.append(reason)
    result["summary"]["failure_reasons"] = sorted(failures)
    return result


def _lock_blocked_result(expert_name: str) -> dict[str, Any]:
    return {
        "schema_version": GRAPH_COMMIT_APPLY_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_APPLY_KIND,
        "contract": {
            "read_only": True,
            "semantic_judgment": False,
            "model_calls": False,
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_expert_state": False,
            "idempotent_operations": True,
            "requires_explicit_command": True,
            "breaking_changes_require_new_schema_version": True,
        },
        "input": {
            "envelope_schema_version": "",
            "envelope_kind": "",
            "envelope_status": "",
            "operation_count": 0,
        },
        "target": {"expert_name": expert_name},
        "summary": {
            "status": "blocked",
            "dry_run": True,
            "planned_write_count": 0,
            "applied_write_count": 0,
            "already_applied_count": 0,
            "blocked_operation_count": 0,
            "failure_reasons": ["expert_graph_commit_apply_locked"],
        },
        "operation_results": [],
        "generated_at": "",
    }


def _requires_confirmation(preview: dict[str, Any], dry_run: bool, yes: bool) -> bool:
    if dry_run or yes:
        return False
    return int(preview.get("summary", {}).get("planned_write_count", 0) or 0) > 0


def _confirmed(preview: dict[str, Any], dry_run: bool, yes: bool) -> bool:
    if not _requires_confirmation(preview, dry_run, yes):
        return True
    if not sys.stdin.isatty():
        return False
    planned = int(preview["summary"]["planned_write_count"])
    return click.confirm(f"Apply {planned} graph commit operation(s) to expert state?", default=False)


def _emit_human_result(result: dict[str, Any]) -> None:
    summary = result.get("summary", {})
    status = str(summary.get("status", "unknown"))
    if status == "blocked":
        print_error("Graph commit apply blocked")
    elif status == "dry_run":
        print_info("Graph commit apply dry run complete")
    elif status == "already_applied":
        print_info("Graph commit already applied")
    else:
        print_success("Graph commit applied")

    click.echo(f"Status: {status}")
    click.echo(f"Planned writes: {summary.get('planned_write_count', 0)}")
    click.echo(f"Applied writes: {summary.get('applied_write_count', 0)}")
    click.echo(f"Already applied: {summary.get('already_applied_count', 0)}")
    click.echo(f"Blocked operations: {summary.get('blocked_operation_count', 0)}")
    failures = summary.get("failure_reasons", [])
    if failures:
        click.echo("Failure reasons: " + ", ".join(str(item) for item in failures))


@expert.command(name="apply-graph-commit")
@click.argument("name")
@click.argument("envelope", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Validate and preview the apply result without writing.")
@click.option("--yes", "-y", is_flag=True, help="Apply without an interactive confirmation prompt.")
@click.option("--json", "json_output", is_flag=True, help="Emit the apply result as JSON.")
def expert_apply_graph_commit(name: str, envelope: Path, dry_run: bool, yes: bool, json_output: bool) -> None:
    """Apply a verified graph commit envelope to an expert belief graph."""
    profile = _load_profile_or_exit(name)
    payload = _load_json_file(envelope)

    with expert_verb_lock(profile.name, "graph-commit-apply") as acquired:
        if not acquired:
            result = _lock_blocked_result(profile.name)
            if json_output:
                click.echo(json.dumps(result, indent=2))
            else:
                print_warning("Another graph commit apply is already running for this expert.")
            raise click.exceptions.Exit(2)

        preview = apply_graph_commit_envelope(
            payload,
            BeliefStore(profile.name),
            gap_tracker=MetaCognitionTracker(profile.name),
            dry_run=True,
        )
        if not _confirmed(preview, dry_run, yes):
            result = _blocked_result(preview, "confirmation_required")
            if json_output:
                click.echo(json.dumps(result, indent=2))
            else:
                print_error("Refusing to apply expert-state writes without interactive confirmation or --yes.")
            raise click.exceptions.Exit(2)

        if dry_run:
            result = preview
        else:
            result = apply_graph_commit_envelope(
                payload,
                BeliefStore(profile.name),
                gap_tracker=MetaCognitionTracker(profile.name),
                dry_run=False,
            )

    if bool(result.get("contract", {}).get("writes_graph")):
        from deepr.experts.knowledge_freshness import advance_knowledge_freshness

        advance_knowledge_freshness(profile, datetime.now(UTC))
        ExpertStore().save(profile)

    if json_output:
        click.echo(json.dumps(result, indent=2))
    else:
        _emit_human_result(result)

    if result.get("summary", {}).get("status") == "blocked":
        raise click.exceptions.Exit(2)
