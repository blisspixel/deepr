"""Embedding cache for efficient knowledge base search.

This module provides pre-computed embedding storage and similarity search,
avoiding the O(n) API calls per query problem in the original implementation.

The cache stores embeddings locally as numpy arrays, enabling fast cosine
similarity search without re-embedding documents on every query.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Caches document embeddings for efficient similarity search.

    Instead of re-embedding every document on every search (O(n) API calls),
    this cache stores embeddings once and performs local similarity search.

    Storage format:
        {expert_name}/embeddings/
            index.json - metadata about cached documents
            embeddings.npy - numpy array of all embeddings
    """

    def __init__(self, expert_name: str, cache_dir: Path | None = None):
        """Initialize embedding cache for an expert.

        Args:
            expert_name: Name of the expert
            cache_dir: Optional custom cache directory
        """
        self.expert_name = expert_name

        if cache_dir:
            self.cache_dir = cache_dir
        else:
            # Default to data/experts/{name}/embeddings/
            from deepr.experts.profile import ExpertStore

            store = ExpertStore()
            self.cache_dir = store.get_knowledge_dir(expert_name) / "embeddings"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.cache_dir / "index.json"
        self.embeddings_path = self.cache_dir / "embeddings.npy"

        # Load existing cache
        self.index: dict[str, dict] = {}  # content_hash -> metadata
        self.embeddings: np.ndarray | None = None
        self.hash_to_idx: dict[str, int] = {}  # content_hash -> array index

        self._load_cache()

    def _load_cache(self):
        """Load existing cache from disk."""
        if self.index_path.exists():
            with open(self.index_path, encoding="utf-8") as f:
                data = json.load(f)
                self.index = data.get("documents", {})
                self.hash_to_idx = {h: i for i, h in enumerate(self.index.keys())}

        if self.embeddings_path.exists():
            self.embeddings = np.load(self.embeddings_path)

    def _save_cache(self):
        """Save cache to disk (atomic write)."""
        from deepr.utils.atomic_io import atomic_write_json

        atomic_write_json(
            self.index_path,
            {
                "expert_name": self.expert_name,
                "updated_at": datetime.now(UTC).isoformat(),
                "document_count": len(self.index),
                "documents": self.index,
            },
        )

        # Save embeddings
        if self.embeddings is not None:
            np.save(self.embeddings_path, self.embeddings)

    @staticmethod
    def _content_hash(content: str) -> str:
        """Generate hash of document content for deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def is_cached(self, content: str) -> bool:
        """Check if document content is already cached."""
        content_hash = self._content_hash(content)
        return content_hash in self.index

    def get_uncached_documents(self, documents: list[dict[str, str]]) -> list[dict[str, str]]:
        """Filter to only documents not yet in cache.

        Args:
            documents: List of dicts with 'filename' and 'content'

        Returns:
            List of documents that need embedding
        """
        uncached = []
        for doc in documents:
            content = doc.get("content", "")
            if not self.is_cached(content):
                uncached.append(doc)
        return uncached

    async def _embed_document(
        self,
        *,
        content: str,
        filename: str,
        client: Any,
        model: str,
        cost_safety: Any,
    ) -> tuple[Any, dict[str, Any]] | None:
        """Embed one document under cost and durable admission gates."""
        from deepr.experts.chat_capacity import (
            MeteredExpertChatDisabledError,
            require_expert_chat_dispatch,
        )
        from deepr.experts.chat_metered import execute_metered_chat_provider_call

        try:
            require_expert_chat_dispatch(None, "expert_chat_embed_document", metered=True)
        except MeteredExpertChatDisabledError as blocked:
            logger.warning("Embedding for %s blocked by metered chat gate: %s", filename, blocked)
            return None

        embed_content = content[:8000]
        estimate = 0.0002
        from deepr.experts.cost_admission import admit_soft_cost_operation

        # Prefer the caller's cost manager when provided; still fail closed if
        # soft admission cannot prove budget headroom.
        if cost_safety is not None:
            try:
                allowed, reason, _ = cost_safety.check_operation(
                    session_id=f"embed:{self.expert_name}",
                    operation_type="embed_document",
                    estimated_cost=estimate,
                    require_confirmation=False,
                )
                if not allowed:
                    logger.warning("Embedding for %s blocked by cost-safety: %s", filename, reason)
                    return None
            except Exception as exc:
                logger.warning(
                    "Embedding for %s blocked; cost-safety check failed closed: %s",
                    filename,
                    exc,
                )
                return None
        else:
            _manager, estimate, deny_reason = admit_soft_cost_operation(
                session_id=f"embed:{self.expert_name}",
                operation_type="embed_document",
                estimated_cost=estimate,
            )
            if deny_reason is not None:
                logger.warning("Embedding for %s blocked by cost-safety: %s", filename, deny_reason)
                return None
        try:
            response = await execute_metered_chat_provider_call(
                provider="openai",
                model=model,
                source="experts.embedding_cache.add_documents",
                max_cost_per_job=max(float(estimate), 0.0002),
                call=lambda: client.embeddings.create(model=model, input=embed_content),
            )
            # Durable admission already wrote the canonical ledger. Do not call
            # cost_safety.record_cost again (that would double-count spend).
            embedding = np.array(response.data[0].embedding)
            content_hash = self._content_hash(content)
            return embedding, {
                "hash": content_hash,
                "filename": filename,
                "content_preview": content[:500],
                "full_content": content[:2000],
                "char_count": len(content),
                "embedded_at": datetime.now(UTC).isoformat(),
            }
        except Exception as error:
            logger.error("Error embedding %s: %s", filename, error)
            return None

    async def add_documents(
        self, documents: list[dict[str, str]], client, model: str = "text-embedding-3-small"
    ) -> int:
        """Add documents to cache, embedding only new ones.

        Args:
            documents: List of dicts with 'filename' and 'content'
            client: AsyncOpenAI client for embedding API
            model: Embedding model to use

        Returns:
            Number of new documents added
        """
        uncached = self.get_uncached_documents(documents)
        if not uncached:
            return 0

        from deepr.experts.cost_admission import admit_soft_cost_operation

        cost_safety, _est, deny_reason = admit_soft_cost_operation(
            session_id=f"embed:{self.expert_name}",
            operation_type="embed_document_batch",
            estimated_cost=0.0002 * max(1, len(uncached)),
        )
        if deny_reason is not None:
            logger.warning("Document embed batch blocked by cost-safety: %s", deny_reason)
            return 0

        new_embeddings = []
        new_metadata = []
        for doc in uncached:
            content = doc.get("content", "")
            filename = doc.get("filename", "unknown")
            embedded = await self._embed_document(
                content=content,
                filename=filename,
                client=client,
                model=model,
                cost_safety=cost_safety,
            )
            if embedded is None:
                continue
            embedding, metadata = embedded
            new_embeddings.append(embedding)
            new_metadata.append(metadata)

        if not new_embeddings:
            return 0

        new_embeddings_array = np.array(new_embeddings)
        if self.embeddings is None:
            self.embeddings = new_embeddings_array
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings_array])

        for meta in new_metadata:
            content_hash = meta["hash"]
            self.index[content_hash] = meta
            self.hash_to_idx[content_hash] = len(self.hash_to_idx)

        self._save_cache()
        return len(new_embeddings)

    async def search(self, query: str, client, top_k: int = 5, model: str = "text-embedding-3-small") -> list[dict]:
        """Search cached documents by similarity.

        Args:
            query: Search query
            client: AsyncOpenAI client for query embedding
            top_k: Number of results to return
            model: Embedding model (must match cached embeddings)

        Returns:
            List of documents with id, content, filename, and score
        """
        if self.embeddings is None or len(self.embeddings) == 0:
            return []

        from deepr.experts.chat_capacity import (
            MeteredExpertChatDisabledError,
            require_expert_chat_dispatch,
        )

        try:
            require_expert_chat_dispatch(None, "expert_chat_embed_query", metered=True)
        except MeteredExpertChatDisabledError as blocked:
            logger.warning("Query embedding blocked by metered chat gate: %s", blocked)
            return []

        # Cost-safety gate for query embedding (fail closed).
        from deepr.experts.cost_admission import admit_soft_cost_operation

        _cost_safety, _est, _reason = admit_soft_cost_operation(
            session_id=f"embed_query:{self.expert_name}",
            operation_type="embed_query",
            estimated_cost=0.0001,
        )
        if _reason is not None:
            logger.warning("Query embedding blocked by cost-safety: %s", _reason)
            return []

        # Embed query (single API call) under durable admission.
        try:
            from deepr.experts.chat_metered import execute_metered_chat_provider_call

            response = await execute_metered_chat_provider_call(
                provider="openai",
                model=model,
                source="experts.embedding_cache.search",
                max_cost_per_job=max(float(_est), 0.0001),
                call=lambda: client.embeddings.create(model=model, input=query),
            )
            # Durable admission is the sole ledger write for this embed.
            query_embedding = np.array(response.data[0].embedding)
        except Exception as e:
            logger.error("Error embedding query: %s", e)
            return []

        # Compute cosine similarity with all cached embeddings (vectorized)
        # Normalize embeddings
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        doc_norms = self.embeddings / np.linalg.norm(self.embeddings, axis=1, keepdims=True)

        # Cosine similarity = dot product of normalized vectors
        similarities = np.dot(doc_norms, query_norm)

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        # Build results
        results = []
        hash_list = list(self.index.keys())

        for idx in top_indices:
            if idx >= len(hash_list):
                continue

            content_hash = hash_list[idx]
            meta = self.index[content_hash]

            results.append(
                {
                    "id": content_hash,
                    "filename": meta.get("filename", "unknown"),
                    "content": meta.get("full_content", meta.get("content_preview", "")),
                    "score": float(similarities[idx]),
                    "char_count": meta.get("char_count", 0),
                }
            )

        return results

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "expert_name": self.expert_name,
            "document_count": len(self.index),
            "embedding_dimensions": self.embeddings.shape[1] if self.embeddings is not None else 0,
            "cache_size_bytes": self.embeddings_path.stat().st_size if self.embeddings_path.exists() else 0,
        }

    def clear(self):
        """Clear the cache."""
        self.index = {}
        self.embeddings = None
        self.hash_to_idx = {}

        if self.index_path.exists():
            self.index_path.unlink()
        if self.embeddings_path.exists():
            self.embeddings_path.unlink()
