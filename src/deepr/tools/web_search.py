"""Web search tool implementation."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

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

    The public tool executes only the unmetered DuckDuckGo adapter. Brave and
    Tavily remain named compatibility values but fail closed until their price,
    reservation, and canonical settlement contracts are implemented.
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
        # Do not retain ambient metered credentials in the free-search tool.
        # The arguments remain accepted so older configuration fails at execute
        # time with an actionable safety message instead of during construction.
        del brave_api_key, tavily_api_key

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
        if num_results < 1 or num_results > 20:
            return ToolResult(success=False, data=None, error="Web search num_results must be between 1 and 20.")

        normalized_backend = str(self.backend).strip().lower()
        if normalized_backend in {"brave", "tavily"}:
            return ToolResult(
                success=False,
                data=None,
                error=(
                    f"{normalized_backend.title()} search is disabled until Deepr can price, reserve, "
                    "and settle every request. Use duckduckgo or a configured SearXNG backend."
                ),
            )
        if normalized_backend not in {"auto", "duckduckgo"}:
            return ToolResult(success=False, data=None, error=f"Unsupported web search backend: {self.backend}")

        return await self._search_duckduckgo(query, num_results)

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
