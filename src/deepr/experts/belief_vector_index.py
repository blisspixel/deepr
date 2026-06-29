"""Persistent local vector index for belief recall candidates.

The index stores vectors supplied by an already-gated embedding path. It never
computes embeddings, calls a provider, or decides belief meaning.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

BELIEF_VECTOR_INDEX_SCHEMA_VERSION = "deepr-belief-vector-index-v1"
DEFAULT_BELIEF_VECTOR_INDEX_FILENAME = "belief_vectors.json"
MAX_INDEX_BYTES = 50 * 1024 * 1024
MAX_VECTOR_DIMENSIONS = 8192


def belief_claim_hash(claim: str) -> str:
    """Return a stable hash for the exact claim text that was embedded."""
    return hashlib.sha256(claim.encode("utf-8")).hexdigest()


def _coerce_embedding(embedding: Sequence[float]) -> tuple[float, ...]:
    if isinstance(embedding, (str, bytes)):
        raise ValueError("embedding must be a numeric sequence")
    values = tuple(float(value) for value in embedding)
    if not values:
        raise ValueError("embedding must not be empty")
    if len(values) > MAX_VECTOR_DIMENSIONS:
        raise ValueError(f"embedding exceeds {MAX_VECTOR_DIMENSIONS} dimensions")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("embedding values must be finite")
    return values


def _record_embedding(record: Mapping[str, Any]) -> tuple[float, ...] | None:
    raw = record.get("embedding", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    try:
        return _coerce_embedding(raw)
    except (TypeError, ValueError):
        return None


class BeliefVectorIndex:
    """Local persisted belief vectors keyed by belief id.

    Records are valid only while the current belief claim hash matches the hash
    stored with the embedding. A revised claim therefore cannot accidentally use
    a stale vector.
    """

    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, dict[str, Any]] = {}
        self._load()

    @classmethod
    def for_belief_store(cls, storage_dir: Path) -> BeliefVectorIndex:
        return cls(storage_dir / DEFAULT_BELIEF_VECTOR_INDEX_FILENAME)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size > MAX_INDEX_BYTES:
                logger.error(
                    "Belief vector index at %s exceeds 50 MB; ignoring until it is rebuilt.",
                    self.path,
                )
                return
            with open(self.path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load belief vector index from %s: %s", self.path, exc)
            return

        raw_records = payload.get("records", {}) if isinstance(payload, Mapping) else {}
        if not isinstance(raw_records, Mapping):
            return
        self.records = {
            str(belief_id): dict(record)
            for belief_id, record in raw_records.items()
            if isinstance(record, Mapping) and _record_embedding(record) is not None
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.path,
            {
                "schema_version": BELIEF_VECTOR_INDEX_SCHEMA_VERSION,
                "updated_at": datetime.now(UTC).isoformat(),
                "record_count": len(self.records),
                "records": self.records,
            },
        )

    def upsert_belief(
        self,
        belief: Any,
        embedding: Sequence[float],
        *,
        model: str = "",
        embedded_at: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> bool:
        """Persist a vector for a belief claim.

        Returns True when the stored index changed.
        """
        belief_id = str(getattr(belief, "id", "") or "")
        claim = str(getattr(belief, "claim", "") or "")
        if not belief_id:
            raise ValueError("belief id is required")
        if not claim:
            raise ValueError("belief claim is required")
        vector = _coerce_embedding(embedding)
        record = {
            "belief_id": belief_id,
            "claim_hash": belief_claim_hash(claim),
            "model": str(model or ""),
            "dimensions": len(vector),
            "embedding": list(vector),
            "embedded_at": embedded_at or datetime.now(UTC).isoformat(),
            "metadata": dict(metadata or {}),
        }
        if self.records.get(belief_id) == record:
            return False
        self.records[belief_id] = record
        self._save()
        return True

    def remove(self, belief_id: str) -> bool:
        """Remove a belief vector if present."""
        key = str(belief_id)
        if key not in self.records:
            return False
        del self.records[key]
        self._save()
        return True

    def prune(self, current_belief_ids: Iterable[str]) -> int:
        """Drop vectors for beliefs no longer present in the canonical store."""
        current = {str(belief_id) for belief_id in current_belief_ids}
        stale = [belief_id for belief_id in self.records if belief_id not in current]
        if not stale:
            return 0
        for belief_id in stale:
            del self.records[belief_id]
        self._save()
        return len(stale)

    def vectors_for(
        self,
        beliefs: Iterable[Any],
        *,
        model: str | None = None,
    ) -> dict[str, tuple[float, ...]]:
        """Return non-stale vectors for current belief claims."""
        vectors: dict[str, tuple[float, ...]] = {}
        for belief in beliefs:
            belief_id = str(getattr(belief, "id", "") or "")
            claim = str(getattr(belief, "claim", "") or "")
            record = self.records.get(belief_id)
            if not belief_id or not claim or not record:
                continue
            if model is not None and str(record.get("model", "")) != model:
                continue
            if str(record.get("claim_hash", "")) != belief_claim_hash(claim):
                continue
            embedding = _record_embedding(record)
            if embedding is not None:
                vectors[belief_id] = embedding
        return vectors

    def missing_or_stale_ids(
        self,
        beliefs: Iterable[Any],
        *,
        model: str | None = None,
    ) -> list[str]:
        """Return current belief ids whose vectors are absent or stale."""
        belief_list = list(beliefs)
        available = self.vectors_for(belief_list, model=model)
        return [
            belief_id
            for belief in belief_list
            if (belief_id := str(getattr(belief, "id", "") or "")) and belief_id not in available
        ]

    def stats(self, beliefs: Iterable[Any] = (), *, model: str | None = None) -> dict[str, Any]:
        """Return local index statistics without inspecting vector values."""
        belief_list = list(beliefs)
        current_vectors = self.vectors_for(belief_list, model=model) if belief_list else {}
        dimensions = sorted({len(vector) for vector in current_vectors.values()})
        return {
            "schema_version": BELIEF_VECTOR_INDEX_SCHEMA_VERSION,
            "record_count": len(self.records),
            "current_vector_count": len(current_vectors),
            "missing_or_stale_count": (len(self.missing_or_stale_ids(belief_list, model=model)) if belief_list else 0),
            "dimensions": dimensions,
            "path": str(self.path),
        }


__all__ = [
    "BELIEF_VECTOR_INDEX_SCHEMA_VERSION",
    "BeliefVectorIndex",
    "belief_claim_hash",
]
