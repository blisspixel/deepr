"""Tests for contracts.py extensions: SupportClass, SourceValidation, ConsensusResult."""

from datetime import datetime, timezone

import pytest

from deepr.core.contracts import (
    ConsensusResult,
    DecisionRecord,
    DecisionType,
    Source,
    SourceValidation,
    SupportClass,
    TrustClass,
)


def _utc_now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# SupportClass enum
# ---------------------------------------------------------------------------


class TestSupportClass:
    def test_values(self):
        assert SupportClass.SUPPORTED == "supported"
        assert SupportClass.PARTIALLY_SUPPORTED == "partially_supported"
        assert SupportClass.UNSUPPORTED == "unsupported"
        assert SupportClass.UNCERTAIN == "uncertain"

    def test_from_string(self):
        assert SupportClass("supported") is SupportClass.SUPPORTED
        assert SupportClass("uncertain") is SupportClass.UNCERTAIN

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            SupportClass("invalid")

    def test_is_str_enum(self):
        assert isinstance(SupportClass.SUPPORTED, str)

    def test_all_members(self):
        assert len(SupportClass) == 4


# ---------------------------------------------------------------------------
# Source with support_class
# ---------------------------------------------------------------------------


class TestSourceSupportClass:
    def test_source_default_support_class_is_none(self):
        src = Source.create(title="test", trust_class=TrustClass.PRIMARY)
        assert src.support_class is None

    def test_source_with_support_class(self):
        src = Source.create(
            title="test",
            trust_class=TrustClass.PRIMARY,
            support_class=SupportClass.SUPPORTED,
        )
        assert src.support_class == SupportClass.SUPPORTED

    def test_source_to_dict_without_support_class(self):
        src = Source.create(title="test", trust_class=TrustClass.PRIMARY)
        d = src.to_dict()
        assert "support_class" not in d

    def test_source_to_dict_with_support_class(self):
        src = Source.create(
            title="test",
            trust_class=TrustClass.PRIMARY,
            support_class=SupportClass.UNSUPPORTED,
        )
        d = src.to_dict()
        assert d["support_class"] == "unsupported"

    def test_source_from_dict_without_support_class(self):
        d = {
            "id": "abc123",
            "title": "test",
            "trust_class": "primary",
            "extraction_method": "llm",
            "retrieved_at": _utc_now().isoformat(),
        }
        src = Source.from_dict(d)
        assert src.support_class is None

    def test_source_from_dict_with_support_class(self):
        d = {
            "id": "abc123",
            "title": "test",
            "trust_class": "primary",
            "extraction_method": "llm",
            "retrieved_at": _utc_now().isoformat(),
            "support_class": "partially_supported",
        }
        src = Source.from_dict(d)
        assert src.support_class == SupportClass.PARTIALLY_SUPPORTED

    def test_source_roundtrip_with_support_class(self):
        src = Source.create(
            title="Test Source",
            trust_class=TrustClass.SECONDARY,
            support_class=SupportClass.SUPPORTED,
            url="https://example.com",
        )
        d = src.to_dict()
        restored = Source.from_dict(d)
        assert restored.support_class == SupportClass.SUPPORTED
        assert restored.title == src.title
        assert restored.id == src.id

    def test_source_roundtrip_without_support_class(self):
        src = Source.create(title="Test Source", trust_class=TrustClass.TERTIARY)
        d = src.to_dict()
        restored = Source.from_dict(d)
        assert restored.support_class is None
        assert restored.title == src.title


# ---------------------------------------------------------------------------
# SourceValidation
# ---------------------------------------------------------------------------


class TestSourceValidation:
    def test_creation(self):
        sv = SourceValidation(
            source_id="src1",
            claim_id="clm1",
            support_class=SupportClass.SUPPORTED,
            explanation="Source directly supports claim.",
        )
        assert sv.source_id == "src1"
        assert sv.claim_id == "clm1"
        assert sv.support_class == SupportClass.SUPPORTED
        assert sv.explanation == "Source directly supports claim."
        assert sv.validated_at is not None

    def test_to_dict(self):
        sv = SourceValidation(
            source_id="src1",
            claim_id="clm1",
            support_class=SupportClass.UNSUPPORTED,
            explanation="No support found.",
        )
        d = sv.to_dict()
        assert d["source_id"] == "src1"
        assert d["claim_id"] == "clm1"
        assert d["support_class"] == "unsupported"
        assert d["explanation"] == "No support found."
        assert "validated_at" in d

    def test_from_dict(self):
        d = {
            "source_id": "src2",
            "claim_id": "clm2",
            "support_class": "uncertain",
            "explanation": "Ambiguous.",
            "validated_at": _utc_now().isoformat(),
        }
        sv = SourceValidation.from_dict(d)
        assert sv.source_id == "src2"
        assert sv.support_class == SupportClass.UNCERTAIN

    def test_from_dict_missing_validated_at(self):
        d = {
            "source_id": "src2",
            "claim_id": "clm2",
            "support_class": "supported",
            "explanation": "OK",
        }
        sv = SourceValidation.from_dict(d)
        assert sv.validated_at is not None

    def test_roundtrip(self):
        sv = SourceValidation(
            source_id="s1",
            claim_id="c1",
            support_class=SupportClass.PARTIALLY_SUPPORTED,
            explanation="Partially aligned.",
        )
        restored = SourceValidation.from_dict(sv.to_dict())
        assert restored.source_id == sv.source_id
        assert restored.claim_id == sv.claim_id
        assert restored.support_class == sv.support_class
        assert restored.explanation == sv.explanation

    def test_all_support_classes(self):
        for sc in SupportClass:
            sv = SourceValidation(
                source_id="s",
                claim_id="c",
                support_class=sc,
                explanation="test",
            )
            d = sv.to_dict()
            restored = SourceValidation.from_dict(d)
            assert restored.support_class == sc


# ---------------------------------------------------------------------------
# ConsensusResult
# ---------------------------------------------------------------------------


class TestConsensusResult:
    def test_creation(self):
        cr = ConsensusResult(
            query="What is X?",
            provider_responses=[
                {"provider": "openai", "model": "gpt-5.2", "answer": "X is Y", "cost": 0.05},
            ],
            agreement_score=0.85,
            consensus_answer="X is Y",
            confidence=0.88,
            total_cost=0.05,
        )
        assert cr.query == "What is X?"
        assert cr.agreement_score == 0.85
        assert cr.confidence == 0.88
        assert cr.total_cost == 0.05
        assert cr.decision_record is None

    def test_creation_with_decision_record(self):
        dr = DecisionRecord.create(
            decision_type=DecisionType.GAP_FILL,
            title="Test",
            rationale="Because",
        )
        cr = ConsensusResult(
            query="Q",
            consensus_answer="A",
            decision_record=dr,
        )
        assert cr.decision_record is not None
        assert cr.decision_record.title == "Test"

    def test_to_dict(self):
        cr = ConsensusResult(
            query="Q",
            provider_responses=[{"provider": "xai", "model": "grok", "answer": "ans", "cost": 0.10}],
            agreement_score=0.7,
            consensus_answer="Consensus",
            confidence=0.76,
            total_cost=0.10,
        )
        d = cr.to_dict()
        assert d["query"] == "Q"
        assert d["agreement_score"] == 0.7
        assert d["consensus_answer"] == "Consensus"
        assert d["confidence"] == 0.76
        assert d["total_cost"] == 0.10
        assert d["decision_record"] is None

    def test_to_dict_with_decision_record(self):
        dr = DecisionRecord.create(
            decision_type=DecisionType.GAP_FILL,
            title="DR",
            rationale="R",
        )
        cr = ConsensusResult(query="Q", consensus_answer="A", decision_record=dr)
        d = cr.to_dict()
        assert d["decision_record"] is not None
        assert d["decision_record"]["title"] == "DR"

    def test_from_dict(self):
        d = {
            "query": "Q",
            "provider_responses": [{"provider": "openai", "model": "m", "answer": "a", "cost": 0.01}],
            "agreement_score": 0.9,
            "consensus_answer": "A",
            "confidence": 0.92,
            "total_cost": 0.01,
        }
        cr = ConsensusResult.from_dict(d)
        assert cr.query == "Q"
        assert cr.agreement_score == 0.9
        assert cr.decision_record is None

    def test_from_dict_with_decision_record(self):
        dr_dict = DecisionRecord.create(
            decision_type=DecisionType.GAP_FILL,
            title="T",
            rationale="R",
        ).to_dict()
        d = {
            "query": "Q",
            "consensus_answer": "A",
            "decision_record": dr_dict,
        }
        cr = ConsensusResult.from_dict(d)
        assert cr.decision_record is not None
        assert cr.decision_record.title == "T"

    def test_from_dict_defaults(self):
        d = {"query": "Q", "consensus_answer": "A"}
        cr = ConsensusResult.from_dict(d)
        assert cr.agreement_score == 0.0
        assert cr.confidence == 0.0
        assert cr.total_cost == 0.0
        assert cr.provider_responses == []

    def test_roundtrip(self):
        dr = DecisionRecord.create(
            decision_type=DecisionType.GAP_FILL,
            title="Consensus",
            rationale="Agreed",
            confidence=0.85,
        )
        cr = ConsensusResult(
            query="Research question",
            provider_responses=[
                {"provider": "openai", "model": "gpt-5.2", "answer": "ans1", "cost": 0.05},
                {"provider": "xai", "model": "grok", "answer": "ans2", "cost": 0.08},
            ],
            agreement_score=0.82,
            consensus_answer="Combined answer",
            confidence=0.86,
            total_cost=0.13,
            decision_record=dr,
        )
        d = cr.to_dict()
        restored = ConsensusResult.from_dict(d)
        assert restored.query == cr.query
        assert restored.agreement_score == cr.agreement_score
        assert restored.consensus_answer == cr.consensus_answer
        assert restored.confidence == cr.confidence
        assert restored.total_cost == cr.total_cost
        assert len(restored.provider_responses) == 2
        assert restored.decision_record is not None
        assert restored.decision_record.title == "Consensus"

    def test_empty_consensus(self):
        cr = ConsensusResult(query="Q")
        assert cr.consensus_answer == ""
        assert cr.total_cost == 0.0
        assert cr.provider_responses == []
