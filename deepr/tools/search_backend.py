"""
Search Backend Abstraction for MCP Client Mode.

Defines the SearchBackend protocol that allows swapping between
the built-in search implementation and external MCP search servers
(Brave Search, Tavily, Google Custom Search, etc.).

STATUS: Interface definitions only. MCP client connections not implemented.
See docs/mcp-client-architecture.md for the full design.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SearchResult:
    """A single search result."""

    title: str
    url: str
    snippet: str
    score: float = 0.0
    source: str = "unknown"


@runtime_checkable
class SearchBackend(Protocol):
    """Protocol for search backends.

    Implementations can be:
    - BuiltinSearchBackend: wraps deepr's existing WebSearchTool
    - MCPSearchBackend: delegates to an MCP search server (not yet implemented)
    """

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Execute a search query.

        Args:
            query: Search query string
            num_results: Maximum number of results to return

        Returns:
            List of search results ordered by relevance
        """
        ...

    async def health_check(self) -> bool:
        """Check if the backend is available and healthy."""
        ...

    @property
    def name(self) -> str:
        """Backend identifier (e.g., 'builtin', 'brave-mcp', 'tavily-mcp')."""
        ...


class BuiltinSearchBackend:
    """Search backend using Deepr's built-in web search.

    Wraps the existing WebSearchTool to conform to the SearchBackend protocol.
    """

    @property
    def name(self) -> str:
        return "builtin"

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Search using built-in web search."""
        try:
            from deepr.tools.web_search import WebSearchTool

            tool = WebSearchTool()
            result = await tool.execute({"query": query, "num_results": num_results})

            if not result.success:
                return []

            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    score=r.get("score", 0.0),
                    source="builtin",
                )
                for r in (result.data or [])
            ]
        except Exception:
            return []

    async def health_check(self) -> bool:
        """Check if built-in search is available."""
        try:
            from deepr.tools.web_search import WebSearchTool

            WebSearchTool()
            return True
        except Exception:
            return False


class MCPSearchBackend:
    """Search backend that delegates to an MCP search server.

    STATUS: Stub implementation. Raises NotImplementedError.
    Will connect to MCP servers like:
    - @modelcontextprotocol/server-brave-search
    - tavily-mcp (when available)
    - Google Custom Search MCP
    """

    def __init__(self, server_name: str = "brave-mcp"):
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._server_name

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Search via MCP server (not yet implemented)."""
        raise NotImplementedError(
            f"MCP search backend '{self._server_name}' not yet implemented. "
            "See docs/mcp-client-architecture.md for the design."
        )

    async def health_check(self) -> bool:
        """Check MCP server health (not yet implemented)."""
        return False
