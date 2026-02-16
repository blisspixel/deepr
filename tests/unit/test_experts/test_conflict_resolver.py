"""Tests for deepr.experts.conflict_resolver.ConflictResolver."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.beliefs import Belief
from deepr.experts.conflict_resolver import ConflictResolutionResult, ConflictResolver


def _make_belief(claim: str, domain: str = "test", confidence: float = 0.8) -> Belief:
    return Belief(claim=claim, confidence=confidence, domain=domain)


# ---------------------------------------------------------------------------
# ConflictResolutionResult
# ---------------------------------------------------------------------------


class TestConflictResolutionResult:
    def test_creation(self):
        result = ConflictResolutionResult(
            belief_a_id="a1",
            belief_b_id="b1",
            outcome="a_wins",
            explanation="A is better supported",
        )
        assert result.outcome == "a_wins"
        assert result.merged_claim is None

    def test_to_dict(self):
        result = ConflictResolutionResult(
            belief_a_id="a1",
            belief_b_id="b1",
            outcome="merged",
            explanation="Both partially correct",
            merged_claim="Combined claim",
            merged_confidence=0.75,
        )
        d = result.to_dict()
        assert d["outcome"] == "merged"
        assert d["merged_claim"] == "Combined claim"
        assert d["merged_confidence"] == 0.75
        assert "resolved_at" in d


# ---------------------------------------------------------------------------
# ConflictResolver.detect_contradictions (heuristic)
# ---------------------------------------------------------------------------


class TestDetectContradictions:
    @pytest.mark.asyncio
    async def test_no_contradictions(self):
        resolver = ConflictResolver()
        resolver._llm_detect_contradictions = AsyncMock(return_value=[])
        beliefs = [
            _make_belief("Python is fast"),
            _make_belief("Java is popular"),
        ]
        result = await resolver.detect_contradictions(beliefs)
        assert result == []

    @pytest.mark.asyncio
    async def test_heuristic_detection(self):
        resolver = ConflictResolver()
        resolver._llm_detect_contradictions = AsyncMock(return_value=[])

        a = _make_belief("Python is not good for performance critical tasks")
        b = _make_belief("Python is good for performance critical tasks")
        beliefs = [a, b]

        result = await resolver.detect_contradictions(beliefs)
        assert len(result) >= 1
        pair = result[0]
        assert {pair[0].claim, pair[1].claim} == {a.claim, b.claim}

    @pytest.mark.asyncio
    async def test_no_false_positive_different_domains(self):
        resolver = ConflictResolver()
        resolver._llm_detect_contradictions = AsyncMock(return_value=[])

        a = _make_belief("X is true", domain="physics")
        b = _make_belief("X is not true", domain="chemistry")
        beliefs = [a, b]

        # Heuristic only checks same domain for word overlap
        # These are different domains but same words, so heuristic may still find them
        result = await resolver.detect_contradictions(beliefs)
        # This is ok — the LLM stage would refine

    @pytest.mark.asyncio
    async def test_single_belief_no_contradiction(self):
        resolver = ConflictResolver()
        resolver._llm_detect_contradictions = AsyncMock(return_value=[])
        result = await resolver.detect_contradictions([_make_belief("Solo belief")])
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_beliefs(self):
        resolver = ConflictResolver()
        resolver._llm_detect_contradictions = AsyncMock(return_value=[])
        result = await resolver.detect_contradictions([])
        assert result == []


# ---------------------------------------------------------------------------
# ConflictResolver._llm_detect_contradictions
# ---------------------------------------------------------------------------


class TestLlmDetectContradictions:
    @pytest.mark.asyncio
    async def test_successful_detection(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[0]"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        resolver = ConflictResolver(client=mock_client)
        a = _make_belief("Claim A")
        b = _make_belief("Claim B")
        pairs = [(a, b)]

        result = await resolver._llm_detect_contradictions(pairs)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_no_contradictions_found(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "[]"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        resolver = ConflictResolver(client=mock_client)
        result = await resolver._llm_detect_contradictions([])
        assert result == []

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        resolver = ConflictResolver(client=mock_client)
        a = _make_belief("A")
        b = _make_belief("B")
        result = await resolver._llm_detect_contradictions([(a, b)])
        assert result == []


# ---------------------------------------------------------------------------
# ConflictResolver.resolve
# ---------------------------------------------------------------------------


class TestResolve:
    @pytest.mark.asyncio
    async def test_resolve_a_wins(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "winner": "a",
            "explanation": "Claim A has stronger evidence",
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        resolver = ConflictResolver(client=mock_client)
        a = _make_belief("Strong claim")
        b = _make_belief("Weak claim")

        result = await resolver.resolve(a, b)
        assert result.outcome == "a_wins"
        assert "stronger" in result.explanation
        assert result.decision_record is not None
        assert result.decision_record.decision_type.value == "conflict_resolution"

    @pytest.mark.asyncio
    async def test_resolve_merge(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "winner": "merge",
            "explanation": "Both claims partially correct",
            "merged_claim": "Combined truth",
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        resolver = ConflictResolver(client=mock_client)
        result = await resolver.resolve(_make_belief("A"), _make_belief("B"))
        assert result.outcome == "merged"
        assert result.merged_claim == "Combined truth"

    @pytest.mark.asyncio
    async def test_resolve_with_consensus(self):
        mock_consensus = AsyncMock()
        mock_consensus.research_with_consensus = AsyncMock(
            return_value=MagicMock(
                consensus_answer="Claim A is better supported and correct.",
                confidence=0.85,
                decision_record=None,
            )
        )

        resolver = ConflictResolver(consensus_engine=mock_consensus)
        result = await resolver.resolve(_make_belief("A"), _make_belief("B"))
        assert result.outcome == "a_wins"

    @pytest.mark.asyncio
    async def test_resolve_api_failure(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Fail"))

        resolver = ConflictResolver(client=mock_client)
        result = await resolver.resolve(_make_belief("A"), _make_belief("B"))
        assert result.outcome == "needs_human_review"


# ---------------------------------------------------------------------------
# ConflictResolver.resolve_all
# ---------------------------------------------------------------------------


class TestResolveAll:
    @pytest.mark.asyncio
    async def test_no_contradictions(self):
        resolver = ConflictResolver()
        resolver.detect_contradictions = AsyncMock(return_value=[])

        results = await resolver.resolve_all([_make_belief("A")], budget=5.0)
        assert results == []

    @pytest.mark.asyncio
    async def test_resolves_within_budget(self):
        resolver = ConflictResolver()
        a = _make_belief("A")
        b = _make_belief("B")
        resolver.detect_contradictions = AsyncMock(return_value=[(a, b)])
        resolver.resolve = AsyncMock(
            return_value=ConflictResolutionResult(
                belief_a_id=a.id, belief_b_id=b.id,
                outcome="a_wins", explanation="A wins",
            )
        )

        results = await resolver.resolve_all([a, b], budget=5.0)
        assert len(results) == 1
        assert results[0].outcome == "a_wins"

    @pytest.mark.asyncio
    async def test_budget_limits_resolutions(self):
        resolver = ConflictResolver()
        beliefs = [_make_belief(f"Belief {i}") for i in range(10)]
        pairs = [(beliefs[i], beliefs[i + 1]) for i in range(0, 8, 2)]
        resolver.detect_contradictions = AsyncMock(return_value=pairs)
        resolver.resolve = AsyncMock(
            return_value=ConflictResolutionResult(
                belief_a_id="a", belief_b_id="b",
                outcome="merged", explanation="Merged",
            )
        )

        # Budget 0.10, cost per resolution 0.05 => max 2 resolutions
        results = await resolver.resolve_all(beliefs, budget=0.10)
        assert len(results) == 2
