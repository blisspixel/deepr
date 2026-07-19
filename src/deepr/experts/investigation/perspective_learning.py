"""Staged non-factual perspective learning from expert investigation positions."""

from __future__ import annotations

from typing import Any

from deepr.experts.graph_commit_envelope import (
    GRAPH_COMMIT_ENVELOPE_KIND,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
)
from deepr.experts.investigation.models import sha256_json, utc_now

_OPERATION_BY_STATE_TYPE = {
    "hypothesis": ("promote_hypothesis", "hypothesis"),
    "concept": ("promote_concept", "concept"),
    "stance": ("promote_stance", "stance"),
    "original_idea": ("promote_original_idea", "original_idea"),
}


def _assessment_index(check: dict[str, Any], expert_name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in check.get("perspective_assessments", []) or []:
        if not isinstance(raw, dict) or raw.get("expert_name") != expert_name:
            continue
        candidate_id = str(raw.get("candidate_id", "") or "")
        if candidate_id:
            result[candidate_id] = raw
    return result


def _common_state(candidate: dict[str, Any], *, origin: str, generated_at: str) -> dict[str, Any]:
    return {
        "origin": origin,
        "rationale": str(candidate.get("rationale", "") or ""),
        "uncertainty": str(candidate.get("uncertainty", "") or ""),
        "expected_observations": list(candidate.get("expected_observations", []) or []),
        "disconfirming_signals": list(candidate.get("disconfirming_signals", []) or []),
        "priority": int(candidate.get("priority", 3) or 3),
        "confidence": float(candidate.get("confidence", 0.0) or 0.0),
        "created_at": generated_at,
        "status": "active",
    }


def _state_payload(
    candidate: dict[str, Any],
    *,
    origin: str,
    generated_at: str,
) -> tuple[str, str, dict[str, Any]]:
    state_type = str(candidate.get("state_type", "") or "")
    operation, payload_key = _OPERATION_BY_STATE_TYPE[state_type]
    title = str(candidate.get("title", "") or "")
    statement = str(candidate.get("statement", "") or "")
    common = _common_state(candidate, origin=origin, generated_at=generated_at)
    if state_type == "hypothesis":
        payload = {
            "id": sha256_json({"title": title, "statement": statement})[:12],
            "title": title,
            "statement": statement,
            "assumptions": list(candidate.get("assumptions", []) or []),
            **common,
        }
    elif state_type == "concept":
        payload = {
            "id": sha256_json({"name": title, "description": statement})[:12],
            "name": title,
            "description": statement,
            "key_properties": list(candidate.get("assumptions", []) or []),
            "related_terms": [],
            **common,
        }
    elif state_type == "stance":
        payload = {
            "id": sha256_json({"title": title, "position": statement})[:12],
            "title": title,
            "position": statement,
            "tradeoffs": list(candidate.get("implications", []) or []),
            "decision_criteria": list(candidate.get("assumptions", []) or []),
            **common,
        }
    else:
        payload = {
            "id": sha256_json({"title": title, "statement": statement})[:12],
            "title": title,
            "statement": statement,
            "assumptions": list(candidate.get("assumptions", []) or []),
            "implications": list(candidate.get("implications", []) or []),
            **common,
        }
    return operation, payload_key, payload


def _operation(
    candidate: dict[str, Any],
    *,
    expert_name: str,
    run_id: str,
    position_artifact: str,
    check_artifact: str,
    generated_at: str,
) -> dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    origin = f"investigation:{run_id}:{expert_name}:{candidate_id}"
    operation_name, payload_key, payload = _state_payload(
        candidate,
        origin=origin,
        generated_at=generated_at,
    )
    idempotency_material = {
        "schema_version": GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "operation": operation_name,
        "expert_name": expert_name,
        "candidate_id": candidate_id,
        "payload": payload,
        "position_artifact": position_artifact,
        "check_artifact": check_artifact,
    }
    idempotency_key = sha256_json(idempotency_material)
    return {
        "operation_id": f"op_{idempotency_key[:16]}",
        "operation": operation_name,
        "candidate_id": candidate_id,
        "decision_status": "model_assessed_well_formed",
        payload_key: payload,
        "idempotency_key": idempotency_key,
        "provenance": {
            "position_artifact": position_artifact,
            "check_artifact": check_artifact,
            "source_refs": list(candidate.get("source_refs", []) or []),
            "source_ref_role": "inspiration_or_context_not_truth_or_novelty_proof",
            "dialogue_is_evidence": False,
            "truth_verified": False,
            "novelty_verified": False,
        },
    }


def build_perspective_graph_commit_envelope(
    *,
    run_id: str,
    expert_name: str,
    domain: str,
    position: dict[str, Any],
    check: dict[str, Any],
    position_artifact: str,
    check_artifact: str,
) -> dict[str, Any]:
    """Build explicit-apply perspective operations without treating them as facts."""
    assessments = _assessment_index(check, expert_name)
    generated_at = str(position.get("generated_at", "") or utc_now())
    operations: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for candidate in position.get("perspective_candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("candidate_id", "") or "")
        reasons = list(candidate.get("form_failure_reasons", []) or [])
        state_type = str(candidate.get("state_type", "") or "")
        if state_type not in _OPERATION_BY_STATE_TYPE:
            reasons.append("unsupported_perspective_state_type")
        assessment = assessments.get(candidate_id)
        if not isinstance(assessment, dict) or assessment.get("status") != "well_formed":
            reasons.append("perspective_not_model_assessed_well_formed")
        if reasons:
            blocked.append(
                {
                    "candidate_id": candidate_id,
                    "state_type": state_type,
                    "failure_reasons": sorted(set(str(reason) for reason in reasons)),
                }
            )
            continue
        operations.append(
            _operation(
                candidate,
                expert_name=expert_name,
                run_id=run_id,
                position_artifact=position_artifact,
                check_artifact=check_artifact,
                generated_at=generated_at,
            )
        )
    if operations:
        status = "ready_for_commit"
    elif blocked:
        status = "blocked"
    else:
        status = "empty"
    failure_reasons = sorted({reason for item in blocked for reason in item.get("failure_reasons", [])})
    return {
        "schema_version": GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_ENVELOPE_KIND,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "model_calls": False,
            "cost_usd": 0.0,
            "writes_graph": False,
            "apply_requires_explicit_command": True,
            "idempotent_operations": True,
            "human_reviewed": False,
            "factual_belief_writes": False,
            "truth_verified": False,
            "novelty_verified": False,
            "model_assessment_scope": "form_internal_coherence_and_testability",
        },
        "input": {
            "position_artifact": position_artifact,
            "position_schema_version": str(position.get("schema_version", "") or ""),
            "check_artifact": check_artifact,
            "check_schema_version": str(check.get("schema_version", "") or ""),
            "perspective_candidate_count": len(position.get("perspective_candidates", []) or []),
        },
        "target": {
            "expert_name": expert_name,
            "domain": domain,
            "authority": "non_factual_perspective_state",
        },
        "summary": {
            "status": status,
            "ready_write_count": len(operations),
            "ready_edge_count": 0,
            "blocked_decision_count": len(blocked),
            "failure_reasons": failure_reasons,
        },
        "operations": operations,
        "blocked_decisions": blocked,
        "compiler": {
            "stage": "investigation_perspective_proposal",
            "previous_stage": "independent_check",
            "next_stage": "graph_commit_apply",
            "graph_writes_require_explicit_apply": True,
            "absence_of_external_support_is_refutation": False,
        },
        "generated_at": generated_at,
    }


__all__ = ["build_perspective_graph_commit_envelope"]
