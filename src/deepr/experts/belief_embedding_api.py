"""Provider-backed embedding batchers for belief recall index refresh."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_OPENAI_BELIEF_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_OPENAI_EMBEDDING_COST_PER_1K_TOKENS = 0.00002
MAX_EMBEDDING_INPUT_CHARS = 8000


@dataclass(frozen=True)
class EmbeddingCostEstimate:
    token_count: int
    cost_usd: float


def _nonnegative(value: float, *, name: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def estimate_embedding_tokens(texts: Sequence[str]) -> int:
    """Return a tokenizer-free embedding input estimate."""
    total_chars = sum(len(text or "") for text in texts)
    return max(1, math.ceil(total_chars / 4))


def estimate_embedding_cost_usd(texts: Sequence[str], *, cost_per_1k_tokens: float) -> EmbeddingCostEstimate:
    token_count = estimate_embedding_tokens(texts)
    cost_per_1k = _nonnegative(cost_per_1k_tokens, name="cost_per_1k_tokens")
    return EmbeddingCostEstimate(
        token_count=token_count,
        cost_usd=round(token_count / 1000 * cost_per_1k, 6),
    )


def _embedding_values(item: Any) -> list[float]:
    raw = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
    if raw is None:
        raise ValueError("embedding response item is missing embedding")
    return [float(value) for value in raw]


def _response_embeddings(response: Any) -> list[list[float]]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    if data is None:
        raise ValueError("embedding response is missing data")
    return [_embedding_values(item) for item in data]


def _response_total_tokens(response: Any) -> int:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0
    raw = usage.get("total_tokens") if isinstance(usage, dict) else getattr(usage, "total_tokens", 0)
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


class OpenAIEmbeddingBatcher:
    """Batch belief claims through an OpenAI-compatible embeddings client."""

    def __init__(
        self,
        client: Any,
        *,
        model: str = DEFAULT_OPENAI_BELIEF_EMBEDDING_MODEL,
        cost_safety: Any | None = None,
        session_id: str,
        budget_usd: float,
        cost_per_1k_tokens: float = DEFAULT_OPENAI_EMBEDDING_COST_PER_1K_TOKENS,
    ) -> None:
        self._client = client
        self.model = model
        self._cost_safety = cost_safety
        self._session_id = session_id
        self._budget_usd = _nonnegative(budget_usd, name="budget_usd")
        self._cost_per_1k_tokens = _nonnegative(cost_per_1k_tokens, name="cost_per_1k_tokens")

    async def __call__(self, claims: list[str]) -> list[list[float]]:
        inputs = [str(claim or "").replace("\n", " ")[:MAX_EMBEDDING_INPUT_CHARS] for claim in claims]
        estimate = estimate_embedding_cost_usd(inputs, cost_per_1k_tokens=self._cost_per_1k_tokens)
        if estimate.cost_usd > self._budget_usd:
            raise ValueError(
                f"estimated embedding cost ${estimate.cost_usd:.6f} exceeds budget ${self._budget_usd:.6f}"
            )

        reservation_id = ""
        if self._cost_safety is not None:
            allowed, reason, needs_confirmation, reservation_id = self._cost_safety.check_and_reserve(
                session_id=self._session_id,
                operation_type="belief_embedding_refresh",
                estimated_cost=estimate.cost_usd,
                require_confirmation=False,
                reserve=True,
            )
            if not allowed or needs_confirmation:
                raise ValueError(f"embedding refresh blocked by cost safety: {reason}")

        try:
            response = await self._client.embeddings.create(model=self.model, input=inputs)
        except Exception:
            if self._cost_safety is not None:
                self._cost_safety.refund_reservation(reservation_id)
            raise

        embeddings = _response_embeddings(response)
        actual_tokens = _response_total_tokens(response) or estimate.token_count
        actual_cost = round(actual_tokens / 1000 * self._cost_per_1k_tokens, 6)
        if self._cost_safety is not None:
            self._cost_safety.record_cost(
                session_id=self._session_id,
                operation_type="belief_embedding_refresh",
                actual_cost=actual_cost,
                provider="openai",
                model=self.model,
                tokens_input=actual_tokens,
                source="experts.belief_embedding_api.OpenAIEmbeddingBatcher",
                reservation_id=reservation_id,
                metadata={
                    "claim_count": len(inputs),
                    "estimated_cost_usd": estimate.cost_usd,
                },
            )
        return embeddings


__all__ = [
    "DEFAULT_OPENAI_BELIEF_EMBEDDING_MODEL",
    "DEFAULT_OPENAI_EMBEDDING_COST_PER_1K_TOKENS",
    "EmbeddingCostEstimate",
    "OpenAIEmbeddingBatcher",
    "estimate_embedding_cost_usd",
    "estimate_embedding_tokens",
]
