"""Map-reduce document ingestion for expert knowledge.

Splits large documents into chunks, extracts key facts per chunk (map),
then consolidates into coherent summaries (reduce). Replaces the naive
2000-char truncation in synthesis.py with full-content condensation.

Usage:
    ingester = MapReduceIngester()
    condensed = await ingester.ingest(documents, domain="quantum computing")
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default chunk size in characters
DEFAULT_CHUNK_SIZE = 4000
# Maximum parallel map operations
DEFAULT_MAX_PARALLEL = 5
# Threshold for triggering map-reduce (20KB total content)
LARGE_DOCUMENT_THRESHOLD = 20_000


class MapReduceIngester:
    """Map-reduce pipeline for large document ingestion.

    Attributes:
        client: OpenAI async client (lazily initialized)
        map_model: Model for map phase (cheap, fast)
        reduce_model: Model for reduce phase (better reasoning)
        chunk_size: Target chunk size in characters
        max_parallel: Maximum concurrent map operations
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        map_model: str = "gpt-4.1-mini",
        reduce_model: str = "gpt-5.2",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
    ):
        self.client = client
        self.map_model = map_model
        self.reduce_model = reduce_model
        self.chunk_size = chunk_size
        self.max_parallel = max_parallel

    async def _get_client(self):
        if self.client is None:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI()
        return self.client

    async def ingest(
        self,
        documents: list[dict],
        domain: str,
    ) -> list[dict]:
        """Ingest documents via map-reduce, returning condensed versions.

        Args:
            documents: List of dicts with 'filename'/'path' and 'content'
            domain: Expert's domain for context

        Returns:
            List of dicts with 'filename' and condensed 'content'
        """
        results = []

        for doc in documents:
            filename = doc.get("filename", doc.get("path", "unknown"))
            content = doc.get("content", "")

            if len(content) <= self.chunk_size:
                # Small document — no need for map-reduce
                results.append({"filename": filename, "content": content})
                continue

            # Split into chunks
            chunks = self._split_document(content)

            # Map: extract facts per chunk (parallel with semaphore)
            semaphore = asyncio.Semaphore(self.max_parallel)
            doc_name = filename  # Bind for closure

            async def map_with_limit(
                chunk: str, idx: int, sem: asyncio.Semaphore = semaphore, name: str = doc_name
            ) -> dict:
                async with sem:
                    return await self._map_chunk(chunk, name, idx)

            map_tasks = [map_with_limit(chunk, i) for i, chunk in enumerate(chunks)]
            chunk_extractions = await asyncio.gather(*map_tasks, return_exceptions=True)

            # Filter out failures
            valid_extractions = [e for e in chunk_extractions if isinstance(e, dict)]

            if not valid_extractions:
                # Fallback: truncate to chunk_size
                results.append({"filename": filename, "content": content[: self.chunk_size]})
                continue

            # Reduce: consolidate into one summary
            condensed = await self._reduce_document(valid_extractions, filename, domain)
            results.append({"filename": filename, "content": condensed})

        return results

    def _split_document(self, content: str) -> list[str]:
        """Split document into chunks by headers, then paragraphs, then hard split.

        Args:
            content: Full document text

        Returns:
            List of chunk strings
        """
        chunks: list[str] = []

        # Try splitting at ## headers first
        header_sections = re.split(r"\n(?=##\s)", content)

        for section in header_sections:
            if len(section) <= self.chunk_size:
                if section.strip():
                    chunks.append(section.strip())
            else:
                # Section too large — split at paragraph boundaries
                paragraphs = section.split("\n\n")
                current_chunk = ""

                for para in paragraphs:
                    if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                        current_chunk += ("\n\n" if current_chunk else "") + para
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        if len(para) <= self.chunk_size:
                            current_chunk = para
                        else:
                            # Paragraph too large — hard split
                            for i in range(0, len(para), self.chunk_size):
                                chunk = para[i : i + self.chunk_size].strip()
                                if chunk:
                                    chunks.append(chunk)
                            current_chunk = ""

                if current_chunk.strip():
                    chunks.append(current_chunk.strip())

        return chunks if chunks else [content[: self.chunk_size]]

    async def _map_chunk(self, chunk: str, doc_name: str, chunk_index: int) -> dict:
        """Extract key facts from a single chunk.

        Args:
            chunk: Text chunk to process
            doc_name: Source document name
            chunk_index: Index of this chunk

        Returns:
            Dict with 'facts' list and metadata
        """
        prompt = (
            f"Document: {doc_name}, Chunk {chunk_index + 1}\n\n"
            f"{chunk}\n\n"
            "Extract 3-5 key facts from this text. Be terse. Bullet points.\n"
            'Output JSON: {"facts": ["fact 1", "fact 2", ...]}\n'
            "Output ONLY the JSON."
        )

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model=self.map_model,
                messages=[
                    {"role": "system", "content": "Extract key facts. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content or '{"facts": []}'
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = json.loads(text)
            return {
                "chunk_index": chunk_index,
                "facts": parsed.get("facts", []),
                "doc_name": doc_name,
            }
        except Exception as e:
            logger.warning("Map chunk %d of %s failed: %s", chunk_index, doc_name, e)
            raise

    async def _reduce_document(
        self,
        chunk_extractions: list[dict],
        doc_name: str,
        domain: str,
    ) -> str:
        """Consolidate chunk extractions into a coherent document summary.

        Args:
            chunk_extractions: List of extraction dicts from map phase
            doc_name: Document name
            domain: Expert's domain

        Returns:
            Condensed document content string
        """
        # Collect all facts
        all_facts = []
        for extraction in chunk_extractions:
            all_facts.extend(extraction.get("facts", []))

        if not all_facts:
            return f"[No facts extracted from {doc_name}]"

        facts_text = "\n".join(f"- {fact}" for fact in all_facts)

        prompt = (
            f"Document: {doc_name}\nDomain: {domain}\n\n"
            f"These facts were extracted from different sections of the document:\n\n{facts_text}\n\n"
            "Deduplicate, resolve any contradictions, and produce a coherent summary.\n"
            "Keep all unique information. Be comprehensive but concise.\n"
            "Output the summary as plain text (not JSON)."
        )

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model=self.reduce_model,
                messages=[
                    {"role": "system", "content": "You consolidate extracted facts into coherent summaries."},
                    {"role": "user", "content": prompt},
                ],
                reasoning_effort="low",
            )
            return response.choices[0].message.content or facts_text
        except Exception as e:
            logger.warning("Reduce for %s failed: %s", doc_name, e)
            # Fallback: return raw facts
            return f"Key facts from {doc_name}:\n{facts_text}"


def should_use_map_reduce(documents: list[dict]) -> bool:
    """Check if documents are large enough to warrant map-reduce.

    Args:
        documents: List of document dicts with 'content'

    Returns:
        True if total content exceeds threshold
    """
    total = sum(len(doc.get("content", "")) for doc in documents)
    return total > LARGE_DOCUMENT_THRESHOLD
