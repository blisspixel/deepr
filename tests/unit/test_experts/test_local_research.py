"""Unit tests for web-grounded local research (deepr/experts/local_research.py).

Everything is faked - no network, no model - so these are fast and deterministic.
They pin the behavior that makes the $0 path trustworthy: live results are
fetched and cited, snippets stay diagnostic-only, under-ready retrieval blocks
model generation, and the result carries a replayable source pack.
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from types import SimpleNamespace

import pytest

from deepr.experts.local_research import gather_fresh_context, gather_sources, research_web_local


class FakeToolResult:
    def __init__(self, success, data, metadata=None):
        self.success = success
        self.data = data
        self.metadata = metadata or {"backend": "duckduckgo"}


class FakeSearch:
    def __init__(self, results, success=True):
        self._results = results
        self._success = success
        self.calls = []

    async def execute(self, query, num_results=8, **kwargs):
        self.calls.append((query, num_results))
        return FakeToolResult(self._success, self._results)


class FakeBrowser:
    """Returns full text per URL; URLs in ``blocked`` raise (bot-blocked site)."""

    def __init__(self, pages, blocked=()):
        self._pages = pages
        self._blocked = set(blocked)
        self.calls = []

    @property
    def name(self):
        return "fake-browser"

    async def fetch_page(self, url):
        self.calls.append(url)
        if url in self._blocked:
            raise RuntimeError("blocked")
        return SimpleNamespace(url=url, title="t", text=self._pages.get(url, ""))


class DelayedFakeBrowser(FakeBrowser):
    def __init__(self, pages, delay=0.5):
        super().__init__(pages)
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def fetch_page(self, url):
        self.calls.append(url)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            return SimpleNamespace(url=url, title="t", text=self._pages.get(url, ""))
        finally:
            self.active -= 1


class FakeChatClient:
    """Mimics the AsyncOpenAI chat surface used by the synthesizer."""

    def __init__(self, content):
        self._content = content
        self.captured = {}
        self.calls = 0

        async def _create(model, messages, **kwargs):
            self.calls += 1
            self.captured["model"] = model
            self.captured["messages"] = messages
            msg = SimpleNamespace(content=self._content)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


async def test_gather_sources_fetches_full_page_over_snippet():
    search = FakeSearch([{"title": "A", "url": "http://a", "snippet": "short"}])
    browser = FakeBrowser({"http://a": "a much longer full page body" * 5})
    sources = await gather_sources(topic="x", search=search, browser=browser)
    assert len(sources) == 1
    assert sources[0]["url"] == "http://a"
    assert "full page body" in sources[0]["text"]  # page text won over the snippet


async def test_gather_fresh_context_fetches_concurrently_with_a_small_bound():
    urls = [f"http://source-{index}" for index in range(5)]
    search = FakeSearch([{"title": url, "url": url, "snippet": ""} for url in urls])
    browser = DelayedFakeBrowser({url: f"content for {url}" for url in urls})

    started = perf_counter()
    context = await gather_fresh_context(
        topic="bounded concurrent retrieval",
        search=search,
        browser=browser,
        num_results=5,
        max_pages=5,
    )
    elapsed = perf_counter() - started

    assert browser.max_active == 4
    assert elapsed < 2.0
    assert browser.calls == urls
    assert [source.url for source in context.sources] == urls


async def test_gather_fresh_context_serializes_fetches_to_the_same_host():
    urls = [f"http://example.com/source-{index}" for index in range(4)]
    search = FakeSearch([{"title": url, "url": url, "snippet": ""} for url in urls])
    browser = DelayedFakeBrowser(
        {url: f"content for {url}" for url in urls},
        delay=0.01,
    )

    context = await gather_fresh_context(
        topic="same host retrieval",
        search=search,
        browser=browser,
        num_results=4,
        max_pages=4,
    )

    assert browser.max_active == 1
    assert browser.calls == urls
    assert [source.url for source in context.sources] == urls


async def test_gather_sources_does_not_promote_snippet_when_page_blocked():
    search = FakeSearch([{"title": "A", "url": "http://a", "snippet": "the snippet text"}])
    browser = FakeBrowser(pages={}, blocked={"http://a"})  # fetch raises
    sources = await gather_sources(topic="x", search=search, browser=browser)
    assert sources == []


async def test_gather_fresh_context_keeps_failed_fetch_as_diagnostic_candidate():
    search = FakeSearch([{"title": "A", "url": "http://a", "snippet": "the snippet text"}])
    context = await gather_fresh_context(topic="x", search=search, browser=FakeBrowser(pages={}, blocked={"http://a"}))

    pack = context.to_source_pack()
    assert pack["source_count"] == 0
    assert pack["retrieved_source_count"] == 1
    assert pack["retrieval_candidates"][0]["snippet"] == "the snippet text"
    assert pack["retrieval_candidates"][0]["content_addressed"] is False
    assert "blocked" in pack["retrieval_candidates"][0]["error"]


async def test_gather_sources_empty_when_search_fails():
    search = FakeSearch([], success=False)
    sources = await gather_sources(topic="x", search=search, browser=FakeBrowser({}))
    assert sources == []


async def test_research_web_local_builds_cited_report():
    search = FakeSearch(
        [
            {"title": "Latest A", "url": "http://a", "snippet": "s1"},
            {"title": "Latest B", "url": "http://b", "snippet": "s2"},
        ]
    )
    browser = FakeBrowser({"http://a": "alpha content " * 20, "http://b": "beta content " * 20})
    client = FakeChatClient("The field advanced [S1]. Also notable [S2].")

    out = await research_web_local(
        "state of X in 2026", model="local-model", client=client, search=search, browser=browser
    )

    assert out["cost"] == 0.0
    assert out["answer"].startswith("# state of X in 2026")
    # The synthesized body and a real Sources section with both URLs are present.
    assert "advanced [S1]" in out["answer"]
    assert "## Sources" in out["answer"]
    assert "http://a" in out["answer"] and "http://b" in out["answer"]
    assert out["sources"] == [
        {"label": "S1", "title": "t", "url": "http://a"},
        {"label": "S2", "title": "t", "url": "http://b"},
    ]
    # The live source text was actually handed to the model (grounding).
    user_msg = client.captured["messages"][-1]["content"]
    assert "alpha content" in user_msg and "beta content" in user_msg
    assert out["fresh_context"]["generation_readiness"]["ready"] is True
    assert out["source_pack"]["source_count"] == 2
    assert all(source["content_hash"] for source in out["source_pack"]["sources"])


async def test_research_web_local_errors_without_results():
    search = FakeSearch([], success=False)
    out = await research_web_local(
        "x", model="m", client=FakeChatClient("ignored"), search=search, browser=FakeBrowser({})
    )
    assert out["answer"] == ""
    assert out["error_code"] == "fresh_context_not_ready"
    assert out["retryable"] is True
    assert out["no_metered_fallback"] is True


async def test_research_web_local_errors_on_empty_model_output():
    search = FakeSearch(
        [
            {"title": "A", "url": "http://a", "snippet": "s"},
            {"title": "B", "url": "http://b", "snippet": "s"},
        ]
    )
    out = await research_web_local(
        "x",
        model="m",
        client=FakeChatClient("   "),
        search=search,
        browser=FakeBrowser({"http://a": "body " * 20, "http://b": "other " * 20}),
    )
    assert out["answer"] == ""
    assert "empty" in out["error"]


async def test_research_web_local_no_model_available():
    # model=None and (faked) no default local model -> clean error, no raise.
    search = FakeSearch(
        [
            {"title": "A", "url": "http://a", "snippet": "s"},
            {"title": "B", "url": "http://b", "snippet": "s"},
        ]
    )
    out = await research_web_local(
        "x",
        model="",
        client=FakeChatClient("x"),
        search=search,
        browser=FakeBrowser({"http://a": "body " * 20, "http://b": "other " * 20}),
    )
    assert out["answer"] == ""
    assert "no local model" in out["error"]


async def test_under_ready_sources_fail_before_model_generation_and_preserve_diagnostics():
    search = FakeSearch(
        [
            {"title": "A", "url": "http://a", "snippet": "s1"},
            {"title": "B", "url": "http://user:pass@b/release?token=secret#private", "snippet": "s2"},
            {"title": "C", "url": "http://c", "snippet": "s3"},
        ]
    )
    client = FakeChatClient("must not run")
    out = await research_web_local(
        "current topic",
        model="plan-or-local",
        client=client,
        search=search,
        browser=FakeBrowser(
            {"http://a": "fetched source" * 20},
            blocked={"http://user:pass@b/release?token=secret#private", "http://c"},
        ),
        max_pages=3,
    )

    assert client.calls == 0
    assert out["answer"] == ""
    assert out["error_code"] == "fresh_context_not_ready"
    assert out["fresh_context"]["source_count"] == 1
    assert out["fresh_context"]["retrieved_source_count"] == 3
    assert len(out["source_pack"]["retrieval_candidates"]) == 3
    assert len(out["source_pack"]["errors"]) == 2
    failed = out["source_pack"]["retrieval_candidates"][1]
    assert failed["diagnostic_label"] == "R2"
    assert failed["diagnostic_target"] == "http://b/release"
    assert "secret" not in failed["diagnostic_target"] and "pass" not in failed["diagnostic_target"]


async def test_explicit_url_allows_one_replayable_source():
    url = "https://example.com/release"
    client = FakeChatClient("A release changed [S1].")
    out = await research_web_local(
        f"Review {url}",
        model="m",
        client=client,
        search=FakeSearch([], success=False),
        browser=FakeBrowser({url: "official release content " * 20}),
        max_pages=1,
    )

    assert client.calls == 1
    assert out["fresh_context"]["generation_readiness"]["required_source_count"] == 1
    assert out["sources"][0]["url"] == url


async def test_retrieval_hard_caps_results_and_fetch_attempts():
    results = [
        {"title": f"Source {index}", "url": f"http://source-{index}", "snippet": "snippet"} for index in range(30)
    ]
    search = FakeSearch(results)
    browser = FakeBrowser({item["url"]: f"content {index}" * 20 for index, item in enumerate(results)})

    context = await gather_fresh_context(
        "bounded topic",
        search=search,
        browser=browser,
        num_results=10_000,
        max_pages=10_000,
    )

    assert search.calls == [("bounded topic", 20)]
    assert len(context.sources) == 20
    assert len(browser.calls) == 8
    assert context.to_source_pack()["source_count"] == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
