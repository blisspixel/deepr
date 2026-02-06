"""Unit tests for the Corpus module - no API calls.

Tests the expert consciousness export/import functionality including
corpus manifest, validation, and file operations.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.corpus import CorpusManifest, _generate_readme, export_corpus, import_corpus, validate_corpus


class TestCorpusManifest:
    """Test CorpusManifest dataclass."""

    def test_create_basic_manifest(self):
        """Test creating a basic manifest."""
        manifest = CorpusManifest(name="test-corpus")
        assert manifest.name == "test-corpus"
        assert manifest.version == "1.0"
        assert manifest.document_count == 0
        assert manifest.files == []

    def test_create_full_manifest(self):
        """Test creating a manifest with all fields."""
        manifest = CorpusManifest(
            name="full-corpus",
            version="2.0",
            source_expert="Test Expert",
            domain="Testing",
            description="A test corpus",
            document_count=5,
            belief_count=3,
            gap_count=2,
            files=["doc1.md", "doc2.md"],
        )
        assert manifest.name == "full-corpus"
        assert manifest.version == "2.0"
        assert manifest.document_count == 5
        assert len(manifest.files) == 2

    def test_manifest_to_dict(self):
        """Test manifest serialization to dict."""
        manifest = CorpusManifest(name="serialize-test", source_expert="Expert", document_count=3)
        data = manifest.to_dict()
        assert data["name"] == "serialize-test"
        assert data["source_expert"] == "Expert"
        assert data["document_count"] == 3
        assert "created_at" in data

    def test_manifest_from_dict(self):
        """Test manifest deserialization from dict."""
        data = {
            "name": "restored-corpus",
            "version": "1.0",
            "created_at": "2025-01-30T12:00:00",
            "source_expert": "Restored Expert",
            "domain": "Restoration",
            "description": "Restored description",
            "document_count": 10,
            "belief_count": 5,
            "gap_count": 2,
            "files": ["a.md", "b.md"],
        }
        manifest = CorpusManifest.from_dict(data)
        assert manifest.name == "restored-corpus"
        assert manifest.document_count == 10
        assert len(manifest.files) == 2

    def test_manifest_save_and_load(self):
        """Test manifest persistence to file."""
        manifest = CorpusManifest(name="persistent-corpus", source_expert="Persistent Expert", document_count=7)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            manifest.save(path)

            loaded = CorpusManifest.load(path)
            assert loaded.name == manifest.name
            assert loaded.source_expert == manifest.source_expert
            assert loaded.document_count == manifest.document_count

    def test_manifest_roundtrip(self):
        """Test manifest serialization roundtrip."""
        original = CorpusManifest(
            name="roundtrip-test",
            version="1.5",
            source_expert="Roundtrip Expert",
            domain="Testing",
            description="Testing roundtrip",
            document_count=15,
            belief_count=8,
            gap_count=3,
            files=["doc1.md", "doc2.md", "doc3.md"],
        )
        data = original.to_dict()
        restored = CorpusManifest.from_dict(data)

        assert restored.name == original.name
        assert restored.version == original.version
        assert restored.document_count == original.document_count
        assert restored.files == original.files


class TestValidateCorpus:
    """Test corpus validation."""

    def test_validate_valid_corpus(self):
        """Test validating a valid corpus structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)

            # Create valid structure
            manifest = CorpusManifest(name="valid-corpus", document_count=1)
            manifest.save(corpus_dir / "manifest.json")

            docs_dir = corpus_dir / "documents"
            docs_dir.mkdir()
            (docs_dir / "test.md").write_text("# Test Document")

            (corpus_dir / "worldview.json").write_text("{}")

            result = validate_corpus(corpus_dir)
            assert result["valid"] is True
            assert len(result["errors"]) == 0
            assert result["manifest"] is not None

    def test_validate_missing_manifest(self):
        """Test validation fails without manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)

            result = validate_corpus(corpus_dir)
            assert result["valid"] is False
            assert "manifest.json not found" in result["errors"]

    def test_validate_missing_documents_dir(self):
        """Test validation fails without documents directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)

            manifest = CorpusManifest(name="test")
            manifest.save(corpus_dir / "manifest.json")

            result = validate_corpus(corpus_dir)
            assert result["valid"] is False
            assert "documents/ directory not found" in result["errors"]

    def test_validate_empty_documents_dir(self):
        """Test validation fails with empty documents directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)

            manifest = CorpusManifest(name="test")
            manifest.save(corpus_dir / "manifest.json")

            docs_dir = corpus_dir / "documents"
            docs_dir.mkdir()

            result = validate_corpus(corpus_dir)
            assert result["valid"] is False
            assert "No .md files in documents/ directory" in result["errors"]

    def test_validate_missing_worldview(self):
        """Test validation warns about missing worldview."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)

            manifest = CorpusManifest(name="test")
            manifest.save(corpus_dir / "manifest.json")

            docs_dir = corpus_dir / "documents"
            docs_dir.mkdir()
            (docs_dir / "test.md").write_text("# Test")

            result = validate_corpus(corpus_dir)
            # Should have warning about worldview
            assert any("worldview.json not found" in e for e in result["errors"])

    def test_validate_invalid_manifest_json(self):
        """Test validation fails with invalid manifest JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)

            # Write invalid JSON
            (corpus_dir / "manifest.json").write_text("not valid json")

            result = validate_corpus(corpus_dir)
            assert result["valid"] is False
            assert any("Invalid manifest.json" in e for e in result["errors"])


class TestGenerateReadme:
    """Test README generation."""

    def test_generate_readme_basic(self):
        """Test generating basic README."""
        profile = MagicMock()
        profile.name = "Test Expert"
        profile.domain = "Testing"
        profile.description = "A test expert"

        readme = _generate_readme(profile, None, 5)

        assert "# Test Expert" in readme
        assert "Testing" in readme
        assert "Documents**: 5" in readme

    def test_generate_readme_with_worldview(self):
        """Test generating README with worldview."""
        from deepr.experts.synthesis import Belief, KnowledgeGap, Worldview

        profile = MagicMock()
        profile.name = "Expert With Worldview"
        profile.domain = "Knowledge"
        profile.description = "Expert with beliefs"

        now = datetime.utcnow()
        worldview = Worldview(
            expert_name="Expert",
            domain="Knowledge",
            beliefs=[
                Belief(
                    topic="Testing",
                    statement="Testing is important",
                    confidence=0.95,
                    evidence=["test.md"],
                    formed_at=now,
                    last_updated=now,
                )
            ],
            knowledge_gaps=[
                KnowledgeGap(topic="Unknown Area", questions=["What is this?"], priority=4, identified_at=now)
            ],
        )

        readme = _generate_readme(profile, worldview, 3)

        assert "Expert With Worldview" in readme
        assert "Beliefs**: 1" in readme
        assert "Knowledge Gaps**: 1" in readme
        assert "Testing is important" in readme
        assert "95%" in readme
        assert "Unknown Area" in readme

    def test_generate_readme_import_command(self):
        """Test README includes import command."""
        profile = MagicMock()
        profile.name = "Import Test"
        profile.domain = "Testing"
        profile.description = ""

        readme = _generate_readme(profile, None, 1)

        assert "deepr expert import" in readme
        assert "import-test" in readme  # lowercase, hyphenated


class TestExportCorpus:
    """Test corpus export functionality."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock ExpertStore."""
        store = MagicMock()
        return store

    @pytest.mark.asyncio
    async def test_export_nonexistent_expert(self, mock_store):
        """Test export fails for nonexistent expert."""
        mock_store.load.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Expert not found"):
                await export_corpus(expert_name="Nonexistent", output_dir=Path(tmpdir), store=mock_store)

    @pytest.mark.asyncio
    async def test_export_creates_directory_structure(self, mock_store):
        """Test export creates proper directory structure."""
        # Setup mock profile
        profile = MagicMock()
        profile.name = "Export Test"
        profile.description = "Test description"
        profile.domain = "Testing"
        profile.provider = "openai"
        profile.model = "gpt-5"
        profile.created_at = datetime.utcnow()
        profile.total_documents = 2
        profile.conversations = 5
        profile.research_triggered = 1
        profile.total_research_cost = 0.50

        mock_store.load.return_value = profile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock knowledge and docs directories
            knowledge_dir = Path(tmpdir) / "knowledge"
            docs_dir = Path(tmpdir) / "docs"
            knowledge_dir.mkdir()
            docs_dir.mkdir()

            # Create test documents
            (docs_dir / "doc1.md").write_text("# Document 1")
            (docs_dir / "doc2.md").write_text("# Document 2")

            mock_store.get_knowledge_dir.return_value = knowledge_dir
            mock_store.get_documents_dir.return_value = docs_dir

            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            manifest = await export_corpus(expert_name="Export Test", output_dir=output_dir, store=mock_store)

            # Check manifest
            assert manifest.name == "export-test"
            assert manifest.source_expert == "Export Test"
            assert manifest.document_count == 2

            # Check directory structure
            corpus_dir = output_dir / "export-test"
            assert corpus_dir.exists()
            assert (corpus_dir / "manifest.json").exists()
            assert (corpus_dir / "metadata.json").exists()
            assert (corpus_dir / "README.md").exists()
            assert (corpus_dir / "documents").exists()
            assert (corpus_dir / "documents" / "doc1.md").exists()


class TestImportCorpus:
    """Test corpus import functionality."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock ExpertStore."""
        store = MagicMock()
        store.load.return_value = None  # Expert doesn't exist
        return store

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        provider = MagicMock()
        provider.create_vector_store = AsyncMock(return_value=MagicMock(id="vs_123"))
        provider.upload_document = AsyncMock(return_value="file_123")
        provider.add_file_to_vector_store = AsyncMock()
        provider.wait_for_vector_store = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_import_invalid_corpus(self, mock_store, mock_provider):
        """Test import fails for invalid corpus."""
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)
            # No manifest.json

            with pytest.raises(ValueError, match="Invalid corpus"):
                await import_corpus(
                    new_expert_name="New Expert", corpus_dir=corpus_dir, store=mock_store, provider=mock_provider
                )

    @pytest.mark.asyncio
    async def test_import_existing_expert(self, mock_store, mock_provider):
        """Test import fails if expert already exists."""
        mock_store.load.return_value = MagicMock()  # Expert exists

        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_dir = Path(tmpdir)
            manifest = CorpusManifest(name="test")
            manifest.save(corpus_dir / "manifest.json")

            with pytest.raises(ValueError, match="Expert already exists"):
                await import_corpus(
                    new_expert_name="Existing Expert", corpus_dir=corpus_dir, store=mock_store, provider=mock_provider
                )


class TestCorpusEdgeCases:
    """Test edge cases in corpus operations."""

    def test_manifest_empty_files_list(self):
        """Test manifest with empty files list."""
        manifest = CorpusManifest(name="empty-files", files=[])
        data = manifest.to_dict()
        assert data["files"] == []

        restored = CorpusManifest.from_dict(data)
        assert restored.files == []

    def test_manifest_special_characters_in_name(self):
        """Test manifest with special characters in name."""
        manifest = CorpusManifest(name="test-corpus_v2.0", source_expert="Test Expert (v2)")
        data = manifest.to_dict()
        restored = CorpusManifest.from_dict(data)
        assert restored.name == "test-corpus_v2.0"

    def test_validate_corpus_nonexistent_dir(self):
        """Test validation of nonexistent directory."""
        result = validate_corpus(Path("/nonexistent/path"))
        assert result["valid"] is False

    def test_manifest_created_at_auto_generated(self):
        """Test that created_at is auto-generated."""
        manifest = CorpusManifest(name="auto-date")
        assert manifest.created_at is not None
        # Should be a valid ISO format string
        datetime.fromisoformat(manifest.created_at)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
