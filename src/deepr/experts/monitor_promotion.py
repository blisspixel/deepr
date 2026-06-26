"""Reviewed promotion for metacognitive monitor proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from deepr.core.contracts import Gap
from deepr.experts.loop_runs import ExpertLoopRunStore
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.metacognitive_monitor import (
    METACOGNITIVE_MONITOR_SCHEMA_VERSION,
    build_consult_trace_candidates_for_expert,
    build_metacognitive_monitor_report,
)
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

METACOGNITIVE_PROMOTION_SCHEMA_VERSION = "deepr-metacognitive-promotion-v1"
METACOGNITIVE_PROMOTION_KIND = "deepr.expert.metacognitive_promotion"
CONSULT_TRACE_EVAL_CASE_SCHEMA_VERSION = "deepr-consult-trace-eval-case-v1"
CONSULT_TRACE_EVAL_CASE_KIND = "deepr.eval.consult_trace_case"
PromotionTarget = Literal["gap", "eval", "both"]


class MonitorPromotionError(ValueError):
    """Raised when a monitor proposal cannot be promoted safely."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _contract(*, apply: bool) -> dict[str, Any]:
    return {
        "read_only": not apply,
        "cost_usd": 0.0,
        "derived_from": METACOGNITIVE_MONITOR_SCHEMA_VERSION,
        "requires_human_review": True,
        "auto_apply": False,
        "apply_required": True,
    }


def _trace_id_from_evidence(evidence_refs: list[str]) -> str:
    for ref in evidence_refs:
        prefix, _, value = ref.partition(":")
        if prefix == "consult_trace" and value:
            return value
    return ""


def _candidate_for_trace(candidate_payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
    for candidate in candidate_payload.get("candidates", []) or []:
        if isinstance(candidate, dict) and str(candidate.get("trace_id", "")) == trace_id:
            return candidate
    raise MonitorPromotionError(f"No consult trace candidate found for trace id '{trace_id}'.")


def _proposal_for_id(monitor_payload: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    for proposal in monitor_payload.get("proposals", []) or []:
        if isinstance(proposal, dict) and proposal.get("proposal_id") == proposal_id:
            return proposal
    raise MonitorPromotionError(f"No monitor proposal found for id '{proposal_id}'.")


def _promotion_status(actions: list[dict[str, Any]], *, apply: bool) -> str:
    if not apply:
        return "preview"
    if any(action.get("status") == "promoted" for action in actions):
        return "promoted"
    if any(action.get("status") == "written" for action in actions):
        return "promoted"
    return "already_exists"


def _gap_action(
    profile: ExpertProfile,
    proposal: dict[str, Any],
    candidate: dict[str, Any],
    *,
    apply: bool,
    experts_base_path: Path | None,
) -> dict[str, Any]:
    gap = Gap.from_dict(candidate["gap"])
    if not apply:
        return {
            "action": "promote_gap",
            "status": "preview",
            "gap": gap.to_dict(),
            "would_write": "metacognition.knowledge_gaps",
        }

    tracker = MetaCognitionTracker(
        profile.name,
        base_path=str(experts_base_path) if experts_base_path is not None else None,
    )
    promoted, created = tracker.promote_gap_candidate(
        gap,
        proposal_id=str(proposal["proposal_id"]),
        evidence_refs=list(proposal.get("evidence_refs", []) or []),
    )
    return {
        "action": "promote_gap",
        "status": "promoted" if created else "already_exists",
        "gap": promoted.to_gap().to_dict(),
        "storage": "metacognition.knowledge_gaps",
    }


def _eval_case_artifact(profile: ExpertProfile, proposal: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(candidate.get("trace_id", ""))
    return {
        "schema_version": CONSULT_TRACE_EVAL_CASE_SCHEMA_VERSION,
        "kind": CONSULT_TRACE_EVAL_CASE_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "source_path_exposed": False,
            "derived_from": METACOGNITIVE_PROMOTION_SCHEMA_VERSION,
        },
        "expert_name": profile.name,
        "proposal_id": str(proposal["proposal_id"]),
        "source_trace_id": trace_id,
        "case": candidate["eval_case"],
        "generated_at": _utc_now().isoformat(),
    }


def _write_eval_case_artifact(artifact: dict[str, Any], *, output_dir: Path | None) -> Path:
    root = output_dir or Path("data/benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S_%f")
    proposal_id = str(artifact["proposal_id"])
    path = root / f"consult_trace_case_{proposal_id}_{timestamp}.json"
    atomic_write_json(path, artifact)
    return path


def _eval_action(
    profile: ExpertProfile,
    proposal: dict[str, Any],
    candidate: dict[str, Any],
    *,
    apply: bool,
    output_dir: Path | None,
) -> dict[str, Any]:
    artifact = _eval_case_artifact(profile, proposal, candidate)
    if not apply:
        return {
            "action": "write_eval_case",
            "status": "preview",
            "artifact": artifact,
            "would_write": str(output_dir or Path("data/benchmarks")),
        }
    path = _write_eval_case_artifact(artifact, output_dir=output_dir)
    return {
        "action": "write_eval_case",
        "status": "written",
        "artifact": artifact,
        "path": str(path),
    }


def promote_monitor_proposal(
    profile: ExpertProfile,
    proposal_id: str,
    *,
    target: PromotionTarget = "gap",
    apply: bool = False,
    trace_path: Path | None = None,
    limit: int = 20,
    max_proposals: int = 20,
    output_dir: Path | None = None,
    experts_base_path: Path | None = None,
) -> dict[str, Any]:
    """Preview or apply one reviewed monitor proposal."""
    if target not in {"gap", "eval", "both"}:
        raise MonitorPromotionError(f"Unsupported promotion target: {target}")

    scan_limit = max(0, limit)
    proposal_limit = max(0, max_proposals)
    candidates = build_consult_trace_candidates_for_expert(
        profile.name,
        path=trace_path,
        limit=scan_limit,
        max_candidates=proposal_limit,
    )
    loop_runs = [] if scan_limit == 0 else ExpertLoopRunStore(profile.name).list_runs(limit=scan_limit)
    monitor = build_metacognitive_monitor_report(
        profile,
        loop_runs=loop_runs,
        consult_trace_candidates=candidates,
        max_proposals=proposal_limit,
    )
    proposal = _proposal_for_id(monitor, proposal_id)
    if proposal.get("proposal_type") != "gap_or_eval_candidate":
        raise MonitorPromotionError(
            f"Proposal '{proposal_id}' has type '{proposal.get('proposal_type')}' and is not promotable as gap/eval."
        )

    evidence_refs = list(proposal.get("evidence_refs", []) or [])
    trace_id = _trace_id_from_evidence(evidence_refs)
    if not trace_id:
        raise MonitorPromotionError(f"Proposal '{proposal_id}' does not reference a consult trace.")
    candidate = _candidate_for_trace(candidates, trace_id)

    actions: list[dict[str, Any]] = []
    if target in {"gap", "both"}:
        actions.append(
            _gap_action(
                profile,
                proposal,
                candidate,
                apply=apply,
                experts_base_path=experts_base_path,
            )
        )
    if target in {"eval", "both"}:
        actions.append(_eval_action(profile, proposal, candidate, apply=apply, output_dir=output_dir))

    return {
        "schema_version": METACOGNITIVE_PROMOTION_SCHEMA_VERSION,
        "kind": METACOGNITIVE_PROMOTION_KIND,
        "contract": _contract(apply=apply),
        "expert_name": profile.name,
        "proposal_id": proposal_id,
        "proposal_type": str(proposal["proposal_type"]),
        "target": target,
        "applied": apply,
        "status": _promotion_status(actions, apply=apply),
        "actions": actions,
        "source": {
            "monitor_schema_version": str(monitor["schema_version"]),
            "candidate_schema_version": str(candidates.get("schema_version", "")),
            "evidence_refs": evidence_refs,
        },
        "generated_at": _utc_now().isoformat(),
    }
