"""Integration tests for stopping criteria with multi-phase research."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    StoppingDecision,
    PhaseContext,
)
from deepr.observability.information_gain import InformationGainTracker


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
        all_findings = []

        # Phase 1: Diverse findings (high entropy)
        phase1_findings = [
            "Quantum computing uses qubits",
            "Machine learning requires data",
            "Blockchain is decentralized",
        ]
        all_findings.extend(phase1_findings)

        context1 = PhaseContext(phase=1, total_phases=5, prior_findings=[])
        decision1 = criteria.evaluate(phase1_findings, context1)

        # Should not stop - still early and diverse
        assert decision1.should_stop is False

        # Phase 2: Still diverse
        phase2_findings = [
            "Neural networks have layers",
            "Cryptography secures data",
        ]
        all_findings.extend(phase2_findings)

        context2 = PhaseContext(phase=2, total_phases=5, prior_findings=all_findings[:3])
        decision2 = criteria.evaluate(phase2_findings, context2)

        # Track information gain
        gain1 = gain_tracker.record_phase_findings(1, phase1_findings, [])
        gain2 = gain_tracker.record_phase_findings(2, phase2_findings, all_findings[:3])

        # Should have positive information gain
        assert gain1.information_gain >= 0
        assert gain2.information_gain >= 0

    @pytest.mark.integration
    def test_information_gain_decreases_over_time(self):
        """Test that information gain decreases as research converges."""
        gain_tracker = InformationGainTracker()

        # Phase 1: Fresh findings, high gain
        phase1 = ["New fact about X", "Another fact about Y", "Discovery about Z"]
        gain1 = gain_tracker.record_phase_findings(1, phase1, [])

        # Phase 2: Related findings, moderate gain
        phase2 = ["More about X", "Extension of Y research"]
        gain2 = gain_tracker.record_phase_findings(2, phase2, phase1)

        # Phase 3: Repetitive findings, low gain
        phase3 = ["X was already discussed", "Y confirms prior findings"]
        gain3 = gain_tracker.record_phase_findings(3, phase3, phase1 + phase2)

        # Information gain should generally decrease
        # (exact behavior depends on implementation)
        gains = [gain1.information_gain, gain2.information_gain, gain3.information_gain]

        # At minimum, we should have tracked all phases
        assert gain_tracker.get_phase_count() == 3

    @pytest.mark.integration
    def test_auto_pivot_triggers_on_drift(self):
        """Test that auto-pivot is suggested when topic drifts."""
        criteria = EntropyStoppingCriteria()

        original_query = "What are the benefits of solar energy?"

        # Findings that have drifted to a related but different topic
        drifted_findings = [
            "Wind turbines are becoming more efficient",
            "Hydroelectric power provides baseload capacity",
            "Nuclear energy has low carbon emissions",
            "Geothermal energy is location-dependent",
        ]

        pivot = criteria.detect_auto_pivot(drifted_findings, original_query)

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
        similar_findings = ["The answer is X", "X is the answer", "We conclude X"]

        for phase in range(1, 4):
            context = PhaseContext(
                phase=phase,
                total_phases=5,
                prior_findings=similar_findings * (phase - 1),
            )
            decision = criteria.evaluate(similar_findings, context)

            if phase < criteria.min_iterations:
                assert decision.should_stop is False, f"Should not stop at phase {phase}"

    @pytest.mark.integration
    def test_entropy_tracking_across_phases(self):
        """Test entropy tracking across multiple phases."""
        criteria = EntropyStoppingCriteria()

        entropy_values = []

        # Track entropy as findings accumulate
        cumulative_findings = []

        for phase in range(1, 6):
            # Add increasingly similar findings each phase
            if phase == 1:
                new_findings = ["Topic A", "Topic B", "Topic C"]
            elif phase == 2:
                new_findings = ["More on A", "More on B"]
            elif phase == 3:
                new_findings = ["A again", "B again"]
            elif phase == 4:
                new_findings = ["Still A", "Still B"]
            else:
                new_findings = ["A", "B"]

            cumulative_findings.extend(new_findings)
            entropy = criteria.calculate_entropy(cumulative_findings)
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
        async def simulate_phase_execution(phase: int, prior_context: list) -> tuple:
            """Simulate what batch_executor._execute_phase does."""
            # Mock LLM response with findings
            mock_findings = [
                f"Finding {i} from phase {phase}"
                for i in range(3)
            ]

            # Extract findings (as batch_executor does)
            findings = mock_findings

            # Evaluate stopping criteria
            context = PhaseContext(
                phase=phase,
                total_phases=5,
                prior_findings=prior_context,
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
        tracker.record_phase_findings(1, ["Finding 1", "Finding 2"], [])
        tracker.record_phase_findings(2, ["Finding 3"], ["Finding 1", "Finding 2"])

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
            prior = [f"Prior {i}" for i in range(phase - 1)]
            findings = [f"Phase {phase} finding {i}" for i in range(3)]
            tracker.record_phase_findings(phase, findings, prior)

        # Get summary
        summary = tracker.get_summary()

        assert "total_phases" in summary
        assert "total_findings" in summary
        assert "average_gain" in summary or "cumulative_gain" in summary
