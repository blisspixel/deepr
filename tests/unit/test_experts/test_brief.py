"""The brief: lands somewhere, cites why, keeps what it could not resolve."""

import json

import pytest

from deepr.experts.brief import assemble_brief, build_brief, build_brief_prompt, render_brief
from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _finding(title, lens="failure", *, grounded=True, payload=None):
    return StudyFinding(
        lens=lens,
        axis="interrogation",
        kind="fail_patterns",
        title=title,
        payload=payload or {"trigger": "t", "correction": "c"},
        grounded_anchor_count=1 if grounded else 0,
        ungrounded_anchor_count=0 if grounded else 1,
        corpus_shas=["abc123"] if grounded else [],
    )


def _result(findings):
    r = StudyResult(expert_name="E")
    r.outcomes = [LensOutcome(lens="failure", axis="interrogation", status="ok", findings=findings)]
    return r


@pytest.fixture
def corpus(tmp_path):
    store = CorpusStore("Brief Test Expert", storage_dir=tmp_path / "corpus")
    store.add("first source body", origin_key="url:a.org", publisher="a.org")
    store.add("second source body", origin_key="url:a.org", publisher="a.org")
    store.add("third source body", origin_key="url:b.org", publisher="b.org")
    return store


_GOOD = {
    "orientation": "The field in sixty seconds.",
    "positions": [
        {
            "question": "Does X hold?",
            "stance": "Mostly, under stated conditions.",
            "reasoning": "Two independent origins report it.",
            "would_change_my_mind": "A controlled result showing the reverse.",
            "supported_by": ["Silent restore failure"],
            "unresolved_dissent": "One source disputes the magnitude.",
            "confidence_basis": "two origins, consistent",
        }
    ],
    "state": {"settled": ["A is real"], "live": ["magnitude"], "unknown": ["mechanism"]},
    "key_quantities": ["about 30%"],
    "anticipated_questions": [
        {
            "question": "Isn't this just Y?",
            "answer": "No, because Z.",
            "why_asked": "surface similarity",
            "supported_by": ["Silent restore failure"],
        }
    ],
    "common_failures": ["Everyone tries the naive fix first."],
}


class TestPromptContract:
    def test_prompt_demands_falsifiers_and_citations(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "would_change_my_mind" in prompt
        assert "supported_by" in prompt
        assert "assertion" in prompt

    def test_prompt_forbids_averaging_dissent(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "Do not average disagreement" in prompt

    def test_prompt_refuses_manufactured_disagreement_when_none_found(self):
        """Without contention findings, inventing dissent is the failure mode."""
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "Do not manufacture disagreement" in prompt

    def test_prompt_flags_contention_findings_when_present(self):
        findings = [_finding("F1"), _finding("Sources disagree on rate", lens="contention")]
        prompt = build_brief_prompt(_result(findings), expert_name="E")
        assert "contention lens" in prompt

    def test_unverified_findings_are_marked_in_the_prompt(self):
        prompt = build_brief_prompt(_result([_finding("F1", grounded=False)]), expert_name="E")
        assert "UNVERIFIED" in prompt


class TestAssemble:
    def test_positions_keep_only_real_citations(self, corpus):
        """A citation naming no real finding cannot answer 'why do you think that'."""
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["supported_by"] = ["Silent restore failure", "Invented finding"]
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].supported_by == ["Silent restore failure"]

    def test_unresolved_dissent_is_carried_forward(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].unresolved_dissent

    def test_positions_without_a_stance_are_dropped(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"].append({"question": "q", "stance": "", "would_change_my_mind": "x"})
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert len(brief.positions) == 1

    def test_ungrounded_findings_become_a_limitation(self, corpus):
        result = _result([_finding("Silent restore failure"), _finding("F2", grounded=False)])
        brief = assemble_brief(_GOOD, expert_name="E", result=result, corpus=corpus)
        assert any("not verifiable" in limit for limit in brief.limitations)


class TestCredibility:
    def test_multiple_sources_from_one_origin_are_flagged(self, corpus):
        brief = assemble_brief(_GOOD, expert_name="E", result=_result([_finding("F1")]), corpus=corpus)
        rows = {c.origin: c for c in brief.credibility}
        assert rows["url:a.org"].is_sole_root is True
        assert rows["url:a.org"].source_count == 2
        assert rows["url:b.org"].is_sole_root is False


class TestIntegrityWarnings:
    def test_position_without_falsifier_is_called_an_assertion(self):
        brief = ExpertBrief(expert_name="E")
        brief.positions = [Position(question="q", stance="s", reasoning="r", would_change_my_mind="")]
        assert any("assertion" in w for w in brief.integrity_warnings())

    def test_position_without_citations_is_flagged(self):
        brief = ExpertBrief(expert_name="E")
        brief.positions = [Position(question="q", stance="s", reasoning="r", would_change_my_mind="x")]
        assert any("why do you think that" in w for w in brief.integrity_warnings())

    def test_absence_of_any_dissent_is_itself_flagged(self):
        """A brief that reads confident may have averaged disagreement away."""
        brief = ExpertBrief(expert_name="E")
        brief.positions = [
            Position(question="q", stance="s", reasoning="r", would_change_my_mind="x", supported_by=["F1"])
        ]
        assert any("averaged away" in w for w in brief.integrity_warnings())

    def test_a_sound_brief_raises_no_warnings(self):
        brief = ExpertBrief(expert_name="E")
        brief.positions = [
            Position(
                question="q",
                stance="s",
                reasoning="r",
                would_change_my_mind="x",
                supported_by=["F1"],
                unresolved_dissent="one source disputes it",
            )
        ]
        assert brief.integrity_warnings() == []


class TestBuildBrief:
    @pytest.mark.asyncio
    async def test_no_findings_refuses_rather_than_inventing(self, corpus):
        calls = []

        async def _completion(prompt):
            calls.append(prompt)
            return "{}"

        brief = await build_brief(
            expert_name="E", result=StudyResult(expert_name="E"), corpus=corpus, completion=_completion
        )
        assert calls == []
        assert any("would be invention" in limit for limit in brief.limitations)

    @pytest.mark.asyncio
    async def test_synthesis_failure_does_not_lose_the_study(self, corpus):
        async def _completion(_prompt):
            raise RuntimeError("backend down")

        brief = await build_brief(
            expert_name="E", result=_result([_finding("F1")]), corpus=corpus, completion=_completion
        )
        assert brief.generated_from_findings == 1
        assert any("Synthesis call failed" in limit for limit in brief.limitations)

    @pytest.mark.asyncio
    async def test_unparseable_synthesis_reports_what_came_back(self, corpus):
        async def _completion(_prompt):
            return "I think the main themes are..."

        brief = await build_brief(
            expert_name="E", result=_result([_finding("F1")]), corpus=corpus, completion=_completion
        )
        assert any("did not return usable JSON" in limit for limit in brief.limitations)
        assert any("main themes" in limit for limit in brief.limitations)

    @pytest.mark.asyncio
    async def test_happy_path_produces_a_grounded_brief(self, corpus):
        async def _completion(_prompt):
            return json.dumps(_GOOD)

        brief = await build_brief(
            expert_name="E",
            result=_result([_finding("Silent restore failure")]),
            corpus=corpus,
            completion=_completion,
        )
        assert brief.orientation
        assert brief.positions[0].is_falsifiable
        assert brief.positions[0].is_grounded
        assert brief.anticipated_questions


class TestRender:
    def test_bottom_line_comes_first(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        text = render_brief(brief)
        assert text.index("In sixty seconds") < text.index("Where I land")
        assert text.index("Where I land") < text.index("Questions I expect")

    def test_missing_falsifier_is_visible_in_the_render(self):
        brief = ExpertBrief(expert_name="E")
        brief.positions = [Position(question="q", stance="s", reasoning="r", would_change_my_mind="")]
        assert "No falsifier stated" in render_brief(brief)

    def test_unresolved_dissent_is_rendered_prominently(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert "Does not resolve" in render_brief(brief)

    def test_settled_section_tells_the_reader_to_skip(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert "skip these" in render_brief(brief)

    def test_render_is_deterministic(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert render_brief(brief) == render_brief(brief)
