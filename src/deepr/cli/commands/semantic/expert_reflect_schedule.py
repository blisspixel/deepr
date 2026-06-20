"""Scheduler wait helpers for expert reflection."""

from __future__ import annotations

import json as _json
from typing import Any

import click

from deepr.cli.colors import console, print_warning

SCHEDULED_REFLECTION_WAIT_KIND = "deepr.expert.scheduled_reflection_wait"
SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION = "deepr-scheduled-reflection-wait-v1"


def _quote_cli_arg(value: str) -> str:
    return f'"{value.replace(chr(34), chr(92) + chr(34))}"'


def _scheduled_reflection_contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "stability": "experimental",
        "compatibility": {
            "additive_fields": True,
            "breaking_changes_require_new_schema_version": True,
            "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
        },
    }


def _reflect_command(
    expert_name: str,
    report_id: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
) -> str:
    depth_flag = "" if depth == 1 else f" --depth {depth}"
    followup_flags = f" --execute-followups --budget {budget:.2f} -y" if execute_followups else ""
    return f"deepr expert reflect {_quote_cli_arg(expert_name)} {_quote_cli_arg(report_id)}{depth_flag}{followup_flags}"


def scheduled_reflection_wait_payload(
    expert_name: str,
    report_id: str,
    question: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
) -> dict[str, Any]:
    detail = "scheduled reflection is waiting for owned/prepaid evaluator capacity instead of making a metered call"
    pending = ["reflection_evaluation"]
    if execute_followups:
        pending.append("followup_research")
    payload = {
        "schema_version": SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION,
        "kind": SCHEDULED_REFLECTION_WAIT_KIND,
        "contract": _scheduled_reflection_contract(),
        "status": "waiting_for_capacity",
        "expert_name": expert_name,
        "report_id": report_id,
        "question": question,
        "detail": detail,
        "scheduled": True,
        "depth": depth,
        "execute_followups": execute_followups,
        "followup_budget_ceiling": round(budget, 4) if execute_followups else 0.0,
        "pending_work": pending,
        "next_actions": [
            {
                "status": "wait",
                "title": "Wait for cheap evaluator capacity",
                "detail": (
                    "Rerun the scheduled job when a local or plan-quota reflection backend exists. "
                    "Scheduled mode does not start metered reflection or follow-up research."
                ),
            },
            {
                "status": "run_once",
                "title": "Run explicitly with the normal budget gates",
                "detail": "Remove --scheduled only when this one-off evaluation and any follow-ups may use metered capacity.",
                "command": _reflect_command(
                    expert_name,
                    report_id,
                    depth=depth,
                    execute_followups=execute_followups,
                    budget=budget,
                ),
            },
        ],
    }
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    loop_run = record_loop_run(
        expert_name=expert_name,
        loop_type="reflection_followups",
        goal=f"Reflect on report {report_id} and run follow-ups",
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        next_action=payload["next_actions"][0],
        budget_limit=budget if execute_followups else None,
        capacity_source="owned/prepaid",
    )
    payload["loop_run"] = loop_run.to_dict()
    return payload


def emit_scheduled_reflection_wait(
    expert_name: str,
    report_id: str,
    question: str,
    *,
    depth: int,
    execute_followups: bool,
    budget: float,
    json_output: bool,
) -> None:
    payload = scheduled_reflection_wait_payload(
        expert_name,
        report_id,
        question,
        depth=depth,
        execute_followups=execute_followups,
        budget=budget,
    )
    if json_output:
        click.echo(_json.dumps(payload, indent=2))
        return

    print_warning("Scheduled reflection is waiting for cheap evaluator capacity.")
    console.print(f"[dim]{payload['detail']}.[/dim]")
    for action in payload["next_actions"]:
        console.print(f"  {action['status']}: {action['title']}")
        if action.get("detail"):
            console.print(f"      [dim]{action['detail']}[/dim]")
        if action.get("command"):
            console.print(f"      [dim]{action['command']}[/dim]")
