"""Fresh retrieval context for local maintenance runs.

Local models are useful for zero-dollar maintenance, but they do not know what
changed online unless Deepr retrieves sources first. This module builds a small,
cited context pack that can be prepended to a local-model prompt.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from deepr.tools.browser_backend import BrowserBackend, BuiltinBrowserBackend
from deepr.tools.search_backend import BuiltinSearchBackend, SearchBackend, SearchResult

_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
_TRAILING_PUNCTUATION = ".,;:!?"


@dataclass(frozen=True)
class FreshContextConfig:
    """Bounds for retrieval context injected into a local model."""

    max_search_results: int = 5
    max_fetches: int = 3
    max_chars_per_source: int = 1800
    max_total_chars: int = 7000


@dataclass(frozen=True)
class FreshSource:
    """One retrieved source available to the local model."""

    title: str
    url: str
    snippet: str = ""
    content: str = ""
    source: str = "unknown"
    fetched: bool = False
    error: str = ""

    def excerpt(self, max_chars: int) -> str:
        text = self.content.strip() or self.snippet.strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 3)].rstrip() + "..."


@dataclass(frozen=True)
class FreshContext:
    """Retrieved context plus metadata for audit and prompts."""

    query: str
    generated_at: str
    sources: tuple[FreshSource, ...] = ()
    search_backend: str = "none"
    browser_backend: str = "none"
    errors: tuple[str, ...] = ()

    @property
    def has_sources(self) -> bool:
        return any(source.excerpt(1) for source in self.sources)

    def to_prompt_context(self, config: FreshContextConfig | None = None) -> str:
        cfg = config or FreshContextConfig()
        lines = [
            "## Fresh retrieval context",
            f"Generated: {self.generated_at}",
            f"Search backend: {self.search_backend}",
            f"Browser backend: {self.browser_backend}",
            "",
            "Use these sources for current factual claims. Cite source labels like [S1].",
        ]
        if not self.has_sources:
            lines.extend(
                [
                    "No fresh web sources were retrieved.",
                    "If the answer depends on current facts, state that fresh context is unavailable.",
                ]
            )
            return "\n".join(lines)

        used_chars = 0
        for index, source in enumerate(self.sources, start=1):
            excerpt = source.excerpt(min(cfg.max_chars_per_source, cfg.max_total_chars - used_chars))
            if not excerpt:
                continue
            used_chars += len(excerpt)
            lines.extend(
                [
                    "",
                    f"[S{index}] {source.title or source.url}",
                    f"URL: {source.url}",
                    f"Retrieved via: {source.source}",
                    excerpt,
                ]
            )
            if used_chars >= cfg.max_total_chars:
                break
        return "\n".join(lines)

    def to_metadata(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "search_backend": self.search_backend,
            "browser_backend": self.browser_backend,
            "source_count": len(self.sources),
            "sources": [
                {
                    "title": source.title,
                    "url": source.url,
                    "source": source.source,
                    "fetched": source.fetched,
                    "error": source.error,
                }
                for source in self.sources
            ],
            "errors": list(self.errors),
        }


class FreshContextBuilder(Protocol):
    async def __call__(self, query: str) -> FreshContext | str:
        """Build context for a local-model prompt."""
        ...


def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.findall(text):
        url = match.rstrip(_TRAILING_PUNCTUATION)
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


async def retrieve_fresh_context(
    query: str,
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
) -> FreshContext:
    """Retrieve a bounded context pack for a local model.

    The default has no search backend so callers cannot accidentally spend via
    API-key search providers. Use ``make_free_fresh_context_builder`` for the
    free-only DuckDuckGo path plus direct page fetches.
    """
    cfg = config or FreshContextConfig()
    search_results: list[SearchResult] = []
    errors: list[str] = []

    if search_backend is not None:
        try:
            search_results = await search_backend.search(query, num_results=cfg.max_search_results)
        except Exception as exc:
            errors.append(f"search failed: {exc}")

    urls: list[str] = []
    seen_urls: set[str] = set()
    result_by_url: dict[str, SearchResult] = {}

    for url in _extract_urls(query):
        seen_urls.add(url)
        urls.append(url)

    for result in search_results:
        if not result.url or result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        urls.append(result.url)
        result_by_url[result.url] = result

    sources: list[FreshSource] = []
    fetched_count = 0
    for url in urls:
        result = result_by_url.get(url)
        title = result.title if result else url
        snippet = result.snippet if result else ""
        source_name = result.source if result else "explicit-url"
        if browser_backend is not None and fetched_count < cfg.max_fetches:
            fetched_count += 1
            try:
                page = await browser_backend.fetch_page(url)
                if page.status_code and page.text.strip():
                    sources.append(
                        FreshSource(
                            title=page.title or title,
                            url=page.url or url,
                            snippet=snippet,
                            content=page.text,
                            source=f"{source_name}+{browser_backend.name}",
                            fetched=True,
                        )
                    )
                    continue
                sources.append(
                    FreshSource(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source=source_name,
                        error=page.text or "fetch returned no text",
                    )
                )
                continue
            except Exception as exc:
                sources.append(FreshSource(title=title, url=url, snippet=snippet, source=source_name, error=str(exc)))
                continue
        sources.append(FreshSource(title=title, url=url, snippet=snippet, source=source_name))

    return FreshContext(
        query=query,
        generated_at=datetime.now(UTC).isoformat(),
        sources=tuple(sources),
        search_backend=search_backend.name if search_backend else "none",
        browser_backend=browser_backend.name if browser_backend else "none",
        errors=tuple(errors),
    )


def make_free_fresh_context_builder(
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
) -> Callable[[str], Awaitable[FreshContext]]:
    """Build a free-only retrieval function for local models.

    The default search backend is DuckDuckGo through ``duckduckgo-search`` when
    installed. It does not use Brave, Tavily, or any API-key search backend.
    """
    cfg = config or FreshContextConfig()
    free_search = search_backend or BuiltinSearchBackend(web_backend="duckduckgo")
    browser = browser_backend or BuiltinBrowserBackend()

    async def build(query: str) -> FreshContext:
        return await retrieve_fresh_context(
            query,
            search_backend=free_search,
            browser_backend=browser,
            config=cfg,
        )

    return build
