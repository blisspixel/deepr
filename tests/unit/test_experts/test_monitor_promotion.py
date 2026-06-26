"""Tests for reviewed metacognitive monitor proposal promotion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.core.contracts import Claim, ExpertManifest
from deepr.experts.consult_traces import build_consult_trace
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.metacognitive_monitor import (
    build_consult_trace_candidates_for_expert,
    build_metacognitive_monitor_report,
)
from deepr.experts.monitor_promotion import (
    CONSULT_TRACE_EVAL_CASE_SCHEMA_VERSION,
    METACOGNITIVE_PROMOTION_SCHEMA_VERSION,
    MonitorPromotionError,
    promote_monitor_proposal,
)
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    profile = ExpertProfile(
        name="Monitor Promotion Expert",
        vector_store_id="vs-monitor-promotion",
        domain="consult reliability",
        knowledge_cutoff_date=datetime(2026, 6, 26, tzinfo=UTC),
    )
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain="consult reliability",
        claims=[
            Claim.create("Consult failures should become reviewed eval or gap artifacts.", "consult reliability", 0.86)
        ],
        gaps=[],
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _trace_path(tmp_path, profile: ExpertProfile):
    trace = build_consult_trace(
        question="What did the failed consult miss about context selection?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError", "message": "synthesis failed"},
        trace_id="consult_promote123",
        recorded_at=datetime(2026, 6, 26, tzinfo=UTC),
    )
    path = tmp_path / "consult_traces.jsonl"
    path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    return path


def _proposal_id(profile: ExpertProfile, trace_path):
    candidates = build_consult_trace_candidates_for_expert(profile.name, path=trace_path)
    monitor = build_metacognitive_monitor_report(
        profile,
        loop_runs=[],
        consult_trace_candidates=candidates,
    )
    return monitor["proposals"][0]["proposal_id"]


def test_monitor_promotion_previews_gap_and_eval_without_writes(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)
    proposal_id = _proposal_id(profile, trace_path)

    payload = promote_monitor_proposal(
        profile,
        proposal_id,
        target="both",
        trace_path=trace_path,
        apply=False,
        output_dir=tmp_path / "benchmarks",
        experts_base_path=tmp_path / "experts",
    )

    assert payload["schema_version"] == METACOGNITIVE_PROMOTION_SCHEMA_VERSION
    assert payload["status"] == "preview"
    assert payload["applied"] is False
    assert {action["action"] for action in payload["actions"]} == {"promote_gap", "write_eval_case"}
    assert not (tmp_path / "benchmarks").exists()
    assert not (tmp_path / "experts").exists()


def test_monitor_promotion_applies_gap_idempotently(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)
    proposal_id = _proposal_id(profile, trace_path)
    experts_base_path = tmp_path / "experts"

    first = promote_monitor_proposal(
        profile,
        proposal_id,
        target="gap",
        trace_path=trace_path,
        apply=True,
        experts_base_path=experts_base_path,
    )
    second = promote_monitor_proposal(
        profile,
        proposal_id,
        target="gap",
        trace_path=trace_path,
        apply=True,
        experts_base_path=experts_base_path,
    )

    tracker = MetaCognitionTracker(profile.name, base_path=str(experts_base_path))
    assert first["status"] == "promoted"
    assert second["status"] == "already_exists"
    assert len(tracker.knowledge_gaps) == 1
    assert next(iter(tracker.knowledge_gaps.values())).topic.startswith("Consult failed:")


def test_monitor_promotion_applies_eval_case_artifact(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)
    proposal_id = _proposal_id(profile, trace_path)

    payload = promote_monitor_proposal(
        profile,
        proposal_id,
        target="eval",
        trace_path=trace_path,
        apply=True,
        output_dir=tmp_path / "benchmarks",
    )

    action = payload["actions"][0]
    artifact_path = Path(action["path"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["status"] == "promoted"
    assert artifact["schema_version"] == CONSULT_TRACE_EVAL_CASE_SCHEMA_VERSION
    assert artifact["proposal_id"] == proposal_id
    assert artifact["source_trace_id"] == "consult_promote123"
    assert artifact["case"]["category"] == "consult_trace_regression"


def test_monitor_promotion_rejects_unknown_proposal(tmp_path):
    profile = _profile()
    trace_path = _trace_path(tmp_path, profile)

    with pytest.raises(MonitorPromotionError, match="No monitor proposal"):
        promote_monitor_proposal(profile, "missing", trace_path=trace_path)
