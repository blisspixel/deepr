"""Policy aware construction of the effective MCP tool surface."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepr.mcp.search.registry import ToolRegistry, ToolSchema
    from deepr.mcp.security.tool_allowlist import ToolAllowlist

_RESEARCH_MODE_VALUES = (
    "read_only",
    "standard",
    "extended",
    "unrestricted",
)


def explicit_research_mode_value() -> str | None:
    """Return an explicitly configured research mode or reject it exactly."""
    value = os.environ.get("DEEPR_RESEARCH_MODE")
    if value is not None and value not in _RESEARCH_MODE_VALUES:
        choices = ", ".join(_RESEARCH_MODE_VALUES)
        raise ValueError(f"DEEPR_RESEARCH_MODE must be one of: {choices}")
    return value


def advertise_full_tool_list_requested() -> bool:
    """Return whether standard clients should receive the full allowed catalog."""
    value = os.environ.get("DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST")
    if value not in (None, "0", "1"):
        raise ValueError("DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST must be 0 or 1")
    return value == "1"


def effective_tool_schemas(registry: ToolRegistry, allowlist: ToolAllowlist) -> list[ToolSchema]:
    """Return registered tools permitted by the active policy."""
    return [tool for tool in registry.all_tools() if allowlist.is_allowed(tool.name)]


def effective_tool_names(registry: ToolRegistry, allowlist: ToolAllowlist) -> set[str]:
    """Return names for the registered and policy permitted tool surface."""
    return {tool.name for tool in effective_tool_schemas(registry, allowlist)}


def build_tools_list(
    registry: ToolRegistry,
    allowlist: ToolAllowlist,
    *,
    use_gateway: bool,
) -> list[dict[str, object]]:
    """Build a policy filtered MCP tools list."""
    if use_gateway:
        gateway = registry.get("deepr_tool_search")
        if gateway is None or not allowlist.is_allowed(gateway.name):
            return []
        return [gateway.to_mcp_format()]
    return [tool.to_mcp_format() for tool in effective_tool_schemas(registry, allowlist)]


def register_bridge_tool_schemas(registry: ToolRegistry) -> None:
    """Register skill and durability tools implemented by the MCP bridge."""
    from deepr.mcp.search.registry import ToolSchema

    registry.register(
        ToolSchema(
            name="deepr_list_skills",
            description=(
                "List available and installed skills for an expert. Skills are domain-specific "
                "capability packages that give experts unique tools (e.g., financial ratios, "
                "code analysis). Pass expert_name to see installed vs available for that expert, "
                "or omit to see all available skills."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {
                        "type": "string",
                        "description": "Optional expert name to check installed skills",
                    },
                },
            },
            category="experts",
            cost_tier="free",
        )
    )
    registry.register(
        ToolSchema(
            name="deepr_get_task_progress",
            description="Get the persisted progress and latest checkpoint for a recoverable task.",
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Durable task identifier"},
                },
                "required": ["task_id"],
            },
            category="tasks",
            cost_tier="free",
        )
    )
    registry.register(
        ToolSchema(
            name="deepr_list_recoverable_tasks",
            description="List persisted tasks for a research job that can be resumed.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Research job identifier"},
                },
                "required": ["job_id"],
            },
            category="tasks",
            cost_tier="free",
        )
    )
    for name, action in (
        ("deepr_resume_task", "Resume a paused durable task from its latest checkpoint."),
        ("deepr_pause_task", "Pause a running durable task and retain its latest checkpoint."),
    ):
        registry.register(
            ToolSchema(
                name=name,
                description=action,
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Durable task identifier"},
                    },
                    "required": ["task_id"],
                },
                category="tasks",
                cost_tier="free",
            )
        )
    registry.register(
        ToolSchema(
            name="deepr_install_skill",
            description=(
                "Install a skill on an expert, giving it access to the skill's tools "
                "and domain-specific capabilities during chat."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expert_name": {
                        "type": "string",
                        "description": "Name of the expert to install the skill on",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to install (e.g., 'financial-data', 'code-analysis')",
                    },
                },
                "required": ["expert_name", "skill_name"],
            },
            category="experts",
            cost_tier="free",
        )
    )
