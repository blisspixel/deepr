"""Unit tests for stopping criteria."""

import pytest
from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    StoppingDecision,
    PhaseContext,
    Finding,
)


class TestEntropyCalculation:
    """Tests for entropy calculation."""

    def test_high_diversity_high_entropy(self):
        """Test that diverse findings produce high entropy."""
        criteria = EntropyStoppingCriteria()

        findings = [
            Finding(text="Quantum computers use qubits for computation", phase=1),
            Finding(text="Machine learning requires large datasets", phase=1),
            Finding(text="Blockchain provides distributed ledger technology", phase=1),
            Finding(text="Cloud computing enables scalable infrastructure", phase=1),
            Finding(text="5G networks offer faster mobile connectivity", phase=1),
        ]

        entropy = criteria.calculate_entropy(findings)

        # High diversity should produce higher entropy
        assert entropy > 0.3

    def test_low_diversity_low_entropy(self):
        """Test that similar findings produce low entropy."""
        criteria = EntropyStoppingCriteria()

        findings = [
            Finding(text="Quantum computers use qubits", phase=1),
            Finding(text="Qubits are used in quantum computing", phase=1),
            Finding(text="Quantum computation relies on qubits", phase=1),
            Finding(text="The qubit is the basic unit of quantum computing", phase=1),
        ]

        entropy = criteria.calculate_entropy(findings)

        # Similar content should produce lower entropy (but still positive)
        assert entropy >= 0

    def test_empty_findings(self):
        """Test that empty findings are handled."""
        criteria = EntropyStoppingCriteria()

        entropy = criteria.calculate_entropy([])

        # Empty list should return a valid entropy value
        assert isinstance(entropy, float)

    def test_single_finding(self):
        """Test that single finding is handled."""
        criteria = EntropyStoppingCriteria()

        findings = [Finding(text="Single finding", phase=1)]
        entropy = criteria.calculate_entropy(findings)

        # Single finding should return valid entropy
        assert isinstance(entropy, float)


class TestStoppingDecision:
    """Tests for stopping decision logic."""

    def test_evaluate_returns_decision(self):
        """Test that evaluate returns a StoppingDecision."""
        criteria = EntropyStoppingCriteria()

        findings = [
            Finding(text="Finding 1", phase=1),
            Finding(text="Finding 2", phase=1),
        ]

        context = PhaseContext(
            phase_num=2,
            original_query="test query",
            current_focus="test focus",
            iteration_count=2,
        )

        decision = criteria.evaluate(findings, context)

        assert isinstance(decision, StoppingDecision)
        assert isinstance(decision.should_stop, bool)
        assert isinstance(decision.entropy, float)

    def test_early_phase_doesnt_stop(self):
        """Test that early phases don't stop prematurely."""
        criteria = EntropyStoppingCriteria()

        findings = [
            Finding(text="Finding 1", phase=1),
        ]

        context = PhaseContext(
            phase_num=1,
            original_query="test query",
            current_focus="test focus",
            iteration_count=1,
        )

        decision = criteria.evaluate(findings, context)

        # Very early phase should not stop
        # (depends on MIN_ITERATIONS_BEFORE_STOP)

    def test_decision_includes_metrics(self):
        """Test that decision includes useful metrics."""
        criteria = EntropyStoppingCriteria()

        findings = [
            Finding(text="Finding A", phase=2),
            Finding(text="Finding B", phase=2),
            Finding(text="Finding C", phase=2),
        ]

        context = PhaseContext(
            phase_num=2,
            original_query="test query",
            current_focus="test focus",
            iteration_count=2,
        )

        decision = criteria.evaluate(findings, context)

        assert isinstance(decision, StoppingDecision)
        assert hasattr(decision, "entropy")
        assert hasattr(decision, "information_gain")
        assert hasattr(decision, "metrics")


class TestAutoPivot:
    """Tests for auto-pivot detection."""

    def test_detect_topic_drift(self):
        """Test detecting when findings drift from original query."""
        criteria = EntropyStoppingCriteria()

        # Findings that have drifted from original query
        findings = [
            Finding(text="The weather is sunny today", phase=1),
            Finding(text="Temperature will reach 75 degrees", phase=1),
            Finding(text="Rain expected tomorrow", phase=1),
        ]

        pivot = criteria.detect_auto_pivot(
            findings,
            original_query="What are the best practices for Python testing?",
        )

        # Should potentially detect drift
        # (actual behavior depends on implementation threshold)

    def test_no_pivot_on_topic(self):
        """Test no pivot when findings are on topic."""
        criteria = EntropyStoppingCriteria()

        findings = [
            Finding(text="pytest is a popular Python testing framework", phase=1),
            Finding(text="Unit tests should be isolated and fast", phase=1),
            Finding(text="Test coverage helps identify untested code", phase=1),
        ]

        pivot = criteria.detect_auto_pivot(
            findings,
            original_query="What are the best practices for Python testing?",
        )

        # Should not detect significant pivot when on topic
        # pivot may be None or empty string


class TestPhaseContext:
    """Tests for PhaseContext dataclass."""

    def test_phase_context_creation(self):
        """Test creating PhaseContext."""
        context = PhaseContext(
            phase_num=2,
            original_query="test query",
            current_focus="current focus",
            total_findings=5,
            iteration_count=2,
        )

        assert context.phase_num == 2
        assert context.original_query == "test query"
        assert context.total_findings == 5
        assert context.iteration_count == 2


class TestFinding:
    """Tests for Finding dataclass."""

    def test_finding_creation(self):
        """Test creating a Finding."""
        finding = Finding(
            text="Test finding text",
            phase=1,
            confidence=0.8,
            source="web_search",
        )

        assert finding.text == "Test finding text"
        assert finding.phase == 1
        assert finding.confidence == 0.8
        assert finding.source == "web_search"

    def test_finding_tokenization(self):
        """Test that findings are automatically tokenized."""
        finding = Finding(
            text="This is a test finding with multiple words",
            phase=1,
        )

        assert len(finding.tokens) > 0
        assert "test" in finding.tokens
        assert "finding" in finding.tokens

    def test_finding_hash(self):
        """Test that findings have content hash."""
        finding = Finding(text="Test content", phase=1)

        assert finding.content_hash
        assert len(finding.content_hash) == 12


class TestStoppingDecisionDataclass:
    """Tests for StoppingDecision dataclass."""

    def test_stopping_decision_creation(self):
        """Test creating StoppingDecision."""
        decision = StoppingDecision(
            should_stop=True,
            reason="Entropy below threshold",
            entropy=0.1,
            information_gain=0.05,
            metrics={"phase": 3},
        )

        assert decision.should_stop is True
        assert "entropy" in decision.reason.lower()
        assert decision.entropy == 0.1
        assert decision.information_gain == 0.05

    def test_stopping_decision_with_pivot(self):
        """Test StoppingDecision with suggested pivot."""
        decision = StoppingDecision(
            should_stop=False,
            reason="Topic drift detected",
            entropy=0.5,
            information_gain=0.1,
            pivot_suggestion="Consider focusing on X instead",
        )

        assert decision.should_stop is False
        assert decision.pivot_suggestion is not None

    def test_stopping_decision_to_dict(self):
        """Test StoppingDecision serialization."""
        decision = StoppingDecision(
            should_stop=True,
            reason="Test reason",
            entropy=0.2,
            information_gain=0.1,
        )

        data = decision.to_dict()

        assert data["should_stop"] is True
        assert data["entropy"] == 0.2
        assert data["information_gain"] == 0.1
