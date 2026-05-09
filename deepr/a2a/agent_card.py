"""Agent card generation for A2A protocol.

Builds an AgentCard from registered experts, exposing each expert
as a discoverable skill.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from deepr.a2a.models import AgentCard, AgentSkill

logger = logging.getLogger(__name__)


@dataclass
class ExpertInfo:
    """Minimal expert information for card generation."""

    name: str
    description: str = ""
    domain: str = ""


class AgentCardGenerator:
    """Generate an AgentCard from registered experts.

    Each expert becomes a skill entry in the agent card with
    name, description, and domain fields.

    Usage::

        generator = AgentCardGenerator(version="2.10.0", url="http://localhost:8080")
        generator.register_expert(ExpertInfo(name="recon", description="DNS recon", domain="infrastructure"))
        card = generator.generate()
    """

    def __init__(
        self,
        version: str = "",
        url: str = "",
        name: str = "deepr",
        description: str = "",
    ) -> None:
        self._version = version
        self._url = url
        self._name = name
        self._description = description or ("Multi-provider research automation with persistent expert agents")
        self._experts: list[ExpertInfo] = []

    def register_expert(self, expert: ExpertInfo) -> None:
        """Register an expert for inclusion in the agent card."""
        self._experts.append(expert)
        logger.debug("Registered expert '%s' for agent card", expert.name)

    def register_experts(self, experts: list[ExpertInfo]) -> None:
        """Register multiple experts at once."""
        for expert in experts:
            self.register_expert(expert)

    def generate(self) -> AgentCard:
        """Generate an AgentCard from all registered experts.

        Each expert becomes one skill entry with name, description, domain.
        """
        skills = [
            AgentSkill(
                name=expert.name,
                description=expert.description,
                domain=expert.domain,
            )
            for expert in self._experts
        ]

        return AgentCard(
            name=self._name,
            description=self._description,
            version=self._version,
            url=self._url,
            skills=skills,
        )

    @property
    def expert_count(self) -> int:
        """Number of registered experts."""
        return len(self._experts)

    def to_dict(self) -> dict[str, Any]:
        """Generate agent card as a dict (for JSON serialization)."""
        return self.generate().to_dict()
