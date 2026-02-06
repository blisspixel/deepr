"""Tests for confidence calibration.

Tests the ConfidenceCalibrator, IsotonicCalibrator, and PlattCalibrator
to ensure confidence scores are properly calibrated.
"""

import tempfile
from datetime import datetime
from pathlib import Path

from deepr.experts.confidence_calibration import (
    CalibrationExample,
    ConfidenceCalibrator,
    IsotonicCalibrator,
    PlattCalibrator,
)


class TestCalibrationExample:
    """Tests for CalibrationExample dataclass."""

    def test_create_example(self):
        """Test creating a calibration example."""
        example = CalibrationExample(raw_confidence=0.85, was_correct=True, metadata={"query": "test"})

        assert example.raw_confidence == 0.85
        assert example.was_correct is True
        assert example.metadata == {"query": "test"}
        assert isinstance(example.timestamp, datetime)

    def test_to_dict(self):
        """Test serialization to dictionary."""
        example = CalibrationExample(raw_confidence=0.75, was_correct=False)

        data = example.to_dict()

        assert data["raw_confidence"] == 0.75
        assert data["was_correct"] is False
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "raw_confidence": 0.9,
            "was_correct": True,
            "timestamp": "2025-01-01T00:00:00",
            "metadata": {"source": "test"},
        }

        example = CalibrationExample.from_dict(data)

        assert example.raw_confidence == 0.9
        assert example.was_correct is True
        assert example.metadata == {"source": "test"}


class TestIsotonicCalibrator:
    """Tests for IsotonicCalibrator."""

    def test_fit_with_perfect_calibration(self):
        """Test fitting with perfectly calibrated data."""
        calibrator = IsotonicCalibrator()

        # Perfect calibration: high confidence = correct, low = incorrect
        confidences = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
        outcomes = [False, False, False, True, True, True]

        calibrator.fit(confidences, outcomes)

        # Should be fitted
        assert calibrator._is_fitted

        # Low confidence should map to low probability
        assert calibrator.calibrate(0.1) < 0.5

        # High confidence should map to high probability
        assert calibrator.calibrate(0.9) > 0.5

    def test_fit_with_overconfident_data(self):
        """Test fitting with overconfident predictions."""
        calibrator = IsotonicCalibrator()

        # Overconfident: high confidence but often wrong
        confidences = [0.8, 0.85, 0.9, 0.95, 0.8, 0.85]
        outcomes = [True, False, True, False, False, True]

        calibrator.fit(confidences, outcomes)

        # Calibrated scores should be lower than raw
        calibrated = calibrator.calibrate(0.9)
        assert calibrated <= 0.9

    def test_fit_with_insufficient_data(self):
        """Test fitting with too few examples."""
        calibrator = IsotonicCalibrator()

        calibrator.fit([0.5], [True])

        assert not calibrator._is_fitted

    def test_calibrate_without_fitting(self):
        """Test calibration without fitting returns raw score."""
        calibrator = IsotonicCalibrator()

        result = calibrator.calibrate(0.75)

        assert result == 0.75


class TestPlattCalibrator:
    """Tests for PlattCalibrator."""

    def test_fit_basic(self):
        """Test basic Platt scaling fit."""
        calibrator = PlattCalibrator()

        confidences = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
        outcomes = [False, False, False, True, True, True]

        calibrator.fit(confidences, outcomes)

        assert calibrator._is_fitted

    def test_calibrate_produces_valid_probabilities(self):
        """Test that calibrated scores are valid probabilities."""
        calibrator = PlattCalibrator()

        confidences = [0.1, 0.3, 0.5, 0.7, 0.9]
        outcomes = [False, False, True, True, True]

        calibrator.fit(confidences, outcomes)

        # Test various inputs
        for conf in [0.0, 0.25, 0.5, 0.75, 1.0]:
            calibrated = calibrator.calibrate(conf)
            assert 0.0 <= calibrated <= 1.0

    def test_calibrate_without_fitting(self):
        """Test calibration without fitting returns raw score."""
        calibrator = PlattCalibrator()

        result = calibrator.calibrate(0.6)

        assert result == 0.6


class TestConfidenceCalibrator:
    """Tests for main ConfidenceCalibrator class."""

    def test_add_example(self):
        """Test adding calibration examples."""
        calibrator = ConfidenceCalibrator()

        calibrator.add_example(0.8, True)
        calibrator.add_example(0.6, False)

        assert len(calibrator.examples) == 2

    def test_fit_with_examples(self):
        """Test fitting with collected examples."""
        calibrator = ConfidenceCalibrator()

        # Add enough examples
        for i in range(10):
            conf = 0.1 * i
            correct = i >= 5
            calibrator.add_example(conf, correct)

        calibrator.fit()

        assert calibrator._is_fitted

    def test_fit_with_insufficient_examples(self):
        """Test fitting with too few examples."""
        calibrator = ConfidenceCalibrator()

        calibrator.add_example(0.5, True)
        calibrator.add_example(0.6, False)

        calibrator.fit()

        assert not calibrator._is_fitted

    def test_calibrate_isotonic(self):
        """Test calibration using isotonic method."""
        calibrator = ConfidenceCalibrator(method="isotonic")

        # Add training data
        for i in range(20):
            conf = 0.05 * i
            correct = i >= 10
            calibrator.add_example(conf, correct)

        calibrator.fit()

        # Test calibration
        result = calibrator.calibrate(0.75)
        assert 0.0 <= result <= 1.0

    def test_calibrate_platt(self):
        """Test calibration using Platt scaling."""
        calibrator = ConfidenceCalibrator(method="platt")

        # Add training data
        for i in range(20):
            conf = 0.05 * i
            correct = i >= 10
            calibrator.add_example(conf, correct)

        calibrator.fit()

        # Test calibration
        result = calibrator.calibrate(0.75)
        assert 0.0 <= result <= 1.0

    def test_get_stats(self):
        """Test getting calibration statistics."""
        calibrator = ConfidenceCalibrator()

        # Add examples
        for i in range(10):
            calibrator.add_example(0.1 * i, i >= 5)

        calibrator.fit()

        stats = calibrator.get_stats()

        assert "total_examples" in stats
        assert "accuracy" in stats
        assert "avg_confidence" in stats
        assert "calibration_error" in stats
        assert stats["total_examples"] == 10

    def test_save_and_load(self):
        """Test saving and loading calibrator state."""
        calibrator = ConfidenceCalibrator()

        # Add examples and fit
        for i in range(10):
            calibrator.add_example(0.1 * i, i >= 5)
        calibrator.fit()

        # Save
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calibrator.json"
            calibrator.save(path)

            # Load
            loaded = ConfidenceCalibrator.load(path)

            assert len(loaded.examples) == 10
            assert loaded._is_fitted

    def test_needs_recalibration(self):
        """Test recalibration detection."""
        calibrator = ConfidenceCalibrator()

        # Without fitting, should need calibration if enough examples
        assert not calibrator.needs_recalibration()

        # Add examples
        for i in range(10):
            calibrator.add_example(0.1 * i, i >= 5)

        assert calibrator.needs_recalibration()

        # After fitting, depends on ECE
        calibrator.fit()
        # Result depends on calibration error


class TestCalibrationAccuracy:
    """Tests for calibration accuracy and quality."""

    def test_well_calibrated_data_has_low_ece(self):
        """Test that well-calibrated data produces low ECE."""
        calibrator = ConfidenceCalibrator()

        # Create well-calibrated data
        # 20% confidence -> 20% correct, etc.
        import random

        random.seed(42)

        for _ in range(100):
            conf = random.random()
            correct = random.random() < conf
            calibrator.add_example(conf, correct)

        calibrator.fit()

        stats = calibrator.get_stats()
        # ECE should be relatively low for well-calibrated data
        assert stats["calibration_error"] < 0.3

    def test_overconfident_data_detection(self):
        """Test detection of overconfident predictions."""
        calibrator = ConfidenceCalibrator()

        # Overconfident: always predicts 90% but only 50% correct
        for i in range(20):
            calibrator.add_example(0.9, i % 2 == 0)

        calibrator.fit()

        # Calibrated score should be lower than raw
        calibrated = calibrator.calibrate(0.9)
        assert calibrated < 0.9

    def test_underconfident_data_detection(self):
        """Test detection of underconfident predictions."""
        calibrator = ConfidenceCalibrator()

        # Underconfident: always predicts 30% but 80% correct
        for i in range(20):
            calibrator.add_example(0.3, i < 16)

        calibrator.fit()

        # Calibrated score should be higher than raw
        calibrated = calibrator.calibrate(0.3)
        assert calibrated > 0.3


class TestCalibrationThresholds:
    """Tests for calibration threshold verification."""

    def test_calibration_meets_threshold(self):
        """Test that calibration error meets acceptable threshold.

        This is the key test for task 24B.1 - verifying calibration
        accuracy meets the required threshold.
        """
        calibrator = ConfidenceCalibrator()

        # Create realistic training data
        import random

        random.seed(123)

        # Simulate expert predictions with some miscalibration
        for _ in range(200):
            # Raw confidence tends to be overconfident
            raw_conf = random.uniform(0.5, 1.0)
            # Actual accuracy is lower
            actual_prob = raw_conf * 0.8  # 20% overconfident
            correct = random.random() < actual_prob
            calibrator.add_example(raw_conf, correct)

        calibrator.fit()

        stats = calibrator.get_stats()

        # After calibration, ECE should be below threshold
        # Threshold of 0.16 is reasonable for practical systems with
        # synthetic data that has systematic miscalibration patterns
        CALIBRATION_THRESHOLD = 0.16

        # Note: The calibrator should reduce ECE, but may not achieve
        # perfect calibration. We verify it's within acceptable bounds.
        assert stats["calibration_error"] < CALIBRATION_THRESHOLD, (
            f"Calibration error {stats['calibration_error']:.3f} exceeds threshold {CALIBRATION_THRESHOLD}"
        )


class TestCalibrationEdgeCases:
    """Tests for edge cases in calibration."""

    def test_all_correct_predictions(self):
        """Test calibration when all predictions are correct."""
        calibrator = ConfidenceCalibrator()

        for i in range(10):
            calibrator.add_example(0.5 + i * 0.05, True)

        calibrator.fit()

        # Should be fitted
        assert calibrator._is_fitted

        # Calibrated scores should be high
        calibrated = calibrator.calibrate(0.9)
        assert calibrated > 0.5

    def test_all_incorrect_predictions(self):
        """Test calibration when all predictions are incorrect."""
        calibrator = ConfidenceCalibrator()

        for i in range(10):
            calibrator.add_example(0.5 + i * 0.05, False)

        calibrator.fit()

        # Should be fitted
        assert calibrator._is_fitted

        # Calibrated scores should be low
        calibrated = calibrator.calibrate(0.9)
        assert calibrated < 0.5

    def test_extreme_confidence_values(self):
        """Test calibration with extreme confidence values."""
        calibrator = ConfidenceCalibrator()

        # Add examples at extremes
        for _ in range(5):
            calibrator.add_example(0.0, False)
            calibrator.add_example(1.0, True)
            calibrator.add_example(0.5, True)
            calibrator.add_example(0.5, False)

        calibrator.fit()

        # Test extreme inputs
        assert 0.0 <= calibrator.calibrate(0.0) <= 1.0
        assert 0.0 <= calibrator.calibrate(1.0) <= 1.0
        assert 0.0 <= calibrator.calibrate(0.5) <= 1.0

    def test_duplicate_confidence_values(self):
        """Test calibration with many duplicate confidence values."""
        calibrator = ConfidenceCalibrator()

        # Many examples at same confidence
        for _ in range(10):
            calibrator.add_example(0.7, True)
        for _ in range(5):
            calibrator.add_example(0.7, False)

        calibrator.fit()

        # Should handle duplicates gracefully
        calibrated = calibrator.calibrate(0.7)
        assert 0.0 <= calibrated <= 1.0
        # Should be close to actual accuracy (10/15 = 0.67)
        assert 0.5 <= calibrated <= 0.8

    def test_metadata_preservation(self):
        """Test that metadata is preserved through save/load."""
        calibrator = ConfidenceCalibrator()

        calibrator.add_example(0.8, True, metadata={"query": "test", "domain": "science"})
        calibrator.add_example(0.6, False, metadata={"query": "test2", "domain": "history"})

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "calibrator.json"
            calibrator.save(path)

            loaded = ConfidenceCalibrator.load(path)

            assert loaded.examples[0].metadata == {"query": "test", "domain": "science"}
            assert loaded.examples[1].metadata == {"query": "test2", "domain": "history"}


class TestPlattCalibratorEdgeCases:
    """Additional edge case tests for Platt calibrator."""

    def test_platt_with_uniform_outcomes(self):
        """Test Platt scaling with uniform outcomes."""
        calibrator = PlattCalibrator()

        # All same outcome
        confidences = [0.1, 0.3, 0.5, 0.7, 0.9]
        outcomes = [True, True, True, True, True]

        calibrator.fit(confidences, outcomes)

        # Should still produce valid probabilities
        for conf in [0.0, 0.5, 1.0]:
            result = calibrator.calibrate(conf)
            assert 0.0 <= result <= 1.0

    def test_platt_numerical_stability(self):
        """Test Platt scaling numerical stability with extreme values."""
        calibrator = PlattCalibrator()

        # Normal training data
        confidences = [0.2, 0.4, 0.6, 0.8]
        outcomes = [False, False, True, True]

        calibrator.fit(confidences, outcomes)

        # Test with values that could cause overflow
        # The implementation should handle these gracefully
        result_low = calibrator.calibrate(-100.0)
        result_high = calibrator.calibrate(100.0)

        assert 0.0 <= result_low <= 1.0
        assert 0.0 <= result_high <= 1.0


class TestIsotonicCalibratorEdgeCases:
    """Additional edge case tests for Isotonic calibrator."""

    def test_isotonic_with_single_breakpoint(self):
        """Test isotonic calibration with minimal data."""
        calibrator = IsotonicCalibrator()

        # Just two points
        confidences = [0.3, 0.7]
        outcomes = [False, True]

        calibrator.fit(confidences, outcomes)

        # Should interpolate between breakpoints
        result = calibrator.calibrate(0.5)
        assert 0.0 <= result <= 1.0

    def test_isotonic_monotonicity(self):
        """Test that isotonic calibration maintains monotonicity."""
        calibrator = IsotonicCalibrator()

        # Data that would violate monotonicity without PAVA
        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        outcomes = [False, True, False, True, False, True, True, True, True]

        calibrator.fit(confidences, outcomes)

        # Verify monotonicity: higher input -> higher or equal output
        prev_result = 0.0
        for conf in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            result = calibrator.calibrate(conf)
            assert result >= prev_result - 0.001, f"Monotonicity violated: {prev_result} -> {result} at {conf}"
            prev_result = result
