"""The biography of a viewpoint, not a store of what is true.

The distinction under test throughout: this graph's nodes are moments of coming
to see something and its edges are what changed what. An expert with two
hundred well-anchored positions and no recorded shifts has never been moved by
anything it read, which is the state a brand-new expert is already in.
"""

from itertools import pairwise
from types import SimpleNamespace

from deepr.experts.perspective_graph import (
    EDGE_BECAME,
    EDGE_HOLDS,
    EDGE_MOVED_BY,
    EDGE_PURSUING,
    EDGE_THROUGH,
    NODE_SHIFT,
    NODE_STANDPOINT,
    PerspectiveGraph,
    build_perspective_graph,
    render_perspective,
)


def _shift(was, now, because="new sources", at="2026-03-01T00:00:00+00:00", fingerprint=""):
    return SimpleNamespace(was=was, now=now, because=because, at=at, corpus_fingerprint=fingerprint)


def _profile(**overrides):
    defaults = dict(
        chosen_name="Hard Skip",
        standpoint="I read this as an operational discipline first.",
        voice="I refuse to average live contentions into false consensus.",
        open_questions=["how much scaffolding dissolves when the model improves"],
        shifts=[],
    )
    return SimpleNamespace(**{**defaults, **overrides})


def _built(**overrides):
    defaults = dict(expert_name="Agentic Harness Design", profile=_profile(), viva=None, at="2026-08-09T00:00:00+00:00")
    return build_perspective_graph(**{**defaults, **overrides})


class TestTheSpineIsTheShiftChain:
    def test_a_shift_links_the_old_reading_to_the_new_one(self):
        graph = _built(profile=_profile(shifts=[_shift("I read it as a naming problem.", "I read it as retraction.")]))

        assert [n.text for n in graph.standpoints][:2] == [
            "I read it as a naming problem.",
            "I read it as retraction.",
        ]
        assert any(e.kind == EDGE_BECAME for e in graph.edges)

    def test_the_change_records_what_caused_it(self):
        graph = _built(
            profile=_profile(shifts=[_shift("was", "now", because="the failure lens put retraction at the centre")])
        )
        assert [s.text for s in graph.shifts] == ["the failure lens put retraction at the centre"]
        assert any(e.kind == EDGE_THROUGH for e in graph.edges)

    def test_a_corpus_state_becomes_the_encounter_that_moved_it(self):
        graph = _built(profile=_profile(shifts=[_shift("was", "now", fingerprint="abc123")]))
        assert any(e.kind == EDGE_MOVED_BY for e in graph.edges)
        assert any("abc123" in n.text for n in graph.nodes)

    def test_successive_shifts_form_one_chain_rather_than_islands(self):
        """Each link starts where the previous one ended, all the way to today.

        Contiguity is the property, not the count: the current standpoint from
        the profile extends the chain past the last recorded shift, which is
        correct - the expert has read more since it last recorded moving.
        """
        graph = _built(
            profile=_profile(
                shifts=[
                    _shift("first", "second", at="2026-01-01T00:00:00+00:00"),
                    _shift("second", "third", at="2026-05-01T00:00:00+00:00"),
                ]
            )
        )
        became = [e for e in graph.edges if e.kind == EDGE_BECAME]

        assert len(became) >= 2
        for earlier, later in pairwise(became):
            assert earlier.target == later.source

    def test_the_chain_ends_at_the_standpoint_it_holds_today(self):
        graph = _built(profile=_profile(standpoint="today's reading", shifts=[_shift("was", "now")]))
        assert graph.current is not None
        assert graph.current.text == "today's reading"

    def test_a_shift_missing_either_side_is_not_a_shift(self):
        graph = _built(profile=_profile(shifts=[_shift("was", "")]))
        assert not graph.has_a_history


class TestHavingBeenMovedIsTheMeasurement:
    def test_an_expert_that_never_changed_its_mind_has_no_history(self):
        """It may have read a great deal. Nothing moved it."""
        graph = _built()
        assert graph.standpoints
        assert not graph.has_a_history

    def test_one_recorded_shift_is_a_history(self):
        assert _built(profile=_profile(shifts=[_shift("was", "now")])).has_a_history

    def test_the_render_says_so_plainly_when_nothing_moved_it(self):
        assert "nothing it read has moved it" in render_perspective(_built())


class TestWhatAFactModelWouldDiscard:
    def test_conduct_is_kept_even_though_it_has_no_truth_value(self):
        """'I refuse to average live contentions' is not a claim about the world."""
        graph = _built()
        assert [c.text for c in graph.commitments] == ["I refuse to average live contentions into false consensus."]
        assert any(e.kind == EDGE_HOLDS for e in graph.edges)

    def test_its_own_agenda_is_kept_separately_from_corpus_gaps(self):
        graph = _built()
        assert len(graph.pursuits) == 1
        assert any(e.kind == EDGE_PURSUING for e in graph.edges)

    def test_the_name_it_chose_is_carried_as_its_own(self):
        assert _built().chosen_name == "Hard Skip"

    def test_the_render_leads_with_the_name_it_picked(self):
        assert render_perspective(_built()).startswith("# Hard Skip")


class TestVivaRevisionsLandOnTheChain:
    def test_positions_a_viva_moved_become_shifts(self):
        """Currently loose sentences in a list nothing points at."""
        viva = SimpleNamespace(positions_that_moved=["I withdraw the confidence on item 9."])
        graph = _built(viva=viva)

        assert any("item 9" in s.text for s in graph.shifts)
        assert graph.has_a_history

    def test_each_one_records_that_examination_caused_it(self):
        viva = SimpleNamespace(positions_that_moved=["moved"])
        graph = _built(viva=viva)
        assert any(n.text == "examined under viva" for n in graph.nodes)


class TestWalkingBackwards:
    def test_history_of_a_standpoint_returns_what_produced_it(self):
        """Assembled by traversal, because the model cannot recall readings
        that were never in its context."""
        graph = _built(
            profile=_profile(shifts=[_shift("I read it as naming.", "I read it as retraction.", fingerprint="abc")])
        )
        arrived = next(n for n in graph.standpoints if n.text == "I read it as retraction.")

        chain = graph.history_of(arrived.id)

        kinds = [n.kind for n in chain]
        assert NODE_STANDPOINT in kinds
        assert NODE_SHIFT in kinds
        assert any("abc" in n.text for n in chain)

    def test_a_cycle_cannot_hang_the_walk(self):
        graph = _built(profile=_profile(shifts=[_shift("a", "b")]))
        graph.edges.append(type(graph.edges[0])(graph.nodes[1].id, graph.nodes[0].id, EDGE_BECAME))
        assert graph.history_of(graph.nodes[0].id)


class TestSerialization:
    def test_the_graph_round_trips(self):
        original = _built(profile=_profile(shifts=[_shift("was", "now")]))
        restored = PerspectiveGraph.from_dict(original.to_dict())
        assert restored.stats() == original.stats()
        assert restored.chosen_name == "Hard Skip"

    def test_junk_is_dropped_rather_than_raising(self):
        restored = PerspectiveGraph.from_dict({"nodes": ["x", {"kind": "shift"}], "edges": ["y", {"from": "a"}]})
        assert restored.nodes == []
        assert restored.edges == []

    def test_an_expert_with_no_profile_yields_an_empty_biography(self):
        graph = build_perspective_graph(expert_name="E", profile=None)
        assert not graph.has_a_history
        assert graph.stats()["standpoints"] == 0
