"""Tests for the read-only expert experience projection."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from deepr.experts.consult_traces import build_consult_trace
from deepr.experts.experience import build_experience_view, trace_ids_for_experience
from deepr.experts.outcomes import ExpertOutcomeDraft, ExpertOutcomeStore
from deepr.experts.position_ledger import PositionLedger, PositionVersion


def _outcome_draft(
    *,
    result: str = "failed",
    trace_id: str | None = "trace:123",
    supersedes: str | None = None,
) -> ExpertOutcomeDraft:
    return ExpertOutcomeDraft.model_validate(
        {
            "expert_name": "Platform Expert",
            "decision_id": "migration-2026",
            "decision_summary": "Choose the migration architecture",
            "result": result,
            "observation": "The cutover exceeded its recovery target.",
            "observed_at": "2026-07-15T12:00:00+00:00",
            "attested_by": "operator",
            "consult_trace_id": trace_id,
            "belief_ids": ["belief-1"],
            "source_refs": [],
            "evidence_refs": ["postmortem-42"],
            "supersedes_outcome_id": supersedes,
        }
    )


def _trace(*, expert_name: str = "Platform Expert") -> dict[str, object]:
    return build_consult_trace(
        question="Which migration architecture should we choose?",
        requested_experts=[expert_name],
        max_experts=1,
        budget=0.0,
        payload={"experts_consulted": [expert_name], "perspectives": [], "cost_usd": 0.0},
        trace_id="trace:123",
        recorded_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def _ledger() -> PositionLedger:
    return PositionLedger(
        expert_name="Platform Expert",
        versions=[
            PositionVersion(
                thread_id="position-thread-1",
                version_id="position-version-1",
                question="Will the migration meet its recovery target?",
                stance="It is likely to meet the target.",
                likelihood="likely",
                confidence="moderate",
                would_change_my_mind="A completed cutover exceeds the recovery target.",
                falsifier_resolution_criterion="The measured recovery time exceeds 30 minutes.",
                falsifier_resolution_date="2026-07-15",
                supported_by=["finding-1"],
                recorded_at="2026-06-01T00:00:00+00:00",
            ),
            PositionVersion(
                thread_id="position-thread-2",
                version_id="position-version-2",
                question="Will the next phase remain within budget?",
                stance="It is likely to remain within budget.",
                likelihood="likely",
                confidence="low",
                would_change_my_mind="The next phase exceeds the approved ceiling.",
                falsifier_resolution_criterion="Settled cost exceeds the approved ceiling.",
                falsifier_resolution_date="2026-12-01",
                supported_by=["finding-2"],
                recorded_at="2026-06-02T00:00:00+00:00",
            ),
        ],
    )


def test_view_joins_current_outcome_to_trace_without_inferring_learning(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    first = store.record(_outcome_draft(), outcome_id="outcome-1")
    store.record(
        _outcome_draft(result="mixed", supersedes=first.outcome.outcome_id),
        outcome_id="outcome-2",
    )

    payload = build_experience_view(
        "Platform Expert",
        outcomes=store.load_all("Platform Expert"),
        traces=[_trace()],
        position_ledger=_ledger(),
        as_of_date=date(2026, 8, 30),
    )

    assert payload["schema_version"] == "deepr-expert-experience-view-v1"
    assert payload["counts"]["outcome_observations"] == 2
    assert payload["counts"]["current_outcomes"] == 1
    assert payload["cases"][0]["outcome_id"] == "outcome-2"
    assert payload["cases"][0]["consult"]["status"] == "matched"
    assert payload["cases"][0]["consult"]["question"].startswith("Which migration")
    assert payload["contract"]["automatic_learning"] is False
    assert payload["contract"]["semantic_quality_verdict"] is False
    assert payload["contract"]["outcome_prediction_link_inferred"] is False


def test_view_exposes_due_and_scheduled_predictions() -> None:
    payload = build_experience_view(
        "Platform Expert",
        outcomes=[],
        traces=[],
        position_ledger=_ledger(),
        as_of_date=date(2026, 8, 30),
    )

    assert payload["counts"]["registered_predictions"] == 2
    assert payload["counts"]["due_predictions"] == 1
    assert payload["counts"]["scheduled_predictions"] == 1
    assert [item["due_status"] for item in payload["predictions"]] == ["due", "scheduled"]
    assert all(item["resolution_status"] == "unresolved" for item in payload["predictions"])


def test_trace_linkage_refuses_duplicate_and_wrong_expert_records(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    store.record(_outcome_draft(), outcome_id="outcome-1")
    outcomes = store.load_all("Platform Expert")

    duplicate = build_experience_view(
        "Platform Expert",
        outcomes=outcomes,
        traces=[_trace(), _trace()],
        position_ledger=PositionLedger(expert_name="Platform Expert"),
    )
    mismatch = build_experience_view(
        "Platform Expert",
        outcomes=outcomes,
        traces=[_trace(expert_name="Security Expert")],
        position_ledger=PositionLedger(expert_name="Platform Expert"),
    )
    roster_unknown = build_experience_view(
        "Platform Expert",
        outcomes=outcomes,
        traces=[{"trace_id": "trace:123", "input": {"question": "private question"}}],
        position_ledger=PositionLedger(expert_name="Platform Expert"),
    )

    assert duplicate["cases"][0]["consult"]["status"] == "ambiguous_duplicate"
    assert mismatch["cases"][0]["consult"]["status"] == "expert_mismatch"
    assert roster_unknown["cases"][0]["consult"] == {"status": "roster_unknown", "trace_id": "trace:123"}


def test_trace_id_selection_uses_only_current_bounded_cases(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    first = store.record(_outcome_draft(trace_id="trace:old"), outcome_id="outcome-1")
    store.record(
        _outcome_draft(trace_id="trace:new", supersedes=first.outcome.outcome_id),
        outcome_id="outcome-2",
    )

    assert trace_ids_for_experience(store.load_all("Platform Expert"), limit=1) == {"trace:new"}


def test_view_bounds_cases_and_predictions(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    for index in range(3):
        draft = _outcome_draft(trace_id=None).model_copy(update={"decision_id": f"decision-{index}"})
        store.record(draft, outcome_id=f"outcome-{index}")

    payload = build_experience_view(
        "Platform Expert",
        outcomes=store.load_all("Platform Expert"),
        traces=[],
        position_ledger=_ledger(),
        limit=1,
    )

    assert payload["counts"]["current_outcomes"] == 3
    assert payload["counts"]["returned_cases"] == 1
    assert payload["counts"]["registered_predictions"] == 2
    assert payload["counts"]["returned_predictions"] == 1


def test_view_refuses_cross_expert_authority_records(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    outcome = store.record(_outcome_draft(), outcome_id="outcome-1").outcome

    with pytest.raises(ValueError, match="position ledger expert"):
        build_experience_view(
            "Platform Expert",
            outcomes=[outcome],
            traces=[],
            position_ledger=PositionLedger(expert_name="Security Expert"),
        )

    with pytest.raises(ValueError, match="outcome expert"):
        build_experience_view(
            "Security Expert",
            outcomes=[outcome],
            traces=[],
            position_ledger=PositionLedger(expert_name="Security Expert"),
        )
