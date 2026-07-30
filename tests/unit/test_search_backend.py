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
async def test_searxng_search_blocks_before_http_client_construction():
    backend = SearXNGSearchBackend("http://127.0.0.1:8080")

    with patch("httpx.AsyncClient", side_effect=AssertionError("must not construct HTTP client")) as client:
        with pytest.raises(RuntimeError, match="does not prove its upstream engines"):
            await backend.search("local deep research", num_results=5)

    client.assert_not_called()


@pytest.mark.asyncio
async def test_searxng_search_requires_base_url():
    backend = SearXNGSearchBackend("")
    with pytest.raises(RuntimeError, match="SearXNG dispatch is disabled"):
        await backend.search("q")
    assert await backend.health_check() is False


def test_searxng_canonicalizes_owned_loopback_base_path():
    backend = SearXNGSearchBackend("http://localhost:8080/searxng/")

    assert backend._base_url == "http://127.0.0.1:8080/searxng"


@pytest.mark.parametrize(
    "configured_url",
    [
        "https://search.example.com",
        "http://192.168.1.25:8080",
        "http://searxng:8080",
    ],
)
def test_searxng_rejects_remote_endpoint_before_search(configured_url):
    with pytest.raises(ValueError, match="remote endpoints need explicit cost attestation"):
        SearXNGSearchBackend(configured_url)


def test_searxng_rejects_remote_endpoint_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPR_SEARXNG_URL", "https://search.example.com")

    with pytest.raises(ValueError, match="remote endpoints need explicit cost attestation"):
        SearXNGSearchBackend()


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf"), True])
def test_searxng_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="finite positive"):
        SearXNGSearchBackend("http://127.0.0.1:8080", timeout=timeout)
