"""Expanded tests for LocalStorage operations."""

import pytest
from deepr.storage.local import LocalStorage
from deepr.storage.base import StorageError


@pytest.mark.asyncio
class TestLocalStorageExpanded:
    """Additional tests for LocalStorage backend."""

    @pytest.fixture
    def storage(self, tmp_path):
        return LocalStorage(base_path=str(tmp_path / "reports"))

    async def test_save_and_retrieve_roundtrip(self, storage):
        """Content is preserved through save/retrieve cycle."""
        content = b"# Full Research Report\n\nContent here."
        await storage.save_report("rt-job", "report.md", content, "text/markdown")
        retrieved = await storage.get_report("rt-job", "report.md")
        assert retrieved == content

    async def test_save_creates_directory(self, storage):
        """save_report creates job directory if missing."""
        await storage.save_report("new-dir-job", "file.txt", b"data", "text/plain")
        assert (storage._get_job_dir("new-dir-job")).exists()

    async def test_list_reports_for_job(self, storage):
        """list_reports returns files for a specific job."""
        await storage.save_report("list-job", "report.md", b"md", "text/markdown")
        await storage.save_report("list-job", "report.json", b"{}", "application/json")
        reports = await storage.list_reports("list-job")
        names = [r.filename for r in reports]
        assert "report.md" in names
        assert "report.json" in names

    async def test_delete_specific_file(self, storage):
        """delete_report removes a specific file."""
        await storage.save_report("del-job", "report.md", b"data", "text/markdown")
        result = await storage.delete_report("del-job", "report.md")
        assert result is True
        with pytest.raises(StorageError):
            await storage.get_report("del-job", "report.md")

    async def test_delete_entire_job(self, storage):
        """delete_report without filename removes entire job directory."""
        await storage.save_report("del-all-job", "file1.txt", b"a", "text/plain")
        await storage.save_report("del-all-job", "file2.txt", b"b", "text/plain")
        result = await storage.delete_report("del-all-job")
        assert result is True

    async def test_delete_nonexistent_returns_false(self, storage):
        """Deleting nonexistent file returns False."""
        result = await storage.delete_report("no-such-job", "no-file.txt")
        assert result is False

    async def test_report_exists_true(self, storage):
        """report_exists returns True for existing report."""
        await storage.save_report("exists-job", "report.md", b"data", "text/markdown")
        assert await storage.report_exists("exists-job", "report.md") is True

    async def test_report_exists_false(self, storage):
        """report_exists returns False for missing report."""
        assert await storage.report_exists("no-job", "no-file.md") is False

    async def test_binary_content_types(self, storage):
        """Binary content (docx, pdf) saved correctly."""
        binary_data = bytes(range(256)) * 10  # 2560 bytes of binary data
        await storage.save_report("bin-job", "report.docx", binary_data, "application/vnd.openxmlformats")
        retrieved = await storage.get_report("bin-job", "report.docx")
        assert retrieved == binary_data

    async def test_large_file_save_retrieve(self, storage):
        """Large files (>1MB) save and retrieve correctly."""
        large_content = b"x" * (1024 * 1024 + 100)  # ~1MB
        await storage.save_report("large-job", "big.md", large_content, "text/markdown")
        retrieved = await storage.get_report("large-job", "big.md")
        assert len(retrieved) == len(large_content)

    async def test_report_metadata_returned(self, storage):
        """save_report returns ReportMetadata with correct fields."""
        meta = await storage.save_report("meta-job", "report.md", b"content", "text/markdown")
        assert meta.job_id == "meta-job"
        assert meta.filename == "report.md"
        assert meta.format == "md"
        assert meta.size_bytes == len(b"content")
        assert meta.content_type == "text/markdown"

    async def test_get_report_url(self, storage):
        """get_report_url returns file:// URL for existing report."""
        await storage.save_report("url-job", "report.md", b"data", "text/markdown")
        url = await storage.get_report_url("url-job", "report.md")
        assert url.startswith("file://")

    async def test_get_report_url_nonexistent_raises(self, storage):
        """get_report_url raises for nonexistent report."""
        with pytest.raises(StorageError):
            await storage.get_report_url("no-job", "no-file.md")
