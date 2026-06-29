"""Tests for semantic memory recall candidate routing."""

from __future__ import annotations

from unittest.mock import patch

from deepr.core.contracts import ExpertOriginalIdea
from deepr.experts.belief_vector_index import BELIEF_VECTOR_INDEX_SCHEMA_VERSION, BeliefVectorIndex
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.lazy_graph_rag import Concept
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.semantic_recall import (
    CANDIDATE_ONLY,
    LEXICAL_METHOD,
    VECTOR_METHOD,
    recall_concept_candidates,
    recall_original_idea_candidates,
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


def test_belief_vector_index_persists_and_filters_stale_claims(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(
        Belief(
            claim="Vector recall finds paraphrased belief memory.",
            confidence=0.8,
            domain="memory",
        )
    )
    index = BeliefVectorIndex.for_belief_store(store.storage_dir)

    assert index.upsert_belief(belief, [0.7, 0.3], model="local-test")

    loaded = BeliefVectorIndex.for_belief_store(store.storage_dir)
    assert loaded.stats(store.beliefs.values(), model="local-test") == {
        "schema_version": BELIEF_VECTOR_INDEX_SCHEMA_VERSION,
        "record_count": 1,
        "current_vector_count": 1,
        "missing_or_stale_count": 0,
        "dimensions": [2],
        "path": str(store.storage_dir / "belief_vectors.json"),
    }
    assert loaded.vectors_for(store.beliefs.values(), model="local-test") == {belief.id: (0.7, 0.3)}

    belief.claim = "The claim changed after the vector was generated."

    assert loaded.vectors_for(store.beliefs.values(), model="local-test") == {}
    assert loaded.missing_or_stale_ids(store.beliefs.values(), model="local-test") == [belief.id]


def test_store_recall_uses_persisted_belief_vectors(tmp_path):
    store = _store(tmp_path)
    relevant, _ = store.add_belief(
        Belief(
            claim="Rack-level power limits delay accelerator deployment.",
            confidence=0.8,
            domain="ai-infra",
        )
    )
    unrelated, _ = store.add_belief(
        Belief(
            claim="Data retention policies drive compliance review cycles.",
            confidence=0.8,
            domain="governance",
        )
    )
    store.upsert_belief_embedding(relevant.id, [1.0, 0.0], model="local-test")
    store.upsert_belief_embedding(unrelated.id, [0.0, 1.0], model="local-test")

    candidates = store.recall_belief_candidates(
        "GPU rollout bottleneck",
        top_k=1,
        query_embedding=[0.97, 0.03],
        embedding_model="local-test",
        include_lexical_fallback=False,
    )

    assert [candidate.item_id for candidate in candidates] == [relevant.id]
    assert candidates[0].method == VECTOR_METHOD
    assert candidates[0].verdict == CANDIDATE_ONLY
    assert candidates[0].metadata["confidence"] == 0.8


def test_store_recall_ignores_stale_index_vectors(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(
        Belief(
            claim="A current claim has a matching vector.",
            confidence=0.8,
            domain="memory",
        )
    )
    store.upsert_belief_embedding(belief.id, [1.0, 0.0], model="local-test")
    belief.claim = "The claim changed after embedding."

    candidates = store.recall_belief_candidates(
        "current claim",
        query_embedding=[1.0, 0.0],
        embedding_model="local-test",
        include_lexical_fallback=False,
    )

    assert candidates == []
    assert store.missing_belief_embedding_ids(embedding_model="local-test") == [belief.id]


def test_archive_prunes_belief_vector_index(tmp_path):
    store = _store(tmp_path)
    belief, _ = store.add_belief(
        Belief(
            claim="Archived beliefs should not keep active recall vectors.",
            confidence=0.8,
            domain="memory",
        )
    )
    store.upsert_belief_embedding(belief.id, [1.0, 0.0], model="local-test")

    change = store.archive_belief(belief.id, reason="covered by a newer belief")

    assert change is not None
    assert BeliefVectorIndex.for_belief_store(store.storage_dir).records == {}
    assert store.belief_embedding_stats(embedding_model="local-test")["record_count"] == 0


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


def test_original_idea_recall_is_labeled_as_perspective_state():
    idea = ExpertOriginalIdea.create(
        "Statistician council packets",
        statement="Use a statistician council to turn agent consults into measurable review packets.",
        rationale="The expert should retain the idea without treating it as an external fact.",
        uncertainty="The idea still needs repeated consult-trace evidence.",
        assumptions=["Consult traces can expose variables, outcomes, and tradeoffs."],
        implications=["Future expert councils can emit more measurable plans."],
        expected_observations=["Future consult plans cite variables and acceptance criteria."],
        disconfirming_signals=["Consult quality does not improve after the idea is used."],
        confidence=0.72,
        priority=4,
    )

    candidates = recall_original_idea_candidates(
        "measurable statistician review packets",
        [idea],
        query_embedding=[1.0, 0.0],
        original_idea_embeddings={idea.id: [0.96, 0.04]},
        include_lexical_fallback=False,
    )

    assert len(candidates) == 1
    assert candidates[0].item_id == idea.id
    assert candidates[0].kind == "original_idea"
    assert candidates[0].method == VECTOR_METHOD
    assert candidates[0].verdict == CANDIDATE_ONLY
    assert candidates[0].metadata["authority"] == "perspective_state"
    assert candidates[0].metadata["factual_claim"] is False
    assert candidates[0].metadata["semantic_verdict"] is False
    assert candidates[0].metadata["schema_version"] == "deepr-expert-perspective-state-v1"
    assert candidates[0].payload is idea


def test_original_idea_recall_on_tracker_is_read_only(tmp_path):
    tracker = MetaCognitionTracker("Recall Ideas Expert", base_path=str(tmp_path))
    idea = ExpertOriginalIdea.create(
        "Statistical expert council",
        statement="A role-diverse expert council should expose variables, assumptions, and disconfirmation checks.",
        rationale="Planning improves when dissent and metrics are first-class.",
        expected_observations=["Council outputs include variables and acceptance criteria."],
        disconfirming_signals=["Plans remain vague after repeated use."],
        confidence=0.8,
        priority=5,
    )
    tracker.promote_original_idea_candidate(
        idea,
        proposal_id="original-idea-recall",
        evidence_refs=["source_note:note:w0"],
        source="test",
    )

    with patch.object(tracker, "_save", side_effect=AssertionError("recall wrote tracker state")):
        candidates = tracker.recall_original_idea_candidates("expert council disconfirmation metrics", top_k=1)

    assert len(candidates) == 1
    assert candidates[0].item_id == idea.id
    assert candidates[0].metadata["promotion_policy"].startswith("Not a verified external fact")
    assert tracker.uncertainty_log[-1]["action"] == "promoted_original_idea_candidate"
