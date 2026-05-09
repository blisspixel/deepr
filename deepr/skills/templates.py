"""SKILL.md template strings for agentskills.io export.

Defines the template structure for generating SKILL.md files
that describe Deepr's MCP tools in a portable format.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolManifest:
    """Manifest entry for a single MCP tool."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


# Frontmatter template
FRONTMATTER_TEMPLATE = """\
---
name: {name}
description: {description}
version: {version}
mcp_server: {mcp_server}
---
"""

# Tools section template
TOOLS_TEMPLATE = """\
## Tools

{tools_list}
"""

# Single tool entry template
TOOL_ENTRY_TEMPLATE = """\
### {name}

{description}

**Parameters:**
{parameters}
"""

# Triggers section template
TRIGGERS_TEMPLATE = """\
## Triggers

{triggers_list}
"""

# Instructions section template
INSTRUCTIONS_TEMPLATE = """\
## Instructions

{instructions}
"""

# Full SKILL.md template
SKILL_TEMPLATE = """\
{frontmatter}
# {name}

{description}

{tools_section}
{triggers_section}
{instructions_section}
"""

# Default trigger keywords for research-related skills
DEFAULT_TRIGGERS = [
    "research",
    "analyze",
    "investigate",
    "company",
    "domain",
    "market",
    "sector",
    "competitive",
    "intelligence",
]

# Default instructions
DEFAULT_INSTRUCTIONS = (
    "Use this skill when conducting research that requires external data sources. "
    "The skill provides access to MCP tools for domain lookup, data ingestion, "
    "and analysis. Respect budget limits and approval requirements."
)
