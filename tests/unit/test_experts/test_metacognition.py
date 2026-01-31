"""Unit tests for the MetaCognition Tracker module.

Tests meta-cognitive awareness tracking including knowledge gaps,
domain confidence, and learning pattern analysis.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile

from deepr.experts.metacognition import (
    KnowledgeGap,
    DomainConfidence,
    MetaCognitionTracker
)


class TestKnowledgeGap:
    """Test KnowledgeGap dataclass."""

    def test_create_knowledge_gap(self):
        """Test creating a knowledge gap."""
        now = datetime.utcnow()
        gap = KnowledgeGap(
            topic="Quantum Computing",
            first_encountered=now,
            times_asked=1,
            research_triggered=False
        )
        assert gap.topic == "Quantum Computing"
        assert gap.times_asked == 1
        assert gap.research_triggered is False
        assert gap.research_date is None
        assert gap.confidence_before == 0.0
        assert gap.confidence_after is None

    def test_knowledge_gap_with_research(self):
        """Test knowledge gap after research."""
        now = datetime.utcnow()
        gap = KnowledgeGap(
            topic="Machine Learning",
            first_encountered=now - timedelta(days=5),
            times_asked=3,
            research_triggered=True,
            research_date=now,
            confidence_before=0.1,
            confidence_after=0.8
        )
        assert gap.research_triggered is True
        assert gap.confidence_after == 0.8


class TestDomainConfidence:
    """Test DomainConfidence dataclass."""

    def test_create_domain_confidence(self):
        """Test creating domain confidence."""
        now = datetime.utcnow()
        conf = DomainConfidence(
            domain="Python",
            confidence=0.85,
            evidence_count=10,
            last_updated=now,
            sources=["doc1.pdf", "research_001"]
        )
        assert conf.domain == "Python"
        assert conf.confidence == 0.85
        assert conf.evidence_count == 10
        assert len(conf.sources) == 2

    def test_domain_confidence_empty_sources(self):
        """Test domain confidence with no sources."""
        conf = DomainConfidence(
            domain="New Domain",
            confidence=0.0,
            evidence_count=0,
            last_updated=datetime.utcnow(),
            sources=[]
        )
        assert conf.sources == []
        assert conf.evidence_count == 0


class TestMetaCognitionTracker:
    """Test MetaCognitionTracker class."""

    @pytest.fixture
    def temp_tracker(self):
        """Create a tracker with temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker(
                expert_name="Test Expert",
                base_path=tmpdir
            )
            yield tracker

    def test_create_tracker(self, temp_tracker):
        """Test creating a metacognition tracker."""
        assert temp_tracker.expert_name == "Test Expert"
        assert len(temp_tracker.knowledge_gaps) == 0
        assert len(temp_tracker.domain_confidence) == 0
        assert len(temp_tracker.uncertainty_log) == 0

    def test_get_expert_dir(self, temp_tracker):
        """Test expert directory path generation."""
        expected_name = "test_expert"
        assert expected_name in str(temp_tracker.expert_dir)

    def test_record_knowledge_gap_new(self, temp_tracker):
        """Test recording a new knowledge gap."""
        gap = temp_tracker.record_knowledge_gap("Quantum Computing", 0.1)
        
        assert gap.topic == "Quantum Computing"
        assert gap.times_asked == 1
        assert gap.confidence_before == 0.1
        assert "Quantum Computing" in temp_tracker.knowledge_gaps
        assert len(temp_tracker.uncertainty_log) == 1

    def test_record_knowledge_gap_existing(self, temp_tracker):
        """Test recording an existing knowledge gap (increments count)."""
        temp_tracker.record_knowledge_gap("Quantum Computing", 0.1)
        gap = temp_tracker.record_knowledge_gap("Quantum Computing", 0.1)
        
        assert gap.times_asked == 2
        assert len(temp_tracker.knowledge_gaps) == 1
        assert len(temp_tracker.uncertainty_log) == 2

    def test_record_research_triggered(self, temp_tracker):
        """Test recording that research was triggered."""
        temp_tracker.record_knowledge_gap("Machine Learning")
        temp_tracker.record_research_triggered("Machine Learning", "deep_research")
        
        gap = temp_tracker.knowledge_gaps["Machine Learning"]
        assert gap.research_triggered is True
        assert gap.research_date is not None

    def test_record_research_triggered_unknown_topic(self, temp_tracker):
        """Test recording research for unknown topic (should not error)."""
        temp_tracker.record_research_triggered("Unknown Topic", "quick_lookup")
        # Should add to uncertainty log but not create gap
        assert len(temp_tracker.uncertainty_log) == 1

    def test_record_learning(self, temp_tracker):
        """Test recording learning completion."""
        temp_tracker.record_knowledge_gap("Python", 0.2)
        temp_tracker.record_learning("Python", 0.9, ["doc1.pdf", "research_001"])
        
        gap = temp_tracker.knowledge_gaps["Python"]
        assert gap.confidence_after == 0.9
        
        conf = temp_tracker.domain_confidence["Python"]
        assert conf.confidence == 0.9
        assert conf.evidence_count == 2

    def test_record_learning_updates_existing_confidence(self, temp_tracker):
        """Test that learning updates existing domain confidence."""
        temp_tracker.record_learning("Python", 0.7, ["doc1.pdf"])
        temp_tracker.record_learning("Python", 0.9, ["doc2.pdf", "doc3.pdf"])
        
        conf = temp_tracker.domain_confidence["Python"]
        assert conf.confidence == 0.9
        assert conf.evidence_count == 3
        assert len(conf.sources) == 3

    def test_get_knowledge_gaps_default(self, temp_tracker):
        """Test get_knowledge_gaps with default threshold."""
        temp_tracker.record_knowledge_gap("Topic 1")
        temp_tracker.record_knowledge_gap("Topic 2")
        temp_tracker.record_knowledge_gap("Topic 2")
        
        gaps = temp_tracker.get_knowledge_gaps()
        assert len(gaps) == 2

    def test_get_knowledge_gaps_threshold(self, temp_tracker):
        """Test get_knowledge_gaps with higher threshold."""
        temp_tracker.record_knowledge_gap("Topic 1")
        temp_tracker.record_knowledge_gap("Topic 2")
        temp_tracker.record_knowledge_gap("Topic 2")
        temp_tracker.record_knowledge_gap("Topic 2")
        
        gaps = temp_tracker.get_knowledge_gaps(min_times_asked=3)
        assert len(gaps) == 1
        assert gaps[0].topic == "Topic 2"

    def test_get_high_confidence_domains(self, temp_tracker):
        """Test get_high_confidence_domains."""
        temp_tracker.record_learning("Python", 0.9, ["src1"])
        temp_tracker.record_learning("JavaScript", 0.8, ["src2"])
        temp_tracker.record_learning("Rust", 0.5, ["src3"])
        
        high_conf = temp_tracker.get_high_confidence_domains(min_confidence=0.7)
        assert len(high_conf) == 2
        domains = [c.domain for c in high_conf]
        assert "Python" in domains
        assert "JavaScript" in domains

    def test_get_low_confidence_domains(self, temp_tracker):
        """Test get_low_confidence_domains."""
        temp_tracker.record_learning("Python", 0.9, ["src1"])
        temp_tracker.record_learning("JavaScript", 0.2, ["src2"])
        temp_tracker.record_learning("Rust", 0.1, ["src3"])
        
        low_conf = temp_tracker.get_low_confidence_domains(max_confidence=0.3)
        assert len(low_conf) == 2
        domains = [c.domain for c in low_conf]
        assert "JavaScript" in domains
        assert "Rust" in domains

    def test_suggest_proactive_research(self, temp_tracker):
        """Test suggest_proactive_research."""
        # Topic asked 3 times, no research
        for _ in range(3):
            temp_tracker.record_knowledge_gap("Frequent Topic")
        
        # Topic asked once
        temp_tracker.record_knowledge_gap("Rare Topic")
        
        # Topic asked 3 times but researched
        for _ in range(3):
            temp_tracker.record_knowledge_gap("Researched Topic")
        temp_tracker.record_research_triggered("Researched Topic", "standard")
        
        suggestions = temp_tracker.suggest_proactive_research(threshold_times_asked=3)
        assert len(suggestions) == 1
        assert "Frequent Topic" in suggestions

    def test_get_learning_stats_empty(self, temp_tracker):
        """Test get_learning_stats with no data."""
        stats = temp_tracker.get_learning_stats()
        
        assert stats["total_knowledge_gaps"] == 0
        assert stats["researched_gaps"] == 0
        assert stats["learned_gaps"] == 0
        assert stats["learning_rate"] == 0.0
        assert stats["domains_tracked"] == 0
        assert stats["average_confidence"] == 0.0

    def test_get_learning_stats_with_data(self, temp_tracker):
        """Test get_learning_stats with data."""
        # Create gaps
        temp_tracker.record_knowledge_gap("Topic 1")
        temp_tracker.record_knowledge_gap("Topic 2")
        temp_tracker.record_knowledge_gap("Topic 3")
        
        # Research one
        temp_tracker.record_research_triggered("Topic 1", "standard")
        
        # Learn one
        temp_tracker.record_learning("Topic 1", 0.8, ["src1"])
        
        # Add domain confidence
        temp_tracker.record_learning("Python", 0.9, ["src2"])
        
        stats = temp_tracker.get_learning_stats()
        
        assert stats["total_knowledge_gaps"] == 3
        assert stats["researched_gaps"] == 1
        assert stats["learned_gaps"] == 1
        assert stats["learning_rate"] == pytest.approx(1/3, rel=0.01)
        assert stats["domains_tracked"] == 2  # Topic 1 and Python


class TestMetaCognitionTrackerPersistence:
    """Test persistence of metacognition data."""

    def test_save_and_load_knowledge_gaps(self):
        """Test saving and loading knowledge gaps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker1 = MetaCognitionTracker("Test Expert", tmpdir)
            tracker1.record_knowledge_gap("Topic 1", 0.1)
            tracker1.record_knowledge_gap("Topic 2", 0.2)
            tracker1.record_knowledge_gap("Topic 1", 0.1)  # Increment
            
            tracker2 = MetaCognitionTracker("Test Expert", tmpdir)
            
            assert len(tracker2.knowledge_gaps) == 2
            assert tracker2.knowledge_gaps["Topic 1"].times_asked == 2

    def test_save_and_load_domain_confidence(self):
        """Test saving and loading domain confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker1 = MetaCognitionTracker("Test Expert", tmpdir)
            tracker1.record_learning("Python", 0.9, ["doc1.pdf", "doc2.pdf"])
            
            tracker2 = MetaCognitionTracker("Test Expert", tmpdir)
            
            assert "Python" in tracker2.domain_confidence
            conf = tracker2.domain_confidence["Python"]
            assert conf.confidence == 0.9
            assert conf.evidence_count == 2

    def test_save_and_load_uncertainty_log(self):
        """Test saving and loading uncertainty log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker1 = MetaCognitionTracker("Test Expert", tmpdir)
            tracker1.record_knowledge_gap("Topic 1")
            tracker1.record_research_triggered("Topic 1", "deep_research")
            
            tracker2 = MetaCognitionTracker("Test Expert", tmpdir)
            
            assert len(tracker2.uncertainty_log) == 2

    def test_save_and_load_research_triggered(self):
        """Test saving and loading research triggered state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker1 = MetaCognitionTracker("Test Expert", tmpdir)
            tracker1.record_knowledge_gap("ML")
            tracker1.record_research_triggered("ML", "standard")
            
            tracker2 = MetaCognitionTracker("Test Expert", tmpdir)
            
            gap = tracker2.knowledge_gaps["ML"]
            assert gap.research_triggered is True
            assert gap.research_date is not None


class TestMetaCognitionEdgeCases:
    """Test edge cases in metacognition tracking."""

    def test_special_characters_in_expert_name(self):
        """Test handling special characters in expert name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker(
                expert_name="Test Expert @#$%",
                base_path=tmpdir
            )
            assert "test_expert" in str(tracker.expert_dir).lower()

    def test_special_characters_in_topic(self):
        """Test handling special characters in topic name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker("Test", tmpdir)
            gap = tracker.record_knowledge_gap("C++ Programming @#$%")
            assert gap.topic == "C++ Programming @#$%"

    def test_zero_confidence(self):
        """Test recording with zero confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker("Test", tmpdir)
            gap = tracker.record_knowledge_gap("Unknown", 0.0)
            assert gap.confidence_before == 0.0

    def test_full_confidence(self):
        """Test recording with full confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker("Test", tmpdir)
            tracker.record_learning("Expert Domain", 1.0, ["comprehensive_doc.pdf"])
            conf = tracker.domain_confidence["Expert Domain"]
            assert conf.confidence == 1.0

    def test_empty_sources_list(self):
        """Test recording learning with empty sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker("Test", tmpdir)
            tracker.record_learning("Topic", 0.5, [])
            conf = tracker.domain_confidence["Topic"]
            assert conf.evidence_count == 0
            assert conf.sources == []

    def test_high_confidence_threshold_edge(self):
        """Test high confidence at exact threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker("Test", tmpdir)
            tracker.record_learning("Topic", 0.7, ["src"])
            
            high = tracker.get_high_confidence_domains(min_confidence=0.7)
            assert len(high) == 1

    def test_low_confidence_threshold_edge(self):
        """Test low confidence at exact threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = MetaCognitionTracker("Test", tmpdir)
            tracker.record_learning("Topic", 0.3, ["src"])
            
            low = tracker.get_low_confidence_domains(max_confidence=0.3)
            assert len(low) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
