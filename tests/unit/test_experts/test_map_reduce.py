"""Tests for deepr.experts.map_reduce.MapReduceIngester."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.map_reduce import (
    DEFAULT_CHUNK_SIZE,
    LARGE_DOCUMENT_THRESHOLD,
    MapReduceIngester,
    should_use_map_reduce,
)


# ---------------------------------------------------------------------------
# should_use_map_reduce
# ---------------------------------------------------------------------------


class TestShouldUseMapReduce:
    def test_small_documents(self):
        docs = [{"content": "small"}]
        assert should_use_map_reduce(docs) is False

    def test_large_documents(self):
        docs = [{"content": "x" * (LARGE_DOCUMENT_THRESHOLD + 1)}]
        assert should_use_map_reduce(docs) is True

    def test_multiple_medium_documents(self):
        docs = [{"content": "x" * 5000} for _ in range(5)]
        assert should_use_map_reduce(docs) is True

    def test_empty_documents(self):
        assert should_use_map_reduce([]) is False

    def test_missing_content(self):
        docs = [{"filename": "test.md"}]
        assert should_use_map_reduce(docs) is False


# ---------------------------------------------------------------------------
# MapReduceIngester._split_document
# ---------------------------------------------------------------------------


class TestSplitDocument:
    def setup_method(self):
        self.ingester = MapReduceIngester(chunk_size=100)

    def test_small_document_single_chunk(self):
        content = "Small document"
        chunks = self.ingester._split_document(content)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_split_at_headers(self):
        content = "## Section 1\nContent 1\n\n## Section 2\nContent 2"
        ingester = MapReduceIngester(chunk_size=1000)
        chunks = ingester._split_document(content)
        assert len(chunks) == 2

    def test_split_at_paragraphs(self):
        # Large section without headers
        content = "Para 1 content here.\n\nPara 2 content here.\n\nPara 3 content here."
        ingester = MapReduceIngester(chunk_size=30)
        chunks = ingester._split_document(content)
        assert len(chunks) >= 2

    def test_hard_split_for_huge_paragraphs(self):
        content = "x" * 500
        ingester = MapReduceIngester(chunk_size=100)
        chunks = ingester._split_document(content)
        assert len(chunks) >= 5
        assert all(len(c) <= 100 for c in chunks)

    def test_empty_content(self):
        chunks = self.ingester._split_document("")
        assert len(chunks) == 1

    def test_preserves_content(self):
        content = "## Header\n\nContent here with important data.\n\n## Another\n\nMore data here."
        ingester = MapReduceIngester(chunk_size=1000)
        chunks = ingester._split_document(content)
        joined = " ".join(chunks)
        assert "important data" in joined
        assert "More data" in joined


# ---------------------------------------------------------------------------
# MapReduceIngester._map_chunk
# ---------------------------------------------------------------------------


class TestMapChunk:
    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "facts": ["Fact 1", "Fact 2", "Fact 3"],
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        ingester = MapReduceIngester(client=mock_client)
        result = await ingester._map_chunk("Some text content", "doc.md", 0)

        assert result["chunk_index"] == 0
        assert len(result["facts"]) == 3
        assert result["doc_name"] == "doc.md"

    @pytest.mark.asyncio
    async def test_extraction_failure(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API fail"))

        ingester = MapReduceIngester(client=mock_client)
        with pytest.raises(Exception, match="API fail"):
            await ingester._map_chunk("text", "doc.md", 0)

    @pytest.mark.asyncio
    async def test_markdown_fenced_response(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '```json\n{"facts": ["F1"]}\n```'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        ingester = MapReduceIngester(client=mock_client)
        result = await ingester._map_chunk("text", "doc.md", 0)
        assert len(result["facts"]) == 1


# ---------------------------------------------------------------------------
# MapReduceIngester._reduce_document
# ---------------------------------------------------------------------------


class TestReduceDocument:
    @pytest.mark.asyncio
    async def test_successful_reduction(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Consolidated summary of all facts."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        ingester = MapReduceIngester(client=mock_client)
        result = await ingester._reduce_document(
            [{"facts": ["F1", "F2"]}, {"facts": ["F3"]}],
            "doc.md",
            "test_domain",
        )
        assert "Consolidated summary" in result

    @pytest.mark.asyncio
    async def test_empty_facts(self):
        ingester = MapReduceIngester()
        result = await ingester._reduce_document(
            [{"facts": []}], "doc.md", "domain"
        )
        assert "No facts extracted" in result

    @pytest.mark.asyncio
    async def test_reduction_failure_fallback(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Fail"))

        ingester = MapReduceIngester(client=mock_client)
        result = await ingester._reduce_document(
            [{"facts": ["Important fact 1"]}, {"facts": ["Important fact 2"]}],
            "doc.md",
            "domain",
        )
        assert "Important fact 1" in result
        assert "Important fact 2" in result


# ---------------------------------------------------------------------------
# MapReduceIngester.ingest
# ---------------------------------------------------------------------------


class TestIngest:
    @pytest.mark.asyncio
    async def test_small_documents_pass_through(self):
        ingester = MapReduceIngester(chunk_size=10000)
        docs = [{"filename": "small.md", "content": "Short content"}]

        result = await ingester.ingest(docs, "domain")
        assert len(result) == 1
        assert result[0]["content"] == "Short content"

    @pytest.mark.asyncio
    async def test_large_document_processed(self):
        mock_client = AsyncMock()

        # Map response (returned for every map call)
        map_response = MagicMock()
        map_response.choices = [MagicMock()]
        map_response.choices[0].message.content = json.dumps({"facts": ["F1", "F2"]})

        # Reduce response
        reduce_response = MagicMock()
        reduce_response.choices = [MagicMock()]
        reduce_response.choices[0].message.content = "Condensed document summary"

        # Use a function to return map responses for any number of chunks, then reduce
        call_count = {"n": 0}
        ingester = MapReduceIngester(client=mock_client, chunk_size=50)
        # Pre-calculate chunk count to set up exact side_effect
        chunks = ingester._split_document("x" * 200)
        responses = [map_response] * len(chunks) + [reduce_response]
        mock_client.chat.completions.create = AsyncMock(side_effect=responses)

        docs = [{"filename": "big.md", "content": "x" * 200}]

        result = await ingester.ingest(docs, "domain")
        assert len(result) == 1
        assert result[0]["filename"] == "big.md"
        assert "Condensed" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_mixed_document_sizes(self):
        mock_client = AsyncMock()

        map_response = MagicMock()
        map_response.choices = [MagicMock()]
        map_response.choices[0].message.content = json.dumps({"facts": ["F1"]})

        reduce_response = MagicMock()
        reduce_response.choices = [MagicMock()]
        reduce_response.choices[0].message.content = "Summary"

        ingester = MapReduceIngester(client=mock_client, chunk_size=50)
        # Pre-calculate chunk count for the big doc
        chunks = ingester._split_document("x" * 100)
        responses = [map_response] * len(chunks) + [reduce_response]
        mock_client.chat.completions.create = AsyncMock(side_effect=responses)

        docs = [
            {"filename": "small.md", "content": "Small"},
            {"filename": "big.md", "content": "x" * 100},
        ]

        result = await ingester.ingest(docs, "domain")
        assert len(result) == 2
        assert result[0]["content"] == "Small"  # Passed through
        assert result[1]["content"] == "Summary"  # Processed

    @pytest.mark.asyncio
    async def test_all_map_failures_fallback(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Fail"))

        ingester = MapReduceIngester(client=mock_client, chunk_size=50)
        docs = [{"filename": "doc.md", "content": "x" * 100}]

        result = await ingester.ingest(docs, "domain")
        assert len(result) == 1
        # Falls back to truncated content
        assert len(result[0]["content"]) <= 50

    @pytest.mark.asyncio
    async def test_empty_documents(self):
        ingester = MapReduceIngester()
        result = await ingester.ingest([], "domain")
        assert result == []
