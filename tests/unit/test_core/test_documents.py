"""Unit tests for the Document Manager module.

Tests document upload, vector store creation, and file validation.
"""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from deepr.core.documents import DocumentManager


class TestDocumentManagerValidation:
    """Test file validation methods."""

    @pytest.fixture
    def doc_manager(self):
        """Create a DocumentManager instance."""
        return DocumentManager()

    def test_validate_pdf(self, doc_manager):
        """Test PDF file validation."""
        assert doc_manager.validate_file_type("document.pdf") is True
        assert doc_manager.validate_file_type("DOCUMENT.PDF") is True

    def test_validate_doc(self, doc_manager):
        """Test DOC file validation."""
        assert doc_manager.validate_file_type("document.doc") is True
        assert doc_manager.validate_file_type("document.docx") is True

    def test_validate_txt(self, doc_manager):
        """Test TXT file validation."""
        assert doc_manager.validate_file_type("document.txt") is True

    def test_validate_md(self, doc_manager):
        """Test Markdown file validation."""
        assert doc_manager.validate_file_type("document.md") is True

    def test_validate_csv(self, doc_manager):
        """Test CSV file validation."""
        assert doc_manager.validate_file_type("data.csv") is True

    def test_validate_json(self, doc_manager):
        """Test JSON file validation."""
        assert doc_manager.validate_file_type("config.json") is True

    def test_validate_xml(self, doc_manager):
        """Test XML file validation."""
        assert doc_manager.validate_file_type("data.xml") is True

    def test_validate_unsupported(self, doc_manager):
        """Test unsupported file types."""
        assert doc_manager.validate_file_type("image.png") is False
        assert doc_manager.validate_file_type("video.mp4") is False
        assert doc_manager.validate_file_type("archive.zip") is False
        assert doc_manager.validate_file_type("script.py") is False

    def test_validate_no_extension(self, doc_manager):
        """Test file without extension."""
        assert doc_manager.validate_file_type("README") is False

    def test_validate_path_with_directories(self, doc_manager):
        """Test file path with directories."""
        assert doc_manager.validate_file_type("path/to/document.pdf") is True
        assert doc_manager.validate_file_type("/absolute/path/doc.txt") is True


class TestDocumentManagerFileSize:
    """Test file size methods."""

    @pytest.fixture
    def doc_manager(self):
        """Create a DocumentManager instance."""
        return DocumentManager()

    def test_get_file_size(self, doc_manager):
        """Test getting file size."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"Hello, World!")
            f.flush()
            
            size = doc_manager.get_file_size(f.name)
            assert size == 13  # "Hello, World!" is 13 bytes

    def test_get_file_size_empty(self, doc_manager):
        """Test getting size of empty file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            size = doc_manager.get_file_size(f.name)
            assert size == 0

    def test_get_file_size_large(self, doc_manager):
        """Test getting size of larger file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"x" * 1024)  # 1KB
            f.flush()
            
            size = doc_manager.get_file_size(f.name)
            assert size == 1024


class TestDocumentManagerUpload:
    """Test document upload functionality."""

    @pytest.fixture
    def doc_manager(self):
        """Create a DocumentManager instance."""
        return DocumentManager()

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        provider = MagicMock()
        provider.upload_document = AsyncMock(return_value="file_123")
        return provider

    @pytest.mark.asyncio
    async def test_upload_single_document(self, doc_manager, mock_provider):
        """Test uploading a single document."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"Test content")
            f.flush()
            
            file_ids = await doc_manager.upload_documents([f.name], mock_provider)
            
            assert len(file_ids) == 1
            assert file_ids[0] == "file_123"
            mock_provider.upload_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_multiple_documents(self, doc_manager, mock_provider):
        """Test uploading multiple documents."""
        mock_provider.upload_document = AsyncMock(
            side_effect=["file_1", "file_2", "file_3"]
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                path = Path(tmpdir) / f"doc{i}.txt"
                path.write_text(f"Content {i}")
                files.append(str(path))
            
            file_ids = await doc_manager.upload_documents(files, mock_provider)
            
            assert len(file_ids) == 3
            assert file_ids == ["file_1", "file_2", "file_3"]
            assert mock_provider.upload_document.call_count == 3

    @pytest.mark.asyncio
    async def test_upload_nonexistent_file(self, doc_manager, mock_provider):
        """Test uploading a file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            await doc_manager.upload_documents(
                ["/nonexistent/path/file.txt"],
                mock_provider
            )

    @pytest.mark.asyncio
    async def test_upload_empty_list(self, doc_manager, mock_provider):
        """Test uploading empty file list."""
        file_ids = await doc_manager.upload_documents([], mock_provider)
        assert file_ids == []
        mock_provider.upload_document.assert_not_called()


class TestDocumentManagerVectorStore:
    """Test vector store creation functionality."""

    @pytest.fixture
    def doc_manager(self):
        """Create a DocumentManager instance."""
        return DocumentManager()

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider with vector store methods."""
        provider = MagicMock()
        
        mock_vector_store = MagicMock()
        mock_vector_store.id = "vs_123"
        mock_vector_store.name = "Test Store"
        
        provider.create_vector_store = AsyncMock(return_value=mock_vector_store)
        provider.wait_for_vector_store = AsyncMock()
        
        return provider

    @pytest.mark.asyncio
    async def test_create_vector_store(self, doc_manager, mock_provider):
        """Test creating a vector store."""
        file_ids = ["file_1", "file_2"]
        
        vector_store = await doc_manager.create_vector_store(
            name="Test Store",
            file_ids=file_ids,
            provider=mock_provider
        )
        
        assert vector_store.id == "vs_123"
        mock_provider.create_vector_store.assert_called_once_with("Test Store", file_ids)
        mock_provider.wait_for_vector_store.assert_called_once_with("vs_123")

    @pytest.mark.asyncio
    async def test_create_vector_store_empty_files(self, doc_manager, mock_provider):
        """Test creating a vector store with no files."""
        vector_store = await doc_manager.create_vector_store(
            name="Empty Store",
            file_ids=[],
            provider=mock_provider
        )
        
        mock_provider.create_vector_store.assert_called_once_with("Empty Store", [])

    @pytest.mark.asyncio
    async def test_create_vector_store_waits_for_ingestion(self, doc_manager, mock_provider):
        """Test that vector store creation waits for ingestion."""
        await doc_manager.create_vector_store(
            name="Test",
            file_ids=["file_1"],
            provider=mock_provider
        )
        
        # Verify wait was called after create
        mock_provider.wait_for_vector_store.assert_called_once()


class TestDocumentManagerEdgeCases:
    """Test edge cases in document management."""

    @pytest.fixture
    def doc_manager(self):
        """Create a DocumentManager instance."""
        return DocumentManager()

    def test_validate_case_insensitive(self, doc_manager):
        """Test file type validation is case insensitive."""
        assert doc_manager.validate_file_type("doc.PDF") is True
        assert doc_manager.validate_file_type("doc.Pdf") is True
        assert doc_manager.validate_file_type("doc.TXT") is True
        assert doc_manager.validate_file_type("doc.Json") is True

    def test_validate_double_extension(self, doc_manager):
        """Test file with double extension."""
        assert doc_manager.validate_file_type("file.backup.pdf") is True
        assert doc_manager.validate_file_type("file.old.txt") is True

    def test_validate_hidden_file(self, doc_manager):
        """Test hidden file validation."""
        assert doc_manager.validate_file_type(".hidden.pdf") is True
        assert doc_manager.validate_file_type(".config.json") is True

    def test_validate_spaces_in_name(self, doc_manager):
        """Test file with spaces in name."""
        assert doc_manager.validate_file_type("my document.pdf") is True
        assert doc_manager.validate_file_type("path/to/my file.txt") is True

    def test_validate_special_characters(self, doc_manager):
        """Test file with special characters."""
        assert doc_manager.validate_file_type("doc-v1.0.pdf") is True
        assert doc_manager.validate_file_type("doc_final.txt") is True
        assert doc_manager.validate_file_type("doc (1).pdf") is True


class TestDocumentManagerStaticMethods:
    """Test that static methods work without instance."""

    def test_validate_file_type_static(self):
        """Test validate_file_type as static method."""
        assert DocumentManager.validate_file_type("test.pdf") is True
        assert DocumentManager.validate_file_type("test.exe") is False

    def test_get_file_size_static(self):
        """Test get_file_size as static method."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"Test")
            f.flush()
            
            size = DocumentManager.get_file_size(f.name)
            assert size == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
