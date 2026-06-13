"""Tests for deepr.experts.calibration - the $0 calibration measurement engine.

Deterministic synthetic datasets (no randomness): a perfectly calibrated set,
an overconfident set, and a separable set, so the curve/ECE/Platt/threshold
math is checked against known ground truth. No model calls, no gold corpus.
"""

from __future__ import annotations

import math

from deepr.experts.calibration import (
    CALIBRATION_METHODOLOGY_VERSION,
    derive_threshold,
    expected_calibration_error,
    fit_platt,
    measure_calibration,
    precision_recall_f1,
)


def _pairs(prob_fn, m: int = 100):
    """Build (confidence, grounded) pairs where P(grounded | c) = prob_fn(c)."""
    pairs: list[tuple[float, bool]] = []
    for i in range(10):
        c = (i + 0.5) / 10  # bin centers 0.05 .. 0.95
        k = round(prob_fn(c) * m)
        pairs += [(c, True)] * k + [(c, False)] * (m - k)
    return pairs


class TestECE:
    def test_perfectly_calibrated_has_near_zero_ece(self):
        ece = expected_calibration_error(_pairs(lambda c: c))
        assert ece < 0.02

    def test_overconfident_has_large_ece(self):
        # True grounding is half the predicted confidence.
        ece = expected_calibration_error(_pairs(lambda c: c / 2))
        assert ece > 0.15

    def test_empty_is_zero(self):
        assert expected_calibration_error([]) == 0.0


class TestPlatt:
    def test_platt_reduces_ece_on_miscalibrated_data(self):
        pairs = _pairs(lambda c: c / 2)
        raw = expected_calibration_error(pairs)
        report = measure_calibration(pairs)
        assert report.ece_platt < raw

    def test_fit_positive_slope_on_separable_data(self):
        # Grounded strongly increases with confidence.
        a, _b = fit_platt(_pairs(lambda c: c))
        assert a > 0

    def test_too_few_samples_degrades_gracefully(self):
        a, b = fit_platt([(0.5, True)])
        assert (a, b) == (0.0, 0.0)


class TestDeriveThreshold:
    def test_solves_for_target(self):
        # sigmoid(10x - 5) = 0.8  ->  x = (logit(0.8) + 5) / 10
        expected = (math.log(0.8 / 0.2) + 5) / 10
        assert abs(derive_threshold(10.0, -5.0, 0.8) - expected) < 0.01

    def test_none_when_no_positive_discrimination(self):
        assert derive_threshold(0.0, 1.0, 0.8) is None
        assert derive_threshold(-3.0, 1.0, 0.8) is None

    def test_clamped_to_unit_interval(self):
        # A threshold the math would place above 1.0 is clamped.
        val = derive_threshold(0.1, -50.0, 0.8)
        assert val == 1.0


class TestPrecisionRecall:
    def test_known_confusion_matrix(self):
        pairs = [(0.9, True), (0.7, True), (0.65, False), (0.5, False), (0.2, False)]
        precision, recall, f1 = precision_recall_f1(pairs, decision_threshold=0.6)
        assert precision == 2 / 3  # 2 true positives, 1 false positive
        assert recall == 1.0  # no grounded claim missed
        assert abs(f1 - 0.8) < 1e-9


class TestParseAndRender:
    def test_parse_graded_pairs(self):
        from deepr.experts.calibration import parse_graded_pairs

        text = (
            '{"confidence": 0.8, "grounded": true, "claim": "x"}\n'
            "# a comment\n"
            "\n"
            '{"confidence": 1.5, "grounded": false}\n'  # clamped to 1.0
        )
        assert parse_graded_pairs(text) == [(0.8, True), (1.0, False)]

    def test_render_markdown_has_key_fields(self):
        from deepr.experts.calibration import render_calibration_markdown

        report = measure_calibration(_pairs(lambda c: c))
        md = render_calibration_markdown(report, model="gpt-5-mini")
        assert md.startswith("# Calibration")
        assert "gpt-5-mini" in md
        assert "Reliability curve" in md
        assert "Expected calibration error" in md
        assert "| Confidence bin |" in md

    def test_render_handles_no_threshold(self):
        from deepr.experts.calibration import render_calibration_markdown

        # All-fresh-ungrounded gives no positive discrimination -> threshold n/a.
        report = measure_calibration([(0.9, False), (0.1, False)])
        md = render_calibration_markdown(report, model="m")
        assert "n/a" in md


class TestGradeCorpus:
    async def test_extracts_and_grades_into_pairs(self):
        from deepr.experts.calibration import grade_corpus

        async def extract(text):
            return [("claim A", 0.9), ("claim B", 0.4)]

        async def grade(claim, text):
            return claim == "claim A"  # A grounded, B not

        pairs, records = await grade_corpus({"r1": "report text"}, extract_fn=extract, grade_fn=grade)
        assert pairs == [(0.9, True), (0.4, False)]
        assert records[0] == {"report_id": "r1", "claim": "claim A", "confidence": 0.9, "grounded": True}

    async def test_failed_extraction_skips_report_not_run(self):
        from deepr.experts.calibration import grade_corpus

        async def extract(text):
            if text == "bad":
                raise RuntimeError("extraction boom")
            return [("ok claim", 0.8)]

        async def grade(claim, text):
            return True

        pairs, _ = await grade_corpus({"good": "x", "bad": "bad"}, extract_fn=extract, grade_fn=grade)
        assert pairs == [(0.8, True)]  # bad report skipped, good one kept

    async def test_failed_grade_skips_claim(self):
        from deepr.experts.calibration import grade_corpus

        async def extract(text):
            return [("a", 0.7), ("b", 0.6)]

        async def grade(claim, text):
            if claim == "b":
                raise RuntimeError("grade boom")
            return True

        pairs, records = await grade_corpus({"r": "t"}, extract_fn=extract, grade_fn=grade)
        assert pairs == [(0.7, True)]
        assert len(records) == 1


class TestReport:
    def test_empty_pairs(self):
        report = measure_calibration([])
        assert report.sample_size == 0
        assert report.derived_threshold is None
        assert "no samples" in report.notes

    def test_methodology_version_and_shape(self):
        report = measure_calibration(_pairs(lambda c: c))
        d = report.to_dict()
        assert d["methodology_version"] == CALIBRATION_METHODOLOGY_VERSION
        assert d["sample_size"] == 1000
        assert "ece" in d and "ece_platt" in d
        assert "extraction" in d and "precision" in d["extraction"]
        assert isinstance(d["bins"], list) and len(d["bins"]) > 0

    def test_well_calibrated_derives_reasonable_threshold(self):
        # Identity calibration: grounding crosses 0.8 around confidence 0.8.
        report = measure_calibration(_pairs(lambda c: c), target_grounding=0.8)
        assert report.derived_threshold is not None
        assert 0.6 < report.derived_threshold < 0.95
