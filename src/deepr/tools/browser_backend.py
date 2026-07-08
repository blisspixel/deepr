"""
Browser Backend Abstraction for MCP Client Mode.

Defines the BrowserBackend protocol for swapping between the built-in scraper
and explicit external browser adapters. This module does not auto-create MCP
client transports; callers must wire a concrete transport-backed adapter before
using MCP-hosted browsing.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PageValidators:
    """HTTP cache validators from the last known page representation."""

    etag: str = ""
    last_modified: str = ""

    def conditional_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers


@dataclass
class PageContent:
    """Content fetched from a web page."""

    url: str
    title: str
    text: str
    html: str | None = None
    status_code: int = 200
    content_type: str = "text/html"
    etag: str = ""
    last_modified: str = ""


@runtime_checkable
class BrowserBackend(Protocol):
    """Protocol for browser/scraper backends.

    Implementations can be:
    - BuiltinBrowserBackend: wraps deepr's existing scraper
    - MCPBrowserBackend: explicit disabled sentinel for MCP-hosted browsing
    """

    async def fetch_page(self, url: str, *, validators: PageValidators | None = None) -> PageContent:
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

    async def fetch_page(self, url: str, *, validators: PageValidators | None = None) -> PageContent:
        """Fetch page using built-in scraper."""
        try:
            from deepr.utils.scrape import ContentExtractor, ContentFetcher, ScrapeConfig

            config = ScrapeConfig(max_pages=1, max_depth=0, try_selenium=False, try_pdf=False, try_archive=False)
            fetcher = ContentFetcher(config)
            result = (
                fetcher.fetch(url, headers=validators.conditional_headers())
                if validators is not None
                else fetcher.fetch(url)
            )
            if not result.success:
                return PageContent(
                    url=url,
                    title="Error",
                    text=result.error or "Fetch failed",
                    status_code=0,
                )
            response_headers = getattr(result, "response_headers", {}) or {}
            status_code = int(getattr(result, "status_code", 0) or 0)
            result_url = str(getattr(result, "url", url) or url)
            headers = {str(k).lower(): str(v) for k, v in response_headers.items()}
            if status_code == 304:
                return PageContent(
                    url=result_url,
                    title="Not modified",
                    text="",
                    status_code=304,
                    etag=headers.get("etag", validators.etag if validators is not None else ""),
                    last_modified=headers.get(
                        "last-modified",
                        validators.last_modified if validators is not None else "",
                    ),
                )
            html = getattr(result, "html", None) or getattr(result, "content", None) or ""
            extractor = ContentExtractor()
            metadata = extractor.extract_metadata(html) if html else {}
            return PageContent(
                url=result_url,
                title=metadata.get("title", ""),
                text=extractor.extract_main_content(html) if html else "",
                html=result.html,
                status_code=status_code or 200,
                etag=headers.get("etag", ""),
                last_modified=headers.get("last-modified", ""),
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
    """Disabled MCP browser backend sentinel.

    Deepr currently fetches pages through the built-in scraper. MCP-hosted
    browsing needs a concrete client transport from the caller, so this sentinel
    fails clearly if selected directly.
    """

    def __init__(self, server_name: str = "puppeteer-mcp"):
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._server_name

    async def fetch_page(self, url: str, *, validators: PageValidators | None = None) -> PageContent:
        raise NotImplementedError(
            f"MCP browser backend '{self._server_name}' has no configured client transport. "
            "Use BuiltinBrowserBackend or provide a concrete adapter."
        )

    async def health_check(self) -> bool:
        return False
