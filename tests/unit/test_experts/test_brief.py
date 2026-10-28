"""The brief: lands somewhere, cites why, keeps what it could not resolve."""

import json
from datetime import date

import pytest
from httpx import ReadTimeout

from deepr.experts.brief import (
    assemble_brief,
    build_brief,
    build_brief_prompt,
    provenance_for,
    render_brief,
)
from deepr.experts.brief_contracts import (
    LIKELIHOOD_BANDS,
    AnticipatedQuestion,
    ExpertBrief,
    Position,
)
from deepr.experts.corpus_store import CorpusStore, content_hash
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult

# Real shas for the corpus fixture below. The fixture used to anchor findings to
# a made-up sha, so every provenance lookup missed and the evidential-depth
# branch was never taken by any test while all of them passed.
_SHA_A = content_hash("first source body")
_SHA_A2 = content_hash("second source body")
_SHA_B = content_hash("third source body")


def _finding(title, lens="failure", *, grounded=True, payload=None, fid="failure-1", shas=None):
    return StudyFinding(
        lens=lens,
        axis="interrogation",
        kind="fail_patterns",
        title=title,
        finding_id=fid,
        payload=payload or {"trigger": "t", "correction": "c"},
        grounded_anchor_count=1 if grounded else 0,
        ungrounded_anchor_count=0 if grounded else 1,
        corpus_shas=list(shas) if shas else ([_SHA_A] if grounded else []),
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


def _sound_position(**overrides):
    """A position with nothing structurally wrong with it."""
    defaults = {
        "question": "q",
        "stance": "s",
        "reasoning": "r",
        "would_change_my_mind": "A controlled trial showing the reverse.",
        "supported_by": ["F1"],
        "unresolved_dissent": "one source disputes it",
        "likelihood": "likely",
        "confidence": "moderate",
    }
    return Position(**{**defaults, **overrides})


_GOOD = {
    "orientation": "The field in sixty seconds.",
    "positions": [
        {
            "question": "Does X hold?",
            "stance": "Mostly, under stated conditions.",
            "reasoning": "Two independent origins report it.",
            "would_change_my_mind": "A controlled result showing the reverse.",
            "falsifier_resolution_criterion": "The controlled result reports the reverse direction.",
            "falsifier_resolution_date": "2099-01-15",
            "supported_by": ["failure-1"],
            "unresolved_dissent": "One source disputes the magnitude.",
            "confidence_basis": "two origins, consistent",
            "likelihood": "likely",
            "confidence": "moderate",
            "resolution": "single",
        }
    ],
    "state": {"settled": ["A is real"], "live": ["magnitude"], "unknown": ["mechanism"]},
    "key_quantities": ["about 30%"],
    "anticipated_questions": [
        {
            "question": "Isn't this just Y?",
            "answer": "No, because Z.",
            "why_asked": "surface similarity",
            "supported_by": ["failure-1"],
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
        assert "same subject, scope and conditions" in prompt
        assert "Do not invent earlier expert beliefs" in prompt
        assert '"orientation":' not in prompt

    def test_prompt_registers_predictions_prospectively(self):
        prompt = build_brief_prompt(
            _result([_finding("F1")]),
            expert_name="E",
            as_of_date=date(2026, 8, 30),
        )
        assert "falsifier_resolution_criterion" in prompt
        assert "falsifier_resolution_date" in prompt
        assert "2026-08-30" in prompt
        assert "explicit future event" in prompt
        assert "routine recheck is not a forecast" in prompt

    def test_prompt_forbids_averaging_dissent(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "Do not average disagreement" in prompt

    def test_prompt_refuses_manufactured_disagreement_when_none_found(self):
        """Without contention findings, inventing dissent is the failure mode."""
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "Do not manufacture disagreement" in prompt

    def test_prompt_flags_contention_findings_when_present(self):
        findings = [_finding("F1"), _finding("Sources disagree on rate", lens="contention", fid="contention-1")]
        prompt = build_brief_prompt(_result(findings), expert_name="E")
        assert "contention lens" in prompt

    def test_prompt_keeps_likelihood_and_confidence_apart(self):
        """Blending them is the documented failure; the prompt must name the split."""
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "must not be mixed" in prompt
        assert "coin flip" in prompt

    def test_prompt_offers_only_the_closed_likelihood_vocabulary(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        for term in LIKELIHOOD_BANDS:
            assert f'"{term}"' in prompt

    def test_prompt_allows_declining_to_resolve(self):
        """Without this the schema forces a stance, which guarantees invention."""
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "irreducible" in prompt
        assert "Prefer irreducible over" in prompt

    def test_prompt_requires_a_question_that_attacks(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "weakens_thesis" in prompt

    def test_prompt_rejects_formulaic_falsifiers_by_example(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "If new evidence emerges" in prompt

    def test_unverified_findings_are_marked_in_the_prompt(self):
        prompt = build_brief_prompt(_result([_finding("F1", grounded=False)]), expert_name="E")
        assert "UNVERIFIED" in prompt


class TestPositionCompatibility:
    def test_prediction_fields_do_not_change_legacy_positional_constructor_order(self):
        position = Position("Q", "S", "R", "F", ["finding-1"])

        assert position.supported_by == ["finding-1"]
        assert position.falsifier_resolution_criterion == ""
        assert position.falsifier_resolution_date == ""


class TestAssemble:
    def test_positions_keep_only_real_citations(self, corpus):
        """A citation naming no real finding cannot answer 'why do you think that'."""
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["supported_by"] = ["failure-1", "invented-99"]
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].supported_by == ["failure-1"]

    def test_unresolved_dissent_is_carried_forward(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].unresolved_dissent

    def test_registered_prediction_survives_assembly(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        position = brief.positions[0]
        assert position.is_registered_prediction
        assert position.falsifier_resolution_date == "2099-01-15"

    def test_invalid_prediction_date_is_not_registered(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["falsifier_resolution_date"] = "next quarter"

        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )

        assert brief.positions[0].falsifier_resolution_date == ""
        assert not brief.positions[0].is_registered_prediction

    def test_retroactive_prediction_date_is_not_registered(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["falsifier_resolution_date"] = "2026-08-29"

        brief = assemble_brief(
            payload,
            expert_name="E",
            result=_result([_finding("Silent restore failure")]),
            corpus=corpus,
            as_of_date=date(2026, 8, 30),
        )

        assert brief.positions[0].falsifier_resolution_date == ""
        assert not brief.positions[0].is_registered_prediction

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
        brief.positions = [_sound_position()]
        assert brief.integrity_warnings() == []

    def test_non_forecast_advice_does_not_require_a_likelihood(self):
        brief = ExpertBrief(expert_name="E")
        position = _sound_position()
        position.likelihood = ""
        brief.positions = [position]
        assert not any("likelihood" in w or "never a judgment" in w for w in brief.integrity_warnings())
        assert "never a judgment" not in render_brief(brief)

    @pytest.mark.parametrize("registration", ["falsifier_resolution_criterion", "falsifier_resolution_date"])
    def test_explicit_prediction_without_likelihood_records_scoring_limitation(self, registration):
        brief = ExpertBrief(expert_name="E")
        position = _sound_position()
        position.likelihood = ""
        setattr(position, registration, "2030-01-01" if registration.endswith("date") else "A measured reversal.")
        brief.positions = [position]
        restored = ExpertBrief.from_dict(brief.to_dict())
        assert getattr(restored.positions[0], registration) == getattr(position, registration)
        assert any("Probability scoring is unavailable" in w for w in restored.integrity_warnings())
        assert "never a judgment" not in render_brief(restored)

    def test_several_sources_from_one_origin_record_is_not_corroboration(self):
        brief = ExpertBrief(expert_name="E")
        position = _sound_position()
        position.supporting_documents, position.distinct_roots = 5, 1
        brief.positions = [position]
        assert position.is_single_origin
        assert any("single origin record" in w for w in brief.integrity_warnings())

    def test_irreducible_without_dissent_is_a_contradiction(self):
        brief = ExpertBrief(expert_name="E")
        position = _sound_position()
        position.resolution, position.unresolved_dissent = "irreducible", ""
        brief.positions = [position]
        assert any("irreducible" in w for w in brief.integrity_warnings())

    def test_question_set_that_never_attacks_is_flagged(self):
        brief = ExpertBrief(expert_name="E")
        brief.positions = [_sound_position()]
        brief.anticipated_questions = [AnticipatedQuestion(question="q", answer="a")]
        assert any("marketing" in w for w in brief.integrity_warnings())


class TestFalsifierQuality:
    """A falsifier nobody can check cannot overturn anything."""

    @pytest.mark.parametrize(
        "falsifier",
        [
            "If new evidence emerges.",
            "If further research changes the picture.",
            "Better understanding of the mechanism.",
        ],
    )
    def test_formulaic_falsifiers_are_flagged_as_decorative(self, falsifier):
        assert Position(question="q", stance="s", reasoning="r", would_change_my_mind=falsifier).falsifier_is_decorative

    @pytest.mark.parametrize(
        "falsifier",
        [
            "A controlled trial showing the reverse.",
            "New evidence that the rate is below 10%.",
            "A published retraction of the founding study.",
            "Audit logs showing the restore never ran.",
        ],
    )
    def test_falsifiers_naming_something_checkable_pass(self, falsifier):
        position = Position(question="q", stance="s", reasoning="r", would_change_my_mind=falsifier)
        assert not position.falsifier_is_decorative

    def test_a_missing_falsifier_is_not_reported_as_decorative(self):
        """Absence has its own, louder warning; reporting both doubles the noise."""
        assert not Position(question="q", stance="s", reasoning="r", would_change_my_mind="").falsifier_is_decorative


class TestCalibration:
    def test_likelihood_outside_the_vocabulary_is_dropped(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["likelihood"] = "pretty much a lock"
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].likelihood == ""

    def test_known_likelihood_carries_its_numbers(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].likelihood_band == (55, 80)

    def test_render_prints_the_band_beside_the_word(self, corpus):
        """A glossary elsewhere does not work; the number travels with the term."""
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert "likely (55-80%)" in render_brief(brief)

    def test_likelihood_and_confidence_render_on_separate_lines(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        rendered = render_brief(brief)
        likelihood_line = next(line for line in rendered.splitlines() if "Likelihood it holds" in line)
        assert "moderate" not in likelihood_line

    def test_unknown_resolution_falls_back_to_single(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["resolution"] = "mostly settled"
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.positions[0].resolution == "single"

    def test_irreducible_position_says_so_before_its_stance(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["resolution"] = "irreducible"
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        rendered = render_brief(brief)
        assert rendered.index("Not resolved") < rendered.index("Stance:")


class TestEvidentialDepth:
    def test_position_counts_publishers_not_citations(self, corpus):
        """Two findings from one publisher are one publisher's authority."""
        shas = [e.sha256 for e in corpus.active_entries() if e.origin_key == "url:a.org"]
        findings = [
            StudyFinding(
                lens="failure", axis="interrogation", kind="k", title="F1", finding_id="f-1", corpus_shas=shas[:1]
            ),
            StudyFinding(
                lens="failure", axis="interrogation", kind="k", title="F2", finding_id="f-2", corpus_shas=shas[1:2]
            ),
        ]
        documents, roots = provenance_for(["f-1", "f-2"], _result(findings), corpus)
        assert (documents, roots) == (2, 1)

    def test_single_origin_support_is_visible_in_the_render(self, corpus):
        shas = [e.sha256 for e in corpus.active_entries() if e.origin_key == "url:a.org"]
        findings = [
            StudyFinding(
                lens="failure",
                axis="interrogation",
                kind="k",
                title="Silent restore failure",
                finding_id="failure-1",
                grounded_anchor_count=1,
                corpus_shas=shas,
            )
        ]
        brief = assemble_brief(_GOOD, expert_name="E", result=_result(findings), corpus=corpus)
        assert "not corroboration" in render_brief(brief)


class TestBuildBrief:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("prediction_date", "registered"),
        [("2026-01-19", False), ("2026-01-20", True), ("2026-01-21", True)],
    )
    async def test_historical_cutoff_controls_prompt_and_prediction_registration(
        self, corpus, monkeypatch, prediction_date, registered
    ):
        monkeypatch.setattr("deepr.experts.brief._utc_today", lambda: date(2026, 9, 5))
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["falsifier_resolution_date"] = prediction_date
        prompts = []

        async def _completion(prompt):
            prompts.append(prompt)
            return json.dumps(payload)

        brief = await build_brief(
            expert_name="E",
            result=_result([_finding("F1")]),
            corpus=corpus,
            completion=_completion,
            as_of_date=date(2026, 1, 20),
        )

        assert len(prompts) == 1
        assert "2026-01-20; never use an earlier date" in prompts[0]
        assert "2026-09-05" not in prompts[0]
        position = brief.positions[0]
        assert position.falsifier_resolution_date == (prediction_date if registered else "")
        assert position.is_registered_prediction is registered

    @pytest.mark.asyncio
    async def test_default_date_stays_fixed_when_completion_crosses_midnight(self, corpus, monkeypatch):
        monkeypatch.setattr("deepr.experts.brief._utc_today", lambda: date(2026, 1, 20))
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["falsifier_resolution_date"] = "2026-01-20"
        prompts = []

        async def _completion(prompt):
            prompts.append(prompt)
            monkeypatch.setattr("deepr.experts.brief._utc_today", lambda: date(2026, 1, 21))
            return json.dumps(payload)

        brief = await build_brief(
            expert_name="E",
            result=_result([_finding("F1")]),
            corpus=corpus,
            completion=_completion,
        )

        assert len(prompts) == 1
        assert "2026-01-20; never use an earlier date" in prompts[0]
        assert brief.positions[0].falsifier_resolution_date == "2026-01-20"
        assert brief.positions[0].is_registered_prediction

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
    @pytest.mark.parametrize(
        "detail", ["", "PRIVATE_EXCEPTION_DETAIL: /private/task?token=secret"], ids=["empty-message", "private-message"]
    )
    async def test_synthesis_timeout_retains_type_without_private_detail_or_retry(self, corpus, detail):
        calls = []

        async def _completion(prompt):
            calls.append(prompt)
            raise ReadTimeout(detail)

        brief = await build_brief(
            expert_name="E", result=_result([_finding("F1")]), corpus=corpus, completion=_completion
        )

        assert len(calls) == 1
        assert brief.orientation == ""
        assert brief.positions == []
        assert brief.generated_from_findings == 1
        assert brief.synthesis_input["admission_status"] == "admitted"
        assert brief.limitations == ["Synthesis call failed (ReadTimeout); no brief was produced."]
        assert "PRIVATE_EXCEPTION_DETAIL" not in json.dumps(brief.to_dict())

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

    def test_registered_prediction_check_is_rendered(self, corpus):
        brief = assemble_brief(
            _GOOD, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        rendered = render_brief(brief)
        assert "Check on 2099-01-15" in rendered
        assert "reports the reverse direction" in rendered

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


class TestHouseStyle:
    """Plain punctuation, enforced rather than requested."""

    def test_the_prompt_states_the_style_rule(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "never an en dash or em dash" in prompt

    def test_dashes_and_smart_quotes_are_normalized_on_the_way_in(self, corpus):
        """A prompt is a request. This is the part that cannot be declined."""
        payload = json.loads(json.dumps(_GOOD))
        payload["orientation"] = "plant\u2013fungus “wood-wide web” \u2014 really…"
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert brief.orientation == 'plant-fungus "wood-wide web" - really...'

    def test_a_rendered_brief_carries_no_dashes_or_curly_quotes(self, corpus):
        payload = json.loads(json.dumps(_GOOD))
        payload["positions"][0]["stance"] = "Mostly \u2014 under “stated” conditions"
        brief = assemble_brief(
            payload, expert_name="E", result=_result([_finding("Silent restore failure")]), corpus=corpus
        )
        assert not (set(render_brief(brief)) & set("\u2013\u2014‘’“”…"))


class TestRepresentationRepairs:
    """Structure only: the right fields reach synthesis and the reader, labelled honestly."""

    def test_falsifier_and_qualifier_wording_is_scope_bound(self):
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "same mechanism the stance describes" in prompt
        assert "asserting or disclaiming a guarantee is not itself such an observation" in prompt
        assert "some tested configurations cannot by itself overturn a stance scoped to all of them" in prompt
        assert "a measurement, a document, a result" not in prompt
        assert "value used in a test is not a default unless the source calls it one" in prompt
        assert "A fetch time is when the source was retained" in prompt

    def test_documented_behavior_falsifier_and_inferred_guarantee_wording(self):
        # Instruction delivery only; whether briefs follow it is a frozen-review question.
        prompt = build_brief_prompt(_result([_finding("F1")]), expert_name="E")
        assert "For a stance about documented behavior, the overturning observation is that behavior" in prompt
        assert "can prompt a recheck; it is not the falsifier" in prompt
        assert "A guarantee class or general property that no finding states" in prompt
        assert "Mark it in the\n  stance as inference and name what it rests on" in prompt

    def test_depth_names_origin_records_and_recorded_publishers(self, corpus):
        findings = [_finding("Silent restore failure", shas=[_SHA_A, _SHA_A2, _SHA_B])]
        brief = assemble_brief(_GOOD, expert_name="E", result=_result(findings), corpus=corpus)
        position = brief.positions[0]
        assert (position.supporting_documents, position.distinct_roots, position.publisher_recorded_sources) == (
            3,
            2,
            3,
        )
        rendered = render_brief(brief)
        assert "3 source(s) from 2 origin record(s); publisher recorded for 3" in rendered
        assert "publisher(s)" not in rendered

    def test_blank_publisher_metadata_is_counted_as_unrecorded(self, tmp_path):
        store = CorpusStore("Blank", storage_dir=tmp_path / "blank")
        store.add("first source body", origin_key="source:one")
        store.add("third source body", origin_key="source:two")
        findings = [_finding("Silent restore failure", shas=[_SHA_A, _SHA_B])]
        brief = assemble_brief(_GOOD, expert_name="E", result=_result(findings), corpus=store)
        assert "2 source(s) from 2 origin record(s); publisher recorded for 0" in render_brief(brief)

    def test_legacy_position_without_publisher_count_reads_and_renders(self):
        legacy = _sound_position(supporting_documents=2, distinct_roots=1).to_dict()
        legacy.pop("publisher_recorded_sources")
        restored = ExpertBrief.from_dict({"expert_name": "E", "positions": [legacy]})
        assert restored.positions[0].publisher_recorded_sources is None
        rendered = render_brief(restored)
        assert "2 source(s) from 1 origin record(s); publisher not counted in this record" in rendered
        assert "one origin record, so this is not corroboration" in rendered

    @pytest.mark.parametrize("value", [-1, True, "3", 2.0])
    def test_malformed_publisher_count_reads_as_not_counted(self, value):
        data = _sound_position().to_dict()
        data["publisher_recorded_sources"] = value
        assert (
            ExpertBrief.from_dict({"expert_name": "E", "positions": [data]}).positions[0].publisher_recorded_sources
            is None
        )

    @pytest.mark.asyncio
    async def test_build_brief_delivers_located_excerpts_with_source_legend(self, tmp_path):
        store = CorpusStore("Excerpt", storage_dir=tmp_path / "excerpt")
        text = "The tested profile used batches of 500 records on Linux only. Other text follows here."
        entry, _ = store.add(text, origin_key="url:a.org", publisher="a.org", fetched_at="2026-05-01T00:00:00+00:00")
        finding = _finding("Batch size", shas=[entry.sha256])
        finding.anchors = ["batches of 500 records on Linux only", "an anchor that is nowhere in the source"]
        seen = {}

        async def completion(prompt):
            seen["prompt"] = prompt
            return json.dumps(_GOOD)

        brief = await build_brief(expert_name="E", result=_result([finding]), corpus=store, completion=completion)
        prompt = seen["prompt"]
        key = f"corpus:{entry.sha256[:12]}"
        assert f"{key}: url:a.org; a.org; retained copy fetched 2026-05-01T00:00:00+00:00" in prompt
        assert f'    - {key}: "batches of 500 records on Linux only"' in prompt
        assert "1 recorded excerpt(s) not located in the cited retained sources; not shown" in prompt
        assert "nowhere in the source" not in prompt
        assert brief.synthesis_input["excerpt_chars_per_finding"] > 0
        assert brief.synthesis_input["excerpts_withheld"] == {}
