"""Web search tool implementation."""

import os
from typing import Any, Optional

import requests

from .base import Tool, ToolResult


class WebSearchTool(Tool):
    """
    Web search tool using multiple backends.

    Supports:
    - Brave Search API (recommended)
    - DuckDuckGo (free, no API key)
    - Tavily (alternative)
    - MCP servers (if available)
    """

    def __init__(
        self,
        backend: str = "auto",
        brave_api_key: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
    ):
        """
        Initialize web search tool.

        Args:
            backend: "brave", "duckduckgo", "tavily", or "auto" (try in order)
            brave_api_key: Brave Search API key (or BRAVE_API_KEY env)
            tavily_api_key: Tavily API key (or TAVILY_API_KEY env)
        """
        self.backend = backend
        self.brave_api_key = brave_api_key or os.getenv("BRAVE_API_KEY")
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information. Returns relevant search results with titles, URLs, and snippets."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, num_results: int = 5, **kwargs) -> ToolResult:
        """Execute web search."""

        # Try backends in order
        backends = ["brave", "tavily", "duckduckgo"] if self.backend == "auto" else [self.backend]

        for backend in backends:
            try:
                if backend == "brave" and self.brave_api_key:
                    return await self._search_brave(query, num_results)
                elif backend == "tavily" and self.tavily_api_key:
                    return await self._search_tavily(query, num_results)
                elif backend == "duckduckgo":
                    return await self._search_duckduckgo(query, num_results)
            except Exception:
                # Try next backend
                continue

        return ToolResult(
            success=False,
            data=None,
            error="No working web search backend available. Set BRAVE_API_KEY or TAVILY_API_KEY.",
        )

    async def _search_brave(self, query: str, num_results: int) -> ToolResult:
        """Search using Brave Search API."""
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {"Accept": "application/json", "X-Subscription-Token": self.brave_api_key}
        params = {"q": query, "count": num_results}

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        results = []

        for item in data.get("web", {}).get("results", [])[:num_results]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("description"),
                }
            )

        return ToolResult(success=True, data=results, metadata={"backend": "brave", "query": query})

    async def _search_tavily(self, query: str, num_results: int) -> ToolResult:
        """Search using Tavily API."""
        url = "https://api.tavily.com/search"
        payload = {"api_key": self.tavily_api_key, "query": query, "max_results": num_results}

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        data = response.json()
        results = []

        for item in data.get("results", [])[:num_results]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content"),
                }
            )

        return ToolResult(success=True, data=results, metadata={"backend": "tavily", "query": query})

    async def _search_duckduckgo(self, query: str, num_results: int) -> ToolResult:
        """
        Search using DuckDuckGo (free, no API key).

        Note: Uses duckduckgo-search library if installed.
        """
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query, max_results=num_results):
                    results.append(
                        {
                            "title": r.get("title"),
                            "url": r.get("href"),
                            "snippet": r.get("body"),
                        }
                    )

                return ToolResult(success=True, data=results, metadata={"backend": "duckduckgo", "query": query})
        except ImportError:
            return ToolResult(
                success=False, data=None, error="duckduckgo-search not installed. Run: pip install duckduckgo-search"
            )


class MCPWebSearchTool(Tool):
    """
    Web search via MCP server.

    Uses local MCP server if available (e.g., Claude Code's fetch tool).
    """

    @property
    def name(self) -> str:
        return "mcp_web_search"

    @property
    def description(self) -> str:
        return "Search the web using local MCP server."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        }

    async def execute(self, query: str, **kwargs) -> ToolResult:
        """Execute MCP web search."""
        # TODO: Integrate with MCP server
        # This would call Claude Code's WebFetch tool or similar
        return ToolResult(success=False, data=None, error="MCP integration not yet implemented")
