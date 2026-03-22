"""Tests for structured corpus import into expert knowledge."""

import json
from unittest.mock import MagicMock

import pytest

from deepr.experts.corpus import (
    _json_to_markdown,
    _jsonl_to_markdown,
    import_structured_bundle,
)


@pytest.fixture
def tmp_expert_dir(tmp_path):
    """Create a mock expert store and docs directory."""
    expert_dir = tmp_path / "experts" / "test-expert"
    expert_dir.mkdir(parents=True)
    docs_dir = expert_dir / "documents"
    docs_dir.mkdir()
    return expert_dir


@pytest.fixture
def mock_store(tmp_expert_dir):
    """Create a mock ExpertStore."""
    store = MagicMock()

    profile = MagicMock()
    profile.name = "test-expert"
    profile.total_documents = 3
    profile.source_files = ["existing.md"]
    profile.last_knowledge_refresh = None

    store.load.return_value = profile
    store.get_documents_dir.return_value = tmp_expert_dir / "documents"
    store.get_knowledge_dir.return_value = tmp_expert_dir / "knowledge"
    return store


class TestJsonToMarkdown:
    def test_dict_conversion(self):
        data = json.dumps({"title": "My Report", "summary": "This is a test"})
        md = _json_to_markdown(data, "report.json")
        assert "# report.json" in md
        assert "## title" in md
        assert "This is a test" in md

    def test_list_conversion(self):
        data = json.dumps([{"name": "A"}, {"name": "B"}])
        md = _json_to_markdown(data, "items.json")
        assert "## Entry 1" in md
        assert "## Entry 2" in md

    def test_invalid_json_fallback(self):
        md = _json_to_markdown("not json at all", "bad.json")
        assert "```json" in md
        assert "not json at all" in md


class TestJsonlToMarkdown:
    def test_multi_line(self):
        content = '{"key": "val1"}\n{"key": "val2"}\n'
        md = _jsonl_to_markdown(content, "data.jsonl")
        assert "## Entry 1" in md
        assert "## Entry 2" in md
        assert "val1" in md
        assert "val2" in md

    def test_skips_invalid_lines(self):
        content = '{"ok": true}\nnot json\n{"ok": false}\n'
        md = _jsonl_to_markdown(content, "mixed.jsonl")
        assert "## Entry 1" in md
        assert "## Entry 2" in md


class TestImportStructuredBundle:
    @pytest.mark.asyncio
    async def test_import_md_files(self, tmp_path, mock_store):
        """Import a directory of markdown files."""
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        (bundle / "report1.md").write_text("# Report 1\n\nSome findings.", encoding="utf-8")
        (bundle / "report2.md").write_text("# Report 2\n\nMore findings.", encoding="utf-8")

        result = await import_structured_bundle("test-expert", bundle, mock_store)

        assert result["documents_imported"] == 2
        assert len(result["files"]) == 2
        mock_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_json_file(self, tmp_path, mock_store):
        """Import a single JSON file — converts to markdown."""
        data = {"title": "Analysis", "findings": ["Finding 1", "Finding 2"]}
        json_file = tmp_path / "analysis.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = await import_structured_bundle("test-expert", json_file, mock_store)

        assert result["documents_imported"] == 1
        # Check the file was converted to markdown
        docs_dir = mock_store.get_documents_dir.return_value
        imported = list(docs_dir.glob("*.md"))
        assert len(imported) >= 1

    @pytest.mark.asyncio
    async def test_import_jsonl_file(self, tmp_path, mock_store):
        """Import a JSONL file."""
        content = '{"topic": "AI Safety"}\n{"topic": "ML Ops"}\n'
        jsonl_file = tmp_path / "data.jsonl"
        jsonl_file.write_text(content, encoding="utf-8")

        result = await import_structured_bundle("test-expert", jsonl_file, mock_store)
        assert result["documents_imported"] == 1

    @pytest.mark.asyncio
    async def test_auto_detect_gaps(self, tmp_path, mock_store):
        """Import should detect questions as potential knowledge gaps."""
        (tmp_path / "report.md").write_text(
            "# Report\n\n"
            "What are the long-term implications of quantum computing on cryptography?\n"
            "This remains an open question.\n"
            "Short?\n",  # Too short, should be skipped
            encoding="utf-8",
        )

        result = await import_structured_bundle("test-expert", tmp_path / "report.md", mock_store)

        assert len(result["gaps_detected"]) == 1
        assert "quantum" in result["gaps_detected"][0]["question"].lower()

    @pytest.mark.asyncio
    async def test_import_nonexistent_expert(self, tmp_path):
        """Should raise if expert doesn't exist."""
        store = MagicMock()
        store.load.return_value = None

        (tmp_path / "file.md").write_text("content", encoding="utf-8")

        with pytest.raises(ValueError, match="Expert not found"):
            await import_structured_bundle("nonexistent", tmp_path / "file.md", store)

    @pytest.mark.asyncio
    async def test_import_empty_bundle(self, tmp_path, mock_store):
        """Should raise if no importable files found."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(ValueError, match="No importable files"):
            await import_structured_bundle("test-expert", empty_dir, mock_store)

    @pytest.mark.asyncio
    async def test_citation_counting(self, tmp_path, mock_store):
        """Should count URLs as citations."""
        (tmp_path / "report.md").write_text(
            "See https://example.com and http://other.com for details.",
            encoding="utf-8",
        )

        result = await import_structured_bundle("test-expert", tmp_path / "report.md", mock_store)
        assert result["citations_mapped"] == 2

    @pytest.mark.asyncio
    async def test_no_overwrite_existing(self, tmp_path, mock_store):
        """Should not overwrite existing documents — appends counter."""
        docs_dir = mock_store.get_documents_dir.return_value
        (docs_dir / "report.md").write_text("existing", encoding="utf-8")

        (tmp_path / "report.md").write_text("new content", encoding="utf-8")

        result = await import_structured_bundle("test-expert", tmp_path / "report.md", mock_store)
        assert result["documents_imported"] == 1

        # Should have created report_1.md instead of overwriting
        assert (docs_dir / "report_1.md").exists()
