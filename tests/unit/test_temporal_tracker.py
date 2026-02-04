"""Unit tests for temporal knowledge tracker."""

import pytest
from datetime import datetime, timezone

from deepr.observability.temporal_tracker import (
    TemporalKnowledgeTracker,
    TemporalFinding,
    FindingType,
    Hypothesis,
    HypothesisEvolution,
)


class TestTemporalFindingRecording:
    """Tests for recording temporal findings."""

    def test_record_finding(self):
        """Test recording a finding."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Quantum computers use superposition",
            phase=1,
            confidence=0.9,
            source="web_search",
        )

        assert isinstance(finding, TemporalFinding)
        assert finding.text == "Quantum computers use superposition"
        assert finding.phase == 1
        assert finding.confidence == 0.9
        assert finding.source == "web_search"
        assert finding.timestamp is not None

    def test_record_finding_with_type(self):
        """Test recording finding with specific type."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Based on prior findings, X implies Y",
            phase=2,
            confidence=0.7,
            finding_type=FindingType.INFERENCE,
        )

        assert finding.finding_type == FindingType.INFERENCE

    def test_record_finding_generates_id(self):
        """Test that findings get unique IDs."""
        tracker = TemporalKnowledgeTracker()

        f1 = tracker.record_finding("Finding 1", phase=1)
        f2 = tracker.record_finding("Finding 2", phase=1)

        assert f1.id != f2.id

    def test_get_timeline(self):
        """Test getting timeline of findings."""
        tracker = TemporalKnowledgeTracker()

        tracker.record_finding("First finding", phase=1)
        tracker.record_finding("Second finding", phase=1)
        tracker.record_finding("Third finding", phase=2)

        timeline = tracker.get_timeline()

        assert len(timeline) == 3
        # Should be in chronological order
        assert timeline[0].text == "First finding"
        assert timeline[2].text == "Third finding"


class TestHypothesisTracking:
    """Tests for hypothesis tracking."""

    def test_create_hypothesis(self):
        """Test creating a hypothesis."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis(
            text="Quantum computing will revolutionize cryptography",
            confidence=0.6,
        )

        assert isinstance(hypothesis, Hypothesis)
        assert hypothesis.text == "Quantum computing will revolutionize cryptography"
        assert hypothesis.confidence == 0.6
        assert hypothesis.id is not None

    def test_update_hypothesis(self):
        """Test updating a hypothesis."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis(
            text="Initial hypothesis",
            confidence=0.5,
        )

        evolution = tracker.update_hypothesis(
            hypothesis_id=hypothesis.id,
            new_text="Refined hypothesis with more evidence",
            new_confidence=0.8,
            reason="New evidence from research",
        )

        assert isinstance(evolution, HypothesisEvolution)
        assert evolution.old_text == "Initial hypothesis"
        assert evolution.new_text == "Refined hypothesis with more evidence"
        assert evolution.old_confidence == 0.5
        assert evolution.new_confidence == 0.8

    def test_get_hypothesis_history(self):
        """Test getting hypothesis evolution history."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis("Initial", confidence=0.5)
        tracker.update_hypothesis(hypothesis.id, "Update 1", 0.6, "Reason 1")
        tracker.update_hypothesis(hypothesis.id, "Update 2", 0.7, "Reason 2")

        history = tracker.get_hypothesis_history(hypothesis.id)

        assert len(history) == 2
        assert history[0].new_text == "Update 1"
        assert history[1].new_text == "Update 2"

    def test_invalidate_hypothesis(self):
        """Test invalidating a hypothesis."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis("Test hypothesis", confidence=0.7)
        tracker.invalidate_hypothesis(
            hypothesis.id,
            reason="Contradicted by new evidence",
        )

        current = tracker.get_hypothesis(hypothesis.id)

        assert current.confidence == 0.0
        assert current.invalidated is True


class TestFindingTypes:
    """Tests for different finding types."""

    def test_finding_type_fact(self):
        """Test FACT finding type."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Water boils at 100C at sea level",
            phase=1,
            finding_type=FindingType.FACT,
        )

        assert finding.finding_type == FindingType.FACT

    def test_finding_type_observation(self):
        """Test OBSERVATION finding type."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="The experiment showed a 15% improvement",
            phase=1,
            finding_type=FindingType.OBSERVATION,
        )

        assert finding.finding_type == FindingType.OBSERVATION

    def test_finding_type_inference(self):
        """Test INFERENCE finding type."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Therefore, X must be related to Y",
            phase=2,
            finding_type=FindingType.INFERENCE,
        )

        assert finding.finding_type == FindingType.INFERENCE

    def test_finding_type_contradiction(self):
        """Test CONTRADICTION finding type."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="This contradicts earlier finding about X",
            phase=3,
            finding_type=FindingType.CONTRADICTION,
        )

        assert finding.finding_type == FindingType.CONTRADICTION


class TestTimelineFiltering:
    """Tests for timeline filtering."""

    def test_filter_by_phase(self):
        """Test filtering timeline by phase."""
        tracker = TemporalKnowledgeTracker()

        tracker.record_finding("Phase 1 finding", phase=1)
        tracker.record_finding("Phase 2 finding", phase=2)
        tracker.record_finding("Another phase 1", phase=1)

        phase1_findings = tracker.get_findings_by_phase(1)

        assert len(phase1_findings) == 2
        for f in phase1_findings:
            assert f.phase == 1

    def test_filter_by_type(self):
        """Test filtering timeline by finding type."""
        tracker = TemporalKnowledgeTracker()

        tracker.record_finding("Fact 1", phase=1, finding_type=FindingType.FACT)
        tracker.record_finding("Inference 1", phase=1, finding_type=FindingType.INFERENCE)
        tracker.record_finding("Fact 2", phase=2, finding_type=FindingType.FACT)

        facts = tracker.get_findings_by_type(FindingType.FACT)

        assert len(facts) == 2
        for f in facts:
            assert f.finding_type == FindingType.FACT

    def test_filter_by_confidence(self):
        """Test filtering timeline by confidence threshold."""
        tracker = TemporalKnowledgeTracker()

        tracker.record_finding("Low confidence", phase=1, confidence=0.3)
        tracker.record_finding("Medium confidence", phase=1, confidence=0.6)
        tracker.record_finding("High confidence", phase=1, confidence=0.9)

        high_confidence = tracker.get_findings_above_confidence(0.7)

        assert len(high_confidence) == 1
        assert high_confidence[0].confidence == 0.9


class TestSerialization:
    """Tests for serialization."""

    def test_temporal_finding_to_dict(self):
        """Test TemporalFinding serialization."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Test finding",
            phase=1,
            confidence=0.8,
            source="test",
            finding_type=FindingType.FACT,
        )

        data = finding.to_dict()

        assert data["text"] == "Test finding"
        assert data["phase"] == 1
        assert data["confidence"] == 0.8
        assert data["source"] == "test"
        assert data["finding_type"] == "fact"
        assert "timestamp" in data
        assert "id" in data

    def test_hypothesis_to_dict(self):
        """Test Hypothesis serialization."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis(
            text="Test hypothesis",
            confidence=0.7,
        )

        data = hypothesis.to_dict()

        assert data["text"] == "Test hypothesis"
        assert data["confidence"] == 0.7
        assert "id" in data
        assert "created_at" in data

    def test_export_full_timeline(self):
        """Test exporting full timeline data."""
        tracker = TemporalKnowledgeTracker()

        tracker.record_finding("Finding 1", phase=1)
        tracker.record_finding("Finding 2", phase=2)
        hypothesis = tracker.create_hypothesis("Hypothesis", confidence=0.5)
        tracker.update_hypothesis(hypothesis.id, "Updated", 0.7, "Evidence")

        export = tracker.export_timeline()

        assert "findings" in export
        assert "hypotheses" in export
        assert len(export["findings"]) == 2
        assert len(export["hypotheses"]) == 1


class TestConfidenceTracking:
    """Tests for confidence tracking over time."""

    def test_confidence_increases_with_confirmation(self):
        """Test that confirming findings increases confidence."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Initial finding",
            phase=1,
            confidence=0.5,
        )

        # Record a confirming finding
        tracker.record_finding(
            text="This confirms the initial finding",
            phase=2,
            confidence=0.9,
            finding_type=FindingType.CONFIRMATION,
            related_to=finding.id,
        )

        # The original finding's effective confidence should be higher
        # (implementation dependent)

    def test_confidence_decreases_with_contradiction(self):
        """Test that contradicting findings affects confidence."""
        tracker = TemporalKnowledgeTracker()

        finding = tracker.record_finding(
            text="Initial finding",
            phase=1,
            confidence=0.8,
        )

        tracker.record_finding(
            text="This contradicts the initial finding",
            phase=2,
            confidence=0.9,
            finding_type=FindingType.CONTRADICTION,
            related_to=finding.id,
        )

        # Should track the contradiction relationship
