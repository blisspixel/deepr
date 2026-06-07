"""Coverage for ExpertStore document/vector-store + bulk helpers.

Exercises add_documents_to_vector_store, refresh_expert_knowledge, and the
bulk get_stale_experts / get_experts_by_domain helpers with a mocked async
provider client (no network, no API key).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore


@pytest.fixture
def store(tmp_path):
    return ExpertStore(base_path=str(tmp_path / "experts"))


def _profile(name: str = "vs-expert", domain: str = "testing") -> ExpertProfile:
    return ExpertProfile(name=name, vector_store_id="vs_1", description="d", domain=domain)


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.files.create = AsyncMock(return_value=MagicMock(id="file_1"))
    client.vector_stores.files.create = AsyncMock(return_value=None)
    return client


class TestAddDocuments:
    @pytest.mark.asyncio
    async def test_uploads_new_file(self, store, tmp_path):
        prof = _profile()
        store.save(prof)
        doc = tmp_path / "a.md"
        doc.write_text("# doc", encoding="utf-8")

        result = await store.add_documents_to_vector_store(prof, [str(doc)], _mock_client())
        assert len(result["uploaded"]) == 1
        assert result["uploaded"][0]["file_id"] == "file_1"
        assert str(doc) in prof.source_files
        assert prof.total_documents == 1

    @pytest.mark.asyncio
    async def test_skips_already_uploaded(self, store, tmp_path):
        prof = _profile()
        doc = tmp_path / "a.md"
        doc.write_text("x", encoding="utf-8")
        prof.source_files.append(str(doc))

        result = await store.add_documents_to_vector_store(prof, [str(doc)], _mock_client())
        assert result["skipped"] == [str(doc)]
        assert result["uploaded"] == []

    @pytest.mark.asyncio
    async def test_records_failure(self, store, tmp_path):
        prof = _profile()
        doc = tmp_path / "a.md"
        doc.write_text("x", encoding="utf-8")
        client = _mock_client()
        client.files.create = AsyncMock(side_effect=RuntimeError("upload boom"))

        result = await store.add_documents_to_vector_store(prof, [str(doc)], client)
        assert len(result["failed"]) == 1
        assert "upload boom" in result["failed"][0]["error"]


class TestRefreshExpertKnowledge:
    @pytest.mark.asyncio
    async def test_missing_expert_raises(self, store):
        with pytest.raises(ValueError):
            await store.refresh_expert_knowledge("ghost", _mock_client())

    @pytest.mark.asyncio
    async def test_no_documents_dir_message(self, store):
        prof = _profile("no-docs")
        store.save(prof)
        # Ensure the documents dir does not exist.
        docs = store.get_documents_dir("no-docs")
        if docs.exists():
            for f in docs.iterdir():
                f.unlink()
            docs.rmdir()
        result = await store.refresh_expert_knowledge("no-docs", _mock_client())
        assert "No documents directory" in result["message"] or result["uploaded"] == []

    @pytest.mark.asyncio
    async def test_uploads_new_docs(self, store):
        prof = _profile("with-docs")
        store.save(prof)
        docs = store.get_documents_dir("with-docs")
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "note.md").write_text("# note", encoding="utf-8")

        result = await store.refresh_expert_knowledge("with-docs", _mock_client())
        assert "1 new documents" in result["message"]
        assert len(result["uploaded"]) == 1

    @pytest.mark.asyncio
    async def test_all_docs_already_known(self, store):
        prof = _profile("known-docs")
        docs = store.get_documents_dir("known-docs")
        docs.mkdir(parents=True, exist_ok=True)
        doc = docs / "note.md"
        doc.write_text("# note", encoding="utf-8")
        prof.source_files.append(str(doc))
        store.save(prof)

        result = await store.refresh_expert_knowledge("known-docs", _mock_client())
        assert "already in vector store" in result["message"]


class TestBulkHelpers:
    def test_get_stale_experts(self, store):
        fresh = _profile("fresh")
        fresh.knowledge_cutoff_date = datetime.now(UTC)
        store.save(fresh)

        stale = _profile("stale")
        stale.knowledge_cutoff_date = datetime.now(UTC) - timedelta(days=3650)
        store.save(stale)

        names = {p.name for p in store.get_stale_experts()}
        assert "stale" in names

    def test_get_experts_by_domain(self, store):
        store.save(_profile("a", domain="ai"))
        store.save(_profile("b", domain="security"))
        ai = {p.name for p in store.get_experts_by_domain("ai")}
        assert ai == {"a"}
