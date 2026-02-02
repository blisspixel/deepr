"""
Browser Backend Abstraction for MCP Client Mode.

Defines the BrowserBackend protocol for swapping between
the built-in scraper and external MCP browser servers
(Puppeteer, Playwright, etc.).

STATUS: Interface definitions only. MCP client connections not implemented.
See docs/mcp-client-architecture.md for the full design.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Optional


@dataclass
class PageContent:
    """Content fetched from a web page."""
    url: str
    title: str
    text: str
    html: Optional[str] = None
    status_code: int = 200
    content_type: str = "text/html"


@runtime_checkable
class BrowserBackend(Protocol):
    """Protocol for browser/scraper backends.

    Implementations can be:
    - BuiltinBrowserBackend: wraps deepr's existing scraper
    - MCPBrowserBackend: delegates to Puppeteer/Playwright MCP server (stub)
    """

    async def fetch_page(self, url: str) -> PageContent:
        """Fetch and return page content.

        Args:
            url: URL to fetch

        Returns:
            PageContent with text and optional HTML
        """
        ...

    async def health_check(self) -> bool:
        """Check if the backend is available."""
        ...

    @property
    def name(self) -> str:
        """Backend identifier."""
        ...


class BuiltinBrowserBackend:
    """Browser backend using Deepr's built-in scraper."""

    @property
    def name(self) -> str:
        return "builtin"

    async def fetch_page(self, url: str) -> PageContent:
        """Fetch page using built-in scraper."""
        try:
            from deepr.utils.scrape import scrape_url
            result = await scrape_url(url)
            return PageContent(
                url=url,
                title=result.get("title", ""),
                text=result.get("text", ""),
                html=result.get("html"),
                status_code=result.get("status_code", 200),
            )
        except Exception as e:
            return PageContent(
                url=url,
                title="Error",
                text=str(e),
                status_code=0,
            )

    async def health_check(self) -> bool:
        return True


class MCPBrowserBackend:
    """Browser backend that delegates to an MCP browser server.

    STATUS: Stub implementation.
    """

    def __init__(self, server_name: str = "puppeteer-mcp"):
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._server_name

    async def fetch_page(self, url: str) -> PageContent:
        raise NotImplementedError(
            f"MCP browser backend '{self._server_name}' not yet implemented."
        )

    async def health_check(self) -> bool:
        return False
