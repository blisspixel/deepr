"""Typed belief-graph edge primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.experts.edge_temporal import normalize_temporal_context


def _utc_now() -> datetime:
    return datetime.now(UTC)


# Edge types for the typed belief graph (TKG step 2, see
# docs/design/temporal-knowledge-graph.md). "contradicts" is symmetric;
# the others are directed src -> dst.
EDGE_TYPES = ("supports", "contradicts", "enables", "derived_from")
_SYMMETRIC_EDGE_TYPES = ("contradicts",)
CONTRADICTION_MODEL_CONFIRMED = "model_confirmed"
CONTRADICTION_UNVERIFIED = "unverified"


@dataclass
class Edge:
    """A typed relationship between two beliefs.

    Provenance accumulates: re-asserting the same relationship from a new
    report adds provenance to the existing edge instead of duplicating it
    (the dedup policy from the TKG design doc).
    """

    src_id: str
    dst_id: str
    edge_type: str  # one of EDGE_TYPES
    provenance: list[str] = field(default_factory=list)
    temporal_contexts: list[dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)

    def key(self) -> tuple[str, str, str]:
        """Canonical identity. Symmetric types sort endpoints so A-B == B-A."""
        if self.edge_type in _SYMMETRIC_EDGE_TYPES:
            lo, hi = sorted((self.src_id, self.dst_id))
            return (lo, hi, self.edge_type)
        return (self.src_id, self.dst_id, self.edge_type)

    def touches(self, belief_id: str) -> bool:
        return belief_id in (self.src_id, self.dst_id)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "src_id": self.src_id,
            "dst_id": self.dst_id,
            "edge_type": self.edge_type,
            "provenance": list(self.provenance),
            "created_at": self.created_at.isoformat(),
        }
        if self.temporal_contexts:
            out["temporal_contexts"] = [dict(context) for context in self.temporal_contexts]
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        return cls(
            src_id=data["src_id"],
            dst_id=data["dst_id"],
            edge_type=data["edge_type"],
            provenance=list(data.get("provenance", [])),
            temporal_contexts=[
                normalized
                for raw in data.get("temporal_contexts", [])
                if (normalized := normalize_temporal_context(raw))
            ],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now(),
        )


def contradiction_verification(edge: Edge) -> str:
    """Return provenance-backed assurance for one contradiction edge.

    This classifies the verification process, not whether the claims truly
    contradict. Only explicit model-verification provenance is confirmed;
    migrated, manual, legacy, and lexical-router edges remain unverified.
    """
    if edge.edge_type != "contradicts":
        raise ValueError("contradiction verification requires a contradicts edge")
    if any(
        item == "contradiction_verification:model_confirmed" or item.startswith("claim_verification:")
        for item in edge.provenance
    ):
        return CONTRADICTION_MODEL_CONFIRMED
    return CONTRADICTION_UNVERIFIED


normalized_edge_temporal_context = normalize_temporal_context


__all__ = [
    "CONTRADICTION_MODEL_CONFIRMED",
    "CONTRADICTION_UNVERIFIED",
    "EDGE_TYPES",
    "Edge",
    "contradiction_verification",
    "normalized_edge_temporal_context",
]
