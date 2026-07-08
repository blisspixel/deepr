"""Web search tool implementation."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

import requests

from .base import Tool, ToolResult

_T = TypeVar("_T")

# DuckDuckGo's free endpoint rate-limits aggressively, so a single attempt fails
# often enough to starve the $0 retrieval path ("no sources -> no report"). Retry
# transient failures with exponential backoff before degrading. Slow is fine for
# unattended $0 work; a wrong "no sources" is not.
_DDG_MAX_ATTEMPTS = 3
_DDG_BACKOFF_BASE_S = 1.5


async def _retry_async(
    operation: Callable[[], Awaitable[_T]],
    *,
    attempts: int,
    base_delay: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> _T:
    """Run ``operation`` with exponential backoff, re-raising the last error.

    Backoff is ``base_delay * 2**attempt`` between tries; the final attempt does
    not sleep. ``sleep`` is injectable so tests run without real delays.
    """
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception:  # transient: rate limit, timeout, network
            if attempt + 1 >= attempts:
                raise  # exhausted: surface the last failure to the caller
            await sleep(base_delay * (2**attempt))
    raise ValueError("attempts must be >= 1")


def _parse_web_search_execute_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str, int, str | None]:
    if len(args) > 2:
        return "", 0, "Web search accepts at most query and num_results positional arguments."
    if args and "query" in kwargs:
        return "", 0, "Web search query was provided twice."
    if len(args) > 1 and "num_results" in kwargs:
        return "", 0, "Web search num_results was provided twice."

    query = args[0] if args else kwargs.get("query")
    if not isinstance(query, str) or not query.strip():
        return "", 0, "Web search requires a non-empty string query."

    num_results_value = args[1] if len(args) > 1 else kwargs.get("num_results", 5)
    try:
        return query, int(num_results_value), None
    except (TypeError, ValueError):
        return "", 0, "Web search num_results must be an integer."


def _load_duckduckgo_client_class() -> type[Any] | None:
    for module_name in ("ddgs", "duckduckgo_search"):
        try:
            module = __import__(module_name, fromlist=["DDGS"])
        except ImportError:
            continue
        ddgs_class = getattr(module, "DDGS", None)
        if ddgs_class is not None:
            return cast(type[Any], ddgs_class)
    return None


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
        brave_api_key: str | None = None,
        tavily_api_key: str | None = None,
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

    async def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        """Execute web search."""
        query, num_results, parse_error = _parse_web_search_execute_args(args, kwargs)
        if parse_error is not None:
            return ToolResult(success=False, data=None, error=parse_error)

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
            except Exception:  # Intentional backend failover in multi-provider web search; one failing provider does not kill the tool call.
                # Try next backend
                continue

        return ToolResult(
            success=False,
            data=None,
            error="No working web search backend available. Set BRAVE_API_KEY or TAVILY_API_KEY.",
        )

    async def _search_brave(self, query: str, num_results: int) -> ToolResult:
        """Search using Brave Search API."""
        if not self.brave_api_key:
            return ToolResult(success=False, data=None, error="Brave Search requires BRAVE_API_KEY.")

        url = "https://api.search.brave.com/res/v1/web/search"
        headers: dict[str, str] = {"Accept": "application/json", "X-Subscription-Token": self.brave_api_key}
        params: dict[str, str | int] = {"q": query, "count": num_results}

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
        """Search using DuckDuckGo (free, no API key).

        Prefers the maintained ``ddgs`` package; falls back to the legacy
        ``duckduckgo_search`` name. The legacy package is deprecated and its
        endpoint now returns no results, so ``ddgs`` is what makes the free
        retrieval path actually work. Network errors degrade to a failed
        ToolResult so the caller records "no sources" rather than crashing.
        """
        ddgs_class = _load_duckduckgo_client_class()
        if ddgs_class is None:
            return ToolResult(success=False, data=None, error="No DuckDuckGo backend installed. Run: pip install ddgs")

        def _query() -> list[dict[str, str | None]]:
            return [
                {"title": r.get("title"), "url": r.get("href") or r.get("url"), "snippet": r.get("body")}
                for r in ddgs_class().text(query, max_results=num_results)
            ]

        try:
            results = await _retry_async(
                lambda: asyncio.to_thread(_query),
                attempts=_DDG_MAX_ATTEMPTS,
                base_delay=_DDG_BACKOFF_BASE_S,
            )
        except Exception as e:  # rate limits / transient network: degrade, don't crash
            return ToolResult(
                success=False,
                data=None,
                error=f"DuckDuckGo search failed after {_DDG_MAX_ATTEMPTS} attempts: {e}",
            )
        return ToolResult(success=True, data=results, metadata={"backend": "duckduckgo", "query": query})


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

    async def execute(self, *args: Any, **kwargs: Any) -> ToolResult:
        """Execute MCP web search."""
        if len(args) > 1:
            return ToolResult(success=False, data=None, error="MCP web search accepts at most one positional query.")
        if args and "query" in kwargs:
            return ToolResult(success=False, data=None, error="MCP web search query was provided twice.")
        query = args[0] if args else kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            return ToolResult(success=False, data=None, error="MCP web search requires a non-empty string query.")
        return ToolResult(success=False, data=None, error="MCP web search transport is not configured.")
