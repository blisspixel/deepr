"""Tests for append-only expert outcomes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from deepr.experts.outcomes import (
    ExpertOutcomeDraft,
    ExpertOutcomeStore,
    OutcomeConflictError,
    OutcomeStorageError,
    build_outcome_summary,
)


def _draft(
    *,
    result: str = "succeeded",
    observation: str = "The migration met its availability target.",
    supersedes: str | None = None,
) -> ExpertOutcomeDraft:
    return ExpertOutcomeDraft.model_validate(
        {
            "expert_name": "Platform Expert",
            "decision_id": "migration-2026",
            "decision_summary": "Choose the migration architecture",
            "result": result,
            "observation": observation,
            "observed_at": "2026-07-15T12:00:00+00:00",
            "attested_by": "operator",
            "consult_trace_id": "trace:123",
            "belief_ids": ["belief-1"],
            "source_refs": ["https://example.test/source"],
            "evidence_refs": ["incident-review-42"],
            "supersedes_outcome_id": supersedes,
        }
    )


def test_record_is_append_only_and_idempotent(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    first = store.record(_draft(), outcome_id="outcome-1", now=now)
    duplicate = store.record(_draft(), outcome_id="outcome-1", now=datetime(2026, 7, 17, tzinfo=UTC))

    assert first.appended is True
    assert duplicate.appended is False
    assert duplicate.outcome == first.outcome
    assert first.outcome.contract.cost_usd == 0.0
    assert first.outcome.contract.automatic_learning is False
    assert first.outcome.contract.operator_attested is True
    assert first.outcome.contract.human_authorship_claimed is False
    assert first.outcome.contract.reviewer_identity_verified is False
    assert len(store.load_all("Platform Expert")) == 1


def test_reused_id_with_different_content_is_rejected(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    store.record(_draft(), outcome_id="outcome-1")

    with pytest.raises(OutcomeConflictError, match="different content"):
        store.record(_draft(observation="A different observation."), outcome_id="outcome-1")


def test_correction_must_reference_an_earlier_outcome(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)

    with pytest.raises(OutcomeConflictError, match="does not exist"):
        store.record(_draft(supersedes="missing"), outcome_id="outcome-2")

    store.record(_draft(), outcome_id="outcome-1")
    corrected = store.record(
        _draft(result="mixed", observation="The later review found a partial miss.", supersedes="outcome-1"),
        outcome_id="outcome-2",
    )
    assert corrected.outcome.supersedes_outcome_id == "outcome-1"

    with pytest.raises(OutcomeConflictError, match="already has a correction"):
        store.record(
            _draft(result="failed", observation="A conflicting correction.", supersedes="outcome-1"),
            outcome_id="outcome-3",
        )


def test_correction_must_retain_the_decision_id(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    store.record(_draft(), outcome_id="outcome-1")
    payload = _draft(supersedes="outcome-1").model_dump(mode="json")
    payload["decision_id"] = "another-decision"

    with pytest.raises(OutcomeConflictError, match="retain the earlier"):
        store.record(ExpertOutcomeDraft.model_validate(payload), outcome_id="outcome-2")


def test_summary_reports_structure_without_quality_verdict(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    store.record(_draft(), outcome_id="outcome-1")
    store.record(_draft(result="failed", observation="The target was missed."), outcome_id="outcome-2")

    payload = build_outcome_summary("Platform Expert", store.load_all("Platform Expert"), limit=1)

    assert payload["result_counts"] == {"succeeded": 1, "mixed": 0, "failed": 1, "unresolved": 0}
    assert payload["linkage"] == {
        "consult_trace_linked": 2,
        "belief_linked": 2,
        "source_linked": 2,
        "evidence_linked": 2,
    }
    assert len(payload["recent_outcomes"]) == 1
    assert payload["contract"]["semantic_quality_verdict"] is False


def test_summary_counts_only_latest_corrections_as_current(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    store.record(_draft(), outcome_id="outcome-1")
    store.record(
        _draft(result="failed", observation="The reviewed correction found a miss.", supersedes="outcome-1"),
        outcome_id="outcome-2",
    )

    payload = build_outcome_summary("Platform Expert", store.load_all("Platform Expert"))

    assert payload["total_outcomes"] == 2
    assert payload["active_outcomes"] == 1
    assert payload["superseded_outcomes"] == 1
    assert payload["result_counts"] == {"succeeded": 0, "mixed": 0, "failed": 1, "unresolved": 0}
    assert payload["observation_result_counts"] == {
        "succeeded": 1,
        "mixed": 0,
        "failed": 1,
        "unresolved": 0,
    }


def test_load_fails_closed_when_history_is_tampered(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    store.record(_draft(), outcome_id="outcome-1")
    path = store.path_for("Platform Expert")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["observation"] = "Tampered observation"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(OutcomeStorageError, match="content hash mismatch"):
        store.load_all("Platform Expert")


def test_invalid_expert_path_fails_with_a_domain_error(tmp_path) -> None:
    with pytest.raises(OutcomeStorageError, match="safety validation"):
        ExpertOutcomeStore(tmp_path).load_all("../../")


def test_display_name_whitespace_normalizes_on_reload_and_summary(tmp_path) -> None:
    store = ExpertOutcomeStore(tmp_path)
    recorded = store.record(_draft(), outcome_id="outcome-1")

    loaded = store.load_all("  Platform   Expert  ")
    summary = build_outcome_summary("  Platform   Expert  ", loaded)

    assert loaded == [recorded.outcome]
    assert summary["expert_name"] == "Platform Expert"
