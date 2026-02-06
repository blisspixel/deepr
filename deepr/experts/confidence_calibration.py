"""Confidence calibration for expert system.

Provides calibrated confidence scoring using isotonic regression
or Platt scaling to ensure confidence scores match actual accuracy.

Usage:
    from deepr.experts.confidence_calibration import ConfidenceCalibrator

    calibrator = ConfidenceCalibrator()

    # Add training examples
    calibrator.add_example(raw_confidence=0.9, was_correct=True)
    calibrator.add_example(raw_confidence=0.8, was_correct=False)

    # Fit calibration model
    calibrator.fit()

    # Calibrate new confidence scores
    calibrated = calibrator.calibrate(0.85)
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CalibrationExample:
    """A single calibration training example."""

    raw_confidence: float
    was_correct: bool
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_confidence": self.raw_confidence,
            "was_correct": self.was_correct,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationExample":
        return cls(
            raw_confidence=data["raw_confidence"],
            was_correct=data["was_correct"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            metadata=data.get("metadata", {}),
        )


class IsotonicCalibrator:
    """Isotonic regression calibrator.

    Fits a monotonically increasing function to map raw confidence
    scores to calibrated probabilities.
    """

    def __init__(self):
        self._breakpoints: List[Tuple[float, float]] = []
        self._is_fitted = False

    def fit(self, confidences: List[float], outcomes: List[bool]):
        """Fit isotonic regression model.

        Args:
            confidences: Raw confidence scores
            outcomes: Whether each prediction was correct
        """
        if len(confidences) < 2:
            self._is_fitted = False
            return

        # Sort by confidence
        pairs = sorted(zip(confidences, outcomes), key=lambda x: x[0])

        # Pool Adjacent Violators Algorithm (PAVA)
        # Simplified implementation
        n = len(pairs)
        weights = [1.0] * n
        values = [1.0 if correct else 0.0 for _, correct in pairs]

        # Forward pass - merge violating pairs
        i = 0
        while i < n - 1:
            if values[i] > values[i + 1]:
                # Merge pools
                total_weight = weights[i] + weights[i + 1]
                merged_value = (weights[i] * values[i] + weights[i + 1] * values[i + 1]) / total_weight

                values[i] = merged_value
                weights[i] = total_weight

                # Remove merged element
                values.pop(i + 1)
                weights.pop(i + 1)
                pairs = pairs[: i + 1] + pairs[i + 2 :]
                n -= 1

                # Check previous pair
                if i > 0:
                    i -= 1
            else:
                i += 1

        # Create breakpoints
        self._breakpoints = []
        for i, (conf, _) in enumerate(pairs):
            self._breakpoints.append((conf, values[i]))

        self._is_fitted = True

    def calibrate(self, confidence: float) -> float:
        """Calibrate a confidence score.

        Args:
            confidence: Raw confidence score

        Returns:
            Calibrated confidence score
        """
        if not self._is_fitted or not self._breakpoints:
            return confidence

        # Find surrounding breakpoints and interpolate
        if confidence <= self._breakpoints[0][0]:
            return self._breakpoints[0][1]

        if confidence >= self._breakpoints[-1][0]:
            return self._breakpoints[-1][1]

        # Linear interpolation between breakpoints
        for i in range(len(self._breakpoints) - 1):
            x1, y1 = self._breakpoints[i]
            x2, y2 = self._breakpoints[i + 1]

            if x1 <= confidence <= x2:
                if x2 == x1:
                    return y1
                t = (confidence - x1) / (x2 - x1)
                return y1 + t * (y2 - y1)

        return confidence


class PlattCalibrator:
    """Platt scaling calibrator.

    Fits a sigmoid function to map raw confidence scores
    to calibrated probabilities.
    """

    def __init__(self):
        self._a: float = 0.0
        self._b: float = 0.0
        self._is_fitted = False

    def fit(self, confidences: List[float], outcomes: List[bool], max_iter: int = 100):
        """Fit Platt scaling model using gradient descent.

        Args:
            confidences: Raw confidence scores
            outcomes: Whether each prediction was correct
            max_iter: Maximum iterations for optimization
        """
        if len(confidences) < 2:
            self._is_fitted = False
            return

        # Initialize parameters
        self._a = 0.0
        self._b = 0.0

        # Convert outcomes to targets
        targets = [1.0 if correct else 0.0 for correct in outcomes]

        # Gradient descent
        learning_rate = 0.1

        for _ in range(max_iter):
            # Compute gradients
            grad_a = 0.0
            grad_b = 0.0

            for conf, target in zip(confidences, targets):
                # Sigmoid: p = 1 / (1 + exp(-(a*conf + b)))
                z = self._a * conf + self._b
                p = 1.0 / (1.0 + math.exp(-z)) if z > -700 else 0.0

                # Gradient of cross-entropy loss
                error = p - target
                grad_a += error * conf
                grad_b += error

            # Update parameters
            self._a -= learning_rate * grad_a / len(confidences)
            self._b -= learning_rate * grad_b / len(confidences)

        self._is_fitted = True

    def calibrate(self, confidence: float) -> float:
        """Calibrate a confidence score.

        Args:
            confidence: Raw confidence score

        Returns:
            Calibrated confidence score
        """
        if not self._is_fitted:
            return confidence

        z = self._a * confidence + self._b

        # Sigmoid with overflow protection
        if z > 700:
            return 1.0
        if z < -700:
            return 0.0

        return 1.0 / (1.0 + math.exp(-z))


class ConfidenceCalibrator:
    """Main confidence calibration class.

    Supports both isotonic regression and Platt scaling,
    with automatic method selection based on data characteristics.

    Attributes:
        examples: Training examples
        method: Calibration method ('isotonic' or 'platt')
    """

    def __init__(self, method: str = "isotonic"):
        """Initialize calibrator.

        Args:
            method: Calibration method ('isotonic' or 'platt')
        """
        self.method = method
        self.examples: List[CalibrationExample] = []

        self._isotonic = IsotonicCalibrator()
        self._platt = PlattCalibrator()
        self._is_fitted = False

        # Calibration statistics
        self._stats = {"total_examples": 0, "accuracy": 0.0, "avg_confidence": 0.0, "calibration_error": 0.0}

    def add_example(self, raw_confidence: float, was_correct: bool, metadata: Optional[Dict[str, Any]] = None):
        """Add a calibration training example.

        Args:
            raw_confidence: The raw confidence score
            was_correct: Whether the prediction was correct
            metadata: Optional metadata about the example
        """
        example = CalibrationExample(raw_confidence=raw_confidence, was_correct=was_correct, metadata=metadata or {})
        self.examples.append(example)
        self._is_fitted = False  # Need to refit

    def fit(self):
        """Fit the calibration model on collected examples."""
        if len(self.examples) < 5:
            # Not enough examples
            self._is_fitted = False
            return

        confidences = [e.raw_confidence for e in self.examples]
        outcomes = [e.was_correct for e in self.examples]

        # Fit both methods
        self._isotonic.fit(confidences, outcomes)
        self._platt.fit(confidences, outcomes)

        # Update statistics
        self._stats["total_examples"] = len(self.examples)
        self._stats["accuracy"] = sum(outcomes) / len(outcomes)
        self._stats["avg_confidence"] = sum(confidences) / len(confidences)
        self._stats["calibration_error"] = self._calculate_ece(confidences, outcomes)

        self._is_fitted = True

    def calibrate(self, confidence: float) -> float:
        """Calibrate a confidence score.

        Args:
            confidence: Raw confidence score (0-1)

        Returns:
            Calibrated confidence score (0-1)
        """
        if not self._is_fitted:
            return confidence

        if self.method == "isotonic":
            return self._isotonic.calibrate(confidence)
        else:
            return self._platt.calibrate(confidence)

    def _calculate_ece(self, confidences: List[float], outcomes: List[bool], n_bins: int = 10) -> float:
        """Calculate Expected Calibration Error.

        Args:
            confidences: Confidence scores
            outcomes: Actual outcomes
            n_bins: Number of bins

        Returns:
            ECE score
        """
        bins: Dict[int, List[Tuple[float, bool]]] = defaultdict(list)

        for conf, outcome in zip(confidences, outcomes):
            bin_idx = min(int(conf * n_bins), n_bins - 1)
            bins[bin_idx].append((conf, outcome))

        ece = 0.0
        total = len(confidences)

        for bin_idx, samples in bins.items():
            if not samples:
                continue

            avg_conf = sum(c for c, _ in samples) / len(samples)
            accuracy = sum(1 for _, o in samples if o) / len(samples)

            weight = len(samples) / total
            ece += weight * abs(avg_conf - accuracy)

        return ece

    def get_stats(self) -> Dict[str, Any]:
        """Get calibration statistics.

        Returns:
            Dictionary of statistics
        """
        return dict(self._stats)

    def save(self, path: Path):
        """Save calibrator state to file.

        Args:
            path: Path to save to
        """
        data = {
            "method": self.method,
            "examples": [e.to_dict() for e in self.examples],
            "stats": self._stats,
            "is_fitted": self._is_fitted,
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ConfidenceCalibrator":
        """Load calibrator state from file.

        Args:
            path: Path to load from

        Returns:
            ConfidenceCalibrator instance
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        calibrator = cls(method=data.get("method", "isotonic"))
        calibrator.examples = [CalibrationExample.from_dict(e) for e in data.get("examples", [])]
        calibrator._stats = data.get("stats", calibrator._stats)

        # Refit if we have examples
        if calibrator.examples:
            calibrator.fit()

        return calibrator

    def needs_recalibration(self, threshold: float = 0.1) -> bool:
        """Check if recalibration is needed.

        Args:
            threshold: ECE threshold for recalibration

        Returns:
            True if recalibration is recommended
        """
        if not self._is_fitted:
            return len(self.examples) >= 5

        return self._stats.get("calibration_error", 1.0) > threshold
