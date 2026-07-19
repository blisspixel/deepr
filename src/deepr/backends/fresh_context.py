"""Fresh retrieval context for local maintenance runs.

Local models are useful for zero-dollar maintenance, but they do not know what
changed online unless Deepr retrieves sources first. This module builds a small,
cited context pack that can be prepended to a local-model prompt.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

from deepr.backends.context_building import ContextGenerationReadiness
from deepr.tools.browser_backend import BrowserBackend, BuiltinBrowserBackend, PageContent, PageValidators
from deepr.tools.search_backend import BuiltinSearchBackend, SearchBackend, SearchResult, SearXNGSearchBackend
from deepr.utils.prompt_security import sanitize_untrusted_content

_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_TRAILING_PUNCTUATION = ".,;:!?"
_MAX_CONCURRENT_SEARCHES = 4
_MAX_CONCURRENT_FETCHES = 4
_UNSAFE_RETRIEVAL_HOST = "unsafe-target"
_DNS_LABEL_RE = re.compile(r"^[a-z0-9-]+$")
_SERIAL_SEARCH_BACKENDS = frozenset({"builtin:auto", "builtin:duckduckgo"})


@dataclass(frozen=True)
class FreshContextConfig:
    """Bounds for retrieval context injected into a local model."""

    max_search_results: int = 5
    max_fetches: int = 3
    max_chars_per_source: int = 1800
    max_total_chars: int = 7000
    max_search_queries: int = 1
    min_content_addressed_sources: int = 2
    min_explicit_url_sources: int = 1


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
    etag: str = ""
    last_modified: str = ""
    not_modified: bool = False
    content_hash_value: str = ""

    def excerpt(self, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        text = self.content.strip() or self.snippet.strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 3)].rstrip() + "..."

    @property
    def content_hash(self) -> str:
        """SHA-256 of the fetched main content, or '' when nothing was fetched.

        The pre-sync change-detection gate (``experts/sync.py``) compares these
        across syncs to skip re-absorbing byte-identical sources. Derived from
        ``content`` so the hash can never drift from the text it summarizes; the
        search snippet is excluded because it is volatile retrieval metadata,
        not the content the absorber reads.
        """
        text = self.content.strip()
        if self.content_hash_value:
            return self.content_hash_value
        if not text:
            return ""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @property
    def has_content_addressed_evidence(self) -> bool:
        """Whether this source has replayable evidence shape for generation."""
        return bool(self.excerpt(1)) and bool(_SHA256_RE.fullmatch(self.content_hash))


@dataclass(frozen=True)
class CachedSource:
    """Prior source-pack metadata used for conditional source retrieval."""

    title: str = ""
    url: str = ""
    etag: str = ""
    last_modified: str = ""
    content_hash: str = ""
    excerpt: str = ""

    @property
    def validators(self) -> PageValidators | None:
        if not self.etag and not self.last_modified:
            return None
        return PageValidators(etag=self.etag, last_modified=self.last_modified)


def cached_sources_from_pack(source_pack: dict[str, Any] | None) -> dict[str, CachedSource]:
    if not isinstance(source_pack, dict):
        return {}
    cached: dict[str, CachedSource] = {}
    for source in source_pack.get("sources", []):
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "")
        if not url:
            continue
        cached[url] = CachedSource(
            title=str(source.get("title") or ""),
            url=url,
            etag=str(source.get("etag") or ""),
            last_modified=str(source.get("last_modified") or ""),
            content_hash=str(source.get("content_hash") or ""),
            excerpt=str(source.get("excerpt") or ""),
        )
    return cached


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
        return bool(self._citable_sources())

    def _citable_sources(self) -> tuple[FreshSource, ...]:
        return tuple(source for source in self.sources if source.has_content_addressed_evidence)

    def generation_readiness(self) -> ContextGenerationReadiness:
        """Return the provenance-only preflight for a generation backend."""
        cfg = self.prompt_config or FreshContextConfig()
        explicit_url_count = len(_extract_urls(self.query))
        minimum = cfg.min_explicit_url_sources if explicit_url_count else cfg.min_content_addressed_sources
        required = max(1, int(minimum))
        ready_count = len(self._citable_sources())
        return ContextGenerationReadiness(
            ready=ready_count >= required,
            mode=self.mode,
            ready_source_count=ready_count,
            required_source_count=required,
            retrieved_source_count=len(self.sources),
            explicit_url_count=explicit_url_count,
        )

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
            sanitized = sanitize_untrusted_content(excerpt, source_label=f"S{index} {source.url}")
            used_chars += len(excerpt)
            lines.extend(
                [
                    "",
                    f"[S{index}] {source.title or source.url}",
                    f"URL: {source.url}",
                    f"Retrieved via: {source.source}",
                    sanitized.delimited,
                ]
            )
            if used_chars >= cfg.max_total_chars:
                break
        return "\n".join(lines)

    def to_metadata(self) -> dict[str, object]:
        usable_sources = self._citable_sources()
        readiness = self.generation_readiness()
        return {
            "generated_at": self.generated_at,
            "mode": self.mode,
            "search_backend": self.search_backend,
            "browser_backend": self.browser_backend,
            "source_count": len(usable_sources),
            "content_addressed_source_count": len(usable_sources),
            "retrieved_source_count": len(self.sources),
            "generation_readiness": readiness.to_dict(),
            "search_queries": list(self.search_queries),
            "sources": [
                {
                    "title": source.title,
                    "url": source.url,
                    "source": source.source,
                    "fetched": source.fetched,
                    "error": source.error,
                    "content_hash": source.content_hash,
                    "etag": source.etag,
                    "last_modified": source.last_modified,
                    "not_modified": source.not_modified,
                }
                for source in self.sources
            ],
            "errors": list(self.errors),
        }

    def to_source_pack(self, *, max_excerpt_chars: int = 2000, include_content: bool = False) -> dict[str, object]:
        """Serialize retrieved sources as a bounded, portable run artifact.

        ``include_content=True`` adds each source's full fetched text under a
        transient ``content`` key so a persister can write content-addressed
        raw snapshots. Persisters must strip that key before the pack is
        written; it is transport, not part of the durable pack contract, and
        its size is bounded only by the snapshot writer's own cap.
        """
        cfg = self.prompt_config or FreshContextConfig()
        excerpt_limit = min(max_excerpt_chars, cfg.max_chars_per_source)
        usable_sources = self._citable_sources()
        readiness = self.generation_readiness()

        def _entry(index: int, source: FreshSource) -> dict[str, object]:
            entry: dict[str, object] = {
                "label": f"S{index}",
                "title": source.title,
                "url": source.url,
                "source": source.source,
                "fetched": source.fetched,
                "error": source.error,
                "snippet": source.snippet,
                "excerpt": source.excerpt(excerpt_limit),
                "content_hash": source.content_hash,
                "etag": source.etag,
                "last_modified": source.last_modified,
                "not_modified": source.not_modified,
            }
            if include_content:
                entry["content"] = source.content
            return entry

        def _retrieval_candidate(source: FreshSource) -> dict[str, object]:
            return {
                "title": source.title,
                "url": source.url,
                "source": source.source,
                "fetched": source.fetched,
                "error": source.error,
                "snippet": source.snippet,
                "content_hash": source.content_hash,
                "etag": source.etag,
                "last_modified": source.last_modified,
                "not_modified": source.not_modified,
                "content_addressed": source.has_content_addressed_evidence,
            }

        return {
            "schema_version": "deepr.source_pack.v1",
            "query": self.query,
            "generated_at": self.generated_at,
            "mode": self.mode,
            "search_backend": self.search_backend,
            "browser_backend": self.browser_backend,
            "search_queries": list(self.search_queries),
            "source_count": len(usable_sources),
            "content_addressed_source_count": len(usable_sources),
            "retrieved_source_count": len(self.sources),
            "generation_readiness": readiness.to_dict(),
            "errors": list(self.errors),
            "sources": [_entry(index, source) for index, source in enumerate(usable_sources, start=1)],
            "retrieval_candidates": [_retrieval_candidate(source) for source in self.sources],
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


def retrieval_host_key(url: str) -> str:
    """Return a conservative rate-limit key for one retrieval target."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return _UNSAFE_RETRIEVAL_HOST
        hostname = parsed.hostname.rstrip(".").lower()
        if not hostname:
            return _UNSAFE_RETRIEVAL_HOST
        try:
            normalized = str(ipaddress.ip_address(hostname))
        except ValueError:
            normalized = hostname.encode("idna").decode("ascii")
            labels = normalized.split(".")
            if len(normalized) > 253 or any(
                not label
                or len(label) > 63
                or not _DNS_LABEL_RE.fullmatch(label)
                or label.startswith("-")
                or label.endswith("-")
                for label in labels
            ):
                return _UNSAFE_RETRIEVAL_HOST
        return f"host:{normalized}"
    except (TypeError, ValueError, UnicodeError):
        return _UNSAFE_RETRIEVAL_HOST


def _default_free_search_backend() -> SearchBackend:
    searxng_url = os.getenv("DEEPR_SEARXNG_URL")
    if searxng_url:
        return SearXNGSearchBackend(searxng_url)
    return BuiltinSearchBackend(web_backend="duckduckgo")


def _deep_search_queries(query: str, max_queries: int) -> tuple[str, ...]:
    """Generate bounded search routes for deep local context."""
    base = " ".join(_URL_RE.sub(" ", query).split())
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

    async def search_one(search_query: str) -> tuple[list[SearchResult], str]:
        try:
            return await search_backend.search(search_query, num_results=max_search_results), ""
        except Exception as exc:
            return [], f"search failed for {search_query!r}: {exc}"

    results: list[SearchResult] = []
    errors: list[str] = []
    backend_name = str(search_backend.name).strip().lower()
    concurrency = 1 if backend_name in _SERIAL_SEARCH_BACKENDS else _MAX_CONCURRENT_SEARCHES
    for offset in range(0, len(search_queries), concurrency):
        batch = search_queries[offset : offset + concurrency]
        outcomes = await asyncio.gather(*(search_one(search_query) for search_query in batch))
        for search_results, error in outcomes:
            results.extend(search_results)
            if error:
                errors.append(error)
    return results, errors


def _is_retrievable_url_form(value: str) -> bool:
    """Accept only bounded absolute HTTP(S) candidates before fetch admission."""
    if not value or len(value) > 8192 or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        _ = parsed.port
    except (TypeError, ValueError):
        return False
    return retrieval_host_key(value) != _UNSAFE_RETRIEVAL_HOST


def _retrieval_urls(
    query: str,
    search_results: list[SearchResult],
) -> tuple[list[str], dict[str, SearchResult], int]:
    urls: list[str] = []
    seen_urls: set[str] = set()
    result_by_url: dict[str, SearchResult] = {}
    rejected_count = 0

    for url in _extract_urls(query):
        if not _is_retrievable_url_form(url):
            rejected_count += 1
            continue
        seen_urls.add(url)
        urls.append(url)

    for result in search_results:
        if not result.url or result.url in seen_urls:
            continue
        if not _is_retrievable_url_form(result.url):
            rejected_count += 1
            continue
        seen_urls.add(result.url)
        urls.append(result.url)
        result_by_url[result.url] = result

    return urls, result_by_url, rejected_count


async def _source_from_url(
    url: str,
    *,
    result_by_url: dict[str, SearchResult],
    browser_backend: BrowserBackend | None,
    cached_by_url: dict[str, CachedSource],
    fetch: bool,
) -> FreshSource:
    result = result_by_url.get(url)
    title = result.title if result else url
    snippet = result.snippet if result else ""
    source_name = result.source if result else "explicit-url"
    cached = cached_by_url.get(url)
    if browser_backend is None or not fetch:
        return FreshSource(title=title, url=url, snippet=snippet, source=source_name)

    try:
        page = await _fetch_page(browser_backend, url, validators=cached.validators if cached else None)
        if page.status_code == 304:
            return _source_from_not_modified_page(
                page,
                fallback_title=title,
                fallback_url=url,
                snippet=snippet,
                source_name=source_name,
                browser_name=browser_backend.name,
                cached=cached,
            )
        if page.status_code and page.text.strip():
            return FreshSource(
                title=page.title or title,
                url=page.url or url,
                snippet=snippet,
                content=page.text,
                source=f"{source_name}+{browser_backend.name}",
                fetched=True,
                etag=page.etag,
                last_modified=page.last_modified,
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
    cached_by_url: dict[str, CachedSource],
    max_fetches: int,
) -> tuple[FreshSource, ...]:
    fetch_count = min(len(urls), max(0, max_fetches)) if browser_backend is not None else 0
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)
    host_locks: dict[str, asyncio.Lock] = {}

    async def fetch_source(url: str) -> FreshSource:
        host_lock = host_locks.setdefault(retrieval_host_key(url), asyncio.Lock())
        async with host_lock:
            async with semaphore:
                return await _source_from_url(
                    url,
                    result_by_url=result_by_url,
                    browser_backend=browser_backend,
                    cached_by_url=cached_by_url,
                    fetch=True,
                )

    sources = list(await asyncio.gather(*(fetch_source(url) for url in urls[:fetch_count])))
    for url in urls[fetch_count:]:
        sources.append(
            await _source_from_url(
                url,
                result_by_url=result_by_url,
                browser_backend=browser_backend,
                cached_by_url=cached_by_url,
                fetch=False,
            )
        )
    return tuple(sources)


def _browser_accepts_validators(browser_backend: BrowserBackend) -> bool:
    try:
        parameters = inspect.signature(browser_backend.fetch_page).parameters
    except (TypeError, ValueError):
        return False
    return "validators" in parameters or any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in parameters.values()
    )


async def _fetch_page(
    browser_backend: BrowserBackend,
    url: str,
    *,
    validators: PageValidators | None,
) -> PageContent:
    if validators is not None and _browser_accepts_validators(browser_backend):
        return await browser_backend.fetch_page(url, validators=validators)
    return await browser_backend.fetch_page(url)


def _source_from_not_modified_page(
    page: PageContent,
    *,
    fallback_title: str,
    fallback_url: str,
    snippet: str,
    source_name: str,
    browser_name: str,
    cached: CachedSource | None,
) -> FreshSource:
    if cached is None:
        return FreshSource(
            title=fallback_title,
            url=page.url or fallback_url,
            snippet=snippet,
            source=f"{source_name}+{browser_name}",
            error="conditional fetch returned 304 without cached source metadata",
            not_modified=True,
            etag=page.etag,
            last_modified=page.last_modified,
        )
    return FreshSource(
        title=page.title if page.title and page.title != "Not modified" else cached.title or fallback_title,
        url=page.url or cached.url or fallback_url,
        snippet=snippet,
        content=cached.excerpt,
        source=f"{source_name}+{browser_name}",
        fetched=False,
        etag=page.etag or cached.etag,
        last_modified=page.last_modified or cached.last_modified,
        not_modified=True,
        content_hash_value=cached.content_hash,
    )


async def retrieve_fresh_context(
    query: str,
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
    search_queries: tuple[str, ...] | None = None,
    mode: str = "fresh",
    prior_source_pack: dict[str, object] | None = None,
) -> FreshContext:
    """Retrieve a bounded context pack for a local model.

    The default has no search backend so callers cannot accidentally spend via
    API-key search providers. Use ``make_free_fresh_context_builder`` for the
    free-only DuckDuckGo path plus direct page fetches.
    """
    cfg = config or FreshContextConfig()
    active_search_queries = (query,) if search_queries is None else search_queries
    search_results, errors = await _collect_search_results(
        search_backend,
        active_search_queries,
        max_search_results=cfg.max_search_results,
    )
    urls, result_by_url, rejected_url_count = _retrieval_urls(query, search_results)
    if rejected_url_count:
        errors.append(f"ignored {rejected_url_count} candidate URL(s) without a retrievable absolute HTTP(S) form")
    cached_by_url = cached_sources_from_pack(prior_source_pack)
    sources = await _build_sources(
        urls,
        result_by_url=result_by_url,
        browser_backend=browser_backend,
        cached_by_url=cached_by_url,
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
        min_content_addressed_sources=3,
    )


async def retrieve_deep_fresh_context(
    query: str,
    *,
    search_backend: SearchBackend | None = None,
    browser_backend: BrowserBackend | None = None,
    config: FreshContextConfig | None = None,
    prior_source_pack: dict[str, object] | None = None,
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
        prior_source_pack=prior_source_pack,
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

    async def build(query: str, *, prior_source_pack: dict[str, object] | None = None) -> FreshContext:
        return await retrieve_fresh_context(
            query,
            search_backend=free_search,
            browser_backend=browser,
            config=cfg,
            prior_source_pack=prior_source_pack,
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

    async def build(query: str, *, prior_source_pack: dict[str, object] | None = None) -> FreshContext:
        return await retrieve_deep_fresh_context(
            query,
            search_backend=free_search,
            browser_backend=browser,
            config=cfg,
            prior_source_pack=prior_source_pack,
        )

    return build
