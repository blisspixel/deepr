"""Read-only next-action guidance for one expert.

This module turns existing structural evidence into a short operator plan. It
does not judge semantic quality or claim that an expert has reached a maturity
level. Human review and calibrated evals remain the authority for meaning.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepr.core.contracts import ExpertManifest
    from deepr.experts.loop_runs import ExpertLoopRun
    from deepr.experts.profile import ExpertProfile

EXPERT_NEXT_SCHEMA_VERSION = "deepr-expert-next-v1"
EXPERT_NEXT_KIND = "deepr.expert.next"


def _status_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _action(
    action_id: str,
    *,
    priority: int,
    title: str,
    reason: str,
    command_argv: list[list[str]],
) -> dict[str, Any]:
    return {
        "id": action_id,
        "priority": priority,
        "title": title,
        "reason": reason,
        "command_argv": [list(argv) for argv in command_argv],
    }


def _learning_evidence(loop_runs: Iterable[ExpertLoopRun]) -> dict[str, Any]:
    runs = list(loop_runs)
    completed = [run for run in runs if _status_value(run.status) == "completed"]
    failed = [run for run in runs if _status_value(run.status) == "failed"]
    waiting = [run for run in runs if _status_value(run.status) == "waiting"]
    verified_improvements = [
        run
        for run in completed
        if int(run.accepted_changes) > 0
        and (
            _status_value(run.stop_reason) == "verifier_passed"
            or str(run.verifier_outcome).lower() in {"passed", "supported", "verified"}
        )
    ]
    latest = runs[0] if runs else None
    return {
        "run_count": len(runs),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "waiting_count": len(waiting),
        "verified_improvement_count": len(verified_improvements),
        "latest_status": _status_value(latest.status) if latest is not None else "none",
        "latest_stop_reason": _status_value(latest.stop_reason) if latest is not None else "",
    }


def _operational_stage(*, claim_count: int, freshness_status: str, learning: dict[str, Any]) -> str:
    if claim_count == 0:
        return "foundation"
    if freshness_status in {"stale", "incomplete"} or learning["latest_status"] == "failed":
        return "recovery"
    if learning["verified_improvement_count"] == 0:
        return "learning"
    return "maintenance"


def build_expert_next_actions(
    profile: ExpertProfile,
    manifest: ExpertManifest,
    *,
    loop_runs: Iterable[ExpertLoopRun] = (),
    max_actions: int = 3,
    has_attested_blueprint: bool,
) -> dict[str, Any]:
    """Build deterministic, read-only guidance from current expert evidence."""
    if max_actions < 1:
        raise ValueError("max_actions must be positive")

    name = profile.name
    domain = profile.domain or manifest.domain or profile.name
    freshness = profile.get_freshness_status()
    freshness_status = str(freshness.get("status", "unknown"))
    active_contradictions = sum(1 for claim in manifest.claims if claim.contradicts)
    learning = _learning_evidence(loop_runs)

    stage = _operational_stage(
        claim_count=manifest.claim_count,
        freshness_status=freshness_status,
        learning=learning,
    )

    actions: list[dict[str, Any]] = []
    if not has_attested_blueprint:
        actions.append(
            _action(
                "define_expert_purpose",
                priority=1,
                title="Define the expert's purpose and acceptance cases",
                reason="No operator-attested blueprint states which decisions this expert exists to improve.",
                command_argv=[
                    [
                        "deepr",
                        "expert",
                        "blueprint",
                        name,
                        "--template",
                        "--output",
                        "expert-blueprint.json",
                    ]
                ],
            )
        )
    if manifest.claim_count == 0:
        actions.append(
            _action(
                "seed_verified_knowledge",
                priority=1,
                title="Seed a verified knowledge foundation",
                reason="The expert has no canonical claims, so later reflection and recall have no grounded base.",
                command_argv=[
                    ["deepr", "expert", "subscribe", name, domain],
                    [
                        "deepr",
                        "capacity",
                        "next",
                        "--task-class",
                        "sync",
                        "--context-mode",
                        "fresh",
                        "--expert",
                        name,
                        "--scheduled",
                    ],
                    [
                        "deepr",
                        "expert",
                        "sync",
                        name,
                        "--scheduled",
                        "--fresh-context",
                        "--compile-claims",
                        "-y",
                    ],
                ],
            )
        )
    elif freshness_status in {"aging", "stale", "incomplete"}:
        actions.append(
            _action(
                "refresh_knowledge",
                priority=1 if freshness_status in {"stale", "incomplete"} else 2,
                title="Refresh changed source material",
                reason=f"Freshness is {freshness_status}; refresh before relying on old context for new decisions.",
                command_argv=[
                    [
                        "deepr",
                        "capacity",
                        "next",
                        "--task-class",
                        "sync",
                        "--context-mode",
                        "fresh",
                        "--expert",
                        name,
                        "--scheduled",
                    ],
                    [
                        "deepr",
                        "expert",
                        "sync",
                        name,
                        "--scheduled",
                        "--fresh-context",
                        "--compile-claims",
                        "-y",
                    ],
                ],
            )
        )

    if learning["latest_status"] in {"failed", "waiting"}:
        actions.append(
            _action(
                "inspect_loop_blockers",
                priority=1,
                title="Inspect blocked or failed learning loops",
                reason="A failed or waiting loop should be resolved before adding more unattended work.",
                command_argv=[["deepr", "expert", "loop-status", name, "--json"]],
            )
        )

    if manifest.open_gap_count:
        actions.append(
            _action(
                "route_high_value_gaps",
                priority=2,
                title="Route the highest-value open gaps",
                reason=f"The expert has {manifest.open_gap_count} open gap(s) that limit useful coverage.",
                command_argv=[["deepr", "expert", "route-gaps", name, "--execute", "--scheduled", "--top", "3"]],
            )
        )

    if active_contradictions:
        actions.append(
            _action(
                "review_contradictions",
                priority=2,
                title="Review contested beliefs before synthesis",
                reason=f"The manifest contains {active_contradictions} claim(s) with active contradictions.",
                command_argv=[["deepr", "expert", "contested", name]],
            )
        )

    if manifest.claim_count and learning["verified_improvement_count"] == 0:
        actions.append(
            _action(
                "establish_learning_evidence",
                priority=3,
                title="Establish a measured learning baseline",
                reason="No completed loop currently proves a verifier-passed accepted change.",
                command_argv=[
                    ["deepr", "eval", "continuity", name],
                    ["deepr", "expert", "monitor", name, "--json"],
                ],
            )
        )

    if not actions:
        actions.extend(
            [
                _action(
                    "review_metacognition",
                    priority=3,
                    title="Review the learning strategy",
                    reason="Core structural signals are healthy; inspect measured traces before changing policy.",
                    command_argv=[["deepr", "expert", "monitor", name, "--json"]],
                ),
                _action(
                    "refresh_derived_orientation",
                    priority=4,
                    title="Refresh the derived expert orientation",
                    reason="Keep the human and host-agent memory card aligned with canonical state.",
                    command_argv=[["deepr", "expert", "memory-card", name, "--write"]],
                ),
            ]
        )

    ordered_actions = sorted(actions, key=lambda item: (int(item["priority"]), str(item["id"])))[:max_actions]
    return {
        "schema_version": EXPERT_NEXT_SCHEMA_VERSION,
        "kind": EXPERT_NEXT_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "structural_signals_only": True,
            "semantic_maturity_verdict": False,
            "default_policy_change_allowed": False,
        },
        "expert": {"name": name, "domain": domain},
        "stage": stage,
        "evidence": {
            "claim_count": manifest.claim_count,
            "open_gap_count": manifest.open_gap_count,
            "avg_confidence": round(float(manifest.avg_confidence), 3),
            "freshness_status": freshness_status,
            "active_contradiction_claim_count": active_contradictions,
            "operator_attested_blueprint": has_attested_blueprint,
            "learning_loops": learning,
        },
        "next_actions": ordered_actions,
        "limitations": [
            "This report measures structural evidence, not answer quality or semantic maturity.",
            "Human or calibrated-model evaluation must judge whether a perspective actually improved.",
        ],
    }


__all__ = [
    "EXPERT_NEXT_KIND",
    "EXPERT_NEXT_SCHEMA_VERSION",
    "build_expert_next_actions",
]
