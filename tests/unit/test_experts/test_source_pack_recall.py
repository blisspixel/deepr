"""Tests for claim-candidate recall routing helpers."""

from __future__ import annotations

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.semantic_recall import LEXICAL_METHOD, VECTOR_METHOD
from deepr.experts.source_pack_recall import build_verification_recall_candidates, embed_ready_claim_statements


def _extraction(candidates: list[dict]) -> dict:
    return {"candidates": candidates}


def _ready(candidate_id: str, statement: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "statement": statement,
        "readiness": {"ready_for_verification": True},
    }


def _eligible_vector_preference() -> dict:
    return {
        "eligible": True,
        "preferred_route": VECTOR_METHOD,
        "fallback_route": LEXICAL_METHOD,
        "routing_evidence_only": True,
        "semantic_verdict": False,
        "embedding_model": "local-test",
        "index_state_digest": "a" * 64,
        "retrieval_contract": {"top_k": 5, "domain": "", "min_score": 0.0},
    }


class RecordingRecallStore:
    def __init__(self, *, vector_hits: list[dict] | None = None, lexical_hits: list[dict] | None = None) -> None:
        self.calls: list[dict] = []
        self.vector_hits = vector_hits if vector_hits is not None else []
        self.lexical_hits = lexical_hits if lexical_hits is not None else []

    def recall_belief_candidates(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if kwargs["include_lexical_fallback"] is False:
            return self.vector_hits
        return self.lexical_hits

    def belief_embedding_stats(self, *, embedding_model: str) -> dict:
        assert embedding_model == "local-test"
        return {
            "record_count": 1,
            "belief_count": 1,
            "current_vector_count": 1,
            "missing_or_stale_count": 0,
            "state_digest": "a" * 64,
        }


def _recall_hit(item_id: str, *, method: str) -> dict:
    return {
        "item_id": item_id,
        "kind": "belief",
        "domain": "infra",
        "text": f"{method} hit",
        "score": 0.91,
        "method": method,
        "matched_terms": [],
        "metadata": {},
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


def test_vector_preference_uses_vector_only_when_evidence_gate_is_eligible():
    store = RecordingRecallStore(vector_hits=[_recall_hit("vector-1", method=VECTOR_METHOD)])

    routed = build_verification_recall_candidates(
        _extraction([_ready("cand-1", "GPU power limits are binding.")]),
        store,
        query_embeddings_by_candidate_id={"cand-1": [1.0, 0.0]},
        embedding_model="local-test",
        route_preference=_eligible_vector_preference(),
    )

    assert [call["include_lexical_fallback"] for call in store.calls] == [False]
    assert routed["cand-1"][0]["item_id"] == "vector-1"
    assert routed["cand-1"][0]["method"] == VECTOR_METHOD
    preference = routed["cand-1"][0]["metadata"]["route_preference"]
    assert preference["preferred_route"] == VECTOR_METHOD
    assert preference["fallback_route"] == LEXICAL_METHOD
    assert preference["routing_evidence_only"] is True
    assert preference["semantic_verdict"] is False


def test_ineligible_vector_preference_keeps_lexical_fallback_enabled():
    store = RecordingRecallStore(lexical_hits=[_recall_hit("lexical-1", method=LEXICAL_METHOD)])

    routed = build_verification_recall_candidates(
        _extraction([_ready("cand-1", "GPU power limits are binding.")]),
        store,
        query_embeddings_by_candidate_id={"cand-1": [1.0, 0.0]},
        embedding_model="local-test",
        route_preference={**_eligible_vector_preference(), "eligible": False, "reasons": ["insufficient_case_count"]},
    )

    assert [call["include_lexical_fallback"] for call in store.calls] == [True]
    assert routed["cand-1"][0]["item_id"] == "lexical-1"
    assert routed["cand-1"][0]["method"] == LEXICAL_METHOD
    assert "route_preference" not in routed["cand-1"][0]["metadata"]


def test_vector_preference_falls_back_to_lexical_when_vector_route_has_no_hits():
    store = RecordingRecallStore(
        vector_hits=[],
        lexical_hits=[_recall_hit("lexical-1", method=LEXICAL_METHOD)],
    )

    routed = build_verification_recall_candidates(
        _extraction([_ready("cand-1", "GPU power limits are binding.")]),
        store,
        query_embeddings_by_candidate_id={"cand-1": [1.0, 0.0]},
        embedding_model="local-test",
        route_preference=_eligible_vector_preference(),
    )

    assert [call["include_lexical_fallback"] for call in store.calls] == [False, True]
    assert routed["cand-1"][0]["item_id"] == "lexical-1"
    assert routed["cand-1"][0]["method"] == LEXICAL_METHOD


def test_vector_preference_falls_back_to_lexical_after_index_state_drift():
    store = RecordingRecallStore(lexical_hits=[_recall_hit("lexical-1", method=LEXICAL_METHOD)])
    preference = {**_eligible_vector_preference(), "index_state_digest": "b" * 64}

    routed = build_verification_recall_candidates(
        _extraction([_ready("cand-1", "GPU power limits are binding.")]),
        store,
        query_embeddings_by_candidate_id={"cand-1": [1.0, 0.0]},
        embedding_model="local-test",
        route_preference=preference,
    )

    assert [call["include_lexical_fallback"] for call in store.calls] == [True]
    assert routed["cand-1"][0]["item_id"] == "lexical-1"
    assert "route_preference" not in routed["cand-1"][0]["metadata"]


@pytest.mark.parametrize(
    ("call_kwargs", "contract"),
    [
        ({"top_k": 3}, {"top_k": 5, "domain": "", "min_score": 0.0}),
        ({"domain": "infra"}, {"top_k": 5, "domain": "", "min_score": 0.0}),
        ({"min_score": 0.2}, {"top_k": 5, "domain": "", "min_score": 0.0}),
    ],
)
def test_vector_preference_falls_back_when_retrieval_contract_differs(call_kwargs, contract):
    store = RecordingRecallStore(lexical_hits=[_recall_hit("lexical-1", method=LEXICAL_METHOD)])
    preference = {**_eligible_vector_preference(), "retrieval_contract": contract}

    routed = build_verification_recall_candidates(
        _extraction([_ready("cand-1", "GPU power limits are binding.")]),
        store,
        query_embeddings_by_candidate_id={"cand-1": [1.0, 0.0]},
        embedding_model="local-test",
        route_preference=preference,
        **call_kwargs,
    )

    assert [call["include_lexical_fallback"] for call in store.calls] == [True]
    assert routed["cand-1"][0]["item_id"] == "lexical-1"
    assert "route_preference" not in routed["cand-1"][0]["metadata"]


def test_retrieval_contract_mismatch_forces_lexical_scoring_with_real_store(tmp_path):
    store = BeliefStore("Recall Fallback", storage_dir=tmp_path / "beliefs")
    lexical_belief, _ = store.add_belief(
        Belief("Power grid constraints limit accelerator racks.", 0.9, domain="infra"),
        check_conflicts=False,
    )
    vector_belief, _ = store.add_belief(
        Belief("Employee travel policy changed.", 0.8, domain="infra"),
        check_conflicts=False,
    )
    store.upsert_belief_embedding(lexical_belief.id, [0.0, 1.0], model="local-test")
    store.upsert_belief_embedding(vector_belief.id, [1.0, 0.0], model="local-test")
    index = store.belief_embedding_stats(embedding_model="local-test")
    preference = {
        **_eligible_vector_preference(),
        "index_state_digest": index["state_digest"],
        "retrieval_contract": {"top_k": 1, "domain": "infra", "min_score": 0.0},
    }

    routed = build_verification_recall_candidates(
        _extraction([_ready("cand-1", "Power grid constraints limit accelerator racks.")]),
        store,
        domain="infra",
        top_k=2,
        query_embeddings_by_candidate_id={"cand-1": [1.0, 0.0]},
        embedding_model="local-test",
        route_preference=preference,
    )

    assert routed["cand-1"][0]["item_id"] == lexical_belief.id
    assert routed["cand-1"][0]["method"] == LEXICAL_METHOD
    assert "route_preference" not in routed["cand-1"][0]["metadata"]
