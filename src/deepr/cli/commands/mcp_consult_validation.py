"""MCP consult validation CLI helpers."""

from __future__ import annotations

import json
import shutil
import sys

import click

from deepr.cli.async_runner import run_async_command

_PLAN_BACKEND_IDS = ("codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot")


@click.command("validate-consult-fleet")
@click.option(
    "--plan",
    "plans",
    multiple=True,
    type=click.Choice(_PLAN_BACKEND_IDS),
    help="Plan backend to validate. Repeatable. Defaults to installed auto-routable backends.",
)
@click.option(
    "--all",
    "all_plans",
    is_flag=True,
    help="Validate every installed non-metered plan backend, including explicit-only experimental CLIs.",
)
@click.option("--expert", "experts", multiple=True, help="Expert to target. Repeatable.")
@click.option(
    "--question",
    default=None,
    help="Validation consult question. Defaults to a contract-focused prompt.",
)
@click.option("--plan-model", help="Optional model hint passed to each selected plan CLI.")
@click.option("--concurrency", type=click.IntRange(1, len(_PLAN_BACKEND_IDS)), default=4, show_default=True)
@click.option("--timeout", "timeout_seconds", default=60.0, show_default=True, type=click.FloatRange(min=0.1))
@click.option("--json", "as_json", is_flag=True, help="Emit the versioned fleet validation payload as JSON.")
def validate_consult_fleet(
    plans: tuple[str, ...],
    all_plans: bool,
    experts: tuple[str, ...],
    question: str | None,
    plan_model: str | None,
    concurrency: int,
    timeout_seconds: float,
    as_json: bool,
):
    """Validate no-metered consults across plan backends concurrently."""
    from deepr.backends.plan_quota import all_adapters
    from deepr.mcp.consult_validation import (
        DEFAULT_VALIDATION_QUESTION,
        run_in_process_plan_consult_fleet_validation,
    )

    if plans and all_plans:
        raise click.ClickException("Use either --plan or --all, not both.")

    adapter_index = {adapter.backend_id: adapter for adapter in all_adapters()}
    selected = _select_consult_fleet_adapters(adapter_index, plans=plans, all_plans=all_plans)
    targets = tuple(_consult_fleet_target(adapter) for adapter in selected)
    payload = run_async_command(
        run_in_process_plan_consult_fleet_validation(
            targets=targets,
            question=question or DEFAULT_VALIDATION_QUESTION,
            experts=experts,
            plan_model=plan_model,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
        )
    )

    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_consult_fleet_validation(payload)

    if payload["failed_count"] or payload["validated_count"] == 0:
        sys.exit(1)


def _select_consult_fleet_adapters(adapter_index, *, plans: tuple[str, ...], all_plans: bool):
    if plans:
        return [adapter_index[plan] for plan in plans]
    if all_plans:
        return [
            adapter
            for adapter in adapter_index.values()
            if _installed_plan_adapter(adapter) and not adapter.metered_at_margin
        ]
    return [
        adapter
        for adapter in adapter_index.values()
        if adapter.enabled_by_default and _installed_plan_adapter(adapter) and not adapter.metered_at_margin
    ]


def _consult_fleet_target(adapter):
    from deepr.mcp.consult_validation import PlanConsultFleetTarget

    installed = _installed_plan_adapter(adapter)
    skip_reason = ""
    if not installed:
        skip_reason = "not installed on PATH"
    elif adapter.metered_at_margin:
        skip_reason = "metered-at-margin backend skipped"
    return PlanConsultFleetTarget(
        plan=adapter.backend_id,
        name=adapter.display_name,
        installed=installed,
        experimental=adapter.experimental,
        metered_at_margin=adapter.metered_at_margin,
        tos_note=adapter.tos_note,
        skip_reason=skip_reason,
    )


def _installed_plan_adapter(adapter) -> bool:
    return shutil.which(adapter.exe) is not None


def _print_consult_fleet_validation(payload) -> None:
    click.echo("MCP consult fleet validation\n")
    for result in payload["results"]:
        plan = result["plan"]
        if result["skipped"]:
            click.echo(f"[skip] {plan:12s} {result['error'].get('message', '')}")
        elif result["ok"]:
            summary = result.get("consult_summary", {})
            trace_id = summary.get("trace_id") or "-"
            click.echo(f"[ok]   {plan:12s} trace={trace_id}")
        else:
            failed = ", ".join(result.get("summary", {}).get("failed_checks", [])) or "validation failed"
            click.echo(f"[fail] {plan:12s} {failed}")
        if result.get("tos_note"):
            click.echo(f"       note: {result['tos_note']}")
    click.echo(
        f"\n{payload['ok_count']} ok, {payload['failed_count']} failed, "
        f"{payload['skipped_count']} skipped, {payload['validated_count']} validated"
    )
