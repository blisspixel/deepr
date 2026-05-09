"""MCP resource handlers for expert state exposure.

Exposes expert knowledge, gaps, and cost summaries as read-only
MCP resources with URI-based routing.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ExpertStateProtocol(Protocol):
    """Protocol for reading expert state."""

    def get_expert_names(self) -> list[str]:
        """Return list of registered expert names."""
        ...

    def get_knowledge(self, name: str) -> dict[str, Any]:
        """Return knowledge state for an expert."""
        ...

    def get_gaps(self, name: str) -> list[dict[str, Any]]:
        """Return knowledge gaps for an expert."""
        ...


class CostStateProtocol(Protocol):
    """Protocol for reading cost state."""

    def get_daily_spend(self) -> float:
        ...

    def get_monthly_spend(self) -> float:
        ...

    def get_remaining_budget(self) -> float:
        ...

    def get_active_job_count(self) -> int:
        ...


@dataclass
class ResourceResult:
    """Result from a resource handler."""

    uri: str
    content: Any
    mime_type: str = "application/json"


@dataclass
class ExpertKnowledge:
    """Expert knowledge summary for resource exposure."""

    claim_count: int = 0
    average_confidence: float = 0.0
    last_updated: str = ""


@dataclass
class ExpertGap:
    """A knowledge gap with priority score."""

    description: str
    category: str
    priority: float = 0.0


class ResourceHandler:
    """Handle MCP resource URI requests.

    Supported URIs:
    - deepr://experts/list
    - deepr://experts/{name}/knowledge
    - deepr://experts/{name}/gaps
    - deepr://costs/summary

    Usage::

        handler = ResourceHandler(expert_state=my_state, cost_state=my_costs)
        result = handler.handle("deepr://experts/list")
    """

    def __init__(
        self,
        expert_state: ExpertStateProtocol | None = None,
        cost_state: CostStateProtocol | None = None,
    ) -> None:
        self._expert_state = expert_state
        self._cost_state = cost_state
        self._change_callbacks: list[Any] = []

    def handle(self, uri: str) -> ResourceResult | None:
        """Route a resource URI to the appropriate handler.

        Returns None if the URI is not recognized.
        """
        if uri == "deepr://experts/list":
            return self._handle_experts_list()

        if uri.startswith("deepr://experts/") and uri.endswith("/knowledge"):
            name = uri.replace("deepr://experts/", "").replace("/knowledge", "")
            return self._handle_expert_knowledge(name)

        if uri.startswith("deepr://experts/") and uri.endswith("/gaps"):
            name = uri.replace("deepr://experts/", "").replace("/gaps", "")
            return self._handle_expert_gaps(name)

        if uri == "deepr://costs/summary":
            return self._handle_costs_summary()

        return None

    def _handle_experts_list(self) -> ResourceResult:
        """Return list of registered experts."""
        if self._expert_state is None:
            return ResourceResult(uri="deepr://experts/list", content=[])

        names = self._expert_state.get_expert_names()
        return ResourceResult(uri="deepr://experts/list", content=names)

    def _handle_expert_knowledge(self, name: str) -> ResourceResult:
        """Return knowledge state for an expert."""
        uri = f"deepr://experts/{name}/knowledge"
        if self._expert_state is None:
            return ResourceResult(uri=uri, content={})

        knowledge = self._expert_state.get_knowledge(name)
        return ResourceResult(uri=uri, content=knowledge)

    def _handle_expert_gaps(self, name: str) -> ResourceResult:
        """Return gaps sorted by priority descending."""
        uri = f"deepr://experts/{name}/gaps"
        if self._expert_state is None:
            return ResourceResult(uri=uri, content=[])

        gaps = self._expert_state.get_gaps(name)
        # Sort by priority descending
        sorted_gaps = sorted(gaps, key=lambda g: g.get("priority", 0), reverse=True)
        return ResourceResult(uri=uri, content=sorted_gaps)

    def _handle_costs_summary(self) -> ResourceResult:
        """Return cost summary."""
        if self._cost_state is None:
            return ResourceResult(
                uri="deepr://costs/summary",
                content={
                    "daily_spend": 0.0,
                    "monthly_spend": 0.0,
                    "remaining_budget": 0.0,
                    "active_job_count": 0,
                },
            )

        return ResourceResult(
            uri="deepr://costs/summary",
            content={
                "daily_spend": self._cost_state.get_daily_spend(),
                "monthly_spend": self._cost_state.get_monthly_spend(),
                "remaining_budget": self._cost_state.get_remaining_budget(),
                "active_job_count": self._cost_state.get_active_job_count(),
            },
        )

    def list_resources(self) -> list[str]:
        """List all available resource URIs."""
        uris = ["deepr://experts/list", "deepr://costs/summary"]
        if self._expert_state:
            for name in self._expert_state.get_expert_names():
                uris.append(f"deepr://experts/{name}/knowledge")
                uris.append(f"deepr://experts/{name}/gaps")
        return uris
