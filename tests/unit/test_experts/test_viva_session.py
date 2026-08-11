"""Running an examination against a scripted panel.

The behaviours that matter here are failure behaviours. A viva makes several
model calls and any of them can come back as prose, as nothing, or as an
exception; the examination has to degrade rather than collapse, because a panel
of three where one times out is still a panel of two.
"""

import asyncio

from deepr.experts.viva import VERDICT_ANSWERED, VERDICT_PARTIAL
from deepr.experts.viva_session import DEFAULT_PANEL, Examiner, run_viva

_PANEL = [Examiner(name="method", frame="evidence", questions=1)]


class _Script:
    """Replies in order, recording what it was asked."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else ""


def _run(script: _Script, examiners=None):
    return asyncio.run(
        run_viva(
            expert_name="E",
            subject="s",
            brief="B",
            examiners=examiners or _PANEL,
            completion=script,
        )
    )


class TestTheHappyPath:
    def test_a_full_examination_produces_a_transcript_and_a_reading_list(self):
        result = _run(
            _Script(
                '{"questions": [{"question": "Why this?", "probes": "reasoning"}]}',
                '{"answers": [{"question": "Why this?", "answer": "Because X."}]}',
                '{"judgements": [{"question": "Why this?", "verdict": "cannot_answer",'
                ' "note": "not held", "would_resolve_it": "The 2024 errata."}]}',
            )
        )
        assert result.exchanges[0].answer == "Because X."
        assert result.reading_queue() == ["The 2024 errata."]

    def test_a_changed_mind_is_carried_into_the_result(self):
        result = _run(
            _Script(
                '{"questions": [{"question": "Q"}]}',
                '{"answers": [{"question": "Q", "answer": "A", "changed_my_mind": "I withdraw 3."}]}',
                '{"judgements": [{"question": "Q", "verdict": "answered"}]}',
            )
        )
        assert result.positions_that_moved == ["I withdraw 3."]

    def test_the_candidate_sees_every_question_at_once(self):
        """Answering question six differently because two covered it is real."""
        script = _Script(
            '{"questions": [{"question": "Q1"}, {"question": "Q2"}]}',
            '{"answers": []}',
            "{}",
        )
        _run(script)
        assert "1. Q1" in script.prompts[1] and "2. Q2" in script.prompts[1]


class TestExaminersJudgeOnlyTheirOwn:
    def test_a_judgement_cannot_reach_another_examiners_question(self):
        """Only the asker knows what was being probed."""
        panel = [Examiner(name="a", frame="f", questions=1), Examiner(name="b", frame="f", questions=1)]
        result = asyncio.run(
            run_viva(
                expert_name="E",
                subject="s",
                brief="B",
                examiners=panel,
                completion=_Script(
                    '{"questions": [{"question": "QA"}]}',
                    '{"questions": [{"question": "QB"}]}',
                    '{"answers": []}',
                    # Examiner a tries to judge both.
                    '{"judgements": [{"question": "QA", "verdict": "answered"},'
                    ' {"question": "QB", "verdict": "cannot_answer", "would_resolve_it": "x"}]}',
                    "{}",
                ),
            )
        )
        by_q = {e.question: e for e in result.exchanges}
        assert by_q["QA"].verdict == VERDICT_ANSWERED
        assert by_q["QB"].verdict == VERDICT_ANSWERED  # untouched default, not a's verdict

    def test_each_examiner_is_shown_only_its_own_transcript(self):
        panel = [Examiner(name="a", frame="f", questions=1), Examiner(name="b", frame="f", questions=1)]
        script = _Script(
            '{"questions": [{"question": "QA"}]}',
            '{"questions": [{"question": "QB"}]}',
            '{"answers": []}',
            "{}",
            "{}",
        )
        asyncio.run(run_viva(expert_name="E", subject="s", brief="B", examiners=panel, completion=script))
        assert "QA" in script.prompts[3] and "QB" not in script.prompts[3]


class TestDegradingRatherThanCollapsing:
    def test_one_examiner_failing_leaves_a_smaller_panel(self):
        panel = [Examiner(name="a", frame="dies", questions=1), Examiner(name="b", frame="lives", questions=1)]

        async def flaky(prompt: str) -> str:
            if "You come from dies" in prompt:
                raise TimeoutError("examiner a died")
            if "You come from lives" in prompt:
                return '{"questions": [{"question": "QB"}]}'
            return '{"answers": [{"question": "QB", "answer": "A"}]}'

        result = asyncio.run(run_viva(expert_name="E", subject="s", brief="B", examiners=panel, completion=flaky))
        assert [e.question for e in result.exchanges] == ["QB"]
        assert result.exchanges[0].asked_by == "b"

    def test_a_panel_that_all_failed_returns_an_examination_that_says_so(self):
        result = _run(_Script("not json at all"))
        assert result.exchanges == []
        assert "No questions" in result.summary()

    def test_prose_around_the_json_is_recovered(self):
        result = _run(
            _Script(
                'Here are my questions:\n{"questions": [{"question": "Q"}]}\nHope that helps.',
                '```json\n{"answers": [{"question": "Q", "answer": "A"}]}\n```',
                "{}",
            )
        )
        assert result.exchanges[0].answer == "A"

    def test_an_unjudged_question_does_not_silently_pass_as_a_gap(self):
        """A judge that returned nothing leaves the default, which is not is_gap."""
        result = _run(_Script('{"questions": [{"question": "Q"}]}', '{"answers": []}', ""))
        assert not result.exchanges[0].is_gap
        assert result.reading_queue() == []

    def test_a_judge_returning_junk_leaves_partial_rather_than_answered(self):
        result = _run(
            _Script(
                '{"questions": [{"question": "Q"}]}',
                '{"answers": [{"question": "Q", "answer": "A"}]}',
                '{"judgements": [{"question": "Q", "verdict": "brilliant"}]}',
            )
        )
        assert result.exchanges[0].verdict == VERDICT_PARTIAL


class TestTheDefaultPanel:
    def test_three_standpoints_not_three_specialists(self):
        assert len(DEFAULT_PANEL) == 3
        assert len({e.frame for e in DEFAULT_PANEL}) == 3

    def test_the_opposing_case_has_a_seat(self):
        """Without one, the panel can agree the candidate is fine by not asking."""
        assert any("opposing" in e.frame for e in DEFAULT_PANEL)

    def test_each_frame_reaches_the_prompt_that_examiner_sees(self):
        script = _Script()
        asyncio.run(run_viva(expert_name="E", subject="s", brief="B", examiners=list(DEFAULT_PANEL), completion=script))
        for examiner in DEFAULT_PANEL:
            assert any(examiner.frame in p for p in script.prompts)


class TestCapacity:
    def test_the_call_count_is_bounded_by_the_panel(self):
        """Two per examiner plus one candidate pass. A viva must not be open-ended."""
        script = _Script()
        asyncio.run(run_viva(expert_name="E", subject="s", brief="B", examiners=list(DEFAULT_PANEL), completion=script))
        # All examiners returned nothing, so it stops after the question round.
        assert len(script.prompts) == 3

    def test_a_full_run_costs_two_per_examiner_plus_one(self):
        script = _Script(
            '{"questions": [{"question": "Q1"}]}',
            '{"questions": [{"question": "Q2"}]}',
            '{"answers": []}',
            "{}",
            "{}",
        )
        panel = [Examiner(name="a", frame="f1"), Examiner(name="b", frame="f2")]
        asyncio.run(run_viva(expert_name="E", subject="s", brief="B", examiners=panel, completion=script))
        assert len(script.prompts) == 5
