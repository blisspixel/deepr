"""Tests for read-only metacognitive monitor artifacts."""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.consult_traces import record_consult_trace
from deepr.experts.loop_runs import ExpertLoopRun, LoopRunStatus, LoopStopReason
from deepr.experts.metacognitive_monitor import (
    METACOGNITIVE_MONITOR_KIND,
    METACOGNITIVE_MONITOR_SCHEMA_VERSION,
    build_consult_trace_candidates_for_expert,
    build_metacognitive_monitor_report,
)
from deepr.experts.profile import ExpertProfile


def _profile(manifest: ExpertManifest) -> ExpertProfile:
    profile = ExpertProfile(
        name="Agent Harness Expert",
        vector_store_id="vs-agent-harness",
        domain="agent harnesses",
        knowledge_cutoff_date=datetime.now(UTC),
        last_knowledge_refresh=datetime.now(UTC),
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _healthy_manifest() -> ExpertManifest:
    return ExpertManifest(
        expert_name="Agent Harness Expert",
        domain="agent harnesses",
        claims=[Claim.create("Trace failures into evals.", "agent harnesses", 0.9)],
    )


def test_metacognitive_monitor_emits_review_required_proposals():
    profile = _profile(_healthy_manifest())
    failed_run = ExpertLoopRun(
        run_id="loop_failed",
        expert_name=profile.name,
        loop_type="sync",
        goal="sync subscribed topics",
        trigger="scheduled",
        status=LoopRunStatus.FAILED,
        stop_reason=LoopStopReason.TOOL_FAILURE,
    )
    candidate_payload = {
        "candidate_count": 1,
        "candidates": [
            {
                "trace_id": "consult_failed",
                "reason": "failed_consult",
                "question_preview": "How should the expert recover from synthesis failure?",
            }
        ],
    }

    payload = build_metacognitive_monitor_report(
        profile,
        loop_runs=[failed_run],
        consult_trace_candidates=candidate_payload,
    )

    assert payload["schema_version"] == METACOGNITIVE_MONITOR_SCHEMA_VERSION
    assert payload["kind"] == METACOGNITIVE_MONITOR_KIND
    assert payload["contract"]["read_only"] is True
    assert payload["contract"]["auto_apply"] is False
    assert payload["signals"]["failed_loop_count"] == 1
    assert payload["signals"]["consult_trace_candidate_count"] == 1
    assert {proposal["proposal_type"] for proposal in payload["proposals"]} >= {
        "learning_strategy_update",
        "gap_or_eval_candidate",
    }
    assert all(proposal["status"] == "review_required" for proposal in payload["proposals"])
    assert all(proposal["auto_apply"] is False for proposal in payload["proposals"])


def test_metacognitive_monitor_does_not_propose_when_only_noop_risk_exists():
    payload = build_metacognitive_monitor_report(
        _profile(_healthy_manifest()),
        loop_runs=[],
        consult_trace_candidates={"candidate_count": 0, "candidates": []},
    )

    assert payload["proposal_count"] == 0
    assert payload["signals"]["active_risk_count"] == 0
    assert payload["next_review"]["status"] == "no_actions"


def test_metacognitive_monitor_proposes_self_model_review_for_blockers():
    manifest = ExpertManifest(
        expert_name="Agent Harness Expert",
        domain="agent harnesses",
        gaps=[Gap.create("missing eval baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    payload = build_metacognitive_monitor_report(
        _profile(manifest),
        loop_runs=[],
        consult_trace_candidates={"candidate_count": 0, "candidates": []},
    )

    assert payload["signals"]["blocked_capability_count"] >= 1
    assert payload["proposals"][0]["proposal_type"] == "self_model_review"
    assert payload["proposals"][0]["requires_human_review"] is True


def test_consult_trace_candidates_for_expert_filters_other_experts(tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    record_consult_trace(
        path=path,
        question="Why did harness consult fail?",
        requested_experts=["Agent Harness Expert"],
        max_experts=3,
        budget=0.0,
        failure={"stage": "consult", "error_type": "RuntimeError"},
        trace_id="consult_harness",
    )
    record_consult_trace(
        path=path,
        question="Why did finance consult fail?",
        requested_experts=["Finance Expert"],
        max_experts=3,
        budget=0.0,
        failure={"stage": "consult", "error_type": "RuntimeError"},
        trace_id="consult_finance",
    )

    payload = build_consult_trace_candidates_for_expert("Agent Harness Expert", path=path)

    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["trace_id"] == "consult_harness"
