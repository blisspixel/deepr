"""
Unified tool system for Deepr providers.

Provides web search, document access, and MCP integration for AI agents.
"""

from .base import Tool, ToolExecutor, ToolResult
from .web_search import WebSearchTool
from .registry import ToolRegistry

__all__ = [
    "Tool",
    "ToolExecutor",
    "ToolResult",
    "WebSearchTool",
    "ToolRegistry",
]
