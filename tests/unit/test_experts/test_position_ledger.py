"""Positions that survive a re-brief, and a record of what changed them.

The defect being removed is the largest destruction of judgement in the system:
every `expert brief` discarded the previous positions - likelihood bands,
falsifiers, carried dissent - and re-derived from scratch, so an expert that
had existed six months had concluded nothing that outlived its last run.

Three distinctions carry the design, and each is tested here: unchanged is not
a new version, revised is not a replacement, and not-restated is not a
retirement.
"""

from types import SimpleNamespace

from deepr.experts.position_ledger import (
    REASON_NOT_RESTATED,
    REASON_REVISED,
    PositionLedger,
    record_brief,
)
from deepr.experts.record_time import END_OF_TIME

JAN = "2026-01-01T00:00:00+00:00"
JUN = "2026-06-01T00:00:00+00:00"
DEC = "2026-12-01T00:00:00+00:00"


def _position(question, *, stance="it holds", likelihood="likely", falsifier="a counterexample", supported=("f1",)):
    return SimpleNamespace(
        question=question,
        stance=stance,
        likelihood=likelihood,
        confidence="moderate",
        would_change_my_mind=falsifier,
        unresolved_dissent="",
        supported_by=list(supported),
    )


class TestAThreadSurvivesARebrief:
    def test_the_same_question_keeps_one_thread_across_revisions(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Does X hold?")], at=JAN, corpus_fingerprint="c1")
        record_brief(
            ledger, [_position("Does X hold?", likelihood="roughly even chance")], at=JUN, corpus_fingerprint="c2"
        )

        assert ledger.stats()["threads"] == 1
        assert ledger.stats()["versions"] == 2

    def test_a_revision_closes_the_prior_and_opens_a_successor(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN)
        record_brief(ledger, [_position("Q", stance="it does not hold")], at=JUN)

        history = ledger.history_of(ledger.versions[0].thread_id)
        assert history[0].superseded_at == JUN
        assert history[0].supersession_reason == REASON_REVISED
        assert history[0].superseded_by == history[1].version_id
        assert history[1].is_live

    def test_versions_tile_with_no_gap(self):
        """predecessor.superseded_at == successor.recorded_at, exactly."""
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN)
        record_brief(ledger, [_position("Q", stance="changed")], at=JUN)

        history = ledger.history_of(ledger.versions[0].thread_id)
        assert history[0].superseded_at == history[1].recorded_at

    def test_only_one_version_is_live_per_thread(self):
        ledger = PositionLedger(expert_name="E")
        for stamp, stance in ((JAN, "a"), (JUN, "b"), (DEC, "c")):
            record_brief(ledger, [_position("Q", stance=stance)], at=stamp)

        assert len(ledger.live) == 1
        assert ledger.live[0].stance == "c"


class TestAnIdenticalRestatementIsNotAVersion:
    def test_restating_the_same_position_adds_no_version(self):
        """A version differing in nothing is noise; the ledger exists to make
        real change visible."""
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN, corpus_fingerprint="c1")
        changed = record_brief(ledger, [_position("Q")], at=JUN, corpus_fingerprint="c2")

        assert changed["unchanged"] == 1
        assert changed["revised"] == 0
        assert len(ledger.versions) == 1

    def test_but_the_survival_evidence_is_kept(self):
        """Reaching the same position again from new material is the evidence."""
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN, corpus_fingerprint="c1")
        record_brief(ledger, [_position("Q")], at=JUN, corpus_fingerprint="c2")

        assert ledger.live[0].corpus_fingerprint == "c2"

    def test_the_question_alone_does_not_make_two_versions_differ(self):
        """The question is the thread identity, not part of the content."""
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Does X hold?")], at=JAN)
        record_brief(ledger, [_position("does x hold")], at=JUN)

        assert len(ledger.versions) == 1


class TestNotRestatedIsNotRetired:
    def test_a_position_a_rebrief_did_not_produce_is_closed(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q1"), _position("Q2")], at=JAN)
        changed = record_brief(ledger, [_position("Q1")], at=JUN)

        assert changed["not_restated"] == 1
        assert len(ledger.live) == 1

    def test_the_reason_says_only_that_it_was_not_restated(self):
        """The expert did not decide to drop it; a later pass did not reach it.
        Calling that a retirement would hide a position vanishing quietly."""
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q1"), _position("Q2")], at=JAN)
        record_brief(ledger, [_position("Q1")], at=JUN)

        dropped = next(v for v in ledger.versions if not v.is_live)
        assert dropped.supersession_reason == REASON_NOT_RESTATED
        assert dropped.superseded_by == ""

    def test_nothing_is_ever_deleted(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q1"), _position("Q2")], at=JAN)
        record_brief(ledger, [], at=JUN)

        assert len(ledger.versions) == 2
        assert ledger.live == []


class TestSurvivalIsEvidence:
    def test_it_counts_distinct_corpus_states_not_reruns(self):
        """Re-running over the same corpus proves nothing new."""
        ledger = PositionLedger(expert_name="E")
        for stamp in (JAN, JUN, DEC):
            record_brief(ledger, [_position("Q")], at=stamp, corpus_fingerprint="same")

        assert ledger.survived(ledger.versions[0].thread_id) == 1

    def test_reaching_it_again_from_new_material_counts(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN, corpus_fingerprint="c1")
        record_brief(ledger, [_position("Q", stance="restated")], at=JUN, corpus_fingerprint="c2")

        assert ledger.survived(ledger.versions[0].thread_id) == 2

    def test_a_fresh_position_has_survived_one_state(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN, corpus_fingerprint="c1")
        assert ledger.stats()["max_survived"] == 1


class TestPointInTime:
    def test_as_of_returns_what_was_held_then(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q", stance="first")], at=JAN)
        record_brief(ledger, [_position("Q", stance="second")], at=JUN)

        assert [v.stance for v in ledger.as_of("2026-03-01T00:00:00+00:00")] == ["first"]
        assert [v.stance for v in ledger.as_of(DEC)] == ["second"]

    def test_the_boundary_belongs_to_the_successor(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q", stance="first")], at=JAN)
        record_brief(ledger, [_position("Q", stance="second")], at=JUN)

        assert [v.stance for v in ledger.as_of(JUN)] == ["second"]

    def test_a_migrated_version_with_no_timestamp_reads_as_live(self):
        """A store written before this ledger existed must not vanish."""
        ledger = PositionLedger.from_dict(
            {"versions": [{"thread_id": "t", "version_id": "v", "question": "Q", "superseded_at": END_OF_TIME}]}
        )
        assert ledger.as_of(JUN)

    def test_history_is_oldest_first(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q", stance="a")], at=JAN)
        record_brief(ledger, [_position("Q", stance="b")], at=JUN)

        history = ledger.history_of(ledger.versions[0].thread_id)
        assert [v.stance for v in history] == ["a", "b"]


class TestHygiene:
    def test_a_position_with_no_question_is_skipped(self):
        ledger = PositionLedger(expert_name="E")
        assert record_brief(ledger, [_position("  ")], at=JAN)["new"] == 0

    def test_ordering_is_total_within_one_instant(self):
        """Two versions can share a timestamp, and as_of must not be ambiguous."""
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q1"), _position("Q2")], at=JAN)

        assert len({v.seq for v in ledger.versions}) == 2

    def test_the_ledger_round_trips(self):
        ledger = PositionLedger(expert_name="E")
        record_brief(ledger, [_position("Q")], at=JAN, corpus_fingerprint="c1")
        record_brief(ledger, [_position("Q", stance="revised")], at=JUN, corpus_fingerprint="c2")

        restored = PositionLedger.from_dict(ledger.to_dict())

        assert restored.stats() == ledger.stats()
        assert len(restored.live) == 1

    def test_junk_versions_are_dropped_rather_than_raising(self):
        restored = PositionLedger.from_dict({"versions": ["nope", {}, {"thread_id": "t"}]})
        assert len(restored.versions) == 1
