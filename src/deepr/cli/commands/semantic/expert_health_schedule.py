"""Scheduler action-plan helpers for expert health checks."""

from __future__ import annotations

import json as _json
from typing import Any

import click

from deepr.cli.colors import console, print_section_header, print_warning
from deepr.experts.approval import ApprovalTier


def _quote_cli_arg(value: str) -> str:
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def _scheduled_action_status(action: Any) -> tuple[str, str]:
    estimated_cost = float(getattr(action, "estimated_cost", 0.0) or 0.0)
    approval_tier = str(getattr(action, "approval_tier", ""))
    if approval_tier == ApprovalTier.CONFIRM.value:
        return "waiting_for_confirmation", "This action requires explicit confirmation before a scheduler can run it."
    if estimated_cost > 0:
        return "waiting_for_capacity", "Scheduled health-check will not start metered corrective work."
    return "ready", "This action is eligible for scheduler execution."


def scheduled_health_action_plan(report: Any) -> dict[str, Any]:
    planned = []
    for action in report.actions:
        status, detail = _scheduled_action_status(action)
        action_dict = action.to_dict()
        action_dict["scheduler_status"] = status
        action_dict["scheduler_detail"] = detail
        planned.append(action_dict)

    statuses = {action["scheduler_status"] for action in planned}
    if not planned:
        status = "no_actions"
        detail = "No corrective actions are recommended."
    elif "waiting_for_confirmation" in statuses:
        status = "waiting_for_confirmation"
        detail = "At least one recommended health-check action requires explicit confirmation."
    elif "waiting_for_capacity" in statuses:
        status = "waiting_for_capacity"
        detail = "At least one recommended health-check action requires metered capacity."
    else:
        status = "ready"
        detail = "All recommended health-check actions are scheduler-eligible."

    return {
        "status": status,
        "detail": detail,
        "actions": planned,
    }


def scheduled_health_payload(report: Any) -> dict[str, Any]:
    payload = report.to_dict()
    payload["scheduled"] = True
    payload["scheduled_action_plan"] = scheduled_health_action_plan(report)
    return payload


def print_scheduled_health_action_plan(plan: dict[str, Any]) -> None:
    print_section_header("Scheduled action plan")
    console.print(f"  {plan['status']}: {plan['detail']}")
    for action in plan["actions"]:
        console.print(f"  - {action['scheduler_status']}: {action['description']}")
        console.print(f"    [dim]{action['scheduler_detail']}[/dim]")
        console.print(f"    [white]{action['command']}[/white]")


def scheduled_archive_confirmation_payload(expert_name: str, candidates: list[Any]) -> dict[str, Any]:
    return {
        "status": "waiting_for_confirmation",
        "expert": expert_name,
        "action": "archive_stale",
        "count": len(candidates),
        "candidates": [
            {
                "belief_id": b.id,
                "claim": b.claim,
                "confidence": round(b.get_current_confidence(), 3),
                "updated_at": b.updated_at.isoformat(),
                "retrieval_count": b.retrieval_count,
            }
            for b in candidates
        ],
        "next_actions": [
            {
                "status": "confirm",
                "title": "Archive stale beliefs",
                "detail": "This is $0 and reversible, but it still mutates the belief store.",
                "command": (
                    f"deepr expert health-check {_quote_cli_arg(expert_name)} --archive-stale --scheduled --yes"
                ),
            }
        ],
    }


def emit_scheduled_archive_confirmation(expert_name: str, candidates: list[Any], *, json_output: bool) -> None:
    payload = scheduled_archive_confirmation_payload(expert_name, candidates)
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_warning("Scheduled health-check archive is waiting for confirmation.")
    console.print(f"[dim]{payload['count']} stale belief(s) are eligible for reversible archival.[/dim]")
    for action in payload["next_actions"]:
        console.print(f"  {action['status']}: {action['title']}")
        console.print(f"      [dim]{action['detail']}[/dim]")
        console.print(f"      [dim]{action['command']}[/dim]")
