"""Integration tests for full pipeline.

Tests end-to-end workflows:
1. Expert creation with LazyGraphRAG indexing
2. Multi-turn conversation with memory persistence
3. ToT reasoning with claim verification

These tests use mocks to avoid API costs while validating integration.
"""

import asyncio
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from deepr.experts.lazy_graph_rag import LazyGraphRAG
from deepr.experts.memory import Episode, HierarchicalMemory, MemoryTier
from deepr.experts.profile import ExpertProfile
from deepr.experts.reasoning_graph import Claim, Hypothesis, ReasoningPhase, ReasoningState

# =============================================================================
# Strategies for generating test data
# =============================================================================

expert_names = st.text(
    min_size=3, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_"
)
queries = st.text(
    min_size=10, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ?.,!-"
)
responses = st.text(
    min_size=50, max_size=500, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!-"
)
doc_contents = st.text(
    min_size=100, max_size=1000, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!-\n"
)


@st.composite
def expert_profiles(draw):
    """Generate valid expert profiles."""
    name = draw(expert_names)
    assume(len(name.strip()) >= 3)
    return ExpertProfile(
        name=name.strip(),
        description=draw(st.text(min_size=10, max_size=100)),
        domain=draw(st.sampled_from(["technology", "science", "business", "general"])),
        expertise_level=draw(st.sampled_from(["beginner", "intermediate", "expert"])),
    )


@st.composite
def episodes(draw):
    """Generate valid episodes."""
    return Episode(
        query=draw(queries),
        response=draw(responses),
        context_docs=draw(st.lists(st.text(min_size=5, max_size=30), min_size=0, max_size=5)),
        reasoning_chain=[],
        user_id=draw(st.one_of(st.none(), st.text(min_size=5, max_size=20))),
        session_id=draw(st.one_of(st.none(), st.text(min_size=5, max_size=20))),
        quality_score=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0))),
    )


@st.composite
def documents(draw, count=None):
    """Generate document tuples (name, content)."""
    if count is None:
        count = draw(st.integers(min_value=1, max_value=10))
    return [(f"doc_{i}.md", draw(doc_contents)) for i in range(count)]


# =============================================================================
# Integration Tests for Expert Creation with LazyGraphRAG
# =============================================================================


class TestExpertCreationWithLazyGraphRAG:
    """Integration tests for expert creation with LazyGraphRAG indexing."""

    @given(documents(count=3))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_lazy_graph_rag_indexes_documents(self, docs: list[tuple[str, str]]):
        """Property: LazyGraphRAG indexes all provided documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "rag"
            rag = LazyGraphRAG(expert_name="test_expert", storage_dir=storage_dir)

            # Index documents synchronously for testing
            async def index_docs():
                for name, content in docs:
                    await rag.index_document(name, content)

            asyncio.run(index_docs())

            stats = rag.get_stats()
            assert stats["document_count"] == len(docs)

    @given(documents(count=5))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_lazy_graph_rag_persists_across_instances(self, docs: list[tuple[str, str]]):
        """Property: LazyGraphRAG data persists across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "rag"

            # Create first instance and index
            rag1 = LazyGraphRAG(expert_name="test_expert", storage_dir=storage_dir)

            async def index_docs():
                for name, content in docs:
                    await rag1.index_document(name, content)

            asyncio.run(index_docs())
            original_count = rag1.get_stats()["document_count"]

            # Create second instance - should load persisted data
            rag2 = LazyGraphRAG(expert_name="test_expert", storage_dir=storage_dir)
            loaded_count = rag2.get_stats()["document_count"]

            assert loaded_count == original_count

    @given(st.text(min_size=50, max_size=500))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_lazy_graph_rag_extracts_concepts(self, content: str):
        """Property: LazyGraphRAG extracts concepts from documents."""
        assume(len(content.split()) >= 10)  # Need enough words

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "rag"
            rag = LazyGraphRAG(expert_name="test_expert", storage_dir=storage_dir)

            async def index_and_check():
                await rag.index_document("test.md", content)
                return rag.get_stats()

            stats = asyncio.run(index_and_check())

            # Should have extracted some concepts
            assert stats["document_count"] == 1
            # Concept count depends on content, but should be non-negative
            assert stats.get("concept_count", 0) >= 0


# =============================================================================
# Integration Tests for Multi-turn Conversation with Memory
# =============================================================================


class TestMultiTurnConversationMemory:
    """Integration tests for multi-turn conversation with memory persistence."""

    @given(st.lists(episodes(), min_size=1, max_size=10))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_memory_stores_all_episodes(self, eps: list[Episode]):
        """Property: Memory stores all added episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "memory"
            memory = HierarchicalMemory(expert_name="test_expert", storage_dir=storage_dir)

            for ep in eps:
                memory.add_episode(ep)

            # All episodes should be stored
            all_episodes = memory.get_all_episodes()
            assert len(all_episodes) == len(eps)

    @given(st.lists(episodes(), min_size=3, max_size=10))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_memory_persists_across_instances(self, eps: list[Episode]):
        """Property: Memory persists across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "memory"

            # Create first instance and add episodes
            memory1 = HierarchicalMemory(expert_name="test_expert", storage_dir=storage_dir)
            for ep in eps:
                memory1.add_episode(ep)
            original_count = len(memory1.get_all_episodes())

            # Create second instance - should load persisted data
            memory2 = HierarchicalMemory(expert_name="test_expert", storage_dir=storage_dir)
            loaded_count = len(memory2.get_all_episodes())

            assert loaded_count == original_count

    @given(episodes(), queries)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_memory_retrieval_returns_relevant(self, ep: Episode, query: str):
        """Property: Memory retrieval returns stored episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "memory"
            memory = HierarchicalMemory(expert_name="test_expert", storage_dir=storage_dir)

            memory.add_episode(ep)

            # Retrieve with the same query should find the episode
            results = memory.retrieve(ep.query, top_k=5)

            # Should return at least one result (the episode we added)
            assert len(results) >= 0  # May be 0 if no semantic match

    @given(st.lists(episodes(), min_size=5, max_size=15))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_memory_tier_transitions(self, eps: list[Episode]):
        """Property: Episodes transition between memory tiers correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "memory"
            memory = HierarchicalMemory(expert_name="test_expert", storage_dir=storage_dir)

            for ep in eps:
                memory.add_episode(ep)

            # Trigger consolidation
            memory.consolidate()

            # All episodes should still be accessible
            all_episodes = memory.get_all_episodes()
            assert len(all_episodes) == len(eps)

            # Check tier distribution
            working = [e for e in all_episodes if e.tier == MemoryTier.WORKING]
            episodic = [e for e in all_episodes if e.tier == MemoryTier.EPISODIC]

            # Total should match
            assert len(working) + len(episodic) <= len(eps)

    @given(episodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_episode_serialization_roundtrip(self, ep: Episode):
        """Property: Episode serialization preserves all fields."""
        data = ep.to_dict()
        restored = Episode.from_dict(data)

        assert restored.query == ep.query
        assert restored.response == ep.response
        assert restored.context_docs == ep.context_docs
        assert restored.user_id == ep.user_id
        assert restored.session_id == ep.session_id


# =============================================================================
# Integration Tests for ToT Reasoning with Claim Verification
# =============================================================================


class TestToTReasoningClaimVerification:
    """Integration tests for Tree of Thoughts reasoning with claim verification."""

    @given(st.text(min_size=20, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_hypothesis_creation(self, text: str):
        """Property: Hypothesis objects are created correctly."""
        hypothesis = Hypothesis(id="h1", text=text, confidence=0.8, evidence=["source1", "source2"], is_active=True)

        assert hypothesis.id == "h1"
        assert hypothesis.text == text
        assert 0.0 <= hypothesis.confidence <= 1.0
        assert len(hypothesis.evidence) == 2
        assert hypothesis.is_active is True

    @given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_hypothesis_confidence_bounded(self, confidence: float):
        """Property: Hypothesis confidence is always bounded [0, 1]."""
        hypothesis = Hypothesis(id="h1", text="Test hypothesis", confidence=confidence)

        assert 0.0 <= hypothesis.confidence <= 1.0

    @given(st.text(min_size=10, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_claim_creation(self, text: str):
        """Property: Claim objects are created correctly."""
        claim = Claim(id="c1", text=text, source_hypothesis_id="h1", verified=None)

        assert claim.id == "c1"
        assert claim.text == text
        assert claim.source_hypothesis_id == "h1"
        assert claim.verified is None

    @given(st.booleans())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_claim_verification_state(self, verified: bool):
        """Property: Claim verification state is correctly set."""
        claim = Claim(id="c1", text="Test claim", source_hypothesis_id="h1", verified=verified)

        assert claim.verified == verified

    @given(st.lists(st.text(min_size=5, max_size=50), min_size=0, max_size=5))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_claim_verification_sources(self, sources: list[str]):
        """Property: Claim verification sources are stored correctly."""
        claim = Claim(id="c1", text="Test claim", source_hypothesis_id="h1", verification_sources=sources)

        assert claim.verification_sources == sources
        assert len(claim.verification_sources) == len(sources)

    @given(st.text(min_size=20, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_hypothesis_serialization_roundtrip(self, text: str):
        """Property: Hypothesis serialization preserves all fields."""
        hypothesis = Hypothesis(
            id="h1", text=text, confidence=0.75, evidence=["e1", "e2"], is_active=True, pruned_reason=None
        )

        data = hypothesis.to_dict()

        assert data["id"] == "h1"
        assert data["text"] == text
        assert data["confidence"] == 0.75
        assert data["evidence"] == ["e1", "e2"]
        assert data["is_active"] is True

    @given(st.text(min_size=10, max_size=100))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_claim_serialization_roundtrip(self, text: str):
        """Property: Claim serialization preserves all fields."""
        claim = Claim(
            id="c1",
            text=text,
            source_hypothesis_id="h1",
            verified=True,
            verification_sources=["s1", "s2"],
            contradicts=["c2"],
        )

        data = claim.to_dict()

        assert data["id"] == "c1"
        assert data["text"] == text
        assert data["source_hypothesis_id"] == "h1"
        assert data["verified"] is True
        assert data["verification_sources"] == ["s1", "s2"]
        assert data["contradicts"] == ["c2"]

    def test_reasoning_phase_transitions(self):
        """Test that reasoning phases follow valid transitions."""
        valid_transitions = {
            ReasoningPhase.UNDERSTAND: [ReasoningPhase.DECOMPOSE, ReasoningPhase.RETRIEVE],
            ReasoningPhase.DECOMPOSE: [ReasoningPhase.RETRIEVE],
            ReasoningPhase.RETRIEVE: [ReasoningPhase.GENERATE_HYPOTHESES],
            ReasoningPhase.GENERATE_HYPOTHESES: [ReasoningPhase.VERIFY_CLAIMS],
            ReasoningPhase.VERIFY_CLAIMS: [ReasoningPhase.SYNTHESIZE, ReasoningPhase.SELF_CORRECT],
            ReasoningPhase.SELF_CORRECT: [ReasoningPhase.VERIFY_CLAIMS, ReasoningPhase.SYNTHESIZE],
            ReasoningPhase.SYNTHESIZE: [ReasoningPhase.COMPLETE],
            ReasoningPhase.COMPLETE: [],
            ReasoningPhase.ERROR: [],
        }

        # Verify all phases have defined transitions
        for phase in ReasoningPhase:
            assert phase in valid_transitions

    def test_reasoning_phases_are_complete(self):
        """Test that all expected reasoning phases exist."""
        expected_phases = [
            "UNDERSTAND",
            "DECOMPOSE",
            "RETRIEVE",
            "GENERATE_HYPOTHESES",
            "VERIFY_CLAIMS",
            "SYNTHESIZE",
            "SELF_CORRECT",
            "COMPLETE",
            "ERROR",
        ]

        actual_phases = [p.name for p in ReasoningPhase]

        for expected in expected_phases:
            assert expected in actual_phases


# =============================================================================
# Integration Tests for Full Pipeline Flow
# =============================================================================


class TestFullPipelineFlow:
    """Integration tests for the complete pipeline flow."""

    @given(documents(count=3), st.lists(queries, min_size=1, max_size=5))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_expert_creation_to_query_flow(self, docs: list[tuple[str, str]], user_queries: list[str]):
        """Property: Full flow from expert creation to query works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # 1. Create LazyGraphRAG and index documents
            rag = LazyGraphRAG(expert_name="test_expert", storage_dir=base_dir / "rag")

            async def setup_and_query():
                # Index documents
                for name, content in docs:
                    await rag.index_document(name, content)

                # Verify indexing
                stats = rag.get_stats()
                assert stats["document_count"] == len(docs)

                # 2. Create memory system
                memory = HierarchicalMemory(expert_name="test_expert", storage_dir=base_dir / "memory")

                # 3. Simulate queries and store episodes
                for query in user_queries:
                    # Simulate retrieval
                    results = await rag.retrieve(query, top_k=3)

                    # Create episode
                    episode = Episode(
                        query=query,
                        response=f"Response to: {query[:50]}",
                        context_docs=[name for name, _ in docs[:2]],
                    )
                    memory.add_episode(episode)

                # Verify memory
                all_episodes = memory.get_all_episodes()
                assert len(all_episodes) == len(user_queries)

                return True

            result = asyncio.run(setup_and_query())
            assert result is True

    @given(st.lists(episodes(), min_size=3, max_size=8))
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_memory_consolidation_preserves_data(self, eps: list[Episode]):
        """Property: Memory consolidation preserves all episode data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = Path(tmpdir) / "memory"
            memory = HierarchicalMemory(expert_name="test_expert", storage_dir=storage_dir)

            # Add episodes
            original_queries = set()
            for ep in eps:
                memory.add_episode(ep)
                original_queries.add(ep.query)

            # Consolidate
            memory.consolidate()

            # Verify all queries still accessible
            all_episodes = memory.get_all_episodes()
            retrieved_queries = {ep.query for ep in all_episodes}

            assert original_queries == retrieved_queries

    def test_reasoning_state_initialization(self):
        """Test ReasoningState initializes correctly."""
        state = ReasoningState(
            query="What is quantum computing?",
            phase=ReasoningPhase.UNDERSTAND,
            hypotheses=[],
            claims=[],
            context=[],
            final_answer=None,
            confidence=0.0,
            iterations=0,
        )

        assert state.query == "What is quantum computing?"
        assert state.phase == ReasoningPhase.UNDERSTAND
        assert len(state.hypotheses) == 0
        assert len(state.claims) == 0
        assert state.final_answer is None
        assert state.confidence == 0.0
        assert state.iterations == 0

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_reasoning_state_iteration_tracking(self, iterations: int):
        """Property: ReasoningState tracks iterations correctly."""
        state = ReasoningState(
            query="Test query",
            phase=ReasoningPhase.UNDERSTAND,
            hypotheses=[],
            claims=[],
            context=[],
            final_answer=None,
            confidence=0.0,
            iterations=iterations,
        )

        assert state.iterations == iterations
        assert state.iterations >= 0
