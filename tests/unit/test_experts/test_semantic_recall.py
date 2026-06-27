"""Tests for semantic memory recall candidate routing."""

from __future__ import annotations

from unittest.mock import patch

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.lazy_graph_rag import Concept
from deepr.experts.semantic_recall import (
    CANDIDATE_ONLY,
    LEXICAL_METHOD,
    VECTOR_METHOD,
    recall_concept_candidates,
)


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Recall Test Expert", storage_dir=tmp_path / "beliefs")


def test_vector_belief_recall_routes_paraphrases_without_claiming_truth(tmp_path):
    store = _store(tmp_path)
    relevant, _ = store.add_belief(
        Belief(
            claim="Advanced packaging shortages limit accelerator rack shipments.",
            confidence=0.8,
            domain="ai-infra",
        )
    )
    unrelated, _ = store.add_belief(
        Belief(
            claim="EU AI Act enforcement creates compliance obligations.",
            confidence=0.7,
            domain="ai-policy",
        )
    )

    candidates = store.recall_belief_candidates(
        "GPU supply delays constrain Blackwell deployment",
        top_k=2,
        query_embedding=[1.0, 0.0],
        belief_embeddings={
            relevant.id: [0.98, 0.02],
            unrelated.id: [0.0, 1.0],
        },
        include_lexical_fallback=False,
    )

    assert [candidate.item_id for candidate in candidates] == [relevant.id, unrelated.id]
    assert candidates[0].method == VECTOR_METHOD
    assert candidates[0].verdict == CANDIDATE_ONLY
    assert candidates[0].guidance == "routing_only"
    assert candidates[0].payload is relevant


def test_lexical_fallback_is_labeled_as_router_only(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(
        Belief(
            claim="Python 3.12 improves typing features.",
            confidence=0.8,
            domain="python",
        )
    )

    candidates = store.recall_belief_candidates("typing changes in Python", top_k=1)

    assert candidates[0].item_id == belief.id
    assert candidates[0].method == LEXICAL_METHOD
    assert candidates[0].verdict == CANDIDATE_ONLY
    assert "python" in candidates[0].matched_terms


def test_contradiction_candidate_recall_is_same_domain_and_excludes_self(tmp_path):
    store = _store(tmp_path)
    candidate, _ = store.add_belief(
        Belief(
            claim="The model supports a one-million-token context window.",
            confidence=0.7,
            domain="models",
        )
    )
    nearby, _ = store.add_belief(
        Belief(
            claim="The model context window is capped far below one million tokens.",
            confidence=0.8,
            domain="models",
        )
    )
    other_domain, _ = store.add_belief(
        Belief(
            claim="One million token corpora are useful for archive analysis.",
            confidence=0.8,
            domain="data",
        )
    )

    candidates = store.recall_contradiction_candidates(
        candidate,
        query_embedding=[1.0, 0.0],
        belief_embeddings={
            candidate.id: [1.0, 0.0],
            nearby.id: [0.99, 0.01],
            other_domain.id: [0.99, 0.01],
        },
        include_lexical_fallback=False,
    )

    assert [item.item_id for item in candidates] == [nearby.id]
    assert all(item.item_id != candidate.id for item in candidates)
    assert all(item.domain == "models" for item in candidates)
    assert store.edges_for(candidate.id, "contradicts") == []


def test_concept_recall_uses_same_candidate_contract():
    concept = Concept(text="temporal knowledge graph", concept_type="heading", frequency=3)
    other = Concept(text="frontend dashboard layout", concept_type="noun_phrase", frequency=1)

    candidates = recall_concept_candidates(
        "agent memory temporal graph",
        [concept, other],
        query_embedding=[1.0, 0.0],
        concept_embeddings={
            concept.id: [0.9, 0.1],
            other.id: [0.0, 1.0],
        },
        include_lexical_fallback=False,
    )

    assert candidates[0].kind == "concept"
    assert candidates[0].item_id == concept.id
    assert candidates[0].method == VECTOR_METHOD
    assert candidates[0].verdict == CANDIDATE_ONLY


def test_recall_does_not_write_belief_store(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief(claim="Read-only recall candidate.", confidence=0.8, domain="test"))

    with patch.object(store, "_save", side_effect=AssertionError("recall wrote store state")):
        with patch.object(store, "_record_change", side_effect=AssertionError("recall wrote event state")):
            candidates = store.recall_belief_candidates("read only candidate", top_k=1)

    assert len(candidates) == 1
    assert store.get_recent_changes(limit=10)
