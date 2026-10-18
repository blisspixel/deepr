"""Attribution records model judgment without inventing legacy provenance."""

import pytest

from deepr.experts.brief import assemble_brief, build_brief_prompt, render_brief
from deepr.experts.brief_attribution import read_orientation_statements, render_orientation
from deepr.experts.brief_contracts import ExpertBrief
from deepr.experts.consult_context import build_consult_context
from deepr.experts.consult_prompt import brief_synthesis_blocks
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


@pytest.fixture
def material(tmp_path):
    corpus = CorpusStore("Bread", storage_dir=tmp_path / "corpus")
    entry, _ = corpus.add("Fermentation depends on dough temperature.", origin_key="bread.notes")
    finding = StudyFinding(
        lens="synopsis",
        axis="interrogation",
        kind="notes",
        title="Temperature",
        finding_id="synopsis-1",
        anchors=["Fermentation depends on dough temperature."],
        corpus_shas=[entry.sha256],
        grounded_anchor_count=1,
    )
    study = StudyResult(
        expert_name="Bread",
        outcomes=[
            LensOutcome(
                lens="synopsis",
                axis="interrogation",
                status="ok",
                findings=[finding],
            )
        ],
    )
    return corpus, study


def test_new_brief_roundtrip_and_every_read_surface_preserve_origins(material):
    corpus, study = material
    statements = [
        {"text": "Temperature matters.", "origin": "studied", "supported_by": ["synopsis-1"]},
        {"text": "Yeast strain may matter.", "origin": "broader_knowledge"},
        {"text": "Measure the dough.", "origin": "reasoning"},
    ]
    brief = assemble_brief(
        {"orientation": "A different model summary must not lose the labels.", "orientation_statements": statements},
        expert_name="Bread",
        corpus=corpus,
        result=study,
    )
    assert brief.orientation == "Temperature matters. Yeast strain may matter. Measure the dough."
    restored = ExpertBrief.from_dict(brief.to_dict())
    assert restored.orientation_statements == brief.orientation_statements
    context = build_consult_context(
        expert_name="Bread", question="Temperature?", brief=restored, result=study, corpus=corpus
    )
    for output in (render_brief(restored), context.orientation, "\n".join(brief_synthesis_blocks(context))):
        assert "Broader knowledge, not established by this study: Yeast strain" in output
        assert "Expert reasoning, not a source observation: Measure" in output
        assert "synopsis-1" in output
    assert "study binding: matched" in context.orientation
    prompt = build_brief_prompt(study, expert_name="Bread")
    assert "orientation_statements" in prompt and "broader_knowledge" in prompt


def test_legacy_and_mismatched_paragraphs_remain_unattributed():
    brief = ExpertBrief.from_dict({"expert": "Bread", "orientation": "Older view."})
    assert "Origin not recorded: Older view." in render_brief(brief)
    brief.orientation_statements = read_orientation_statements([{"text": "Other view.", "origin": "studied"}])
    assert "Origin not recorded: Older view." in render_brief(brief)
    assert "Other view" not in render_brief(brief)


@pytest.mark.parametrize("value", [None, "bad", {}, [None], [{"text": ""}], [{"text": "ok"}, {"text": 3}]])
def test_malformed_statements_preserve_existing_orientation(material, value):
    corpus, study = material
    brief = assemble_brief(
        {"orientation": "Existing prose.", "orientation_statements": value},
        expert_name="Bread",
        corpus=corpus,
        result=study,
    )
    assert brief.orientation == "Existing prose."
    assert brief.orientation_statements == []


def test_unknown_origins_and_unresolved_citations_do_not_become_sourced():
    statements = read_orientation_statements(
        [
            {"text": "Unclassified.", "origin": {"invalid": True}, "supported_by": [None, "made-up"]},
            {"text": "Source claim.", "origin": "studied", "supported_by": "bad-shape"},
        ]
    )
    output = render_orientation("Unclassified. Source claim.", statements, binding="mismatch")
    assert "Origin not recorded: Unclassified." in output
    assert "made-up" in output and "study binding: mismatch" in output
    assert "No supporting finding recorded" in output
