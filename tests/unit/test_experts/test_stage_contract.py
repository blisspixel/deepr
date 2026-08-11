"""Preconditions declared once, instead of patched in after each one bites.

The distinction the whole module turns on: presence is not validity. Every
guard in the loop asked "does the file exist and parse". A brief holding zero
positions passes both, and profiling against it produced a standpoint about the
pipeline failing rather than about the subject.
"""

from deepr.experts.stage_contract import (
    STAGE_BRIEF,
    STAGE_GRAPH,
    STAGE_PROFILE,
    STAGE_STUDY,
    STAGES,
    evaluate_all,
    evaluate_stage,
    get_stage,
    next_stage,
)


def _artifacts(**overrides):
    """A fully healthy expert, unless a key is overridden with None or junk."""
    defaults = {
        "corpus/index.jsonl": {"active_count": 12},
        "noticed/current.json": {"totals": {"findings": 40, "grounded_findings": 31}},
        "hold/current.json": {"positions": [{"question": "Q"}]},
        "self.json": {"standpoint": "I read this as a systems problem."},
        "graph/evidence.json": {"stats": {"is_formed": True}},
        "attend/practice.json": {"stats": {"live_pursuits": 3}},
        "met/examination.json": {"exchanges": [{"question": "Q"}]},
    }
    return {**defaults, **overrides}


class TestPresenceIsNotValidity:
    def test_a_brief_holding_no_positions_blocks_the_profile(self):
        """The exact failure: a timed-out synthesis wrote a parseable, useless brief."""
        state = evaluate_stage(get_stage(STAGE_PROFILE), _artifacts(**{"hold/current.json": {"positions": []}}))

        assert state.status == "blocked"
        assert "holds no positions" in state.blockers[0].reason
        assert state.blockers[0].fix == "expert brief"

    def test_a_study_with_findings_that_anchor_in_nothing_blocks_the_brief(self):
        """Briefing from it produces positions resting on text nobody can open."""
        state = evaluate_stage(
            get_stage(STAGE_BRIEF),
            _artifacts(**{"noticed/current.json": {"totals": {"findings": 40, "grounded_findings": 0}}}),
        )
        assert state.status == "blocked"

    def test_an_unreadable_input_blocks_exactly_like_a_missing_one(self):
        """Treating a corrupt file as present is how the corruption travels."""
        missing = evaluate_stage(get_stage(STAGE_BRIEF), _artifacts(**{"noticed/current.json": None}))
        assert missing.status == "blocked"

    def test_an_empty_corpus_blocks_the_study(self):
        state = evaluate_stage(get_stage(STAGE_STUDY), _artifacts(**{"corpus/index.jsonl": {"active_count": 0}}))
        assert "nothing to read" in state.blockers[0].reason


class TestProducingAFileIsNotSucceeding:
    def test_an_artifact_that_carries_nothing_reads_as_failed_not_done(self):
        """Without this, an empty output is indistinguishable from a good one."""
        state = evaluate_stage(get_stage(STAGE_BRIEF), _artifacts(**{"hold/current.json": {"positions": []}}))
        assert state.produced
        assert state.status == "failed"

    def test_a_real_artifact_reads_as_done(self):
        assert evaluate_stage(get_stage(STAGE_BRIEF), _artifacts()).status == "done"

    def test_an_absent_artifact_with_inputs_met_reads_as_ready(self):
        state = evaluate_stage(get_stage(STAGE_BRIEF), _artifacts(**{"hold/current.json": None}))
        assert state.status == "ready"

    def test_a_graph_that_is_a_pile_of_nodes_reads_as_failed(self):
        state = evaluate_stage(
            get_stage(STAGE_GRAPH), _artifacts(**{"graph/evidence.json": {"stats": {"is_formed": False}}})
        )
        assert state.status == "failed"

    def test_every_stage_states_what_success_means(self):
        """A status nobody can interpret is not a status."""
        for stage in STAGES:
            assert stage.success_means, stage.name


class TestWhatToDoNext:
    def test_a_failed_stage_outranks_a_ready_one(self):
        """Building on top of a stage that produced nothing usable is how a
        timed-out brief became a standpoint about the pipeline failing."""
        states = evaluate_all(_artifacts(**{"hold/current.json": {"positions": []}, "attend/practice.json": None}))
        assert next_stage(states).name == STAGE_BRIEF

    def test_otherwise_the_first_runnable_stage_wins(self):
        states = evaluate_all(_artifacts(**{"attend/practice.json": None, "met/examination.json": None}))
        assert next_stage(states).name == "practice"

    def test_a_complete_expert_has_nothing_next(self):
        assert next_stage(evaluate_all(_artifacts())) is None

    def test_a_blocked_stage_is_never_offered_as_next(self):
        states = evaluate_all({"corpus/index.jsonl": None})
        assert next_stage(states).name == "acquire"


class TestTheWholeLoop:
    def test_an_empty_expert_blocks_everything_downstream_of_acquire(self):
        states = {s.name: s for s in evaluate_all({})}
        assert states["acquire"].status == "ready"
        assert states["study"].status == "blocked"
        assert states["brief"].status == "blocked"
        assert states["profile"].status == "blocked"

    def test_the_graph_needs_both_a_study_and_a_brief(self):
        """It joins claims to passages, so half the chain is not enough."""
        state = evaluate_stage(get_stage(STAGE_GRAPH), _artifacts(**{"hold/current.json": {"positions": []}}))
        assert state.status == "blocked"

    def test_every_blocker_names_a_command_that_would_fix_it(self):
        for state in evaluate_all({}):
            for blocker in state.blockers:
                assert blocker.fix.startswith("expert "), blocker

    def test_states_serialize_for_the_json_surface(self):
        payload = evaluate_all(_artifacts(**{"hold/current.json": {"positions": []}}))[2].to_dict()
        assert payload["status"] == "failed"
        assert payload["success_means"]
