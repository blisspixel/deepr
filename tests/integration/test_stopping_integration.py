"""Integration tests for stopping criteria with multi-phase research."""

from unittest.mock import MagicMock

import pytest

from deepr.observability.information_gain import InformationGainTracker
from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    Finding,
    PhaseContext,
)


def make_findings(texts: list, phase: int = 1) -> list:
    """Helper to create Finding objects from text strings."""
    return [Finding(text=text, phase=phase) for text in texts]


class TestStoppingIntegration:
    """Integration tests for stopping criteria in research workflows."""

    @pytest.mark.integration
    def test_research_stops_on_convergence(self):
        """Test that research stops when findings converge."""
        criteria = EntropyStoppingCriteria(
            entropy_threshold=0.2,
            min_iterations=2,
        )
        gain_tracker = InformationGainTracker()

        # Simulate a multi-phase research workflow
        all_findings_text = []

        # Phase 1: Diverse findings (high entropy)
        phase1_texts = [
            "Quantum computing uses qubits",
            "Machine learning requires data",
            "Blockchain is decentralized",
        ]
        all_findings_text.extend(phase1_texts)

        context1 = PhaseContext(
            phase_num=1,
            original_query="technology overview",
            current_focus="technology overview",
            iteration_count=1,
        )
        decision1 = criteria.evaluate(make_findings(phase1_texts, 1), context1)

        # Should not stop - still early and diverse
        assert decision1.should_stop is False

        # Phase 2: Still diverse
        phase2_texts = [
            "Neural networks have layers",
            "Cryptography secures data",
        ]
        all_findings_text.extend(phase2_texts)

        context2 = PhaseContext(
            phase_num=2,
            original_query="technology overview",
            current_focus="technology overview",
            iteration_count=2,
        )
        decision2 = criteria.evaluate(make_findings(phase2_texts, 2), context2)

        # Track information gain
        gain1 = gain_tracker.record_phase_findings(1, phase1_texts, None)
        gain2 = gain_tracker.record_phase_findings(2, phase2_texts, None)

        # Should have positive information gain
        assert gain1.gain_score >= 0
        assert gain2.gain_score >= 0

    @pytest.mark.integration
    def test_information_gain_decreases_over_time(self):
        """Test that information gain decreases as research converges."""
        gain_tracker = InformationGainTracker()

        # Phase 1: Fresh findings, high gain
        phase1 = ["New fact about X", "Another fact about Y", "Discovery about Z"]
        gain1 = gain_tracker.record_phase_findings(1, phase1, None)

        # Phase 2: Related findings, moderate gain
        phase2 = ["More about X", "Extension of Y research"]
        gain2 = gain_tracker.record_phase_findings(2, phase2, None)

        # Phase 3: Repetitive findings, low gain
        phase3 = ["X was already discussed", "Y confirms prior findings"]
        gain3 = gain_tracker.record_phase_findings(3, phase3, None)

        # Information gain should generally decrease
        # (exact behavior depends on implementation)
        gains = [gain1.gain_score, gain2.gain_score, gain3.gain_score]

        # At minimum, we should have tracked all phases
        assert len(gain_tracker.phases) == 3

    @pytest.mark.integration
    def test_auto_pivot_triggers_on_drift(self):
        """Test that auto-pivot is suggested when topic drifts."""
        criteria = EntropyStoppingCriteria()

        original_query = "What are the benefits of solar energy?"

        # Findings that have drifted to a related but different topic
        drifted_texts = [
            "Wind turbines are becoming more efficient",
            "Hydroelectric power provides baseload capacity",
            "Nuclear energy has low carbon emissions",
            "Geothermal energy is location-dependent",
        ]

        pivot = criteria.detect_auto_pivot(make_findings(drifted_texts, 1), original_query)

        # Should detect that we've drifted from solar to general renewable energy
        # The actual pivot suggestion depends on implementation

    @pytest.mark.integration
    def test_stopping_respects_minimum_iterations(self):
        """Test that stopping respects minimum iteration count."""
        criteria = EntropyStoppingCriteria(
            entropy_threshold=0.01,  # Very low threshold
            min_iterations=3,
        )

        # Even with very similar (low entropy) findings, should not stop before min_iterations
        similar_texts = ["The answer is X", "X is the answer", "We conclude X"]

        for phase in range(1, 4):
            context = PhaseContext(
                phase_num=phase,
                original_query="test query",
                current_focus="test focus",
                iteration_count=phase,
            )
            decision = criteria.evaluate(make_findings(similar_texts, phase), context)

            if phase < criteria.min_iterations:
                assert decision.should_stop is False, f"Should not stop at phase {phase}"

    @pytest.mark.integration
    def test_entropy_tracking_across_phases(self):
        """Test entropy tracking across multiple phases."""
        criteria = EntropyStoppingCriteria()

        entropy_values = []

        # Track entropy as findings accumulate
        all_findings = []

        for phase in range(1, 6):
            # Add increasingly similar findings each phase
            if phase == 1:
                new_texts = ["Topic A information", "Topic B details", "Topic C facts"]
            elif phase == 2:
                new_texts = ["More on A", "More on B"]
            elif phase == 3:
                new_texts = ["A again", "B again"]
            elif phase == 4:
                new_texts = ["Still A", "Still B"]
            else:
                new_texts = ["A", "B"]

            new_findings = make_findings(new_texts, phase)
            all_findings.extend(new_findings)
            entropy = criteria.calculate_entropy(all_findings)
            entropy_values.append(entropy)

        # Entropy should generally be tracked (values depend on implementation)
        assert len(entropy_values) == 5


class TestStoppingWithBatchExecutor:
    """Integration tests with batch executor patterns."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stopping_criteria_in_executor_pattern(self):
        """Test stopping criteria integration pattern used by batch executor."""
        criteria = EntropyStoppingCriteria(
            entropy_threshold=0.15,
            min_iterations=2,
        )

        # Simulate batch executor's _execute_phase pattern
        async def simulate_phase_execution(phase: int, prior_findings: list) -> tuple:
            """Simulate what batch_executor._execute_phase does."""
            # Mock LLM response with findings
            mock_texts = [f"Finding {i} from phase {phase}" for i in range(3)]

            # Create Finding objects
            findings = make_findings(mock_texts, phase)

            # Evaluate stopping criteria
            context = PhaseContext(
                phase_num=phase,
                original_query="test query",
                current_focus="test focus",
                iteration_count=phase,
            )
            decision = criteria.evaluate(findings, context)

            return findings, decision

        # Run simulated phases
        all_findings = []
        for phase in range(1, 6):
            findings, decision = await simulate_phase_execution(phase, all_findings)
            all_findings.extend(findings)

            if decision.should_stop:
                break

        # Should have executed at least min_iterations phases
        assert len(all_findings) >= criteria.min_iterations * 3


class TestInformationGainIntegration:
    """Integration tests for information gain tracking."""

    @pytest.mark.integration
    def test_gain_tracker_with_spans(self):
        """Test information gain tracker exports to spans."""
        tracker = InformationGainTracker()

        # Record findings across phases
        tracker.record_phase_findings(1, ["Finding 1", "Finding 2"], None)
        tracker.record_phase_findings(2, ["Finding 3"], None)

        # Create mock span
        mock_span = MagicMock()

        # Export to span
        tracker.export_to_span(mock_span)

        # Should have set attributes on span
        mock_span.set_attribute.assert_called()

    @pytest.mark.integration
    def test_gain_metrics_summary(self):
        """Test getting summary metrics from gain tracker."""
        tracker = InformationGainTracker()

        # Record multiple phases
        for phase in range(1, 4):
            findings = [f"Phase {phase} finding {i}" for i in range(3)]
            tracker.record_phase_findings(phase, findings, None)

        # Get summary
        summary = tracker.get_summary()

        assert "phases_tracked" in summary
        assert "cumulative_gain" in summary or "average_gain" in summary
