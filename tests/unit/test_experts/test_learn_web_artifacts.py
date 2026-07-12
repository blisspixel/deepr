from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from deepr.experts.learn_web_artifacts import LearnWebArtifactError, persist_learn_web_artifacts


def _research(*, answer: str = "# Topic\n\nFact [S1].") -> dict:
    first = "first fetched page"
    second = "second fetched page"
    sources = []
    for index, (url, content) in enumerate(
        (("https://a.example/release", first), ("https://b.example/news", second)),
        start=1,
    ):
        sources.append(
            {
                "label": f"S{index}",
                "title": f"Source {index}",
                "url": url,
                "source": "duckduckgo+builtin",
                "fetched": True,
                "excerpt": content,
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "answer": answer,
        "sources": [
            {"label": "S1", "title": "Source 1", "url": "https://a.example/release"},
            {"label": "S2", "title": "Source 2", "url": "https://b.example/news"},
        ],
        "source_pack": {
            "schema_version": "deepr.source_pack.v1",
            "mode": "learn-web",
            "source_count": 2,
            "retrieved_source_count": 2,
            "generation_readiness": {"ready": True},
            "sources": sources,
        },
    }


def test_persist_learn_web_artifacts_writes_replayable_contracts(tmp_path):
    artifacts = persist_learn_web_artifacts(
        expert_root=tmp_path,
        expert_name="Web Expert",
        topic="current topic",
        research=_research(),
        started_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    pack = json.loads((tmp_path / artifacts.source_pack).read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / artifacts.source_pack_manifest).read_text(encoding="utf-8"))
    notes = json.loads((tmp_path / artifacts.source_notes).read_text(encoding="utf-8"))
    report = json.loads((tmp_path / artifacts.report).read_text(encoding="utf-8"))

    assert pack["schema_version"] == "deepr.learn_web_source_pack.v1"
    assert "content" not in pack["source_pack"]["sources"][0]
    snapshot_ref = pack["source_pack"]["sources"][0]["snapshot_ref"]
    snapshot = tmp_path / snapshot_ref
    assert snapshot.is_file()
    assert (
        hashlib.sha256(snapshot.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        == pack["source_pack"]["sources"][0]["content_hash"]
    )
    assert manifest["manifest"]["ready_for_semantic_compile"] is True
    assert notes["summary"]["ready_note_count"] == 2
    assert report["source_pack_artifact"] == artifacts.source_pack
    assert report["source_note_artifact"] == artifacts.source_notes
    assert artifacts.report_id == artifacts.report
    assert set(artifacts.source_ref_catalog) == {"S1", "S2"}
    assert all(ref.startswith("source_note:sn_") for ref in artifacts.source_ref_catalog.values())


def test_under_ready_attempt_persists_pack_without_report(tmp_path):
    research = _research(answer="")
    research["source_pack"]["generation_readiness"] = {"ready": False}

    artifacts = persist_learn_web_artifacts(
        expert_root=tmp_path,
        expert_name="Web Expert",
        topic="retry topic",
        research=research,
        started_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )

    assert (tmp_path / artifacts.source_pack).is_file()
    assert artifacts.report == ""
    assert artifacts.report_id == artifacts.source_pack


def test_missing_source_pack_fails_closed(tmp_path):
    with pytest.raises(LearnWebArtifactError, match="no source-pack"):
        persist_learn_web_artifacts(
            expert_root=tmp_path,
            expert_name="Web Expert",
            topic="topic",
            research={"answer": "unsupported"},
            started_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
        )
