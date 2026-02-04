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


class TestHypothesisTracking:
    """Tests for hypothesis tracking."""

    def test_create_hypothesis(self):
        """Test creating a hypothesis."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis(
            text="Quantum computing will revolutionize cryptography",
            phase=1,
            confidence=0.6,
        )

        assert isinstance(hypothesis, Hypothesis)
        assert hypothesis.current_state.text == "Quantum computing will revolutionize cryptography"
        assert hypothesis.current_state.confidence == 0.6
        assert hypothesis.id is not None

    def test_update_hypothesis(self):
        """Test updating a hypothesis."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis(
            text="Initial hypothesis",
            phase=1,
            confidence=0.5,
        )

        evolution = tracker.update_hypothesis(
            hypothesis_id=hypothesis.id,
            new_text="Refined hypothesis with more evidence",
            reason="New evidence from research",
            confidence=0.8,
        )

        assert isinstance(evolution, HypothesisEvolution)
        assert evolution.old_state.text == "Initial hypothesis"
        assert evolution.new_state.text == "Refined hypothesis with more evidence"

    def test_get_hypothesis_history(self):
        """Test getting hypothesis evolution history."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis("Initial", phase=1, confidence=0.5)
        tracker.update_hypothesis(hypothesis.id, "Update 1", "Reason 1", confidence=0.6)
        tracker.update_hypothesis(hypothesis.id, "Update 2", "Reason 2", confidence=0.7)

        history = tracker.get_hypothesis_history(hypothesis.id)

        # Should have evolution entries (created + 2 updates = 3)
        assert len(history) >= 3

    def test_invalidate_hypothesis(self):
        """Test invalidating a hypothesis."""
        tracker = TemporalKnowledgeTracker()

        hypothesis = tracker.create_hypothesis("Test hypothesis", phase=1, confidence=0.7)
        tracker.invalidate_hypothesis(
            hypothesis.id,
            reason="Contradicted by new evidence",
        )

        # Get the updated hypothesis
        updated = tracker.hypotheses.get(hypothesis.id)

        assert updated is not None
        assert updated.current_state.confidence == 0.0


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
            phase=1,
            confidence=0.7,
        )

        data = hypothesis.to_dict()

        assert "id" in data
        assert "current_state" in data
        assert "created_at" in data

    def test_export_full_timeline(self):
        """Test exporting full timeline data."""
        tracker = TemporalKnowledgeTracker()

        tracker.record_finding("Finding 1", phase=1)
        tracker.record_finding("Finding 2", phase=2)
        tracker.create_hypothesis("Hypothesis", phase=1, confidence=0.5)

        export = tracker.export_for_job_manager()

        assert "findings" in export
        assert "hypotheses" in export
        assert len(export["findings"]) == 2
        assert len(export["hypotheses"]) == 1


class TestTemporalFindingDataclass:
    """Tests for TemporalFinding dataclass."""

    def test_finding_from_dict(self):
        """Test TemporalFinding deserialization."""
        data = {
            "id": "test123",
            "text": "Test finding",
            "phase": 1,
            "confidence": 0.8,
            "source": "test",
            "finding_type": "fact",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "related_findings": [],
            "tags": ["test"],
            "metadata": {},
        }

        finding = TemporalFinding.from_dict(data)

        assert finding.id == "test123"
        assert finding.text == "Test finding"
        assert finding.finding_type == FindingType.FACT
