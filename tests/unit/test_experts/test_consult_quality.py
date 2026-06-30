"""Tests for reviewed consult-quality scoring and promotion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.core.contracts import Claim, ExpertManifest
from deepr.experts.consult_quality import (
    CONSULT_QUALITY_REVIEW_SCHEMA_VERSION,
    CONSULT_QUALITY_TREND_SCHEMA_VERSION,
    ConsultQualityReviewError,
    build_consult_quality_review,
    build_consult_quality_trend_report,
    review_consult_quality_candidate,
)
from deepr.experts.consult_traces import build_consult_trace, build_consult_trace_candidates
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    profile = ExpertProfile(
        name="Consult Quality Expert",
        vector_store_id="vs-consult-quality",
        domain="agentic consult quality",
        knowledge_cutoff_date=datetime(2026, 6, 27, tzinfo=UTC),
    )
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain="agentic consult quality",
        claims=[Claim.create("Consult failures should become reviewed quality artifacts.", "quality", 0.87)],
        gaps=[],
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _scores(value: float = 5.0) -> dict[str, float]:
    return {
        "uses_expert_state": value,
        "surfaces_uncertainty": value,
        "preserves_dissent": value,
        "actionability": value,
        "grounded_when_factual": value,
        "original_thought": value,
    }


def _trace_path(tmp_path: Path, profile: ExpertProfile) -> Path:
    trace = build_consult_trace(
        question="What did this consult miss about expert disagreement?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError", "message": "synthesis failed"},
        trace_id="consult_quality123",
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    path = tmp_path / "consult_traces.jsonl"
    path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    return path


def _candidate(trace_id: str):
    trace = build_consult_trace(
        question=f"What should improve for {trace_id}?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError"},
        trace_id=trace_id,
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    return build_consult_trace_candidates([trace])["candidates"][0]


def _write_review(output_dir: Path, review: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"consult_quality_review_{review['review_id']}.json"
    path.write_text(json.dumps(review), encoding="utf-8")


def test_build_consult_quality_review_records_reviewer_scores():
    trace = build_consult_trace(
        question="What should improve?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError"},
        trace_id="consult_review123",
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    candidate = build_consult_trace_candidates([trace])["candidates"][0]

    review = build_consult_quality_review(
        expert_name="A",
        case=candidate["semantic_eval_case"],
        scores=_scores(4.5),
        reviewer="operator",
        decision="accept",
        candidate=candidate,
    )

    assert review["schema_version"] == CONSULT_QUALITY_REVIEW_SCHEMA_VERSION
    assert review["kind"] == "deepr.eval.consult_quality_review"
    assert review["review_status"] == "accepted"
    assert review["eligible_for_promotion"] is True
    assert review["mean_score"] == 4.5
    assert review["contract"]["lexical_verdict_allowed"] is False
    assert review["acceptance_policy"]["never_commits_beliefs"] is True


def test_build_consult_quality_review_rejects_missing_scores():
    trace = build_consult_trace(
        question="What should improve?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError"},
        trace_id="consult_review123",
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    candidate = build_consult_trace_candidates([trace])["candidates"][0]

    with pytest.raises(ConsultQualityReviewError, match="Missing score"):
        build_consult_quality_review(
            expert_name="A",
            case=candidate["semantic_eval_case"],
            scores={"uses_expert_state": 5.0},
            reviewer="operator",
            decision="accept",
        )


def test_review_consult_quality_preview_does_not_write(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)

    payload = review_consult_quality_candidate(
        profile,
        "consult_quality123",
        scores=_scores(),
        reviewer="operator",
        decision="accept",
        target="both",
        trace_path=trace_path,
        output_dir=tmp_path / "benchmarks",
        experts_base_path=tmp_path / "experts",
    )

    assert payload["status"] == "preview"
    assert payload["review_status"] == "accepted"
    assert {action["status"] for action in payload["actions"]} == {"preview"}
    assert not (tmp_path / "benchmarks").exists()
    assert not (tmp_path / "experts").exists()


def test_review_consult_quality_apply_promotes_gap_and_eval(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)
    output_dir = tmp_path / "benchmarks"
    experts_base_path = tmp_path / "experts"

    payload = review_consult_quality_candidate(
        profile,
        "consult_quality123",
        scores=_scores(),
        reviewer="operator",
        decision="accept",
        target="both",
        apply=True,
        trace_path=trace_path,
        output_dir=output_dir,
        experts_base_path=experts_base_path,
    )

    assert payload["status"] == "promoted"
    review_paths = [Path(action["path"]) for action in payload["actions"] if action["action"] == "write_quality_review"]
    eval_paths = [Path(action["path"]) for action in payload["actions"] if action["action"] == "write_eval_case"]
    assert len(review_paths) == 1
    assert len(eval_paths) == 1
    review_artifact = json.loads(review_paths[0].read_text(encoding="utf-8"))
    eval_artifact = json.loads(eval_paths[0].read_text(encoding="utf-8"))
    assert review_artifact["review_status"] == "accepted"
    assert eval_artifact["source_quality_review_id"] == review_artifact["review_id"]

    tracker = MetaCognitionTracker(profile.name, base_path=str(experts_base_path))
    assert len(tracker.knowledge_gaps) == 1
    assert next(iter(tracker.knowledge_gaps.values())).topic.startswith("Consult failed:")


def test_review_consult_quality_blocks_promotion_when_policy_fails(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)

    payload = review_consult_quality_candidate(
        profile,
        "consult_quality123",
        scores=_scores(3.0),
        reviewer="operator",
        decision="accept",
        target="both",
        apply=True,
        trace_path=trace_path,
        output_dir=tmp_path / "benchmarks",
        experts_base_path=tmp_path / "experts",
    )

    assert payload["status"] == "review_recorded"
    assert payload["review_status"] == "policy_blocked"
    assert [action["status"] for action in payload["actions"]].count("blocked_by_review") == 2
    assert len(list((tmp_path / "benchmarks").glob("consult_quality_review_*.json"))) == 1
    assert not (tmp_path / "experts").exists()


def test_build_consult_quality_trend_report_selects_regression_candidates(tmp_path):
    output_dir = tmp_path / "benchmarks"
    accepted_candidate = _candidate("consult_good123")
    blocked_candidate = _candidate("consult_bad123")
    accepted = build_consult_quality_review(
        expert_name="A",
        case=accepted_candidate["semantic_eval_case"],
        scores=_scores(5.0),
        reviewer="operator",
        decision="accept",
        candidate=accepted_candidate,
        generated_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    blocked = build_consult_quality_review(
        expert_name="A",
        case=blocked_candidate["semantic_eval_case"],
        scores=_scores(2.0),
        reviewer="operator",
        decision="accept",
        candidate=blocked_candidate,
        generated_at=datetime(2026, 6, 27, 13, 0, tzinfo=UTC),
    )
    _write_review(output_dir, accepted)
    _write_review(output_dir, blocked)

    report = build_consult_quality_trend_report(expert_name="A", output_dir=output_dir, regression_limit=5)

    assert report["schema_version"] == CONSULT_QUALITY_TREND_SCHEMA_VERSION
    assert report["kind"] == "deepr.eval.consult_quality_trend"
    assert report["contract"]["read_only"] is True
    assert report["contract"]["semantic_verdict"] is False
    assert report["review_count"] == 2
    assert report["status_counts"] == {"accepted": 1, "policy_blocked": 1}
    assert report["mean_score"] == 3.5
    assert report["regression_candidate_count"] == 1
    assert report["regression_candidates"][0]["source_trace_id"] == "consult_bad123"
    assert report["regression_candidates"][0]["selection_reason"] == "review_status_policy_blocked"
    assert report["selection_policy"]["uses_reviewer_scores_only"] is True
