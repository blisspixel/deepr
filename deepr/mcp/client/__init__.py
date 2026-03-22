"""MCP client infrastructure for outbound connections to MCP servers.

Deepr can act as both MCP server (providing tools to other agents) and
MCP client (consuming tools from external MCP servers).
"""

from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile

__all__ = [
    "MCPClient",
    "MCPClientError",
    "MCPClientPool",
    "MCPClientProfile",
    "MCPToolResult",
]
