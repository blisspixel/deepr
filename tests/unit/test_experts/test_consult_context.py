"""What the expert actually brings to a turn.

The path this replaces carried eight claim strings with three references each,
truncated at 140 characters, against a backend measured holding 567,000. The
corpus, the study and the brief were all on disk and none of them was read.
"""

import json

import pytest

from deepr.experts.brief_contracts import ExpertBrief, Position, SettledState
from deepr.experts.consult_context import (
    ConsultContext,
    build_consult_context,
    gather_sources,
    load_brief,
    rank_positions,
    render_consult_packet,
    render_standing_header,
)
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


@pytest.fixture
def corpus(tmp_path):
    store = CorpusStore("Consult Expert", storage_dir=tmp_path / "corpus")
    store.add(
        "Reconciliation latency rises sharply above fifty clusters in the measured deployments.",
        origin_key="url:a.org",
    )
    store.add("A second publisher reports the opposite under different load.", origin_key="url:b.org")
    return store


@pytest.fixture
def study(corpus):
    shas = [e.sha256 for e in corpus.active_entries()]
    result = StudyResult(expert_name="E")
    result.outcomes = [
        LensOutcome(
            lens="failure",
            axis="interrogation",
            status="ok",
            findings=[
                StudyFinding(
                    lens="failure",
                    axis="interrogation",
                    kind="fail_patterns",
                    title="Reconciliation latency climbs past fifty clusters",
                    finding_id="failure-1",
                    grounded_anchor_count=1,
                    corpus_shas=shas[:1],
                ),
                StudyFinding(
                    lens="contention",
                    axis="interrogation",
                    kind="tensions",
                    title="Publishers disagree about the latency threshold",
                    finding_id="contention-1",
                    grounded_anchor_count=1,
                    corpus_shas=shas,
                ),
                StudyFinding(
                    lens="mechanism",
                    axis="interrogation",
                    kind="concepts",
                    title="Unrelated subject about billing reconciliation forms",
                    finding_id="mechanism-1",
                    grounded_anchor_count=1,
                    corpus_shas=shas[1:],
                ),
            ],
        )
    ]
    return result


@pytest.fixture
def brief():
    b = ExpertBrief(expert_name="E", orientation="The field in sixty seconds.")
    b.state = SettledState(
        settled=["Clusters do reconcile eventually"],
        live=["Where the latency threshold sits"],
        unknown=["Behaviour above five hundred clusters"],
    )
    b.positions = [
        Position(
            question="Does reconciliation latency degrade with cluster count?",
            stance="Yes, above roughly fifty clusters.",
            reasoning="Measured deployments report it.",
            would_change_my_mind="A deployment above fifty clusters showing flat latency.",
            falsifier_resolution_criterion="Measured latency remains flat above fifty clusters.",
            falsifier_resolution_date="2099-01-15",
            supported_by=["failure-1"],
            likelihood="likely",
            confidence="moderate",
        ),
        Position(
            question="Is the billing reconciliation form still required?",
            stance="No, superseded.",
            reasoning="Different subject entirely.",
            would_change_my_mind="A filing that still demands it.",
            supported_by=["mechanism-1"],
            likelihood="unlikely",
            confidence="low",
        ),
    ]
    return b


class TestRanking:
    def test_only_positions_the_question_touches_come_back(self, brief):
        ranked = rank_positions("does latency degrade as clusters grow?", brief)
        assert [p.stance for p in ranked] == ["Yes, above roughly fifty clusters."]

    def test_an_unrelated_question_returns_nothing_rather_than_the_best_guess(self, brief):
        """Backfilling by confidence is how a system answers what it cannot."""
        assert rank_positions("what is the airspeed of a swallow?", brief) == []

    def test_stopwords_do_not_manufacture_a_match(self, brief):
        assert rank_positions("what is it that they should do with this?", brief) == []


class TestSupportTravelsWithThePosition:
    def test_a_ranked_position_pulls_its_own_findings(self, brief, study, corpus):
        context = build_consult_context(
            expert_name="E",
            question="does latency degrade as clusters grow?",
            brief=brief,
            result=study,
            corpus=corpus,
        )
        assert "failure-1" in {f.finding_id for f in context.findings}

    def test_those_findings_bring_the_retained_passage(self, brief, study, corpus):
        """A claim you cannot check is an assertion, whatever else is attached."""
        context = build_consult_context(
            expert_name="E",
            question="does latency degrade as clusters grow?",
            brief=brief,
            result=study,
            corpus=corpus,
        )
        assert context.sources
        assert any("fifty clusters" in passage for _, _, passage in context.sources)

    def test_the_expert_brings_far_more_than_the_old_budget(self, brief, study, corpus):
        """The path this replaces capped its evidence at roughly four kilobytes."""
        context = build_consult_context(
            expert_name="E",
            question="does reconciliation latency degrade as clusters grow?",
            brief=brief,
            result=study,
            corpus=corpus,
        )
        assert context.evidence_chars() > 200


@pytest.mark.parametrize("offset", [0, 1500, 2800, 10000])
def test_cited_anchor_survives_source_selection_and_packet_rendering(tmp_path, offset):
    anchor = "The supported retention period is exactly 37 days."
    text = "Background. " * (offset // 12) + anchor + " Further context." * 200
    store = CorpusStore("Consult Expert", storage_dir=tmp_path / "corpus")
    entry, _ = store.add(text, origin_key="url:primary.example")
    finding = StudyFinding(
        lens="failure",
        axis="interrogation",
        kind="facts",
        title="Retention period",
        anchors=[anchor],
        corpus_shas=[entry.sha256],
        grounded_anchor_count=1,
    )

    sources = gather_sources([finding], store)
    packet = render_consult_packet(ConsultContext(expert_name="Consult Expert", findings=[finding], sources=sources))

    assert len(sources) == 1
    assert sources[0][:2] == (entry.sha256, "url:primary.example")
    assert anchor in sources[0][2]
    assert len(sources[0][2]) <= 2000
    assert anchor in packet
    assert store.read(entry.sha256) == text


def test_shared_source_keeps_distant_anchors_within_both_excerpt_budgets(tmp_path):
    first = "A policy with a 37 day retention period."
    second = "A distinct exception with a 12 day retention period."
    text = "Background. " * 300 + first + " Unrelated material." * 300 + second
    store = CorpusStore("Consult Expert", storage_dir=tmp_path / "corpus")
    entry, _ = store.add(text, origin_key="url:primary.example")
    findings = [
        StudyFinding(
            lens="failure",
            axis="interrogation",
            kind="facts",
            title="Retention period",
            anchors=[anchor, anchor],
            corpus_shas=[entry.sha256],
            grounded_anchor_count=1,
        )
        for anchor in (first, second)
    ]

    sources = gather_sources(findings, store)
    packet = render_consult_packet(ConsultContext(expert_name="Consult Expert", findings=findings, sources=sources))

    assert len(sources) == 1
    excerpt = sources[0][2]
    assert len(excerpt) <= 2000
    assert excerpt.count(first) == excerpt.count(second) == 1
    assert all(span in text for span in excerpt.split("\n[...]\n"))
    assert first in packet and second in packet
    rendered_excerpt = packet.split("---\n", 1)[1].strip()
    assert len(rendered_excerpt) <= 1200


def test_absent_or_oversized_anchors_fall_back_without_claiming_support(tmp_path):
    store = CorpusStore("Consult Expert", storage_dir=tmp_path / "corpus")
    text = "Retained context. " * 300
    entry, _ = store.add(text, origin_key="url:primary.example")
    finding = StudyFinding(
        lens="failure",
        axis="interrogation",
        kind="facts",
        title="Retention period",
        anchors=["not present", "", text],
        corpus_shas=[entry.sha256],
        ungrounded_anchor_count=1,
    )

    sources = gather_sources([finding], store)

    assert sources[0][2] == text[:2000]
    assert finding.is_grounded is False
    assert finding.ungrounded_anchor_count == 1


def test_anchor_selection_keeps_source_and_rendering_limits(tmp_path):
    store = CorpusStore("Consult Expert", storage_dir=tmp_path / "corpus")
    findings = []
    for index in range(10):
        anchors = [f"Exact evidence {index}:{number}." for number in range(15)]
        text = ("Background. " * 300).join(anchors)
        entry, _ = store.add(text, origin_key=f"url:primary-{index}.example")
        findings.append(
            StudyFinding(
                lens="failure",
                axis="interrogation",
                kind="facts",
                title="Evidence",
                anchors=anchors,
                corpus_shas=[entry.sha256],
            )
        )

    sources = gather_sources(findings, store)
    packet = render_consult_packet(ConsultContext(expert_name="Consult Expert", findings=findings, sources=sources))

    assert len(sources) == 8
    assert all(len(passage) <= 2000 for _, _, passage in sources)
    assert packet.count("--- url:") == 4
    for block in packet.split("--- url:")[1:]:
        assert len(block.split("---\n", 1)[1].strip()) <= 1200
    assert gather_sources(findings, store) == sources


class TestCoverage:
    def test_a_matched_grounded_position_is_covered(self, brief, study, corpus):
        context = build_consult_context(
            expert_name="E",
            question="does latency degrade as clusters grow?",
            brief=brief,
            result=study,
            corpus=corpus,
        )
        assert context.coverage == "grounded"

    def test_findings_without_a_position_are_partial_not_covered(self, study, corpus):
        """No position formed, but material that bears on it. Say exactly that."""
        context = build_consult_context(
            expert_name="E",
            question="what do publishers say about the threshold?",
            brief=None,
            result=study,
            corpus=corpus,
        )
        assert context.coverage == "partial"

    def test_nothing_at_all_is_uncovered(self, brief, study, corpus):
        context = build_consult_context(
            expert_name="E",
            question="what is the airspeed of a swallow?",
            brief=brief,
            result=study,
            corpus=corpus,
        )
        assert context.coverage == "uncovered"

    def test_an_expert_never_briefed_still_assembles(self, study, corpus):
        context = build_consult_context(expert_name="E", question="latency", brief=None, result=study, corpus=corpus)
        assert context.orientation == ""
        assert context.coverage in {"partial", "uncovered"}


class TestStandingHeader:
    def test_settled_comes_before_live(self, brief):
        context = build_consult_context(
            expert_name="E", question="latency clusters", brief=brief, result=None, corpus=None
        )
        header = render_standing_header(context)
        assert header.index("Settled") < header.index("Genuinely live")

    def test_the_header_survives_an_unrelated_question(self, brief):
        """It is never retrieved, so a bad match must not drop it."""
        context = build_consult_context(
            expert_name="E", question="airspeed of a swallow", brief=brief, result=None, corpus=None
        )
        header = render_standing_header(context)
        assert "Settled" in header
        assert context.positions == []

    def test_what_is_not_known_is_stated(self, brief):
        context = build_consult_context(expert_name="E", question="latency", brief=brief, result=None, corpus=None)
        assert "Behaviour above five hundred clusters" in render_standing_header(context)


class TestBriefRoundTrip:
    def test_a_persisted_brief_reloads_with_its_calibration(self, tmp_path, brief):
        path = tmp_path / "brief.json"
        path.write_text(json.dumps(brief.to_dict()), encoding="utf-8")

        loaded = load_brief(path)

        assert loaded is not None
        assert loaded.positions[0].likelihood == "likely"
        assert loaded.positions[0].would_change_my_mind
        assert loaded.positions[0].supported_by == ["failure-1"]
        assert loaded.positions[0].is_registered_prediction

    def test_registered_prediction_is_available_during_consult(self, brief):
        context = build_consult_context(
            expert_name="E",
            question="latency above fifty clusters",
            brief=brief,
            result=None,
            corpus=None,
        )

        rendered = render_consult_packet(context)

        assert "Scheduled check 2099-01-15" in rendered
        assert "Measured latency remains flat" in rendered

    def test_a_missing_brief_is_absence_not_an_error(self, tmp_path):
        assert load_brief(tmp_path / "nope.json") is None

    def test_a_corrupt_brief_is_absence_not_a_crash(self, tmp_path):
        path = tmp_path / "brief.json"
        path.write_text("{not json", encoding="utf-8")
        assert load_brief(path) is None


class TestBriefedExpertWithoutBeliefs:
    """acquire -> study -> brief never writes the claim ledger.

    Consult gated its whole path on beliefs.json existing, so an expert with a
    corpus, findings and positions all on disk answered "no stored belief
    context is available". Observed live on a freshly built expert.
    """

    def test_a_brief_alone_produces_a_perspective(self, tmp_path, monkeypatch, brief):
        import json

        from deepr.experts import briefed_perspective as bp

        (tmp_path / "brief.json").write_text(json.dumps(brief.to_dict()), encoding="utf-8")
        monkeypatch.setattr(bp, "canonical_expert_dir", lambda name: tmp_path, raising=False)
        monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda name: tmp_path)

        class _P:
            def __init__(self, **kw):
                self.__dict__.update(kw)

        result = bp.briefed_perspective_without_beliefs("latency clusters", "E", "d", _P)

        assert result is not None
        assert result.context["source"] == "brief"

    def test_no_brief_falls_through_rather_than_inventing(self, tmp_path, monkeypatch):
        from deepr.experts import briefed_perspective as bp

        monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda name: tmp_path)
        assert bp.briefed_perspective_without_beliefs("q", "E", "d", object) is None
