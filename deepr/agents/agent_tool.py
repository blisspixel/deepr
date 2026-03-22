"""Wrap SubagentContract implementations as OpenAI-compatible tool definitions.

This allows a planner agent to invoke worker agents the same way it invokes
any other tool (search_knowledge_base, deep_research, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from deepr.agents.contract import (
    AgentBudget,
    AgentIdentity,
    AgentResult,
    AgentRole,
    AgentStatus,
    SubagentContract,
)

logger = logging.getLogger(__name__)


class AgentTool:
    """Wraps a SubagentContract as an OpenAI function-calling tool.

    The tool schema exposes a ``query`` parameter. When called, it
    creates a child identity, allocates a budget slice from the parent,
    and delegates to the underlying agent.
    """

    def __init__(
        self,
        name: str,
        description: str,
        agent: SubagentContract,
        budget_limit: float = 5.0,
    ):
        self.name = name
        self.description = description
        self.agent = agent
        self.budget_limit = budget_limit

    def to_openai_tool(self) -> dict[str, Any]:
        """Return an OpenAI-compatible tool definition dict."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The query or task for this agent to handle.",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(
        self,
        arguments: dict[str, Any] | str,
        parent_identity: AgentIdentity,
    ) -> AgentResult:
        """Execute the wrapped agent with a child identity and budget slice.

        Args:
            arguments: Tool call arguments (dict or JSON string with 'query' key).
            parent_identity: The calling agent's identity for trace propagation.

        Returns:
            AgentResult from the delegated execution.
        """
        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        query = arguments.get("query")
        if not query:
            return AgentResult(
                agent_id=parent_identity.agent_id,
                trace_id=parent_identity.trace_id,
                output="Missing required 'query' parameter",
                status=AgentStatus.FAILED,
                metadata={"error": "missing_query"},
            )
        child_identity = parent_identity.child(
            role=AgentRole.WORKER,
            name=f"tool-{self.name}",
        )
        budget = AgentBudget(max_cost=self.budget_limit)

        try:
            result = await self.agent.execute(query, budget, child_identity)
            return result
        except Exception as e:
            logger.warning("AgentTool %s failed: %s", self.name, e)
            return AgentResult(
                agent_id=child_identity.agent_id,
                trace_id=child_identity.trace_id,
                output=f"Agent tool failed: {e}",
                cost=budget.cost_accumulated,
                status=AgentStatus.FAILED,
                metadata={"error": str(e)},
            )
