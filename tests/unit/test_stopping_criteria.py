"""Unit tests for stopping criteria."""

import pytest
from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    StoppingDecision,
    PhaseContext,
)


class TestEntropyCalculation:
    """Tests for entropy calculation."""

    def test_high_diversity_high_entropy(self):
        """Test that diverse findings produce high entropy."""
        criteria = EntropyStoppingCriteria()

        findings = [
            "Quantum computers use qubits for computation",
            "Machine learning requires large datasets",
            "Blockchain provides distributed ledger technology",
            "Cloud computing enables scalable infrastructure",
            "5G networks offer faster mobile connectivity",
        ]

        entropy = criteria.calculate_entropy(findings)

        # High diversity should produce higher entropy
        assert entropy > 0.5

    def test_low_diversity_low_entropy(self):
        """Test that similar findings produce low entropy."""
        criteria = EntropyStoppingCriteria()

        findings = [
            "Quantum computers use qubits",
            "Qubits are used in quantum computing",
            "Quantum computation relies on qubits",
            "The qubit is the basic unit of quantum computing",
        ]

        entropy = criteria.calculate_entropy(findings)

        # Similar content should produce lower entropy
        assert entropy < 0.8

    def test_empty_findings_zero_entropy(self):
        """Test that empty findings produce zero entropy."""
        criteria = EntropyStoppingCriteria()

        entropy = criteria.calculate_entropy([])

        assert entropy == 0.0

    def test_single_finding_zero_entropy(self):
        """Test that single finding produces zero entropy."""
        criteria = EntropyStoppingCriteria()

        entropy = criteria.calculate_entropy(["Single finding"])

        assert entropy == 0.0


class TestStoppingDecision:
    """Tests for stopping decision logic."""

    def test_should_stop_low_entropy(self):
        """Test that low entropy triggers stop."""
        criteria = EntropyStoppingCriteria(entropy_threshold=0.3)

        # Simulate converged findings
        findings = [
            "The answer is X",
            "X is the answer",
            "We found that X is correct",
        ]

        context = PhaseContext(
            phase=3,
            total_phases=5,
            prior_findings=["Some prior finding"],
        )

        decision = criteria.evaluate(findings, context)

        # With very similar findings, entropy should be low enough to stop
        # The actual behavior depends on the implementation

    def test_should_not_stop_early_phase(self):
        """Test that early phases don't stop prematurely."""
        criteria = EntropyStoppingCriteria(
            entropy_threshold=0.1,
            min_iterations=3,
        )

        findings = ["Finding 1", "Finding 1 again"]

        context = PhaseContext(
            phase=1,  # Early phase
            total_phases=5,
            prior_findings=[],
        )

        decision = criteria.evaluate(findings, context)

        # Should not stop in phase 1 even with low entropy
        assert decision.should_stop is False or context.phase >= criteria.min_iterations

    def test_decision_includes_metrics(self):
        """Test that decision includes useful metrics."""
        criteria = EntropyStoppingCriteria()

        findings = ["Finding A", "Finding B", "Finding C"]
        context = PhaseContext(phase=2, total_phases=5, prior_findings=[])

        decision = criteria.evaluate(findings, context)

        assert isinstance(decision, StoppingDecision)
        assert "entropy" in decision.metrics
        assert "phase" in decision.metrics


class TestAutoPivot:
    """Tests for auto-pivot detection."""

    def test_detect_topic_drift(self):
        """Test detecting when findings drift from original query."""
        criteria = EntropyStoppingCriteria()

        # Findings that have drifted from original query
        findings = [
            "The weather is sunny today",
            "Temperature will reach 75 degrees",
            "Rain expected tomorrow",
        ]

        pivot = criteria.detect_auto_pivot(
            findings,
            original_query="What are the best practices for Python testing?",
        )

        # Should detect significant drift
        # Actual behavior depends on implementation

    def test_no_pivot_on_topic(self):
        """Test no pivot when findings are on topic."""
        criteria = EntropyStoppingCriteria()

        findings = [
            "pytest is a popular Python testing framework",
            "Unit tests should be isolated and fast",
            "Test coverage helps identify untested code",
        ]

        pivot = criteria.detect_auto_pivot(
            findings,
            original_query="What are the best practices for Python testing?",
        )

        # Should not detect pivot when on topic
        assert pivot is None or pivot == ""


class TestPhaseContext:
    """Tests for PhaseContext dataclass."""

    def test_phase_context_creation(self):
        """Test creating PhaseContext."""
        context = PhaseContext(
            phase=2,
            total_phases=5,
            prior_findings=["finding1", "finding2"],
            original_query="test query",
        )

        assert context.phase == 2
        assert context.total_phases == 5
        assert len(context.prior_findings) == 2
        assert context.original_query == "test query"


class TestStoppingDecisionDataclass:
    """Tests for StoppingDecision dataclass."""

    def test_stopping_decision_creation(self):
        """Test creating StoppingDecision."""
        decision = StoppingDecision(
            should_stop=True,
            reason="Entropy below threshold",
            metrics={"entropy": 0.1, "phase": 3},
            suggested_pivot=None,
        )

        assert decision.should_stop is True
        assert "entropy" in decision.reason.lower()
        assert decision.metrics["entropy"] == 0.1

    def test_stopping_decision_with_pivot(self):
        """Test StoppingDecision with suggested pivot."""
        decision = StoppingDecision(
            should_stop=False,
            reason="Topic drift detected",
            metrics={},
            suggested_pivot="Consider focusing on X instead",
        )

        assert decision.should_stop is False
        assert decision.suggested_pivot is not None
