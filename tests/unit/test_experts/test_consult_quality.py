"""Tests for reviewed consult-quality scoring and promotion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepr.core.contracts import Claim, ExpertManifest
from deepr.experts.consult_quality import (
    CONSULT_QUALITY_REVIEW_SCHEMA_VERSION,
    CONSULT_QUALITY_TREND_SCHEMA_VERSION,
    ConsultQualityReviewError,
    build_consult_quality_review,
    build_consult_quality_trend_report,
    parse_consult_quality_judge_response,
    review_consult_quality_candidate,
    review_consult_quality_candidate_with_api_judge,
    review_consult_quality_candidate_with_local_judge,
    review_consult_quality_candidate_with_plan_judge,
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


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str, *, usage=None, response_id: str = ""):
        self.choices = [_FakeChoice(content)]
        self.usage = usage
        self.id = response_id


class _FakeConsultQualityCompletions:
    def __init__(self, *, expected_model: str, usage=None, response_id: str = ""):
        self.calls = []
        self.expected_model = expected_model
        self.usage = usage
        self.response_id = response_id

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["messages"][-1]["content"]
        assert kwargs["model"] == self.expected_model
        assert "Thin answer." in prompt
        return _FakeResponse(
            json.dumps(
                {
                    "scores": _scores(2.0),
                    "failure_labels": ["thin_or_generic_answer"],
                    "decision": "needs_improvement",
                    "notes": "The consult answer did not use stored expert context.",
                }
            ),
            usage=self.usage,
            response_id=self.response_id,
        )


class _FakeConsultQualityChat:
    def __init__(self, *, expected_model: str, usage=None, response_id: str = ""):
        self.completions = _FakeConsultQualityCompletions(
            expected_model=expected_model,
            usage=usage,
            response_id=response_id,
        )


class _FakeConsultQualityClient:
    def __init__(self, *, expected_model: str = "judge-local", usage=None, response_id: str = ""):
        self.chat = _FakeConsultQualityChat(expected_model=expected_model, usage=usage, response_id=response_id)


class _FakeCostSafety:
    def __init__(self):
        self.checks = []
        self.records = []
        self.refunds = []

    def check_and_reserve(self, **kwargs):
        self.checks.append(kwargs)
        return True, "OK", False, "reservation-1"

    def record_cost(self, **kwargs):
        self.records.append(kwargs)
        return True

    def refund_reservation(self, reservation_id):
        self.refunds.append(reservation_id)


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


async def test_review_consult_quality_with_local_judge_scores_raw_trace_without_storing_answer(tmp_path):
    profile = _profile()
    trace = build_consult_trace(
        question="How should consult improve the expert council?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "How should consult improve the expert council?",
            "answer": "Thin answer.",
            "experts_consulted": [profile.name],
            "perspectives": [{"expert": profile.name, "confidence": 0.2, "response": "thin"}],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_localjudge",
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    trace_path = tmp_path / "consult_traces.jsonl"
    trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")

    payload = await review_consult_quality_candidate_with_local_judge(
        profile,
        "consult_localjudge",
        judge_model="judge-local",
        trace_path=trace_path,
        client=_FakeConsultQualityClient(),
    )

    assert payload["judge"]["type"] == "calibrated_model"
    assert payload["judge"]["reviewer"] == "local:judge-local"
    assert payload["review_status"] == "needs_improvement"
    assert payload["failure_labels"] == ["thin_or_generic_answer"]
    assert payload["calibrated_judge"] == {
        "backend": "local",
        "model": "judge-local",
        "cost_usd": 0.0,
        "raw_response_stored": False,
        "source_trace_output_stored": False,
    }
    assert "Thin answer." not in json.dumps(payload)


async def test_review_consult_quality_with_plan_judge_records_zero_dollar_quota_metadata(tmp_path):
    profile = _profile()
    trace = build_consult_trace(
        question="How should consult improve the expert council?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "How should consult improve the expert council?",
            "answer": "Thin answer.",
            "experts_consulted": [profile.name],
            "perspectives": [{"expert": profile.name, "confidence": 0.2, "response": "thin"}],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_planjudge",
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    trace_path = tmp_path / "consult_traces.jsonl"
    trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")

    payload = await review_consult_quality_candidate_with_plan_judge(
        profile,
        "consult_planjudge",
        plan_backend_id="codex",
        judge_model="gpt-5-mini",
        trace_path=trace_path,
        client=_FakeConsultQualityClient(expected_model="gpt-5-mini"),
    )

    assert payload["judge"]["type"] == "calibrated_model"
    assert payload["judge"]["reviewer"] == "plan_quota:codex"
    assert payload["calibrated_judge"] == {
        "backend": "plan_quota",
        "plan_backend_id": "codex",
        "model": "gpt-5-mini",
        "cost_usd": 0.0,
        "raw_response_stored": False,
        "source_trace_output_stored": False,
        "quota_consuming": True,
        "cost_ledger_source": "plan_quota",
    }
    assert "Thin answer." not in json.dumps(payload)


async def test_review_consult_quality_with_api_judge_settles_metered_cost(tmp_path):
    profile = _profile()
    trace = build_consult_trace(
        question="How should consult improve the expert council?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "How should consult improve the expert council?",
            "answer": "Thin answer.",
            "experts_consulted": [profile.name],
            "perspectives": [{"expert": profile.name, "confidence": 0.2, "response": "thin"}],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_apijudge",
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    trace_path = tmp_path / "consult_traces.jsonl"
    trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    cost_safety = _FakeCostSafety()
    usage = SimpleNamespace(prompt_tokens=1_000, completion_tokens=250, prompt_tokens_details=None)

    payload = await review_consult_quality_candidate_with_api_judge(
        profile,
        "consult_apijudge",
        api_provider="xai",
        judge_model="grok-4.3",
        budget_usd=1.0,
        confirm_metered_cost=True,
        trace_path=trace_path,
        client=_FakeConsultQualityClient(expected_model="grok-4.3", usage=usage, response_id="chatcmpl-test"),
        cost_safety_manager=cost_safety,
    )

    assert payload["judge"]["type"] == "calibrated_model"
    assert payload["judge"]["reviewer"] == "api_metered:xai:grok-4.3"
    assert payload["calibrated_judge"]["backend"] == "api_metered"
    assert payload["calibrated_judge"]["provider"] == "xai"
    assert payload["calibrated_judge"]["model"] == "grok-4.3"
    assert payload["calibrated_judge"]["cost_usd"] > 0
    assert payload["calibrated_judge"]["estimated_cost_usd"] > 0
    assert payload["calibrated_judge"]["budget_usd"] == 1.0
    assert payload["calibrated_judge"]["confirmed_metered_cost"] is True
    assert payload["calibrated_judge"]["cost_ledger_source"] == "api_metered"
    assert payload["calibrated_judge"]["request_id"] == "chatcmpl-test"
    assert cost_safety.checks[0]["operation_type"] == "consult_quality_judge"
    assert cost_safety.records[0]["reservation_id"] == "reservation-1"
    assert cost_safety.records[0]["provider"] == "xai"
    assert cost_safety.records[0]["model"] == "grok-4.3"
    assert cost_safety.records[0]["tokens_input"] == 1_000
    assert cost_safety.records[0]["tokens_output"] == 250
    assert cost_safety.refunds == []
    assert "Thin answer." not in json.dumps(payload)


async def test_review_consult_quality_with_api_judge_requires_confirmation_before_client(tmp_path):
    profile = _profile()
    cost_safety = _FakeCostSafety()

    with pytest.raises(ConsultQualityReviewError, match="confirm-metered-cost"):
        await review_consult_quality_candidate_with_api_judge(
            profile,
            "consult_apijudge",
            api_provider="openai",
            judge_model="gpt-5.2",
            budget_usd=1.0,
            confirm_metered_cost=False,
            cost_safety_manager=cost_safety,
            client=_FakeConsultQualityClient(expected_model="gpt-5.2"),
        )

    assert cost_safety.checks == []
    assert cost_safety.records == []


def test_parse_consult_quality_judge_response_rejects_unknown_label():
    candidate = _candidate("consult_badlabel")
    raw = json.dumps(
        {
            "scores": _scores(5.0),
            "failure_labels": ["made_up_label"],
            "decision": "accept",
            "notes": "bad label",
        }
    )

    with pytest.raises(ConsultQualityReviewError, match="Unknown failure label"):
        parse_consult_quality_judge_response(raw, candidate["semantic_eval_case"])


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
