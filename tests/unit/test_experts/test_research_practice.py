"""What an expert does to stay expert, rather than what it knows.

The split under test throughout: which sources it follows is measured and not
the model's call, while what it chases and where its attention goes is entirely
the model's. Letting a model rank sources would reintroduce exactly the
guessing that measuring them replaced.
"""

from deepr.experts.research_practice import (
    DEPTH_DEEPENING,
    DEPTH_MAINTAINING,
    PURSUIT_ABANDONED,
    PURSUIT_ANSWERED,
    Interest,
    Pursuit,
    ResearchPractice,
    Watch,
    apply_practice_update,
    build_practice_prompt,
    open_pursuits,
    render_practice,
    resolve_pursuit,
    set_interests,
    update_watches,
)

AT = "2026-08-09T00:00:00+00:00"


def _practice(**overrides) -> ResearchPractice:
    practice = ResearchPractice(expert_name="E")
    for key, value in overrides.items():
        setattr(practice, key, value)
    return practice


class TestPursuitsAreChoicesNotGaps:
    def test_a_pursuit_records_why_it_matters(self):
        """A gap is missing material. A pursuit is something it chose to care about."""
        practice = _practice()
        open_pursuits(practice, ["Does X scale?"], origin="viva", at=AT, why="it decides position 3")

        assert practice.pursuits[0].why_it_matters == "it decides position 3"
        assert practice.pursuits[0].origin == "viva"

    def test_the_same_question_does_not_open_twice(self):
        practice = _practice()
        open_pursuits(practice, ["Does X scale?"], origin="viva", at=AT)
        added = open_pursuits(practice, ["does x scale"], origin="profile", at=AT)

        assert added == 0
        assert len(practice.pursuits) == 1

    def test_an_abandoned_question_does_not_silently_reopen(self):
        """Reopening a line of enquiry should be a decision. Reappearing is not one."""
        practice = _practice(pursuits=[Pursuit(question="Does X scale?", status=PURSUIT_ABANDONED)])

        assert open_pursuits(practice, ["Does X scale?"], origin="viva", at=AT) == 0

    def test_answering_one_records_what_answered_it(self):
        practice = _practice()
        open_pursuits(practice, ["Does X scale?"], origin="viva", at=AT)

        assert resolve_pursuit(practice, "does X scale", resolution="the 2026 benchmark settles it", at=AT)
        assert practice.pursuits[0].status == PURSUIT_ANSWERED
        assert practice.pursuits[0].resolution == "the 2026 benchmark settles it"

    def test_resolving_something_it_is_not_chasing_reports_no_match(self):
        assert not resolve_pursuit(_practice(), "unheard of", resolution="x", at=AT)


class TestAttentionIsEarnedNotChosen:
    def test_a_source_carrying_positions_becomes_a_watch(self):
        practice = _practice()
        update_watches(practice, [("anthropic.com", 6)], at=AT)

        assert practice.watches[0].origin == "anthropic.com"
        assert practice.watches[0].positions_resting_on_it == 6

    def test_watches_are_ordered_by_how_much_rests_on_them(self):
        practice = _practice()
        update_watches(practice, [("minor.org", 1), ("major.org", 9)], at=AT)

        assert [w.origin for w in practice.watches] == ["major.org", "minor.org"]

    def test_a_quiet_round_does_not_drop_a_source(self):
        """A publisher with a quiet quarter has not stopped mattering."""
        practice = _practice()
        update_watches(practice, [("a.org", 3)], at=AT)
        update_watches(practice, [], at=AT)

        assert [w.origin for w in practice.watches] == ["a.org"]
        assert practice.watches[0].quiet_rounds == 1

    def test_three_quiet_rounds_drops_it(self):
        """How a field moving on becomes visible instead of carried forever."""
        practice = _practice()
        update_watches(practice, [("a.org", 3)], at=AT)
        for _ in range(3):
            update_watches(practice, [], at=AT)

        assert practice.watches == []

    def test_carrying_something_again_resets_the_counter(self):
        practice = _practice()
        update_watches(practice, [("a.org", 3)], at=AT)
        update_watches(practice, [], at=AT)
        update_watches(practice, [("a.org", 1)], at=AT)

        assert practice.watches[0].quiet_rounds == 0

    def test_the_reading_list_is_bounded(self):
        practice = _practice()
        update_watches(practice, [(f"pub{i}.org", i) for i in range(30)], at=AT)

        assert len(practice.watches) == 12


class TestTheDeepeningBudget:
    def test_excess_deepening_areas_are_demoted_not_dropped(self):
        """It still cares; it just cannot go deep on eight things at once."""
        practice = _practice()
        set_interests(practice, [Interest(area=f"area {i}", depth=DEPTH_DEEPENING) for i in range(6)])

        assert len(practice.deepening) == 3
        assert len(practice.interests) == 6
        assert all(i.depth == DEPTH_MAINTAINING for i in practice.interests[3:])

    def test_a_demoted_area_says_why(self):
        practice = _practice()
        set_interests(practice, [Interest(area=f"a{i}", depth=DEPTH_DEEPENING) for i in range(4)])

        assert "deepening budget is full" in practice.interests[3].why


class TestWhetherItIsPractisingAtAll:
    def test_a_live_question_and_somewhere_to_look_is_a_practice(self):
        practice = _practice(pursuits=[Pursuit(question="Q")], watches=[Watch(origin="a.org")])
        assert practice.is_practising

    def test_questions_with_nowhere_to_look_is_not(self):
        assert not _practice(pursuits=[Pursuit(question="Q")]).is_practising

    def test_sources_with_nothing_to_chase_is_not(self):
        """Waiting to be re-researched, which is what the whole fleet does."""
        assert not _practice(watches=[Watch(origin="a.org")]).is_practising

    def test_the_render_says_so_plainly(self):
        assert "waiting to be re-researched" in render_practice(_practice())


class TestNextReading:
    def test_questions_come_before_sources(self):
        """A question is a better search than a topic."""
        practice = _practice(pursuits=[Pursuit(question="Does X scale?")], watches=[Watch(origin="a.org")])

        assert practice.next_reading()[0] == "Does X scale?"

    def test_answered_questions_drop_off_the_list(self):
        practice = _practice(pursuits=[Pursuit(question="Q", status=PURSUIT_ANSWERED)])
        assert practice.next_reading() == []


class TestTheAgenticHalf:
    def test_the_prompt_tells_it_the_source_list_is_not_its_call(self):
        prompt = build_practice_prompt(expert_name="E", standpoint="S", practice=_practice(), material="M")
        assert "already settled" in prompt
        assert "cannot promote a source you" in prompt

    def test_the_prompt_carries_the_deepening_budget(self):
        prompt = build_practice_prompt(expert_name="E", standpoint="S", practice=_practice(), material="M")
        assert "At most 3 may be deepening" in prompt

    def test_abandoning_is_offered_as_a_real_finding(self):
        prompt = build_practice_prompt(expert_name="E", standpoint="S", practice=_practice(), material="M")
        assert "is not a failure" in prompt

    def test_an_update_answers_abandons_and_opens(self):
        practice = _practice()
        open_pursuits(practice, ["settled one", "wrong question"], origin="viva", at=AT)

        changed = apply_practice_update(
            practice,
            {
                "reviewed": [
                    {"question": "settled one", "verdict": "answered", "resolution": "the 2026 study"},
                    {"question": "wrong question", "verdict": "abandon", "resolution": "it was the wrong frame"},
                ],
                "new_pursuits": [{"question": "a fresh one", "why_it_matters": "it decides position 3"}],
                "interests": [{"area": "verification", "depth": "deepening"}],
            },
            at=AT,
        )

        assert changed == {"answered": 1, "abandoned": 1, "opened": 1}
        assert [p.question for p in practice.live_pursuits] == ["a fresh one"]
        assert practice.deepening[0].area == "verification"

    def test_a_question_answered_then_reasked_does_not_reopen(self):
        """Resolutions apply before new pursuits, so the rephrase deduplicates."""
        practice = _practice()
        open_pursuits(practice, ["Does X scale?"], origin="viva", at=AT)

        apply_practice_update(
            practice,
            {
                "reviewed": [{"question": "Does X scale?", "verdict": "answered", "resolution": "yes"}],
                "new_pursuits": [{"question": "does x scale"}],
            },
            at=AT,
        )

        assert len(practice.pursuits) == 1
        assert practice.pursuits[0].status == PURSUIT_ANSWERED

    def test_junk_in_the_reply_does_not_corrupt_the_practice(self):
        practice = _practice()
        changed = apply_practice_update(
            practice, {"reviewed": ["nope", {}], "new_pursuits": [None, {"question": "  "}]}, at=AT
        )
        assert changed == {"answered": 0, "abandoned": 0, "opened": 0}
        assert practice.pursuits == []

    def test_an_abandon_with_no_reason_still_records_that_it_was_abandoned(self):
        practice = _practice()
        open_pursuits(practice, ["Q"], origin="viva", at=AT)
        apply_practice_update(practice, {"reviewed": [{"question": "Q", "verdict": "abandon"}]}, at=AT)

        assert practice.pursuits[0].status == PURSUIT_ABANDONED
        assert "without a stated reason" in practice.pursuits[0].resolution


class TestSerialization:
    def test_the_practice_round_trips(self):
        practice = _practice(
            pursuits=[Pursuit(question="Q", origin="viva")],
            watches=[Watch(origin="a.org", positions_resting_on_it=4)],
            interests=[Interest(area="verification", depth=DEPTH_DEEPENING)],
        )
        restored = ResearchPractice.from_dict(practice.to_dict())

        assert restored.stats() == practice.stats()
        assert restored.watches[0].positions_resting_on_it == 4

    def test_junk_is_dropped_rather_than_raising(self):
        restored = ResearchPractice.from_dict(
            {"pursuits": ["x", {}], "watches": ["y", {}], "interests": ["z", {}]}
        )
        assert restored.pursuits == restored.watches == restored.interests == []
