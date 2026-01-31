"""Tests for embedding cache functionality."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import json

from deepr.experts.embedding_cache import EmbeddingCache


class TestEmbeddingCacheBasics:
    """Test basic cache operations."""

    def test_cache_initialization(self, tmp_path):
        """Test cache initializes correctly."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        assert cache.expert_name == "test-expert"
        assert cache.cache_dir == tmp_path
        assert cache.index == {}
        assert cache.embeddings is None

    def test_content_hash_deterministic(self, tmp_path):
        """Test content hashing is deterministic."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        content = "This is test content"
        hash1 = cache._content_hash(content)
        hash2 = cache._content_hash(content)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA256 truncated to 16 chars

    def test_content_hash_different_for_different_content(self, tmp_path):
        """Test different content produces different hashes."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        hash1 = cache._content_hash("Content A")
        hash2 = cache._content_hash("Content B")
        
        assert hash1 != hash2

    def test_is_cached_returns_false_for_new_content(self, tmp_path):
        """Test is_cached returns False for uncached content."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        assert cache.is_cached("New content") is False

    def test_get_uncached_documents_returns_all_when_empty(self, tmp_path):
        """Test get_uncached_documents returns all docs when cache is empty."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        docs = [
            {"filename": "doc1.md", "content": "Content 1"},
            {"filename": "doc2.md", "content": "Content 2"},
        ]
        
        uncached = cache.get_uncached_documents(docs)
        
        assert len(uncached) == 2


class TestEmbeddingCachePersistence:
    """Test cache save/load functionality."""

    def test_save_and_load_index(self, tmp_path):
        """Test index is saved and loaded correctly."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        # Add some data to index
        cache.index = {
            "abc123": {
                "hash": "abc123",
                "filename": "test.md",
                "content_preview": "Test content",
            }
        }
        cache._save_cache()
        
        # Create new cache instance and verify data loaded
        cache2 = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        assert "abc123" in cache2.index
        assert cache2.index["abc123"]["filename"] == "test.md"

    def test_save_and_load_embeddings(self, tmp_path):
        """Test embeddings are saved and loaded correctly."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        # Add embeddings
        cache.embeddings = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        cache.index = {"a": {}, "b": {}}
        cache._save_cache()
        
        # Create new cache instance and verify embeddings loaded
        cache2 = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        assert cache2.embeddings is not None
        assert cache2.embeddings.shape == (2, 3)
        np.testing.assert_array_equal(cache2.embeddings[0], [1.0, 2.0, 3.0])


class TestEmbeddingCacheStats:
    """Test cache statistics."""

    def test_get_stats_empty_cache(self, tmp_path):
        """Test stats for empty cache."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        stats = cache.get_stats()
        
        assert stats["expert_name"] == "test-expert"
        assert stats["document_count"] == 0
        assert stats["embedding_dimensions"] == 0

    def test_get_stats_with_data(self, tmp_path):
        """Test stats with cached data."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        cache.embeddings = np.random.rand(5, 1536)  # 5 docs, 1536 dims
        cache.index = {f"doc{i}": {} for i in range(5)}
        
        stats = cache.get_stats()
        
        assert stats["document_count"] == 5
        assert stats["embedding_dimensions"] == 1536


class TestEmbeddingCacheClear:
    """Test cache clearing."""

    def test_clear_removes_all_data(self, tmp_path):
        """Test clear removes all cached data."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        # Add some data
        cache.embeddings = np.array([[1.0, 2.0, 3.0]])
        cache.index = {"abc": {"filename": "test.md"}}
        cache._save_cache()
        
        # Clear cache
        cache.clear()
        
        assert cache.index == {}
        assert cache.embeddings is None
        assert not cache.index_path.exists()
        assert not cache.embeddings_path.exists()


class TestEmbeddingCacheSearch:
    """Test search functionality (mocked API calls)."""

    @pytest.mark.asyncio
    async def test_search_empty_cache_returns_empty(self, tmp_path):
        """Test search on empty cache returns empty list."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        mock_client = AsyncMock()
        results = await cache.search("test query", mock_client)
        
        assert results == []

    @pytest.mark.asyncio
    async def test_search_returns_sorted_results(self, tmp_path):
        """Test search returns results sorted by similarity."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        # Set up cache with embeddings
        cache.embeddings = np.array([
            [1.0, 0.0, 0.0],  # doc1 - orthogonal to query
            [0.0, 1.0, 0.0],  # doc2 - similar to query
            [0.0, 0.5, 0.5],  # doc3 - somewhat similar
        ])
        cache.index = {
            "doc1": {"filename": "doc1.md", "full_content": "Content 1", "char_count": 10},
            "doc2": {"filename": "doc2.md", "full_content": "Content 2", "char_count": 10},
            "doc3": {"filename": "doc3.md", "full_content": "Content 3", "char_count": 10},
        }
        
        # Mock client to return query embedding similar to doc2
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.0, 1.0, 0.0])]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        
        results = await cache.search("test query", mock_client, top_k=3)
        
        assert len(results) == 3
        # doc2 should be first (highest similarity)
        assert results[0]["filename"] == "doc2.md"
        assert results[0]["score"] > results[1]["score"]


class TestEmbeddingCacheAddDocuments:
    """Test document addition (mocked API calls)."""

    @pytest.mark.asyncio
    async def test_add_documents_skips_cached(self, tmp_path):
        """Test add_documents skips already cached documents."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        # Pre-cache a document
        content = "Already cached content"
        content_hash = cache._content_hash(content)
        cache.index[content_hash] = {"filename": "cached.md"}
        cache.embeddings = np.array([[1.0, 2.0, 3.0]])
        
        # Try to add same document
        docs = [{"filename": "cached.md", "content": content}]
        
        mock_client = AsyncMock()
        added = await cache.add_documents(docs, mock_client)
        
        assert added == 0
        mock_client.embeddings.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_documents_embeds_new(self, tmp_path):
        """Test add_documents embeds new documents."""
        cache = EmbeddingCache("test-expert", cache_dir=tmp_path)
        
        docs = [
            {"filename": "new1.md", "content": "New content 1"},
            {"filename": "new2.md", "content": "New content 2"},
        ]
        
        # Mock client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[1.0] * 1536)]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        
        added = await cache.add_documents(docs, mock_client)
        
        assert added == 2
        assert len(cache.index) == 2
        assert cache.embeddings.shape == (2, 1536)
