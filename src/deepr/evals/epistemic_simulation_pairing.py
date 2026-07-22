"""Structural fingerprints for matched epistemic-simulation contexts."""

from __future__ import annotations

from deepr.experts.epistemic_simulation_contract import (
    CompiledContextPath,
    EpistemicEdge,
    EpistemicRecord,
    EvidenceUnit,
    canonical_sha256,
)


def paired_path_shape(
    path: CompiledContextPath,
    condition_record_id: str,
    record_by_id: dict[str, EpistemicRecord],
    edge_by_id: dict[str, EpistemicEdge],
    evidence_by_id: dict[str, EvidenceUnit],
) -> tuple[object, ...]:
    """Fingerprint one path while normalizing only its declared intervention."""
    records = tuple(record_by_id[item] for item in path.record_ids)
    edges = tuple(edge_by_id[item] for item in path.edge_ids)
    record_position = {record_id: position for position, record_id in enumerate(path.record_ids)}
    return (
        path.lane_sequence,
        path.scenario_time,
        path.why_this_lens,
        tuple(_paired_record_shape(record, condition_record_id, record_by_id, evidence_by_id) for record in records),
        tuple(
            (
                edge.relation,
                record_position[edge.source_record_id],
                record_position[edge.target_record_id],
                edge.scenario_time,
                tuple(_provenance_shape(item, record_by_id, evidence_by_id) for item in edge.provenance_refs),
            )
            for edge in edges
        ),
        tuple(_provenance_shape(item, record_by_id, evidence_by_id) for item in path.provenance_refs),
    )


def _paired_record_shape(
    record: EpistemicRecord,
    condition_record_id: str,
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
) -> tuple[object, ...]:
    varies_with_condition = record.record_id == condition_record_id or (
        record.record_type == "counterfactual_implication" and condition_record_id in record.assumption_refs
    )
    if not varies_with_condition:
        return ("fixed_record", canonical_sha256(record))
    return (
        "condition_dependent_record",
        record.lane,
        record.record_type,
        record.provenance_class,
        record.verification_status,
        record.candidate_only,
        record.status,
        record.valid_time,
        record.recorded_at,
        record.scenario_time,
        record.review_after,
        record.expires_at,
        tuple(
            (
                evidence_id,
                evidence_by_id[evidence_id].content_sha256,
                evidence_by_id[evidence_id].independence_root_id,
            )
            for evidence_id in record.evidence_refs
        ),
        tuple(_provenance_shape(item, record_by_id, evidence_by_id) for item in record.assumption_refs),
    )


def _provenance_shape(
    provenance_ref: str,
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
) -> tuple[object, ...]:
    record = record_by_id.get(provenance_ref)
    if record is not None:
        if record.branch_condition is not None:
            return (
                "controlled_condition",
                record.lane,
                record.record_type,
                record.verification_status,
                record.branch_condition.variable,
            )
        return ("record", provenance_ref, record.lane, record.record_type, record.verification_status)
    evidence = evidence_by_id[provenance_ref]
    return (
        "evidence",
        evidence.evidence_id,
        evidence.content_sha256,
        evidence.independence_root_id,
        evidence.evidence_class,
        evidence.verification_status,
        evidence.access_policy.visibility,
    )


__all__ = ["paired_path_shape"]
