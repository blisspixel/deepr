"""Tests for `deepr expert review-consult-quality`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_consult_quality import (
    expert_consult_quality_trends,
    expert_judge_consult_quality,
    expert_review_consult_quality,
)
from deepr.cli.main import cli
from deepr.core.contracts import Claim, ExpertManifest
from deepr.experts.consult_quality import build_consult_quality_review
from deepr.experts.consult_traces import build_consult_trace, build_consult_trace_candidates, record_consult_trace
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    profile = ExpertProfile(
        name="Consult Quality Expert",
        vector_store_id="vs-consult-quality",
        domain="consult quality",
        knowledge_cutoff_date=datetime(2026, 6, 27, tzinfo=UTC),
    )
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain="consult quality",
        claims=[Claim.create("Consult quality reviews are human gated.", "consult quality", 0.9)],
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _patch_store(profile):
    return patch(
        "deepr.cli.commands.semantic.expert_consult_quality.ExpertStore",
        return_value=MagicMock(load=MagicMock(return_value=profile)),
    )


def _write_failed_trace(path, profile: ExpertProfile):
    record_consult_trace(
        path=path,
        question="What should the consult council improve?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_cli_quality",
    )


def _score_args() -> list[str]:
    return [
        "--score",
        "uses_expert_state=5",
        "--score",
        "surfaces_uncertainty=5",
        "--score",
        "preserves_dissent=5",
        "--score",
        "actionability=5",
        "--score",
        "grounded_when_factual=5",
        "--score",
        "original_thought=5",
    ]


def _scores(value: float) -> dict[str, float]:
    return {
        "uses_expert_state": value,
        "surfaces_uncertainty": value,
        "preserves_dissent": value,
        "actionability": value,
        "grounded_when_factual": value,
        "original_thought": value,
    }


def _write_quality_review(output_dir, profile: ExpertProfile, trace_id: str, score: float):
    trace = build_consult_trace(
        question=f"What should the consult council improve for {trace_id}?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id=trace_id,
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    candidate = build_consult_trace_candidates([trace])["candidates"][0]
    review = build_consult_quality_review(
        expert_name=profile.name,
        case=candidate["semantic_eval_case"],
        scores=_scores(score),
        reviewer="operator",
        decision="accept",
        candidate=candidate,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"consult_quality_review_{review['review_id']}.json"
    path.write_text(json.dumps(review), encoding="utf-8")


def test_review_consult_quality_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "review-consult-quality", "--help"])

    assert result.exit_code == 0
    assert "consult semantic-quality case" in result.output.lower()


def test_review_consult_quality_json_preview(tmp_path):
    profile = _profile()
    trace_path = tmp_path / "consult_traces.jsonl"
    _write_failed_trace(trace_path, profile)

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_review_consult_quality,
            [
                profile.name,
                "consult_cli_quality",
                *_score_args(),
                "--reviewer",
                "operator",
                "--decision",
                "accept",
                "--target",
                "eval",
                "--trace-path",
                str(trace_path),
                "--output-dir",
                str(tmp_path / "benchmarks"),
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-consult-quality-review-v1"
    assert payload["status"] == "preview"
    assert payload["review_status"] == "accepted"
    assert not (tmp_path / "benchmarks").exists()


def test_review_consult_quality_missing_expert_exits_nonzero():
    with _patch_store(None):
        result = CliRunner().invoke(
            expert_review_consult_quality,
            ["Ghost Expert", "consult_missing", *_score_args(), "--reviewer", "operator", "--decision", "accept"],
        )

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_judge_consult_quality_local_json(monkeypatch):
    profile = _profile()

    monkeypatch.setattr("deepr.backends.capacity.available_local_models", lambda: ["judge-local"])

    async def fake_review(profile_arg, trace_id, **kwargs):
        assert profile_arg.name == profile.name
        assert trace_id == "consult_cli_quality"
        assert kwargs["judge_model"] == "judge-local"
        assert kwargs["target"] == "eval"
        return {
            "schema_version": "deepr-consult-quality-review-v1",
            "kind": "deepr.eval.consult_quality_review",
            "expert_name": profile.name,
            "trace_id": trace_id,
            "review_status": "needs_improvement",
            "mean_score": 2.0,
            "decision": "needs_improvement",
            "eligible_for_promotion": False,
            "applied": False,
            "actions": [],
            "calibrated_judge": {
                "backend": "local",
                "model": "judge-local",
                "cost_usd": 0.0,
                "raw_response_stored": False,
                "source_trace_output_stored": False,
            },
        }

    monkeypatch.setattr(
        "deepr.experts.consult_quality.review_consult_quality_candidate_with_local_judge",
        fake_review,
    )

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_judge_consult_quality,
            [
                profile.name,
                "consult_cli_quality",
                "--local-judge-model",
                "judge-local",
                "--target",
                "eval",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["calibrated_judge"]["backend"] == "local"
    assert payload["calibrated_judge"]["cost_usd"] == 0.0
    assert payload["review_status"] == "needs_improvement"


def test_judge_consult_quality_plan_json(monkeypatch):
    profile = _profile()

    monkeypatch.setattr(
        "deepr.backends.waterfall.choose_plan_quota_backend",
        lambda backend: SimpleNamespace(is_plan_quota=True, plan_backend_id=backend, reason="plan backend selected"),
    )

    async def fake_review(profile_arg, trace_id, **kwargs):
        assert profile_arg.name == profile.name
        assert trace_id == "consult_cli_quality"
        assert kwargs["plan_backend_id"] == "codex"
        assert kwargs["judge_model"] == "gpt-5-mini"
        assert kwargs["target"] == "eval"
        return {
            "schema_version": "deepr-consult-quality-review-v1",
            "kind": "deepr.eval.consult_quality_review",
            "expert_name": profile.name,
            "trace_id": trace_id,
            "review_status": "needs_improvement",
            "mean_score": 2.0,
            "decision": "needs_improvement",
            "eligible_for_promotion": False,
            "applied": False,
            "actions": [],
            "calibrated_judge": {
                "backend": "plan_quota",
                "plan_backend_id": "codex",
                "model": "gpt-5-mini",
                "cost_usd": 0.0,
                "raw_response_stored": False,
                "source_trace_output_stored": False,
                "quota_consuming": True,
                "cost_ledger_source": "plan_quota",
            },
        }

    monkeypatch.setattr(
        "deepr.experts.consult_quality.review_consult_quality_candidate_with_plan_judge",
        fake_review,
    )

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_judge_consult_quality,
            [
                profile.name,
                "consult_cli_quality",
                "--plan",
                "codex",
                "--plan-model",
                "gpt-5-mini",
                "--target",
                "eval",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["calibrated_judge"]["backend"] == "plan_quota"
    assert payload["calibrated_judge"]["cost_usd"] == 0.0
    assert payload["calibrated_judge"]["quota_consuming"] is True


def test_judge_consult_quality_api_json(monkeypatch):
    profile = _profile()

    async def fake_review(profile_arg, trace_id, **kwargs):
        assert profile_arg.name == profile.name
        assert trace_id == "consult_cli_quality"
        assert kwargs["api_provider"] == "xai"
        assert kwargs["judge_model"] == "grok-4.3"
        assert kwargs["budget_usd"] == 0.5
        assert kwargs["confirm_metered_cost"] is True
        assert kwargs["target"] == "eval"
        return {
            "schema_version": "deepr-consult-quality-review-v1",
            "kind": "deepr.eval.consult_quality_review",
            "expert_name": profile.name,
            "trace_id": trace_id,
            "review_status": "needs_improvement",
            "mean_score": 2.0,
            "decision": "needs_improvement",
            "eligible_for_promotion": False,
            "applied": False,
            "actions": [],
            "calibrated_judge": {
                "backend": "api_metered",
                "provider": "xai",
                "model": "grok-4.3",
                "cost_usd": 0.004,
                "estimated_cost_usd": 0.01,
                "budget_usd": 0.5,
                "raw_response_stored": False,
                "source_trace_output_stored": False,
                "confirmed_metered_cost": True,
                "cost_ledger_source": "api_metered",
            },
        }

    monkeypatch.setattr(
        "deepr.experts.consult_quality.estimate_consult_quality_api_judge_cost",
        lambda _model: 0.01,
    )
    monkeypatch.setattr(
        "deepr.experts.consult_quality.review_consult_quality_candidate_with_api_judge",
        fake_review,
    )

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_judge_consult_quality,
            [
                profile.name,
                "consult_cli_quality",
                "--api-provider",
                "xai",
                "--api-model",
                "grok-4.3",
                "--budget",
                "0.50",
                "--confirm-metered-cost",
                "--target",
                "eval",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["calibrated_judge"]["backend"] == "api_metered"
    assert payload["calibrated_judge"]["provider"] == "xai"
    assert payload["calibrated_judge"]["confirmed_metered_cost"] is True


def test_judge_consult_quality_requires_exactly_one_backend():
    result = CliRunner().invoke(
        expert_judge_consult_quality,
        ["Consult Quality Expert", "consult_cli_quality"],
    )

    assert result.exit_code != 0
    assert "exactly one" in result.output.lower()


def test_judge_consult_quality_rejects_plan_model_without_plan():
    result = CliRunner().invoke(
        expert_judge_consult_quality,
        ["Consult Quality Expert", "consult_cli_quality", "--plan-model", "gpt-5-mini"],
    )

    assert result.exit_code != 0
    assert "use --plan-model with --plan" in result.output.lower()


def test_judge_consult_quality_rejects_api_model_without_provider():
    result = CliRunner().invoke(
        expert_judge_consult_quality,
        ["Consult Quality Expert", "consult_cli_quality", "--api-model", "grok-4.3"],
    )

    assert result.exit_code != 0
    assert "use --api-model with --api-provider" in result.output.lower()


def test_judge_consult_quality_rejects_api_without_metered_confirmation():
    profile = _profile()

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_judge_consult_quality,
            [
                profile.name,
                "consult_cli_quality",
                "--api-provider",
                "xai",
                "--api-model",
                "grok-4.3",
                "--budget",
                "0.50",
            ],
        )

    assert result.exit_code != 0
    assert "confirm-metered-cost" in result.output.lower()


def test_judge_consult_quality_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "judge-consult-quality", "--help"])

    assert result.exit_code == 0
    assert "explicit calibrated judge" in result.output.lower()
    assert "--api-provider" in result.output


def test_consult_quality_trends_json_outputs_review_summary(tmp_path):
    profile = _profile()
    output_dir = tmp_path / "benchmarks"
    _write_quality_review(output_dir, profile, "consult_cli_good", 5.0)
    _write_quality_review(output_dir, profile, "consult_cli_bad", 2.0)

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_consult_quality_trends,
            [
                profile.name,
                "--output-dir",
                str(output_dir),
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-consult-quality-trend-v1"
    assert payload["review_count"] == 2
    assert payload["status_counts"] == {"accepted": 1, "policy_blocked": 1}
    assert payload["regression_candidates"][0]["source_trace_id"] == "consult_cli_bad"


def _write_judge_review(output_dir, profile: ExpertProfile, trace_id, score, *, judge_type, reviewer):
    trace = build_consult_trace(
        question=f"What should the consult council improve for {trace_id}?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id=trace_id,
        recorded_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    candidate = build_consult_trace_candidates([trace])["candidates"][0]
    review = build_consult_quality_review(
        expert_name=profile.name,
        case=candidate["semantic_eval_case"],
        scores=_scores(score),
        reviewer=reviewer,
        decision="accept",
        judge_type=judge_type,
        candidate=candidate,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"consult_quality_review_{review['review_id']}.json").write_text(json.dumps(review), encoding="utf-8")


def test_consult_quality_trends_gate_excludes_untrusted_model_judge(tmp_path):
    profile = _profile()
    output_dir = tmp_path / "benchmarks"
    _write_judge_review(output_dir, profile, "consult_human_bad", 2.0, judge_type="human", reviewer="operator")
    _write_judge_review(
        output_dir, profile, "consult_model_bad", 2.0, judge_type="calibrated_model", reviewer="unproven_judge"
    )

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_consult_quality_trends,
            [profile.name, "--output-dir", str(output_dir), "--gate-untrusted-judges", "--json"],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["regression_gate"]["applied"] is True
    assert payload["regression_gate"]["excluded_untrusted_model_review_count"] == 1
    traces = {c["source_trace_id"] for c in payload["regression_candidates"]}
    assert traces == {"consult_human_bad"}


def test_consult_quality_trends_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "consult-quality-trends", "--help"])

    assert result.exit_code == 0
    assert "regression candidates" in result.output.lower()
