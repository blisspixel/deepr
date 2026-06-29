"""Verifier-supplied candidate edge normalization for source-pack compiler artifacts."""

from __future__ import annotations

from typing import Any

from deepr.experts import edge_temporal as _edge_temporal
from deepr.experts import source_pack_values as _values


def _edge_decision_values(
    raw_edge: dict[str, Any],
    *,
    current_candidate_id: str,
    edge_types: set[str],
) -> dict[str, Any]:
    source_candidate_id = str(raw_edge.get("source_candidate_id", current_candidate_id) or "").strip()
    target_candidate_id = str(raw_edge.get("target_candidate_id", raw_edge.get("dst_candidate_id", "")) or "").strip()
    return {
        "source_candidate_id": source_candidate_id,
        "target_candidate_id": target_candidate_id,
        "edge_type": _values.enum_value(raw_edge.get("edge_type"), edge_types, default=""),
        "confidence": _values.float_0_1(raw_edge.get("confidence")),
        "rationale": _values.string_field(raw_edge, "rationale"),
        "temporal": _edge_temporal.normalize_temporal_context(raw_edge),
    }


def _edge_decision_failures(edge: dict[str, Any], candidates_by_id: dict[str, dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    source_candidate_id = str(edge.get("source_candidate_id", "") or "")
    target_candidate_id = str(edge.get("target_candidate_id", "") or "")
    if not source_candidate_id:
        failures.append("missing_source_candidate_id")
    elif source_candidate_id not in candidates_by_id:
        failures.append("unknown_source_candidate_id")
    if not target_candidate_id:
        failures.append("missing_target_candidate_id")
    elif target_candidate_id not in candidates_by_id:
        failures.append("unknown_target_candidate_id")
    if not str(edge.get("edge_type", "") or ""):
        failures.append("invalid_edge_type")
    if source_candidate_id and target_candidate_id and source_candidate_id == target_candidate_id:
        failures.append("self_edge")
    failures.extend(
        _edge_temporal.temporal_failure_reasons(
            edge.get("temporal", {}) or {},
            field_error="invalid_edge_{field}",
            order_error="invalid_edge_temporal_order",
        )
    )
    return failures


def edge_decision_sets(
    item: dict[str, Any],
    *,
    current_candidate_id: str,
    candidates_by_id: dict[str, dict[str, Any]],
    edge_types: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edge_decisions: list[dict[str, Any]] = []
    edge_failures: list[dict[str, Any]] = []
    raw_edges = item.get("edge_decisions", [])
    if "edge_decisions" in item and not isinstance(raw_edges, list):
        return [], [{"index": 0, "failure_reasons": ["invalid_edge_decisions_field"]}]
    if not isinstance(raw_edges, list):
        raw_edges = []
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, dict):
            edge_failures.append({"index": index, "failure_reasons": ["invalid_edge_decision"]})
            continue
        edge = _edge_decision_values(raw_edge, current_candidate_id=current_candidate_id, edge_types=edge_types)
        failures = _edge_decision_failures(edge, candidates_by_id)
        if failures:
            edge_failures.append({"index": index, "failure_reasons": sorted(set(failures))})
            continue
        edge_decision = {
            "source_candidate_id": edge["source_candidate_id"],
            "target_candidate_id": edge["target_candidate_id"],
            "edge_type": edge["edge_type"],
        }
        if "confidence" in raw_edge:
            edge_decision["confidence"] = edge["confidence"]
        if edge["rationale"]:
            edge_decision["rationale"] = edge["rationale"]
        if edge["temporal"]:
            edge_decision["temporal"] = edge["temporal"]
        edge_decisions.append(edge_decision)
    return edge_decisions, edge_failures


__all__ = ["edge_decision_sets"]
