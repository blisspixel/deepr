"""Tool registry for default tools."""

from typing import List

from .base import Tool, ToolExecutor
from .web_search import WebSearchTool


class ToolRegistry:
    """
    Central registry for default tools.

    Makes it easy to get standard tool sets for providers.
    """

    @staticmethod
    def get_default_tools(
        web_search: bool = True,
        backend: str = "auto",
    ) -> List[Tool]:
        """
        Get default tool set.

        Args:
            web_search: Include web search tool
            backend: Web search backend ("brave", "tavily", "duckduckgo", "auto")

        Returns:
            List of configured tools
        """
        tools = []

        if web_search:
            tools.append(WebSearchTool(backend=backend))

        return tools

    @staticmethod
    def create_executor(
        web_search: bool = True,
        backend: str = "auto",
    ) -> ToolExecutor:
        """
        Create tool executor with default tools.

        Args:
            web_search: Include web search tool
            backend: Web search backend

        Returns:
            Configured ToolExecutor
        """
        tools = ToolRegistry.get_default_tools(web_search=web_search, backend=backend)
        return ToolExecutor(tools=tools)
