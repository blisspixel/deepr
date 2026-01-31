"""
Gateway Tool for Dynamic Tool Discovery.

This module implements the single gateway tool that is exposed by default,
enabling ~85% context reduction by loading tool schemas on demand.
"""

from typing import Optional
from .registry import ToolRegistry, ToolSchema


class GatewayTool:
    """
    The gateway tool that enables dynamic tool discovery.
    
    This is the ONLY tool exposed by default in list_tools.
    All other tools are discovered through this gateway.
    """
    
    SCHEMA = ToolSchema(
        name="deepr_tool_search",
        description=(
            "Search Deepr capabilities by natural language query. "
            "Returns relevant tool schemas for research, experts, and agentic workflows. "
            "Use this to discover what Deepr can do before calling specific tools."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of desired capability"
                },
                "limit": {
                    "type": "integer",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Maximum number of tools to return"
                }
            },
            "required": ["query"]
        },
        category="discovery",
        cost_tier="free"
    )
    
    def __init__(self, registry: ToolRegistry):
        """
        Initialize gateway with tool registry.
        
        Args:
            registry: ToolRegistry containing all searchable tools
        """
        self._registry = registry
    
    def search(self, query: str, limit: int = 3) -> dict:
        """
        Search for tools matching the query.
        
        Args:
            query: Natural language description of desired capability
            limit: Maximum tools to return (1-10)
        
        Returns:
            Dict with tools array and metadata
        """
        if not query or not query.strip():
            return {
                "error": "Query cannot be empty",
                "tools": [],
                "total_available": self._registry.count()
            }
        
        # Clamp limit
        limit = max(1, min(10, limit))
        
        # Search registry
        matches = self._registry.search(query, limit=limit)
        
        # Format results
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "category": tool.category,
                "cost_tier": tool.cost_tier
            }
            for tool in matches
        ]
        
        return {
            "tools": tools,
            "count": len(tools),
            "total_available": self._registry.count(),
            "query": query,
            "message": self._generate_message(tools, query)
        }
    
    def _generate_message(self, tools: list[dict], query: str) -> str:
        """Generate helpful message based on search results."""
        if not tools:
            return (
                f"No tools found matching '{query}'. "
                "Try broader terms like 'research', 'expert', or 'agentic'."
            )
        
        if len(tools) == 1:
            return f"Found 1 tool matching '{query}'. Use it directly with the schema provided."
        
        return (
            f"Found {len(tools)} tools matching '{query}'. "
            "Review the descriptions and choose the most appropriate one."
        )
    
    @classmethod
    def get_gateway_schema(cls) -> dict:
        """Get the MCP-formatted schema for the gateway tool."""
        return cls.SCHEMA.to_mcp_format()
    
    def estimate_context_savings(self) -> dict:
        """
        Estimate context savings from using gateway pattern.
        
        Returns:
            Dict with token estimates and savings percentage
        """
        all_tools_tokens = self._registry.estimate_tokens()
        gateway_tokens = self._registry.estimate_tokens([self.SCHEMA])
        
        # After typical search (3 tools)
        typical_search = self._registry.search("research", limit=3)
        search_result_tokens = self._registry.estimate_tokens(typical_search)
        
        total_with_gateway = gateway_tokens + search_result_tokens
        savings = (all_tools_tokens - total_with_gateway) / max(all_tools_tokens, 1)
        
        return {
            "all_tools_tokens": all_tools_tokens,
            "gateway_only_tokens": gateway_tokens,
            "typical_search_tokens": search_result_tokens,
            "total_with_gateway": total_with_gateway,
            "savings_percentage": round(savings * 100, 1)
        }
