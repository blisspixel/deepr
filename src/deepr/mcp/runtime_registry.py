"""Pure construction of the complete Deepr MCP runtime tool registry."""

from __future__ import annotations

from deepr.mcp.consult_tool import CONSULT_EXPERTS_INPUT_SCHEMA, CONSULT_EXPERTS_OUTPUT_SCHEMA
from deepr.mcp.search.gateway import GatewayTool
from deepr.mcp.search.registry import ToolRegistry, ToolSchema, create_default_registry
from deepr.mcp.tool_surface import register_bridge_tool_schemas


def create_runtime_registry() -> ToolRegistry:
    """Build the authoritative registry advertised by the MCP server."""
    registry = create_default_registry()
    registry.register(
        ToolSchema(
            name="deepr_status",
            description=(
                "Health check for the Deepr MCP server. Returns version, uptime, "
                "active jobs count, daily/monthly cost summary, and available capabilities. "
                "Use this to verify the server is running and check spending before starting research."
            ),
            input_schema={"type": "object", "properties": {}},
            category="system",
            cost_tier="free",
        )
    )
    registry.register(
        ToolSchema(
            name="deepr_cancel_job",
            description=(
                "Cancel a running research job. Use when the user wants to stop an "
                "in-progress research task. Cannot cancel already completed or failed jobs."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Job ID from deepr_research or deepr_agentic_research",
                    },
                },
                "required": ["job_id"],
            },
            category="research",
            cost_tier="free",
        )
    )
    registry.register(GatewayTool.SCHEMA)
    registry.register(
        ToolSchema(
            name="deepr_consult_experts",
            description=(
                "Consult a TEAM of domain experts on a question and get one synthesized, "
                "calibrated answer (the deepr-consult-v1 artifact: answer, each expert's "
                "perspective with confidence, points of agreement and dissent, and cost). "
                "Routes to the most relevant experts automatically, or pass 'experts' to name "
                "them. One bounded knowledge transaction - Deepr recommends; your harness "
                "decides and enacts."
            ),
            input_schema=CONSULT_EXPERTS_INPUT_SCHEMA,
            output_schema=CONSULT_EXPERTS_OUTPUT_SCHEMA,
            category="experts",
            cost_tier="low",
        )
    )

    from deepr.mcp.expert_conversation import register_conversation_tools

    register_conversation_tools(registry)
    register_bridge_tool_schemas(registry)
    return registry


__all__ = ["create_runtime_registry"]
