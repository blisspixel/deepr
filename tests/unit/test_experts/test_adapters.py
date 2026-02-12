"""Unit tests for adapter methods on existing Belief/KnowledgeGap classes.

Tests to_claim() and to_gap() adapters that bridge old types to canonical contracts.
"""

import pytest
from datetime import datetime, timezone

from deepr.core.contracts import Claim, Gap, TrustClass


class TestBeliefsToClaim:
    """Test beliefs.Belief.to_claim() adapter."""

    def test_preserves_statement(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="Python is great", confidence=0.9, domain="python")
        claim = b.to_claim()
        assert claim.statement == "Python is great"

    def test_preserves_domain(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="test", confidence=0.5, domain="testing")
        claim = b.to_claim()
        assert claim.domain == "testing"

    def test_preserves_id(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="test", confidence=0.5, domain="d")
        claim = b.to_claim()
        assert claim.id == b.id

    def test_applies_confidence_decay(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="test", confidence=0.9, domain="d")
        claim = b.to_claim()
        # Freshly created, so decay should be minimal
        assert 0.89 <= claim.confidence <= 0.91

    def test_converts_evidence_refs_to_sources(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="test", confidence=0.5, evidence_refs=["doc1", "doc2"], domain="d")
        claim = b.to_claim()
        assert len(claim.sources) == 2
        assert claim.sources[0].title == "doc1"
        assert claim.sources[0].trust_class == TrustClass.TERTIARY

    def test_preserves_contradictions(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="test", confidence=0.5, domain="d",
                   contradictions_with=["abc", "def"])
        claim = b.to_claim()
        assert claim.contradicts == ["abc", "def"]

    def test_source_type_in_tags(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="test", confidence=0.5, domain="d", source_type="inferred")
        claim = b.to_claim()
        assert "inferred" in claim.tags

    def test_preserves_timestamps(self):
        from deepr.experts.beliefs import Belief
        ts = datetime(2025, 3, 15, tzinfo=timezone.utc)
        b = Belief(claim="test", confidence=0.5, domain="d",
                   created_at=ts, updated_at=ts)
        claim = b.to_claim()
        assert claim.created_at == ts
        assert claim.updated_at == ts


class TestSynthesisBeliefToClaim:
    """Test synthesis.Belief.to_claim() adapter."""

    def test_preserves_statement(self):
        from deepr.experts.synthesis import Belief
        b = Belief(topic="AI", statement="AI is transformative",
                   confidence=0.85, evidence=["paper.pdf"],
                   formed_at=datetime.now(timezone.utc),
                   last_updated=datetime.now(timezone.utc))
        claim = b.to_claim()
        assert claim.statement == "AI is transformative"

    def test_uses_topic_as_domain(self):
        from deepr.experts.synthesis import Belief
        b = Belief(topic="ML", statement="test", confidence=0.5,
                   evidence=[], formed_at=datetime.now(timezone.utc),
                   last_updated=datetime.now(timezone.utc))
        claim = b.to_claim()
        assert claim.domain == "ML"

    def test_converts_evidence_to_sources(self):
        from deepr.experts.synthesis import Belief
        b = Belief(topic="t", statement="s", confidence=0.5,
                   evidence=["src1.md", "src2.md"],
                   formed_at=datetime.now(timezone.utc),
                   last_updated=datetime.now(timezone.utc))
        claim = b.to_claim()
        assert len(claim.sources) == 2
        assert claim.sources[0].title == "src1.md"

    def test_generates_content_hash_id(self):
        from deepr.experts.synthesis import Belief
        b = Belief(topic="t", statement="s", confidence=0.5,
                   evidence=[], formed_at=datetime.now(timezone.utc),
                   last_updated=datetime.now(timezone.utc))
        claim = b.to_claim()
        assert len(claim.id) == 12


class TestSynthesisKnowledgeGapToGap:
    """Test synthesis.KnowledgeGap.to_gap() adapter."""

    def test_preserves_topic(self):
        from deepr.experts.synthesis import KnowledgeGap
        kg = KnowledgeGap(topic="quantum", questions=["What?"],
                          priority=4, identified_at=datetime.now(timezone.utc))
        gap = kg.to_gap()
        assert gap.topic == "quantum"

    def test_preserves_questions(self):
        from deepr.experts.synthesis import KnowledgeGap
        kg = KnowledgeGap(topic="t", questions=["Q1", "Q2"],
                          priority=3, identified_at=datetime.now(timezone.utc))
        gap = kg.to_gap()
        assert gap.questions == ["Q1", "Q2"]

    def test_preserves_priority(self):
        from deepr.experts.synthesis import KnowledgeGap
        kg = KnowledgeGap(topic="t", questions=[], priority=5,
                          identified_at=datetime.now(timezone.utc))
        gap = kg.to_gap()
        assert gap.priority == 5

    def test_generates_content_hash_id(self):
        from deepr.experts.synthesis import KnowledgeGap
        kg = KnowledgeGap(topic="t", questions=[], priority=3,
                          identified_at=datetime.now(timezone.utc))
        gap = kg.to_gap()
        assert len(gap.id) == 12


class TestMetacognitionKnowledgeGapToGap:
    """Test metacognition.KnowledgeGap.to_gap() adapter."""

    def test_preserves_topic(self):
        from deepr.experts.metacognition import KnowledgeGap
        kg = KnowledgeGap(topic="NLP", first_encountered=datetime.now(timezone.utc),
                          times_asked=3, research_triggered=False)
        gap = kg.to_gap()
        assert gap.topic == "NLP"

    def test_uses_times_asked(self):
        from deepr.experts.metacognition import KnowledgeGap
        kg = KnowledgeGap(topic="t", first_encountered=datetime.now(timezone.utc),
                          times_asked=7, research_triggered=False)
        gap = kg.to_gap()
        assert gap.times_asked == 7

    def test_priority_capped_at_5(self):
        from deepr.experts.metacognition import KnowledgeGap
        kg = KnowledgeGap(topic="t", first_encountered=datetime.now(timezone.utc),
                          times_asked=100, research_triggered=False)
        gap = kg.to_gap()
        assert gap.priority == 5

    def test_filled_when_research_completed(self):
        from deepr.experts.metacognition import KnowledgeGap
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        kg = KnowledgeGap(topic="t", first_encountered=ts, times_asked=2,
                          research_triggered=True, research_date=ts,
                          confidence_after=0.8)
        gap = kg.to_gap()
        assert gap.filled is True
        assert gap.filled_at == ts

    def test_not_filled_when_no_confidence_after(self):
        from deepr.experts.metacognition import KnowledgeGap
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        kg = KnowledgeGap(topic="t", first_encountered=ts, times_asked=2,
                          research_triggered=True, research_date=ts)
        gap = kg.to_gap()
        assert gap.filled is False


class TestRoundTrip:
    """Test full round-trip: existing type -> canonical -> dict -> canonical."""

    def test_belief_to_claim_round_trip(self):
        from deepr.experts.beliefs import Belief
        b = Belief(claim="Python is great", confidence=0.9,
                   evidence_refs=["doc1"], domain="python",
                   source_type="learned")
        claim = b.to_claim()
        d = claim.to_dict()
        restored = Claim.from_dict(d)
        assert restored.statement == "Python is great"
        assert restored.domain == "python"
        assert len(restored.sources) == 1

    def test_synthesis_gap_round_trip(self):
        from deepr.experts.synthesis import KnowledgeGap
        kg = KnowledgeGap(topic="ML ops", questions=["How to deploy?"],
                          priority=4, identified_at=datetime.now(timezone.utc))
        gap = kg.to_gap()
        d = gap.to_dict()
        restored = Gap.from_dict(d)
        assert restored.topic == "ML ops"
        assert restored.questions == ["How to deploy?"]
        assert restored.priority == 4
