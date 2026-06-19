"""Tests for search backend error visibility and fallback behavior."""

from unittest.mock import patch

import pytest

from deepr.tools.search_backend import BuiltinSearchBackend, SearXNGSearchBackend


class _FailingTool:
    def __init__(self, *args, **kwargs):
        pass

    async def execute(self, *_args, **_kwargs):
        raise RuntimeError("backend boom")


class _BadInitTool:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("init boom")


class _FakeResponse:
    def __init__(self, data=None, *, error=None):
        self._data = data or {}
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return self._data


class _FakeAsyncClient:
    calls = []
    response = _FakeResponse()

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, *, params):
        self.calls.append((url, params))
        return self.response


@pytest.mark.asyncio
async def test_builtin_search_logs_and_returns_empty_on_exception(caplog):
    backend = BuiltinSearchBackend()

    with patch("deepr.tools.web_search.WebSearchTool", _FailingTool), caplog.at_level("WARNING"):
        results = await backend.search("test query")

    assert results == []
    assert "Builtin search backend failed for query" in caplog.text
    assert "backend boom" in caplog.text


@pytest.mark.asyncio
async def test_builtin_health_check_logs_and_returns_false(caplog):
    backend = BuiltinSearchBackend()

    with patch("deepr.tools.web_search.WebSearchTool", _BadInitTool), caplog.at_level("WARNING"):
        healthy = await backend.health_check()

    assert healthy is False
    assert "Builtin search backend health check failed" in caplog.text
    assert "init boom" in caplog.text


@pytest.mark.asyncio
async def test_searxng_search_maps_json_results(monkeypatch):
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.response = _FakeResponse(
        {
            "results": [
                {
                    "title": "Result",
                    "url": "https://example.com/result",
                    "content": "Snippet",
                    "score": "2.5",
                    "engine": "duckduckgo",
                },
                {"title": "Missing URL", "content": "ignored"},
            ]
        }
    )

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    backend = SearXNGSearchBackend("http://127.0.0.1:8080")
    results = await backend.search("local deep research", num_results=5)

    assert _FakeAsyncClient.calls == [("http://127.0.0.1:8080/search", {"q": "local deep research", "format": "json"})]
    assert len(results) == 1
    assert results[0].title == "Result"
    assert results[0].url == "https://example.com/result"
    assert results[0].snippet == "Snippet"
    assert results[0].score == 2.5
    assert results[0].source == "searxng:duckduckgo"


@pytest.mark.asyncio
async def test_searxng_search_requires_base_url():
    assert await SearXNGSearchBackend("").search("q") == []
    assert await SearXNGSearchBackend("").health_check() is False
