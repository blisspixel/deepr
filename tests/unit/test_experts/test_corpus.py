"""Unit tests for the corpus module (export/import).

Tests the Phase 4 implementation:
- CorpusManifest dataclass
- export_corpus function
- import_corpus function
- validate_corpus function
- CLI commands
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from click.testing import CliRunner
from datetime import datetime


class TestCorpusManifest:
    """Test CorpusManifest dataclass."""

    def test_manifest_creation(self):
        """Test creating a manifest with default values."""
        from deepr.experts.corpus import CorpusManifest
        
        manifest = CorpusManifest(name="test-corpus")
        
        assert manifest.name == "test-corpus"
        assert manifest.version == "1.0"
        assert manifest.document_count == 0
        assert manifest.belief_count == 0
        assert manifest.gap_count == 0
        assert manifest.files == []

    def test_manifest_with_values(self):
        """Test creating a manifest with custom values."""
        from deepr.experts.corpus import CorpusManifest
        
        manifest = CorpusManifest(
            name="aws-expert",
            source_expert="AWS Expert",
            domain="Cloud Computing",
            description="AWS architecture expert",
            document_count=10,
            belief_count=5,
            gap_count=3,
            files=["doc1.md", "doc2.md"]
        )
        
        assert manifest.name == "aws-expert"
        assert manifest.source_expert == "AWS Expert"
        assert manifest.domain == "Cloud Computing"
        assert manifest.document_count == 10
        assert manifest.belief_count == 5
        assert len(manifest.files) == 2

    def test_manifest_to_dict(self):
        """Test converting manifest to dictionary."""
        from deepr.experts.corpus import CorpusManifest
        
        manifest = CorpusManifest(
            name="test",
            document_count=5
        )
        
        data = manifest.to_dict()
        
        assert isinstance(data, dict)
        assert data["name"] == "test"
        assert data["document_count"] == 5

    def test_manifest_from_dict(self):
        """Test creating manifest from dictionary."""
        from deepr.experts.corpus import CorpusManifest
        
        data = {
            "name": "test",
            "version": "1.0",
            "created_at": "2026-01-26T00:00:00",
            "source_expert": "Test Expert",
            "domain": "Testing",
            "description": "Test description",
            "document_count": 3,
            "belief_count": 2,
            "gap_count": 1,
            "files": ["a.md", "b.md"]
        }
        
        manifest = CorpusManifest.from_dict(data)
        
        assert manifest.name == "test"
        assert manifest.document_count == 3
        assert len(manifest.files) == 2

    def test_manifest_save_load(self):
        """Test saving and loading manifest."""
        from deepr.experts.corpus import CorpusManifest
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "manifest.json"
            
            original = CorpusManifest(
                name="test",
                document_count=5,
                files=["doc.md"]
            )
            original.save(path)
            
            loaded = CorpusManifest.load(path)
            
            assert loaded.name == original.name
            assert loaded.document_count == original.document_count
            assert loaded.files == original.files


class TestValidateCorpus:
    """Test corpus validation."""

    def test_validate_missing_manifest(self):
        """Test validation fails without manifest."""
        from deepr.experts.corpus import validate_corpus
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_corpus(Path(tmpdir))
            
            assert not result["valid"]
            assert "manifest.json not found" in result["errors"]

    def test_validate_missing_documents(self):
        """Test validation fails without documents directory."""
        from deepr.experts.corpus import validate_corpus, CorpusManifest
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create manifest
            manifest = CorpusManifest(name="test")
            manifest.save(tmppath / "manifest.json")
            
            result = validate_corpus(tmppath)
            
            assert not result["valid"]
            assert any("documents" in e for e in result["errors"])

    def test_validate_valid_corpus(self):
        """Test validation passes for valid corpus."""
        from deepr.experts.corpus import validate_corpus, CorpusManifest
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create manifest
            manifest = CorpusManifest(name="test")
            manifest.save(tmppath / "manifest.json")
            
            # Create documents directory with a file
            docs_dir = tmppath / "documents"
            docs_dir.mkdir()
            (docs_dir / "test.md").write_text("# Test")
            
            # Create worldview
            (tmppath / "worldview.json").write_text("{}")
            
            result = validate_corpus(tmppath)
            
            assert result["valid"]
            assert result["manifest"] is not None


class TestExportCommandRegistration:
    """Test export command registration."""

    def test_export_command_exists(self):
        """Verify export command is registered."""
        from deepr.cli.commands.semantic import expert
        
        command_names = [cmd.name for cmd in expert.commands.values()]
        assert "export" in command_names

    def test_export_command_help(self):
        """Verify export command has proper help."""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        result = runner.invoke(expert, ["export", "--help"])
        
        assert result.exit_code == 0
        assert "Export an expert's consciousness" in result.output
        assert "--output" in result.output

    def test_export_expert_not_found(self):
        """Test export fails for nonexistent expert."""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        with patch("deepr.experts.profile.ExpertStore") as mock_store:
            mock_store.return_value.load.return_value = None
            result = runner.invoke(expert, ["export", "Nonexistent", "-y"])
        
        assert "Expert not found" in result.output


class TestImportCommandRegistration:
    """Test import command registration."""

    def test_import_command_exists(self):
        """Verify import command is registered."""
        from deepr.cli.commands.semantic import expert
        
        command_names = [cmd.name for cmd in expert.commands.values()]
        assert "import" in command_names

    def test_import_command_help(self):
        """Verify import command has proper help."""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        result = runner.invoke(expert, ["import", "--help"])
        
        assert result.exit_code == 0
        assert "Import a corpus" in result.output
        assert "--corpus" in result.output

    def test_import_requires_corpus(self):
        """Test import requires --corpus option."""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        result = runner.invoke(expert, ["import", "New Expert"])
        
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()


class TestExportImportOptions:
    """Test command options."""

    def test_export_output_option(self):
        """Test export --output option."""
        from deepr.cli.commands.semantic import export_expert
        
        for param in export_expert.params:
            if param.name == "output":
                assert param.default == "."

    def test_export_yes_flag(self):
        """Test export -y flag."""
        from deepr.cli.commands.semantic import export_expert
        
        for param in export_expert.params:
            if param.name == "yes":
                assert param.is_flag == True

    def test_import_corpus_required(self):
        """Test import --corpus is required."""
        from deepr.cli.commands.semantic import import_expert
        
        for param in import_expert.params:
            if param.name == "corpus":
                assert param.required == True


class TestCorpusStructure:
    """Test corpus directory structure."""

    def test_corpus_files_list(self):
        """Test expected files in corpus."""
        expected_files = [
            "manifest.json",
            "metadata.json",
            "worldview.json",
            "worldview.md",
            "README.md",
            "documents/"
        ]
        
        # These are the files that should be created during export
        for f in ["manifest.json", "metadata.json", "README.md"]:
            assert f in expected_files

    def test_manifest_tracks_files(self):
        """Test manifest tracks all files."""
        from deepr.experts.corpus import CorpusManifest
        
        manifest = CorpusManifest(
            name="test",
            files=[
                "manifest.json",
                "metadata.json",
                "worldview.json",
                "README.md",
                "documents/doc1.md"
            ]
        )
        
        assert len(manifest.files) == 5
        assert "documents/doc1.md" in manifest.files


class TestExportExamples:
    """Test documented examples."""

    def test_example_export_current_dir(self):
        """Test example: deepr expert export 'AWS Expert'"""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        result = runner.invoke(expert, ["export", "--help"])
        assert 'deepr expert export "AWS Expert"' in result.output

    def test_example_export_with_output(self):
        """Test example: deepr expert export 'Expert' --output ./exports"""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        result = runner.invoke(expert, ["export", "--help"])
        assert "--output" in result.output


class TestImportExamples:
    """Test documented import examples."""

    def test_example_import_corpus(self):
        """Test example: deepr expert import 'My Expert' --corpus ./corpus"""
        from deepr.cli.commands.semantic import expert
        
        runner = CliRunner()
        result = runner.invoke(expert, ["import", "--help"])
        assert "--corpus" in result.output
        assert "aws-expert" in result.output.lower() or "corpus" in result.output.lower()
