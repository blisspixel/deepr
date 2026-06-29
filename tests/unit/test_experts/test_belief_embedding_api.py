"""Tests for provider-backed belief embedding batchers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deepr.experts.belief_embedding_api import OpenAIEmbeddingBatcher, estimate_embedding_cost_usd


class _FakeCostSafety:
    def __init__(self) -> None:
        self.reserved = []
        self.recorded = []
        self.refunded = []

    def check_and_reserve(self, **kwargs):
        self.reserved.append(kwargs)
        return True, "OK", False, "reservation-1"

    def record_cost(self, **kwargs):
        self.recorded.append(kwargs)
        return True

    def refund_reservation(self, reservation_id):
        self.refunded.append(reservation_id)


def test_estimate_embedding_cost_usd_uses_token_estimate():
    estimate = estimate_embedding_cost_usd(["abcd", "efgh"], cost_per_1k_tokens=0.001)

    assert estimate.token_count == 2
    assert estimate.cost_usd == 0.000002


@pytest.mark.asyncio
async def test_openai_embedding_batcher_records_cost_and_returns_embeddings():
    cost_safety = _FakeCostSafety()
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[SimpleNamespace(embedding=[1, 0]), SimpleNamespace(embedding=[0, 1])],
                    usage=SimpleNamespace(total_tokens=12),
                )
            )
        )
    )

    batcher = OpenAIEmbeddingBatcher(
        client,
        model="text-embedding-3-small",
        cost_safety=cost_safety,
        session_id="absorb:Expert:belief-embedding-refresh",
        budget_usd=0.01,
        cost_per_1k_tokens=0.001,
    )

    embeddings = await batcher(["alpha", "beta"])

    assert embeddings == [[1.0, 0.0], [0.0, 1.0]]
    client.embeddings.create.assert_awaited_once_with(model="text-embedding-3-small", input=["alpha", "beta"])
    assert cost_safety.reserved[0]["operation_type"] == "belief_embedding_refresh"
    assert cost_safety.recorded[0]["actual_cost"] == 0.000012
    assert cost_safety.recorded[0]["reservation_id"] == "reservation-1"
    assert cost_safety.refunded == []


@pytest.mark.asyncio
async def test_openai_embedding_batcher_blocks_over_budget_before_provider_call():
    create = AsyncMock()
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    batcher = OpenAIEmbeddingBatcher(
        client,
        model="text-embedding-3-small",
        session_id="s",
        budget_usd=0.0,
        cost_per_1k_tokens=1.0,
    )

    with pytest.raises(ValueError, match="exceeds budget"):
        await batcher(["x" * 1000])

    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_openai_embedding_batcher_refunds_reservation_on_provider_error():
    cost_safety = _FakeCostSafety()
    create = AsyncMock(side_effect=RuntimeError("provider down"))
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    batcher = OpenAIEmbeddingBatcher(
        client,
        model="text-embedding-3-small",
        cost_safety=cost_safety,
        session_id="s",
        budget_usd=0.01,
        cost_per_1k_tokens=0.001,
    )

    with pytest.raises(RuntimeError, match="provider down"):
        await batcher(["alpha"])

    assert cost_safety.refunded == ["reservation-1"]
    assert cost_safety.recorded == []
