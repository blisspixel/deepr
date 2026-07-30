"""Fail-closed execution boundary for expert skill tools.

Skill manifests are inventory, not spend authority. A Python function or MCP
subprocess can make arbitrary provider calls that Deepr cannot constrain from
the manifest's cost tier, budget argument, or self-reported result. Until skill
tools run inside a boundary that can prove network and credential confinement,
all executable tool types remain quarantined.
"""

from __future__ import annotations

import math
from typing import Any

from deepr.experts.skills.definition import SkillDefinition, SkillTool

SKILL_TOOL_EXECUTION_DISABLED = "SKILL_TOOL_EXECUTION_DISABLED"


def _blocked_result(tool: SkillTool) -> dict[str, Any]:
    """Return the stable no-dispatch result for an inventoried skill tool."""
    return {
        "error": SKILL_TOOL_EXECUTION_DISABLED,
        "status": "blocked",
        "detail": (
            "Skill tool execution is quarantined because arbitrary Python and MCP tools "
            "can incur external spend that manifest estimates and self-reported costs "
            "cannot enforce. Skill inventory and inspection remain available."
        ),
        "tool_type": tool.type,
        "cost": 0.0,
    }


class SkillExecutor:
    """Preserve the skill execution contract while refusing every dispatch.

    ``allow_metered_tools`` remains accepted for compatibility, but it is not
    spend authority and cannot override the quarantine.
    """

    def __init__(
        self,
        skill: SkillDefinition,
        budget_remaining: float,
        *,
        allow_metered_tools: bool = False,
    ) -> None:
        if (
            isinstance(budget_remaining, bool)
            or not isinstance(budget_remaining, (int, float))
            or not math.isfinite(budget_remaining)
            or budget_remaining < 0
        ):
            raise ValueError("budget_remaining must be a finite non-negative number")
        self._skill = skill
        self._budget_remaining = float(budget_remaining)
        self._allow_metered_tools = allow_metered_tools
        self._tool_map: dict[str, SkillTool] = {tool.name: tool for tool in skill.tools}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Refuse execution before importing code, spawning, or reserving spend."""
        del arguments
        tool = self._tool_map.get(tool_name)
        if tool is None:
            return {"error": f"Unknown tool: {tool_name}", "cost": 0.0}
        return _blocked_result(tool)

    async def cleanup(self) -> None:
        """Retain the async lifecycle API; quarantine creates no resources."""
