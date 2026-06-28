"""Graph commit envelope primitives for verified compiler decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from deepr.experts.beliefs import EDGE_TYPES
from deepr.experts.source_pack_compiler import CLAIM_VERIFICATION_SCHEMA_VERSION

GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V1 = "deepr-graph-commit-envelope-v1"
GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION = "deepr-graph-commit-envelope-v2"
GRAPH_COMMIT_ENVELOPE_KIND = "deepr.expert.graph_commit_envelope"

_BELIEF_STATE_TYPES = {"factual_claim", "fact", "external_fact", "current_fact"}
_GAP_STATE_TYPES = {"gap", "knowledge_gap", "research_gap"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _json_hash_material(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_json_hash_material(value).encode("utf-8")).hexdigest()


def _candidate_by_id(claim_extraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for raw_candidate in claim_extraction.get("candidates", []) or []:
        if not isinstance(raw_candidate, dict):
            continue
        candidate_id = str(raw_candidate.get("candidate_id", "") or "")
        if candidate_id:
            candidates[candidate_id] = raw_candidate
    return candidates


def _valid_evidence_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for raw_ref in candidate.get("evidence_refs", []) or []:
        if not isinstance(raw_ref, dict) or raw_ref.get("valid_ref") is not True:
            continue
        note_id = str(raw_ref.get("note_id", "") or "")
        window_id = str(raw_ref.get("window_id", "") or "")
        if note_id and window_id:
            refs.append(
                {
                    "note_id": note_id,
                    "window_id": window_id,
                    "source_pointer": str(raw_ref.get("source_pointer", "") or ""),
                    "source_index": int(raw_ref.get("source_index", 0) or 0),
                }
            )
    return refs


def _evidence_tokens(refs: list[dict[str, Any]]) -> list[str]:
    return [f"source_note:{ref['note_id']}:{ref['window_id']}" for ref in refs]


def _confidence(candidate: dict[str, Any], decision: dict[str, Any]) -> float:
    value = (decision.get("model_judgment", {}) or {}).get("confidence")
    if value in (None, ""):
        value = candidate.get("confidence")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(1.0, parsed))


def _float_nonnegative(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, parsed)


def _int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _belief_id(candidate: dict[str, Any]) -> str:
    statement = str(candidate.get("statement", "") or "").strip()
    candidate_id = str(candidate.get("candidate_id", "") or "")
    return f"bg_{_sha256_json({'candidate_id': candidate_id, 'statement': statement})[:16]}"


def _gap_id(topic: str) -> str:
    return hashlib.sha256(topic.encode()).hexdigest()[:12]


def _decision_state_type(candidate: dict[str, Any], decision: dict[str, Any]) -> str:
    policy = decision.get("state_policy", candidate.get("state_policy", {})) or {}
    return str(policy.get("state_type", candidate.get("claim_kind", "")) or "")


def _gap_verdict_ready(verdicts: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if verdicts.get("support") not in {"supported", "not_applicable"}:
        failures.append("support_not_verified")
    if verdicts.get("contradiction") != "none":
        failures.append("contradiction_not_clear")
    if verdicts.get("deduplication") != "new":
        failures.append("deduplication_not_new")
    if verdicts.get("temporal_scope") not in {"valid", "not_applicable"}:
        failures.append("temporal_scope_not_valid")
    return failures


def _belief_verdict_ready(verdicts: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if verdicts.get("support") != "supported":
        failures.append("support_not_verified")
    if verdicts.get("contradiction") != "none":
        failures.append("contradiction_not_clear")
    if verdicts.get("deduplication") != "new":
        failures.append("deduplication_not_new")
    if verdicts.get("temporal_scope") != "valid":
        failures.append("temporal_scope_not_valid")
    return failures


def _commit_failures(candidate: dict[str, Any] | None, decision: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    readiness = decision.get("readiness", {}) or {}
    failures.extend(str(reason) for reason in readiness.get("failure_reasons", []) or [])
    if readiness.get("ready_for_commit_envelope") is not True:
        failures.append("decision_not_ready_for_commit_envelope")
    if candidate is None:
        failures.append("unknown_candidate_id")
        return sorted(set(failures))

    state_type = _decision_state_type(candidate, decision)
    is_gap = state_type in _GAP_STATE_TYPES
    if state_type not in _BELIEF_STATE_TYPES and not is_gap:
        failures.append("non_factual_state_requires_perspective_store")

    verdicts = decision.get("verdicts", {}) or {}
    if is_gap:
        failures.extend(_gap_verdict_ready(verdicts))
    else:
        failures.extend(_belief_verdict_ready(verdicts))
    if not str(candidate.get("statement", "") or "").strip():
        failures.append("missing_statement")
    if not _valid_evidence_refs(candidate):
        failures.append("missing_valid_evidence_refs")
    return sorted(set(failures))


def _edge_decision_items(decision: dict[str, Any]) -> list[dict[str, Any]]:
    raw_edges = decision.get("edge_decisions", [])
    if not isinstance(raw_edges, list):
        return []
    return [edge for edge in raw_edges if isinstance(edge, dict)]


def _edge_operation(
    edge: dict[str, Any],
    *,
    belief_id_by_candidate_id: dict[str, str],
    claim_verification_artifact: str,
) -> dict[str, Any] | None:
    source_candidate_id = str(edge.get("source_candidate_id", "") or "")
    target_candidate_id = str(edge.get("target_candidate_id", "") or "")
    source_belief_id = belief_id_by_candidate_id.get(source_candidate_id, "")
    target_belief_id = belief_id_by_candidate_id.get(target_candidate_id, "")
    edge_type = str(edge.get("edge_type", "") or "")
    if not source_belief_id or not target_belief_id or edge_type not in EDGE_TYPES:
        return None
    if source_belief_id == target_belief_id:
        return None
    result = {
        "src_id": source_belief_id,
        "dst_id": target_belief_id,
        "edge_type": edge_type,
        "source_candidate_id": source_candidate_id,
        "target_candidate_id": target_candidate_id,
        "provenance": (
            f"claim_verification:{claim_verification_artifact}:{source_candidate_id}:{target_candidate_id}:{edge_type}"
        ),
    }
    if edge.get("confidence") not in (None, ""):
        try:
            result["confidence"] = max(0.0, min(1.0, float(edge["confidence"])))
        except (TypeError, ValueError):
            pass
    rationale = str(edge.get("rationale", "") or "").strip()
    if rationale:
        result["rationale"] = rationale
    return result


def _edge_operations_by_source_candidate(
    decisions: list[dict[str, Any]],
    *,
    belief_id_by_candidate_id: dict[str, str],
    claim_verification_artifact: str,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    edges_by_source: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str]] = set()
    skipped_count = 0
    for decision in decisions:
        for edge in _edge_decision_items(decision):
            operation = _edge_operation(
                edge,
                belief_id_by_candidate_id=belief_id_by_candidate_id,
                claim_verification_artifact=claim_verification_artifact,
            )
            if operation is None:
                skipped_count += 1
                continue
            key = (operation["src_id"], operation["dst_id"], operation["edge_type"])
            if operation["edge_type"] == "contradicts":
                left, right = sorted((operation["src_id"], operation["dst_id"]))
                key = (left, right, operation["edge_type"])
            if key in seen:
                continue
            seen.add(key)
            edges_by_source.setdefault(operation["source_candidate_id"], []).append(operation)
    return edges_by_source, skipped_count


def _write_operation(
    candidate: dict[str, Any],
    decision: dict[str, Any],
    *,
    edges: list[dict[str, Any]],
    domain: str,
    trust_class: str,
    grounding_assurance: str,
    claim_extraction_artifact: str,
    claim_verification_artifact: str,
    source_note_artifact: str,
) -> dict[str, Any]:
    evidence_refs = _valid_evidence_refs(candidate)
    statement = str(candidate.get("statement", "") or "").strip()
    candidate_id = str(candidate.get("candidate_id", "") or "")
    belief_id = _belief_id(candidate)
    idempotency_material = {
        "schema_version": GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "belief_id": belief_id,
        "verdicts": decision.get("verdicts", {}),
        "evidence_refs": evidence_refs,
        "edges": edges,
    }
    return {
        "operation_id": f"op_{_sha256_json(idempotency_material)[:16]}",
        "operation": "add_belief",
        "candidate_id": candidate_id,
        "decision_status": str((decision.get("commit_gate", {}) or {}).get("status", "")),
        "belief": {
            "id": belief_id,
            "claim": statement,
            "domain": domain,
            "confidence": _confidence(candidate, decision),
            "evidence_refs": _evidence_tokens(evidence_refs),
            "source_type": "compiled_source_claim",
            "trust_class": trust_class,
            "grounding_assurance": grounding_assurance,
        },
        "edges": edges,
        "idempotency_key": _sha256_json(idempotency_material),
        "provenance": {
            "claim_extraction_artifact": claim_extraction_artifact,
            "claim_verification_artifact": claim_verification_artifact,
            "source_note_artifact": source_note_artifact,
            "source_refs": evidence_refs,
        },
    }


def _gap_payload(candidate: dict[str, Any], generated_at: str) -> dict[str, Any]:
    statement = str(candidate.get("statement", "") or "").strip()
    raw_gap = candidate.get("gap")
    gap = raw_gap if isinstance(raw_gap, dict) else {}
    topic = str(gap.get("topic", statement) or statement).strip()
    questions = _string_items(gap.get("questions"))
    estimated_cost = _float_nonnegative(gap.get("estimated_cost"))
    expected_value = _confidence(candidate, {})
    if "expected_value" in gap:
        expected_value = max(0.0, min(1.0, _float_nonnegative(gap.get("expected_value"))))
    return {
        "id": _gap_id(topic),
        "topic": topic,
        "questions": questions,
        "priority": _int_range(gap.get("priority"), default=3, minimum=1, maximum=5),
        "estimated_cost": estimated_cost,
        "expected_value": expected_value,
        "ev_cost_ratio": expected_value / max(estimated_cost, 0.001) if expected_value else 0.0,
        "times_asked": max(1, _int_range(gap.get("times_asked"), default=1, minimum=1, maximum=1_000_000)),
        "identified_at": generated_at,
        "filled": False,
        "filled_at": None,
        "filled_by_job": None,
    }


def _gap_operation(
    candidate: dict[str, Any],
    decision: dict[str, Any],
    *,
    generated_at: str,
    claim_extraction_artifact: str,
    claim_verification_artifact: str,
    source_note_artifact: str,
) -> dict[str, Any]:
    evidence_refs = _valid_evidence_refs(candidate)
    candidate_id = str(candidate.get("candidate_id", "") or "")
    gap = _gap_payload(candidate, generated_at)
    idempotency_material = {
        "schema_version": GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "operation": "promote_gap",
        "candidate_id": candidate_id,
        "gap_id": gap["id"],
        "gap_topic": gap["topic"],
        "verdicts": decision.get("verdicts", {}),
        "evidence_refs": evidence_refs,
    }
    return {
        "operation_id": f"op_{_sha256_json(idempotency_material)[:16]}",
        "operation": "promote_gap",
        "candidate_id": candidate_id,
        "decision_status": str((decision.get("commit_gate", {}) or {}).get("status", "")),
        "gap": gap,
        "idempotency_key": _sha256_json(idempotency_material),
        "provenance": {
            "claim_extraction_artifact": claim_extraction_artifact,
            "claim_verification_artifact": claim_verification_artifact,
            "source_note_artifact": source_note_artifact,
            "source_refs": evidence_refs,
        },
    }


def _blocked_entry(
    candidate_id: str,
    candidate: dict[str, Any] | None,
    decision: dict[str, Any],
    failure_reasons: list[str],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "claim_kind": str((candidate or decision).get("claim_kind", "") or ""),
        "statement_hash": _sha256_json(str((candidate or {}).get("statement", "") or "")),
        "failure_reasons": failure_reasons,
    }


def build_graph_commit_envelope(
    claim_extraction: dict[str, Any],
    claim_verification: dict[str, Any],
    *,
    claim_extraction_artifact: str = "",
    claim_verification_artifact: str = "",
    expert_name: str = "",
    domain: str = "",
    trust_class: str = "tertiary",
    grounding_assurance: str = "unverified",
    generated_at: str = "",
) -> dict[str, Any]:
    """Build the deterministic write boundary after claim verification.

    The envelope makes no model calls and writes no graph state. It only
    converts verified factual decisions into idempotent write operations and
    blocks anything that still needs a richer perspective-state store or a
    clearer semantic verifier decision.
    """
    candidates_by_id = _candidate_by_id(claim_extraction)
    ready_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    ready_decisions: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    resolved_generated_at = generated_at or _utc_now().isoformat()

    for raw_decision in claim_verification.get("decisions", []) or []:
        if not isinstance(raw_decision, dict):
            continue
        candidate_id = str(raw_decision.get("candidate_id", "") or "")
        candidate = candidates_by_id.get(candidate_id)
        failures = _commit_failures(candidate, raw_decision)
        if failures:
            blocked.append(_blocked_entry(candidate_id, candidate, raw_decision, failures))
            continue
        ready_pairs.append((candidate or {}, raw_decision))
        ready_decisions.append(raw_decision)

    belief_id_by_candidate_id = {
        str(candidate.get("candidate_id", "") or ""): _belief_id(candidate)
        for candidate, _decision in ready_pairs
        if str(candidate.get("candidate_id", "") or "")
    }
    edges_by_source_candidate, skipped_edge_count = _edge_operations_by_source_candidate(
        ready_decisions,
        belief_id_by_candidate_id=belief_id_by_candidate_id,
        claim_verification_artifact=claim_verification_artifact,
    )

    for candidate, decision in ready_pairs:
        candidate_id = str(candidate.get("candidate_id", "") or "")
        source_note_artifact = str((claim_extraction.get("input", {}) or {}).get("source_note_artifact", ""))
        if _decision_state_type(candidate, decision) in _GAP_STATE_TYPES:
            operations.append(
                _gap_operation(
                    candidate,
                    decision,
                    generated_at=resolved_generated_at,
                    claim_extraction_artifact=claim_extraction_artifact,
                    claim_verification_artifact=claim_verification_artifact,
                    source_note_artifact=source_note_artifact,
                )
            )
        else:
            operations.append(
                _write_operation(
                    candidate,
                    decision,
                    edges=edges_by_source_candidate.get(candidate_id, []),
                    domain=domain,
                    trust_class=trust_class,
                    grounding_assurance=grounding_assurance,
                    claim_extraction_artifact=claim_extraction_artifact,
                    claim_verification_artifact=claim_verification_artifact,
                    source_note_artifact=source_note_artifact,
                )
            )

    failure_reasons = sorted({reason for entry in blocked for reason in entry["failure_reasons"]})
    if not operations and not blocked:
        status = "empty"
    elif operations and not blocked:
        status = "ready_for_commit"
    else:
        status = "blocked"

    return {
        "schema_version": GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_ENVELOPE_KIND,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "semantic_judgment": False,
            "model_calls": False,
            "cost_usd": 0.0,
            "writes_graph": False,
            "apply_requires_explicit_command": True,
            "idempotent_operations": True,
            "breaking_changes_require_new_schema_version": True,
        },
        "input": {
            "claim_extraction_artifact": claim_extraction_artifact,
            "claim_extraction_schema_version": str(claim_extraction.get("schema_version", "")),
            "claim_verification_artifact": claim_verification_artifact,
            "claim_verification_schema_version": str(claim_verification.get("schema_version", "")),
            "claim_verification_kind": str(claim_verification.get("kind", "")),
            "decision_count": len(claim_verification.get("decisions", []) or []),
        },
        "target": {
            "expert_name": expert_name,
            "domain": domain,
            "trust_class": trust_class,
            "grounding_assurance": grounding_assurance,
        },
        "summary": {
            "status": status,
            "ready_write_count": len(operations),
            "ready_edge_count": sum(len(operation.get("edges", [])) for operation in operations),
            "skipped_edge_count": skipped_edge_count,
            "blocked_decision_count": len(blocked),
            "failure_reasons": failure_reasons,
        },
        "operations": operations,
        "blocked_decisions": blocked,
        "compiler": {
            "stage": "graph_commit_envelope",
            "previous_stage": "claim_verification",
            "previous_schema_version": CLAIM_VERIFICATION_SCHEMA_VERSION,
            "next_stage": "graph_commit_apply",
            "next_stage_requires_model_judgment": False,
            "graph_writes_require_explicit_apply": True,
        },
        "generated_at": resolved_generated_at,
    }


__all__ = [
    "GRAPH_COMMIT_ENVELOPE_KIND",
    "GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION",
    "GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V1",
    "build_graph_commit_envelope",
]
