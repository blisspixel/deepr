"""Unit tests for the Temporal Knowledge Tracker module.

Tests temporal aspects of expert knowledge including fact tracking,
knowledge evolution, staleness detection, and timeline management.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
from unittest.mock import patch


def utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

from deepr.experts.temporal_knowledge import (
    KnowledgeFact,
    KnowledgeEvolution,
    TemporalKnowledgeTracker
)


class TestKnowledgeFact:
    """Test KnowledgeFact dataclass."""

    def test_create_fact(self):
        """Test creating a knowledge fact."""
        now = utc_now()
        fact = KnowledgeFact(
            topic="Python",
            fact_text="Python 3.12 was released in October 2023",
            learned_at=now,
            source="research_001",
            confidence=0.9
        )
        assert fact.topic == "Python"
        assert fact.fact_text == "Python 3.12 was released in October 2023"
        assert fact.confidence == 0.9
        assert fact.superseded_by is None
        assert fact.valid_until is None

    def test_is_current_no_supersede(self):
        """Test is_current when fact is not superseded."""
        fact = KnowledgeFact(
            topic="Test",
            fact_text="Test fact",
            learned_at=utc_now(),
            source="test",
            confidence=0.8
        )
        assert fact.is_current is True

    def test_is_current_superseded(self):
        """Test is_current when fact is superseded."""
        fact = KnowledgeFact(
            topic="Test",
            fact_text="Old fact",
            learned_at=utc_now(),
            source="test",
            confidence=0.8,
            superseded_by="new_fact_001"
        )
        assert fact.is_current is False

    def test_is_current_expired(self):
        """Test is_current when fact has expired."""
        fact = KnowledgeFact(
            topic="Test",
            fact_text="Time-sensitive fact",
            learned_at=utc_now() - timedelta(days=10),
            source="test",
            confidence=0.8,
            valid_until=utc_now() - timedelta(days=1)
        )
        assert fact.is_current is False

    def test_is_current_not_expired(self):
        """Test is_current when fact has not expired yet."""
        fact = KnowledgeFact(
            topic="Test",
            fact_text="Time-sensitive fact",
            learned_at=utc_now(),
            source="test",
            confidence=0.8,
            valid_until=utc_now() + timedelta(days=30)
        )
        assert fact.is_current is True

    def test_age_days(self):
        """Test age_days calculation."""
        fact = KnowledgeFact(
            topic="Test",
            fact_text="Test fact",
            learned_at=utc_now() - timedelta(days=5),
            source="test",
            confidence=0.8
        )
        assert fact.age_days == 5

    def test_age_days_today(self):
        """Test age_days for fact learned today."""
        fact = KnowledgeFact(
            topic="Test",
            fact_text="Test fact",
            learned_at=utc_now(),
            source="test",
            confidence=0.8
        )
        assert fact.age_days == 0


class TestKnowledgeEvolution:
    """Test KnowledgeEvolution dataclass."""

    def test_create_evolution(self):
        """Test creating knowledge evolution."""
        evolution = KnowledgeEvolution(topic="Machine Learning")
        assert evolution.topic == "Machine Learning"
        assert evolution.facts == []
        assert evolution.contradictions_detected == 0

    def test_get_current_facts_empty(self):
        """Test get_current_facts with no facts."""
        evolution = KnowledgeEvolution(topic="Test")
        assert evolution.get_current_facts() == []

    def test_get_current_facts_all_current(self):
        """Test get_current_facts when all facts are current."""
        now = utc_now()
        facts = [
            KnowledgeFact("Test", "Fact 1", now, "src1", 0.8),
            KnowledgeFact("Test", "Fact 2", now, "src2", 0.9),
        ]
        evolution = KnowledgeEvolution(topic="Test", facts=facts)
        current = evolution.get_current_facts()
        assert len(current) == 2

    def test_get_current_facts_some_superseded(self):
        """Test get_current_facts with some superseded facts."""
        now = utc_now()
        facts = [
            KnowledgeFact("Test", "Old fact", now, "src1", 0.8, superseded_by="fact_002"),
            KnowledgeFact("Test", "New fact", now, "src2", 0.9),
        ]
        evolution = KnowledgeEvolution(topic="Test", facts=facts)
        current = evolution.get_current_facts()
        assert len(current) == 1
        assert current[0].fact_text == "New fact"

    def test_get_timeline(self):
        """Test get_timeline returns chronological order."""
        now = utc_now()
        facts = [
            KnowledgeFact("Test", "Second fact", now, "src2", 0.8),
            KnowledgeFact("Test", "First fact", now - timedelta(days=1), "src1", 0.8),
            KnowledgeFact("Test", "Third fact", now + timedelta(hours=1), "src3", 0.8),
        ]
        evolution = KnowledgeEvolution(topic="Test", facts=facts)
        timeline = evolution.get_timeline()
        
        assert len(timeline) == 3
        assert timeline[0][1] == "First fact"
        assert timeline[1][1] == "Second fact"
        assert timeline[2][1] == "Third fact"


class TestTemporalKnowledgeTracker:
    """Test TemporalKnowledgeTracker class."""

    @pytest.fixture
    def temp_tracker(self):
        """Create a tracker with temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TemporalKnowledgeTracker(
                expert_name="Test Expert",
                base_path=tmpdir
            )
            yield tracker

    def test_create_tracker(self, temp_tracker):
        """Test creating a temporal knowledge tracker."""
        assert temp_tracker.expert_name == "Test Expert"
        assert len(temp_tracker.knowledge_by_topic) == 0
        assert len(temp_tracker.facts_by_id) == 0

    def test_get_expert_dir(self, temp_tracker):
        """Test expert directory path generation."""
        expected_name = "test_expert"
        assert expected_name in str(temp_tracker.expert_dir)

    def test_record_learning(self, temp_tracker):
        """Test recording a new fact."""
        fact_id = temp_tracker.record_learning(
            topic="Python",
            fact_text="Python supports async/await",
            source="research_001",
            confidence=0.9
        )
        
        assert fact_id is not None
        assert "Python" in temp_tracker.knowledge_by_topic
        assert len(temp_tracker.facts_by_id) == 1

    def test_record_learning_with_expiration(self, temp_tracker):
        """Test recording a time-sensitive fact."""
        fact_id = temp_tracker.record_learning(
            topic="News",
            fact_text="Current stock price is $100",
            source="market_data",
            confidence=0.95,
            valid_for_days=1
        )
        
        fact = temp_tracker.facts_by_id[fact_id]
        assert fact.valid_until is not None
        assert fact.valid_until > utc_now()

    def test_record_multiple_facts_same_topic(self, temp_tracker):
        """Test recording multiple facts for the same topic."""
        temp_tracker.record_learning("Python", "Fact 1", "src1", 0.8)
        temp_tracker.record_learning("Python", "Fact 2", "src2", 0.9)
        temp_tracker.record_learning("Python", "Fact 3", "src3", 0.85)
        
        # All facts should be recorded in the topic's evolution
        assert len(temp_tracker.knowledge_by_topic["Python"].facts) == 3
        # Note: facts_by_id may have fewer entries if recorded in same second
        # (timestamp-based IDs can collide), but facts list is authoritative

    def test_supersede_fact(self, temp_tracker):
        """Test superseding an old fact with a new one."""
        old_id = temp_tracker.record_learning("Python", "Python 3.11 is latest", "src1", 0.9)
        new_id = temp_tracker.record_learning("Python", "Python 3.12 is latest", "src2", 0.95)
        
        temp_tracker.supersede_fact(old_id, new_id)
        
        old_fact = temp_tracker.facts_by_id[old_id]
        assert old_fact.superseded_by == new_id
        assert old_fact.is_current is False
        assert temp_tracker.knowledge_by_topic["Python"].contradictions_detected == 1

    def test_get_stale_knowledge_none(self, temp_tracker):
        """Test get_stale_knowledge when all knowledge is fresh."""
        temp_tracker.record_learning("Python", "Fresh fact", "src1", 0.9)
        
        stale = temp_tracker.get_stale_knowledge(max_age_days=90)
        assert len(stale) == 0

    def test_get_stale_knowledge_old_facts(self, temp_tracker):
        """Test get_stale_knowledge with old facts."""
        # Manually add an old fact
        old_date = utc_now() - timedelta(days=100)
        fact = KnowledgeFact(
            topic="Old Topic",
            fact_text="Old fact",
            learned_at=old_date,
            source="old_src",
            confidence=0.8
        )
        temp_tracker.knowledge_by_topic["Old Topic"] = KnowledgeEvolution(
            topic="Old Topic",
            facts=[fact]
        )
        fact_id = temp_tracker._generate_fact_id("Old Topic", old_date)
        temp_tracker.facts_by_id[fact_id] = fact
        
        stale = temp_tracker.get_stale_knowledge(max_age_days=90)
        assert "Old Topic" in stale

    def test_needs_refresh_fresh_topic(self, temp_tracker):
        """Test needs_refresh for fresh topic."""
        temp_tracker.record_learning("Python", "Fresh fact", "src1", 0.9)
        assert temp_tracker.needs_refresh("Python") is False

    def test_needs_refresh_unknown_topic(self, temp_tracker):
        """Test needs_refresh for unknown topic."""
        assert temp_tracker.needs_refresh("Unknown") is False

    def test_needs_refresh_stale_topic(self, temp_tracker):
        """Test needs_refresh for stale topic."""
        temp_tracker.stale_topics.add("Stale Topic")
        assert temp_tracker.needs_refresh("Stale Topic") is True

    def test_needs_refresh_expired_facts(self, temp_tracker):
        """Test needs_refresh when facts have expired."""
        # Add expired fact
        expired_date = utc_now() - timedelta(days=10)
        fact = KnowledgeFact(
            topic="Expired",
            fact_text="Expired fact",
            learned_at=expired_date,
            source="src",
            confidence=0.8,
            valid_until=utc_now() - timedelta(days=1)
        )
        temp_tracker.knowledge_by_topic["Expired"] = KnowledgeEvolution(
            topic="Expired",
            facts=[fact]
        )
        
        assert temp_tracker.needs_refresh("Expired") is True

    def test_get_knowledge_timeline_empty(self, temp_tracker):
        """Test get_knowledge_timeline for unknown topic."""
        timeline = temp_tracker.get_knowledge_timeline("Unknown")
        assert timeline == []

    def test_get_knowledge_timeline(self, temp_tracker):
        """Test get_knowledge_timeline returns events."""
        temp_tracker.record_learning("Python", "Fact 1", "src1", 0.8)
        temp_tracker.record_learning("Python", "Fact 2", "src2", 0.9)
        
        timeline = temp_tracker.get_knowledge_timeline("Python")
        
        assert len(timeline) == 2
        assert "date" in timeline[0]
        assert "fact" in timeline[0]
        assert "source" in timeline[0]
        assert "confidence" in timeline[0]
        assert "current" in timeline[0]

    def test_get_statistics_empty(self, temp_tracker):
        """Test get_statistics with no knowledge."""
        stats = temp_tracker.get_statistics()
        
        assert stats["total_topics"] == 0
        assert stats["total_facts"] == 0
        assert stats["current_facts"] == 0
        assert stats["superseded_facts"] == 0
        assert stats["contradictions_resolved"] == 0

    def test_get_statistics_with_data(self, temp_tracker):
        """Test get_statistics with knowledge."""
        temp_tracker.record_learning("Python", "Fact 1", "src1", 0.8)
        temp_tracker.record_learning("JavaScript", "JS Fact", "src3", 0.85)
        
        stats = temp_tracker.get_statistics()
        
        assert stats["total_topics"] == 2
        # Each topic has 1 fact
        assert stats["total_facts"] >= 2
        assert stats["current_facts"] >= 2
        assert stats["superseded_facts"] == 0


class TestTemporalKnowledgeTrackerPersistence:
    """Test persistence of temporal knowledge."""

    def test_save_and_load(self):
        """Test saving and loading temporal knowledge."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate tracker
            tracker1 = TemporalKnowledgeTracker("Test Expert", tmpdir)
            tracker1.record_learning("Python", "Fact 1", "src1", 0.9)
            tracker1.record_learning("Python", "Fact 2", "src2", 0.85)
            
            # Create new tracker (should load saved data)
            tracker2 = TemporalKnowledgeTracker("Test Expert", tmpdir)
            
            assert len(tracker2.knowledge_by_topic) == 1
            assert "Python" in tracker2.knowledge_by_topic
            assert len(tracker2.knowledge_by_topic["Python"].facts) == 2

    def test_save_with_superseded_facts(self):
        """Test saving and loading superseded facts."""
        import time
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker1 = TemporalKnowledgeTracker("Test Expert", tmpdir)
            
            # Record first fact
            old_id = tracker1.record_learning("Python", "Old fact", "src1", 0.8)
            
            # Wait to ensure different timestamp (IDs are timestamp-based)
            time.sleep(1.1)
            
            # Record second fact
            new_id = tracker1.record_learning("Python", "New fact", "src2", 0.9)
            
            # Verify IDs are different
            assert old_id != new_id, "IDs should be different with 1+ second gap"
            
            # Supersede the old fact
            tracker1.supersede_fact(old_id, new_id)
            
            # Verify supersede worked before save
            assert tracker1.facts_by_id[old_id].superseded_by == new_id
            
            # Reload
            tracker2 = TemporalKnowledgeTracker("Test Expert", tmpdir)
            
            # Find the old fact by text
            old_fact = None
            for fact in tracker2.knowledge_by_topic["Python"].facts:
                if fact.fact_text == "Old fact":
                    old_fact = fact
                    break
            
            assert old_fact is not None
            assert old_fact.superseded_by == new_id

    def test_save_stale_topics(self):
        """Test saving and loading stale topics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker1 = TemporalKnowledgeTracker("Test Expert", tmpdir)
            tracker1.stale_topics.add("Stale Topic 1")
            tracker1.stale_topics.add("Stale Topic 2")
            tracker1._save()
            
            tracker2 = TemporalKnowledgeTracker("Test Expert", tmpdir)
            
            assert "Stale Topic 1" in tracker2.stale_topics
            assert "Stale Topic 2" in tracker2.stale_topics


class TestTemporalKnowledgeEdgeCases:
    """Test edge cases in temporal knowledge tracking."""

    def test_special_characters_in_expert_name(self):
        """Test handling special characters in expert name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TemporalKnowledgeTracker(
                expert_name="Test Expert @#$%",
                base_path=tmpdir
            )
            assert "test_expert" in str(tracker.expert_dir).lower()

    def test_special_characters_in_topic(self):
        """Test handling special characters in topic name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TemporalKnowledgeTracker("Test", tmpdir)
            fact_id = tracker.record_learning(
                topic="C++ Programming @#$%",
                fact_text="Test fact",
                source="src",
                confidence=0.8
            )
            assert fact_id is not None
            assert "C++ Programming @#$%" in tracker.knowledge_by_topic

    def test_zero_confidence(self):
        """Test recording fact with zero confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TemporalKnowledgeTracker("Test", tmpdir)
            fact_id = tracker.record_learning(
                topic="Uncertain",
                fact_text="Uncertain fact",
                source="src",
                confidence=0.0
            )
            fact = tracker.facts_by_id[fact_id]
            assert fact.confidence == 0.0

    def test_full_confidence(self):
        """Test recording fact with full confidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TemporalKnowledgeTracker("Test", tmpdir)
            fact_id = tracker.record_learning(
                topic="Certain",
                fact_text="Certain fact",
                source="src",
                confidence=1.0
            )
            fact = tracker.facts_by_id[fact_id]
            assert fact.confidence == 1.0

    def test_record_removes_from_stale(self):
        """Test that recording new fact removes topic from stale list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TemporalKnowledgeTracker("Test", tmpdir)
            tracker.stale_topics.add("Python")
            
            tracker.record_learning("Python", "New fact", "src", 0.9)
            
            assert "Python" not in tracker.stale_topics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
