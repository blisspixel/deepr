"""Tests for claim-candidate recall routing helpers."""

from __future__ import annotations

import pytest

from deepr.experts.source_pack_recall import embed_ready_claim_statements


def _extraction(candidates: list[dict]) -> dict:
    return {"candidates": candidates}


def _ready(candidate_id: str, statement: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "statement": statement,
        "readiness": {"ready_for_verification": True},
    }


async def test_embed_ready_claim_statements_maps_ids_in_batch_order():
    seen: list[list[str]] = []

    async def embed_claims(claims):
        seen.append(list(claims))
        return [(1.0, 0.0), (0.0, 1.0)]

    extraction = _extraction(
        [
            _ready("cand-1", "First statement."),
            {"candidate_id": "cand-skip", "statement": "Not ready.", "readiness": {}},
            _ready("cand-2", "Second statement."),
        ]
    )

    embeddings = await embed_ready_claim_statements(extraction, embed_claims)

    assert seen == [["First statement.", "Second statement."]]
    assert embeddings == {"cand-1": (1.0, 0.0), "cand-2": (0.0, 1.0)}


async def test_embed_ready_claim_statements_short_circuits_without_ready_candidates():
    async def embed_claims(claims):
        raise AssertionError("embedder must not run without ready candidates")

    assert await embed_ready_claim_statements(_extraction([]), embed_claims) == {}


async def test_embed_ready_claim_statements_rejects_vector_count_mismatch():
    async def embed_claims(claims):
        return [(1.0, 0.0)]

    extraction = _extraction([_ready("cand-1", "One."), _ready("cand-2", "Two.")])

    with pytest.raises(ValueError, match="returned 1 vector"):
        await embed_ready_claim_statements(extraction, embed_claims)
