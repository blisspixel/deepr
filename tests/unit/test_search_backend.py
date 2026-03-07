"""Tests for search backend error visibility and fallback behavior."""

from unittest.mock import patch

import pytest

from deepr.tools.search_backend import BuiltinSearchBackend


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
