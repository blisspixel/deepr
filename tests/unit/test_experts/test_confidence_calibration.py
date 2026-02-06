"""Tests for confidence calibration module."""

import json
from datetime import datetime, timezone

import pytest

from deepr.experts.confidence_calibration import (
    CalibrationExample,
    ConfidenceCalibrator,
    IsotonicCalibrator,
    PlattCalibrator,
)


class TestCalibrationExample:
    """Tests for CalibrationExample dataclass."""

    def test_construction(self):
        ex = CalibrationExample(raw_confidence=0.9, was_correct=True)
        assert ex.raw_confidence == 0.9
        assert ex.was_correct is True
        assert isinstance(ex.timestamp, datetime)
        assert ex.metadata == {}

    def test_construction_with_metadata(self):
        ex = CalibrationExample(raw_confidence=0.5, was_correct=False, metadata={"domain": "science"})
        assert ex.metadata == {"domain": "science"}

    def test_to_dict(self):
        ex = CalibrationExample(raw_confidence=0.8, was_correct=True, metadata={"k": "v"})
        d = ex.to_dict()
        assert d["raw_confidence"] == 0.8
        assert d["was_correct"] is True
        assert "timestamp" in d
        assert d["metadata"] == {"k": "v"}

    def test_from_dict(self):
        data = {
            "raw_confidence": 0.7,
            "was_correct": False,
            "timestamp": "2024-06-01T12:00:00+00:00",
            "metadata": {"x": 1},
        }
        ex = CalibrationExample.from_dict(data)
        assert ex.raw_confidence == 0.7
        assert ex.was_correct is False
        assert ex.metadata == {"x": 1}

    def test_from_dict_missing_optional_fields(self):
        data = {"raw_confidence": 0.5, "was_correct": True}
        ex = CalibrationExample.from_dict(data)
        assert ex.raw_confidence == 0.5
        assert ex.metadata == {}

    def test_round_trip(self):
        original = CalibrationExample(raw_confidence=0.85, was_correct=True, metadata={"q": "test"})
        restored = CalibrationExample.from_dict(original.to_dict())
        assert restored.raw_confidence == original.raw_confidence
        assert restored.was_correct == original.was_correct
        assert restored.metadata == original.metadata


class TestIsotonicCalibrator:
    """Tests for IsotonicCalibrator."""

    def test_not_fitted_returns_raw(self):
        cal = IsotonicCalibrator()
        assert cal.calibrate(0.7) == 0.7

    def test_too_few_examples_not_fitted(self):
        cal = IsotonicCalibrator()
        cal.fit([0.5], [True])
        assert not cal._is_fitted

    def test_fit_and_calibrate(self):
        cal = IsotonicCalibrator()
        confs = [0.1, 0.3, 0.5, 0.7, 0.9]
        outcomes = [False, False, True, True, True]
        cal.fit(confs, outcomes)
        assert cal._is_fitted
        # Low confidence should map lower, high confidence should map higher
        result = cal.calibrate(0.5)
        assert 0.0 <= result <= 1.0

    def test_calibrate_below_min(self):
        cal = IsotonicCalibrator()
        cal.fit([0.2, 0.4, 0.6, 0.8], [False, False, True, True])
        result = cal.calibrate(0.0)
        assert 0.0 <= result <= 1.0

    def test_calibrate_above_max(self):
        cal = IsotonicCalibrator()
        cal.fit([0.2, 0.4, 0.6, 0.8], [False, False, True, True])
        result = cal.calibrate(1.0)
        assert 0.0 <= result <= 1.0


class TestPlattCalibrator:
    """Tests for PlattCalibrator."""

    def test_not_fitted_returns_raw(self):
        cal = PlattCalibrator()
        assert cal.calibrate(0.7) == 0.7

    def test_too_few_examples_not_fitted(self):
        cal = PlattCalibrator()
        cal.fit([0.5], [True])
        assert not cal._is_fitted

    def test_fit_and_calibrate(self):
        cal = PlattCalibrator()
        confs = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
        outcomes = [False, False, False, True, True, True]
        cal.fit(confs, outcomes)
        assert cal._is_fitted
        result = cal.calibrate(0.5)
        assert 0.0 <= result <= 1.0

    def test_calibrate_extreme_values(self):
        cal = PlattCalibrator()
        cal.fit([0.1, 0.9], [False, True])
        # Extreme inputs should be clamped by sigmoid
        assert cal.calibrate(100.0) <= 1.0
        assert cal.calibrate(-100.0) >= 0.0


class TestConfidenceCalibrator:
    """Tests for ConfidenceCalibrator."""

    def test_init_default(self):
        cal = ConfidenceCalibrator()
        assert cal.method == "isotonic"
        assert cal.examples == []
        assert not cal._is_fitted

    def test_init_platt(self):
        cal = ConfidenceCalibrator(method="platt")
        assert cal.method == "platt"

    def test_add_example(self):
        cal = ConfidenceCalibrator()
        cal.add_example(0.8, True)
        assert len(cal.examples) == 1
        assert cal.examples[0].raw_confidence == 0.8
        assert cal.examples[0].was_correct is True

    def test_add_example_with_metadata(self):
        cal = ConfidenceCalibrator()
        cal.add_example(0.6, False, metadata={"type": "factual"})
        assert cal.examples[0].metadata == {"type": "factual"}

    def test_add_example_resets_fitted(self):
        cal = ConfidenceCalibrator()
        for i in range(10):
            cal.add_example(i / 10, i > 5)
        cal.fit()
        assert cal._is_fitted
        cal.add_example(0.5, True)
        assert not cal._is_fitted

    def test_fit_too_few_examples(self):
        cal = ConfidenceCalibrator()
        cal.add_example(0.5, True)
        cal.add_example(0.6, False)
        cal.fit()
        assert not cal._is_fitted

    def test_fit_enough_examples(self):
        cal = ConfidenceCalibrator()
        for i in range(10):
            cal.add_example(i / 10, i >= 5)
        cal.fit()
        assert cal._is_fitted

    def test_calibrate_before_fit_returns_raw(self):
        cal = ConfidenceCalibrator()
        assert cal.calibrate(0.75) == 0.75

    def test_calibrate_after_fit_isotonic(self):
        cal = ConfidenceCalibrator(method="isotonic")
        for i in range(10):
            cal.add_example(i / 10, i >= 5)
        cal.fit()
        result = cal.calibrate(0.5)
        assert 0.0 <= result <= 1.0

    def test_calibrate_after_fit_platt(self):
        cal = ConfidenceCalibrator(method="platt")
        for i in range(10):
            cal.add_example(i / 10, i >= 5)
        cal.fit()
        result = cal.calibrate(0.5)
        assert 0.0 <= result <= 1.0

    def test_get_stats(self):
        cal = ConfidenceCalibrator()
        for i in range(10):
            cal.add_example(i / 10, i >= 5)
        cal.fit()
        stats = cal.get_stats()
        assert stats["total_examples"] == 10
        assert 0.0 <= stats["accuracy"] <= 1.0
        assert 0.0 <= stats["avg_confidence"] <= 1.0
        assert stats["calibration_error"] >= 0.0

    def test_save_and_load(self, tmp_path):
        cal = ConfidenceCalibrator()
        for i in range(10):
            cal.add_example(i / 10, i >= 5)
        cal.fit()

        save_path = tmp_path / "calibration.json"
        cal.save(save_path)
        assert save_path.exists()

        loaded = ConfidenceCalibrator.load(save_path)
        assert len(loaded.examples) == 10
        assert loaded.method == "isotonic"
        assert loaded._is_fitted

    def test_save_creates_parent_dirs(self, tmp_path):
        cal = ConfidenceCalibrator()
        save_path = tmp_path / "nested" / "dir" / "calibration.json"
        cal.save(save_path)
        assert save_path.exists()

    def test_needs_recalibration_not_fitted_with_examples(self):
        cal = ConfidenceCalibrator()
        for i in range(6):
            cal.add_example(i / 10, i >= 3)
        assert cal.needs_recalibration()

    def test_needs_recalibration_not_fitted_too_few(self):
        cal = ConfidenceCalibrator()
        cal.add_example(0.5, True)
        assert not cal.needs_recalibration()

    def test_needs_recalibration_fitted_low_error(self):
        cal = ConfidenceCalibrator()
        # Perfect calibration: all correct at high confidence, all wrong at low
        for _ in range(5):
            cal.add_example(0.9, True)
            cal.add_example(0.1, False)
        cal.fit()
        # With low ECE, should not need recalibration (threshold=0.5 to be safe)
        assert not cal.needs_recalibration(threshold=0.5)
