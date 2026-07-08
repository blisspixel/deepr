"""
Search Backend Abstraction for MCP Client Mode.

Defines the SearchBackend protocol that allows swapping between
the built-in search implementation and explicit external search adapters.
This module does not auto-create MCP client transports; callers must wire a
concrete transport-backed adapter before using MCP-hosted search.
"""

import logging
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


def _score(value: object) -> float:
    if value is None or value == "":
        return 0.0
    try:
        if isinstance(value, str | bytes | int | float):
            return float(value)
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


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
    - MCPSearchBackend: explicit disabled sentinel for MCP-hosted search
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

    def __init__(self, *, web_backend: str = "auto") -> None:
        self._web_backend = web_backend

    @property
    def name(self) -> str:
        return f"builtin:{self._web_backend}"

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Search using built-in web search."""
        try:
            from deepr.tools.web_search import WebSearchTool

            tool = WebSearchTool(backend=self._web_backend)
            result = await tool.execute(query=query, num_results=num_results)

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
        except Exception as exc:
            logger.warning("Builtin search backend failed for query %r: %s", query, exc)
            return []

    async def health_check(self) -> bool:
        """Check if built-in search is available."""
        try:
            from deepr.tools.web_search import WebSearchTool

            WebSearchTool()
            return True
        except Exception as exc:
            logger.warning("Builtin search backend health check failed: %s", exc)
            return False


class SearXNGSearchBackend:
    """Free search backend for a self-hosted or user-selected SearXNG instance."""

    def __init__(self, base_url: str | None = None, *, timeout: float = 10.0) -> None:
        self._base_url = (base_url or os.getenv("DEEPR_SEARXNG_URL") or "").rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "searxng"

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Search SearXNG JSON results without any provider API key."""
        if not self._base_url:
            return []

        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=self._timeout) as client:
                response = await client.get(
                    f"{self._base_url}/search",
                    params={"q": query, "format": "json"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("SearXNG search backend failed for query %r: %s", query, exc)
            return []

        results: list[SearchResult] = []
        for item in data.get("results", [])[:num_results]:
            url = item.get("url") or ""
            if not url:
                continue
            engine = item.get("engine") or item.get("source") or "searxng"
            results.append(
                SearchResult(
                    title=item.get("title") or url,
                    url=url,
                    snippet=item.get("content") or item.get("snippet") or "",
                    score=_score(item.get("score")),
                    source=f"searxng:{engine}",
                )
            )
        return results

    async def health_check(self) -> bool:
        """Check that the configured SearXNG endpoint returns JSON search results."""
        if not self._base_url:
            return False
        return bool(await self.search("deepr", num_results=1))


class MCPSearchBackend:
    """Disabled MCP search backend sentinel.

    Deepr currently wires fresh-context search through built-in free search or
    SearXNG. MCP-hosted search needs a concrete client transport from the caller,
    so this sentinel fails clearly if selected directly.
    """

    def __init__(self, server_name: str = "brave-mcp"):
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._server_name

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Reject direct MCP search until a transport-backed adapter is supplied."""
        raise NotImplementedError(
            f"MCP search backend '{self._server_name}' has no configured client transport. "
            "Use BuiltinSearchBackend, SearXNGSearchBackend, or provide a concrete adapter."
        )

    async def health_check(self) -> bool:
        """Report unavailable unless a concrete transport-backed adapter is supplied."""
        return False
