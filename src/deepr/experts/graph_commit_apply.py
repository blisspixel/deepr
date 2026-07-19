"""Apply graph commit envelopes to an expert belief store."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

from deepr.core.contracts import (
    ExpertConcept,
    ExpertHypothesis,
    ExpertOriginalIdea,
    ExpertStance,
    ExplorationAgenda,
    Gap,
)
from deepr.experts import edge_temporal as _edge_temporal
from deepr.experts.beliefs import EDGE_TYPES, Belief, BeliefStore
from deepr.experts.graph_commit_envelope import (
    GRAPH_COMMIT_ENVELOPE_KIND,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V1,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V2,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V3,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V4,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V5,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V6,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V7,
)
from deepr.experts.metacognition import MetaCognitionTracker

GRAPH_COMMIT_APPLY_SCHEMA_VERSION = "deepr-graph-commit-apply-v1"
GRAPH_COMMIT_APPLY_KIND = "deepr.expert.graph_commit_apply"

_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_ADD_BELIEF = "add_belief"
_PROMOTE_GAP = "promote_gap"
_PROMOTE_EXPLORATION_AGENDA = "promote_exploration_agenda"
_PROMOTE_HYPOTHESIS = "promote_hypothesis"
_PROMOTE_CONCEPT = "promote_concept"
_PROMOTE_STANCE = "promote_stance"
_PROMOTE_ORIGINAL_IDEA = "promote_original_idea"
_SUPPORTED_OPERATIONS = {
    _ADD_BELIEF,
    _PROMOTE_GAP,
    _PROMOTE_EXPLORATION_AGENDA,
    _PROMOTE_HYPOTHESIS,
    _PROMOTE_CONCEPT,
    _PROMOTE_STANCE,
    _PROMOTE_ORIGINAL_IDEA,
}
_SUPPORTED_ENVELOPE_SCHEMA_VERSIONS = {
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V1,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V2,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V3,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V4,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V5,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V6,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION_V7,
    GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
}
_TRACKER_APPLIED_SPECS = {
    _PROMOTE_GAP: ("gap", "knowledge_gaps", "topic"),
    _PROMOTE_EXPLORATION_AGENDA: ("agenda", "exploration_agendas", "title"),
    _PROMOTE_HYPOTHESIS: ("hypothesis", "hypotheses", "title"),
    _PROMOTE_CONCEPT: ("concept", "concepts", "name"),
    _PROMOTE_STANCE: ("stance", "stances", "title"),
    _PROMOTE_ORIGINAL_IDEA: ("original_idea", "original_ideas", "title"),
}
_PROMOTION_SPECS = {
    _PROMOTE_GAP: ("gap", Gap.from_dict, "promote_gap_candidate"),
    _PROMOTE_EXPLORATION_AGENDA: (
        "agenda",
        ExplorationAgenda.from_dict,
        "promote_exploration_agenda_candidate",
    ),
    _PROMOTE_HYPOTHESIS: ("hypothesis", ExpertHypothesis.from_dict, "promote_hypothesis_candidate"),
    _PROMOTE_CONCEPT: ("concept", ExpertConcept.from_dict, "promote_concept_candidate"),
    _PROMOTE_STANCE: ("stance", ExpertStance.from_dict, "promote_stance_candidate"),
    _PROMOTE_ORIGINAL_IDEA: (
        "original_idea",
        ExpertOriginalIdea.from_dict,
        "promote_original_idea_candidate",
    ),
}


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


def _operation_name(operation: dict[str, Any]) -> str:
    return str(operation.get("operation", "") or "")


def _is_add_belief(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _ADD_BELIEF


def _is_promote_gap(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _PROMOTE_GAP


def _is_promote_exploration_agenda(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _PROMOTE_EXPLORATION_AGENDA


def _is_promote_hypothesis(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _PROMOTE_HYPOTHESIS


def _is_promote_concept(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _PROMOTE_CONCEPT


def _is_promote_stance(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _PROMOTE_STANCE


def _is_promote_original_idea(operation: dict[str, Any]) -> bool:
    return _operation_name(operation) == _PROMOTE_ORIGINAL_IDEA


def _operation_shape_failures(operation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if _operation_name(operation) not in _SUPPORTED_OPERATIONS:
        failures.append("unsupported_operation")

    idempotency_key = str(operation.get("idempotency_key", ""))
    if not _HEX64_RE.match(idempotency_key):
        failures.append("invalid_idempotency_key")
    return failures


def _gap_identity_failures(gap: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = ["gap_tracker_missing"] if gap_tracker is None else []
    if not str(gap.get("id", "")).strip():
        failures.append("missing_gap_id")
    if not str(gap.get("topic", "")).strip():
        failures.append("missing_gap_topic")
    return failures


def _gap_priority_failure(gap: dict[str, Any]) -> str:
    try:
        priority = int(gap.get("priority", 3))
    except (TypeError, ValueError):
        return "invalid_gap_priority"
    return "invalid_gap_priority" if priority < 1 or priority > 5 else ""


def _nonnegative_number_failure(gap: dict[str, Any], field: str) -> str:
    try:
        value = float(gap.get(field, 0.0))
    except (TypeError, ValueError):
        return f"invalid_gap_{field}"
    return f"invalid_gap_{field}" if not math.isfinite(value) or value < 0.0 else ""


def _gap_expected_value_failure(gap: dict[str, Any]) -> str:
    try:
        expected_value = float(gap.get("expected_value", 0.0))
    except (TypeError, ValueError):
        return "invalid_gap_expected_value"
    return (
        "invalid_gap_expected_value"
        if not math.isfinite(expected_value) or expected_value < 0.0 or expected_value > 1.0
        else ""
    )


def _gap_times_asked_failure(gap: dict[str, Any]) -> str:
    try:
        times_asked = int(gap.get("times_asked", 1))
    except (TypeError, ValueError):
        return "invalid_gap_times_asked"
    return "invalid_gap_times_asked" if times_asked < 1 else ""


def _gap_identified_at_failure(gap: dict[str, Any]) -> str:
    if not gap.get("identified_at"):
        return ""
    try:
        datetime.fromisoformat(str(gap["identified_at"]))
    except ValueError:
        return "invalid_gap_identified_at"
    return ""


def _iso_datetime_failure(payload: dict[str, Any], field: str, reason: str) -> str:
    if not payload.get(field):
        return ""
    try:
        datetime.fromisoformat(str(payload[field]))
    except ValueError:
        return reason
    return ""


def _edge_temporal_context(raw_edge: dict[str, Any]) -> dict[str, str]:
    return _edge_temporal.normalize_temporal_context(raw_edge.get("temporal", {}))


def _edge_temporal_failure_reasons(raw_edge: dict[str, Any]) -> list[str]:
    return _edge_temporal.temporal_failure_reasons(
        raw_edge.get("temporal", {}),
        field_error="edge_{field}_invalid",
        order_error="edge_temporal_order_invalid",
    )


def _gap_failure_reasons(gap: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = [
        *_gap_identity_failures(gap, gap_tracker),
        _gap_priority_failure(gap),
        _nonnegative_number_failure(gap, "estimated_cost"),
        _nonnegative_number_failure(gap, "ev_cost_ratio"),
        _gap_expected_value_failure(gap),
        _gap_times_asked_failure(gap),
        _gap_identified_at_failure(gap),
    ]
    failures = [failure for failure in failures if failure]
    return failures


def _agenda_identity_failures(agenda: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = ["agenda_tracker_missing"] if gap_tracker is None else []
    if not str(agenda.get("id", "")).strip():
        failures.append("missing_agenda_id")
    if not str(agenda.get("title", "")).strip():
        failures.append("missing_agenda_title")
    return failures


def _required_text_failures(payload: dict[str, Any], prefix: str) -> list[str]:
    failures: list[str] = []
    for field in ("origin", "rationale", "uncertainty"):
        if not str(payload.get(field, "")).strip():
            failures.append(f"missing_{prefix}_{field}")
    if not _evidence_refs(payload.get("expected_observations")):
        failures.append(f"missing_{prefix}_expected_observations")
    if not _evidence_refs(payload.get("disconfirming_signals")):
        failures.append(f"missing_{prefix}_disconfirming_signals")
    return failures


def _agenda_failure_reasons(agenda: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = [
        *_agenda_identity_failures(agenda, gap_tracker),
        *_required_text_failures(agenda, "agenda"),
        _gap_priority_failure(agenda).replace("gap", "agenda", 1),
        _nonnegative_number_failure(agenda, "estimated_cost").replace("gap", "agenda", 1),
        _nonnegative_number_failure(agenda, "ev_cost_ratio").replace("gap", "agenda", 1),
        _gap_expected_value_failure(agenda).replace("gap", "agenda", 1),
        _iso_datetime_failure(agenda, "created_at", "invalid_agenda_created_at"),
    ]
    return [failure for failure in failures if failure]


def _hypothesis_identity_failures(hypothesis: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = ["hypothesis_tracker_missing"] if gap_tracker is None else []
    if not str(hypothesis.get("id", "")).strip():
        failures.append("missing_hypothesis_id")
    if not str(hypothesis.get("title", "")).strip():
        failures.append("missing_hypothesis_title")
    if not str(hypothesis.get("statement", "")).strip():
        failures.append("missing_hypothesis_statement")
    return failures


def _hypothesis_confidence_failure(hypothesis: dict[str, Any]) -> str:
    try:
        confidence = float(hypothesis.get("confidence", 0.0))
    except (TypeError, ValueError):
        return "invalid_hypothesis_confidence"
    return (
        "invalid_hypothesis_confidence" if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0 else ""
    )


def _hypothesis_failure_reasons(hypothesis: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = [
        *_hypothesis_identity_failures(hypothesis, gap_tracker),
        *_required_text_failures(hypothesis, "hypothesis"),
        _gap_priority_failure(hypothesis).replace("gap", "hypothesis", 1),
        _hypothesis_confidence_failure(hypothesis),
        _iso_datetime_failure(hypothesis, "created_at", "invalid_hypothesis_created_at"),
    ]
    return [failure for failure in failures if failure]


def _concept_identity_failures(concept: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = ["concept_tracker_missing"] if gap_tracker is None else []
    if not str(concept.get("id", "")).strip():
        failures.append("missing_concept_id")
    if not str(concept.get("name", "")).strip():
        failures.append("missing_concept_name")
    if not str(concept.get("description", "")).strip():
        failures.append("missing_concept_description")
    return failures


def _concept_confidence_failure(concept: dict[str, Any]) -> str:
    try:
        confidence = float(concept.get("confidence", 0.0))
    except (TypeError, ValueError):
        return "invalid_concept_confidence"
    return "invalid_concept_confidence" if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0 else ""


def _concept_failure_reasons(concept: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = [
        *_concept_identity_failures(concept, gap_tracker),
        *_required_text_failures(concept, "concept"),
        _gap_priority_failure(concept).replace("gap", "concept", 1),
        _concept_confidence_failure(concept),
        _iso_datetime_failure(concept, "created_at", "invalid_concept_created_at"),
    ]
    return [failure for failure in failures if failure]


def _stance_identity_failures(stance: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = ["stance_tracker_missing"] if gap_tracker is None else []
    if not str(stance.get("id", "")).strip():
        failures.append("missing_stance_id")
    if not str(stance.get("title", "")).strip():
        failures.append("missing_stance_title")
    if not str(stance.get("position", "")).strip():
        failures.append("missing_stance_position")
    return failures


def _stance_confidence_failure(stance: dict[str, Any]) -> str:
    try:
        confidence = float(stance.get("confidence", 0.0))
    except (TypeError, ValueError):
        return "invalid_stance_confidence"
    return "invalid_stance_confidence" if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0 else ""


def _stance_failure_reasons(stance: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = [
        *_stance_identity_failures(stance, gap_tracker),
        *_required_text_failures(stance, "stance"),
        _gap_priority_failure(stance).replace("gap", "stance", 1),
        _stance_confidence_failure(stance),
        _iso_datetime_failure(stance, "created_at", "invalid_stance_created_at"),
    ]
    return [failure for failure in failures if failure]


def _original_idea_identity_failures(
    original_idea: dict[str, Any],
    gap_tracker: MetaCognitionTracker | None,
) -> list[str]:
    failures = ["original_idea_tracker_missing"] if gap_tracker is None else []
    if not str(original_idea.get("id", "")).strip():
        failures.append("missing_original_idea_id")
    if not str(original_idea.get("title", "")).strip():
        failures.append("missing_original_idea_title")
    if not str(original_idea.get("statement", "")).strip():
        failures.append("missing_original_idea_statement")
    return failures


def _original_idea_confidence_failure(original_idea: dict[str, Any]) -> str:
    try:
        confidence = float(original_idea.get("confidence", 0.0))
    except (TypeError, ValueError):
        return "invalid_original_idea_confidence"
    return (
        "invalid_original_idea_confidence"
        if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0
        else ""
    )


def _original_idea_failure_reasons(
    original_idea: dict[str, Any],
    gap_tracker: MetaCognitionTracker | None,
) -> list[str]:
    failures = [
        *_original_idea_identity_failures(original_idea, gap_tracker),
        *_required_text_failures(original_idea, "original_idea"),
        _gap_priority_failure(original_idea).replace("gap", "original_idea", 1),
        _original_idea_confidence_failure(original_idea),
        _iso_datetime_failure(original_idea, "created_at", "invalid_original_idea_created_at"),
    ]
    return [failure for failure in failures if failure]


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
        if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
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
        failures.extend(_edge_temporal_failure_reasons(edge))
    return failures


def _add_belief_operation_failures(
    operation: dict[str, Any],
    store: BeliefStore,
    future_belief_ids: set[str],
) -> list[str]:
    belief = _as_dict(operation.get("belief"))
    return [
        *_belief_failure_reasons(belief, store),
        *_edge_failure_reasons(operation, store, future_belief_ids),
    ]


def _gap_operation_failures(operation: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = _gap_failure_reasons(_as_dict(operation.get("gap")), gap_tracker)
    if _as_list(operation.get("edges")):
        failures.append("gap_operation_edges_not_supported")
    return failures


def _agenda_operation_failures(operation: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = _agenda_failure_reasons(_as_dict(operation.get("agenda")), gap_tracker)
    if _as_list(operation.get("edges")):
        failures.append("agenda_operation_edges_not_supported")
    return failures


def _hypothesis_operation_failures(operation: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = _hypothesis_failure_reasons(_as_dict(operation.get("hypothesis")), gap_tracker)
    if _as_list(operation.get("edges")):
        failures.append("hypothesis_operation_edges_not_supported")
    return failures


def _concept_operation_failures(operation: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = _concept_failure_reasons(_as_dict(operation.get("concept")), gap_tracker)
    if _as_list(operation.get("edges")):
        failures.append("concept_operation_edges_not_supported")
    return failures


def _stance_operation_failures(operation: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> list[str]:
    failures = _stance_failure_reasons(_as_dict(operation.get("stance")), gap_tracker)
    if _as_list(operation.get("edges")):
        failures.append("stance_operation_edges_not_supported")
    return failures


def _original_idea_operation_failures(
    operation: dict[str, Any],
    gap_tracker: MetaCognitionTracker | None,
) -> list[str]:
    failures = _original_idea_failure_reasons(_as_dict(operation.get("original_idea")), gap_tracker)
    if _as_list(operation.get("edges")):
        failures.append("original_idea_operation_edges_not_supported")
    return failures


def _operation_failure_reasons(
    operation: dict[str, Any],
    store: BeliefStore,
    future_belief_ids: set[str],
    gap_tracker: MetaCognitionTracker | None,
) -> list[str]:
    failures = _operation_shape_failures(operation)
    if "unsupported_operation" in failures:
        return sorted(set(failures))
    operation_failures = {
        _ADD_BELIEF: _add_belief_operation_failures(operation, store, future_belief_ids),
        _PROMOTE_GAP: _gap_operation_failures(operation, gap_tracker),
        _PROMOTE_EXPLORATION_AGENDA: _agenda_operation_failures(operation, gap_tracker),
        _PROMOTE_HYPOTHESIS: _hypothesis_operation_failures(operation, gap_tracker),
        _PROMOTE_CONCEPT: _concept_operation_failures(operation, gap_tracker),
        _PROMOTE_STANCE: _stance_operation_failures(operation, gap_tracker),
        _PROMOTE_ORIGINAL_IDEA: _original_idea_operation_failures(operation, gap_tracker),
    }
    failures.extend(operation_failures.get(_operation_name(operation), []))
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
    temporal_context = _edge_temporal_context(raw_edge)
    if temporal_context and temporal_context not in edge.temporal_contexts:
        return False
    return not provenance or provenance in edge.provenance


def _operation_fully_applied(operation: dict[str, Any], store: BeliefStore) -> bool:
    if not _is_add_belief(operation):
        return False
    belief = _as_dict(operation.get("belief"))
    existing = store.beliefs.get(str(belief.get("id", "")))
    if existing is None or not _same_belief(existing, belief):
        return False
    return all(
        _edge_already_applied(store, _as_dict(raw_edge), operation) for raw_edge in _as_list(operation.get("edges"))
    )


def _tracker_state_fully_applied(operation: dict[str, Any], gap_tracker: MetaCognitionTracker | None) -> bool:
    if gap_tracker is None:
        return False
    spec = _TRACKER_APPLIED_SPECS.get(_operation_name(operation))
    if spec is None:
        return False
    payload_name, tracker_attr, identity_field = spec
    identity = str(_as_dict(operation.get(payload_name)).get(identity_field, "")).strip()
    return bool(identity and identity in getattr(gap_tracker, tracker_attr))


def _state_fully_applied(
    operation: dict[str, Any],
    store: BeliefStore,
    gap_tracker: MetaCognitionTracker | None,
) -> bool:
    if _is_add_belief(operation):
        return _operation_fully_applied(operation, store)
    return _tracker_state_fully_applied(operation, gap_tracker)


def _operation_result(
    operation: dict[str, Any],
    *,
    status: str,
    failure_reasons: list[str] | None = None,
    change_timestamp: str = "",
    edge_count: int = 0,
    gap_created: bool = False,
) -> dict[str, Any]:
    belief = _as_dict(operation.get("belief"))
    gap = _as_dict(operation.get("gap"))
    agenda = _as_dict(operation.get("agenda"))
    hypothesis = _as_dict(operation.get("hypothesis"))
    concept = _as_dict(operation.get("concept"))
    stance = _as_dict(operation.get("stance"))
    original_idea = _as_dict(operation.get("original_idea"))
    result = {
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
    if gap:
        result["gap_id"] = str(gap.get("id", ""))
        result["gap_topic"] = str(gap.get("topic", ""))
        result["gap_created"] = gap_created
    if agenda:
        result["agenda_id"] = str(agenda.get("id", ""))
        result["agenda_title"] = str(agenda.get("title", ""))
        result["agenda_created"] = status == "applied" and _is_promote_exploration_agenda(operation)
    if hypothesis:
        result["hypothesis_id"] = str(hypothesis.get("id", ""))
        result["hypothesis_title"] = str(hypothesis.get("title", ""))
        result["hypothesis_created"] = status == "applied" and _is_promote_hypothesis(operation)
    if concept:
        result["concept_id"] = str(concept.get("id", ""))
        result["concept_name"] = str(concept.get("name", ""))
        result["concept_created"] = status == "applied" and _is_promote_concept(operation)
    if stance:
        result["stance_id"] = str(stance.get("id", ""))
        result["stance_title"] = str(stance.get("title", ""))
        result["stance_created"] = status == "applied" and _is_promote_stance(operation)
    if original_idea:
        result["original_idea_id"] = str(original_idea.get("id", ""))
        result["original_idea_title"] = str(original_idea.get("title", ""))
        result["original_idea_created"] = status == "applied" and _is_promote_original_idea(operation)
    return result


def _edge_count(operation: dict[str, Any]) -> int:
    if not _is_add_belief(operation):
        return 0
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
    graph_applied = any(item["status"] == "applied" and item["operation"] == _ADD_BELIEF for item in operation_results)
    return {
        "schema_version": GRAPH_COMMIT_APPLY_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_APPLY_KIND,
        "contract": {
            "read_only": dry_run,
            "semantic_judgment": False,
            "model_calls": False,
            "cost_usd": 0.0,
            "writes_graph": not dry_run and graph_applied,
            "writes_expert_state": not dry_run and applied > 0,
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
    if envelope.get("schema_version") not in _SUPPORTED_ENVELOPE_SCHEMA_VERSIONS:
        failures.append("unsupported_envelope_schema_version")
    if envelope.get("kind") != GRAPH_COMMIT_ENVELOPE_KIND:
        failures.append("unsupported_envelope_kind")

    target_name = str(_as_dict(envelope.get("target")).get("expert_name", "")).strip()
    if not target_name:
        failures.append("missing_target_expert")
    elif target_name != store.expert_name:
        failures.append("target_expert_mismatch")

    if _as_dict(envelope.get("summary")).get("status") != "ready_for_commit":
        failures.append("envelope_not_ready_for_commit")
    return failures


def _envelope_operations(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _as_list(envelope.get("operations")) if isinstance(item, dict)]


def _operation_results(
    operations: list[dict[str, Any]],
    store: BeliefStore,
    gap_tracker: MetaCognitionTracker | None,
) -> list[dict[str, Any]]:
    future_belief_ids = {str(_as_dict(op.get("belief")).get("id", "")) for op in operations if _is_add_belief(op)}
    results: list[dict[str, Any]] = []
    for operation in operations:
        failures = _operation_failure_reasons(operation, store, future_belief_ids, gap_tracker)
        if failures:
            results.append(_operation_result(operation, status="blocked", failure_reasons=failures))
            continue
        status = "already_applied" if _state_fully_applied(operation, store, gap_tracker) else "would_apply"
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
        if not _is_add_belief(operation):
            continue
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
        if not _is_add_belief(operation):
            continue
        edge_count = 0
        for raw_edge in _as_list(operation.get("edges")):
            edge_payload = _as_dict(raw_edge)
            if _edge_already_applied(store, edge_payload, operation):
                continue
            src_id, dst_id, edge_type, provenance = _edge_values(edge_payload, operation)
            store.add_edge(
                src_id,
                dst_id,
                edge_type,
                provenance=provenance,
                temporal_context=_edge_temporal_context(edge_payload),
                save=False,
            )
            edge_count += 1
        if edge_count:
            edge_counts[str(operation["idempotency_key"])] = edge_count
    if edge_counts:
        store._save()
    return edge_counts


def _gap_evidence_refs(operation: dict[str, Any]) -> list[str]:
    refs = _as_list(_as_dict(operation.get("provenance")).get("source_refs"))
    return [
        f"source_note:{ref['note_id']}:{ref['window_id']}"
        for ref in refs
        if isinstance(ref, dict) and str(ref.get("note_id", "")).strip() and str(ref.get("window_id", "")).strip()
    ]


def _promote_missing_tracker_states(
    operations: list[dict[str, Any]],
    gap_tracker: MetaCognitionTracker | None,
    *,
    generated_at: str,
) -> dict[str, str]:
    if gap_tracker is None:
        return {}
    applied_changes: dict[str, str] = {}
    for operation in operations:
        spec = _PROMOTION_SPECS.get(_operation_name(operation))
        if spec is None:
            continue
        payload_name, from_dict, method_name = spec
        promoted_state = from_dict(_as_dict(operation[payload_name]))
        _promoted, created = getattr(gap_tracker, method_name)(
            promoted_state,
            proposal_id=str(operation.get("idempotency_key", "")),
            evidence_refs=_gap_evidence_refs(operation),
            source="graph_commit_apply",
        )
        if created:
            applied_changes[str(operation["idempotency_key"])] = generated_at
    return applied_changes


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
                    gap_created=_is_promote_gap(operation),
                )
            )
        else:
            final_results.append(_operation_result(operation, status="already_applied"))
    return final_results


def apply_graph_commit_envelope(
    envelope: dict[str, Any],
    store: BeliefStore,
    *,
    gap_tracker: MetaCognitionTracker | None = None,
    dry_run: bool = True,
    generated_at: str = "",
) -> dict[str, Any]:
    """Apply a verified graph commit envelope to expert state.

    The semantic verdicts have already happened upstream. This function only
    validates the write contract, checks idempotency, and performs the explicit
    state mutation requested by the caller.
    """
    resolved_generated_at = _generated_at(generated_at)
    envelope_failures = _envelope_failure_reasons(envelope, store)
    operations = _envelope_operations(envelope)
    if not operations:
        envelope_failures.append("empty_operations")
    operation_results = _operation_results(operations, store, gap_tracker)
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
    applied_changes = {
        **_add_missing_beliefs(pending, store),
        **_promote_missing_tracker_states(pending, gap_tracker, generated_at=resolved_generated_at),
    }
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
