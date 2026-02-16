"""Tests for deepr.experts.multi_pass.MultiPassPipeline."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts.multi_pass import CrossReferenceResult, MultiPassPipeline, MultiPassResult


# ---------------------------------------------------------------------------
# MultiPassResult
# ---------------------------------------------------------------------------


class TestMultiPassResult:
    def test_default_values(self):
        result = MultiPassResult(gap_topic="Test Gap")
        assert result.gap_topic == "Test Gap"
        assert result.beliefs == []
        assert result.changes == []
        assert result.filled is False
        assert result.total_cost == 0.0
        assert result.passes_completed == 0

    def test_to_dict(self):
        result = MultiPassResult(
            gap_topic="Quantum",
            beliefs=[{"statement": "Q is real", "confidence": 0.9}],
            filled=True,
            passes_completed=3,
            total_cost=0.15,
        )
        d = result.to_dict()
        assert d["gap_topic"] == "Quantum"
        assert d["filled"] is True
        assert d["passes_completed"] == 3
        assert len(d["beliefs"]) == 1

    def test_to_dict_with_cross_reference(self):
        result = MultiPassResult(
            gap_topic="Test",
            cross_reference=CrossReferenceResult(
                confirmations=["A confirms B"],
                contradictions=["C contradicts D"],
                novel_facts=["E is new"],
                confidence_adjustment=0.05,
            ),
        )
        d = result.to_dict()
        assert d["cross_reference"]["confirmations"] == ["A confirms B"]
        assert d["cross_reference"]["confidence_adjustment"] == 0.05


# ---------------------------------------------------------------------------
# CrossReferenceResult
# ---------------------------------------------------------------------------


class TestCrossReferenceResult:
    def test_defaults(self):
        cr = CrossReferenceResult()
        assert cr.confirmations == []
        assert cr.contradictions == []
        assert cr.novel_facts == []
        assert cr.confidence_adjustment == 0.0

    def test_with_data(self):
        cr = CrossReferenceResult(
            confirmations=["A"],
            contradictions=["B"],
            novel_facts=["C"],
            confidence_adjustment=0.1,
        )
        assert len(cr.confirmations) == 1
        assert cr.confidence_adjustment == 0.1


# ---------------------------------------------------------------------------
# MultiPassPipeline._pass_extract
# ---------------------------------------------------------------------------


class TestPassExtract:
    @pytest.mark.asyncio
    async def test_standard_extraction(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Finding 1: Important data. Finding 2: Key result."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = MultiPassPipeline(client=mock_client)
        result = await pipeline._pass_extract("Quantum computing", ["What is decoherence?"], 2.5, False)

        assert result.phase == 1
        assert result.summary is not None

    @pytest.mark.asyncio
    async def test_extraction_with_consensus(self):
        mock_consensus = AsyncMock()
        mock_consensus.research_with_consensus = AsyncMock(
            return_value=MagicMock(consensus_answer="Consensus finding about the topic.")
        )

        pipeline = MultiPassPipeline(consensus_engine=mock_consensus)
        result = await pipeline._pass_extract("Topic", ["Question?"], 2.5, use_consensus=True)

        mock_consensus.research_with_consensus.assert_called_once()
        assert result.phase == 1


# ---------------------------------------------------------------------------
# MultiPassPipeline._pass_cross_reference
# ---------------------------------------------------------------------------


class TestPassCrossReference:
    @pytest.mark.asyncio
    async def test_cross_reference(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "confirmations": ["Finding A confirms Claim X"],
            "contradictions": ["Finding B contradicts Claim Y"],
            "novel_facts": ["Finding C is entirely new"],
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = MultiPassPipeline(client=mock_client)

        # Create a mock extraction
        from deepr.services.context_chainer import ExtractedFinding, StructuredPhaseOutput
        from deepr.observability.temporal_tracker import FindingType

        extraction = StructuredPhaseOutput(
            phase=1,
            key_findings=[
                ExtractedFinding(text="Finding A about topic", confidence=0.8, finding_type=FindingType.FACT),
            ],
            summary="Summary",
            entities=[],
            open_questions=[],
            contradictions=[],
            confidence_avg=0.8,
        )

        existing_claims = [
            {"statement": "Claim X is true", "confidence": 0.7},
            {"statement": "Claim Y is also true", "confidence": 0.6},
        ]

        result = await pipeline._pass_cross_reference(extraction, existing_claims, 1.0)

        assert isinstance(result, CrossReferenceResult)
        assert len(result.confirmations) == 1
        assert len(result.contradictions) == 1
        assert len(result.novel_facts) == 1

    @pytest.mark.asyncio
    async def test_cross_reference_confidence_boost(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "confirmations": ["A", "B", "C"],
            "contradictions": [],
            "novel_facts": [],
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = MultiPassPipeline(client=mock_client)
        from deepr.services.context_chainer import StructuredPhaseOutput

        extraction = StructuredPhaseOutput(
            phase=1, key_findings=[], summary="", entities=[],
            open_questions=[], contradictions=[], confidence_avg=0.5,
        )
        result = await pipeline._pass_cross_reference(extraction, [], 1.0)
        assert result.confidence_adjustment > 0

    @pytest.mark.asyncio
    async def test_cross_reference_contradiction_penalty(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "confirmations": [],
            "contradictions": ["X", "Y"],
            "novel_facts": [],
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = MultiPassPipeline(client=mock_client)
        from deepr.services.context_chainer import StructuredPhaseOutput

        extraction = StructuredPhaseOutput(
            phase=1, key_findings=[], summary="", entities=[],
            open_questions=[], contradictions=[], confidence_avg=0.5,
        )
        result = await pipeline._pass_cross_reference(extraction, [], 1.0)
        assert result.confidence_adjustment < 0


# ---------------------------------------------------------------------------
# MultiPassPipeline._pass_synthesize
# ---------------------------------------------------------------------------


class TestPassSynthesize:
    @pytest.mark.asyncio
    async def test_synthesis(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "beliefs": [
                {"statement": "New belief", "confidence": 0.85, "evidence": ["research"]},
            ],
            "changes": [{"type": "created", "description": "New belief formed"}],
            "gap_filled": True,
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = MultiPassPipeline(client=mock_client)
        from deepr.services.context_chainer import StructuredPhaseOutput

        extraction = StructuredPhaseOutput(
            phase=1, key_findings=[], summary="", entities=[],
            open_questions=[], contradictions=[], confidence_avg=0.5,
        )

        beliefs, changes, filled = await pipeline._pass_synthesize(
            extraction, None, "Test Topic", "test_domain", 1.0
        )

        assert len(beliefs) == 1
        assert beliefs[0]["statement"] == "New belief"
        assert filled is True

    @pytest.mark.asyncio
    async def test_synthesis_applies_confidence_adjustment(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "beliefs": [{"statement": "Belief", "confidence": 0.70, "evidence": []}],
            "changes": [],
            "gap_filled": True,
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        pipeline = MultiPassPipeline(client=mock_client)
        from deepr.services.context_chainer import StructuredPhaseOutput

        extraction = StructuredPhaseOutput(
            phase=1, key_findings=[], summary="", entities=[],
            open_questions=[], contradictions=[], confidence_avg=0.5,
        )
        cross_ref = CrossReferenceResult(confidence_adjustment=0.1)

        beliefs, _, _ = await pipeline._pass_synthesize(
            extraction, cross_ref, "Topic", "domain", 1.0
        )

        assert beliefs[0]["confidence"] == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# MultiPassPipeline.fill_gap (integration)
# ---------------------------------------------------------------------------


class TestFillGap:
    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        mock_client = AsyncMock()

        # Extract response
        extract_response = MagicMock()
        extract_response.choices = [MagicMock()]
        extract_response.choices[0].message.content = "Key finding: Important research result."

        # Cross-reference response
        xref_response = MagicMock()
        xref_response.choices = [MagicMock()]
        xref_response.choices[0].message.content = json.dumps({
            "confirmations": ["Confirms existing"],
            "contradictions": [],
            "novel_facts": ["New info"],
        })

        # Synthesize response
        synth_response = MagicMock()
        synth_response.choices = [MagicMock()]
        synth_response.choices[0].message.content = json.dumps({
            "beliefs": [{"statement": "Result", "confidence": 0.8, "evidence": ["research"]}],
            "changes": [{"type": "created", "description": "New"}],
            "gap_filled": True,
        })

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[extract_response, xref_response, synth_response]
        )

        pipeline = MultiPassPipeline(client=mock_client)

        gap = MagicMock()
        gap.topic = "Test Topic"
        gap.questions = ["What is X?"]

        result = await pipeline.fill_gap(
            gap=gap,
            existing_claims=[{"statement": "Old claim", "confidence": 0.6}],
            expert_name="Test Expert",
            domain="test",
            budget=5.0,
        )

        assert result.passes_completed == 3
        assert result.filled is True
        assert len(result.beliefs) == 1

    @pytest.mark.asyncio
    async def test_pipeline_handles_extract_failure(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API fail"))

        pipeline = MultiPassPipeline(client=mock_client)
        gap = MagicMock()
        gap.topic = "Test"
        gap.questions = []

        result = await pipeline.fill_gap(gap, [], "expert", "domain", 5.0)
        assert result.passes_completed == 0
        assert result.filled is False
