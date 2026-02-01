"""Tests for CLI file handler module.

Tests file pattern resolution, upload, and vector store creation.
Requirements: 6.3 - Extract file handling logic
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


class TestFileUploadResult:
    """Tests for FileUploadResult dataclass."""
    
    def test_success_with_uploads(self):
        """Test success is True when files uploaded."""
        from deepr.cli.commands.file_handler import FileUploadResult
        
        result = FileUploadResult(
            resolved_files=[Path("test.txt")],
            uploaded_ids=["file-123"],
            vector_store_id="vs-123",
            errors=[]
        )
        
        assert result.success is True
    
    def test_success_false_no_uploads(self):
        """Test success is False when no files uploaded."""
        from deepr.cli.commands.file_handler import FileUploadResult
        
        result = FileUploadResult(
            resolved_files=[],
            uploaded_ids=[],
            vector_store_id=None,
            errors=["No files found"]
        )
        
        assert result.success is False
    
    def test_has_errors_true(self):
        """Test has_errors is True when errors present."""
        from deepr.cli.commands.file_handler import FileUploadResult
        
        result = FileUploadResult(
            resolved_files=[],
            uploaded_ids=[],
            vector_store_id=None,
            errors=["Error 1", "Error 2"]
        )
        
        assert result.has_errors is True
    
    def test_has_errors_false(self):
        """Test has_errors is False when no errors."""
        from deepr.cli.commands.file_handler import FileUploadResult
        
        result = FileUploadResult(
            resolved_files=[Path("test.txt")],
            uploaded_ids=["file-123"],
            vector_store_id="vs-123",
            errors=[]
        )
        
        assert result.has_errors is False


class TestResolveFilePatterns:
    """Tests for resolve_file_patterns function."""
    
    def test_resolve_single_file(self, tmp_path):
        """Test resolving a single file path."""
        from deepr.cli.commands.file_handler import resolve_file_patterns
        
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        # Patch at source module since import happens inside function
        with patch("deepr.utils.paths.resolve_file_path") as mock_resolve:
            mock_resolve.return_value = test_file
            
            files, errors = resolve_file_patterns((str(test_file),))
            
            assert len(files) == 1
            assert files[0] == test_file
            assert len(errors) == 0
    
    def test_resolve_glob_pattern(self, tmp_path):
        """Test resolving glob patterns."""
        from deepr.cli.commands.file_handler import resolve_file_patterns
        
        # Create test files
        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"
        file1.write_text("content1")
        file2.write_text("content2")
        
        # Patch at source module since import happens inside function
        with patch("deepr.utils.paths.resolve_glob_pattern") as mock_glob:
            mock_glob.return_value = [file1, file2]
            
            files, errors = resolve_file_patterns((f"{tmp_path}/*.txt",))
            
            assert len(files) == 2
            assert len(errors) == 0
    
    def test_file_not_found_error(self):
        """Test handling file not found."""
        from deepr.cli.commands.file_handler import resolve_file_patterns
        
        # Patch at source module since import happens inside function
        with patch("deepr.utils.paths.resolve_file_path") as mock_resolve:
            mock_resolve.side_effect = FileNotFoundError("File not found: missing.txt")
            
            files, errors = resolve_file_patterns(("missing.txt",))
            
            assert len(files) == 0
            assert len(errors) == 1
            assert "File not found" in errors[0]


class TestUploadFiles:
    """Tests for upload_files function."""
    
    @pytest.mark.asyncio
    async def test_upload_single_file(self, tmp_path):
        """Test uploading a single file."""
        from deepr.cli.commands.file_handler import upload_files
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        mock_provider = MagicMock()
        mock_provider.upload_document = AsyncMock(return_value="file-123")
        
        uploaded, errors = await upload_files(mock_provider, [test_file])
        
        assert uploaded == ["file-123"]
        assert len(errors) == 0
        mock_provider.upload_document.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_multiple_files(self, tmp_path):
        """Test uploading multiple files."""
        from deepr.cli.commands.file_handler import upload_files
        
        file1 = tmp_path / "test1.txt"
        file2 = tmp_path / "test2.txt"
        file1.write_text("content1")
        file2.write_text("content2")
        
        mock_provider = MagicMock()
        mock_provider.upload_document = AsyncMock(side_effect=["file-1", "file-2"])
        
        uploaded, errors = await upload_files(mock_provider, [file1, file2])
        
        assert uploaded == ["file-1", "file-2"]
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_upload_error_handling(self, tmp_path):
        """Test handling upload errors."""
        from deepr.cli.commands.file_handler import upload_files
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        mock_provider = MagicMock()
        mock_provider.upload_document = AsyncMock(side_effect=Exception("Upload failed"))
        
        uploaded, errors = await upload_files(mock_provider, [test_file])
        
        assert len(uploaded) == 0
        assert len(errors) == 1
        assert "Failed to upload" in errors[0]


class TestCreateVectorStoreForFiles:
    """Tests for create_vector_store_for_files function."""
    
    @pytest.mark.asyncio
    async def test_create_vector_store_success(self):
        """Test successful vector store creation."""
        from deepr.cli.commands.file_handler import create_vector_store_for_files
        
        mock_provider = MagicMock()
        mock_vs = MagicMock()
        mock_vs.id = "vs-test-123"
        mock_provider.create_vector_store = AsyncMock(return_value=mock_vs)
        mock_provider.wait_for_vector_store = AsyncMock(return_value=True)
        
        vs_id, errors = await create_vector_store_for_files(
            mock_provider, ["file-1", "file-2"]
        )
        
        assert vs_id == "vs-test-123"
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_create_vector_store_not_ready(self):
        """Test vector store not ready in time."""
        from deepr.cli.commands.file_handler import create_vector_store_for_files
        
        mock_provider = MagicMock()
        mock_vs = MagicMock()
        mock_vs.id = "vs-test-123"
        mock_provider.create_vector_store = AsyncMock(return_value=mock_vs)
        mock_provider.wait_for_vector_store = AsyncMock(return_value=False)
        
        vs_id, errors = await create_vector_store_for_files(
            mock_provider, ["file-1"]
        )
        
        assert vs_id == "vs-test-123"
        assert len(errors) == 1
        assert "still processing" in errors[0]
    
    @pytest.mark.asyncio
    async def test_create_vector_store_error(self):
        """Test vector store creation error."""
        from deepr.cli.commands.file_handler import create_vector_store_for_files
        
        mock_provider = MagicMock()
        mock_provider.create_vector_store = AsyncMock(
            side_effect=Exception("Creation failed")
        )
        
        vs_id, errors = await create_vector_store_for_files(
            mock_provider, ["file-1"]
        )
        
        assert vs_id is None
        assert len(errors) == 1
        assert "creation failed" in errors[0].lower()


class TestHandleFileUploads:
    """Tests for handle_file_uploads function."""
    
    @pytest.mark.asyncio
    async def test_empty_patterns_returns_empty_result(self):
        """Test empty patterns returns empty result."""
        from deepr.cli.commands.file_handler import handle_file_uploads
        
        result = await handle_file_uploads("openai", tuple())
        
        assert result.success is False
        assert len(result.uploaded_ids) == 0
    
    @pytest.mark.asyncio
    async def test_full_workflow_openai(self, tmp_path):
        """Test full upload workflow for OpenAI."""
        from deepr.cli.commands.file_handler import handle_file_uploads
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        # Patch the functions where they're defined, not where imported
        with patch("deepr.cli.commands.file_handler.resolve_file_patterns") as mock_resolve, \
             patch("deepr.cli.commands.provider_factory.create_provider_instance") as mock_create, \
             patch("deepr.cli.commands.file_handler.upload_files") as mock_upload, \
             patch("deepr.cli.commands.file_handler.create_vector_store_for_files") as mock_vs:
            
            mock_resolve.return_value = ([test_file], [])
            mock_provider = MagicMock()
            mock_create.return_value = mock_provider
            mock_upload.return_value = (["file-123"], [])
            mock_vs.return_value = ("vs-123", [])
            
            result = await handle_file_uploads(
                "openai",
                (str(test_file),),
                config={"api_key": "test"}
            )
            
            assert result.success is True
            assert result.vector_store_id == "vs-123"
            assert "file-123" in result.uploaded_ids
    
    @pytest.mark.asyncio
    async def test_gemini_no_vector_store(self, tmp_path):
        """Test Gemini doesn't create vector store."""
        from deepr.cli.commands.file_handler import handle_file_uploads
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        # Patch the functions where they're defined, not where imported
        with patch("deepr.cli.commands.file_handler.resolve_file_patterns") as mock_resolve, \
             patch("deepr.cli.commands.provider_factory.create_provider_instance") as mock_create, \
             patch("deepr.cli.commands.file_handler.upload_files") as mock_upload, \
             patch("deepr.cli.commands.file_handler.create_vector_store_for_files") as mock_vs:
            
            mock_resolve.return_value = ([test_file], [])
            mock_provider = MagicMock()
            mock_create.return_value = mock_provider
            mock_upload.return_value = (["file-123"], [])
            
            result = await handle_file_uploads(
                "gemini",
                (str(test_file),),
                config={"gemini_api_key": "test"}
            )
            
            assert result.success is True
            assert result.vector_store_id is None
            # Vector store should not be created for Gemini
            mock_vs.assert_not_called()
