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
