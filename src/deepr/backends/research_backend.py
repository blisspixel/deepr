"""Typed research-backend profiles for capacity-aware routing.

Capacity detection answers what appears available on this machine. A
``ResearchBackend`` is the normalized profile above that detector: stable
identity, cost model, task eligibility, and whether quota observations are
required before a backend can be trusted by the waterfall.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from deepr.backends.capacity import BackendKind, CapacitySource, CostModel, detect_capacity


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "backend"


def _source_backend_id(source: CapacitySource) -> str:
    return source.backend_id or _slug(source.name)


@dataclass(frozen=True)
class ResearchBackend:
    """A capacity source normalized for routing, logs, and quota decisions."""

    backend_id: str
    name: str
    kind: BackendKind
    cost_model: CostModel
    available: bool
    detail: str = ""
    task_classes: tuple[str, ...] = ()
    requires_quota_ledger: bool = False
    allow_paid_fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_metered(self) -> bool:
        return self.kind == BackendKind.API_METERED or self.cost_model == CostModel.METERED

    @property
    def is_owned_or_prepaid(self) -> bool:
        return not self.is_metered

    def supports_task(self, task_class: str) -> bool:
        """Return whether this profile allows ``task_class``.

        An empty task-class tuple means the profile itself is unrestricted. A
        concrete adapter or admission gate may still reject execution.
        """
        return not self.task_classes or task_class in self.task_classes

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "name": self.name,
            "kind": self.kind.value,
            "cost_model": self.cost_model.value,
            "available": self.available,
            "detail": self.detail,
            "task_classes": list(self.task_classes),
            "requires_quota_ledger": self.requires_quota_ledger,
            "allow_paid_fallback": self.allow_paid_fallback,
            "is_metered": self.is_metered,
            "metadata": self.metadata,
        }


def backend_from_capacity_source(source: CapacitySource) -> ResearchBackend:
    """Normalize a detected capacity source into a router-facing profile."""
    requires_quota = source.kind == BackendKind.PLAN_QUOTA
    return ResearchBackend(
        backend_id=_source_backend_id(source),
        name=source.name,
        kind=source.kind,
        cost_model=source.cost_model,
        available=source.available,
        detail=source.detail,
        requires_quota_ledger=requires_quota,
        allow_paid_fallback=False,
        metadata={"marginal_cost": source.marginal_cost},
    )


def discover_research_backends(**detect_kwargs: Any) -> list[ResearchBackend]:
    """Detect capacity sources and return normalized backend profiles."""
    return [backend_from_capacity_source(source) for source in detect_capacity(**detect_kwargs)]
