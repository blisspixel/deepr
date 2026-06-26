"""Read-only metacognitive monitor over measured expert evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepr.experts.consult_traces import build_consult_trace_candidates, load_consult_traces
from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.self_model import build_expert_self_model

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

METACOGNITIVE_MONITOR_SCHEMA_VERSION = "deepr-metacognitive-monitor-v1"
METACOGNITIVE_MONITOR_KIND = "deepr.expert.metacognitive_monitor"


def _contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "stability": "experimental",
        "derived_view": True,
        "auto_apply": False,
        "review_required": True,
        "compatibility": {
            "additive_fields": True,
            "breaking_changes_require_new_schema_version": True,
            "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
        },
    }


def _proposal_id(expert_name: str, proposal_type: str, title: str, evidence_refs: list[str]) -> str:
    seed = "|".join([expert_name, proposal_type, title, *sorted(evidence_refs)])
    return f"meta_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _proposal(
    expert_name: str,
    *,
    proposal_type: str,
    target: str,
    title: str,
    rationale: str,
    evidence_refs: list[str],
    recommended_command: str,
    expected_effect: str,
) -> dict[str, Any]:
    proposal_id = _proposal_id(expert_name, proposal_type, title, evidence_refs)
    if "{proposal_id}" in recommended_command:
        recommended_command = recommended_command.format(proposal_id=proposal_id)
    return {
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "status": "review_required",
        "target": target,
        "title": title,
        "rationale": rationale,
        "evidence_refs": evidence_refs,
        "recommended_command": recommended_command,
        "expected_effect": expected_effect,
        "requires_human_review": True,
        "auto_apply": False,
    }


def _active_risks(self_model: dict[str, Any]) -> list[str]:
    risks = []
    for risk in self_model.get("unresolved_risks", []) or []:
        text = str(risk)
        if text.startswith("No unresolved self-model risks"):
            continue
        risks.append(text)
    return risks


def _self_model_proposals(profile: ExpertProfile, self_model: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    blocked = list(self_model.get("blocked_capabilities", []) or [])
    risks = _active_risks(self_model)
    if blocked or risks:
        proposals.append(
            _proposal(
                profile.name,
                proposal_type="self_model_review",
                target="self_model.blocked_capabilities",
                title="Review self-model blockers and risks",
                rationale=f"{len(blocked)} blocker(s) and {len(risks)} active risk(s) require review.",
                evidence_refs=[f"self_model:{self_model['schema_version']}"],
                recommended_command=f'deepr expert propose-self-model "{profile.name}" {{proposal_id}} --json',
                expected_effect="Clarify whether the expert needs gap-fill, source refresh, or operator setup.",
            )
        )

    calibration = self_model.get("calibration", {}) if isinstance(self_model.get("calibration"), dict) else {}
    avg_confidence = float(calibration.get("avg_confidence", 0.0) or 0.0)
    claim_count = int(calibration.get("claim_count", 0) or 0)
    if claim_count and avg_confidence < 0.5:
        proposals.append(
            _proposal(
                profile.name,
                proposal_type="calibration_review",
                target="self_model.calibration",
                title="Review low-confidence belief calibration",
                rationale=f"Average belief confidence is {avg_confidence:.2f} across {claim_count} claim(s).",
                evidence_refs=[f"self_model:{self_model['schema_version']}"],
                recommended_command=f'deepr expert propose-self-model "{profile.name}" {{proposal_id}} --json',
                expected_effect="Decide whether to refresh sources, lower reliance, or create targeted eval cases.",
            )
        )
    return proposals


def _loop_proposals(profile: ExpertProfile, loop_runs: list[ExpertLoopRun]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    failure_stops = {
        LoopStopReason.TOOL_FAILURE,
        LoopStopReason.VERIFIER_FAILED,
        LoopStopReason.SCHEMA_ERROR,
        LoopStopReason.MAX_ITERATIONS,
    }
    for run in loop_runs:
        evidence_refs = [f"loop_run:{run.run_id}"]
        if run.status == LoopRunStatus.FAILED or run.stop_reason in failure_stops:
            proposals.append(
                _proposal(
                    profile.name,
                    proposal_type="learning_strategy_update",
                    target="self_model.learning_strategy",
                    title=f"Review failed {run.loop_type} loop",
                    rationale=f"Loop stopped with status {run.status.value} and reason {run.stop_reason.value if run.stop_reason else 'unknown'}.",
                    evidence_refs=evidence_refs,
                    recommended_command=f'deepr expert propose-self-model "{profile.name}" {{proposal_id}} --json',
                    expected_effect="Turn the failed run into a reviewed gap, eval case, or safer retry strategy.",
                )
            )
        elif run.status == LoopRunStatus.WAITING and run.stop_reason == LoopStopReason.CAPACITY_UNAVAILABLE:
            proposals.append(
                _proposal(
                    profile.name,
                    proposal_type="capacity_strategy_review",
                    target="self_model.learning_strategy.capacity_order",
                    title=f"Review blocked {run.loop_type} capacity",
                    rationale="A learning loop is waiting for owned or prepaid capacity.",
                    evidence_refs=evidence_refs,
                    recommended_command=f'deepr expert propose-self-model "{profile.name}" {{proposal_id}} --json',
                    expected_effect="Decide whether to wait, admit local capacity, use explicit plan quota, or approve metered fallback.",
                )
            )
    return proposals


def _consult_candidate_proposals(profile: ExpertProfile, candidate_payload: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for candidate in candidate_payload.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        reason = str(candidate.get("reason", "consult_trace"))
        trace_id = str(candidate.get("trace_id", ""))
        evidence_refs = [f"consult_trace:{trace_id}"] if trace_id else ["consult_trace:unknown"]
        proposals.append(
            _proposal(
                profile.name,
                proposal_type="gap_or_eval_candidate",
                target="gap_backlog",
                title=f"Review consult trace candidate: {reason}",
                rationale=str(candidate.get("question_preview", "Consult trace candidate requires review.")),
                evidence_refs=evidence_refs,
                recommended_command=f'deepr expert promote-monitor "{profile.name}" {{proposal_id}} --target gap --apply',
                expected_effect="Promote the candidate into a gap-fill route or eval case only after review.",
            )
        )
    return proposals


def _trace_mentions_expert(trace: dict[str, Any], expert_name: str) -> bool:
    expected = expert_name.casefold()
    input_block = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    requested = [str(item).casefold() for item in input_block.get("requested_experts", []) or []]
    packet = trace.get("context_packet") if isinstance(trace.get("context_packet"), dict) else {}
    always = packet.get("always") if isinstance(packet.get("always"), dict) else {}
    consulted = [str(item).casefold() for item in always.get("experts_consulted", []) or []]
    selected = packet.get("selected", []) if isinstance(packet.get("selected"), list) else []
    selected_names = [str(item.get("expert", "")).casefold() for item in selected if isinstance(item, dict)]
    return expected in {*requested, *consulted, *selected_names}


def build_consult_trace_candidates_for_expert(
    expert_name: str,
    *,
    path: Path | None = None,
    limit: int = 50,
    max_candidates: int = 20,
    low_context_threshold: int = 1,
) -> dict[str, Any]:
    """Return sanitized consult trace candidates that mention one expert."""
    traces = [
        trace for trace in load_consult_traces(path=path, limit=limit) if _trace_mentions_expert(trace, expert_name)
    ]
    return build_consult_trace_candidates(
        traces,
        max_candidates=max_candidates,
        low_context_threshold=low_context_threshold,
    )


def build_metacognitive_monitor_report(
    profile: ExpertProfile,
    *,
    loop_runs: list[ExpertLoopRun] | None = None,
    consult_trace_candidates: dict[str, Any] | None = None,
    max_proposals: int = 20,
) -> dict[str, Any]:
    """Build review-required proposals from measured expert failures and risks."""
    max_proposals = max(0, max_proposals)
    self_model = build_expert_self_model(profile, profile.get_manifest(), focus_limit=3)
    runs = loop_runs if loop_runs is not None else ExpertLoopRunStore(profile.name).list_runs(limit=max_proposals or 1)
    candidate_payload = consult_trace_candidates or {
        "schema_version": "deepr-consult-trace-candidates-v1",
        "kind": "deepr.expert.consult_trace_candidates",
        "candidate_count": 0,
        "candidates": [],
    }
    proposals = [
        *_self_model_proposals(profile, self_model),
        *_loop_proposals(profile, runs),
        *_consult_candidate_proposals(profile, candidate_payload),
    ][:max_proposals]
    failed_loop_count = sum(1 for run in runs if run.status == LoopRunStatus.FAILED)
    waiting_capacity_count = sum(
        1
        for run in runs
        if run.status == LoopRunStatus.WAITING and run.stop_reason == LoopStopReason.CAPACITY_UNAVAILABLE
    )
    return {
        "schema_version": METACOGNITIVE_MONITOR_SCHEMA_VERSION,
        "kind": METACOGNITIVE_MONITOR_KIND,
        "contract": _contract(),
        "expert_name": profile.name,
        "inputs": {
            "self_model_schema_version": self_model["schema_version"],
            "loop_run_count": len(runs),
            "consult_trace_candidate_count": int(candidate_payload.get("candidate_count", 0) or 0),
        },
        "signals": {
            "blocked_capability_count": len(self_model.get("blocked_capabilities", []) or []),
            "active_risk_count": len(_active_risks(self_model)),
            "failed_loop_count": failed_loop_count,
            "waiting_capacity_count": waiting_capacity_count,
            "consult_trace_candidate_count": int(candidate_payload.get("candidate_count", 0) or 0),
        },
        "proposal_count": len(proposals),
        "proposals": proposals,
        "next_review": {
            "status": "review_required" if proposals else "no_actions",
            "auto_apply": False,
            "recommended_command": f'deepr expert monitor "{profile.name}" --json',
        },
    }
