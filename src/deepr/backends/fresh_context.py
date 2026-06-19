"""Fresh retrieval context for local maintenance runs.

Local models are useful for zero-dollar maintenance, but they do not know what
changed online unless Deepr retrieves sources first. This module builds a small,
cited context pack that can be prepended to a local-model prompt.
"""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from deepr.tools.browser_backend import BrowserBackend, BuiltinBrowserBackend
from deepr.tools.search_backend import BuiltinSearchBackend, SearchBackend, SearchResult, SearXNGSearchBackend

_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
_TRAILING_PUNCTUATION = ".,;:!?"


@dataclass(frozen=True)
class FreshContextConfig:
    """Bounds for retrieval context injected into a local model."""

    max_search_results: int = 5
    max_fetches: int = 3
    max_chars_per_source: int = 1800
    max_total_chars: int = 7000
    max_search_queries: int = 1


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
        if max_chars <= 0:
            return ""
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
    mode: str = "fresh"
    search_queries: tuple[str, ...] = ()
    prompt_config: FreshContextConfig | None = None

    @property
    def has_sources(self) -> bool:
        return any(source.excerpt(1) for source in self.sources)

    def _citable_sources(self) -> tuple[FreshSource, ...]:
        return tuple(source for source in self.sources if source.excerpt(1))

    def to_prompt_context(self, config: FreshContextConfig | None = None) -> str:
        cfg = config or self.prompt_config or FreshContextConfig()
        lines = [
            "## Fresh retrieval context",
            f"Generated: {self.generated_at}",
            f"Mode: {self.mode}",
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
        for index, source in enumerate(self._citable_sources(), start=1):
            remaining = cfg.max_total_chars - used_chars
            if remaining <= 0:
                break
            excerpt = source.excerpt(min(cfg.max_chars_per_source, remaining))
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
        usable_sources = self._citable_sources()
        return {
            "generated_at": self.generated_at,
            "mode": self.mode,
            "search_backend": self.search_backend,
            "browser_backend": self.browser_backend,
            "source_count": len(usable_sources),
            "retrieved_source_count": len(self.sources),
            "search_queries": list(self.search_queries),
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

    def to_source_pack(self, *, max_excerpt_chars: int = 2000) -> dict[str, object]:
        """Serialize retrieved sources as a bounded, portable run artifact."""
        cfg = self.prompt_config or FreshContextConfig()
        excerpt_limit = min(max_excerpt_chars, cfg.max_chars_per_source)
        usable_sources = self._citable_sources()
        return {
            "schema_version": "deepr.source_pack.v1",
            "query": self.query,
            "generated_at": self.generated_at,
            "mode": self.mode,
            "search_backend": self.search_backend,
            "browser_backend": self.browser_backend,
            "search_queries": list(self.search_queries),
            "source_count": len(usable_sources),
            "retrieved_source_count": len(self.sources),
            "errors": list(self.errors),
            "sources": [
                {
                    "label": f"S{index}",
                    "title": source.title,
                    "url": source.url,
                    "source": source.source,
                    "fetched": source.fetched,
                    "error": source.error,
                    "snippet": source.snippet,
                    "excerpt": source.excerpt(excerpt_limit),
                }
                for index, source in enumerate(usable_sources, start=1)
            ],
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


def _default_free_search_backend() -> SearchBackend:
    searxng_url = os.getenv("DEEPR_SEARXNG_URL")
    if searxng_url:
        return SearXNGSearchBackend(searxng_url)
    return BuiltinSearchBackend(web_backend="duckduckgo")


def _deep_search_queries(query: str, max_queries: int) -> tuple[str, ...]:
    """Generate bounded search routes for deep local context."""
    base = " ".join(query.split())
    if not base or max_queries <= 0:
        return ()

    current_year = datetime.now(UTC).year
    suffixes = (
        "",
        f"latest updates {current_year}",
        "official documentation release notes changelog",
        "pricing policy deprecation announcement",
        "implementation guide comparison limitations",
    )
    queries: list[str] = []
    seen: set[str] = set()
    for suffix in suffixes:
        search_query = base if not suffix else f"{base} {suffix}"
        if search_query not in seen:
            seen.add(search_query)
            queries.append(search_query)
        if len(queries) >= max_queries:
            break
    return tuple(queries)


async def _collect_search_results(
    search_backend: SearchBackend | None,
    search_queries: tuple[str, ...],
    *,
    max_search_results: int,
) -> tuple[list[SearchResult], list[str]]:
    if search_backend is None:
        return [], []

    results: list[SearchResult] = []
    errors: list[str] = []
    for search_query in search_queries:
        try:
            results.extend(await search_backend.search(search_query, num_results=max_search_results))
        except Exception as exc:
            errors.append(f"search failed for {search_query!r}: {exc}")
    return results, errors


def _retrieval_urls(query: str, search_results: list[SearchResult]) -> tuple[list[str], dict[str, SearchResult]]:
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

    return urls, result_by_url


async def _source_from_url(
    url: str,
    *,
    result_by_url: dict[str, SearchResult],
    browser_backend: BrowserBackend | None,
    fetch: bool,
) -> FreshSource:
    result = result_by_url.get(url)
    title = result.title if result else url
    snippet = result.snippet if result else ""
    source_name = result.source if result else "explicit-url"
    if browser_backend is None or not fetch:
        return FreshSource(title=title, url=url, snippet=snippet, source=source_name)

    try:
        page = await browser_backend.fetch_page(url)
        if page.status_code and page.text.strip():
            return FreshSource(
                title=page.title or title,
                url=page.url or url,
                snippet=snippet,
                content=page.text,
                source=f"{source_name}+{browser_backend.name}",
                fetched=True,
            )
        return FreshSource(
            title=title,
            url=url,
            snippet=snippet,
            source=source_name,
            error=page.text or "fetch returned no text",
        )
    except Exception as exc:
        return FreshSource(title=title, url=url, snippet=snippet, source=source_name, error=str(exc))


async def _build_sources(
    urls: list[str],
    *,
    result_by_url: dict[str, SearchResult],
    browser_backend: BrowserBackend | None,
    max_fetches: int,
) -> tuple[FreshSource, ...]:
    sources: list[FreshSource] = []
    fetched_count = 0
    for url in urls:
        fetch = fetched_count < max_fetches
        if browser_backend is not None and fetch:
            fetched_count += 1
        sources.append(
            await _source_from_url(
                url,
                result_by_url=result_by_url,
                browser_backend=browser_backend,
                fetch=fetch,
            )
        )
    return tuple(sources)


async def retrieve_fresh_context(
    query: str,
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
    search_queries: tuple[str, ...] | None = None,
    mode: str = "fresh",
) -> FreshContext:
    """Retrieve a bounded context pack for a local model.

    The default has no search backend so callers cannot accidentally spend via
    API-key search providers. Use ``make_free_fresh_context_builder`` for the
    free-only DuckDuckGo path plus direct page fetches.
    """
    cfg = config or FreshContextConfig()
    active_search_queries = search_queries or (query,)
    search_results, errors = await _collect_search_results(
        search_backend,
        active_search_queries,
        max_search_results=cfg.max_search_results,
    )
    urls, result_by_url = _retrieval_urls(query, search_results)
    sources = await _build_sources(
        urls,
        result_by_url=result_by_url,
        browser_backend=browser_backend,
        max_fetches=cfg.max_fetches,
    )

    return FreshContext(
        query=query,
        generated_at=datetime.now(UTC).isoformat(),
        sources=sources,
        search_backend=search_backend.name if search_backend else "none",
        browser_backend=browser_backend.name if browser_backend else "none",
        errors=tuple(errors),
        mode=mode,
        search_queries=active_search_queries if search_backend else (),
        prompt_config=cfg,
    )


def deep_fresh_context_config() -> FreshContextConfig:
    """Default bounds for multi-query local deep context."""
    return FreshContextConfig(
        max_search_results=6,
        max_fetches=8,
        max_chars_per_source=1600,
        max_total_chars=14000,
        max_search_queries=4,
    )


async def retrieve_deep_fresh_context(
    query: str,
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
) -> FreshContext:
    """Retrieve a deeper free-only source pack for local deep-context sync."""
    cfg = config or deep_fresh_context_config()
    search_queries = _deep_search_queries(query, cfg.max_search_queries)
    return await retrieve_fresh_context(
        query,
        search_backend=search_backend,
        browser_backend=browser_backend,
        config=cfg,
        search_queries=search_queries,
        mode="deep",
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
    free_search = search_backend or _default_free_search_backend()
    browser = browser_backend or BuiltinBrowserBackend()

    async def build(query: str) -> FreshContext:
        return await retrieve_fresh_context(
            query,
            search_backend=free_search,
            browser_backend=browser,
            config=cfg,
        )

    return build


def make_free_deep_context_builder(
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
) -> Callable[[str], Awaitable[FreshContext]]:
    """Build a bounded multi-query free retrieval function for local models."""
    cfg = config or deep_fresh_context_config()
    free_search = search_backend or _default_free_search_backend()
    browser = browser_backend or BuiltinBrowserBackend()

    async def build(query: str) -> FreshContext:
        return await retrieve_deep_fresh_context(
            query,
            search_backend=free_search,
            browser_backend=browser,
            config=cfg,
        )

    return build
