"""Tests for the quality metrics module.

Tests the QualityMetrics, EvaluationResult, and MetricsSummary classes
for measuring expert response quality.
"""

import pytest
from datetime import datetime

from deepr.observability.quality_metrics import (
    QualityMetrics,
    EvaluationResult,
    MetricsSummary
)


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""
    
    def test_create_evaluation_result(self):
        """Test creating an evaluation result."""
        result = EvaluationResult(
            example_id="test_001",
            category="simple_factual",
            citation_precision=1.0,
            citation_recall=0.8,
            citation_f1=0.89,
            answer_relevance=0.95,
            contains_expected=True,
            confidence=0.9,
            is_correct=True,
            brier_score=0.01,
            quality_score=0.92
        )
        
        assert result.example_id == "test_001"
        assert result.category == "simple_factual"
        assert result.citation_precision == 1.0
        assert result.is_correct is True
    
    def test_evaluation_result_to_dict(self):
        """Test serialization of evaluation result."""
        result = EvaluationResult(
            example_id="test_001",
            category="simple_factual",
            citation_precision=1.0,
            citation_recall=0.8,
            citation_f1=0.89,
            answer_relevance=0.95,
            contains_expected=True,
            confidence=0.9,
            is_correct=True,
            brier_score=0.01,
            quality_score=0.92
        )
        
        d = result.to_dict()
        
        assert d["example_id"] == "test_001"
        assert d["category"] == "simple_factual"
        assert "timestamp" in d


class TestQualityMetrics:
    """Tests for QualityMetrics class."""
    
    def test_evaluate_response_basic(self):
        """Test basic response evaluation."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_001",
            category="simple_factual",
            response="Paris is the capital of France.",
            expected_contains=["Paris", "France"],
            actual_citations=["wiki_france.md"],
            expected_citation_count=1,
            confidence=0.95,
            is_correct=True
        )
        
        assert result.example_id == "test_001"
        assert result.contains_expected is True
        assert result.answer_relevance == 1.0
        assert result.citation_recall == 1.0
    
    def test_evaluate_response_missing_terms(self):
        """Test evaluation when expected terms are missing."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_002",
            category="simple_factual",
            response="The capital is a major city.",
            expected_contains=["Paris", "France"],
            actual_citations=["wiki.md"],
            expected_citation_count=1,
            confidence=0.8,
            is_correct=False
        )
        
        assert result.contains_expected is False
        assert result.answer_relevance == 0.0
    
    def test_evaluate_response_partial_terms(self):
        """Test evaluation with partial expected terms."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_003",
            category="simple_factual",
            response="Paris is a beautiful city.",
            expected_contains=["Paris", "France", "capital"],
            actual_citations=["wiki.md"],
            expected_citation_count=1,
            confidence=0.7,
            is_correct=False
        )
        
        assert result.contains_expected is False
        # Only 1 of 3 terms found
        assert result.answer_relevance == pytest.approx(1/3, rel=0.01)
    
    def test_citation_metrics_no_citations(self):
        """Test citation metrics when no citations provided."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_004",
            category="simple_factual",
            response="Some answer",
            expected_contains=["answer"],
            actual_citations=[],
            expected_citation_count=2,
            confidence=0.5,
            is_correct=False
        )
        
        assert result.citation_precision == 0.0
        assert result.citation_recall == 0.0
        assert result.citation_f1 == 0.0
    
    def test_citation_metrics_no_expected(self):
        """Test citation metrics when no citations expected."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_005",
            category="simple_factual",
            response="Some answer",
            expected_contains=["answer"],
            actual_citations=[],
            expected_citation_count=0,
            confidence=0.9,
            is_correct=True
        )
        
        # No citations expected, none provided = perfect
        assert result.citation_precision == 1.0
        assert result.citation_recall == 1.0
        assert result.citation_f1 == 1.0
    
    def test_citation_metrics_with_relevant_citations(self):
        """Test citation metrics with relevant citations specified."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_006",
            category="simple_factual",
            response="Some answer",
            expected_contains=["answer"],
            actual_citations=["doc1.md", "doc2.md", "doc3.md"],
            expected_citation_count=2,
            confidence=0.8,
            is_correct=True,
            relevant_citations=["doc1.md", "doc2.md"]  # Only 2 of 3 are relevant
        )
        
        # Precision: 2 relevant / 3 provided = 0.67
        assert result.citation_precision == pytest.approx(2/3, rel=0.01)
        # Recall: 3 provided / 2 expected = 1.0 (capped)
        assert result.citation_recall == 1.0
    
    def test_brier_score_correct_high_confidence(self):
        """Test Brier score for correct answer with high confidence."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_007",
            category="simple_factual",
            response="Correct answer",
            expected_contains=["Correct"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.95,
            is_correct=True
        )
        
        # Brier = (0.95 - 1.0)^2 = 0.0025
        assert result.brier_score == pytest.approx(0.0025, rel=0.01)
    
    def test_brier_score_incorrect_high_confidence(self):
        """Test Brier score for incorrect answer with high confidence."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_008",
            category="simple_factual",
            response="Wrong answer",
            expected_contains=["Correct"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.95,
            is_correct=False
        )
        
        # Brier = (0.95 - 0.0)^2 = 0.9025
        assert result.brier_score == pytest.approx(0.9025, rel=0.01)
    
    def test_get_summary_empty(self):
        """Test getting summary with no evaluations."""
        metrics = QualityMetrics()
        
        summary = metrics.get_summary()
        
        assert summary.total_examples == 0
        assert summary.avg_citation_precision == 0.0
        assert summary.by_category == {}
    
    def test_get_summary_with_evaluations(self):
        """Test getting summary with multiple evaluations."""
        metrics = QualityMetrics()
        
        # Add several evaluations
        metrics.evaluate_response(
            example_id="test_001",
            category="factual",
            response="Paris is the capital of France.",
            expected_contains=["Paris"],
            actual_citations=["wiki.md"],
            expected_citation_count=1,
            confidence=0.9,
            is_correct=True
        )
        
        metrics.evaluate_response(
            example_id="test_002",
            category="factual",
            response="Berlin is the capital of Germany.",
            expected_contains=["Berlin"],
            actual_citations=["wiki.md"],
            expected_citation_count=1,
            confidence=0.85,
            is_correct=True
        )
        
        metrics.evaluate_response(
            example_id="test_003",
            category="reasoning",
            response="The answer is 42.",
            expected_contains=["42"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.7,
            is_correct=True
        )
        
        summary = metrics.get_summary()
        
        assert summary.total_examples == 3
        assert "factual" in summary.by_category
        assert "reasoning" in summary.by_category
        assert summary.by_category["factual"]["count"] == 2
        assert summary.by_category["reasoning"]["count"] == 1
    
    def test_expected_calibration_error(self):
        """Test ECE calculation."""
        metrics = QualityMetrics()
        
        # Add well-calibrated examples
        # High confidence, correct
        for _ in range(8):
            metrics.evaluate_response(
                example_id=f"high_correct_{_}",
                category="test",
                response="answer",
                expected_contains=["answer"],
                actual_citations=["doc.md"],
                expected_citation_count=1,
                confidence=0.9,
                is_correct=True
            )
        
        # High confidence, incorrect (2 out of 10 = 20% error)
        for _ in range(2):
            metrics.evaluate_response(
                example_id=f"high_incorrect_{_}",
                category="test",
                response="answer",
                expected_contains=["answer"],
                actual_citations=["doc.md"],
                expected_citation_count=1,
                confidence=0.9,
                is_correct=False
            )
        
        summary = metrics.get_summary()
        
        # ECE should reflect the miscalibration
        # 90% confidence but only 80% accuracy = 10% error
        assert summary.calibration_error > 0
    
    def test_reset(self):
        """Test resetting metrics."""
        metrics = QualityMetrics()
        
        metrics.evaluate_response(
            example_id="test_001",
            category="test",
            response="answer",
            expected_contains=["answer"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.9,
            is_correct=True
        )
        
        assert len(metrics.results) == 1
        
        metrics.reset()
        
        assert len(metrics.results) == 0
        summary = metrics.get_summary()
        assert summary.total_examples == 0
    
    def test_custom_weights(self):
        """Test using custom weights for quality score."""
        custom_weights = {
            "citation_accuracy": 0.5,
            "answer_relevance": 0.3,
            "confidence_calibration": 0.2
        }
        
        metrics = QualityMetrics(weights=custom_weights)
        
        result = metrics.evaluate_response(
            example_id="test_001",
            category="test",
            response="answer",
            expected_contains=["answer"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.9,
            is_correct=True
        )
        
        # Quality score should use custom weights
        # With perfect scores, should still be close to 1.0
        assert result.quality_score > 0.9


class TestMetricsSummary:
    """Tests for MetricsSummary dataclass."""
    
    def test_metrics_summary_to_dict(self):
        """Test serialization of metrics summary."""
        summary = MetricsSummary(
            total_examples=10,
            avg_citation_precision=0.9,
            avg_citation_recall=0.85,
            avg_citation_f1=0.87,
            avg_answer_relevance=0.92,
            contains_expected_rate=0.8,
            avg_brier_score=0.05,
            calibration_error=0.08,
            avg_quality_score=0.88,
            by_category={"factual": {"count": 5, "avg_quality_score": 0.9}}
        )
        
        d = summary.to_dict()
        
        assert d["total_examples"] == 10
        assert d["avg_citation_precision"] == 0.9
        assert "by_category" in d
        assert d["by_category"]["factual"]["count"] == 5


class TestQualityMetricsEdgeCases:
    """Edge case tests for quality metrics."""
    
    def test_empty_expected_contains(self):
        """Test evaluation with empty expected_contains."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_001",
            category="test",
            response="Any response",
            expected_contains=[],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.9,
            is_correct=True
        )
        
        # No expected terms = perfect relevance
        assert result.answer_relevance == 1.0
        assert result.contains_expected is True
    
    def test_case_insensitive_matching(self):
        """Test that expected term matching is case-insensitive."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_001",
            category="test",
            response="PARIS is the capital",
            expected_contains=["paris"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.9,
            is_correct=True
        )
        
        assert result.contains_expected is True
        assert result.answer_relevance == 1.0
    
    def test_zero_confidence(self):
        """Test evaluation with zero confidence."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_001",
            category="test",
            response="answer",
            expected_contains=["answer"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=0.0,
            is_correct=True
        )
        
        # Brier = (0.0 - 1.0)^2 = 1.0
        assert result.brier_score == 1.0
    
    def test_perfect_confidence(self):
        """Test evaluation with perfect confidence."""
        metrics = QualityMetrics()
        
        result = metrics.evaluate_response(
            example_id="test_001",
            category="test",
            response="answer",
            expected_contains=["answer"],
            actual_citations=["doc.md"],
            expected_citation_count=1,
            confidence=1.0,
            is_correct=True
        )
        
        # Brier = (1.0 - 1.0)^2 = 0.0
        assert result.brier_score == 0.0
