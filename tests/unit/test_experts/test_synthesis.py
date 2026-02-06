"""Unit tests for the Knowledge Synthesis module - no API calls.

Tests the expert consciousness system including beliefs, knowledge gaps,
worldview management, and synthesis operations.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.synthesis import Belief, KnowledgeGap, KnowledgeSynthesizer, Worldview


class TestBelief:
    """Test Belief dataclass."""

    def test_create_belief(self):
        """Test creating a basic belief."""
        now = datetime.utcnow()
        belief = Belief(
            topic="Python Performance",
            statement="Python 3.12+ has significant performance improvements",
            confidence=0.85,
            evidence=["python-release-notes.md", "benchmark-results.md"],
            formed_at=now,
            last_updated=now,
        )
        assert belief.topic == "Python Performance"
        assert belief.confidence == 0.85
        assert len(belief.evidence) == 2

    def test_belief_to_dict(self):
        """Test belief serialization to dict."""
        now = datetime.utcnow()
        belief = Belief(
            topic="Testing",
            statement="Unit tests catch bugs early",
            confidence=0.95,
            evidence=["testing-guide.md"],
            formed_at=now,
            last_updated=now,
        )
        data = belief.to_dict()
        assert data["topic"] == "Testing"
        assert data["confidence"] == 0.95
        assert "formed_at" in data
        assert isinstance(data["formed_at"], str)  # ISO format

    def test_belief_from_dict(self):
        """Test belief deserialization from dict."""
        now = datetime.utcnow()
        data = {
            "topic": "Architecture",
            "statement": "Microservices add complexity",
            "confidence": 0.75,
            "evidence": ["arch-doc.md"],
            "formed_at": now.isoformat(),
            "last_updated": now.isoformat(),
        }
        belief = Belief.from_dict(data)
        assert belief.topic == "Architecture"
        assert belief.confidence == 0.75
        assert isinstance(belief.formed_at, datetime)

    def test_belief_roundtrip(self):
        """Test belief serialization roundtrip."""
        now = datetime.utcnow()
        original = Belief(
            topic="Roundtrip Test",
            statement="Data survives serialization",
            confidence=0.99,
            evidence=["test.md"],
            formed_at=now,
            last_updated=now,
        )
        data = original.to_dict()
        restored = Belief.from_dict(data)
        assert restored.topic == original.topic
        assert restored.statement == original.statement
        assert restored.confidence == original.confidence

    def test_belief_confidence_bounds(self):
        """Test belief with edge confidence values."""
        now = datetime.utcnow()
        # Zero confidence
        belief_zero = Belief(
            topic="Uncertain",
            statement="Not sure about this",
            confidence=0.0,
            evidence=[],
            formed_at=now,
            last_updated=now,
        )
        assert belief_zero.confidence == 0.0

        # Full confidence
        belief_full = Belief(
            topic="Certain",
            statement="Absolutely sure",
            confidence=1.0,
            evidence=["proof.md"],
            formed_at=now,
            last_updated=now,
        )
        assert belief_full.confidence == 1.0


class TestKnowledgeGap:
    """Test KnowledgeGap dataclass."""

    def test_create_knowledge_gap(self):
        """Test creating a knowledge gap."""
        now = datetime.utcnow()
        gap = KnowledgeGap(
            topic="Kubernetes Networking",
            questions=["How does CNI work?", "What are network policies?"],
            priority=4,
            identified_at=now,
        )
        assert gap.topic == "Kubernetes Networking"
        assert len(gap.questions) == 2
        assert gap.priority == 4

    def test_knowledge_gap_to_dict(self):
        """Test knowledge gap serialization."""
        now = datetime.utcnow()
        gap = KnowledgeGap(topic="Security", questions=["What is zero trust?"], priority=5, identified_at=now)
        data = gap.to_dict()
        assert data["topic"] == "Security"
        assert data["priority"] == 5
        assert isinstance(data["identified_at"], str)

    def test_knowledge_gap_from_dict(self):
        """Test knowledge gap deserialization."""
        now = datetime.utcnow()
        data = {
            "topic": "ML Ops",
            "questions": ["How to deploy models?", "What is model drift?"],
            "priority": 3,
            "identified_at": now.isoformat(),
        }
        gap = KnowledgeGap.from_dict(data)
        assert gap.topic == "ML Ops"
        assert len(gap.questions) == 2
        assert isinstance(gap.identified_at, datetime)

    def test_knowledge_gap_priority_range(self):
        """Test knowledge gap with various priorities."""
        now = datetime.utcnow()
        for priority in [1, 2, 3, 4, 5]:
            gap = KnowledgeGap(
                topic=f"Priority {priority}", questions=["Question?"], priority=priority, identified_at=now
            )
            assert gap.priority == priority


class TestWorldview:
    """Test Worldview dataclass."""

    def test_create_empty_worldview(self):
        """Test creating an empty worldview."""
        worldview = Worldview(expert_name="Test Expert", domain="Testing")
        assert worldview.expert_name == "Test Expert"
        assert worldview.domain == "Testing"
        assert worldview.beliefs == []
        assert worldview.knowledge_gaps == []
        assert worldview.synthesis_count == 0

    def test_create_worldview_with_beliefs(self):
        """Test creating worldview with beliefs."""
        now = datetime.utcnow()
        beliefs = [
            Belief(
                topic="Topic 1",
                statement="Statement 1",
                confidence=0.8,
                evidence=["doc1.md"],
                formed_at=now,
                last_updated=now,
            )
        ]
        worldview = Worldview(expert_name="Expert", domain="Domain", beliefs=beliefs, synthesis_count=1)
        assert len(worldview.beliefs) == 1
        assert worldview.synthesis_count == 1

    def test_worldview_to_dict(self):
        """Test worldview serialization."""
        now = datetime.utcnow()
        worldview = Worldview(expert_name="Serialization Expert", domain="Data", last_synthesis=now, synthesis_count=5)
        data = worldview.to_dict()
        assert data["expert_name"] == "Serialization Expert"
        assert data["synthesis_count"] == 5
        assert data["last_synthesis"] is not None

    def test_worldview_from_dict(self):
        """Test worldview deserialization."""
        now = datetime.utcnow()
        data = {
            "expert_name": "Restored Expert",
            "domain": "Restoration",
            "beliefs": [],
            "knowledge_gaps": [],
            "last_synthesis": now.isoformat(),
            "synthesis_count": 3,
        }
        worldview = Worldview.from_dict(data)
        assert worldview.expert_name == "Restored Expert"
        assert worldview.synthesis_count == 3
        assert isinstance(worldview.last_synthesis, datetime)

    def test_worldview_save_and_load(self):
        """Test worldview persistence to file."""
        now = datetime.utcnow()
        worldview = Worldview(
            expert_name="Persistent Expert",
            domain="Persistence",
            beliefs=[
                Belief(
                    topic="Persistence",
                    statement="Data should survive restarts",
                    confidence=0.99,
                    evidence=["persistence.md"],
                    formed_at=now,
                    last_updated=now,
                )
            ],
            last_synthesis=now,
            synthesis_count=1,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            worldview.save(path)
            loaded = Worldview.load(path)
            assert loaded.expert_name == worldview.expert_name
            assert len(loaded.beliefs) == 1
            assert loaded.beliefs[0].topic == "Persistence"
        finally:
            path.unlink()

    def test_worldview_with_gaps(self):
        """Test worldview with knowledge gaps."""
        now = datetime.utcnow()
        gaps = [
            KnowledgeGap(
                topic="Unknown Area", questions=["What is this?", "How does it work?"], priority=4, identified_at=now
            )
        ]
        worldview = Worldview(expert_name="Curious Expert", domain="Learning", knowledge_gaps=gaps)
        assert len(worldview.knowledge_gaps) == 1
        assert worldview.knowledge_gaps[0].priority == 4


class TestKnowledgeSynthesizer:
    """Test KnowledgeSynthesizer class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock OpenAI client."""
        client = MagicMock()
        client.chat = MagicMock()
        client.chat.completions = MagicMock()
        return client

    @pytest.fixture
    def synthesizer(self, mock_client):
        """Create a synthesizer with mock client."""
        return KnowledgeSynthesizer(mock_client)

    def test_synthesizer_init(self, mock_client):
        """Test synthesizer initialization."""
        synthesizer = KnowledgeSynthesizer(mock_client)
        assert synthesizer.client == mock_client

    def test_build_synthesis_prompt_basic(self, synthesizer):
        """Test building synthesis prompt without existing worldview."""
        documents = [{"filename": "test.md", "content": "Test content here"}]
        prompt = synthesizer._build_synthesis_prompt(
            expert_name="Test Expert", domain="Testing", documents=documents, existing_worldview=None
        )
        assert "Test Expert" in prompt
        assert "Testing" in prompt
        assert "test.md" in prompt
        assert "KEY INSIGHTS" in prompt
        assert "BELIEF FORMATION" in prompt

    def test_build_synthesis_prompt_with_worldview(self, synthesizer):
        """Test building synthesis prompt with existing worldview."""
        now = datetime.utcnow()
        worldview = Worldview(
            expert_name="Existing Expert",
            domain="Domain",
            beliefs=[
                Belief(
                    topic="Prior Knowledge",
                    statement="I already know this",
                    confidence=0.9,
                    evidence=["old.md"],
                    formed_at=now,
                    last_updated=now,
                )
            ],
        )
        documents = [{"filename": "new.md", "content": "New content"}]
        prompt = synthesizer._build_synthesis_prompt(
            expert_name="Existing Expert", domain="Domain", documents=documents, existing_worldview=worldview
        )
        assert "EXISTING BELIEFS" in prompt
        assert "I already know this" in prompt

    def test_build_synthesis_prompt_truncates_long_docs(self, synthesizer):
        """Test that long documents are truncated in prompt."""
        long_content = "x" * 5000
        documents = [{"filename": "long.md", "content": long_content}]
        prompt = synthesizer._build_synthesis_prompt(
            expert_name="Expert", domain="Domain", documents=documents, existing_worldview=None
        )
        assert "[...document continues...]" in prompt

    def test_update_worldview_adds_new_beliefs(self, synthesizer):
        """Test that new beliefs are added to worldview."""
        now = datetime.utcnow()
        existing = Worldview(expert_name="Expert", domain="Domain", beliefs=[], synthesis_count=0)
        new_beliefs = [
            Belief(
                topic="New Topic",
                statement="New belief",
                confidence=0.8,
                evidence=["new.md"],
                formed_at=now,
                last_updated=now,
            )
        ]
        updated = synthesizer._update_worldview(existing, new_beliefs, [])
        assert len(updated.beliefs) == 1
        assert updated.synthesis_count == 1

    def test_update_worldview_updates_existing_beliefs(self, synthesizer):
        """Test that existing beliefs are updated."""
        now = datetime.utcnow()
        old_time = now - timedelta(days=1)
        existing = Worldview(
            expert_name="Expert",
            domain="Domain",
            beliefs=[
                Belief(
                    topic="Topic",
                    statement="Old statement",
                    confidence=0.5,
                    evidence=["old.md"],
                    formed_at=old_time,
                    last_updated=old_time,
                )
            ],
            synthesis_count=1,
        )
        new_beliefs = [
            Belief(
                topic="Topic",  # Same topic
                statement="Updated statement",
                confidence=0.9,
                evidence=["new.md"],
                formed_at=now,
                last_updated=now,
            )
        ]
        updated = synthesizer._update_worldview(existing, new_beliefs, [])
        assert len(updated.beliefs) == 1  # Still one belief
        assert updated.beliefs[0].statement == "Updated statement"
        assert updated.beliefs[0].confidence == 0.9
        assert "old.md" in updated.beliefs[0].evidence
        assert "new.md" in updated.beliefs[0].evidence

    def test_update_worldview_adds_gaps(self, synthesizer):
        """Test that knowledge gaps are added."""
        now = datetime.utcnow()
        existing = Worldview(expert_name="Expert", domain="Domain", knowledge_gaps=[])
        new_gaps = [KnowledgeGap(topic="Unknown", questions=["What is this?"], priority=3, identified_at=now)]
        updated = synthesizer._update_worldview(existing, [], new_gaps)
        assert len(updated.knowledge_gaps) == 1

    @pytest.mark.asyncio
    async def test_synthesize_no_documents(self, synthesizer):
        """Test synthesis with no documents returns error."""
        result = await synthesizer.synthesize_new_knowledge(expert_name="Expert", domain="Domain", new_documents=[])
        assert result["success"] is False
        assert "No documents" in result["error"]

    @pytest.mark.asyncio
    async def test_synthesize_with_content(self, synthesizer, mock_client):
        """Test synthesis with document content provided."""
        # Mock the API responses
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
## 1. KEY INSIGHTS
Important finding about testing.

## 2. BELIEF FORMATION
I believe testing is important (Confidence: 90%)
"""
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Second call for parsing
        parse_response = MagicMock()
        parse_response.choices = [MagicMock()]
        parse_response.choices[0].message.content = json.dumps(
            {
                "beliefs": [
                    {
                        "topic": "Testing",
                        "statement": "Testing is important",
                        "confidence": 0.9,
                        "evidence": ["test.md"],
                    }
                ],
                "knowledge_gaps": [],
            }
        )
        mock_client.chat.completions.create = AsyncMock(side_effect=[mock_response, parse_response])

        result = await synthesizer.synthesize_new_knowledge(
            expert_name="Test Expert", domain="Testing", new_documents=[{"path": "test.md", "content": "Test content"}]
        )
        assert result["success"] is True
        assert result["documents_processed"] == 1
        assert "worldview" in result

    @pytest.mark.asyncio
    async def test_generate_worldview_document(self, synthesizer):
        """Test generating markdown worldview document."""
        now = datetime.utcnow()
        worldview = Worldview(
            expert_name="Doc Expert",
            domain="Documentation",
            beliefs=[
                Belief(
                    topic="Docs",
                    statement="Good docs matter",
                    confidence=0.95,
                    evidence=["docs.md"],
                    formed_at=now,
                    last_updated=now,
                )
            ],
            knowledge_gaps=[KnowledgeGap(topic="Unknown", questions=["What else?"], priority=3, identified_at=now)],
            last_synthesis=now,
            synthesis_count=1,
        )
        doc = await synthesizer.generate_worldview_document(worldview, "Expert reflection text")
        assert "# Worldview: Doc Expert" in doc
        assert "Documentation" in doc
        assert "Good docs matter" in doc
        assert "95%" in doc
        assert "Knowledge Gaps" in doc


class TestSynthesisEdgeCases:
    """Test edge cases in synthesis."""

    def test_belief_empty_evidence(self):
        """Test belief with no evidence."""
        now = datetime.utcnow()
        belief = Belief(
            topic="Speculation", statement="Just a guess", confidence=0.1, evidence=[], formed_at=now, last_updated=now
        )
        data = belief.to_dict()
        assert data["evidence"] == []

    def test_knowledge_gap_empty_questions(self):
        """Test knowledge gap with no questions."""
        now = datetime.utcnow()
        gap = KnowledgeGap(topic="Vague Area", questions=[], priority=1, identified_at=now)
        data = gap.to_dict()
        assert data["questions"] == []

    def test_worldview_no_synthesis_date(self):
        """Test worldview without synthesis date."""
        worldview = Worldview(expert_name="New Expert", domain="New Domain")
        data = worldview.to_dict()
        assert data["last_synthesis"] is None

    def test_worldview_from_dict_no_synthesis(self):
        """Test loading worldview without synthesis date."""
        data = {
            "expert_name": "Expert",
            "domain": "Domain",
            "beliefs": [],
            "knowledge_gaps": [],
            "last_synthesis": None,
            "synthesis_count": 0,
        }
        worldview = Worldview.from_dict(data)
        assert worldview.last_synthesis is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
