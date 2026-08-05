"""Belief-store claim inventory for honest expert listings ($0, no model).

Absorb and local paths populate belief claims without creating vector-store
documents. Surfaces that report only ``Documents`` therefore render a populated
expert as empty, which made hosts skip consults against real knowledge. Every
inventory surface should read claim counts through here so the CLI, MCP, and
web renderings cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClaimInventory:
    """Structural inventory counts. Carries no judgment about quality."""

    claim_count: int = 0
    avg_confidence: float | None = None
    manifest_available: bool = False

    @property
    def is_empty(self) -> bool:
        """True only when the manifest was read and reported no claims.

        An unreadable manifest is unknown, not empty. Reporting unknown as
        empty is the failure this module exists to prevent.
        """
        return self.manifest_available and self.claim_count == 0


def _coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_FRESHNESS_COLORS = {"fresh": "green", "recent": "yellow"}


def format_knowledge_status(expert: Any, inventory: ClaimInventory) -> str:
    """Rich-markup knowledge line for listing surfaces.

    Freshness wins when a cutoff date exists; otherwise claims stand in for it,
    so an absorbed expert with zero vector-store documents never renders as
    having no knowledge.
    """
    if getattr(expert, "knowledge_cutoff_date", None):
        freshness = expert.get_freshness_status()
        status = freshness.get("status", "unknown")
        color = _FRESHNESS_COLORS.get(status, "red")
        return f"{freshness.get('age_days', 0)} days old [{color}]{status}[/{color}]"
    if inventory.claim_count > 0:
        return (
            f"[green]{inventory.claim_count} claim(s) in belief store[/green] "
            "[dim](Documents may be 0 after absorb --file)[/dim]"
        )
    return "[yellow]incomplete - no claims or verified documents yet[/yellow]"


def read_claim_inventory(expert: Any) -> ClaimInventory:
    """Read claim counts from an expert profile's belief-store manifest.

    Never raises: a manifest that cannot be read yields ``manifest_available``
    False so callers can distinguish unknown from empty.
    """
    get_manifest = getattr(expert, "get_manifest", None)
    if not callable(get_manifest):
        return ClaimInventory()
    try:
        manifest = get_manifest()
    except Exception:
        return ClaimInventory()
    return ClaimInventory(
        claim_count=int(getattr(manifest, "claim_count", 0) or 0),
        avg_confidence=_coerce_confidence(getattr(manifest, "avg_confidence", None)),
        manifest_available=True,
    )
