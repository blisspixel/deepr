"""MCP client infrastructure for outbound connections to MCP servers.

Deepr can act as both MCP server (providing tools to other agents) and
MCP client (consuming tools from external MCP servers).
"""

from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult
from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.config_loader import ConfigLoader
from deepr.mcp.client.errors import BudgetDecision, MCPErrorCode, StructuredError
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.client.progress_notifier import ProgressEvent, ProgressNotifier
from deepr.mcp.client.trace_stitcher import SpanContext, TraceStitcher

__all__ = [
    "BudgetDecision",
    "BudgetPropagator",
    "ConfigLoader",
    "MCPClient",
    "MCPClientError",
    "MCPClientPool",
    "MCPClientProfile",
    "MCPErrorCode",
    "MCPToolResult",
    "ProgressEvent",
    "ProgressNotifier",
    "SpanContext",
    "StructuredError",
    "TraceStitcher",
]
