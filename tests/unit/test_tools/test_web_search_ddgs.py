"""Regression tests for the DuckDuckGo free-search backend.

The legacy ``duckduckgo_search`` package was renamed to ``ddgs`` and its old
endpoint now returns nothing, which silently broke the only keyless web-search
path (and with it $0 fresh-context expert maintenance). These pin the new
behavior: prefer ``ddgs``, map its fields, and degrade gracefully on error.
"""

from __future__ import annotations

import sys
import types

import pytest

from deepr.tools.web_search import WebSearchTool, _retry_async


def _install_fake_ddgs(monkeypatch, *, rows=None, error=None, fail_first=None, attempts=None):
    """Install a fake ``ddgs`` module.

    ``error`` raises on every call unless ``fail_first`` is set, in which case it
    raises only on the first ``fail_first`` calls and then returns ``rows``.
    ``attempts`` (a list) records each call so a test can assert the retry count.
    """
    module = types.ModuleType("ddgs")
    fail_through = fail_first if fail_first is not None else 10**9

    class _FakeDDGS:
        def text(self, query, max_results=10):
            if attempts is not None:
                attempts.append(query)
            call_index = len(attempts) if attempts is not None else 1
            if error is not None and call_index <= fail_through:
                raise error
            return list(rows or [])

    module.DDGS = _FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", module)


class TestDuckDuckGoBackend:
    async def test_maps_ddgs_fields(self, monkeypatch):
        _install_fake_ddgs(
            monkeypatch,
            rows=[{"title": "Codex CLI", "href": "https://example.com/codex", "body": "snippet text"}],
        )
        result = await WebSearchTool()._search_duckduckgo("agentic CLIs", 5)
        assert result.success
        assert result.data[0] == {
            "title": "Codex CLI",
            "url": "https://example.com/codex",
            "snippet": "snippet text",
        }
        assert result.metadata["backend"] == "duckduckgo"

    async def test_network_error_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr("deepr.tools.web_search._DDG_BACKOFF_BASE_S", 0.0)
        attempts: list[str] = []
        _install_fake_ddgs(monkeypatch, error=RuntimeError("rate limited"), attempts=attempts)
        result = await WebSearchTool()._search_duckduckgo("q", 3)
        assert not result.success
        assert result.data is None
        assert "rate limited" in result.error
        assert "after 3 attempts" in result.error
        assert len(attempts) == 3  # retried before degrading

    async def test_retries_then_succeeds_on_transient_rate_limit(self, monkeypatch):
        monkeypatch.setattr("deepr.tools.web_search._DDG_BACKOFF_BASE_S", 0.0)
        attempts: list[str] = []
        _install_fake_ddgs(
            monkeypatch,
            rows=[{"title": "T", "href": "https://example.com", "body": "b"}],
            error=RuntimeError("rate limited"),
            fail_first=2,
            attempts=attempts,
        )
        result = await WebSearchTool()._search_duckduckgo("q", 3)
        assert result.success
        assert result.data[0]["url"] == "https://example.com"
        assert len(attempts) == 3  # failed twice, succeeded on the third

    async def test_missing_package_reports_install_hint(self, monkeypatch):
        # Neither ddgs nor the legacy package importable.
        monkeypatch.setitem(sys.modules, "ddgs", None)
        monkeypatch.setitem(sys.modules, "duckduckgo_search", None)
        result = await WebSearchTool()._search_duckduckgo("q", 3)
        assert not result.success
        assert "pip install ddgs" in result.error


class TestRetryAsync:
    async def _no_sleep(self, _delay):
        return None

    async def test_returns_on_first_success_without_sleeping(self):
        slept: list[float] = []

        async def sleep(delay):
            slept.append(delay)

        async def op():
            return 42

        assert await _retry_async(op, attempts=3, base_delay=1.0, sleep=sleep) == 42
        assert slept == []

    async def test_retries_then_succeeds(self):
        calls = {"n": 0}

        async def op():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        assert await _retry_async(op, attempts=3, base_delay=0.0, sleep=self._no_sleep) == "ok"
        assert calls["n"] == 3

    async def test_reraises_last_error_after_exhausting_attempts(self):
        async def op():
            raise RuntimeError("always")

        with pytest.raises(RuntimeError, match="always"):
            await _retry_async(op, attempts=3, base_delay=0.0, sleep=self._no_sleep)

    async def test_backoff_grows_exponentially(self):
        slept: list[float] = []

        async def sleep(delay):
            slept.append(delay)

        async def op():
            raise RuntimeError("x")

        with pytest.raises(RuntimeError):
            await _retry_async(op, attempts=3, base_delay=1.5, sleep=sleep)
        # Two sleeps between three attempts: 1.5 * 2**0, 1.5 * 2**1.
        assert slept == [1.5, 3.0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
