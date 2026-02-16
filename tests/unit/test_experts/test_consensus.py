"""Tests for deepr.experts.consensus.ConsensusEngine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts.consensus import (
    ConsensusEngine,
    ProviderResponse,
    _ESTIMATED_COST,
    _PROVIDER_MODELS,
    _has_api_key,
)


# ---------------------------------------------------------------------------
# _has_api_key
# ---------------------------------------------------------------------------


class TestHasApiKey:
    def test_returns_false_when_no_key(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _has_api_key("openai") is False

    def test_returns_true_when_key_set(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            assert _has_api_key("openai") is True

    def test_returns_false_for_unknown_provider(self):
        assert _has_api_key("unknown_provider") is False

    def test_returns_false_for_empty_key(self):
        with patch.dict("os.environ", {"XAI_API_KEY": ""}):
            assert _has_api_key("xai") is False


# ---------------------------------------------------------------------------
# ConsensusEngine._select_providers
# ---------------------------------------------------------------------------


class TestSelectProviders:
    def test_no_providers_when_no_keys(self):
        with patch.dict("os.environ", {}, clear=True):
            engine = ConsensusEngine()
            assert engine._select_providers(5.0) == []

    def test_single_provider_low_budget(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test", "XAI_API_KEY": "xai-test"}):
            engine = ConsensusEngine()
            result = engine._select_providers(0.05)
            assert len(result) == 1

    def test_multiple_providers_adequate_budget(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test", "XAI_API_KEY": "xai-test"}):
            engine = ConsensusEngine()
            result = engine._select_providers(5.0)
            assert len(result) >= 2

    def test_respects_max_providers(self):
        env = {
            "OPENAI_API_KEY": "test",
            "XAI_API_KEY": "test",
            "GEMINI_API_KEY": "test",
            "ANTHROPIC_API_KEY": "test",
        }
        with patch.dict("os.environ", env):
            engine = ConsensusEngine(max_providers=2)
            result = engine._select_providers(50.0)
            assert len(result) <= 2

    def test_sorts_by_cost(self):
        env = {"OPENAI_API_KEY": "test", "GEMINI_API_KEY": "test"}
        with patch.dict("os.environ", env):
            engine = ConsensusEngine()
            result = engine._select_providers(5.0)
            # Should be sorted by estimated cost
            if len(result) >= 2:
                costs = [_ESTIMATED_COST.get(p, 1.0) for p, _ in result]
                assert costs == sorted(costs)


# ---------------------------------------------------------------------------
# ConsensusEngine._merge_answers
# ---------------------------------------------------------------------------


class TestMergeAnswers:
    def setup_method(self):
        self.engine = ConsensusEngine()

    def _make_response(self, provider: str, answer: str) -> ProviderResponse:
        return ProviderResponse(
            provider=provider, model="test", answer=answer, citations=[], cost=0.05, latency=1.0
        )

    def test_empty_responses(self):
        assert self.engine._merge_answers([], 0.5) == ""

    def test_high_agreement_picks_longest(self):
        responses = [
            self._make_response("openai", "Short answer"),
            self._make_response("xai", "This is a much longer and more detailed answer about the topic"),
        ]
        result = self.engine._merge_answers(responses, 0.9)
        assert "much longer" in result

    def test_low_agreement_shows_all_perspectives(self):
        responses = [
            self._make_response("openai", "X is true"),
            self._make_response("xai", "X is false"),
        ]
        result = self.engine._merge_answers(responses, 0.2)
        assert "disagree" in result.lower() or "openai" in result.lower()

    def test_moderate_agreement_combines(self):
        responses = [
            self._make_response("openai", "Fact A and Fact B are important"),
            self._make_response("xai", "Completely different perspective on C and D"),
        ]
        result = self.engine._merge_answers(responses, 0.6)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# ConsensusEngine._heuristic_agreement
# ---------------------------------------------------------------------------


class TestHeuristicAgreement:
    def setup_method(self):
        self.engine = ConsensusEngine()

    def _make_response(self, answer: str) -> ProviderResponse:
        return ProviderResponse(
            provider="test", model="test", answer=answer, citations=[], cost=0.0, latency=0.0
        )

    def test_identical_answers(self):
        responses = [
            self._make_response("The answer is 42"),
            self._make_response("The answer is 42"),
        ]
        score = self.engine._heuristic_agreement(responses)
        assert score == 1.0

    def test_completely_different_answers(self):
        responses = [
            self._make_response("aaa bbb ccc ddd eee"),
            self._make_response("fff ggg hhh iii jjj"),
        ]
        score = self.engine._heuristic_agreement(responses)
        assert score == 0.0

    def test_partial_overlap(self):
        responses = [
            self._make_response("the cat sat on the mat"),
            self._make_response("the dog sat on the rug"),
        ]
        score = self.engine._heuristic_agreement(responses)
        assert 0.0 < score < 1.0

    def test_single_response(self):
        responses = [self._make_response("only one")]
        assert self.engine._heuristic_agreement(responses) == 0.5


# ---------------------------------------------------------------------------
# ConsensusEngine.research_with_consensus
# ---------------------------------------------------------------------------


class TestResearchWithConsensus:
    @pytest.mark.asyncio
    async def test_no_providers_available(self):
        with patch.dict("os.environ", {}, clear=True):
            engine = ConsensusEngine()
            result = await engine.research_with_consensus("test query", 5.0, "expert")
            assert "No providers available" in result.consensus_answer

    @pytest.mark.asyncio
    async def test_single_provider_fallback(self):
        engine = ConsensusEngine()
        engine._select_providers = MagicMock(return_value=[("openai", "gpt-5.2")])
        engine._query_provider = AsyncMock(
            return_value=ProviderResponse(
                provider="openai", model="gpt-5.2", answer="Test answer",
                citations=[], cost=0.05, latency=1.0,
            )
        )
        result = await engine.research_with_consensus("test", 0.05, "expert")
        assert result.consensus_answer == "Test answer"
        assert result.agreement_score == 0.5
        assert result.total_cost == 0.05

    @pytest.mark.asyncio
    async def test_multi_provider_success(self):
        engine = ConsensusEngine()
        engine._select_providers = MagicMock(return_value=[("openai", "gpt-5.2"), ("xai", "grok")])
        engine._query_provider = AsyncMock(
            side_effect=[
                ProviderResponse(
                    provider="openai", model="gpt-5.2", answer="Answer A",
                    citations=[], cost=0.05, latency=1.0,
                ),
                ProviderResponse(
                    provider="xai", model="grok", answer="Answer B is longer and more detailed",
                    citations=[], cost=0.08, latency=1.5,
                ),
            ]
        )
        engine._compute_agreement = AsyncMock(return_value=0.85)

        result = await engine.research_with_consensus("test", 5.0, "expert")
        assert result.agreement_score == 0.85
        assert result.total_cost == 0.13
        assert result.decision_record is not None
        assert len(result.provider_responses) == 2

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        engine = ConsensusEngine()
        engine._select_providers = MagicMock(return_value=[("openai", "gpt-5.2"), ("xai", "grok")])
        engine._query_provider = AsyncMock(side_effect=Exception("API error"))

        result = await engine.research_with_consensus("test", 5.0, "expert")
        assert "All providers failed" in result.consensus_answer

    @pytest.mark.asyncio
    async def test_confidence_calibration(self):
        engine = ConsensusEngine()
        engine._select_providers = MagicMock(return_value=[("openai", "m"), ("xai", "m")])
        engine._query_provider = AsyncMock(
            side_effect=[
                ProviderResponse(provider="openai", model="m", answer="A", citations=[], cost=0.01, latency=0.5),
                ProviderResponse(provider="xai", model="m", answer="A", citations=[], cost=0.01, latency=0.5),
            ]
        )
        engine._compute_agreement = AsyncMock(return_value=1.0)

        result = await engine.research_with_consensus("test", 5.0, "expert")
        # confidence = min(1.0, 1.0 * 0.8 + 0.2) = 1.0
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_low_agreement_confidence(self):
        engine = ConsensusEngine()
        engine._select_providers = MagicMock(return_value=[("openai", "m"), ("xai", "m")])
        engine._query_provider = AsyncMock(
            side_effect=[
                ProviderResponse(provider="openai", model="m", answer="Yes", citations=[], cost=0.01, latency=0.5),
                ProviderResponse(provider="xai", model="m", answer="No", citations=[], cost=0.01, latency=0.5),
            ]
        )
        engine._compute_agreement = AsyncMock(return_value=0.1)

        result = await engine.research_with_consensus("test", 5.0, "expert")
        # confidence = min(1.0, 0.1 * 0.8 + 0.2) = 0.28
        assert result.confidence == pytest.approx(0.28)
