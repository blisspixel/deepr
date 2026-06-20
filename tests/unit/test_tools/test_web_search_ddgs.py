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

from deepr.tools.web_search import WebSearchTool


def _install_fake_ddgs(monkeypatch, *, rows=None, error=None):
    module = types.ModuleType("ddgs")

    class _FakeDDGS:
        def text(self, query, max_results=10):
            if error is not None:
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
        _install_fake_ddgs(monkeypatch, error=RuntimeError("rate limited"))
        result = await WebSearchTool()._search_duckduckgo("q", 3)
        assert not result.success
        assert result.data is None
        assert "rate limited" in result.error

    async def test_missing_package_reports_install_hint(self, monkeypatch):
        # Neither ddgs nor the legacy package importable.
        monkeypatch.setitem(sys.modules, "ddgs", None)
        monkeypatch.setitem(sys.modules, "duckduckgo_search", None)
        result = await WebSearchTool()._search_duckduckgo("q", 3)
        assert not result.success
        assert "pip install ddgs" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
