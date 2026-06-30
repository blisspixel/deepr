"""Plan-fleet validation helpers for the ``deepr capacity`` CLI."""

from __future__ import annotations

import json as _json
from typing import Any

import click

_FLEET_VALIDATION_SCHEMA_VERSION = "deepr-plan-fleet-validation-v1"
_FLEET_VALIDATION_KIND = "deepr.capacity.validate_fleet"
# Keep the wrapper above the plan subprocess guard (240s) so typed backend
# errors can surface instead of being masked by the validation wrapper timeout.
FLEET_VALIDATION_DEFAULT_TIMEOUT_S = 270.0


def build_fleet_validation_payload(
    adapters,
    *,
    transport: dict[str, Any],
    experts: tuple[str, ...],
    question: str | None,
    plan_model: str | None,
    concurrency: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Build one plan-fleet validation report from transport and consult checks."""
    from deepr.cli.async_runner import run_async_command
    from deepr.mcp.consult_validation import (
        DEFAULT_VALIDATION_QUESTION,
        run_in_process_plan_consult_fleet_validation,
    )

    transport_by_backend = {result["backend"]: result for result in transport["results"]}
    targets = tuple(
        _fleet_validation_consult_target(adapter, transport_result=transport_by_backend.get(adapter.backend_id))
        for adapter in adapters
    )
    consult = run_async_command(
        run_in_process_plan_consult_fleet_validation(
            targets=targets,
            question=question or DEFAULT_VALIDATION_QUESTION,
            experts=experts,
            plan_model=plan_model,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
        )
    )
    return _fleet_validation_payload(transport=transport, consult=consult, concurrency=concurrency)


def emit_fleet_validation_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return
    _print_fleet_validation(payload)


def _fleet_validation_consult_target(adapter, *, transport_result: dict[str, Any] | None):
    from deepr.mcp.consult_validation import PlanConsultFleetTarget

    installed = False
    skip_reason = ""
    if transport_result is None:
        skip_reason = "transport probe did not run"
    else:
        installed = bool(transport_result.get("installed"))
        error = str(transport_result.get("error") or "")
        if transport_result.get("skipped"):
            skip_reason = f"transport skipped: {error}".strip()
        elif transport_result.get("ok") is not True:
            skip_reason = f"transport failed: {error}".strip()
    return PlanConsultFleetTarget(
        plan=adapter.backend_id,
        name=adapter.display_name,
        installed=installed,
        experimental=adapter.experimental,
        metered_at_margin=adapter.metered_at_margin,
        tos_note=adapter.tos_note,
        skip_reason=skip_reason,
    )


def _fleet_validation_payload(
    *, transport: dict[str, Any], consult: dict[str, Any], concurrency: int
) -> dict[str, Any]:
    transport_ok = {result["backend"] for result in transport["results"] if result.get("ok") is True}
    consult_ok = {result["plan"] for result in consult["results"] if result.get("ok") is True}
    end_to_end_ok = sorted(transport_ok & consult_ok)
    selected_count = int(transport["selected_count"])
    skipped_count = int(transport["skipped_count"]) + int(consult["skipped_count"])
    failed_count = int(transport["failed_count"]) + int(consult["failed_count"])
    expected_ok = selected_count > 0 and len(end_to_end_ok) == selected_count
    summary_ok = expected_ok and failed_count == 0 and skipped_count == 0
    return {
        "schema_version": _FLEET_VALIDATION_SCHEMA_VERSION,
        "kind": _FLEET_VALIDATION_KIND,
        "contract": {
            "cost_usd": 0.0,
            "uses_plan_quota": True,
            "calls_metered_api": False,
            "live_metered_fallback": False,
            "quota_observations_recorded": True,
            "semantic_verdict": False,
            "checks_form_and_side_effects_only": True,
            "metered_backends_skipped_by_default": True,
        },
        "concurrency": concurrency,
        "selected_count": selected_count,
        "end_to_end_ok_count": len(end_to_end_ok),
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "summary": {
            "ok": summary_ok,
            "end_to_end_ok_backends": end_to_end_ok,
            "failed_transport_backends": [
                result["backend"]
                for result in transport["results"]
                if not result.get("skipped") and not result.get("ok")
            ],
            "skipped_transport_backends": [
                result["backend"] for result in transport["results"] if result.get("skipped")
            ],
            "failed_consult_plans": consult["summary"]["failed_plans"],
            "skipped_consult_plans": [result["plan"] for result in consult["results"] if result.get("skipped")],
        },
        "stages": {
            "transport": transport,
            "consult": consult,
        },
    }


def _print_fleet_validation(payload: dict[str, Any]) -> None:
    click.echo("Plan-quota fleet validation\n")
    click.echo("Transport")
    for result in payload["stages"]["transport"]["results"]:
        backend = result["backend"]
        if result["skipped"]:
            click.echo(f"[skip] {backend:12s} {result['error']}")
        elif result["ok"]:
            click.echo(f"[ok]   {backend:12s} replied {result['reply'][:60]!r} in {result['latency_ms']}ms")
        else:
            click.echo(f"[fail] {backend:12s} {result['error']}")
        if result.get("tos_note"):
            click.echo(f"       note: {result['tos_note']}")

    click.echo("\nConsult contract")
    for result in payload["stages"]["consult"]["results"]:
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

    click.echo(
        f"\n{payload['end_to_end_ok_count']} end-to-end ok, {payload['failed_count']} failed, "
        f"{payload['skipped_count']} skipped"
    )
