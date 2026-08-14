"""Belief lifecycle and salience (docs/design/belief-lifecycle.md).

Covers the v2.15 lifecycle substrate:
- bi-temporal valid time on belief events (world time vs record time)
- lossless archival (snapshot in the event) + restore_belief round-trip
- usage salience counters (record_retrieval; protective-only semantics)
- archive_candidates gates (confidence floor, recency, usage, contested)
- archive_stale consolidation pass
- read-side purity: the $0 query surface never records usage
- health-check surfacing of archive candidates
"""

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from deepr.experts.beliefs import Belief, BeliefChange, BeliefStore
from deepr.experts.mutation_audit import state_hash


@pytest.fixture
def store(tmp_path):
    return BeliefStore("Lifecycle Test Expert", storage_dir=tmp_path / "beliefs")


def _insert(store: BeliefStore, belief: Belief) -> Belief:
    """Insert directly, bypassing similarity-merge and conflict detection.

    The lifecycle gate tests target the candidate policy, not the add
    path; direct insertion keeps each fixture belief independent.
    """
    store.beliefs[belief.id] = belief
    store._index_belief(belief)
    return belief


def _stale_belief(claim: str, *, days_old: int = 120, confidence: float = 0.3) -> Belief:
    """A belief whose decayed confidence is under the 0.2 archival floor."""
    old = datetime.now(UTC) - timedelta(days=days_old)
    return Belief(claim=claim, confidence=confidence, domain="test", created_at=old, updated_at=old)


class TestBiTemporalEvents:
    def test_plain_event_omits_optional_fields(self):
        change = BeliefChange(belief_id="b1", change_type="created", new_claim="x", new_confidence=0.8)
        d = change.to_dict()
        assert "invalidated_at" not in d
        assert "snapshot" not in d

    def test_invalidated_at_round_trips(self):
        world_time = datetime(2026, 1, 15, tzinfo=UTC)
        change = BeliefChange(
            belief_id="b1",
            change_type="archived",
            new_claim="",
            new_confidence=0.0,
            invalidated_at=world_time,
        )
        restored = BeliefChange.from_dict(change.to_dict())
        assert restored.invalidated_at == world_time

    def test_pre_change_event_line_still_parses(self):
        # An event written before the bi-temporal fields existed.
        legacy = {
            "belief_id": "b1",
            "change_type": "updated",
            "old_claim": "a",
            "new_claim": "a",
            "old_confidence": 0.5,
            "new_confidence": 0.6,
            "reason": "",
            "evidence": "",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        change = BeliefChange.from_dict(legacy)
        assert change.invalidated_at is None
        assert change.snapshot is None

    def test_revise_belief_records_world_time(self, store):
        belief, _ = store.add_belief(Belief(claim="GPT-5 is the latest model", confidence=0.8, domain="ai"))
        world_time = datetime(2026, 3, 1, tzinfo=UTC)
        store.revise_belief(
            belief.id, "GPT-5.5 is the latest model", 0.85, reason="superseded", invalidated_at=world_time
        )
        events = store.iter_events()
        revised = [e for e in events if e.change_type == "revised"]
        assert revised and revised[-1].invalidated_at == world_time

    def test_archive_belief_records_world_time(self, store):
        belief, _ = store.add_belief(Belief(claim="The API sunset is pending", confidence=0.7, domain="ai"))
        world_time = datetime(2026, 2, 1, tzinfo=UTC)
        store.archive_belief(belief.id, reason="sunset happened", invalidated_at=world_time)
        archived = [e for e in store.iter_events() if e.change_type == "archived"]
        assert archived and archived[-1].invalidated_at == world_time


class TestLosslessArchival:
    def test_archival_event_carries_full_snapshot(self, store):
        belief, _ = store.add_belief(
            Belief(
                claim="Snapshot test claim",
                confidence=0.7,
                domain="test",
                evidence_refs=["report:abc", "report:def"],
                trust_class="secondary",
            )
        )
        store.archive_belief(belief.id, reason="testing")
        archived = [e for e in store.iter_events() if e.change_type == "archived"][-1]
        assert archived.snapshot is not None
        assert archived.snapshot["claim"] == "Snapshot test claim"
        assert archived.snapshot["evidence_refs"] == ["report:abc", "report:def"]
        assert archived.snapshot["trust_class"] == "secondary"

    def test_restore_round_trips_belief(self, store):
        belief, _ = store.add_belief(
            Belief(
                claim="Restorable claim",
                confidence=0.65,
                domain="test",
                evidence_refs=["report:xyz"],
                trust_class="secondary",
            )
        )
        belief_id = belief.id
        store.archive_belief(belief_id, reason="round trip")
        assert belief_id not in store.beliefs

        restored = store.restore_belief(belief_id)
        assert restored is not None
        assert restored.id == belief_id
        assert restored.claim == "Restorable claim"
        assert restored.evidence_refs == ["report:xyz"]
        assert restored.trust_class == "secondary"
        assert belief_id in store.beliefs
        # Restoration is event-logged
        assert any(e.belief_id == belief_id and "restored" in e.reason for e in store.iter_events())

    def test_restore_survives_reload(self, store):
        belief, _ = store.add_belief(Belief(claim="Persistent restore", confidence=0.6, domain="test"))
        store.archive_belief(belief.id)
        # A fresh store instance restores purely from the on-disk event log.
        fresh = BeliefStore("Lifecycle Test Expert", storage_dir=store.storage_dir)
        restored = fresh.restore_belief(belief.id)
        assert restored is not None and restored.claim == "Persistent restore"

    def test_restore_returns_live_belief_unchanged(self, store):
        belief, _ = store.add_belief(Belief(claim="Still live", confidence=0.8, domain="test"))
        assert store.restore_belief(belief.id) is belief

    def test_restore_unknown_belief_returns_none(self, store):
        assert store.restore_belief("nonexistent") is None

    def test_restore_pre_snapshot_archive_returns_none(self, store):
        # Archival events written before the snapshot field existed cannot
        # be restored; the method must say so rather than fabricate.
        change = BeliefChange(
            belief_id="legacy1", change_type="archived", new_claim="", new_confidence=0.0, old_claim="legacy claim"
        )
        store._record_change(change)
        assert store.restore_belief("legacy1") is None


class TestMutationAudit:
    def test_create_update_archive_restore_records_state_hashes(self, store):
        belief, _ = store.add_belief(Belief(claim="Audited claim", confidence=0.7, domain="test"))

        created = store.iter_mutation_audit()[-1]
        assert created.schema_version == "deepr-expert-mutation-audit-v1"
        assert created.operation == "created"
        assert created.expert == "Lifecycle Test Expert"
        assert created.actor == "deepr"
        assert created.belief_id == belief.id
        assert created.before_hash is None
        assert created.after_hash == state_hash(store.beliefs[belief.id].to_dict())

        store.update_belief(belief.id, new_confidence=0.8, reason="stronger source")
        updated = store.iter_mutation_audit()[-1]
        assert updated.operation == "updated"
        assert updated.before_hash == created.after_hash
        assert updated.after_hash == state_hash(store.beliefs[belief.id].to_dict())

        store.archive_belief(belief.id, reason="retired")
        archived = store.iter_mutation_audit()[-1]
        assert archived.operation == "archived"
        assert archived.before_hash == updated.after_hash
        assert archived.after_hash is None

        restored = store.restore_belief(belief.id)
        assert restored is not None
        restored_entry = store.iter_mutation_audit()[-1]
        assert restored_entry.operation == "restored"
        assert restored_entry.before_hash is None
        assert restored_entry.after_hash == archived.before_hash

    def test_mutation_audit_survives_reload_and_since_filter(self, store):
        first, _ = store.add_belief(Belief(claim="First audited claim", confidence=0.7, domain="test"))
        cutoff = store.iter_mutation_audit()[-1].timestamp
        second, _ = store.add_belief(Belief(claim="Second audited claim", confidence=0.8, domain="test"))

        fresh = BeliefStore("Lifecycle Test Expert", storage_dir=store.storage_dir)
        entries = fresh.iter_mutation_audit()
        assert [entry.belief_id for entry in entries] == [first.id, second.id]
        assert [entry.belief_id for entry in fresh.iter_mutation_audit(since=cutoff)] == [second.id]

    def test_lower_confidence_similar_claim_corroborates_without_overwriting(self, tmp_path):
        store = BeliefStore("Lifecycle Test Expert", storage_dir=tmp_path / "beliefs")
        high, _ = store.add_belief(
            Belief(
                claim="Python is a popular language",
                confidence=0.9,
                domain="python",
                evidence_refs=["report:file:a.md"],
                trust_class="tertiary",
            )
        )

        kept, change = store.add_belief(
            Belief(
                claim="Python is popular language",
                confidence=0.5,
                domain="python",
                evidence_refs=["report:file:b.md"],
                trust_class="tertiary",
            )
        )

        assert kept.id == high.id
        assert change is not None
        assert kept.claim == "Python is a popular language"
        assert kept.confidence == 0.9  # raw conf not raised by weaker candidate
        assert "report:file:a.md" in kept.evidence_refs
        assert "report:file:b.md" in kept.evidence_refs
        assert kept.get_current_confidence() == 0.8  # two independent tertiary sources
        audited = store.iter_mutation_audit()[-1]
        assert audited.operation == "updated"
        assert audited.belief_id == high.id

    def test_negated_claim_does_not_corroborate_into_a_higher_ceiling(self, tmp_path):
        """A contradicting source must never read as independent corroboration.

        Word overlap cannot see negation, so without a polarity guard the
        opposite claim would dedup-merge and lift the single-source tertiary
        ceiling from 0.60 to 0.80 - inverting the poisoned-ingestion backstop.
        """
        store = BeliefStore("Polarity Test Expert", storage_dir=tmp_path / "beliefs")
        original, _ = store.add_belief(
            Belief(
                claim="Release 2.0 is the latest supported version",
                confidence=0.9,
                domain="releases",
                evidence_refs=["report:file:a.md"],
                trust_class="tertiary",
            )
        )

        opposing, _ = store.add_belief(
            Belief(
                claim="Release 2.0 is not the latest supported version",
                confidence=0.9,
                domain="releases",
                evidence_refs=["report:file:b.md"],
                trust_class="tertiary",
            )
        )

        assert opposing.id != original.id, "opposite-polarity claims must not merge"
        kept = store.beliefs[original.id]
        assert "report:file:b.md" not in kept.evidence_refs
        assert kept.get_current_confidence() == 0.6  # still single-source tertiary

    def test_negation_guard_survives_adjacent_punctuation(self, tmp_path):
        """Whitespace splitting leaves "not," attached and slips past the guard.

        The polarity test must tokenize on word characters, or the guard fails
        on exactly the natural phrasings a real source uses.
        """
        store = BeliefStore("Punctuation Test Expert", storage_dir=tmp_path / "beliefs")
        original, _ = store.add_belief(
            Belief(
                claim="Release 2.0 is the latest supported version",
                confidence=0.9,
                domain="releases",
                evidence_refs=["report:file:a.md"],
                trust_class="tertiary",
            )
        )

        opposing, _ = store.add_belief(
            Belief(
                claim="Release 2.0 is not, in fact, the latest supported version",
                confidence=0.9,
                domain="releases",
                evidence_refs=["report:file:b.md"],
                trust_class="tertiary",
            )
        )

        assert opposing.id != original.id
        kept = store.beliefs[original.id]
        assert "report:file:b.md" not in kept.evidence_refs
        assert kept.get_current_confidence() == 0.6


class TestUsageSalience:
    def test_record_retrieval_bumps_counters(self, store):
        belief, _ = store.add_belief(Belief(claim="Used belief", confidence=0.8, domain="test"))
        assert belief.retrieval_count == 0
        assert belief.last_retrieved_at is None

        touched = store.record_retrieval([belief.id], context="unit test")
        assert touched == 1
        assert belief.retrieval_count == 1
        assert belief.last_retrieved_at is not None

    def test_record_retrieval_persists(self, store):
        belief, _ = store.add_belief(Belief(claim="Persisted usage", confidence=0.8, domain="test"))
        store.record_retrieval([belief.id])
        fresh = BeliefStore("Lifecycle Test Expert", storage_dir=store.storage_dir)
        assert fresh.beliefs[belief.id].retrieval_count == 1
        assert fresh.beliefs[belief.id].last_retrieved_at is not None

    def test_record_retrieval_ignores_unknown_ids(self, store):
        assert store.record_retrieval(["missing1", "missing2"]) == 0

    def test_retrieval_fields_survive_serialization(self):
        now = datetime.now(UTC)
        belief = Belief(claim="Ser test", confidence=0.5, retrieval_count=3, last_retrieved_at=now)
        restored = Belief.from_dict(belief.to_dict())
        assert restored.retrieval_count == 3
        assert restored.last_retrieved_at == now

    def test_pre_change_belief_dict_still_parses(self):
        legacy = {
            "claim": "Old belief",
            "confidence": 0.7,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        belief = Belief.from_dict(legacy)
        assert belief.retrieval_count == 0
        assert belief.last_retrieved_at is None


class TestArchiveCandidates:
    def test_decayed_unused_uncontested_is_candidate(self, store):
        belief = _insert(store, _stale_belief("Decayed and unused"))
        assert belief.get_current_confidence() < 0.2
        candidates = store.archive_candidates()
        assert [b.id for b in candidates] == [belief.id]

    def test_confidence_above_floor_protects(self, store):
        old = datetime.now(UTC) - timedelta(days=120)
        _insert(
            store,
            Belief(
                claim="Still confident",
                confidence=0.9,
                domain="test",
                created_at=old,
                updated_at=old,
                decay_rate=0.001,
                trust_class="secondary",
            ),
        )
        assert store.archive_candidates() == []

    def test_recent_update_protects(self, store):
        # Below the floor even fresh, but recently updated: not a candidate.
        _insert(store, Belief(claim="Fresh but weak", confidence=0.05, domain="test"))
        assert store.archive_candidates() == []

    def test_recent_retrieval_protects(self, store):
        belief = _insert(store, _stale_belief("Stale but used"))
        belief.last_retrieved_at = datetime.now(UTC)
        assert store.archive_candidates() == []

    def test_contested_belief_is_never_a_candidate(self, store):
        belief = _insert(store, _stale_belief("Stale but contested"))
        other = _insert(store, Belief(claim="The opposing side of the contest", confidence=0.8, domain="test"))
        store.add_edge(belief.id, other.id, "contradicts", provenance="test")
        assert store.archive_candidates() == []

    def test_candidates_sorted_weakest_first(self, store):
        weaker = _insert(store, _stale_belief("Very weak claim about topic A", days_old=300, confidence=0.3))
        stronger = _insert(store, _stale_belief("Slightly stronger claim about topic B", days_old=95, confidence=0.4))
        ids = [b.id for b in store.archive_candidates()]
        assert ids == [weaker.id, stronger.id]


class TestArchiveStale:
    def test_archives_all_candidates_with_snapshots(self, store):
        a = _insert(store, _stale_belief("Stale claim one about topic X"))
        b = _insert(store, _stale_belief("Stale claim two about topic Y"))
        keep = _insert(store, Belief(claim="Fresh claim", confidence=0.9, domain="test", trust_class="secondary"))

        changes = store.archive_stale()
        assert {c.belief_id for c in changes} == {a.id, b.id}
        assert all(c.snapshot is not None for c in changes)
        assert all("lifecycle" in c.reason for c in changes)
        assert keep.id in store.beliefs
        assert a.id not in store.beliefs and b.id not in store.beliefs

    def test_archive_stale_is_reversible(self, store):
        belief = _insert(store, _stale_belief("Reversible stale claim"))
        store.archive_stale()
        restored = store.restore_belief(belief.id)
        assert restored is not None and restored.claim == "Reversible stale claim"

    def test_noop_when_nothing_qualifies(self, store):
        _insert(store, Belief(claim="Healthy belief", confidence=0.9, domain="test", trust_class="secondary"))
        assert store.archive_stale() == []


class TestReadSidePurity:
    """The $0 query surface must never record usage (MCP READ_ONLY depends on it)."""

    def test_read_side_queries_never_record_retrieval(self, store):
        belief, _ = store.add_belief(Belief(claim="Read-side purity test belief", confidence=0.8, domain="test"))

        from deepr.experts.digest import build_digest
        from deepr.experts.perspective import contested, explain_belief, what_changed

        with patch.object(BeliefStore, "record_retrieval", side_effect=AssertionError("read path recorded usage")):
            build_digest(store)
            contested(store, expert_name="Lifecycle Test Expert")
            what_changed(store, since=datetime.now(UTC) - timedelta(days=1), expert_name="Lifecycle Test Expert")
            explain_belief(store, belief.id, expert_name="Lifecycle Test Expert")


class TestHealthCheckSurfacing:
    def _profile(self):
        from unittest.mock import MagicMock

        profile = MagicMock()
        profile.name = "Lifecycle Test Expert"
        profile.domain = "test"
        return profile

    def test_archive_candidates_finding_and_action(self):
        from deepr.experts.health_check import ExpertHealthChecker

        checker = ExpertHealthChecker(self._profile())
        summaries = [
            {
                "id": "b1",
                "claim": "Old claim",
                "confidence": 0.1,
                "updated_at": "2026-01-01T00:00:00+00:00",
                "retrieval_count": 0,
            }
        ]
        with patch.object(checker, "_archive_candidate_summaries", return_value=summaries):
            finding, action = checker._check_archive_candidates(None, [])

        assert finding.category == "archive_candidates"
        assert finding.severity == "info"
        assert finding.detail["count"] == 1
        assert action is not None
        assert "--archive-stale" in action.command
        assert action.estimated_cost == 0.0
        assert action.approval_tier == "confirm"

    def test_no_candidates_is_ok(self):
        from deepr.experts.health_check import ExpertHealthChecker

        checker = ExpertHealthChecker(self._profile())
        with patch.object(checker, "_archive_candidate_summaries", return_value=[]):
            finding, action = checker._check_archive_candidates(None, [])
        assert finding.severity == "ok"
        assert action is None

    def test_candidate_loader_does_not_create_state(self, tmp_path, monkeypatch):
        from deepr.experts.health_check import ExpertHealthChecker

        monkeypatch.chdir(tmp_path)
        checker = ExpertHealthChecker(self._profile())
        assert checker._archive_candidate_summaries() == []
        assert not (tmp_path / "data").exists()


class TestDecayNeverRaisesConfidence:
    """Decay is a one-way function. A future timestamp used to invert it.

    ``get_current_confidence`` computed ``now - updated_at`` and fed it to
    ``exp(-rate * days)``. A belief stamped in the future gives a negative
    elapsed, so the exponent turns positive and the result exceeds the stored
    value; the trust-ceiling cap then pinned it at the maximum. A belief stored
    at 0.50 came back as 0.60 - the one record with a reason to be distrusted
    reading as maximally trustworthy.

    Clock skew between machines writing to a synced expert folder is the
    realistic way this happens, which is exactly the setup where the two
    machines disagree about what is current.
    """

    def _belief(self, *, days_offset: int) -> Belief:
        belief = Belief(claim="a claim", domain="d", confidence=0.5)
        belief.decay_rate = 0.01
        belief.updated_at = datetime.now(UTC) + timedelta(days=days_offset)
        return belief

    def test_a_future_timestamp_does_not_inflate_confidence(self) -> None:
        assert self._belief(days_offset=30).get_current_confidence() == pytest.approx(0.5)

    def test_a_far_future_timestamp_does_not_inflate_confidence(self) -> None:
        assert self._belief(days_offset=3650).get_current_confidence() == pytest.approx(0.5)

    def test_the_past_still_decays(self) -> None:
        """The fix must not flatten decay into a no-op."""
        assert self._belief(days_offset=-30).get_current_confidence() < 0.5

    def test_decay_never_exceeds_the_stored_value(self) -> None:
        for offset in (-365, -30, -1, 0, 1, 30, 365):
            assert self._belief(days_offset=offset).get_current_confidence() <= 0.5

    def test_historical_read_does_not_apply_today_decay(self) -> None:
        """A point-in-time read must decay against that instant, not wall-clock now."""
        belief = self._belief(days_offset=-30)
        then = belief.updated_at + timedelta(days=1)
        today = belief.get_current_confidence()
        historical = belief.get_current_confidence(as_of=then)
        assert historical == pytest.approx(0.5 * math.exp(-0.01 * 1))
        assert today < historical

    def test_naive_stored_timestamp_does_not_crash_decay(self) -> None:
        """Legacy or hand-edited beliefs may lack tzinfo; decay must still run."""
        belief = Belief(claim="a claim", domain="d", confidence=0.5)
        belief.decay_rate = 0.01
        belief.updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
        assert 0.0 <= belief.get_current_confidence() <= 0.5

    def test_naive_iso_round_trip_stays_comparable(self) -> None:
        payload = Belief(claim="a claim", domain="d", confidence=0.5).to_dict()
        payload["created_at"] = "2024-01-01T00:00:00"
        payload["updated_at"] = "2024-01-01T00:00:00"
        loaded = Belief.from_dict(payload)
        assert loaded.updated_at.tzinfo is not None
        assert loaded.get_current_confidence() <= 0.5
