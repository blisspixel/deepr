"""Quality metrics for expert system evaluation.

Provides metrics for measuring expert response quality:
- Citation accuracy (precision/recall)
- Answer relevance (semantic similarity)
- Confidence calibration (Brier score)

Usage:
    from deepr.observability.quality_metrics import QualityMetrics

    metrics = QualityMetrics()

    # Evaluate a single response
    result = metrics.evaluate_response(
        response="Paris is the capital of France.",
        expected_contains=["Paris"],
        actual_citations=["wiki_france.md"],
        expected_citation_count=1,
        confidence=0.95,
        is_correct=True
    )

    # Get aggregated metrics
    summary = metrics.get_summary()
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


from collections import defaultdict


@dataclass
class EvaluationResult:
    """Result of evaluating a single response."""

    example_id: str
    category: str

    # Citation metrics
    citation_precision: float  # Relevant citations / Total citations
    citation_recall: float  # Found citations / Expected citations
    citation_f1: float  # Harmonic mean of precision and recall

    # Relevance metrics
    answer_relevance: float  # 0-1 score for answer quality
    contains_expected: bool  # Whether answer contains expected terms

    # Confidence metrics
    confidence: float  # Model's stated confidence
    is_correct: bool  # Whether answer was correct
    brier_score: float  # (confidence - correct)^2

    # Overall
    quality_score: float  # Weighted combination

    # Fields with defaults must come after required fields
    novelty_score: float = 0.0  # How novel/unique this response is (0-1)
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "example_id": self.example_id,
            "category": self.category,
            "citation_precision": self.citation_precision,
            "citation_recall": self.citation_recall,
            "citation_f1": self.citation_f1,
            "answer_relevance": self.answer_relevance,
            "contains_expected": self.contains_expected,
            "confidence": self.confidence,
            "is_correct": self.is_correct,
            "brier_score": self.brier_score,
            "novelty_score": self.novelty_score,
            "quality_score": self.quality_score,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class MetricsSummary:
    """Aggregated metrics summary."""

    total_examples: int

    # Citation metrics
    avg_citation_precision: float
    avg_citation_recall: float
    avg_citation_f1: float

    # Relevance metrics
    avg_answer_relevance: float
    contains_expected_rate: float

    # Confidence calibration
    avg_brier_score: float
    calibration_error: float  # Expected Calibration Error

    # Overall
    avg_quality_score: float

    # By category
    by_category: Dict[str, Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_examples": self.total_examples,
            "avg_citation_precision": self.avg_citation_precision,
            "avg_citation_recall": self.avg_citation_recall,
            "avg_citation_f1": self.avg_citation_f1,
            "avg_answer_relevance": self.avg_answer_relevance,
            "contains_expected_rate": self.contains_expected_rate,
            "avg_brier_score": self.avg_brier_score,
            "calibration_error": self.calibration_error,
            "avg_quality_score": self.avg_quality_score,
            "by_category": self.by_category,
        }


class QualityMetrics:
    """Quality metrics calculator for expert responses.

    Tracks and aggregates quality metrics across multiple evaluations.

    Attributes:
        results: List of evaluation results
        weights: Weights for combining metrics into quality score
    """

    DEFAULT_WEIGHTS = {"citation_accuracy": 0.3, "answer_relevance": 0.4, "confidence_calibration": 0.3}

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize quality metrics.

        Args:
            weights: Optional custom weights for metric combination
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.results: List[EvaluationResult] = []

        # For calibration binning
        self._calibration_bins: Dict[int, List[Tuple[float, bool]]] = defaultdict(list)

    def evaluate_response(
        self,
        example_id: str,
        category: str,
        response: str,
        expected_contains: List[str],
        actual_citations: List[str],
        expected_citation_count: int,
        confidence: float,
        is_correct: bool,
        relevant_citations: Optional[List[str]] = None,
    ) -> EvaluationResult:
        """Evaluate a single response.

        Args:
            example_id: ID of the evaluation example
            category: Category of the example
            response: The actual response text
            expected_contains: Terms expected in the response
            actual_citations: Citations provided in response
            expected_citation_count: Expected number of citations
            confidence: Model's stated confidence (0-1)
            is_correct: Whether the answer was correct
            relevant_citations: Optional list of relevant citations (for precision)

        Returns:
            EvaluationResult with all metrics
        """
        # Citation metrics
        citation_precision, citation_recall, citation_f1 = self._calculate_citation_metrics(
            actual_citations=actual_citations,
            expected_count=expected_citation_count,
            relevant_citations=relevant_citations,
        )

        # Answer relevance
        answer_relevance, contains_expected = self._calculate_relevance(
            response=response, expected_contains=expected_contains
        )

        # Confidence calibration (Brier score)
        brier_score = self._calculate_brier_score(confidence, is_correct)

        # Track for calibration error calculation
        bin_idx = int(confidence * 10)  # 10 bins
        self._calibration_bins[bin_idx].append((confidence, is_correct))

        # Overall quality score
        quality_score = self._calculate_quality_score(
            citation_f1=citation_f1, answer_relevance=answer_relevance, brier_score=brier_score
        )

        result = EvaluationResult(
            example_id=example_id,
            category=category,
            citation_precision=citation_precision,
            citation_recall=citation_recall,
            citation_f1=citation_f1,
            answer_relevance=answer_relevance,
            contains_expected=contains_expected,
            confidence=confidence,
            is_correct=is_correct,
            brier_score=brier_score,
            quality_score=quality_score,
        )

        self.results.append(result)
        return result

    def _calculate_citation_metrics(
        self, actual_citations: List[str], expected_count: int, relevant_citations: Optional[List[str]] = None
    ) -> Tuple[float, float, float]:
        """Calculate citation precision, recall, and F1.

        Args:
            actual_citations: Citations in the response
            expected_count: Expected number of citations
            relevant_citations: Optional list of relevant citations

        Returns:
            Tuple of (precision, recall, f1)
        """
        if not actual_citations:
            if expected_count == 0:
                return 1.0, 1.0, 1.0  # No citations expected, none provided
            return 0.0, 0.0, 0.0

        # Precision: relevant / total provided
        if relevant_citations is not None:
            relevant_count = len(set(actual_citations) & set(relevant_citations))
            precision = relevant_count / len(actual_citations)
        else:
            # Assume all provided citations are relevant if not specified
            precision = 1.0

        # Recall: provided / expected
        if expected_count > 0:
            recall = min(len(actual_citations) / expected_count, 1.0)
        else:
            recall = 1.0 if not actual_citations else 0.0

        # F1
        if precision + recall > 0:
            f1 = 2 * (precision * recall) / (precision + recall)
        else:
            f1 = 0.0

        return precision, recall, f1

    def _calculate_relevance(self, response: str, expected_contains: List[str]) -> Tuple[float, bool]:
        """Calculate answer relevance.

        Args:
            response: The response text
            expected_contains: Terms expected in response

        Returns:
            Tuple of (relevance_score, contains_all_expected)
        """
        if not expected_contains:
            return 1.0, True

        response_lower = response.lower()
        found = sum(1 for term in expected_contains if term.lower() in response_lower)

        relevance = found / len(expected_contains)
        contains_all = found == len(expected_contains)

        return relevance, contains_all

    def _calculate_brier_score(self, confidence: float, is_correct: bool) -> float:
        """Calculate Brier score for confidence calibration.

        Brier score = (confidence - actual)^2
        Lower is better (0 = perfect calibration)

        Args:
            confidence: Stated confidence (0-1)
            is_correct: Whether answer was correct

        Returns:
            Brier score
        """
        actual = 1.0 if is_correct else 0.0
        return (confidence - actual) ** 2

    def _calculate_quality_score(self, citation_f1: float, answer_relevance: float, brier_score: float) -> float:
        """Calculate overall quality score.

        Args:
            citation_f1: Citation F1 score
            answer_relevance: Answer relevance score
            brier_score: Brier score (lower is better)

        Returns:
            Weighted quality score (0-1)
        """
        # Convert Brier score to a "goodness" score (1 - brier)
        calibration_score = 1.0 - brier_score

        score = (
            self.weights["citation_accuracy"] * citation_f1
            + self.weights["answer_relevance"] * answer_relevance
            + self.weights["confidence_calibration"] * calibration_score
        )

        return score

    def _calculate_expected_calibration_error(self) -> float:
        """Calculate Expected Calibration Error (ECE).

        ECE measures how well confidence scores match actual accuracy.

        Returns:
            ECE score (lower is better)
        """
        if not self._calibration_bins:
            return 0.0

        total_samples = sum(len(samples) for samples in self._calibration_bins.values())
        if total_samples == 0:
            return 0.0

        ece = 0.0
        for bin_idx, samples in self._calibration_bins.items():
            if not samples:
                continue

            # Average confidence in bin
            avg_confidence = sum(conf for conf, _ in samples) / len(samples)

            # Accuracy in bin
            accuracy = sum(1 for _, correct in samples if correct) / len(samples)

            # Weighted absolute difference
            weight = len(samples) / total_samples
            ece += weight * abs(avg_confidence - accuracy)

        return ece

    def get_summary(self) -> MetricsSummary:
        """Get aggregated metrics summary.

        Returns:
            MetricsSummary with all aggregated metrics
        """
        if not self.results:
            return MetricsSummary(
                total_examples=0,
                avg_citation_precision=0.0,
                avg_citation_recall=0.0,
                avg_citation_f1=0.0,
                avg_answer_relevance=0.0,
                contains_expected_rate=0.0,
                avg_brier_score=0.0,
                calibration_error=0.0,
                avg_quality_score=0.0,
                by_category={},
            )

        n = len(self.results)

        # Aggregate metrics
        avg_citation_precision = sum(r.citation_precision for r in self.results) / n
        avg_citation_recall = sum(r.citation_recall for r in self.results) / n
        avg_citation_f1 = sum(r.citation_f1 for r in self.results) / n
        avg_answer_relevance = sum(r.answer_relevance for r in self.results) / n
        contains_expected_rate = sum(1 for r in self.results if r.contains_expected) / n
        avg_brier_score = sum(r.brier_score for r in self.results) / n
        avg_quality_score = sum(r.quality_score for r in self.results) / n

        # Calculate ECE
        calibration_error = self._calculate_expected_calibration_error()

        # By category
        by_category: Dict[str, Dict[str, float]] = {}
        categories = set(r.category for r in self.results)

        for category in categories:
            cat_results = [r for r in self.results if r.category == category]
            cat_n = len(cat_results)

            by_category[category] = {
                "count": cat_n,
                "avg_citation_f1": sum(r.citation_f1 for r in cat_results) / cat_n,
                "avg_answer_relevance": sum(r.answer_relevance for r in cat_results) / cat_n,
                "avg_brier_score": sum(r.brier_score for r in cat_results) / cat_n,
                "avg_quality_score": sum(r.quality_score for r in cat_results) / cat_n,
            }

        return MetricsSummary(
            total_examples=n,
            avg_citation_precision=avg_citation_precision,
            avg_citation_recall=avg_citation_recall,
            avg_citation_f1=avg_citation_f1,
            avg_answer_relevance=avg_answer_relevance,
            contains_expected_rate=contains_expected_rate,
            avg_brier_score=avg_brier_score,
            calibration_error=calibration_error,
            avg_quality_score=avg_quality_score,
            by_category=by_category,
        )

    def reset(self):
        """Reset all tracked metrics."""
        self.results.clear()
        self._calibration_bins.clear()
