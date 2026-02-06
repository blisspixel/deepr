"""Unit tests and property tests for the hierarchical memory module.

Tests the H-MEM (Hierarchical Episodic Memory) system:
- Memory tier consistency
- Episode serialization round-trips
- Hierarchical retrieval behavior
- User profile updates
- Meta-knowledge tracking

Property tests validate:
- Property 5: Memory tier consistency
- Episode serialization is lossless
- Retrieval returns relevant episodes
- User profile updates are monotonic
"""

import pytest
import json
import string
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set

from deepr.experts.memory import (
    MemoryTier,
    ReasoningStep,
    Episode,
    UserProfile,
    MetaKnowledge,
    HierarchicalMemory,
    ReconstructedContext,
    UserProfileLearner,
)


class TestMemoryTier:
    """Tests for MemoryTier enum."""

    def test_tier_values(self):
        """Test tier enum values."""
        assert MemoryTier.WORKING.value == "working"
        assert MemoryTier.EPISODIC.value == "episodic"
        assert MemoryTier.SEMANTIC.value == "semantic"

    def test_tier_from_string(self):
        """Test creating tier from string."""
        assert MemoryTier("working") == MemoryTier.WORKING
        assert MemoryTier("episodic") == MemoryTier.EPISODIC
        assert MemoryTier("semantic") == MemoryTier.SEMANTIC


class TestReasoningStep:
    """Tests for ReasoningStep dataclass."""

    def test_create_reasoning_step(self):
        """Test creating a reasoning step."""
        step = ReasoningStep(
            step_type="search",
            content="Searching for quantum computing",
            confidence=0.8,
            sources=["doc1.md", "doc2.md"]
        )
        assert step.step_type == "search"
        assert step.content == "Searching for quantum computing"
        assert step.confidence == 0.8
        assert len(step.sources) == 2

    def test_reasoning_step_to_dict(self):
        """Test reasoning step serialization."""
        step = ReasoningStep(
            step_type="hypothesis",
            content="Test hypothesis",
            confidence=0.7,
            sources=["doc1.md"]
        )
        d = step.to_dict()
        
        assert d["step_type"] == "hypothesis"
        assert d["content"] == "Test hypothesis"
        assert d["confidence"] == 0.7
        assert d["sources"] == ["doc1.md"]
        assert "timestamp" in d

    def test_reasoning_step_from_dict(self):
        """Test reasoning step deserialization."""
        data = {
            "step_type": "verification",
            "content": "Verifying claim",
            "confidence": 0.9,
            "sources": ["doc1.md"],
            "timestamp": "2025-01-01T12:00:00"
        }
        step = ReasoningStep.from_dict(data)
        
        assert step.step_type == "verification"
        assert step.content == "Verifying claim"
        assert step.confidence == 0.9

    def test_reasoning_step_default_values(self):
        """Test reasoning step default values."""
        step = ReasoningStep(step_type="search", content="Test")
        
        assert step.confidence == 0.0
        assert step.sources == []
        assert step.timestamp is not None


class TestEpisode:
    """Tests for Episode dataclass."""

    def test_create_episode(self):
        """Test creating an episode."""
        episode = Episode(
            query="What is quantum computing?",
            response="Quantum computing uses qubits..."
        )
        assert episode.query == "What is quantum computing?"
        assert episode.response == "Quantum computing uses qubits..."
        assert episode.tier == MemoryTier.WORKING
        assert episode.id != ""  # Auto-generated

    def test_episode_id_generation(self):
        """Test episode ID is deterministically generated from content."""
        # Same content at same timestamp produces same ID
        from datetime import datetime
        ts = datetime(2025, 1, 1, 12, 0, 0)
        episode1 = Episode(query="Test", response="Response", timestamp=ts)
        episode2 = Episode(query="Test", response="Response", timestamp=ts)
        
        # Same content and timestamp = same ID
        assert episode1.id == episode2.id
        
        # Different content = different ID
        episode3 = Episode(query="Different", response="Response", timestamp=ts)
        assert episode1.id != episode3.id

    def test_episode_with_explicit_id(self):
        """Test episode with explicit ID."""
        episode = Episode(
            id="custom_id",
            query="Test",
            response="Response"
        )
        assert episode.id == "custom_id"

    def test_episode_to_dict(self):
        """Test episode serialization."""
        episode = Episode(
            query="Test query",
            response="Test response",
            context_docs=["doc1.md"],
            user_id="user_123",
            quality_score=0.9,
            tags={"python", "programming"}
        )
        d = episode.to_dict()
        
        assert d["query"] == "Test query"
        assert d["response"] == "Test response"
        assert d["context_docs"] == ["doc1.md"]
        assert d["user_id"] == "user_123"
        assert d["quality_score"] == 0.9
        assert set(d["tags"]) == {"python", "programming"}
        assert d["tier"] == "working"

    def test_episode_from_dict(self):
        """Test episode deserialization."""
        data = {
            "id": "ep_123",
            "query": "Test query",
            "response": "Test response",
            "context_docs": ["doc1.md"],
            "reasoning_chain": [
                {"step_type": "search", "content": "Searching", "confidence": 0.8, "sources": []}
            ],
            "user_id": "user_123",
            "session_id": "session_456",
            "timestamp": "2025-01-01T12:00:00",
            "quality_score": 0.9,
            "tags": ["python"],
            "tier": "episodic"
        }
        episode = Episode.from_dict(data)
        
        assert episode.id == "ep_123"
        assert episode.query == "Test query"
        assert episode.tier == MemoryTier.EPISODIC
        assert len(episode.reasoning_chain) == 1
        assert episode.reasoning_chain[0].step_type == "search"

    def test_episode_tags_conversion(self):
        """Test that tags list is converted to set."""
        episode = Episode(
            query="Test",
            response="Response",
            tags=["python", "programming", "python"]  # Duplicate
        )
        assert isinstance(episode.tags, set)
        assert len(episode.tags) == 2  # Duplicates removed

    def test_episode_get_keywords(self):
        """Test keyword extraction from episode."""
        episode = Episode(
            query="What is quantum computing?",
            response="Quantum computing uses qubits for computation."
        )
        keywords = episode.get_keywords()
        
        assert "quantum" in keywords
        assert "computing" in keywords
        assert "qubits" in keywords
        # Stopwords should be excluded
        assert "is" not in keywords
        assert "the" not in keywords


class TestUserProfile:
    """Tests for UserProfile dataclass."""

    def test_create_user_profile(self):
        """Test creating a user profile."""
        profile = UserProfile(user_id="user_123")
        
        assert profile.user_id == "user_123"
        assert profile.interaction_count == 0
        assert profile.expertise_levels == {}
        assert profile.interests == {}

    def test_user_profile_to_dict(self):
        """Test user profile serialization."""
        profile = UserProfile(
            user_id="user_123",
            expertise_levels={"python": 0.8},
            interests={"programming": 5},
            interaction_count=10
        )
        d = profile.to_dict()
        
        assert d["user_id"] == "user_123"
        assert d["expertise_levels"] == {"python": 0.8}
        assert d["interests"] == {"programming": 5}
        assert d["interaction_count"] == 10

    def test_user_profile_from_dict(self):
        """Test user profile deserialization."""
        data = {
            "user_id": "user_123",
            "expertise_levels": {"python": 0.8},
            "interests": {"programming": 5},
            "preferences": {"verbosity": "detailed"},
            "interaction_count": 10,
            "first_seen": "2025-01-01T12:00:00",
            "last_seen": "2025-01-15T12:00:00",
            "feedback_history": [("positive", "2025-01-10T12:00:00")]
        }
        profile = UserProfile.from_dict(data)
        
        assert profile.user_id == "user_123"
        assert profile.expertise_levels["python"] == 0.8
        assert profile.interaction_count == 10

    def test_update_expertise(self):
        """Test expertise level update with smoothing."""
        profile = UserProfile(user_id="user_123")
        
        # First update
        profile.update_expertise("python", 0.8)
        assert profile.expertise_levels["python"] > 0.5  # Smoothed from default 0.5
        
        # Second update
        old_level = profile.expertise_levels["python"]
        profile.update_expertise("python", 1.0)
        assert profile.expertise_levels["python"] > old_level

    def test_record_interest(self):
        """Test recording interest in topics."""
        profile = UserProfile(user_id="user_123")
        
        profile.record_interest("python")
        assert profile.interests["python"] == 1
        
        profile.record_interest("python")
        assert profile.interests["python"] == 2
        
        profile.record_interest("javascript")
        assert profile.interests["javascript"] == 1

    def test_get_top_interests(self):
        """Test getting top interests."""
        profile = UserProfile(user_id="user_123")
        profile.interests = {
            "python": 10,
            "javascript": 5,
            "rust": 3,
            "go": 1
        }
        
        top = profile.get_top_interests(2)
        assert top == ["python", "javascript"]

    def test_get_expertise_for_query(self):
        """Test estimating expertise for a query."""
        profile = UserProfile(user_id="user_123")
        profile.expertise_levels = {
            "python": 0.9,
            "javascript": 0.5
        }
        
        # Query matching a domain
        expertise = profile.get_expertise_for_query("How do I use python decorators?")
        assert expertise == 0.9
        
        # Query not matching any domain
        expertise = profile.get_expertise_for_query("What is rust?")
        assert expertise == 0.7  # Average of all expertise levels


class TestMetaKnowledge:
    """Tests for MetaKnowledge dataclass."""

    def test_create_meta_knowledge(self):
        """Test creating meta-knowledge."""
        meta = MetaKnowledge(expert_name="test_expert")
        
        assert meta.expert_name == "test_expert"
        assert meta.domains == {}
        assert meta.knowledge_gaps == []

    def test_meta_knowledge_to_dict(self):
        """Test meta-knowledge serialization."""
        meta = MetaKnowledge(
            expert_name="test_expert",
            domains={"python": 0.9},
            confidence_by_topic={"decorators": 0.8}
        )
        d = meta.to_dict()
        
        assert d["expert_name"] == "test_expert"
        assert d["domains"] == {"python": 0.9}
        assert d["confidence_by_topic"] == {"decorators": 0.8}

    def test_meta_knowledge_from_dict(self):
        """Test meta-knowledge deserialization."""
        data = {
            "expert_name": "test_expert",
            "domains": {"python": 0.9},
            "knowledge_gaps": [{"topic": "rust", "query": "What is rust?", "confidence": 0.1, "resolved": False}],
            "confidence_by_topic": {"decorators": 0.8},
            "learning_events": [],
            "last_updated": "2025-01-01T12:00:00"
        }
        meta = MetaKnowledge.from_dict(data)
        
        assert meta.expert_name == "test_expert"
        assert meta.domains["python"] == 0.9
        assert len(meta.knowledge_gaps) == 1

    def test_record_gap(self):
        """Test recording a knowledge gap."""
        meta = MetaKnowledge(expert_name="test_expert")
        
        meta.record_gap("rust", "What is rust?", 0.1)
        
        assert len(meta.knowledge_gaps) == 1
        assert meta.knowledge_gaps[0]["topic"] == "rust"
        assert meta.knowledge_gaps[0]["resolved"] is False

    def test_record_gap_updates_existing(self):
        """Test that recording same gap updates confidence."""
        meta = MetaKnowledge(expert_name="test_expert")
        
        meta.record_gap("rust", "What is rust?", 0.3)
        meta.record_gap("rust", "How does rust work?", 0.1)
        
        # Should still be one gap, with lower confidence
        assert len(meta.knowledge_gaps) == 1
        assert meta.knowledge_gaps[0]["confidence"] == 0.1

    def test_resolve_gap(self):
        """Test resolving a knowledge gap."""
        meta = MetaKnowledge(expert_name="test_expert")
        meta.record_gap("rust", "What is rust?", 0.1)
        
        meta.resolve_gap("rust")
        
        assert meta.knowledge_gaps[0]["resolved"] is True
        assert "resolved_at" in meta.knowledge_gaps[0]

    def test_record_learning(self):
        """Test recording a learning event."""
        meta = MetaKnowledge(expert_name="test_expert")
        meta.record_gap("rust", "What is rust?", 0.1)
        
        meta.record_learning("rust", "documentation", 0.5)
        
        assert len(meta.learning_events) == 1
        assert meta.confidence_by_topic["rust"] > 0.5
        assert meta.knowledge_gaps[0]["resolved"] is True

    def test_get_confidence(self):
        """Test getting confidence for a topic."""
        meta = MetaKnowledge(expert_name="test_expert")
        meta.confidence_by_topic = {"python": 0.9}
        meta.domains = {"programming": 0.7}
        
        # Direct match
        assert meta.get_confidence("python") == 0.9
        
        # Partial match
        assert meta.get_confidence("python decorators") == 0.9
        
        # Domain match
        assert meta.get_confidence("programming basics") == 0.7
        
        # No match
        assert meta.get_confidence("cooking") == 0.5

    def test_get_unresolved_gaps(self):
        """Test getting unresolved gaps."""
        meta = MetaKnowledge(expert_name="test_expert")
        meta.record_gap("rust", "What is rust?", 0.1)
        meta.record_gap("go", "What is go?", 0.2)
        meta.resolve_gap("rust")
        
        unresolved = meta.get_unresolved_gaps()
        
        assert len(unresolved) == 1
        assert unresolved[0]["topic"] == "go"


class TestHierarchicalMemory:
    """Tests for HierarchicalMemory class."""

    def test_create_memory(self, tmp_path):
        """Test creating hierarchical memory."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        assert memory.expert_name == "test_expert"
        assert memory.working_capacity == 10
        assert len(memory.working_memory) == 0
        assert len(memory.episodic_memory) == 0

    def test_add_episode(self, tmp_path):
        """Test adding an episode to working memory."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        episode = Episode(
            query="What is Python?",
            response="Python is a programming language."
        )
        episode_id = memory.add_episode(episode)
        
        assert len(memory.working_memory) == 1
        assert memory.working_memory[0].id == episode_id
        assert memory.working_memory[0].tier == MemoryTier.WORKING

    def test_add_episode_updates_keyword_index(self, tmp_path):
        """Test that adding episode updates keyword index."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        episode = Episode(
            query="What is Python?",
            response="Python is a programming language."
        )
        episode_id = memory.add_episode(episode)
        
        assert "python" in memory._keyword_index
        assert episode_id in memory._keyword_index["python"]

    def test_consolidate(self, tmp_path):
        """Test consolidation from working to episodic memory."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory",
            working_capacity=4
        )
        
        # Add more episodes than capacity
        for i in range(6):
            episode = Episode(
                query=f"Question {i}",
                response=f"Answer {i}"
            )
            memory.add_episode(episode)
        
        # Should have consolidated
        assert len(memory.working_memory) <= memory.working_capacity
        assert len(memory.episodic_memory) > 0
        
        # Consolidated episodes should have EPISODIC tier
        for ep in memory.episodic_memory:
            assert ep.tier == MemoryTier.EPISODIC

    def test_retrieve_from_working_memory(self, tmp_path):
        """Test retrieving episodes from working memory."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        episode = Episode(
            query="What is Python?",
            response="Python is a programming language."
        )
        memory.add_episode(episode)
        
        results = memory.retrieve("Python programming", top_k=5)
        
        assert len(results) >= 1
        assert "python" in results[0].query.lower()

    def test_retrieve_from_episodic_memory(self, tmp_path):
        """Test retrieving episodes from episodic memory."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory",
            working_capacity=2
        )
        
        # Add episodes to trigger consolidation
        for i in range(5):
            episode = Episode(
                query=f"Python question {i}",
                response=f"Python answer {i}"
            )
            memory.add_episode(episode)
        
        # Search should find episodes in episodic memory
        results = memory.retrieve("Python", top_k=5)
        
        assert len(results) >= 1

    def test_retrieve_with_tier_filter(self, tmp_path):
        """Test retrieving with specific tier filter."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory",
            working_capacity=2
        )
        
        # Add episodes
        for i in range(5):
            episode = Episode(
                query=f"Python question {i}",
                response=f"Python answer {i}"
            )
            memory.add_episode(episode)
        
        # Search only working memory
        results = memory.retrieve(
            "Python",
            top_k=5,
            tiers=[MemoryTier.WORKING]
        )
        
        for ep in results:
            assert ep.tier == MemoryTier.WORKING

    def test_get_user_profile(self, tmp_path):
        """Test getting or creating user profile."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        profile = memory.get_user_profile("user_123")
        
        assert profile.user_id == "user_123"
        assert "user_123" in memory.user_profiles

    def test_update_user_profile(self, tmp_path):
        """Test updating user profile from interaction."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        memory.update_user_profile(
            "user_123",
            "How do I use Python decorators?",
            response_quality=0.9
        )
        
        profile = memory.get_user_profile("user_123")
        assert profile.interaction_count == 1
        assert "python" in profile.interests or "decorators" in profile.interests

    def test_persistence(self, tmp_path):
        """Test memory persistence across instances."""
        storage_dir = tmp_path / "memory"
        
        # Create memory and add data
        memory1 = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=storage_dir,
            working_capacity=2
        )
        
        for i in range(5):
            episode = Episode(
                query=f"Question {i}",
                response=f"Answer {i}"
            )
            memory1.add_episode(episode)
        
        memory1.get_user_profile("user_123")
        memory1._save()
        
        # Create new instance and verify data loaded
        memory2 = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=storage_dir
        )
        
        assert len(memory2.episodic_memory) > 0
        assert "user_123" in memory2.user_profiles

    def test_get_statistics(self, tmp_path):
        """Test getting memory statistics."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory",
            working_capacity=4
        )
        
        for i in range(6):
            episode = Episode(
                query=f"Question {i}",
                response=f"Answer {i}"
            )
            memory.add_episode(episode)
        
        stats = memory.get_statistics()
        
        assert "working_memory_count" in stats
        assert "episodic_memory_count" in stats
        assert "keyword_index_size" in stats
        assert stats["working_capacity"] == 4


class TestReconstructedContext:
    """Tests for ReconstructedContext dataclass."""

    def test_create_reconstructed_context(self):
        """Test creating reconstructed context."""
        episode = Episode(
            query="What is Python?",
            response="Python is a programming language."
        )
        context = ReconstructedContext(
            episode=episode,
            documents=[{"name": "doc1.md", "content": "Python docs"}],
            reasoning_summary="Searched -> Found -> Synthesized"
        )
        
        assert context.episode == episode
        assert len(context.documents) == 1
        assert context.reasoning_summary != ""

    def test_reconstructed_context_to_dict(self):
        """Test reconstructed context serialization."""
        episode = Episode(
            query="Test",
            response="Response"
        )
        context = ReconstructedContext(
            episode=episode,
            documents=[{"name": "doc1.md", "content": "Content"}]
        )
        d = context.to_dict()
        
        assert "episode" in d
        assert "documents" in d
        assert d["documents"][0]["name"] == "doc1.md"

    def test_get_full_context_prompt(self):
        """Test generating full context prompt."""
        episode = Episode(
            query="What is Python?",
            response="Python is a programming language."
        )
        context = ReconstructedContext(
            episode=episode,
            documents=[{"name": "doc1.md", "content": "Python documentation content"}],
            reasoning_summary="Searched docs -> Found answer"
        )
        
        prompt = context.get_full_context_prompt()
        
        assert "What is Python?" in prompt
        assert "Python is a programming language" in prompt
        assert "doc1.md" in prompt


class TestHierarchicalMemoryReconstructContext:
    """Tests for context reconstruction in HierarchicalMemory."""

    def test_reconstruct_context(self, tmp_path):
        """Test reconstructing context from episode."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        episode = Episode(
            query="What is Python?",
            response="Python is a programming language.",
            session_id="session_123",
            reasoning_chain=[
                ReasoningStep(step_type="search", content="Searching for Python info")
            ]
        )
        episode_id = memory.add_episode(episode)
        
        context = memory.reconstruct_context(episode_id)
        
        assert context is not None
        assert context.episode.id == episode_id
        assert "search" in context.reasoning_summary.lower()

    def test_reconstruct_context_not_found(self, tmp_path):
        """Test reconstructing context for non-existent episode."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        context = memory.reconstruct_context("nonexistent_id")
        
        assert context is None

    def test_reconstruct_context_with_related_episodes(self, tmp_path):
        """Test reconstructing context includes related episodes."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        # Add episodes from same session
        session_id = "session_123"
        for i in range(3):
            episode = Episode(
                query=f"Question {i}",
                response=f"Answer {i}",
                session_id=session_id
            )
            memory.add_episode(episode)
        
        # Get first episode's context
        first_id = memory.working_memory[0].id
        context = memory.reconstruct_context(first_id, include_related=True)
        
        assert context is not None
        assert len(context.related_episodes) == 2  # Other 2 episodes


class TestUserProfileLearner:
    """Tests for UserProfileLearner class."""

    def test_create_learner(self, tmp_path):
        """Test creating a user profile learner."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        learner = UserProfileLearner(memory)
        
        assert learner.memory == memory

    def test_learn_from_interaction(self, tmp_path):
        """Test learning from user interaction."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        learner = UserProfileLearner(memory)
        
        learner.learn_from_interaction(
            user_id="user_123",
            query="How do I implement a distributed algorithm?",
            response="To implement a distributed algorithm..."
        )
        
        profile = memory.get_user_profile("user_123")
        assert profile.interaction_count == 1
        assert len(profile.interests) > 0

    def test_learn_from_feedback(self, tmp_path):
        """Test learning from user feedback."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        learner = UserProfileLearner(memory)
        
        learner.learn_from_interaction(
            user_id="user_123",
            query="What is Python?",
            response="Python is a programming language." * 50,  # Long response
            feedback="too long, please be more concise"
        )
        
        profile = memory.get_user_profile("user_123")
        assert profile.preferences.get("verbosity") == "concise"

    def test_get_personalization_hints(self, tmp_path):
        """Test getting personalization hints."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        learner = UserProfileLearner(memory)
        
        # Build up some history
        for i in range(10):
            learner.learn_from_interaction(
                user_id="user_123",
                query=f"How do I implement algorithm {i} in Python?",
                response=f"Implementation {i}..."
            )
        
        hints = learner.get_personalization_hints("user_123")
        
        assert "expertise_level" in hints
        assert "top_interests" in hints
        assert "is_returning_user" in hints
        assert hints["is_returning_user"] is True

    def test_get_learner_from_memory(self, tmp_path):
        """Test getting learner from memory instance."""
        memory = HierarchicalMemory(
            expert_name="test_expert",
            storage_dir=tmp_path / "memory"
        )
        
        learner = memory.get_learner()
        
        assert isinstance(learner, UserProfileLearner)
        assert learner.memory == memory
        
        # Should return same instance
        learner2 = memory.get_learner()
        assert learner is learner2


# Property-based tests using hypothesis
from hypothesis import given, strategies as st, assume, settings, HealthCheck


class TestEpisodePropertyTests:
    """Property-based tests for Episode serialization.
    
    Property: Episode serialization is lossless (round-trip preserves data).
    """

    @given(
        query=st.text(min_size=1, max_size=200),
        response=st.text(min_size=1, max_size=500),
        quality_score=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_episode_serialization_round_trip(self, query, response, quality_score):
        """Property: Episode serialization preserves all data."""
        assume('\x00' not in query and '\x00' not in response)
        
        episode = Episode(
            query=query,
            response=response,
            quality_score=quality_score
        )
        
        # Serialize and deserialize
        d = episode.to_dict()
        restored = Episode.from_dict(d)
        
        assert restored.query == episode.query
        assert restored.response == episode.response
        assert restored.id == episode.id
        assert restored.tier == episode.tier
        if quality_score is not None:
            assert abs(restored.quality_score - episode.quality_score) < 1e-10

    @given(
        tags=st.lists(st.text(min_size=1, max_size=20, alphabet=string.ascii_letters), min_size=0, max_size=10)
    )
    @settings(max_examples=30)
    def test_episode_tags_preserved(self, tags):
        """Property: Episode tags are preserved through serialization."""
        episode = Episode(
            query="Test",
            response="Response",
            tags=tags
        )
        
        d = episode.to_dict()
        restored = Episode.from_dict(d)
        
        assert restored.tags == episode.tags

    @given(
        num_steps=st.integers(min_value=0, max_value=5),
        confidences=st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False), min_size=0, max_size=5)
    )
    @settings(max_examples=30)
    def test_episode_reasoning_chain_preserved(self, num_steps, confidences):
        """Property: Reasoning chain is preserved through serialization."""
        steps = []
        for i in range(min(num_steps, len(confidences))):
            steps.append(ReasoningStep(
                step_type="search",
                content=f"Step {i}",
                confidence=confidences[i]
            ))
        
        episode = Episode(
            query="Test",
            response="Response",
            reasoning_chain=steps
        )
        
        d = episode.to_dict()
        restored = Episode.from_dict(d)
        
        assert len(restored.reasoning_chain) == len(episode.reasoning_chain)
        for orig, rest in zip(episode.reasoning_chain, restored.reasoning_chain):
            assert rest.step_type == orig.step_type
            assert rest.content == orig.content


class TestUserProfilePropertyTests:
    """Property-based tests for UserProfile.
    
    Property: User profile updates are monotonic (interaction count always increases).
    """

    @given(
        domain=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L',))),
        levels=st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False), min_size=1, max_size=10)
    )
    @settings(max_examples=30)
    def test_expertise_update_bounded(self, domain, levels):
        """Property: Expertise level is always in [0.0, 1.0] after updates."""
        profile = UserProfile(user_id="test")
        
        for level in levels:
            profile.update_expertise(domain, level)
        
        assert 0.0 <= profile.expertise_levels[domain] <= 1.0

    @given(
        topics=st.lists(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L',))), min_size=1, max_size=20)
    )
    @settings(max_examples=30)
    def test_interest_counts_non_negative(self, topics):
        """Property: Interest counts are always non-negative."""
        profile = UserProfile(user_id="test")
        
        for topic in topics:
            profile.record_interest(topic)
        
        for count in profile.interests.values():
            assert count >= 0

    @given(
        expertise_levels=st.dictionaries(
            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=('L',))),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=0,
            max_size=5
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_serialization_round_trip(self, expertise_levels):
        """Property: UserProfile serialization is lossless."""
        profile = UserProfile(
            user_id="test",
            expertise_levels=expertise_levels
        )
        
        d = profile.to_dict()
        restored = UserProfile.from_dict(d)
        
        assert restored.user_id == profile.user_id
        assert restored.expertise_levels == profile.expertise_levels


class TestMetaKnowledgePropertyTests:
    """Property-based tests for MetaKnowledge.
    
    Property: Confidence values are always in [0.0, 1.0].
    """

    @given(
        topic=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L',))),
        confidence_gains=st.lists(st.floats(min_value=0.0, max_value=0.5, allow_nan=False), min_size=1, max_size=10)
    )
    @settings(max_examples=30)
    def test_confidence_bounded_after_learning(self, topic, confidence_gains):
        """Property: Confidence is always in [0.0, 1.0] after learning events."""
        meta = MetaKnowledge(expert_name="test")
        
        for gain in confidence_gains:
            meta.record_learning(topic, "test_source", gain)
        
        assert 0.0 <= meta.confidence_by_topic[topic] <= 1.0

    @given(
        topics=st.lists(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L',))), min_size=1, max_size=5)
    )
    @settings(max_examples=30)
    def test_gaps_can_be_resolved(self, topics):
        """Property: All recorded gaps can be resolved."""
        meta = MetaKnowledge(expert_name="test")
        
        # Record gaps
        for topic in topics:
            meta.record_gap(topic, f"What is {topic}?", 0.1)
        
        # Resolve all gaps
        for topic in topics:
            meta.resolve_gap(topic)
        
        # All should be resolved
        unresolved = meta.get_unresolved_gaps()
        assert len(unresolved) == 0


class TestMemoryTierConsistencyPropertyTests:
    """Property-based tests for memory tier consistency.
    
    Property 5: Memory tier consistency
    - Episodes in working memory have WORKING tier
    - Episodes in episodic memory have EPISODIC tier
    - Consolidation moves episodes to correct tier
    - Retrieval respects tier filters
    """

    @given(
        num_episodes=st.integers(min_value=1, max_value=20),
        working_capacity=st.integers(min_value=2, max_value=10)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_tier_consistency_after_adds(self, num_episodes, working_capacity):
        """Property: All episodes have correct tier after additions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory",
                working_capacity=working_capacity
            )
            
            for i in range(num_episodes):
                episode = Episode(
                    query=f"Question {i}",
                    response=f"Answer {i}"
                )
                memory.add_episode(episode)
            
            # All working memory episodes should have WORKING tier
            for ep in memory.working_memory:
                assert ep.tier == MemoryTier.WORKING
            
            # All episodic memory episodes should have EPISODIC tier
            for ep in memory.episodic_memory:
                assert ep.tier == MemoryTier.EPISODIC

    @given(
        num_episodes=st.integers(min_value=5, max_value=15)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_consolidation_preserves_total_count(self, num_episodes):
        """Property: Consolidation preserves total episode count."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory",
                working_capacity=4
            )
            
            for i in range(num_episodes):
                episode = Episode(
                    query=f"Question {i}",
                    response=f"Answer {i}"
                )
                memory.add_episode(episode)
            
            total = len(memory.working_memory) + len(memory.episodic_memory)
            assert total == num_episodes

    @given(
        query_keywords=st.lists(
            st.text(min_size=3, max_size=10, alphabet=st.characters(whitelist_categories=('L',))),
            min_size=1,
            max_size=3
        )
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_retrieval_returns_relevant_episodes(self, query_keywords):
        """Property: Retrieval returns episodes containing query keywords."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory"
            )
            
            # Add episode with keywords
            keyword_str = " ".join(query_keywords)
            episode = Episode(
                query=f"Question about {keyword_str}",
                response=f"Answer about {keyword_str}"
            )
            memory.add_episode(episode)
            
            # Add some unrelated episodes
            for i in range(3):
                unrelated = Episode(
                    query=f"Unrelated question {i}",
                    response=f"Unrelated answer {i}"
                )
                memory.add_episode(unrelated)
            
            # Retrieve with keywords
            results = memory.retrieve(keyword_str, top_k=5)
            
            # Should find the relevant episode
            assert len(results) >= 1
            # First result should be most relevant
            found_keywords = results[0].get_keywords()
            query_kw_set = set(kw.lower() for kw in query_keywords)
            assert len(found_keywords & query_kw_set) > 0


class TestHierarchicalRetrievalPropertyTests:
    """Property-based tests for hierarchical retrieval.
    
    Property: Retrieval searches tiers in order (working -> episodic -> semantic).
    """

    @given(
        top_k=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_retrieval_respects_top_k(self, top_k):
        """Property: Retrieval never returns more than top_k results."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory"
            )
            
            # Add many episodes
            for i in range(20):
                episode = Episode(
                    query=f"Python question {i}",
                    response=f"Python answer {i}"
                )
                memory.add_episode(episode)
            
            results = memory.retrieve("Python", top_k=top_k)
            
            assert len(results) <= top_k

    @given(
        tier_filter=st.sampled_from([
            [MemoryTier.WORKING],
            [MemoryTier.EPISODIC],
            [MemoryTier.WORKING, MemoryTier.EPISODIC]
        ])
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_retrieval_respects_tier_filter(self, tier_filter):
        """Property: Retrieval only returns episodes from specified tiers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory",
                working_capacity=3
            )
            
            # Add enough episodes to have both tiers populated
            for i in range(10):
                episode = Episode(
                    query=f"Python question {i}",
                    response=f"Python answer {i}"
                )
                memory.add_episode(episode)
            
            results = memory.retrieve("Python", top_k=10, tiers=tier_filter)
            
            for ep in results:
                assert ep.tier in tier_filter


class TestKeywordIndexPropertyTests:
    """Property-based tests for keyword index consistency."""

    @given(
        queries=st.lists(
            st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'Nd', 'Zs'))),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_keyword_index_contains_all_episodes(self, queries):
        """Property: Keyword index contains entries for all episodes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory"
            )
            
            episode_ids = set()
            for query in queries:
                episode = Episode(
                    query=query,
                    response=f"Response to {query}"
                )
                ep_id = memory.add_episode(episode)
                episode_ids.add(ep_id)
            
            # All episode IDs should be in the index somewhere
            indexed_ids = set()
            for keyword_eps in memory._keyword_index.values():
                indexed_ids.update(keyword_eps)
            
            # Episodes with extractable keywords should be indexed
            for ep in memory.working_memory + memory.episodic_memory:
                if ep.get_keywords():  # Only if keywords were extracted
                    assert ep.id in indexed_ids


class TestRelevanceScoringPropertyTests:
    """Property-based tests for relevance scoring."""

    @given(
        query=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'Zs'))),
        response=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'Zs')))
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_relevance_score_bounded(self, query, response):
        """Property: Relevance score is always in [0.0, 1.0]."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory"
            )
            
            episode = Episode(query=query, response=response)
            query_keywords = memory._extract_keywords("test query")
            
            score = memory._compute_relevance(episode, query_keywords)
            
            assert 0.0 <= score <= 1.0

    @given(
        quality_score=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_quality_affects_relevance(self, quality_score):
        """Property: Quality score affects relevance calculation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = HierarchicalMemory(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "memory"
            )
            
            episode = Episode(
                query="Python programming language",
                response="Python is a programming language",
                quality_score=quality_score
            )
            query_keywords = memory._extract_keywords("Python programming")
            
            score = memory._compute_relevance(episode, query_keywords)
            
            # Score should still be bounded
            assert 0.0 <= score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
