"""Tests for the operator-facing semantic recall payload."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.expert_semantic_recall import (
    build_expert_semantic_recall,
    build_expert_semantic_recall_refresh_local,
    coerce_query_embedding,
)
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    return ExpertProfile(
        name="Recall Surface Expert",
        vector_store_id="vs-recall-surface",
        domain="ai infrastructure",
        knowledge_cutoff_date=datetime(2026, 6, 29, tzinfo=UTC),
    )


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Recall Surface Expert", storage_dir=tmp_path / "beliefs")


def test_expert_semantic_recall_payload_is_candidate_only_and_zero_cost(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(
        Belief(
            claim="Rack power constraints slow accelerator deployment.",
            confidence=0.82,
            domain="ai-infra",
        )
    )

    payload = build_expert_semantic_recall(
        _profile(),
        store,
        "accelerator power deployment",
        top_k=3,
    )

    assert payload["schema_version"] == "deepr-expert-semantic-recall-v1"
    assert payload["contract"] == {
        "cost_usd": 0.0,
        "writes_graph": False,
        "writes_belief_store": False,
        "semantic_verdict": False,
        "candidate_verdict": "candidate_only",
        "routing": "candidate_only",
        "embedding_generation": "not_performed",
    }
    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["lexical_candidate_count"] == 1
    assert payload["candidates"][0]["item_id"] == belief.id
    assert payload["candidates"][0]["text"] == belief.claim
    assert payload["candidates"][0]["verdict"] == "candidate_only"


def test_expert_semantic_recall_uses_indexed_vectors_only_with_supplied_query_embedding(tmp_path):
    store = _store(tmp_path)
    relevant, _ = store.add_belief(
        Belief(
            claim="Advanced packaging supply limits accelerator rollout.",
            confidence=0.86,
            domain="ai-infra",
        )
    )
    unrelated, _ = store.add_belief(
        Belief(
            claim="Retention policies affect legal archive reviews.",
            confidence=0.8,
            domain="governance",
        )
    )
    store.upsert_belief_embedding(relevant.id, [1.0, 0.0], model="local-test")
    store.upsert_belief_embedding(unrelated.id, [0.0, 1.0], model="local-test")

    payload = build_expert_semantic_recall(
        _profile(),
        store,
        "GPU supply bottleneck",
        query_embedding=[0.99, 0.01],
        embedding_model="local-test",
        include_lexical_fallback=False,
        top_k=1,
    )

    assert payload["index"]["used"] is True
    assert payload["query"]["query_embedding_dimensions"] == 2
    assert payload["summary"]["vector_candidate_count"] == 1
    assert payload["summary"]["lexical_candidate_count"] == 0
    assert payload["candidates"][0]["item_id"] == relevant.id
    assert payload["candidates"][0]["method"] == "vector_similarity"


def test_expert_semantic_recall_records_local_query_embedding_generation(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(Belief(claim="Local vectors route recall.", confidence=0.8, domain="memory"))
    store.upsert_belief_embedding(belief.id, [1.0, 0.0], model="nomic-embed-text")

    payload = build_expert_semantic_recall(
        _profile(),
        store,
        "local recall routing",
        query_embedding=[1.0, 0.0],
        embedding_model="nomic-embed-text",
        include_lexical_fallback=False,
        embedding_generation="local_ollama_query",
    )

    assert payload["contract"]["embedding_generation"] == "local_ollama_query"
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["candidates"][0]["item_id"] == belief.id


async def test_local_refresh_indexes_missing_beliefs_at_zero_cost(tmp_path):
    store = _store(tmp_path)
    first, _ = store.add_belief(Belief(claim="First claim.", confidence=0.8, domain="memory"))
    second, _ = store.add_belief(Belief(claim="Second claim.", confidence=0.8, domain="memory"))
    seen_claims: list[list[str]] = []

    async def embed_claims(claims):
        seen_claims.append(list(claims))
        return [(1.0, 0.0), (0.0, 1.0)][: len(claims)]

    payload = await build_expert_semantic_recall_refresh_local(
        _profile(),
        store,
        embed_claims,
        embedding_model="nomic-embed-text",
    )

    assert payload["schema_version"] == "deepr-expert-semantic-recall-refresh-v1"
    assert payload["request"]["embedding_source"] == "local_ollama"
    assert payload["contract"]["embedding_generation"] == "local_ollama"
    assert payload["contract"]["embedding_source"] == "local_ollama"
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["estimated_external_cost_usd"] == 0.0
    assert payload["summary"]["status"] == "indexed"
    assert payload["summary"]["indexed_count"] == 2
    assert seen_claims == [[first.claim, second.claim]]
    assert store.missing_belief_embedding_ids(embedding_model="nomic-embed-text") == []


async def test_local_refresh_requires_embedding_model(tmp_path):
    async def embed_claims(claims):
        return []

    with pytest.raises(ValueError, match="embedding_model is required"):
        await build_expert_semantic_recall_refresh_local(
            _profile(),
            _store(tmp_path),
            embed_claims,
            embedding_model="  ",
        )


async def test_local_refresh_blocks_on_embedder_count_mismatch_without_writing(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(Belief(claim="One claim.", confidence=0.8, domain="memory"))

    async def embed_claims(claims):
        return []

    payload = await build_expert_semantic_recall_refresh_local(
        _profile(),
        store,
        embed_claims,
        embedding_model="nomic-embed-text",
    )

    assert payload["summary"]["status"] == "blocked"
    assert payload["contract"]["writes_belief_vectors"] is False
    assert "different number of embeddings" in payload["refresh"]["blocked_reason"]
    assert store.missing_belief_embedding_ids(embedding_model="nomic-embed-text") == [belief.id]


def test_expert_semantic_recall_requires_model_for_supplied_query_embedding(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief(claim="A belief exists.", confidence=0.8, domain="test"))

    with pytest.raises(ValueError, match="embedding_model is required"):
        build_expert_semantic_recall(_profile(), store, "belief", query_embedding=[1.0])


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not a vector",
        [True],
        [math.nan],
        [math.inf],
    ],
)
def test_coerce_query_embedding_rejects_invalid_vectors(raw):
    with pytest.raises(ValueError):
        coerce_query_embedding(raw)  # type: ignore[arg-type]
