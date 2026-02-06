"""
Unified tool system for Deepr providers.

Provides web search, document access, and MCP integration for AI agents.
"""

from .base import Tool, ToolExecutor, ToolResult
from .registry import ToolRegistry
from .web_search import WebSearchTool

__all__ = [
    "Tool",
    "ToolExecutor",
    "ToolRegistry",
    "ToolResult",
    "WebSearchTool",
]
