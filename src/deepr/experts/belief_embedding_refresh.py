"""Budget-gated construction-side refresh for belief recall embeddings.

This module does not know how to call an embedding provider. Callers must supply
an already-approved embedder function, which keeps spend and capacity policy at
the orchestration boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

EmbeddingBatcher = Callable[[list[str]], Awaitable[Sequence[Sequence[float]]] | Sequence[Sequence[float]]]


@dataclass(frozen=True)
class BeliefEmbeddingRefreshResult:
    """Result of an explicit belief embedding refresh attempt."""

    status: str
    requested_count: int
    indexed_count: int = 0
    skipped_count: int = 0
    estimated_cost_usd: float = 0.0
    blocked_reason: str = ""
    indexed_belief_ids: tuple[str, ...] = ()
    skipped_belief_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "requested_count": self.requested_count,
            "indexed_count": self.indexed_count,
            "skipped_count": self.skipped_count,
            "estimated_cost_usd": self.estimated_cost_usd,
            "blocked_reason": self.blocked_reason,
            "indexed_belief_ids": list(self.indexed_belief_ids),
            "skipped_belief_ids": list(self.skipped_belief_ids),
            "errors": list(self.errors),
            "metadata": self.metadata,
        }


def _nonnegative(value: float, *, name: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


async def refresh_missing_belief_embeddings(
    belief_store: Any,
    embed_claims: EmbeddingBatcher,
    *,
    model: str,
    budget_usd: float = 0.0,
    estimated_cost_per_belief: float = 0.0,
    max_beliefs: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> BeliefEmbeddingRefreshResult:
    """Embed missing or stale belief claims through an injected embedder.

    The function only indexes active beliefs reported by the store as missing
    or stale for the requested model. It blocks before calling ``embed_claims``
    when the declared estimate exceeds the supplied budget.
    """
    budget = _nonnegative(budget_usd, name="budget_usd")
    cost_per_belief = _nonnegative(estimated_cost_per_belief, name="estimated_cost_per_belief")
    limit = None if max_beliefs is None else max(0, int(max_beliefs))
    missing_ids = list(belief_store.missing_belief_embedding_ids(embedding_model=model))
    target_ids = missing_ids if limit is None else missing_ids[:limit]
    requested_count = len(target_ids)
    estimated_cost = round(cost_per_belief * requested_count, 6)
    result_metadata = dict(metadata or {})
    result_metadata["model"] = model

    if requested_count == 0:
        return BeliefEmbeddingRefreshResult(
            status="up_to_date",
            requested_count=0,
            estimated_cost_usd=estimated_cost,
            metadata=result_metadata,
        )
    if estimated_cost > budget:
        return BeliefEmbeddingRefreshResult(
            status="blocked",
            requested_count=requested_count,
            estimated_cost_usd=estimated_cost,
            blocked_reason=f"estimated embedding cost ${estimated_cost:.6f} exceeds budget ${budget:.6f}",
            skipped_count=requested_count,
            skipped_belief_ids=tuple(target_ids),
            metadata=result_metadata,
        )

    beliefs = [belief_store.beliefs[belief_id] for belief_id in target_ids]
    claims = [str(getattr(belief, "claim", "") or "") for belief in beliefs]
    raw_embeddings = embed_claims(claims)
    embeddings = await raw_embeddings if inspect.isawaitable(raw_embeddings) else raw_embeddings
    embeddings = list(embeddings)
    if len(embeddings) != requested_count:
        return BeliefEmbeddingRefreshResult(
            status="blocked",
            requested_count=requested_count,
            estimated_cost_usd=estimated_cost,
            blocked_reason="embedder returned a different number of embeddings than requested",
            skipped_count=requested_count,
            skipped_belief_ids=tuple(target_ids),
            metadata=result_metadata,
        )

    indexed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for belief, embedding in zip(beliefs, embeddings, strict=True):
        belief_id = str(getattr(belief, "id", "") or "")
        try:
            belief_store.upsert_belief_embedding(
                belief_id,
                embedding,
                model=model,
                metadata=result_metadata,
            )
        except (TypeError, ValueError) as exc:
            skipped.append(belief_id)
            errors.append(f"{belief_id}: {exc}")
            continue
        indexed.append(belief_id)

    status = "indexed" if not skipped else "partial"
    return BeliefEmbeddingRefreshResult(
        status=status,
        requested_count=requested_count,
        indexed_count=len(indexed),
        skipped_count=len(skipped),
        estimated_cost_usd=estimated_cost,
        indexed_belief_ids=tuple(indexed),
        skipped_belief_ids=tuple(skipped),
        errors=tuple(errors),
        metadata=result_metadata,
    )


__all__ = [
    "BeliefEmbeddingRefreshResult",
    "EmbeddingBatcher",
    "refresh_missing_belief_embeddings",
]
