"""Apply graph commit envelopes to an expert belief store."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from deepr.experts.beliefs import EDGE_TYPES, Belief, BeliefStore
from deepr.experts.graph_commit_envelope import GRAPH_COMMIT_ENVELOPE_KIND, GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION

GRAPH_COMMIT_APPLY_SCHEMA_VERSION = "deepr-graph-commit-apply-v1"
GRAPH_COMMIT_APPLY_KIND = "deepr.expert.graph_commit_apply"

_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _generated_at(value: str = "") -> str:
    return value or _utc_now().isoformat()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evidence_refs(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item).strip()]


def _same_belief(existing: Belief, payload: dict[str, Any]) -> bool:
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        return False
    return (
        existing.claim == str(payload.get("claim", ""))
        and existing.confidence == confidence
        and existing.domain == str(payload.get("domain", ""))
        and existing.evidence_refs == _evidence_refs(payload.get("evidence_refs"))
        and existing.source_type == str(payload.get("source_type", "compiled_source_claim"))
        and existing.trust_class == str(payload.get("trust_class", "tertiary"))
        and existing.grounding_assurance == str(payload.get("grounding_assurance", "unverified"))
    )


def _operation_shape_failures(operation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if operation.get("operation") != "add_belief":
        failures.append("unsupported_operation")

    idempotency_key = str(operation.get("idempotency_key", ""))
    if not _HEX64_RE.match(idempotency_key):
        failures.append("invalid_idempotency_key")
    return failures


def _belief_failure_reasons(belief: dict[str, Any], store: BeliefStore) -> list[str]:
    failures: list[str] = []
    belief_id = str(belief.get("id", ""))
    if not belief_id:
        failures.append("missing_belief_id")
    if not str(belief.get("claim", "")).strip():
        failures.append("missing_claim")
    try:
        confidence = float(belief.get("confidence"))
    except (TypeError, ValueError):
        failures.append("invalid_confidence")
    else:
        if confidence < 0.0 or confidence > 1.0:
            failures.append("invalid_confidence")
    if not _evidence_refs(belief.get("evidence_refs")):
        failures.append("missing_evidence_refs")

    existing = store.beliefs.get(belief_id)
    if existing is not None and not _same_belief(existing, belief):
        failures.append("idempotency_conflict")
    return failures


def _edge_failure_reasons(operation: dict[str, Any], store: BeliefStore, future_belief_ids: set[str]) -> list[str]:
    failures: list[str] = []
    known_ids = set(store.beliefs) | future_belief_ids
    for raw_edge in _as_list(operation.get("edges")):
        edge = _as_dict(raw_edge)
        src_id = str(edge.get("src_id", edge.get("source_belief_id", "")))
        dst_id = str(edge.get("dst_id", edge.get("target_belief_id", "")))
        if src_id not in known_ids:
            failures.append("edge_source_missing")
        if dst_id not in known_ids:
            failures.append("edge_target_missing")
        if str(edge.get("edge_type", "")) not in EDGE_TYPES:
            failures.append("edge_type_invalid")
        if src_id and dst_id and src_id == dst_id:
            failures.append("edge_self_reference")
    return failures


def _operation_failure_reasons(operation: dict[str, Any], store: BeliefStore, future_belief_ids: set[str]) -> list[str]:
    belief = _as_dict(operation.get("belief"))
    failures = [
        *_operation_shape_failures(operation),
        *_belief_failure_reasons(belief, store),
        *_edge_failure_reasons(operation, store, future_belief_ids),
    ]
    return sorted(set(failures))


def _belief_from_operation(operation: dict[str, Any]) -> Belief:
    payload = _as_dict(operation["belief"])
    return Belief(
        id=str(payload["id"]),
        claim=str(payload["claim"]).strip(),
        confidence=float(payload["confidence"]),
        evidence_refs=_evidence_refs(payload.get("evidence_refs")),
        domain=str(payload.get("domain", "")),
        source_type=str(payload.get("source_type", "compiled_source_claim")),
        trust_class=str(payload.get("trust_class", "tertiary")),
        grounding_assurance=str(payload.get("grounding_assurance", "unverified")),
    )


def _edge_values(raw_edge: dict[str, Any], operation: dict[str, Any]) -> tuple[str, str, str, str]:
    src_id = str(raw_edge.get("src_id", raw_edge.get("source_belief_id", "")))
    dst_id = str(raw_edge.get("dst_id", raw_edge.get("target_belief_id", "")))
    edge_type = str(raw_edge.get("edge_type", ""))
    provenance = str(raw_edge.get("provenance", f"graph_commit_apply:{operation.get('idempotency_key', '')}"))
    return src_id, dst_id, edge_type, provenance


def _edge_key(src_id: str, dst_id: str, edge_type: str) -> tuple[str, str, str]:
    if edge_type == "contradicts":
        lo, hi = sorted((src_id, dst_id))
        return lo, hi, edge_type
    return src_id, dst_id, edge_type


def _edge_already_applied(store: BeliefStore, raw_edge: dict[str, Any], operation: dict[str, Any]) -> bool:
    src_id, dst_id, edge_type, provenance = _edge_values(raw_edge, operation)
    edge = store.edges.get(_edge_key(src_id, dst_id, edge_type))
    if edge is None:
        return False
    return not provenance or provenance in edge.provenance


def _operation_fully_applied(operation: dict[str, Any], store: BeliefStore) -> bool:
    belief = _as_dict(operation.get("belief"))
    existing = store.beliefs.get(str(belief.get("id", "")))
    if existing is None or not _same_belief(existing, belief):
        return False
    return all(
        _edge_already_applied(store, _as_dict(raw_edge), operation) for raw_edge in _as_list(operation.get("edges"))
    )


def _operation_result(
    operation: dict[str, Any],
    *,
    status: str,
    failure_reasons: list[str] | None = None,
    change_timestamp: str = "",
    edge_count: int = 0,
) -> dict[str, Any]:
    belief = _as_dict(operation.get("belief"))
    return {
        "operation_id": str(operation.get("operation_id", "")),
        "operation": str(operation.get("operation", "")),
        "candidate_id": str(operation.get("candidate_id", "")),
        "belief_id": str(belief.get("id", "")),
        "idempotency_key": str(operation.get("idempotency_key", "")),
        "status": status,
        "failure_reasons": failure_reasons or [],
        "change_timestamp": change_timestamp,
        "edge_count": edge_count,
    }


def _edge_count(operation: dict[str, Any]) -> int:
    return len(_as_list(operation.get("edges")))


def _blocked_result(
    envelope: dict[str, Any],
    *,
    target_expert: str,
    dry_run: bool,
    operation_results: list[dict[str, Any]],
    failure_reasons: list[str],
    generated_at: str,
) -> dict[str, Any]:
    return _result(
        envelope,
        target_expert=target_expert,
        dry_run=dry_run,
        operation_results=operation_results,
        status="blocked",
        failure_reasons=failure_reasons,
        generated_at=generated_at,
    )


def _result(
    envelope: dict[str, Any],
    *,
    target_expert: str,
    dry_run: bool,
    operation_results: list[dict[str, Any]],
    status: str,
    failure_reasons: list[str],
    generated_at: str,
) -> dict[str, Any]:
    applied = sum(1 for item in operation_results if item["status"] == "applied")
    already = sum(1 for item in operation_results if item["status"] == "already_applied")
    blocked = sum(1 for item in operation_results if item["status"] == "blocked")
    pending = sum(1 for item in operation_results if item["status"] == "would_apply")
    return {
        "schema_version": GRAPH_COMMIT_APPLY_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_APPLY_KIND,
        "contract": {
            "read_only": dry_run,
            "semantic_judgment": False,
            "model_calls": False,
            "cost_usd": 0.0,
            "writes_graph": not dry_run and applied > 0,
            "idempotent_operations": True,
            "requires_explicit_command": True,
            "breaking_changes_require_new_schema_version": True,
        },
        "input": {
            "envelope_schema_version": str(envelope.get("schema_version", "")),
            "envelope_kind": str(envelope.get("kind", "")),
            "envelope_status": str((_as_dict(envelope.get("summary"))).get("status", "")),
            "operation_count": len(_as_list(envelope.get("operations"))),
        },
        "target": {
            "expert_name": target_expert,
        },
        "summary": {
            "status": status,
            "dry_run": dry_run,
            "planned_write_count": pending,
            "applied_write_count": applied,
            "already_applied_count": already,
            "blocked_operation_count": blocked,
            "failure_reasons": sorted(set(failure_reasons)),
        },
        "operation_results": operation_results,
        "generated_at": generated_at,
    }


def _envelope_failure_reasons(envelope: dict[str, Any], store: BeliefStore) -> list[str]:
    failures: list[str] = []
    if envelope.get("schema_version") != GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION:
        failures.append("unsupported_envelope_schema_version")
    if envelope.get("kind") != GRAPH_COMMIT_ENVELOPE_KIND:
        failures.append("unsupported_envelope_kind")

    target_name = str(_as_dict(envelope.get("target")).get("expert_name", "")).strip()
    if target_name and target_name != store.expert_name:
        failures.append("target_expert_mismatch")

    if _as_dict(envelope.get("summary")).get("status") != "ready_for_commit":
        failures.append("envelope_not_ready_for_commit")
    return failures


def _envelope_operations(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _as_list(envelope.get("operations")) if isinstance(item, dict)]


def _operation_results(operations: list[dict[str, Any]], store: BeliefStore) -> list[dict[str, Any]]:
    future_belief_ids = {str(_as_dict(op.get("belief")).get("id", "")) for op in operations}
    results: list[dict[str, Any]] = []
    for operation in operations:
        failures = _operation_failure_reasons(operation, store, future_belief_ids)
        if failures:
            results.append(_operation_result(operation, status="blocked", failure_reasons=failures))
            continue
        status = "already_applied" if _operation_fully_applied(operation, store) else "would_apply"
        results.append(_operation_result(operation, status=status))
    return results


def _combined_failures(envelope_failures: list[str], operation_results: list[dict[str, Any]]) -> list[str]:
    return sorted(
        set(envelope_failures) | {reason for item in operation_results for reason in item.get("failure_reasons", [])}
    )


def _pending_operations(
    operations: list[dict[str, Any]], operation_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [op for op, result in zip(operations, operation_results, strict=True) if result["status"] == "would_apply"]


def _add_missing_beliefs(operations: list[dict[str, Any]], store: BeliefStore) -> dict[str, str]:
    applied_changes: dict[str, str] = {}
    for operation in operations:
        if str(_as_dict(operation.get("belief")).get("id", "")) in store.beliefs:
            continue
        belief = _belief_from_operation(operation)
        _stored, change = store.add_belief(
            belief,
            check_conflicts=False,
            dedup=False,
            change_reason=f"graph_commit_apply:{operation['idempotency_key']}",
            edge_provenance=f"graph_commit_apply:{operation['idempotency_key']}",
        )
        applied_changes[str(operation["idempotency_key"])] = change.timestamp.isoformat() if change is not None else ""
    return applied_changes


def _add_missing_edges(operations: list[dict[str, Any]], store: BeliefStore) -> dict[str, int]:
    edge_counts: dict[str, int] = {}
    for operation in operations:
        edge_count = 0
        for raw_edge in _as_list(operation.get("edges")):
            edge_payload = _as_dict(raw_edge)
            if _edge_already_applied(store, edge_payload, operation):
                continue
            src_id, dst_id, edge_type, provenance = _edge_values(edge_payload, operation)
            store.add_edge(src_id, dst_id, edge_type, provenance=provenance, save=False)
            edge_count += 1
        if edge_count:
            edge_counts[str(operation["idempotency_key"])] = edge_count
    if edge_counts:
        store._save()
    return edge_counts


def _applied_operation_results(
    operations: list[dict[str, Any]],
    operation_results: list[dict[str, Any]],
    applied_changes: dict[str, str],
    edge_counts: dict[str, int],
) -> list[dict[str, Any]]:
    final_results: list[dict[str, Any]] = []
    for operation, result in zip(operations, operation_results, strict=True):
        idempotency_key = str(operation.get("idempotency_key", ""))
        if result["status"] == "would_apply":
            final_results.append(
                _operation_result(
                    operation,
                    status="applied",
                    change_timestamp=applied_changes.get(idempotency_key, ""),
                    edge_count=edge_counts.get(idempotency_key, _edge_count(operation)),
                )
            )
        else:
            final_results.append(_operation_result(operation, status="already_applied"))
    return final_results


def apply_graph_commit_envelope(
    envelope: dict[str, Any],
    store: BeliefStore,
    *,
    dry_run: bool = True,
    generated_at: str = "",
) -> dict[str, Any]:
    """Apply a verified graph commit envelope to a belief store.

    The semantic verdicts have already happened upstream. This function only
    validates the write contract, checks idempotency, and performs the explicit
    graph mutation requested by the caller.
    """
    resolved_generated_at = _generated_at(generated_at)
    envelope_failures = _envelope_failure_reasons(envelope, store)
    operations = _envelope_operations(envelope)
    if not operations:
        envelope_failures.append("empty_operations")
    operation_results = _operation_results(operations, store)
    all_failures = _combined_failures(envelope_failures, operation_results)
    if all_failures:
        return _blocked_result(
            envelope,
            target_expert=store.expert_name,
            dry_run=dry_run,
            operation_results=operation_results,
            failure_reasons=all_failures,
            generated_at=resolved_generated_at,
        )

    if dry_run:
        status = "empty" if not operation_results else "dry_run"
        return _result(
            envelope,
            target_expert=store.expert_name,
            dry_run=True,
            operation_results=operation_results,
            status=status,
            failure_reasons=[],
            generated_at=resolved_generated_at,
        )

    pending = _pending_operations(operations, operation_results)
    applied_changes = _add_missing_beliefs(pending, store)
    edge_counts = _add_missing_edges(pending, store)
    final_results = _applied_operation_results(operations, operation_results, applied_changes, edge_counts)
    status = "applied" if any(result["status"] == "applied" for result in final_results) else "already_applied"
    return _result(
        envelope,
        target_expert=store.expert_name,
        dry_run=False,
        operation_results=final_results,
        status=status,
        failure_reasons=[],
        generated_at=resolved_generated_at,
    )


__all__ = [
    "GRAPH_COMMIT_APPLY_KIND",
    "GRAPH_COMMIT_APPLY_SCHEMA_VERSION",
    "apply_graph_commit_envelope",
]
