"""MCP prompt template definitions and rendering.

Provides reusable prompt templates for research workflows,
expert consultation, and sector analysis.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Placeholder pattern: {{name}}
_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class PromptTemplate:
    """A reusable prompt template with named placeholders."""

    name: str
    description: str
    template: str
    parameters: list[str] = field(default_factory=list)


# Built-in prompt templates
_TEMPLATES: dict[str, PromptTemplate] = {
    "research-workflow": PromptTemplate(
        name="research-workflow",
        description="Guided research with budget and expert selection",
        template=(
            "Research workflow for {{topic}}.\n"
            "Budget: ${{budget}}\n"
            "Expert: {{expert}}\n"
            "Depth: {{depth}}\n"
            "Focus on key findings and actionable insights."
        ),
        parameters=["topic", "budget", "expert", "depth"],
    ),
    "expert-consult": PromptTemplate(
        name="expert-consult",
        description="Structured expert question",
        template=(
            "Expert consultation request:\n"
            "Expert: {{expert}}\n"
            "Question: {{question}}\n"
            "Context: {{context}}\n"
            "Please provide a structured analysis with confidence levels."
        ),
        parameters=["expert", "question", "context"],
    ),
    "sector-analysis": PromptTemplate(
        name="sector-analysis",
        description="Multi-company sector mapping",
        template=(
            "Sector analysis for {{sector}}.\n"
            "Companies: {{companies}}\n"
            "Timeframe: {{timeframe}}\n"
            "Compare market positions, growth trajectories, and competitive dynamics."
        ),
        parameters=["sector", "companies", "timeframe"],
    ),
}


class PromptRenderer:
    """Render prompt templates with argument substitution.

    Substitutes {{name}} placeholders with provided argument values.
    Unresolved placeholders for provided arguments are guaranteed to
    not appear in the output.

    Usage::

        renderer = PromptRenderer()
        result = renderer.render("research-workflow", {
            "topic": "AI market",
            "budget": "5.00",
            "expert": "analyst",
            "depth": "deep",
        })
    """

    def __init__(self, extra_templates: dict[str, PromptTemplate] | None = None) -> None:
        self._templates = dict(_TEMPLATES)
        if extra_templates:
            self._templates.update(extra_templates)

    def render(self, template_name: str, arguments: dict[str, str]) -> str:
        """Render a prompt template with argument substitution.

        Args:
            template_name: Name of the template to render.
            arguments: Key-value pairs for placeholder substitution.

        Returns:
            Rendered prompt string.

        Raises:
            KeyError: If template_name is not found.
        """
        template = self._templates.get(template_name)
        if template is None:
            raise KeyError(f"Unknown prompt template: {template_name}")

        result = template.template
        for key, value in arguments.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))

        return result

    def list_templates(self) -> list[dict[str, Any]]:
        """List all available prompt templates."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._templates.values()
        ]

    def get_template(self, name: str) -> PromptTemplate | None:
        """Get a template by name."""
        return self._templates.get(name)

    def has_template(self, name: str) -> bool:
        """Check if a template exists."""
        return name in self._templates
