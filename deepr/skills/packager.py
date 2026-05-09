"""SKILL.md generation for agentskills.io export.

Generates portable SKILL.md files that describe Deepr's MCP tools
in a format compatible with other agent frameworks.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from deepr.skills.templates import (
    DEFAULT_INSTRUCTIONS,
    DEFAULT_TRIGGERS,
    FRONTMATTER_TEMPLATE,
    INSTRUCTIONS_TEMPLATE,
    SKILL_TEMPLATE,
    TOOL_ENTRY_TEMPLATE,
    TOOLS_TEMPLATE,
    TRIGGERS_TEMPLATE,
    ToolManifest,
)

logger = logging.getLogger(__name__)


class SkillPackager:
    """Generate SKILL.md files from registered MCP tools.

    Exports Deepr's expert capabilities as agentskills.io SKILL.md
    files for interoperability with other agent frameworks.

    Usage::

        packager = SkillPackager(
            name="deepr-research",
            description="Research automation tools",
            version="2.10.0",
            mcp_server="deepr",
        )
        packager.add_tool(ToolManifest(name="domain_lookup", description="..."))
        path = packager.generate(Path("./output"))
    """

    def __init__(
        self,
        name: str = "deepr-research",
        description: str = "Multi-provider research automation tools",
        version: str = "",
        mcp_server: str = "deepr",
        triggers: list[str] | None = None,
        instructions: str = "",
    ) -> None:
        self._name = name
        self._description = description
        self._version = version
        self._mcp_server = mcp_server
        self._triggers = triggers or list(DEFAULT_TRIGGERS)
        self._instructions = instructions or DEFAULT_INSTRUCTIONS
        self._tools: list[ToolManifest] = []

    def add_tool(self, tool: ToolManifest) -> None:
        """Add a tool to the manifest."""
        self._tools.append(tool)

    def add_tools(self, tools: list[ToolManifest]) -> None:
        """Add multiple tools to the manifest."""
        self._tools.extend(tools)

    def get_tools_manifest(self) -> list[ToolManifest]:
        """Get all registered tools."""
        return list(self._tools)

    def generate(self, output_dir: Path) -> Path:
        """Generate SKILL.md file and return its path.

        Args:
            output_dir: Directory to write SKILL.md to.

        Returns:
            Path to the generated SKILL.md file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "SKILL.md"

        content = self._render()
        output_path.write_text(content, encoding="utf-8")

        logger.info("Generated SKILL.md at %s (%d tools)", output_path, len(self._tools))
        return output_path

    def render(self) -> str:
        """Render the SKILL.md content as a string."""
        return self._render()

    def _render(self) -> str:
        """Render the full SKILL.md content."""
        frontmatter = FRONTMATTER_TEMPLATE.format(
            name=self._name,
            description=self._description,
            version=self._version,
            mcp_server=self._mcp_server,
        )

        tools_section = self._render_tools()
        triggers_section = self._render_triggers()
        instructions_section = INSTRUCTIONS_TEMPLATE.format(
            instructions=self._instructions,
        )

        return SKILL_TEMPLATE.format(
            frontmatter=frontmatter,
            name=self._name,
            description=self._description,
            tools_section=tools_section,
            triggers_section=triggers_section,
            instructions_section=instructions_section,
        )

    def _render_tools(self) -> str:
        """Render the tools section."""
        if not self._tools:
            return TOOLS_TEMPLATE.format(tools_list="No tools registered.")

        entries = []
        for tool in self._tools:
            params = self._format_parameters(tool.parameters)
            entry = TOOL_ENTRY_TEMPLATE.format(
                name=tool.name,
                description=tool.description,
                parameters=params,
            )
            entries.append(entry)

        return TOOLS_TEMPLATE.format(tools_list="\n".join(entries))

    def _render_triggers(self) -> str:
        """Render the triggers section."""
        triggers_list = "\n".join(f"- {t}" for t in self._triggers)
        return TRIGGERS_TEMPLATE.format(triggers_list=triggers_list)

    def _format_parameters(self, params: dict[str, Any]) -> str:
        """Format parameter schema as markdown."""
        if not params:
            return "None"

        lines = []
        properties = params.get("properties", params)
        for name, schema in properties.items():
            if isinstance(schema, dict):
                type_str = schema.get("type", "any")
                desc = schema.get("description", "")
                lines.append(f"- `{name}` ({type_str}): {desc}")
            else:
                lines.append(f"- `{name}`: {schema}")

        return "\n".join(lines) if lines else "None"
