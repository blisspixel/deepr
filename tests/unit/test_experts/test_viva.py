"""Examination where nobody holds the answer key.

The property under test throughout: an unanswered question is an output, not a
failure. What matters is telling apart the two reasons an expert cannot answer
- material exists and it has not read it, versus nobody knows - because the
first is a reading list and the second is the edge of the field.
"""

import pytest

from deepr.experts.viva import (
    VERDICT_ANSWERED,
    VERDICT_CANNOT,
    VERDICT_OPEN,
    VERDICT_PARTIAL,
    VivaExchange,
    VivaResult,
    attach_answers,
    attach_judgements,
    build_candidate_prompt,
    build_examiner_prompt,
    build_judge_prompt,
    parse_questions,
    render_viva,
)


def _exchange(**overrides) -> VivaExchange:
    defaults = dict(
        question="Why this and not the alternative?",
        asked_by="provenance",
        probes="whether the choice was reasoned or inherited",
        answer="Because the alternative loses the dependency chain.",
        verdict=VERDICT_ANSWERED,
    )
    return VivaExchange(**{**defaults, **overrides})


class TestTheTwoKindsOfUnanswered:
    """The distinction the whole module exists to draw."""

    def test_unread_material_becomes_a_reading_list_entry(self):
        gap = _exchange(verdict=VERDICT_CANNOT, would_resolve_it="The 2024 revision of the spec.")
        assert gap.is_gap
        assert not gap.is_frontier

    def test_an_open_question_is_not_a_deficiency(self):
        frontier = _exchange(verdict=VERDICT_OPEN)
        assert frontier.is_frontier
        assert not frontier.is_gap

    def test_cannot_answer_without_a_route_is_not_a_reading_list_entry(self):
        """'Go and find out' is not an instruction anyone can follow."""
        vague = _exchange(verdict=VERDICT_CANNOT, would_resolve_it="")
        assert not vague.is_gap

    def test_the_reading_queue_is_the_examiners_words_not_the_questions(self):
        result = VivaResult(
            expert_name="E",
            exchanges=[
                _exchange(verdict=VERDICT_CANNOT, would_resolve_it="The errata list."),
                _exchange(question="Q2", verdict=VERDICT_OPEN),
                _exchange(question="Q3"),
            ],
        )
        assert result.reading_queue() == ["The errata list."]
        assert len(result.frontier) == 1
        assert len(result.handled) == 1


class TestParsing:
    def test_a_question_with_no_target_is_small_talk_but_still_kept(self):
        """Recorded without a probe, so the omission is visible in the render."""
        exchanges = parse_questions({"questions": [{"question": "Thoughts?"}]}, asked_by="x")
        assert exchanges[0].probes == ""

    def test_questions_without_text_are_dropped(self):
        parsed = {"questions": [{"probes": "something"}, {"question": "Real?", "probes": "p"}]}
        assert [e.question for e in parse_questions(parsed, asked_by="x")] == ["Real?"]

    def test_a_flood_of_questions_is_bounded(self):
        parsed = {"questions": [{"question": f"Q{i}"} for i in range(50)]}
        assert len(parse_questions(parsed, asked_by="x")) == 8

    def test_junk_entries_do_not_take_the_examination_down(self):
        parsed = {"questions": ["not a dict", None, {"question": "Real?"}]}
        assert len(parse_questions(parsed, asked_by="x")) == 1

    def test_the_examiner_is_recorded_on_every_question(self):
        """A judgement nobody is attached to cannot be argued with."""
        exchanges = parse_questions({"questions": [{"question": "Q"}]}, asked_by="chinese-writing")
        assert exchanges[0].asked_by == "chinese-writing"


class TestAnswers:
    def test_answers_match_back_case_insensitively(self):
        exchanges = [_exchange(answer="")]
        attach_answers(exchanges, {"answers": [{"question": "WHY THIS AND NOT THE ALTERNATIVE?", "answer": "A"}]})
        assert exchanges[0].answer == "A"

    def test_an_answer_to_a_question_nobody_asked_is_ignored(self):
        exchanges = [_exchange(answer="")]
        attach_answers(exchanges, {"answers": [{"question": "invented", "answer": "A"}]})
        assert exchanges[0].answer == ""

    def test_a_changed_mind_is_collected(self):
        """The most valuable outcome available, and the one a score cannot show."""
        exchanges = [_exchange()]
        moved = attach_answers(
            exchanges,
            {
                "answers": [
                    {"question": exchanges[0].question, "answer": "A", "changed_my_mind": "I withdraw position 3."}
                ]
            },
        )
        assert moved == ["I withdraw position 3."]

    def test_nothing_moving_is_the_normal_case(self):
        exchanges = [_exchange()]
        assert attach_answers(exchanges, {"answers": [{"question": exchanges[0].question, "answer": "A"}]}) == []


class TestJudgements:
    def test_an_unrecognised_verdict_falls_back_to_partial_not_to_a_pass(self):
        """A malformed judgement must not be able to award a clean result."""
        exchanges = [_exchange(verdict=VERDICT_ANSWERED)]
        attach_judgements(exchanges, {"judgements": [{"question": exchanges[0].question, "verdict": "excellent"}]})
        assert exchanges[0].verdict == VERDICT_PARTIAL

    @pytest.mark.parametrize("verdict", [VERDICT_ANSWERED, VERDICT_PARTIAL, VERDICT_CANNOT, VERDICT_OPEN])
    def test_every_real_verdict_survives_the_round_trip(self, verdict):
        exchanges = [_exchange()]
        attach_judgements(exchanges, {"judgements": [{"question": exchanges[0].question, "verdict": verdict}]})
        assert exchanges[0].verdict == verdict

    def test_the_note_is_kept_so_the_verdict_can_be_argued_with(self):
        exchanges = [_exchange()]
        attach_judgements(
            exchanges,
            {
                "judgements": [
                    {"question": exchanges[0].question, "verdict": VERDICT_PARTIAL, "note": "Dodged the sharp half."}
                ]
            },
        )
        assert exchanges[0].examiner_note == "Dodged the sharp half."


class TestSummaryIsNotAScore:
    def test_no_letter_and_no_number_out_of_anything(self):
        result = VivaResult(expert_name="E", examiners=["a"], exchanges=[_exchange()])
        assert "/" not in result.summary()

    def test_an_examination_with_no_questions_says_so_rather_than_passing(self):
        assert "No questions" in VivaResult(expert_name="E").summary()

    def test_moved_positions_are_surfaced_in_the_summary(self):
        result = VivaResult(
            expert_name="E", examiners=["a"], exchanges=[_exchange()], positions_that_moved=["dropped position 2"]
        )
        assert "1 position(s) moved" in result.summary()


class TestRender:
    def test_gaps_render_as_work_and_frontier_renders_as_context(self):
        result = VivaResult(
            expert_name="Provenance",
            examiners=["chinese-writing"],
            exchanges=[
                _exchange(verdict=VERDICT_CANNOT, would_resolve_it="The errata list."),
                _exchange(question="Q2", verdict=VERDICT_OPEN),
            ],
        )
        text = render_viva(result)
        assert "## What to go and read" in text
        assert "The errata list." in text
        assert "Not deficiencies" in text

    def test_a_clean_examination_renders_neither_section(self):
        text = render_viva(VivaResult(expert_name="E", examiners=["a"], exchanges=[_exchange()]))
        assert "## What to go and read" not in text
        assert "has not settled" not in text

    def test_the_examiner_is_named_next_to_the_question(self):
        text = render_viva(
            VivaResult(expert_name="E", examiners=["furniture"], exchanges=[_exchange(asked_by="furniture")])
        )
        assert "asked by furniture" in text

    def test_moved_positions_lead_the_document(self):
        """What changed is the finding; the transcript is the supporting detail."""
        result = VivaResult(expert_name="E", exchanges=[_exchange()], positions_that_moved=["withdrew position 3"])
        text = render_viva(result)
        assert text.index("withdrew position 3") < text.index(result.exchanges[0].question)


class TestPrompts:
    def test_the_examiner_is_told_it_is_not_the_subject_expert(self):
        prompt = build_examiner_prompt(subject="hieroglyphs", examiner_frame="evaluation design", brief="B")
        assert "you are not expected to be" in prompt
        assert "evaluation design" in prompt

    def test_the_candidate_is_told_that_not_knowing_is_a_real_answer(self):
        prompt = build_candidate_prompt(subject="s", brief="B", questions=["Q1", "Q2"])
        assert "not a failure" in prompt
        assert "1. Q1" in prompt

    def test_the_candidate_is_invited_to_change_its_mind(self):
        assert "changed_my_mind" in build_candidate_prompt(subject="s", brief="B", questions=["Q"])

    def test_examiners_are_required_to_ask_about_the_subject_not_only_the_brief(self):
        """Measured: without this, a live run returned 12 answered and 0 gaps.

        Reasoning questions can always be answered by introspection - "no, I
        did not run that check" is honest and is not a knowledge gap. Only a
        question about substance the corpus may not cover can find something
        the expert has not read, so the reading queue stays empty without one.
        """
        prompt = build_examiner_prompt(subject="s", examiner_frame="f", brief="B")
        assert "Coverage questions" in prompt
        assert "third of your questions must be coverage questions" in prompt

    def test_the_judge_decides_on_substance_not_on_candour(self):
        """Measured: a model gap answer was graded 'answered' for being candid.

        Asked whether aviation human-factors work on alarm fatigue had been
        consulted, the expert said no and explained what it used instead. The
        judge rewarded the honesty and threw away the reading-list entry.
        """
        prompt = build_judge_prompt(subject="s", exchanges=[_exchange()])
        assert "does it contain" in prompt
        assert "explain the absence" in prompt
        assert "alarm-fatigue" in prompt
        assert "judging failure" in prompt

    def test_a_gap_must_name_material_outside_the_expert(self):
        """Measured: over-correcting produced 'the expert explaining its own...'

        No amount of reading fills a missing account of the expert's own
        reasoning - it already holds everything needed and did not say. Those
        belong in a re-brief, not in an acquisition queue.
        """
        prompt = build_judge_prompt(subject="s", exchanges=[_exchange()])
        assert "outside the expert" in prompt
        assert "the expert explaining" in prompt

    def test_house_style_reaches_every_prompt(self):
        """No em dashes, per the house rule, stated where the model will see it."""
        for prompt in (
            build_examiner_prompt(subject="s", examiner_frame="f", brief="B"),
            build_candidate_prompt(subject="s", brief="B", questions=["Q"]),
        ):
            assert "never an en dash or em dash" in prompt


class TestSerialization:
    def test_the_dict_carries_the_reading_queue_not_just_the_transcript(self):
        result = VivaResult(
            expert_name="E",
            exchanges=[_exchange(verdict=VERDICT_CANNOT, would_resolve_it="The errata list.")],
        )
        data = result.to_dict()
        assert data["reading_queue"] == ["The errata list."]
        assert data["exchanges"][0]["is_gap"] is True
