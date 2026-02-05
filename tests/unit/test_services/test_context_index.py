"""Tests for context index service (context discovery 6.1-6.3)."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.services.context_index import ContextIndex, SearchResult


@pytest.fixture
def temp_index_dir(tmp_path):
    """Create a temporary directory for index storage."""
    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    data_dir.mkdir()
    reports_dir.mkdir()
    return data_dir, reports_dir


@pytest.fixture
def context_index(temp_index_dir):
    """Create a ContextIndex with temp directories."""
    data_dir, reports_dir = temp_index_dir
    return ContextIndex(data_dir=data_dir, reports_dir=reports_dir)


@pytest.fixture
def sample_report(temp_index_dir):
    """Create a sample report for testing."""
    _, reports_dir = temp_index_dir

    report_dir = reports_dir / "test-job-123"
    report_dir.mkdir()

    # Create metadata.json
    metadata = {
        "job_id": "test-job-123",
        "prompt": "What are the best practices for Kubernetes deployment?",
        "model": "o4-mini-deep-research",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (report_dir / "metadata.json").write_text(json.dumps(metadata))

    # Create report.md
    report_content = """# Kubernetes Deployment Best Practices

## Introduction
This report covers best practices for deploying applications on Kubernetes.

## Key Findings
1. Use resource limits
2. Implement health checks
3. Use namespaces for isolation
"""
    (report_dir / "report.md").write_text(report_content)

    return report_dir, metadata


class TestContextIndexBasics:
    """Test basic ContextIndex functionality."""

    def test_init_creates_directories(self, temp_index_dir):
        """Test that initialization creates required directories."""
        data_dir, reports_dir = temp_index_dir
        index = ContextIndex(data_dir=data_dir, reports_dir=reports_dir)

        assert data_dir.exists()
        assert index.db_path.exists()

    def test_get_stats_empty(self, context_index):
        """Test stats on empty index."""
        stats = context_index.get_stats()

        assert stats["indexed_reports"] == 0
        assert stats["embedding_count"] == 0
        assert stats["oldest_report"] is None
        assert stats["newest_report"] is None

    def test_clear_empty_index(self, context_index):
        """Test clearing an empty index."""
        context_index.clear()
        stats = context_index.get_stats()

        assert stats["indexed_reports"] == 0


class TestContextDiscovery:
    """Test context discovery features (6.1, 6.2, 6.3)."""

    def test_get_report_by_job_id_not_found(self, context_index):
        """Test getting a non-existent report."""
        result = context_index.get_report_by_job_id("nonexistent")
        assert result is None

    def test_get_report_content_not_found(self, context_index):
        """Test getting content for non-existent report."""
        content = context_index.get_report_content("nonexistent")
        assert content is None

    def test_check_stale_context_unknown(self, context_index):
        """Test stale check for unknown job returns True."""
        is_stale = context_index.check_stale_context("unknown-job")
        assert is_stale is True

    @pytest.mark.asyncio
    async def test_find_related_empty_index(self, context_index):
        """Test finding related research on empty index."""
        related = await context_index.find_related("test query")
        assert related == []


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_to_dict(self):
        """Test SearchResult serialization."""
        result = SearchResult(
            report_id="abc123",
            job_id="job-456",
            prompt="Test prompt",
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            similarity=0.85,
            report_path=Path("/reports/job-456"),
            model="o4-mini-deep-research",
            summary="Test summary",
        )

        d = result.to_dict()

        assert d["report_id"] == "abc123"
        assert d["job_id"] == "job-456"
        assert d["prompt"] == "Test prompt"
        assert d["similarity"] == 0.85
        assert d["model"] == "o4-mini-deep-research"
        assert "2024-01-15" in d["created_at"]


class TestIndexingAndSearch:
    """Test report indexing and search with mocked embeddings."""

    @pytest.mark.asyncio
    async def test_index_reports_no_reports(self, context_index):
        """Test indexing when no reports exist."""
        count = await context_index.index_reports()
        assert count == 0

    @pytest.mark.asyncio
    async def test_keyword_search_fallback(self, context_index, sample_report):
        """Test keyword search when no embeddings available."""
        report_dir, metadata = sample_report

        # Manually insert into database (simulating indexing without embeddings)
        import sqlite3
        conn = sqlite3.connect(context_index.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "report-abc",
            metadata["job_id"],
            metadata["prompt"],
            metadata["model"],
            metadata["created_at"],
            str(report_dir),
            "Summary about Kubernetes",
            None,  # No embedding
            datetime.now(timezone.utc).isoformat(),
        ))

        # Insert into FTS table
        cursor.execute("""
            INSERT INTO reports_fts (report_id, prompt, summary)
            VALUES (?, ?, ?)
        """, ("report-abc", metadata["prompt"], "Summary about Kubernetes"))

        conn.commit()
        conn.close()

        # Search should use keyword fallback
        results = await context_index.search("Kubernetes", threshold=0.0)

        assert len(results) >= 1
        assert any("Kubernetes" in r.prompt for r in results)


class TestExplicitContext:
    """Test explicit context reuse (6.3)."""

    def test_get_report_by_prefix(self, context_index, sample_report):
        """Test getting report by job ID prefix."""
        report_dir, metadata = sample_report

        # Insert into database
        import sqlite3
        conn = sqlite3.connect(context_index.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "report-abc",
            metadata["job_id"],
            metadata["prompt"],
            metadata["model"],
            metadata["created_at"],
            str(report_dir),
            "Summary",
            None,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Test prefix match
        result = context_index.get_report_by_job_id("test-job")
        assert result is not None
        assert result.job_id == metadata["job_id"]

    def test_get_report_content(self, context_index, sample_report):
        """Test getting report content for context injection."""
        report_dir, metadata = sample_report

        # Insert into database
        import sqlite3
        conn = sqlite3.connect(context_index.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "report-abc",
            metadata["job_id"],
            metadata["prompt"],
            metadata["model"],
            metadata["created_at"],
            str(report_dir),
            "Summary",
            None,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Get content
        content = context_index.get_report_content(metadata["job_id"])

        assert content is not None
        assert "Kubernetes Deployment Best Practices" in content
        assert "Use resource limits" in content

    def test_get_report_content_truncation(self, context_index, sample_report):
        """Test content truncation for large reports."""
        report_dir, metadata = sample_report

        # Create a large report
        large_content = "# Test Report\n\n" + "Content paragraph.\n\n" * 500
        (report_dir / "report.md").write_text(large_content)

        # Insert into database
        import sqlite3
        conn = sqlite3.connect(context_index.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "report-abc",
            metadata["job_id"],
            metadata["prompt"],
            metadata["model"],
            metadata["created_at"],
            str(report_dir),
            "Summary",
            None,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Get content with max_chars limit
        content = context_index.get_report_content(metadata["job_id"], max_chars=1000)

        assert content is not None
        assert len(content) <= 1100  # Slightly over due to truncation message
        assert "truncated" in content.lower()

    def test_check_stale_context_fresh(self, context_index, sample_report):
        """Test that recent reports are not marked stale."""
        report_dir, metadata = sample_report

        # Insert with recent date
        import sqlite3
        conn = sqlite3.connect(context_index.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "report-abc",
            metadata["job_id"],
            metadata["prompt"],
            metadata["model"],
            datetime.now(timezone.utc).isoformat(),  # Fresh date
            str(report_dir),
            "Summary",
            None,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        is_stale = context_index.check_stale_context(metadata["job_id"])
        assert is_stale is False

    def test_check_stale_context_old(self, context_index, sample_report):
        """Test that old reports are marked stale."""
        report_dir, metadata = sample_report

        # Insert with old date
        import sqlite3
        conn = sqlite3.connect(context_index.db_path)
        cursor = conn.cursor()

        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        cursor.execute("""
            INSERT INTO reports
            (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "report-abc",
            metadata["job_id"],
            metadata["prompt"],
            metadata["model"],
            old_date,
            str(report_dir),
            "Summary",
            None,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        is_stale = context_index.check_stale_context(metadata["job_id"], max_age_days=30)
        assert is_stale is True
