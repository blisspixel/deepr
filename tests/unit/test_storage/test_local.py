"""
Unit tests for LocalStorage backend.

Tests human-readable naming, metadata generation, and legacy compatibility.
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from deepr.storage.local import LocalStorage


@pytest.mark.unit
class TestLocalStorage:
    """Test LocalStorage backend."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create temporary storage instance."""
        return LocalStorage(base_path=str(tmp_path / "reports"))

    @pytest.fixture
    def sample_metadata(self):
        """Sample metadata for testing."""
        return {
            "prompt": "Analyze AI code editor market as of October 2025",
            "model": "o3-deep-research",
            "status": "completed",
            "provider_job_id": "chatcmpl-test123",
        }

    # Test Human-Readable Directory Naming

    @pytest.mark.asyncio
    async def test_save_report_creates_readable_dirname(self, storage, sample_metadata):
        """Test that save_report creates human-readable directory name."""
        job_id = "ac2d48e1-51c7-4344-b556-143a358c0132"
        content = b"# Research Report\n\nTest content..."

        await storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=content,
            content_type="text/markdown",
            metadata=sample_metadata
        )

        # Find the created directory
        base_path = storage.base_path
        # Look for directory containing any part of the job_id
        short_id = job_id.split('-')[-1][:8]  # Last 8 chars
        dirs = [d for d in base_path.iterdir() if d.is_dir() and d.name != 'campaigns' and short_id in d.name]

        assert len(dirs) == 1, f"Should create exactly one directory, found: {[d.name for d in base_path.iterdir()]}"

        dir_name = dirs[0].name
        # Check format: YYYY-MM-DD_HHMM_slug_shortid
        assert dir_name.count("_") >= 3, "Should have timestamp, slug, and ID"
        assert dir_name[:4].isdigit(), "Should start with year"
        assert "ai-code-editor" in dir_name, "Should contain topic slug"
        assert short_id in dir_name, "Should contain short job ID"

    @pytest.mark.asyncio
    async def test_save_report_generates_metadata_json(self, storage, sample_metadata):
        """Test that metadata.json is created with report."""
        job_id = "test-job-001"
        content = b"Report content"

        await storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=content,
            content_type="text/markdown",
            metadata=sample_metadata
        )

        # Find metadata file
        job_dir = storage._get_job_dir(job_id)
        metadata_path = job_dir / "metadata.json"

        assert metadata_path.exists(), "Should create metadata.json"

        # Verify metadata content
        with open(metadata_path) as f:
            saved_metadata = json.load(f)

        assert saved_metadata["job_id"] == job_id
        assert saved_metadata["filename"] == "report.md"
        assert saved_metadata["prompt"] == sample_metadata["prompt"]
        assert saved_metadata["model"] == sample_metadata["model"]
        assert "created_at" in saved_metadata

    @pytest.mark.asyncio
    async def test_slug_generation_from_prompt(self, storage):
        """Test slug generation logic."""
        test_cases = [
            ("Analyze AI code editors", "analyze-ai-code-editors"),
            ("What should Ford do in EVs for 2026?", "what-should-ford-do-in-evs-for-2026"),
            ("Context injection best practices (Python)", "context-injection-best-practices-python"),
            ("A" * 100, "a" * 40),  # Should truncate to 40 chars
            ("Test!@#$%^&*()_+ prompt", "test-prompt"),  # Should remove special chars
        ]

        for prompt, expected_slug in test_cases:
            slug = storage._create_readable_dirname("test-id", prompt)
            # Slug should be in the directory name
            assert expected_slug in slug or expected_slug[:30] in slug, \
                f"Expected '{expected_slug}' in slug '{slug}'"

    # Test Legacy Compatibility

    @pytest.mark.asyncio
    async def test_get_job_dir_finds_legacy_uuid(self, storage):
        """Test that _get_job_dir can find legacy UUID-only directories."""
        # Create legacy directory (UUID only)
        job_id = "legacy-uuid-1234-5678"
        legacy_dir = storage.base_path / job_id
        legacy_dir.mkdir(parents=True)

        # Should find the legacy directory
        found_dir = storage._get_job_dir(job_id)
        assert found_dir == legacy_dir

    @pytest.mark.asyncio
    async def test_get_job_dir_finds_human_readable(self, storage, sample_metadata):
        """Test that _get_job_dir can find human-readable directories."""
        # Create a report with human-readable name
        job_id = "test-job-readable"
        await storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=b"test",
            content_type="text/markdown",
            metadata=sample_metadata
        )

        # Should find by job_id even though directory name is different
        found_dir = storage._get_job_dir(job_id)
        assert found_dir.exists()
        # Directory name should contain short_id from job_id
        short_id = job_id.split('-')[-1][:8] if '-' in job_id else job_id[:8]
        assert short_id in found_dir.name or "readable" in found_dir.name

    @pytest.mark.asyncio
    async def test_get_report_works_with_both_formats(self, storage, sample_metadata):
        """Test get_report works with both legacy and new naming."""
        content = b"Test report content"

        # Test 1: Legacy format (direct job_id as directory name)
        legacy_id = "legacy-direct-id"
        legacy_dir = storage.base_path / legacy_id
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "report.md").write_bytes(content)

        retrieved = await storage.get_report(legacy_id, "report.md")
        assert retrieved == content

        # Test 2: New format (human-readable)
        new_id = "new-readable-id"
        await storage.save_report(
            job_id=new_id,
            filename="report.md",
            content=content,
            content_type="text/markdown",
            metadata=sample_metadata
        )

        retrieved = await storage.get_report(new_id, "report.md")
        assert retrieved == content

    # Test Campaign Handling

    @pytest.mark.asyncio
    async def test_campaign_uses_campaigns_subfolder(self, storage):
        """Test that campaigns are saved in campaigns/ subfolder."""
        campaign_id = "campaign-test12345"
        metadata = {
            "prompt": "Multi-phase research campaign",
            "type": "campaign",
            "task_count": 3,
        }

        await storage.save_report(
            job_id=campaign_id,
            filename="campaign_results.json",
            content=b'{"test": "data"}',
            content_type="application/json",
            metadata=metadata
        )

        # Should be in campaigns folder
        campaigns_dir = storage.campaigns_path
        assert campaigns_dir.exists()

        campaign_dirs = [d for d in campaigns_dir.iterdir() if d.is_dir()]
        assert len(campaign_dirs) > 0, "Should create campaign directory"
        # Campaign ID or short version should be in directory name
        short_id = campaign_id.replace('campaign-', '')[:12]
        assert any(campaign_id in d.name or short_id in d.name for d in campaign_dirs)

    # Test Metadata Structure

    @pytest.mark.asyncio
    async def test_metadata_json_structure(self, storage, sample_metadata):
        """Test that metadata.json has expected structure."""
        job_id = "metadata-test-job"
        await storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=b"content",
            content_type="text/markdown",
            metadata=sample_metadata
        )

        job_dir = storage._get_job_dir(job_id)
        metadata_path = job_dir / "metadata.json"

        with open(metadata_path) as f:
            metadata = json.load(f)

        # Required fields
        assert "job_id" in metadata
        assert "created_at" in metadata
        assert "filename" in metadata
        assert "content_type" in metadata
        assert "size_bytes" in metadata

        # Passed metadata preserved
        assert metadata["prompt"] == sample_metadata["prompt"]
        assert metadata["model"] == sample_metadata["model"]
        assert metadata["status"] == sample_metadata["status"]

        # created_at is valid ISO format
        datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))

    # Test Report Listing

    @pytest.mark.asyncio
    async def test_list_reports_includes_both_formats(self, storage, sample_metadata):
        """Test that list_reports finds both legacy and new format reports."""
        # Create legacy format
        legacy_id = "legacy-list-test"
        legacy_dir = storage.base_path / legacy_id
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "report.md").write_bytes(b"legacy content")

        # Create new format
        new_id = "new-list-test"
        await storage.save_report(
            job_id=new_id,
            filename="report.md",
            content=b"new content",
            content_type="text/markdown",
            metadata=sample_metadata
        )

        # List all reports
        reports = await storage.list_reports()

        # Should find both (job_id is the directory name for list_reports)
        job_ids = [r.job_id for r in reports]
        # Legacy should match exactly
        assert any(legacy_id == jid for jid in job_ids), f"Should find legacy report. Got: {job_ids}"
        # New format: directory name contains short_id or full id
        new_short_id = new_id.split('-')[-1][:8] if '-' in new_id else new_id[:8]
        assert any(new_id in jid or new_short_id in jid for jid in job_ids), f"Should find new format report. Got: {job_ids}"

    # Test Error Handling

    @pytest.mark.asyncio
    async def test_get_report_nonexistent_raises_error(self, storage):
        """Test that get_report raises error for nonexistent report."""
        from deepr.storage.base import StorageError

        with pytest.raises(StorageError):
            await storage.get_report("nonexistent-job", "report.md")

    @pytest.mark.asyncio
    async def test_save_without_metadata_still_works(self, storage):
        """Test that save_report works even without metadata."""
        job_id = "no-metadata-job"

        # Should not crash without metadata
        await storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=b"content",
            content_type="text/markdown",
            metadata=None
        )

        # Report should be saved (as legacy format since no prompt for slug)
        content = await storage.get_report(job_id, "report.md")
        assert content == b"content"

    # Test Directory Creation

    @pytest.mark.asyncio
    async def test_campaigns_folder_created_on_init(self, tmp_path):
        """Test that campaigns folder is created on initialization."""
        storage = LocalStorage(base_path=str(tmp_path / "test_reports"))

        assert storage.campaigns_path.exists()
        assert storage.campaigns_path.is_dir()
        assert storage.campaigns_path.name == "campaigns"


@pytest.mark.unit
class TestReadableDirname:
    """Test _create_readable_dirname edge cases."""

    @pytest.fixture
    def storage(self, tmp_path):
        return LocalStorage(base_path=str(tmp_path))

    def test_handles_empty_prompt(self, storage):
        """Test handling of empty prompt."""
        dirname = storage._create_readable_dirname("test-id", "")
        assert dirname  # Should still create valid dirname
        # Should use default "research" slug when prompt is empty
        assert "research" in dirname

    def test_handles_unicode_prompt(self, storage):
        """Test handling of unicode characters."""
        prompt = "Analyze 日本 market trends"
        dirname = storage._create_readable_dirname("test-id", prompt)
        # Should strip unicode, keep ascii
        assert "analyze" in dirname
        assert "market" in dirname

    def test_short_id_extraction_uuid(self, storage):
        """Test short ID extraction from UUID."""
        uuid = "ac2d48e1-51c7-4344-b556-143a358c0132"
        dirname = storage._create_readable_dirname(uuid, "test")
        # Should use last 8 chars
        assert "358c0132" in dirname or "143a358c" in dirname

    def test_short_id_extraction_campaign(self, storage):
        """Test short ID extraction from campaign ID."""
        campaign_id = "campaign-86285e7bcd24"
        dirname = storage._create_readable_dirname(campaign_id, "test", is_campaign=True)
        # Should use first 12 chars after "campaign-"
        assert "86285e7bcd24" in dirname

    def test_timestamp_format(self, storage):
        """Test that timestamp is in expected format."""
        dirname = storage._create_readable_dirname("test-id", "test prompt")
        # Should start with YYYY-MM-DD_HHMM
        parts = dirname.split("_")
        assert len(parts) >= 3
        # First part should be date
        assert len(parts[0]) == 10  # YYYY-MM-DD
        assert parts[0].count("-") == 2
        # Second part should be time
        assert len(parts[1]) == 4  # HHMM
        assert parts[1].isdigit()
