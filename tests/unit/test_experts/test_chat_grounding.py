"""Tests for grounding expert chat in the maintained belief graph.

Covers the three things that matter: the summary reflects *current* (decayed,
trust-capped) confidence rather than the stored number, building the summary
never writes, and recording usage updates the retrieval counters that the
archival lifecycle uses to protect load-bearing beliefs.
"""

from pathlib import Path

import pytest

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.chat_grounding import (
    build_stored_belief_grounding,
    record_grounded_retrieval,
)


@pytest.fixture
def expert_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point canonical_expert_dir at a temp directory for one expert."""
    root = tmp_path / "expert"
    (root / "beliefs").mkdir(parents=True)
    monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda _name, base_path=None: root)
    return root


def _seed(root: Path, claims: list[tuple[str, float]]) -> BeliefStore:
    store = BeliefStore("Test Expert", storage_dir=root / "beliefs")
    for claim, confidence in claims:
        store.add_belief(Belief(claim=claim, confidence=confidence, domain="testing"))
    return store


def test_returns_none_without_a_belief_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda _n, base_path=None: tmp_path / "missing")
    assert build_stored_belief_grounding("Test Expert") is None


def test_returns_none_when_store_has_no_beliefs(expert_root: Path) -> None:
    _seed(expert_root, [])
    assert build_stored_belief_grounding("Test Expert") is None


def test_summary_ranks_by_current_confidence_and_exposes_ids(expert_root: Path) -> None:
    _seed(expert_root, [("Weak claim", 0.30), ("Strong claim", 0.95)])

    grounding = build_stored_belief_grounding("Test Expert")

    assert grounding is not None
    # Strongest first, so the ordering reflects what the expert believes most.
    assert grounding.summary.index("Strong claim") < grounding.summary.index("Weak claim")
    assert len(grounding.belief_ids) == 2
    # Ids are what make record_retrieval possible at all.
    assert all(isinstance(bid, str) and bid for bid in grounding.belief_ids)


def test_summary_respects_the_limit(expert_root: Path) -> None:
    _seed(expert_root, [(f"Claim {i}", 0.9 - i / 100) for i in range(8)])

    grounding = build_stored_belief_grounding("Test Expert", limit=3)

    assert grounding is not None
    assert len(grounding.belief_ids) == 3


def test_building_the_summary_does_not_write(expert_root: Path) -> None:
    _seed(expert_root, [("A durable claim", 0.9)])
    beliefs_file = expert_root / "beliefs" / "beliefs.json"
    before = beliefs_file.read_bytes()

    build_stored_belief_grounding("Test Expert")

    # The read-only contract: the pure summary path must leave state untouched.
    assert beliefs_file.read_bytes() == before


def test_record_grounded_retrieval_updates_usage_counters(expert_root: Path) -> None:
    store = _seed(expert_root, [("A load-bearing claim", 0.9)])
    belief_id = next(iter(store.beliefs))

    updated = record_grounded_retrieval("Test Expert", [belief_id])

    assert updated == 1
    reloaded = BeliefStore("Test Expert", read_only=True, read_path=expert_root / "beliefs" / "beliefs.json")
    belief = reloaded.beliefs[belief_id]
    # last_retrieved_at is the signal archive_candidates uses to protect a
    # belief that is actually being used; before this wiring it was always None.
    assert belief.retrieval_count == 1
    assert belief.last_retrieved_at is not None


def test_record_grounded_retrieval_is_a_noop_without_ids(expert_root: Path) -> None:
    _seed(expert_root, [("A claim", 0.9)])
    assert record_grounded_retrieval("Test Expert", []) == 0


def test_record_grounded_retrieval_survives_a_missing_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda _n, base_path=None: tmp_path / "missing")
    # Usage salience is telemetry; a missing store must never fail a chat turn.
    assert record_grounded_retrieval("Test Expert", ["belief-1"]) == 0
