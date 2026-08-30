"""Read-only experience projection over existing expert records.

An experience is not a new authority store. This module joins the canonical
position ledger, consult traces, and operator-attested outcomes into one view
that shows what the expert expected, what later happened, and which records are
still missing. It never infers whether advice was good and never changes expert
state.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from deepr.experts.outcomes import ExpertOutcome
from deepr.experts.position_ledger import PositionLedger, PositionVersion

EXPERT_EXPERIENCE_VIEW_SCHEMA_VERSION = "deepr-expert-experience-view-v1"
EXPERT_EXPERIENCE_VIEW_KIND = "deepr.expert.experience_view"


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _active_outcomes(outcomes: list[ExpertOutcome]) -> list[ExpertOutcome]:
    superseded = {item.supersedes_outcome_id for item in outcomes if item.supersedes_outcome_id is not None}
    return [item for item in outcomes if item.outcome_id not in superseded]


def trace_ids_for_experience(outcomes: list[ExpertOutcome], *, limit: int = 20) -> set[str]:
    """Return the bounded trace identities needed for the projected cases."""
    bounded_limit = max(1, min(int(limit), 100))
    return {
        item.consult_trace_id
        for item in _active_outcomes(outcomes)[-bounded_limit:]
        if item.consult_trace_id is not None
    }


def _trace_index(traces: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for trace in traces:
        trace_id = str(trace.get("trace_id", "")).strip()
        if not trace_id:
            continue
        if trace_id in indexed:
            duplicates.add(trace_id)
            continue
        indexed[trace_id] = trace
    return indexed, duplicates


def _trace_roster(trace: dict[str, Any]) -> list[str]:
    output = trace.get("output")
    if isinstance(output, dict):
        roster = output.get("experts_consulted")
        if isinstance(roster, list):
            return [str(item) for item in roster if str(item).strip()]

    packet = trace.get("context_packet")
    if not isinstance(packet, dict):
        return []
    always = packet.get("always")
    if not isinstance(always, dict):
        return []
    roster = always.get("experts_consulted")
    if not isinstance(roster, list):
        return []
    return [str(item) for item in roster if str(item).strip()]


def _consult_link(
    outcome: ExpertOutcome,
    *,
    expert_name: str,
    traces_by_id: dict[str, dict[str, Any]],
    duplicate_trace_ids: set[str],
) -> dict[str, Any]:
    trace_id = outcome.consult_trace_id
    if trace_id is None:
        return {"status": "not_linked", "trace_id": None}
    if trace_id in duplicate_trace_ids:
        return {"status": "ambiguous_duplicate", "trace_id": trace_id}

    trace = traces_by_id.get(trace_id)
    if trace is None:
        return {"status": "missing", "trace_id": trace_id}

    roster = _trace_roster(trace)
    if not roster:
        return {"status": "roster_unknown", "trace_id": trace_id}
    normalized_roster = {_normalized_name(item) for item in roster}
    if _normalized_name(expert_name) not in normalized_roster:
        return {"status": "expert_mismatch", "trace_id": trace_id, "experts_consulted": roster}

    input_block = trace.get("input")
    input_record = input_block if isinstance(input_block, dict) else {}
    return {
        "status": "matched",
        "trace_id": trace_id,
        "trace_status": str(trace.get("status", "")),
        "recorded_at": str(trace.get("recorded_at", "")),
        "question": str(input_record.get("question", "")),
        "question_hash": str(input_record.get("question_hash", "")),
        "experts_consulted": roster,
    }


def _outcome_case(
    outcome: ExpertOutcome,
    *,
    expert_name: str,
    traces_by_id: dict[str, dict[str, Any]],
    duplicate_trace_ids: set[str],
) -> dict[str, Any]:
    return {
        "outcome_id": outcome.outcome_id,
        "decision_id": outcome.decision_id,
        "decision_summary": outcome.decision_summary,
        "result": outcome.result,
        "observation": outcome.observation,
        "observed_at": outcome.observed_at,
        "recorded_at": outcome.recorded_at,
        "attested_by": outcome.attested_by,
        "belief_ids": list(outcome.belief_ids),
        "source_refs": list(outcome.source_refs),
        "evidence_refs": list(outcome.evidence_refs),
        "consult": _consult_link(
            outcome,
            expert_name=expert_name,
            traces_by_id=traces_by_id,
            duplicate_trace_ids=duplicate_trace_ids,
        ),
    }


def _prediction_due_status(value: str, *, today: date) -> str:
    try:
        due = date.fromisoformat(value)
    except ValueError:
        return "invalid_date"
    return "due" if due <= today else "scheduled"


def _prediction_view(version: PositionVersion, *, today: date) -> dict[str, Any]:
    return {
        "thread_id": version.thread_id,
        "version_id": version.version_id,
        "question": version.question,
        "stance": version.stance,
        "likelihood": version.likelihood,
        "confidence": version.confidence,
        "would_change_my_mind": version.would_change_my_mind,
        "resolution_criterion": version.falsifier_resolution_criterion,
        "resolution_date": version.falsifier_resolution_date,
        "due_status": _prediction_due_status(version.falsifier_resolution_date, today=today),
        "resolution_status": "unresolved",
        "registered_at": version.recorded_at,
        "position_is_live": version.is_live,
        "supported_by": list(version.supported_by),
    }


def build_experience_view(
    expert_name: str,
    *,
    outcomes: list[ExpertOutcome],
    traces: list[dict[str, Any]],
    position_ledger: PositionLedger,
    as_of_date: date | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Build one bounded view without inferring learning or semantic quality."""
    normalized_expert = _normalized_name(expert_name)
    if position_ledger.expert_name and _normalized_name(position_ledger.expert_name) != normalized_expert:
        raise ValueError("position ledger expert does not match the requested expert")
    if any(_normalized_name(item.expert_name) != normalized_expert for item in outcomes):
        raise ValueError("outcome expert does not match the requested expert")

    today = as_of_date or _utc_today()
    bounded_limit = max(1, min(int(limit), 100))
    active = _active_outcomes(outcomes)
    traces_by_id, duplicate_trace_ids = _trace_index(traces)
    cases = [
        _outcome_case(
            item,
            expert_name=expert_name,
            traces_by_id=traces_by_id,
            duplicate_trace_ids=duplicate_trace_ids,
        )
        for item in reversed(active[-bounded_limit:])
    ]

    registered = [
        version
        for version in position_ledger.versions
        if version.would_change_my_mind.strip()
        and version.falsifier_resolution_criterion.strip()
        and version.falsifier_resolution_date.strip()
    ]
    all_predictions = [_prediction_view(version, today=today) for version in registered]
    all_predictions.sort(key=lambda item: (item["resolution_date"], item["registered_at"], item["version_id"]))
    predictions = all_predictions[:bounded_limit]

    linkage_counts = Counter(str(case["consult"]["status"]) for case in cases)
    due_counts = Counter(str(item["due_status"]) for item in all_predictions)
    return {
        "schema_version": EXPERT_EXPERIENCE_VIEW_SCHEMA_VERSION,
        "kind": EXPERT_EXPERIENCE_VIEW_KIND,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "writes_state": False,
            "cost_usd": 0.0,
            "model_calls": 0,
            "automatic_learning": False,
            "semantic_quality_verdict": False,
            "outcome_prediction_link_inferred": False,
            "canonical_sources": ["position_ledger", "consult_traces", "expert_outcomes"],
        },
        "expert_name": " ".join(expert_name.split()),
        "as_of_date": today.isoformat(),
        "counts": {
            "outcome_observations": len(outcomes),
            "current_outcomes": len(active),
            "returned_cases": len(cases),
            "registered_predictions": len(all_predictions),
            "returned_predictions": len(predictions),
            "positions_without_registered_prediction": len(position_ledger.versions) - len(registered),
            "due_predictions": due_counts["due"],
            "scheduled_predictions": due_counts["scheduled"],
            "invalid_prediction_dates": due_counts["invalid_date"],
            "consult_linkage": dict(sorted(linkage_counts.items())),
        },
        "cases": cases,
        "predictions": predictions,
    }


__all__ = [
    "EXPERT_EXPERIENCE_VIEW_KIND",
    "EXPERT_EXPERIENCE_VIEW_SCHEMA_VERSION",
    "build_experience_view",
    "trace_ids_for_experience",
]
