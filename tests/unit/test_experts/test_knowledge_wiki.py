"""Knowledge pages bind actual research without manufacturing qualification."""

import hashlib
import json
import re

import pytest

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.corpus_store import CorpusStore
from deepr.experts.knowledge_wiki import build_knowledge_view, write_knowledge_view
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


@pytest.fixture
def knowledge(tmp_path):
    corpus = CorpusStore("Runtime", storage_dir=tmp_path / "corpus")
    entry, _ = corpus.add(
        "A compound operation needs coordination.",
        origin_key="docs.example",
        title="Coordination",
        url="https://docs.example/runtime",
        fetched_at="2026-09-20T12:00:00Z",
    )
    finding = StudyFinding(
        lens="mechanism",
        axis="interrogation",
        kind="concepts",
        title="Compound operations",
        finding_id="../../untrusted-id",
        payload={"mechanism": "Separate operations can interleave."},
        corpus_shas=[entry.sha256],
        grounded_anchor_count=1,
        ungrounded_anchor_count=1,
    )
    study = StudyResult(
        expert_name="Runtime",
        started_at="2026-09-20T13:00:00Z",
        outcomes=[LensOutcome(lens="mechanism", axis="interrogation", status="ok", findings=[finding])],
    )
    brief = ExpertBrief(
        expert_name="Runtime",
        orientation="Coordinate compound work.",
        positions=[
            Position(
                question="Can these steps interleave?",
                stance="Yes, coordinate them.",
                reasoning="Each step is separate.",
                would_change_my_mind="A documented transaction guarantee.",
                supported_by=[finding.finding_id],
            )
        ],
    )
    return dict(study=study, brief=brief, entries=[entry], history={"revisions": []})


def test_linked_view_is_reproducible_and_all_internal_links_resolve(tmp_path, knowledge):
    identity, pages = build_knowledge_view(**knowledge)
    assert (identity, pages) == build_knowledge_view(**knowledge)
    index = write_knowledge_view(tmp_path, **knowledge)
    assert write_knowledge_view(tmp_path, **knowledge) == index
    manifest = json.loads((index.parent / "manifest.json").read_text())
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((index.parent / relative).read_bytes()).hexdigest() == digest
    for relative, content in pages.items():
        if relative.endswith(".md"):
            for link in re.findall(r"\]\(([^)]+)\)", content):
                if not link.startswith("<https:"):
                    assert (index.parent / relative).parent.joinpath(link).resolve().is_file(), link
    assert "Separate operations can interleave." in "\n".join(pages.values())
    graph = json.loads(pages["evidence.json"])
    assert graph["stats"]["unsupported_positions"] == 0
    assert all(node["first_seen"] == "" for node in graph["nodes"] if node["kind"] == "position")
    assert "unmatched excerpts: 1" in "\n".join(pages.values())
    assert "performs no new search" in pages["currentness.md"]


def test_source_paths_reject_non_content_identities_before_writing(tmp_path, knowledge):
    knowledge["entries"][0].sha256 = "../../outside"
    with pytest.raises(ValueError, match="SHA256"):
        write_knowledge_view(tmp_path, **knowledge)
    assert not (tmp_path / "knowledge").exists()


def test_bound_currentness_notes_are_unique_and_keep_run_history(knowledge):
    from deepr.experts.consult_support import study_fingerprint

    note = "Earlier chunk checkpoints were unavailable or stale; their study contract could not be verified."
    knowledge["study"].limitations = [note, note]
    knowledge["brief"].limitations = [note, "A brief-specific limitation."]
    knowledge["brief"].study_fingerprint = study_fingerprint(knowledge["study"])
    _, pages = build_knowledge_view(**knowledge)
    assert pages["currentness.md"].count(note) == 1
    assert "Checkpoint and retry notes record what happened during that run" in pages["currentness.md"]
    assert "A brief-specific limitation." in pages["currentness.md"]
    assert knowledge["study"].limitations == [note, note]
    assert knowledge["brief"].limitations == [note, "A brief-specific limitation."]


@pytest.mark.parametrize("fingerprint", ["", "older-study"])
def test_old_brief_limitations_are_not_presented_as_current_study_failures(knowledge, fingerprint):
    knowledge["study"].limitations = ["Current recorded limitation."]
    knowledge["brief"].limitations = ["Earlier failure retained for review."]
    knowledge["brief"].study_fingerprint = fingerprint
    _, pages = build_knowledge_view(**knowledge)
    current, earlier = pages["currentness.md"].split("### Brief from a different or unverified study")
    assert "Current recorded limitation." in current
    assert "Earlier failure retained for review." not in current
    assert "Earlier failure retained for review." in earlier
    assert "not attributed to the loaded study" in earlier


def test_changed_understanding_creates_new_view_preserving_old_bytes(tmp_path, knowledge):
    old_index = write_knowledge_view(tmp_path, **knowledge)
    original = {p: p.read_bytes() for p in old_index.parent.rglob("*") if p.is_file()}
    knowledge["brief"].orientation = "A revised perspective."
    new_index = write_knowledge_view(tmp_path, **knowledge)
    assert new_index != old_index
    assert all(path.read_bytes() == content for path, content in original.items())


def test_authored_index_is_preserved_before_any_view_is_written(tmp_path, knowledge):
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "INDEX.md").write_text("My notes", encoding="utf-8")
    with pytest.raises(ValueError, match="authored"):
        write_knowledge_view(tmp_path, **knowledge)
    assert (root / "INDEX.md").read_text() == "My notes"
    assert not (root / "views").exists()


def test_modified_view_is_not_silently_overwritten(tmp_path, knowledge):
    index = write_knowledge_view(tmp_path, **knowledge)
    index.write_text("Reviewed note", encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting content"):
        write_knowledge_view(tmp_path, **knowledge)
    assert index.read_text() == "Reviewed note"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://user:password@example.org", "https://[invalid"])
def test_unsafe_source_urls_are_not_rendered_as_links(knowledge, url):
    knowledge["entries"][0].url = url
    _, pages = build_knowledge_view(**knowledge)
    assert "[Original source]" not in "\n".join(pages.values())


def test_findings_show_actual_excerpts_and_recorded_support(tmp_path, knowledge):
    from deepr.experts.consult_support import study_fingerprint

    finding = knowledge["study"].findings[0]
    finding.anchors = ["A compound operation needs coordination.", "A fabricated unsupported excerpt."]
    position = knowledge["brief"].positions[0]
    position.confidence = "moderate"
    position.confidence_basis = "one retained note"
    knowledge["brief"].study_fingerprint = study_fingerprint(knowledge["study"])
    index = write_knowledge_view(tmp_path, **knowledge)
    finding_page = next((index.parent / "findings").glob("*.md")).read_text()
    assert "> A compound operation needs coordination." in finding_page
    assert "> A fabricated unsupported excerpt." in finding_page
    assert "Matched in retained text:" in finding_page
    assert "Unmatched in the linked retained text." in finding_page
    page = next((index.parent / "positions").glob("*.md")).read_text()
    assert "Recorded support label: moderate" in page
    assert "Basis: one retained note" in page
    assert "1 findings; 1 present" in page
    assert "Findings anchored 1 of 1" in index.read_text()


def test_missing_or_tampered_source_bytes_never_assign_individual_match_status(knowledge):
    finding = knowledge["study"].findings[0]
    finding.anchors = ["A compound operation needs coordination."]
    sha = knowledge["entries"][0].sha256
    for bodies in ({}, {sha: "Tampered retained text"}):
        _, pages = build_knowledge_view(**knowledge, source_texts=bodies)
        page = next(value for key, value in pages.items() if key.startswith("findings/"))
        assert "Match unverified: linked retained text unavailable." in page
        assert "Matched in retained text:" not in page


def test_attribution_links_only_the_bound_study(knowledge):
    from deepr.experts.brief_attribution import OrientationStatement
    from deepr.experts.consult_support import study_fingerprint

    brief = knowledge["brief"]
    fid = knowledge["study"].findings[0].finding_id
    brief.orientation_statements = [OrientationStatement(brief.orientation, "studied", [fid, "missing-id"])]
    brief.study_fingerprint = study_fingerprint(knowledge["study"])
    _, pages = build_knowledge_view(**knowledge)
    perspective = pages["index.md"].split("## Guidance and reasoning")[0]
    assert "Studied sources (recorded attribution)" in perspective
    assert "[Compound operations](findings/" in perspective
    assert "Unresolved finding citation: `missing-id`" in perspective
    brief.study_fingerprint = "old-study"
    _, pages = build_knowledge_view(**knowledge)
    perspective = pages["index.md"].split("## Guidance and reasoning")[0]
    assert "[Compound operations](findings/" not in perspective
    assert "study binding: mismatch" in perspective
    finding_page = next(value for key, value in pages.items() if key.startswith("findings/"))
    assert "Guidance links unresolved" in finding_page
    assert "](../positions/" not in finding_page


def test_renderer_revision_creates_new_view_without_rewriting_prior(tmp_path, knowledge, monkeypatch):
    import deepr.experts.knowledge_wiki as wiki

    old = write_knowledge_view(tmp_path, **knowledge)
    old_bytes = old.read_bytes()
    monkeypatch.setattr(wiki, "RENDERER_VERSION", "future-renderer")
    new = write_knowledge_view(tmp_path, **knowledge)
    assert old != new
    assert old.read_bytes() == old_bytes
