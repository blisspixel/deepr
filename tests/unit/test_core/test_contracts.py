"""Unit tests for core.contracts canonical types.

Tests creation, serialization round-trips, ID generation, and computed properties.
"""

import pytest
from datetime import datetime, timezone

from deepr.core.contracts import (
    Claim,
    DecisionRecord,
    DecisionType,
    ExpertManifest,
    Gap,
    Source,
    TrustClass,
)


class TestSource:
    """Test Source dataclass."""

    def test_create_generates_id(self):
        src = Source.create(title="doc.md")
        assert src.id
        assert len(src.id) == 12

    def test_create_same_input_same_id(self):
        s1 = Source.create(title="doc.md", url="https://example.com")
        s2 = Source.create(title="doc.md", url="https://example.com")
        assert s1.id == s2.id

    def test_create_different_input_different_id(self):
        s1 = Source.create(title="doc1.md")
        s2 = Source.create(title="doc2.md")
        assert s1.id != s2.id

    def test_defaults(self):
        src = Source.create(title="test.md")
        assert src.trust_class == TrustClass.TERTIARY
        assert src.extraction_method == "llm"
        assert src.url is None
        assert src.content_hash == ""

    def test_to_dict(self):
        src = Source.create(title="test.md", trust_class=TrustClass.PRIMARY,
                           url="https://example.com")
        d = src.to_dict()
        assert d["title"] == "test.md"
        assert d["trust_class"] == "primary"
        assert d["url"] == "https://example.com"
        assert "retrieved_at" in d

    def test_round_trip(self):
        src = Source.create(title="test.md", trust_class=TrustClass.SECONDARY,
                           extraction_method="scrape", url="https://x.com",
                           content_hash="abc123")
        d = src.to_dict()
        restored = Source.from_dict(d)
        assert restored.id == src.id
        assert restored.title == src.title
        assert restored.trust_class == src.trust_class
        assert restored.extraction_method == src.extraction_method
        assert restored.url == src.url
        assert restored.content_hash == src.content_hash


class TestClaim:
    """Test Claim dataclass."""

    def test_create_generates_id(self):
        claim = Claim.create(statement="Python is great", domain="python", confidence=0.9)
        assert claim.id
        assert len(claim.id) == 12

    def test_create_deterministic_id(self):
        c1 = Claim.create(statement="X is Y", domain="test", confidence=0.5)
        c2 = Claim.create(statement="X is Y", domain="test", confidence=0.8)
        assert c1.id == c2.id  # ID based on statement+domain, not confidence

    def test_to_dict(self):
        claim = Claim.create(statement="test", domain="d", confidence=0.75,
                             tags=["inferred"])
        d = claim.to_dict()
        assert d["statement"] == "test"
        assert d["domain"] == "d"
        assert d["confidence"] == 0.75
        assert d["tags"] == ["inferred"]
        assert isinstance(d["sources"], list)

    def test_round_trip(self):
        src = Source.create(title="evidence.md")
        claim = Claim.create(
            statement="A claim", domain="test", confidence=0.8,
            sources=[src], contradicts=["abc"], supersedes="xyz",
            tags=["learned"],
        )
        d = claim.to_dict()
        restored = Claim.from_dict(d)
        assert restored.id == claim.id
        assert restored.statement == claim.statement
        assert restored.confidence == claim.confidence
        assert len(restored.sources) == 1
        assert restored.sources[0].title == "evidence.md"
        assert restored.contradicts == ["abc"]
        assert restored.supersedes == "xyz"
        assert restored.tags == ["learned"]

    def test_from_dict_missing_optional_fields(self):
        d = {
            "id": "abc123456789",
            "statement": "test",
            "domain": "d",
            "confidence": 0.5,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        claim = Claim.from_dict(d)
        assert claim.sources == []
        assert claim.contradicts == []
        assert claim.supersedes is None
        assert claim.tags == []

    def test_confidence_bounds(self):
        claim = Claim.create(statement="x", domain="d", confidence=0.0)
        assert claim.confidence == 0.0
        claim2 = Claim.create(statement="y", domain="d", confidence=1.0)
        assert claim2.confidence == 1.0


class TestGap:
    """Test Gap dataclass."""

    def test_create_generates_id(self):
        gap = Gap.create(topic="quantum computing")
        assert gap.id
        assert len(gap.id) == 12

    def test_create_deterministic_id(self):
        g1 = Gap.create(topic="topic A")
        g2 = Gap.create(topic="topic A")
        assert g1.id == g2.id

    def test_defaults(self):
        gap = Gap.create(topic="test")
        assert gap.priority == 3
        assert gap.estimated_cost == 0.0
        assert gap.expected_value == 0.0
        assert gap.ev_cost_ratio == 0.0
        assert gap.times_asked == 0
        assert gap.filled is False
        assert gap.filled_at is None
        assert gap.filled_by_job is None

    def test_to_dict(self):
        gap = Gap.create(topic="ML", questions=["What is?", "How?"], priority=5,
                         times_asked=3)
        d = gap.to_dict()
        assert d["topic"] == "ML"
        assert d["questions"] == ["What is?", "How?"]
        assert d["priority"] == 5
        assert d["times_asked"] == 3
        assert d["filled"] is False

    def test_round_trip(self):
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        gap = Gap.create(
            topic="testing", questions=["Q1"], priority=4,
            estimated_cost=1.5, expected_value=0.8, ev_cost_ratio=0.533,
            times_asked=7, identified_at=ts, filled=True, filled_at=ts,
            filled_by_job="job_123",
        )
        d = gap.to_dict()
        restored = Gap.from_dict(d)
        assert restored.id == gap.id
        assert restored.topic == gap.topic
        assert restored.priority == 4
        assert restored.estimated_cost == 1.5
        assert restored.filled is True
        assert restored.filled_by_job == "job_123"

    def test_zero_cost_gap(self):
        gap = Gap.create(topic="free", estimated_cost=0.0)
        assert gap.estimated_cost == 0.0


class TestDecisionRecord:
    """Test DecisionRecord dataclass."""

    def test_create_generates_uuid(self):
        rec = DecisionRecord.create(
            decision_type=DecisionType.ROUTING,
            title="Use OpenAI",
            rationale="Best for this query",
        )
        assert rec.id  # UUID string
        assert len(rec.id) == 36  # UUID format

    def test_create_unique_ids(self):
        r1 = DecisionRecord.create(DecisionType.STOP, "Stop", "Done")
        r2 = DecisionRecord.create(DecisionType.STOP, "Stop", "Done")
        assert r1.id != r2.id  # UUIDs are always unique

    def test_to_dict(self):
        rec = DecisionRecord.create(
            decision_type=DecisionType.BUDGET,
            title="Increase budget",
            rationale="User requested",
            confidence=0.95,
            alternatives=["Keep budget", "Reduce"],
            cost_impact=5.0,
            context={"job_id": "j1"},
        )
        d = rec.to_dict()
        assert d["decision_type"] == "budget"
        assert d["title"] == "Increase budget"
        assert d["confidence"] == 0.95
        assert d["alternatives"] == ["Keep budget", "Reduce"]
        assert d["cost_impact"] == 5.0
        assert d["context"]["job_id"] == "j1"

    def test_round_trip(self):
        rec = DecisionRecord.create(
            decision_type=DecisionType.PIVOT,
            title="Switch provider",
            rationale="Rate limited",
            confidence=0.7,
            alternatives=["Wait", "Retry"],
            evidence_refs=["span_1"],
            cost_impact=0.5,
            context={"expert": "test"},
        )
        d = rec.to_dict()
        restored = DecisionRecord.from_dict(d)
        assert restored.id == rec.id
        assert restored.decision_type == DecisionType.PIVOT
        assert restored.title == rec.title
        assert restored.rationale == rec.rationale
        assert restored.confidence == 0.7
        assert restored.alternatives == ["Wait", "Retry"]
        assert restored.evidence_refs == ["span_1"]
        assert restored.context == {"expert": "test"}

    def test_from_dict_missing_optional_fields(self):
        d = {
            "id": "test-uuid",
            "decision_type": "routing",
            "title": "t",
            "rationale": "r",
            "timestamp": "2025-01-01T00:00:00+00:00",
        }
        rec = DecisionRecord.from_dict(d)
        assert rec.confidence == 0.0
        assert rec.alternatives == []
        assert rec.evidence_refs == []
        assert rec.cost_impact == 0.0
        assert rec.context == {}


class TestExpertManifest:
    """Test ExpertManifest dataclass."""

    def _make_manifest(self, n_claims=3, n_gaps=2, n_decisions=1):
        claims = [
            Claim.create(f"claim_{i}", "test", confidence=0.5 + i * 0.1)
            for i in range(n_claims)
        ]
        gaps = [
            Gap.create(f"gap_{i}", priority=i + 1, ev_cost_ratio=float(i + 1))
            for i in range(n_gaps)
        ]
        decisions = [
            DecisionRecord.create(DecisionType.ROUTING, f"dec_{i}", "reason")
            for i in range(n_decisions)
        ]
        return ExpertManifest(
            expert_name="test_expert",
            domain="testing",
            claims=claims,
            gaps=gaps,
            decisions=decisions,
            policies={"refresh_days": 90},
        )

    def test_claim_count(self):
        m = self._make_manifest(n_claims=5)
        assert m.claim_count == 5

    def test_open_gap_count(self):
        m = self._make_manifest(n_gaps=3)
        assert m.open_gap_count == 3
        m.gaps[0].filled = True
        assert m.open_gap_count == 2

    def test_avg_confidence(self):
        m = self._make_manifest(n_claims=2)
        # claims have confidence 0.5 and 0.6
        assert 0.54 < m.avg_confidence < 0.56

    def test_avg_confidence_empty(self):
        m = ExpertManifest(expert_name="e", domain="d")
        assert m.avg_confidence == 0.0

    def test_top_gaps(self):
        m = self._make_manifest(n_gaps=4)
        top = m.top_gaps(2)
        assert len(top) == 2
        assert top[0].ev_cost_ratio >= top[1].ev_cost_ratio

    def test_top_gaps_excludes_filled(self):
        m = self._make_manifest(n_gaps=3)
        m.gaps[2].filled = True  # highest ev_cost_ratio gap
        top = m.top_gaps(5)
        assert all(not g.filled for g in top)

    def test_to_dict_includes_computed(self):
        m = self._make_manifest()
        d = m.to_dict()
        assert "claim_count" in d
        assert "open_gap_count" in d
        assert "avg_confidence" in d

    def test_round_trip(self):
        m = self._make_manifest()
        d = m.to_dict()
        restored = ExpertManifest.from_dict(d)
        assert restored.expert_name == "test_expert"
        assert restored.domain == "testing"
        assert len(restored.claims) == 3
        assert len(restored.gaps) == 2
        assert len(restored.decisions) == 1
        assert restored.policies == {"refresh_days": 90}

    def test_empty_manifest(self):
        m = ExpertManifest(expert_name="empty", domain="none")
        d = m.to_dict()
        assert d["claim_count"] == 0
        assert d["open_gap_count"] == 0
        assert d["avg_confidence"] == 0.0
