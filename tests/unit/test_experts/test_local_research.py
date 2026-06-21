"""Unit tests for web-grounded local research (deepr/experts/local_research.py).

Everything is faked - no network, no model - so these are fast and deterministic.
They pin the behavior that makes the $0 path trustworthy: live results are
fetched and cited, blocked pages degrade to snippets instead of failing, and the
report carries real URL provenance.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.local_research import gather_sources, research_web_local


class FakeToolResult:
    def __init__(self, success, data):
        self.success = success
        self.data = data


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

    async def fetch_page(self, url):
        if url in self._blocked:
            raise RuntimeError("blocked")
        return SimpleNamespace(url=url, title="t", text=self._pages.get(url, ""))


class FakeChatClient:
    """Mimics the AsyncOpenAI chat surface used by the synthesizer."""

    def __init__(self, content):
        self._content = content
        self.captured = {}

        async def _create(model, messages, **kwargs):
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


async def test_gather_sources_falls_back_to_snippet_when_page_blocked():
    search = FakeSearch([{"title": "A", "url": "http://a", "snippet": "the snippet text"}])
    browser = FakeBrowser(pages={}, blocked={"http://a"})  # fetch raises
    sources = await gather_sources(topic="x", search=search, browser=browser)
    assert sources == [{"title": "A", "url": "http://a", "text": "the snippet text"}]


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
    client = FakeChatClient("The field advanced [1]. Also notable [2].")

    out = await research_web_local(
        "state of X in 2026", model="local-model", client=client, search=search, browser=browser
    )

    assert out["cost"] == 0.0
    assert out["answer"].startswith("# state of X in 2026")
    # The synthesized body and a real Sources section with both URLs are present.
    assert "advanced [1]" in out["answer"]
    assert "## Sources" in out["answer"]
    assert "http://a" in out["answer"] and "http://b" in out["answer"]
    assert out["sources"] == [
        {"n": 1, "title": "Latest A", "url": "http://a"},
        {"n": 2, "title": "Latest B", "url": "http://b"},
    ]
    # The live source text was actually handed to the model (grounding).
    user_msg = client.captured["messages"][-1]["content"]
    assert "alpha content" in user_msg and "beta content" in user_msg


async def test_research_web_local_errors_without_results():
    search = FakeSearch([], success=False)
    out = await research_web_local("x", model="m", client=FakeChatClient("ignored"), search=search, browser=FakeBrowser({}))
    assert out["answer"] == ""
    assert "no web results" in out["error"]


async def test_research_web_local_errors_on_empty_model_output():
    search = FakeSearch([{"title": "A", "url": "http://a", "snippet": "s"}])
    out = await research_web_local(
        "x", model="m", client=FakeChatClient("   "), search=search, browser=FakeBrowser({"http://a": "body " * 20})
    )
    assert out["answer"] == ""
    assert "empty" in out["error"]


async def test_research_web_local_no_model_available():
    # model=None and (faked) no default local model -> clean error, no raise.
    out = await research_web_local("x", model="", client=FakeChatClient("x"), search=FakeSearch([]), browser=FakeBrowser({}))
    assert out["answer"] == ""
    assert "no local model" in out["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
