"""Tests for the $0 judge-calibration eval."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.judge_calibration import (
    JUDGE_CALIBRATION_REPORT_SCHEMA_VERSION,
    build_judge_calibration_report,
    pair_reviews_by_trace,
)


def _review(trace_id, judge_type, scores, *, decision="accept", generated_at="2026-07-03T00:00:00+00:00", expert="X"):
    return {
        "schema_version": "deepr-consult-quality-review-v1",
        "expert_name": expert,
        "judge": {"type": judge_type, "reviewer": judge_type},
        "source": {"source_trace_id": trace_id},
        "scores": [{"dimension": dim, "score": score} for dim, score in scores.items()],
        "decision": decision,
        "generated_at": generated_at,
    }


class TestPairing:
    def test_pairs_only_traces_with_both_judge_types(self):
        reviews = [
            _review("t1", "human", {"grounded": 5}),
            _review("t1", "calibrated_model", {"grounded": 4}),
            _review("t2", "human", {"grounded": 3}),  # unpaired
        ]

        pairs = pair_reviews_by_trace(reviews)

        assert [p.trace_id for p in pairs] == ["t1"]

    def test_latest_review_per_type_is_the_anchor(self):
        reviews = [
            _review("t1", "human", {"grounded": 2}, generated_at="2026-07-01T00:00:00+00:00"),
            _review("t1", "human", {"grounded": 5}, generated_at="2026-07-03T00:00:00+00:00"),
            _review("t1", "calibrated_model", {"grounded": 5}, generated_at="2026-07-03T00:00:00+00:00"),
        ]

        pairs = pair_reviews_by_trace(reviews)

        assert len(pairs) == 1
        assert pairs[0].human["scores"][0]["score"] == 5  # the newer human review won


class TestReport:
    def test_perfect_agreement_reports_zero_error(self):
        reviews = []
        for i in range(5):
            reviews.append(_review(f"t{i}", "human", {"grounded": 4, "actionable": 5}))
            reviews.append(_review(f"t{i}", "calibrated_model", {"grounded": 4, "actionable": 5}))

        report = build_judge_calibration_report(reviews)

        assert report["schema_version"] == JUDGE_CALIBRATION_REPORT_SCHEMA_VERSION
        assert report["contract"]["cost_usd"] == 0.0
        assert report["contract"]["semantic_judgment"] is False
        assert report["summary"]["sufficient_data"] is True
        assert report["overall_agreement"]["mean_absolute_error"] == 0.0
        assert report["overall_agreement"]["exact_agreement_rate"] == 1.0
        assert report["decision_agreement"]["agreement_rate"] == 1.0

    def test_directional_bias_is_signed_model_minus_human(self):
        # Model scores one point higher than the human on every dimension.
        reviews = [
            _review("t1", "human", {"grounded": 3}),
            _review("t1", "calibrated_model", {"grounded": 4}),
        ]

        report = build_judge_calibration_report(reviews, agreement_tolerance=1.0)

        overall = report["overall_agreement"]
        assert overall["mean_signed_error"] == 1.0  # positive: model over-scores
        assert overall["mean_absolute_error"] == 1.0
        assert overall["exact_agreement_rate"] == 0.0
        assert overall["within_tolerance_rate"] == 1.0  # within the tolerance of 1

    def test_decision_disagreement_and_per_dimension_split(self):
        reviews = [
            _review("t1", "human", {"grounded": 5, "actionable": 2}, decision="accept"),
            _review("t1", "calibrated_model", {"grounded": 5, "actionable": 5}, decision="revise"),
        ]

        report = build_judge_calibration_report(reviews)

        per_dim = report["per_dimension_agreement"]
        assert per_dim["grounded"]["mean_absolute_error"] == 0.0
        assert per_dim["actionable"]["mean_absolute_error"] == 3.0
        assert report["decision_agreement"]["agreement_rate"] == 0.0
        assert report["decision_agreement"]["comparable_trace_count"] == 1

    def test_insufficient_data_is_flagged(self):
        reviews = [
            _review("t1", "human", {"grounded": 4}),
            _review("t1", "calibrated_model", {"grounded": 4}),
        ]

        report = build_judge_calibration_report(reviews)

        assert report["summary"]["sufficient_data"] is False
        assert report["summary"]["paired_trace_count"] == 1

    def test_no_reviews_produces_an_empty_but_valid_report(self):
        report = build_judge_calibration_report([])

        assert report["summary"]["paired_trace_count"] == 0
        assert report["overall_agreement"]["pair_count"] == 0
        assert report["decision_agreement"]["agreement_rate"] == 0.0


class TestCommand:
    def test_command_reports_json_over_loaded_reviews(self, monkeypatch):
        reviews = [
            _review("t1", "human", {"grounded": 4}),
            _review("t1", "calibrated_model", {"grounded": 3}),
        ]
        monkeypatch.setattr(
            "deepr.experts.consult_quality.load_consult_quality_reviews",
            lambda *, expert_name=None, limit=200: reviews,
        )

        result = CliRunner().invoke(cli, ["eval", "judge-calibration", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == JUDGE_CALIBRATION_REPORT_SCHEMA_VERSION
        assert payload["overall_agreement"]["mean_signed_error"] == -1.0  # model under-scores human here

    def test_command_save_keeps_stdout_one_json_document(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "deepr.experts.consult_quality.load_consult_quality_reviews",
            lambda *, expert_name=None, limit=200: [],
        )
        monkeypatch.setattr("deepr.config.runtime_data_path", lambda kind: tmp_path / kind)

        result = CliRunner().invoke(cli, ["eval", "judge-calibration", "--json", "--save"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["saved_to"].endswith(".json")
