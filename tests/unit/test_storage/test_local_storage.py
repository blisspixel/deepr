"""Tests for deepr.storage.local.LocalStorage."""

from __future__ import annotations

import os
import time

import pytest

from deepr.storage.base import StorageError
from deepr.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(base_path=str(tmp_path / "reports"))


class TestValidation:
    def test_job_id_traversal_rejected(self, storage):
        for bad in ["../etc", "a/b", "a\\b", ".."]:
            with pytest.raises(StorageError):
                storage._validate_job_id(bad)

    def test_filename_with_path_rejected(self, storage):
        for bad in ["a/b.md", "..\\x", "../report.md"]:
            with pytest.raises(StorageError):
                storage._validate_filename(bad)

    def test_filename_ok(self, storage):
        assert storage._validate_filename("report.md") == "report.md"


class TestReadableDirname:
    def test_slug_from_prompt(self, storage):
        name = storage._create_readable_dirname("abcd-1234-ef567890", "AI Code Editor Market!!!")
        assert "ai-code-editor-market" in name
        assert name.endswith("ef567890")

    def test_empty_prompt_uses_default(self, storage):
        name = storage._create_readable_dirname("abcd-1234-ef567890", "")
        assert "research" in name

    def test_campaign_id_shortening(self, storage):
        name = storage._create_readable_dirname("campaign-86285e7bcd24", "Sector map")
        assert "86285e7bcd24" in name


class TestSaveGetList:
    @pytest.mark.asyncio
    async def test_save_creates_readable_dir_and_metadata(self, storage):
        meta = await storage.save_report(
            job_id="11111111-2222-3333-4444-555566667777",
            filename="report.md",
            content=b"# Hello",
            content_type="text/markdown",
            metadata={"prompt": "Quantum computing trends"},
        )
        assert meta.format == "md"
        assert meta.size_bytes == len(b"# Hello")
        # Directory is human-readable (contains the slug).
        dirs = [p.name for p in (storage.base_path).iterdir() if p.is_dir() and p.name != "campaigns"]
        assert any("quantum-computing-trends" in d for d in dirs)

    @pytest.mark.asyncio
    async def test_get_report_roundtrip(self, storage):
        jid = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
        await storage.save_report(jid, "report.md", b"body", "text/markdown", {"prompt": "p"})
        got = await storage.get_report(jid, "report.md")
        assert got == b"body"

    @pytest.mark.asyncio
    async def test_get_missing_raises(self, storage):
        with pytest.raises(StorageError):
            await storage.get_report("nope-nope-nope-nope-nope", "report.md")

    @pytest.mark.asyncio
    async def test_report_exists(self, storage):
        jid = "1234abcd-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        assert await storage.report_exists(jid, "report.md") is True
        assert await storage.report_exists(jid, "missing.md") is False

    @pytest.mark.asyncio
    async def test_list_reports_by_job_and_all(self, storage):
        jid = "5678abcd-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        by_job = await storage.list_reports(jid)
        assert any(r.filename == "report.md" for r in by_job)
        all_reports = await storage.list_reports()
        assert any(r.filename == "report.md" for r in all_reports)

    @pytest.mark.asyncio
    async def test_list_reports_unknown_job_empty(self, storage):
        assert await storage.list_reports("ffffffff-0000-0000-0000-000000000000") == []


class TestDeleteAndUrl:
    @pytest.mark.asyncio
    async def test_delete_single_file(self, storage):
        jid = "del10000-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        assert await storage.delete_report(jid, "report.md") is True
        assert await storage.report_exists(jid, "report.md") is False

    @pytest.mark.asyncio
    async def test_delete_missing_file_returns_false(self, storage):
        jid = "del20000-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        assert await storage.delete_report(jid, "missing.md") is False

    @pytest.mark.asyncio
    async def test_delete_whole_job_dir(self, storage):
        jid = "del30000-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        assert await storage.delete_report(jid) is True

    @pytest.mark.asyncio
    async def test_get_report_url_file_uri(self, storage):
        jid = "url10000-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        url = await storage.get_report_url(jid, "report.md")
        assert url.startswith("file:")

    @pytest.mark.asyncio
    async def test_get_report_url_missing_raises(self, storage):
        with pytest.raises(StorageError):
            await storage.get_report_url("missing0-0000-1111-2222-333344445555", "report.md")


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_old_reports_removes_aged(self, storage):
        jid = "old10000-0000-1111-2222-333344445555"
        meta = await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        # Backdate the file mtime by 40 days.
        old = time.time() - 40 * 86400
        report_file = storage._get_report_path(jid, "report.md")
        os.utime(report_file, (old, old))
        # metadata.json too, so the whole dir is "old".
        meta_file = report_file.parent / "metadata.json"
        if meta_file.exists():
            os.utime(meta_file, (old, old))
        deleted = await storage.cleanup_old_reports(days=30)
        assert deleted >= 1
        assert meta.format == "md"

    @pytest.mark.asyncio
    async def test_cleanup_keeps_fresh(self, storage):
        jid = "new10000-0000-1111-2222-333344445555"
        await storage.save_report(jid, "report.md", b"x", "text/markdown", {"prompt": "p"})
        assert await storage.cleanup_old_reports(days=30) == 0
