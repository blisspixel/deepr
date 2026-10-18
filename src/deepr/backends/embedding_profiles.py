"""Versioned local embedding inputs and dimension contracts, without inference."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

PROFILE_CHOICES = ("none", "auto", "nomic-v1", "embeddinggemma-fact-checking-v1")


@dataclass(frozen=True)
class EmbeddingProfile:
    name: str
    dimensions: int | None = None

    def prepare(self, text: str, role: str) -> str:
        if not isinstance(text, str):
            raise ValueError("embedding inputs must be text")
        if role not in {"query", "document"}:
            raise ValueError("embedding role must be query or document")
        if self.name == "nomic-v1":
            return f"search_{role}: {text}"
        if self.name == "embeddinggemma-fact-checking-v1":
            return f"task: fact checking | query: {text}" if role == "query" else f"title: none | text: {text}"
        return text

    def vector(self, values: Sequence[float]) -> tuple[float, ...]:
        if isinstance(values, (str, bytes)) or any(isinstance(value, bool) for value in values):
            raise ValueError("embedding response values must be numeric")
        vector = tuple(float(value) for value in values)
        if not vector or len(vector) > 8192 or any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding must contain 1 to 8192 finite values")
        if self.name == "embeddinggemma-fact-checking-v1":
            if len(vector) != 768:
                raise ValueError("EmbeddingGemma requires a native 768-dimensional response")
            vector = vector[: self.dimensions or 768]
            norm = math.hypot(*vector)
            if not math.isfinite(norm) or norm == 0:
                raise ValueError("embedding must not have zero norm")
            return tuple(value / norm for value in vector)
        if self.dimensions is not None and len(vector) != self.dimensions:
            raise ValueError("embedding response dimensions do not match the requested dimensions")
        if not math.isfinite(math.hypot(*vector)) or math.hypot(*vector) == 0:
            raise ValueError("embedding must not have zero norm")
        return vector


def resolve_embedding_profile(model: str, profile: str = "none", dimensions: int | None = None) -> EmbeddingProfile:
    if profile not in PROFILE_CHOICES:
        raise ValueError(f"unknown embedding profile: {profile}")
    family = model.strip().lower().rsplit("/", 1)[-1].partition(":")[0]
    known = {"nomic-embed-text": "nomic-v1", "embeddinggemma-2": "embeddinggemma-fact-checking-v1"}
    resolved = known.get(family, "none") if profile == "auto" else profile
    if resolved != "none" and known.get(family) != resolved:
        raise ValueError("embedding profile does not match this model family")
    if dimensions is not None and (type(dimensions) is not int or not 1 <= dimensions <= 8192):
        raise ValueError("embedding dimensions must be an integer between 1 and 8192")
    if resolved == "embeddinggemma-fact-checking-v1":
        if dimensions not in {None, 128, 256, 512, 768}:
            raise ValueError("EmbeddingGemma dimensions must be 128, 256, 512 or 768")
        dimensions = dimensions or 768
    return EmbeddingProfile(resolved, dimensions)
