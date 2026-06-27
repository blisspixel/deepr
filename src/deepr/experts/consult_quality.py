"""Reviewed consult-quality scoring and safe promotion.

The consult trace miner produces semantic review cases, but deterministic code
must not score answer meaning. This module stores reviewer or calibrated-judge
scores, validates only the contract shape, and promotes accepted cases into
gap or eval artifacts without committing beliefs.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from deepr.core.contracts import Gap
from deepr.experts.consult_traces import (
    CONSULT_QUALITY_EVAL_CASE_KIND,
    CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION,
)
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.metacognitive_monitor import build_consult_trace_candidates_for_expert
from deepr.experts.monitor_promotion import (
    CONSULT_TRACE_EVAL_CASE_KIND,
    CONSULT_TRACE_EVAL_CASE_SCHEMA_VERSION,
)
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

CONSULT_QUALITY_REVIEW_SCHEMA_VERSION = "deepr-consult-quality-review-v1"
CONSULT_QUALITY_REVIEW_KIND = "deepr.eval.consult_quality_review"

ConsultQualityDecision = Literal["accept", "needs_improvement", "reject"]
ConsultQualityJudgeType = Literal["human", "calibrated_model"]
ConsultQualityTarget = Literal["none", "gap", "eval", "both"]


class ConsultQualityReviewError(ValueError):
    """Raised when a consult-quality review cannot be recorded safely."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hash_payload(parts: list[str]) -> str:
    seed = "|".join(parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _contract(*, apply: bool) -> dict[str, Any]:
    return {
        "read_only": not apply,
        "cost_usd": 0.0,
        "writes_expert_state": False,
        "writes_beliefs": False,
        "semantic_scores_from_reviewer": True,
        "lexical_verdict_allowed": False,
        "requires_reviewer": True,
        "auto_apply": False,
        "derived_from": CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION,
    }


def _validate_semantic_case(case: dict[str, Any]) -> None:
    if case.get("schema_version") != CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION:
        raise ConsultQualityReviewError("Consult quality case has an unsupported schema_version.")
    if case.get("kind") != CONSULT_QUALITY_EVAL_CASE_KIND:
        raise ConsultQualityReviewError("Consult quality case has an unsupported kind.")
    contract = case.get("contract") if isinstance(case.get("contract"), dict) else {}
    if contract.get("lexical_verdict_allowed") is not False:
        raise ConsultQualityReviewError("Consult quality case must forbid lexical semantic verdicts.")
    if contract.get("requires_human_or_calibrated_model_judge") is not True:
        raise ConsultQualityReviewError("Consult quality case must require a human or calibrated-model judge.")


def _rubric_by_dimension(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rubric: dict[str, dict[str, Any]] = {}
    for item in case.get("rubric", []) or []:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension", "")).strip()
        if dimension:
            rubric[dimension] = item
    if not rubric:
        raise ConsultQualityReviewError("Consult quality case must include at least one rubric dimension.")
    return rubric


def _normalize_scores(case: dict[str, Any], scores: dict[str, float]) -> list[dict[str, Any]]:
    rubric = _rubric_by_dimension(case)
    provided = set(scores)
    expected = set(rubric)
    missing = sorted(expected - provided)
    unknown = sorted(provided - expected)
    if missing:
        raise ConsultQualityReviewError(f"Missing score(s): {', '.join(missing)}.")
    if unknown:
        raise ConsultQualityReviewError(f"Unknown score dimension(s): {', '.join(unknown)}.")

    normalized: list[dict[str, Any]] = []
    for dimension, item in rubric.items():
        score = float(scores[dimension])
        score_min = float(item.get("score_min", 1))
        score_max = float(item.get("score_max", 5))
        if score < score_min or score > score_max:
            raise ConsultQualityReviewError(f"Score for {dimension} must be between {score_min:g} and {score_max:g}.")
        normalized.append(
            {
                "dimension": dimension,
                "score": score,
                "score_min": score_min,
                "score_max": score_max,
                "judge_question": str(item.get("judge_question", "")),
            }
        )
    return normalized


def _normalize_failure_labels(case: dict[str, Any], failure_labels: list[str]) -> list[str]:
    allowed = {str(label) for label in case.get("failure_labels", []) or []}
    normalized = []
    for label in failure_labels:
        cleaned = label.strip()
        if not cleaned:
            continue
        if cleaned not in allowed:
            raise ConsultQualityReviewError(f"Unknown failure label: {cleaned}.")
        normalized.append(cleaned)
    return sorted(set(normalized))


def _review_status(
    *,
    decision: ConsultQualityDecision,
    mean_score: float,
    minimum_mean_score: float,
    failure_labels: list[str],
) -> str:
    if decision == "reject":
        return "rejected"
    if decision == "needs_improvement":
        return "needs_improvement"
    if mean_score < minimum_mean_score:
        return "policy_blocked"
    if failure_labels:
        return "policy_blocked"
    return "accepted"


def build_consult_quality_review(
    *,
    expert_name: str,
    case: dict[str, Any],
    scores: dict[str, float],
    reviewer: str,
    decision: ConsultQualityDecision,
    judge_type: ConsultQualityJudgeType = "human",
    failure_labels: list[str] | None = None,
    notes: str = "",
    calibration_ref: str = "",
    candidate: dict[str, Any] | None = None,
    apply: bool = False,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a reviewed consult-quality score artifact without writing it."""
    if decision not in {"accept", "needs_improvement", "reject"}:
        raise ConsultQualityReviewError(f"Unsupported review decision: {decision}.")
    if judge_type not in {"human", "calibrated_model"}:
        raise ConsultQualityReviewError(f"Unsupported judge type: {judge_type}.")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ConsultQualityReviewError("Reviewer is required.")

    _validate_semantic_case(case)
    normalized_scores = _normalize_scores(case, scores)
    labels = _normalize_failure_labels(case, failure_labels or [])
    mean_score = sum(float(item["score"]) for item in normalized_scores) / len(normalized_scores)
    acceptance_policy = case.get("acceptance_policy") if isinstance(case.get("acceptance_policy"), dict) else {}
    minimum_mean_score = float(acceptance_policy.get("minimum_mean_score", 4.0) or 4.0)
    status = _review_status(
        decision=decision,
        mean_score=mean_score,
        minimum_mean_score=minimum_mean_score,
        failure_labels=labels,
    )
    eligible_promotions = list(acceptance_policy.get("eligible_promotions", []) or [])
    eligible_for_promotion = status == "accepted"
    source_input = case.get("input") if isinstance(case.get("input"), dict) else {}
    timestamp = generated_at or _utc_now()
    review_id = "consult_quality_" + _hash_payload(
        [
            expert_name,
            str(case.get("case_id", "")),
            reviewer,
            decision,
            ",".join(f"{item['dimension']}={item['score']}" for item in normalized_scores),
            ",".join(labels),
        ]
    )

    payload: dict[str, Any] = {
        "schema_version": CONSULT_QUALITY_REVIEW_SCHEMA_VERSION,
        "kind": CONSULT_QUALITY_REVIEW_KIND,
        "contract": _contract(apply=apply),
        "expert_name": expert_name,
        "review_id": review_id,
        "source": {
            "case_schema_version": str(case.get("schema_version", "")),
            "case_id": str(case.get("case_id", "")),
            "source_trace_id": str(case.get("source_trace_id", "")),
            "category": str(case.get("category", "")),
            "reason": str(source_input.get("reason", "")),
            "question_hash": str(source_input.get("question_hash", "")),
            "question_preview": str(source_input.get("question_preview", "")),
        },
        "judge": {
            "type": judge_type,
            "reviewer": reviewer,
            "calibration_ref": calibration_ref,
        },
        "decision": decision,
        "scores": normalized_scores,
        "mean_score": round(mean_score, 4),
        "failure_labels": labels,
        "notes": notes,
        "acceptance_policy": {
            "minimum_mean_score": minimum_mean_score,
            "eligible_promotions": eligible_promotions,
            "never_commits_beliefs": bool(acceptance_policy.get("never_commits_beliefs", True)),
            "requires_reviewer": bool(acceptance_policy.get("requires_reviewer", True)),
        },
        "review_status": status,
        "eligible_for_promotion": eligible_for_promotion,
        "promotion_policy": {
            "eligible_targets": eligible_promotions if eligible_for_promotion else [],
            "requires_apply": True,
            "never_commits_beliefs": True,
            "gap_or_eval_only": True,
        },
        "generated_at": timestamp.isoformat(),
    }
    if candidate is not None:
        payload["candidate"] = {
            "trace_id": str(candidate.get("trace_id", "")),
            "reason": str(candidate.get("reason", "")),
            "severity": int(candidate.get("severity", 0) or 0),
            "gap": candidate.get("gap", {}),
            "eval_case": candidate.get("eval_case", {}),
        }
    return payload


def _write_review_artifact(artifact: dict[str, Any], *, output_dir: Path | None) -> Path:
    root = output_dir or Path("data/benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"consult_quality_review_{artifact['review_id']}_{timestamp}.json"
    atomic_write_json(path, artifact)
    return path


def _eval_case_artifact(profile: ExpertProfile, review: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CONSULT_TRACE_EVAL_CASE_SCHEMA_VERSION,
        "kind": CONSULT_TRACE_EVAL_CASE_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "source_path_exposed": False,
            "derived_from": CONSULT_QUALITY_REVIEW_SCHEMA_VERSION,
            "review_required": True,
        },
        "expert_name": profile.name,
        "proposal_id": str(review["review_id"]),
        "source_trace_id": str(candidate.get("trace_id", "")),
        "source_quality_review_id": str(review["review_id"]),
        "case": candidate["eval_case"],
        "quality_review": {
            "review_id": str(review["review_id"]),
            "review_status": str(review["review_status"]),
            "mean_score": float(review["mean_score"]),
            "decision": str(review["decision"]),
            "failure_labels": list(review.get("failure_labels", []) or []),
        },
        "generated_at": _utc_now().isoformat(),
    }


def _write_eval_case_artifact(artifact: dict[str, Any], *, output_dir: Path | None) -> Path:
    root = output_dir or Path("data/benchmarks")
    root.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"consult_quality_case_{artifact['proposal_id']}_{timestamp}.json"
    atomic_write_json(path, artifact)
    return path


def _find_candidate(candidates: dict[str, Any], trace_id: str) -> dict[str, Any]:
    for candidate in candidates.get("candidates", []) or []:
        if isinstance(candidate, dict) and str(candidate.get("trace_id", "")) == trace_id:
            return candidate
    raise ConsultQualityReviewError(f"No consult quality candidate found for trace id '{trace_id}'.")


def _promotion_status(actions: list[dict[str, Any]], *, apply: bool) -> str:
    if not apply:
        return "preview"
    promotion_actions = [action for action in actions if action.get("action") != "write_quality_review"]
    if any(action.get("status") in {"promoted", "written"} for action in promotion_actions):
        return "promoted"
    if any(action.get("status") == "already_exists" for action in promotion_actions):
        return "already_exists"
    return "review_recorded"


def _review_action(review: dict[str, Any], *, apply: bool, output_dir: Path | None) -> dict[str, Any]:
    if not apply:
        return {
            "action": "write_quality_review",
            "status": "preview",
            "artifact": review,
            "would_write": str(output_dir or Path("data/benchmarks")),
        }
    path = _write_review_artifact(review, output_dir=output_dir)
    return {
        "action": "write_quality_review",
        "status": "written",
        "artifact": review,
        "path": str(path),
    }


def _blocked_action(action: str, review: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": action,
        "status": "blocked_by_review",
        "review_status": str(review["review_status"]),
        "reason": "Only accepted consult-quality reviews can promote candidates.",
    }


def _gap_action(
    profile: ExpertProfile,
    review: dict[str, Any],
    candidate: dict[str, Any],
    *,
    apply: bool,
    experts_base_path: Path | None,
) -> dict[str, Any]:
    if not review["eligible_for_promotion"]:
        return _blocked_action("promote_gap", review)

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
        proposal_id=str(review["review_id"]),
        evidence_refs=[
            f"consult_trace:{candidate.get('trace_id', '')}",
            f"consult_quality_review:{review['review_id']}",
        ],
        source="consult_quality_review",
    )
    return {
        "action": "promote_gap",
        "status": "promoted" if created else "already_exists",
        "gap": promoted.to_gap().to_dict(),
        "storage": "metacognition.knowledge_gaps",
    }


def _eval_action(
    profile: ExpertProfile,
    review: dict[str, Any],
    candidate: dict[str, Any],
    *,
    apply: bool,
    output_dir: Path | None,
) -> dict[str, Any]:
    if not review["eligible_for_promotion"]:
        return _blocked_action("write_eval_case", review)

    artifact = _eval_case_artifact(profile, review, candidate)
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


def review_consult_quality_candidate(
    profile: ExpertProfile,
    trace_id: str,
    *,
    scores: dict[str, float],
    reviewer: str,
    decision: ConsultQualityDecision,
    judge_type: ConsultQualityJudgeType = "human",
    failure_labels: list[str] | None = None,
    notes: str = "",
    calibration_ref: str = "",
    target: ConsultQualityTarget = "none",
    apply: bool = False,
    trace_path: Path | None = None,
    limit: int = 50,
    max_candidates: int = 20,
    output_dir: Path | None = None,
    experts_base_path: Path | None = None,
) -> dict[str, Any]:
    """Review one consult trace candidate and optionally promote accepted output."""
    if target not in {"none", "gap", "eval", "both"}:
        raise ConsultQualityReviewError(f"Unsupported promotion target: {target}.")

    candidates = build_consult_trace_candidates_for_expert(
        profile.name,
        path=trace_path,
        limit=max(0, limit),
        max_candidates=max(0, max_candidates),
    )
    candidate = _find_candidate(candidates, trace_id)
    case = candidate.get("semantic_eval_case")
    if not isinstance(case, dict):
        raise ConsultQualityReviewError(f"Candidate '{trace_id}' does not include a semantic quality case.")

    review = build_consult_quality_review(
        expert_name=profile.name,
        case=case,
        scores=scores,
        reviewer=reviewer,
        decision=decision,
        judge_type=judge_type,
        failure_labels=failure_labels,
        notes=notes,
        calibration_ref=calibration_ref,
        candidate=candidate,
        apply=apply,
    )
    actions = [_review_action(review, apply=apply, output_dir=output_dir)]
    if target in {"gap", "both"}:
        actions.append(
            _gap_action(
                profile,
                review,
                candidate,
                apply=apply,
                experts_base_path=experts_base_path,
            )
        )
    if target in {"eval", "both"}:
        actions.append(_eval_action(profile, review, candidate, apply=apply, output_dir=output_dir))

    payload = {
        **review,
        "trace_id": trace_id,
        "target": target,
        "applied": apply,
        "status": _promotion_status(actions, apply=apply),
        "actions": actions,
        "operation_source": {
            "candidate_schema_version": str(candidates.get("schema_version", "")),
            "case_schema_version": str(case.get("schema_version", "")),
            "source_trace_id": str(case.get("source_trace_id", "")),
        },
        "generated_at": _utc_now().isoformat(),
    }
    return payload
