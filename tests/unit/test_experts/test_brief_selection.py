"""Which findings a brief synthesis sees is a recorded, lens-balanced choice."""

import hashlib
import itertools
from collections import Counter

import pytest

from deepr.experts.brief import assemble_brief, brief_prompt_with_selection, build_brief
from deepr.experts.brief_contracts import ExpertBrief
from deepr.experts.brief_selection import (
    MAX_FIELD_CHARS,
    MAX_FINDINGS_IN_PROMPT,
    BriefSelection,
    select_findings,
    shorten_field,
)
from deepr.experts.consult_support import study_fingerprint
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _finding(lens: str, ordinal: int, **payload: object) -> StudyFinding:
    return StudyFinding(
        lens=lens,
        axis="interrogation",
        kind="notes",
        title=f"{lens} note {ordinal}",
        finding_id=f"{lens}-{ordinal}",
        payload=dict(payload) or {"note": f"{lens} detail {ordinal}"},
        grounded_anchor_count=1,
    )


def _study(*lenses: tuple[str, int]) -> StudyResult:
    return StudyResult(
        expert_name="E",
        outcomes=[
            LensOutcome(
                lens=lens,
                axis="interrogation",
                status="ok",
                findings=[_finding(lens, ordinal) for ordinal in range(1, count + 1)],
            )
            for lens, count in lenses
        ],
    )


@pytest.fixture
def corpus(tmp_path):
    return CorpusStore("Selection Expert", storage_dir=tmp_path / "corpus")


def test_late_contention_reaches_synthesis_past_the_finding_cap():
    """The prefix cap used to drop every contention finding behind 130 notes."""
    study = _study(("synopsis", 130), ("contention", 3))
    prompt, selection = brief_prompt_with_selection(study, expert_name="E")

    assert all(f"contention-{n} [contention]" in prompt for n in (1, 2, 3))
    assert len(selection.presented_ids) == MAX_FINDINGS_IN_PROMPT
    assert selection.total_findings == 133
    assert len(selection.omitted_ids) == 13
    assert selection.contention_presented == selection.contention_total == 3
    assert not selection.complete
    assert "3 finding(s) below came from the contention lens" in prompt
    assert f"shown {MAX_FINDINGS_IN_PROMPT} of 133 study findings" in prompt
    assert "Do not claim the whole study was considered" in prompt
    assert set(selection.presented_ids).isdisjoint(selection.omitted_ids)
    assert set(selection.presented_ids) | set(selection.omitted_ids) == {f.finding_id for f in study.findings}


def test_selection_is_invariant_to_lens_order():
    """Which lens runs first must not decide which lenses synthesis hears from."""
    shapes = [("synopsis", 90), ("mechanism", 40), ("contention", 12), ("failure", 2)]
    counts = set()
    for order in itertools.permutations(shapes):
        chosen = select_findings(_study(*order))
        counts.add(tuple(sorted(Counter(f.lens for f in chosen).items())))
    assert counts == {(("contention", 12), ("failure", 2), ("mechanism", 40), ("synopsis", 66))}


def test_selection_keeps_study_order_within_and_across_lenses():
    study = _study(("synopsis", 3), ("contention", 2))
    assert [f.finding_id for f in select_findings(study, limit=4)] == [
        "synopsis-1",
        "synopsis-2",
        "contention-1",
        "contention-2",
    ]


def test_small_study_is_presented_whole_and_reports_complete():
    study = _study(("synopsis", 2), ("contention", 1))
    prompt, selection = brief_prompt_with_selection(study, expert_name="E")
    assert selection.complete
    assert selection.omitted_ids == []
    assert selection.limitations() == []
    assert "You are shown" not in prompt
    assert selection.prompt_sha256 == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert selection.prompt_chars == len(prompt)
    assert selection.study_fingerprint == study_fingerprint(study)


def test_complete_long_field_preserves_its_trailing_condition():
    condition = "This only holds on version 3 and fails on Windows."
    long_field = ("The setting is safe to enable in production deployments. " * 12) + condition
    finding = _finding("synopsis", 1, note=long_field, short="kept whole")
    study = StudyResult(
        expert_name="E",
        outcomes=[LensOutcome(lens="synopsis", axis="interrogation", status="ok", findings=[finding])],
    )
    prompt, selection = brief_prompt_with_selection(study, expert_name="E")

    assert long_field in prompt
    assert condition in prompt
    assert "short: kept whole\n" in prompt
    assert selection.shortened == []
    assert selection.complete


def test_shortening_prefers_a_sentence_boundary_and_never_marks_fitting_text():
    fitting = "x" * MAX_FIELD_CHARS
    assert shorten_field(fitting) == fitting
    text = "First sentence ends here. " * 30
    shown = shorten_field(text)
    kept = shown.rsplit(" [shortened:", 1)[0]
    assert kept.endswith("here.")
    assert len(kept) <= MAX_FIELD_CHARS
    unbroken = "y" * (MAX_FIELD_CHARS + 50)
    assert shorten_field(unbroken).startswith("y" * MAX_FIELD_CHARS + " [shortened:")


def test_contention_omitted_by_the_cap_is_counted_and_disclosed():
    study = _study(*[(f"lens{n}", 20) for n in range(7)], ("contention", 20))
    prompt, selection = brief_prompt_with_selection(study, expert_name="E")
    assert selection.contention_presented == 15
    assert selection.contention_total == 20
    assert "5 further contention finding(s) exist in the study but are not shown here" in prompt
    assert any("5 of 20 contention" in note for note in selection.limitations())


def test_citation_of_an_unshown_finding_is_dropped(corpus):
    study = _study(("synopsis", 130), ("contention", 1))
    _, selection = brief_prompt_with_selection(study, expert_name="E")
    unshown = selection.omitted_ids[0]
    parsed = {
        "positions": [
            {
                "question": "q",
                "stance": "s",
                "reasoning": "r",
                "would_change_my_mind": "A measured counterexample.",
                "supported_by": [unshown, "contention-1"],
            }
        ],
        "anticipated_questions": [{"question": "why", "answer": "a", "supported_by": [unshown]}],
    }
    brief = assemble_brief(parsed, expert_name="E", result=study, corpus=corpus, selection=selection)

    assert brief.positions[0].supported_by == ["contention-1"]
    assert brief.anticipated_questions[0].supported_by == []
    assert brief.generated_from_findings == 131
    assert brief.synthesis_input["omitted_ids"] == selection.omitted_ids
    assert any("Synthesis was shown 120 of 131" in note for note in brief.limitations)


def test_receipt_round_trips_and_legacy_briefs_report_none(corpus):
    study = _study(("synopsis", 2))
    _, selection = brief_prompt_with_selection(study, expert_name="E")
    brief = assemble_brief({"positions": []}, expert_name="E", result=study, corpus=corpus, selection=selection)

    restored = ExpertBrief.from_dict(brief.to_dict())
    assert restored.synthesis_input == brief.synthesis_input
    assert BriefSelection.from_dict(restored.synthesis_input) == selection
    legacy = ExpertBrief.from_dict({"expert": "E", "generated_from_findings": 4})
    assert legacy.synthesis_input == {}
    assert BriefSelection.from_dict(legacy.synthesis_input) is None


async def test_failed_synthesis_still_records_what_it_was_shown(corpus):
    study = _study(("synopsis", 125))
    prompts: list[str] = []

    async def failing(prompt: str) -> str:
        prompts.append(prompt)
        raise RuntimeError("local model unavailable")

    brief = await build_brief(expert_name="E", result=study, corpus=corpus, completion=failing)
    assert brief.synthesis_input["prompt_sha256"] == hashlib.sha256(prompts[0].encode("utf-8")).hexdigest()
    assert len(brief.synthesis_input["omitted_ids"]) == 5
    assert any("Synthesis call failed" in note for note in brief.limitations)


def test_orientation_cannot_cite_a_finding_synthesis_was_not_shown(corpus):
    """Review finding: orientation statements kept citations to unshown findings."""
    study = _study(("synopsis", 130), ("contention", 1))
    _, selection = brief_prompt_with_selection(study, expert_name="E")
    unshown = selection.omitted_ids[0]
    parsed = {
        "orientation_statements": [
            {"text": "Studied claim.", "origin": "studied", "supported_by": [unshown, "contention-1"]}
        ],
        "positions": [],
    }
    brief = assemble_brief(parsed, expert_name="E", result=study, corpus=corpus, selection=selection)
    assert brief.orientation_statements[0].supported_by == ["contention-1"]


def test_oversized_finding_is_omitted_whole_and_cannot_be_cited(corpus):
    study = _study(("synopsis", 1), ("contention", 1))
    long = study.findings[0]
    long.payload = {"note": "Visible prefix. " + "x" * 60000, "condition": "Only after origin validation."}
    prompt, selection = brief_prompt_with_selection(study, expert_name="E", max_prompt_chars=8000)
    assert "Visible prefix." not in prompt
    assert "Only after origin validation." not in prompt
    assert selection.presented_ids == ["contention-1"]
    assert selection.omission_reasons == {"synopsis-1": "prompt_chars"}
    assert selection.prompt_chars <= selection.max_prompt_chars == 8000
    brief = assemble_brief(
        {"positions": [{"stance": "unsafe", "supported_by": [long.finding_id]}]},
        expert_name="E",
        result=study,
        corpus=corpus,
        selection=selection,
    )
    assert brief.positions[0].supported_by == []


def test_exact_envelope_and_payload_bound_drill_down():
    study = _study(("synopsis", 1))
    study.findings[0].payload = {"note": "Source condition: origin validation is mandatory."}
    prompt, selection = brief_prompt_with_selection(study, expert_name="Unicode \u96ea")
    _, tight = brief_prompt_with_selection(study, expert_name="Unicode \u96ea", max_prompt_chars=len(prompt))
    assert tight.complete
    restored = BriefSelection.from_dict(tight.to_dict())
    assert restored == tight
    assert restored.resolve_finding(study, "synopsis-1") is study.findings[0]
    study.findings[0].payload["note"] = "Source condition removed."
    assert study_fingerprint(study) == selection.study_fingerprint
    with pytest.raises(ValueError, match="content"):
        restored.resolve_finding(study, "synopsis-1")


async def test_oversized_framing_refuses_before_completion_and_retains_receipt(corpus):
    calls = []

    async def completion(prompt):
        calls.append(prompt)
        return "{}"

    study = _study(("synopsis", 1))
    brief = await build_brief(expert_name="E" * 60000, result=study, corpus=corpus, completion=completion)
    assert calls == []
    assert brief.synthesis_input["admission_status"] == "refused_prompt_envelope"
    assert brief.synthesis_input["presented_ids"] == []
    assert brief.synthesis_input["omitted_ids"] == ["synopsis-1"]
    assert any("before dispatch" in note for note in brief.limitations)


async def test_no_complete_finding_fit_refuses_before_completion(corpus):
    study = _study(("synopsis", 1))
    study.findings[0].payload = {"note": "complete unit " * 5000}
    calls = []

    async def completion(prompt):
        calls.append(prompt)
        return "{}"

    brief = await build_brief(
        expert_name="E", result=study, corpus=corpus, completion=completion, max_prompt_chars=8000
    )
    assert calls == []
    assert brief.synthesis_input["admission_status"] == "refused_no_complete_findings"
    assert brief.synthesis_input["omission_reasons"] == {"synopsis-1": "prompt_chars"}


@pytest.mark.parametrize("duplicate", [True, False])
async def test_ambiguous_or_empty_finding_identity_refuses_before_completion(corpus, duplicate):
    study = _study(("synopsis", 2))
    study.findings[1].finding_id = study.findings[0].finding_id if duplicate else ""
    calls = []

    async def completion(prompt):
        calls.append(prompt)
        return "{}"

    brief = await build_brief(expert_name="E", result=study, corpus=corpus, completion=completion)
    assert calls == []
    assert brief.synthesis_input["admission_status"] == "refused_finding_identity"
    assert brief.synthesis_input["presented_ids"] == []


def test_character_bound_preserves_lens_balance_and_complete_multifield_units():
    from types import SimpleNamespace

    counts = set()
    for lenses in itertools.permutations([("lensA", 8), ("lensB", 8), ("lensC", 8)]):
        study = _study(*lenses)
        for finding in study.findings:
            finding.payload = {
                "note": "qualification \u96ea " * 15,
                "condition": ["origin validation", "version 3 only"],
            }
            finding.grounded_anchor_count = 0
        prompt, selection = brief_prompt_with_selection(
            study,
            expert_name="Unicode \u96ea",
            prior_positions=[SimpleNamespace(question="Original question?" * 25)],
            max_prompt_chars=10000,
        )
        assert 0 < len(selection.presented_ids) < len(study.findings)
        assert selection.prompt_chars == len(prompt) <= 10000
        assert selection.max_prompt_chars == 10000
        assert selection.shortened == []
        counts.add(
            tuple(sorted(Counter(f.lens for f in study.findings if f.finding_id in selection.presented_ids).items()))
        )
        for finding in study.findings:
            assert (f"{finding.finding_id} [{finding.lens}]" in prompt) == (
                finding.finding_id in selection.presented_ids
            )
        assert prompt.count("condition: origin validation; version 3 only") == len(selection.presented_ids)
        assert prompt.count("UNVERIFIED: quoted support not found") == len(selection.presented_ids)
    assert all(max(value for _, value in row) - min(value for _, value in row) <= 1 for row in counts)
    assert len({sum(value for _, value in row) for row in counts}) == 1


@pytest.mark.parametrize("with_retry", [False, True])
def test_shrinking_notices_cannot_hide_a_fitting_complete_unit(with_retry):
    from datetime import date

    from deepr.experts.brief import _render_brief_prompt, _render_finding
    from deepr.experts.brief_selection import start_selection

    study = _study(("synopsis", 2 if with_retry else 1), ("contention", 1))
    study.findings[0].payload = {"note": "x" * (30 if with_retry else 61000)}
    if with_retry:
        study.findings[1].payload = {"note": "x" * 61000}
    study.findings[-1].payload = {"note": "b"}
    desired = [study.findings[0], study.findings[-1]] if with_retry else [study.findings[-1]]
    expected = _render_brief_prompt(
        expert_name="E",
        domain="",
        prior_positions=None,
        as_of_date=date(2026, 10, 20),
        rendered="\n".join(_render_finding(finding) for finding in desired),
        selection=start_selection(study, desired, study_fingerprint(study)),
    )
    prompt, selection = brief_prompt_with_selection(
        study,
        expert_name="E",
        as_of_date=date(2026, 10, 20),
        max_prompt_chars=len(expected),
    )
    assert prompt == expected
    assert selection.presented_ids == [finding.finding_id for finding in desired]
    assert selection.omission_reasons == {"synopsis-2" if with_retry else "synopsis-1": "prompt_chars"}


def _excerpt_study(tmp_path, count: int = 6) -> tuple[StudyResult, CorpusStore]:
    """Findings whose anchors are located in retained sources with mixed metadata."""
    store = CorpusStore("Excerpt Expert", storage_dir=tmp_path / "excerpt-corpus")
    findings = []
    for ordinal in range(1, count + 1):
        sentence = f"Observation number {ordinal} held only for the tested profile on platform {ordinal}."
        dated = {"publisher": "pub.example", "fetched_at": f"2026-04-0{ordinal % 9 + 1}T00:00:00+00:00"}
        entry, _ = store.add(
            sentence + " " + "Filler text. " * 20, origin_key=f"url:{ordinal}", **(dated if ordinal % 2 else {})
        )
        finding = _finding("synopsis" if ordinal % 2 else "contention", ordinal)
        finding.corpus_shas = [entry.sha256]
        finding.anchors = [sentence]
        findings.append(finding)
    study = StudyResult(
        expert_name="E",
        outcomes=[LensOutcome(lens="synopsis", axis="interrogation", status="ok", findings=findings)],
    )
    return study, store


def test_excerpts_never_displace_a_complete_finding(tmp_path):
    """Admission of findings is identical with and without excerpts; excerpts fill what is left."""
    study, store = _excerpt_study(tmp_path)
    plain_prompt, _ = brief_prompt_with_selection(study, expert_name="E")
    for cap, shown in ((len(plain_prompt) + 600, 2), (len(plain_prompt), 0), (len(plain_prompt) - 40, 0)):
        _, without = brief_prompt_with_selection(study, expert_name="E", max_prompt_chars=cap)
        prompt, selection = brief_prompt_with_selection(study, expert_name="E", max_prompt_chars=cap, corpus=store)
        assert selection.presented_ids == without.presented_ids
        assert len(prompt) <= cap
        assert selection.prompt_sha256 == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        assert prompt.count("    - S") == shown
        assert all(selection.excerpt_omission_reasons[fid] == "prompt_chars" for fid in selection.excerpts_withheld)
        assert len(selection.excerpts_withheld) == len(selection.presented_ids) - shown
    assert len(without.presented_ids) < len(study.findings)


def test_full_room_shows_every_located_excerpt_with_its_source_key(tmp_path):
    study, store = _excerpt_study(tmp_path, count=3)
    prompt, selection = brief_prompt_with_selection(study, expert_name="E", corpus=store)
    assert selection.excerpts_withheld == {}
    assert selection.excerpt_chars_per_finding > 0
    assert prompt.index("===== EXCERPT SOURCES") < prompt.index("===== FINDINGS BEGIN =====")
    assert "S1: url:1; pub.example; fetched 2026-04-02T00:00:00+00:00" in prompt
    assert "S2: url:2; publisher unrecorded; fetch time unrecorded" in prompt
    assert '    - S2: "Observation number 2 held only for the tested profile on platform 2."' in prompt


def test_per_finding_bound_withholds_whole_excerpts_and_records_them(tmp_path):
    from deepr.experts.brief_selection import MAX_EXCERPT_CHARS_PER_FINDING

    store = CorpusStore("Bound", storage_dir=tmp_path / "bound")
    words = [f"distinctword{index:04d}" for index in range(400)]
    entry, _ = store.add(" ".join(words), origin_key="url:a")
    finding = _finding("synopsis", 1)
    finding.corpus_shas = [entry.sha256]
    first = " ".join(words[:40])
    second = " ".join(words[40:80])
    assert len(first) + len(second) > MAX_EXCERPT_CHARS_PER_FINDING >= len(first)
    finding.anchors = [first, second]
    study = StudyResult(
        expert_name="E", outcomes=[LensOutcome(lens="synopsis", axis="interrogation", status="ok", findings=[finding])]
    )
    prompt, selection = brief_prompt_with_selection(study, expert_name="E", corpus=store)
    assert first in prompt and second not in prompt
    assert "1 further located excerpt(s) withheld by the per-finding bound" in prompt
    assert selection.excerpts_withheld == {"synopsis-1": 1}
    assert selection.excerpt_omission_reasons == {"synopsis-1": "excerpt_chars"}
    assert any("located source excerpt(s)" in note for note in selection.limitations())


def test_excerpt_receipt_round_trips_and_legacy_receipts_default(tmp_path):
    study, store = _excerpt_study(tmp_path)
    plain_prompt, _ = brief_prompt_with_selection(study, expert_name="E")
    _, selection = brief_prompt_with_selection(study, expert_name="E", max_prompt_chars=len(plain_prompt), corpus=store)
    restored = BriefSelection.from_dict(selection.to_dict())
    assert restored is not None
    assert restored.excerpts_withheld == selection.excerpts_withheld
    assert restored.excerpt_omission_reasons == selection.excerpt_omission_reasons
    assert restored.excerpt_chars_per_finding == selection.excerpt_chars_per_finding
    legacy = selection.to_dict()
    for key in ("excerpt_chars_per_finding", "excerpts_withheld", "excerpt_omission_reasons"):
        legacy.pop(key)
    old = BriefSelection.from_dict(legacy)
    assert old is not None and old.excerpts_withheld == {} and old.excerpt_chars_per_finding == 0


def test_brief_prompt_without_corpus_carries_no_excerpt_legend():
    study = _study(("synopsis", 2))
    prompt, selection = brief_prompt_with_selection(study, expert_name="E")
    assert "EXCERPT SOURCES" not in prompt
    assert selection.excerpt_chars_per_finding == 0


def test_a_single_overlong_excerpt_is_withheld_by_the_bound_not_the_prompt(tmp_path):
    from deepr.experts.brief_selection import MAX_EXCERPT_CHARS_PER_FINDING

    store = CorpusStore("Long", storage_dir=tmp_path / "long")
    words = [f"token{index:04d}" for index in range(300)]
    entry, _ = store.add(" ".join(words), origin_key="url:a")
    anchor = " ".join(words[:120])
    assert len(anchor) > MAX_EXCERPT_CHARS_PER_FINDING
    finding = _finding("synopsis", 1)
    finding.corpus_shas, finding.anchors = [entry.sha256], [anchor]
    study = StudyResult(
        expert_name="E", outcomes=[LensOutcome(lens="synopsis", axis="interrogation", status="ok", findings=[finding])]
    )
    prompt, selection = brief_prompt_with_selection(study, expert_name="E", corpus=store)
    assert anchor not in prompt and "EXCERPT SOURCES" not in prompt
    assert selection.excerpts_withheld == {"synopsis-1": 1}
    assert selection.excerpt_omission_reasons == {"synopsis-1": "excerpt_chars"}
