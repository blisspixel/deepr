"""Tests for free retrieval context used by local maintenance."""

from __future__ import annotations

from deepr.backends.fresh_context import (
    FreshContextConfig,
    FreshSource,
    make_free_fresh_context_builder,
    retrieve_fresh_context,
)
from deepr.tools.browser_backend import PageContent
from deepr.tools.search_backend import SearchResult


class _SearchBackend:
    name = "fake-search"

    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    async def search(self, query: str, num_results: int = 10):
        self.calls.append((query, num_results))
        if self.error:
            raise self.error
        return self.results[:num_results]

    async def health_check(self):
        return True


class _BrowserBackend:
    name = "fake-browser"

    def __init__(self, pages=None):
        self.pages = pages or {}
        self.calls = []

    async def fetch_page(self, url: str):
        self.calls.append(url)
        return self.pages.get(url, PageContent(url=url, title="Missing", text="", status_code=0))

    async def health_check(self):
        return True


async def test_retrieve_fresh_context_searches_and_fetches_sources():
    search = _SearchBackend(
        [
            SearchResult(
                title="Release notes",
                url="https://example.com/release",
                snippet="Version changed",
                source="duck",
            )
        ]
    )
    browser = _BrowserBackend(
        {
            "https://example.com/release": PageContent(
                url="https://example.com/release",
                title="Release notes",
                text="The release shipped today with a new pricing tier.",
            )
        }
    )

    context = await retrieve_fresh_context("what changed?", search_backend=search, browser_backend=browser)

    assert search.calls == [("what changed?", 5)]
    assert browser.calls == ["https://example.com/release"]
    assert context.has_sources is True
    assert context.sources[0].fetched is True
    prompt = context.to_prompt_context()
    assert "[S1] Release notes" in prompt
    assert "new pricing tier" in prompt


async def test_retrieve_fresh_context_uses_explicit_urls_without_search():
    browser = _BrowserBackend(
        {
            "https://example.com/page": PageContent(
                url="https://example.com/page",
                title="Page",
                text="Current page text",
            )
        }
    )

    context = await retrieve_fresh_context("read https://example.com/page.", browser_backend=browser)

    assert context.search_backend == "none"
    assert context.sources[0].url == "https://example.com/page"
    assert "Current page text" in context.to_prompt_context()


async def test_retrieve_fresh_context_records_search_errors():
    context = await retrieve_fresh_context(
        "q",
        search_backend=_SearchBackend(error=RuntimeError("down")),
        browser_backend=_BrowserBackend(),
    )

    assert context.sources == ()
    assert context.errors == ("search failed: down",)
    assert "No fresh web sources" in context.to_prompt_context()


def test_fresh_source_excerpt_truncates():
    source = FreshSource(title="T", url="https://x", content="abcdef")
    assert source.excerpt(4) == "a..."


async def test_make_free_builder_uses_injected_backends():
    search = _SearchBackend([SearchResult(title="T", url="https://x", snippet="S")])
    browser = _BrowserBackend({"https://x": PageContent(url="https://x", title="T", text="Body")})
    builder = make_free_fresh_context_builder(
        search_backend=search,
        browser_backend=browser,
        config=FreshContextConfig(max_search_results=1),
    )

    context = await builder("q")

    assert context.search_backend == "fake-search"
    assert context.browser_backend == "fake-browser"
    assert context.sources[0].content == "Body"
