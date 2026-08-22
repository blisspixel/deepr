"""Tests for deepr.storage.local.LocalStorage."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from deepr.storage.base import StorageError
from deepr.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(base_path=str(tmp_path / "reports"))


class TestValidation:
    def test_job_id_traversal_rejected(self, storage):
        for bad in ["../etc", "a/b", "a\\b", "..", "job$name"]:
            with pytest.raises(StorageError):
                storage._validate_job_id(bad)

    def test_filename_with_path_rejected(self, storage):
        for bad in ["a/b.md", "..\\x", "../report.md"]:
            with pytest.raises(StorageError):
                storage._validate_filename(bad)

    def test_filename_ok(self, storage):
        assert storage._validate_filename("report.md") == "report.md"

    @pytest.mark.parametrize("filename", ["metadata.json", "METADATA.JSON", "Metadata.Json"])
    def test_internal_metadata_filename_is_reserved(self, storage, filename):
        with pytest.raises(StorageError):
            storage._validate_filename(filename)

    @pytest.mark.parametrize("job_id", ["_job", "job_", "job__id"])
    def test_valid_underscore_job_ids_are_preserved(self, storage, job_id):
        assert storage._validate_job_id(job_id) == job_id

    def test_job_dir_resolves_in_base_symlink(self, storage):
        target = storage.base_path / "target"
        target.mkdir()
        link = storage.base_path / "job"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("Directory symlinks are unavailable on this platform")

        assert storage._get_job_dir("job") == target.resolve()

    def test_job_dir_rejects_symlink_escape(self, storage, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        link = storage.base_path / "job"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("Directory symlinks are unavailable on this platform")

        with pytest.raises(StorageError):
            storage._get_job_dir("job")


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
    async def test_short_job_id_does_not_match_unrelated_readable_dir(self, storage):
        jid = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
        await storage.save_report(jid, "report.md", b"private body", "text/markdown", {"prompt": "alpha report"})

        with pytest.raises(StorageError):
            await storage.get_report("a", "report.md")

    @pytest.mark.asyncio
    async def test_job_id_does_not_match_prompt_slug_substring(self, storage):
        jid = "11111111-2222-3333-4444-555566667777"
        await storage.save_report(jid, "report.md", b"private body", "text/markdown", {"prompt": "quantum market"})

        with pytest.raises(StorageError):
            await storage.get_report("quantum", "report.md")

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

    @pytest.mark.asyncio
    async def test_colliding_readable_suffixes_remain_isolated(self, storage):
        first_id = "11111111-2222-3333-4444-deadbeef0000"
        second_id = "99999999-8888-7777-6666-deadbeef9999"
        metadata = {"prompt": "Identical topic"}

        await storage.save_report(first_id, "report.md", b"first", "text/markdown", metadata)
        await storage.save_report(second_id, "report.md", b"second", "text/markdown", metadata)

        assert await storage.get_report(first_id, "report.md") == b"first"
        assert await storage.get_report(second_id, "report.md") == b"second"
        assert storage._get_job_dir(first_id) != storage._get_job_dir(second_id)

    @pytest.mark.asyncio
    async def test_authoritative_metadata_fields_cannot_be_overridden(self, storage):
        job_id = "trusted00-0000-1111-2222-333344445555"
        saved = await storage.save_report(
            job_id,
            "report.md",
            b"trusted",
            "text/markdown",
            {
                "prompt": "Metadata integrity",
                "job_id": "spoofed-job",
                "filename": "spoofed.txt",
                "content_type": "application/x-spoofed",
                "size_bytes": 999999,
                "created_at": "not-a-date",
            },
        )

        metadata = json.loads((Path(saved.url).parent / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["job_id"] == job_id
        assert metadata["filename"] == "report.md"
        assert metadata["content_type"] == "text/markdown"
        assert metadata["size_bytes"] == len(b"trusted")
        datetime.fromisoformat(metadata["created_at"])

    @pytest.mark.asyncio
    async def test_non_string_prompt_uses_legacy_directory_without_crashing(self, storage):
        job_id = "prompt00-0000-1111-2222-333344445555"
        await storage.save_report(
            job_id,
            "report.md",
            b"body",
            "text/markdown",
            {"prompt": {"unexpected": "object"}},
        )

        assert await storage.get_report(job_id, "report.md") == b"body"
        assert storage._get_job_dir(job_id).name == job_id

    @pytest.mark.asyncio
    async def test_invalid_metadata_does_not_replace_existing_report(self, storage):
        job_id = "atomic00-0000-1111-2222-333344445555"
        await storage.save_report(job_id, "report.md", b"original", "text/markdown")

        with pytest.raises(StorageError):
            await storage.save_report(
                job_id,
                "report.md",
                b"replacement",
                "text/markdown",
                {"not_json": object()},
            )

        assert await storage.get_report(job_id, "report.md") == b"original"

    @pytest.mark.asyncio
    async def test_list_all_reports_excludes_internal_metadata_and_includes_campaigns(self, storage):
        regular_id = "regular0-0000-1111-2222-333344445555"
        campaign_id = "campaign-freshcampaign"
        await storage.save_report(
            regular_id,
            "regular.md",
            b"regular",
            "text/markdown",
            {"prompt": "Regular report"},
        )
        await storage.save_report(
            campaign_id,
            "campaign.md",
            b"campaign",
            "text/markdown",
            {"prompt": "Campaign report"},
        )

        reports = await storage.list_reports()
        assert sorted((report.job_id, report.filename) for report in reports) == [
            (campaign_id, "campaign.md"),
            (regular_id, "regular.md"),
        ]


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

    @pytest.mark.asyncio
    async def test_cleanup_preserves_fresh_campaigns(self, storage):
        old_id = "old20000-0000-1111-2222-333344445555"
        campaign_id = "campaign-freshcleanup"
        await storage.save_report(old_id, "old.md", b"old", "text/markdown", {"prompt": "Old report"})
        await storage.save_report(
            campaign_id,
            "fresh.md",
            b"fresh",
            "text/markdown",
            {"prompt": "Fresh campaign"},
        )

        old_timestamp = time.time() - 40 * 86400
        old_report = storage._get_report_path(old_id, "old.md")
        os.utime(old_report, (old_timestamp, old_timestamp))
        os.utime(old_report.parent / "metadata.json", (old_timestamp, old_timestamp))

        assert await storage.cleanup_old_reports(days=30) == 1
        assert await storage.get_report(campaign_id, "fresh.md") == b"fresh"
        assert storage.campaigns_path.is_dir()

    @pytest.mark.asyncio
    async def test_cleanup_removes_only_old_reports_from_mixed_job(self, storage):
        job_id = "mixed000-0000-1111-2222-333344445555"
        await storage.save_report(job_id, "old.md", b"old", "text/markdown")
        await storage.save_report(job_id, "fresh.md", b"fresh", "text/markdown")
        old_timestamp = time.time() - 40 * 86400
        old_report = storage._get_report_path(job_id, "old.md")
        os.utime(old_report, (old_timestamp, old_timestamp))

        assert await storage.cleanup_old_reports(days=30) == 1
        assert not await storage.report_exists(job_id, "old.md")
        assert await storage.get_report(job_id, "fresh.md") == b"fresh"

    @pytest.mark.asyncio
    async def test_cleanup_rejects_negative_retention(self, storage):
        job_id = "safe0000-0000-1111-2222-333344445555"
        await storage.save_report(job_id, "fresh.md", b"fresh", "text/markdown")

        with pytest.raises(StorageError):
            await storage.cleanup_old_reports(days=-1)

        assert await storage.get_report(job_id, "fresh.md") == b"fresh"
