"""Coverage for ``deepr/tools/{web_search.py, base.py, registry.py, search_backend.py}``.

These modules sit on the boundary that lets agents reach the public internet,
so the failover/error paths matter even though they had no unit coverage.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.tools.base import Tool, ToolExecutor, ToolResult
from deepr.tools.registry import ToolRegistry
from deepr.tools.search_backend import (
    BuiltinSearchBackend,
    MCPSearchBackend,
    SearchBackend,
    SearchResult,
)
from deepr.tools.web_search import MCPWebSearchTool, WebSearchTool

# ---------------------------------------------------------------------- #
# WebSearchTool
# ---------------------------------------------------------------------- #


class TestWebSearchTool:
    def test_metadata_surface(self):
        tool = WebSearchTool(backend="duckduckgo")
        assert tool.name == "web_search"
        assert "Search the web" in tool.description
        assert tool.parameters["properties"]["query"]["type"] == "string"
        assert "query" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_brave_backend_fails_before_network(self):
        tool = WebSearchTool(backend="brave", brave_api_key="bk")
        with patch.object(tool, "_search_duckduckgo") as free_search:
            res = await tool.execute(query="hi", num_results=2)
        assert res.success is False
        assert "price, reserve, and settle" in res.error
        free_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_positional_query_contract_still_enforces_metered_gate(self):
        tool = WebSearchTool(backend="brave", brave_api_key="bk")
        res = await tool.execute("hi", 2)
        assert res.success is False
        assert "disabled" in res.error

    @pytest.mark.asyncio
    async def test_tavily_backend_fails_before_network(self):
        tool = WebSearchTool(backend="tavily", tavily_api_key="tk")
        res = await tool.execute(query="q", num_results=1)
        assert res.success is False
        assert "price, reserve, and settle" in res.error

    @pytest.mark.asyncio
    async def test_named_metered_backend_is_blocked_without_key(self):
        tool = WebSearchTool(backend="brave")
        res = await tool.execute(query="hi")
        assert res.success is False
        assert "disabled" in res.error

    @pytest.mark.asyncio
    async def test_auto_mode_ignores_ambient_metered_keys(self):
        tool = WebSearchTool(backend="auto", brave_api_key="bk", tavily_api_key="tk")
        with patch.object(
            tool,
            "_search_duckduckgo",
            return_value=ToolResult(success=True, data=[], metadata={"backend": "duckduckgo"}),
        ) as free_search:
            res = await tool.execute(query="q", num_results=1)
        assert res.success is True
        assert res.metadata["backend"] == "duckduckgo"
        free_search.assert_awaited_once_with("q", 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("num_results", [0, 21])
    async def test_result_count_is_bounded_before_search(self, num_results):
        tool = WebSearchTool(backend="auto")
        with patch.object(tool, "_search_duckduckgo") as free_search:
            res = await tool.execute(query="q", num_results=num_results)
        assert res.success is False
        assert "between 1 and 20" in res.error
        free_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_duckduckgo_missing_lib_reports_install_hint(self):
        tool = WebSearchTool(backend="duckduckgo")
        # Force the import inside _search_duckduckgo to fail.
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def _fake_import(name, *args, **kwargs):
            if name in ("ddgs", "duckduckgo_search"):
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            res = await tool.execute(query="q")
        assert res.success is False
        assert "pip install ddgs" in res.error


# ---------------------------------------------------------------------- #
# MCPWebSearchTool disabled transport behavior
# ---------------------------------------------------------------------- #


class TestMCPWebSearchTool:
    @pytest.mark.asyncio
    async def test_returns_transport_error(self):
        tool = MCPWebSearchTool()
        assert tool.name == "mcp_web_search"
        res = await tool.execute(query="x")
        assert res.success is False
        assert "transport is not configured" in res.error

    @pytest.mark.asyncio
    async def test_positional_query_contract_returns_transport_error(self):
        tool = MCPWebSearchTool()
        res = await tool.execute("x")
        assert res.success is False
        assert "transport is not configured" in res.error


# ---------------------------------------------------------------------- #
# Tool / ToolExecutor base
# ---------------------------------------------------------------------- #


class _EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo input"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        if text == "BOOM":
            raise RuntimeError("kaboom")
        return ToolResult(success=True, data={"echoed": text})


class TestToolBase:
    def test_to_openai_tool_shape(self):
        t = _EchoTool()
        sch = t.to_openai_tool()
        assert sch["type"] == "function"
        assert sch["function"]["name"] == "echo"
        assert sch["function"]["parameters"]["type"] == "object"

    def test_to_anthropic_tool_shape(self):
        t = _EchoTool()
        sch = t.to_anthropic_tool()
        assert sch["name"] == "echo"
        assert "input_schema" in sch

    @pytest.mark.asyncio
    async def test_executor_unknown_tool(self):
        ex = ToolExecutor()
        res = await ex.execute("missing")
        assert res.success is False
        assert "not found" in res.error

    @pytest.mark.asyncio
    async def test_executor_runs_tool(self):
        ex = ToolExecutor([_EchoTool()])
        res = await ex.execute("echo", text="hi")
        assert res.success is True
        assert res.data == {"echoed": "hi"}

    @pytest.mark.asyncio
    async def test_executor_wraps_tool_exception(self):
        ex = ToolExecutor([_EchoTool()])
        res = await ex.execute("echo", text="BOOM")
        assert res.success is False
        assert "Tool execution failed" in res.error

    def test_executor_definitions_openai(self):
        ex = ToolExecutor([_EchoTool()])
        defs = ex.get_tool_definitions("openai")
        assert defs[0]["type"] == "function"

    def test_executor_definitions_anthropic(self):
        ex = ToolExecutor([_EchoTool()])
        defs = ex.get_tool_definitions("anthropic")
        assert defs[0]["name"] == "echo"

    def test_executor_definitions_unknown_format(self):
        ex = ToolExecutor([_EchoTool()])
        with pytest.raises(ValueError, match="Unknown format"):
            ex.get_tool_definitions("xml")

    def test_tool_result_timestamp_defaulted(self):
        r = ToolResult(success=True, data=None)
        assert r.timestamp is not None

    def test_tool_result_explicit_none_timestamp_defaulted(self):
        r = ToolResult(success=True, data=None, timestamp=None)
        assert r.timestamp is not None


# ---------------------------------------------------------------------- #
# ToolRegistry
# ---------------------------------------------------------------------- #


class TestToolRegistry:
    def test_default_tools_includes_web_search_by_default(self):
        tools = ToolRegistry.get_default_tools()
        assert any(t.name == "web_search" for t in tools)

    def test_default_tools_can_omit_web_search(self):
        tools = ToolRegistry.get_default_tools(web_search=False)
        assert tools == []

    def test_create_executor_registers_default_tools(self):
        ex = ToolRegistry.create_executor()
        assert "web_search" in ex.tools


# ---------------------------------------------------------------------- #
# Search backends
# ---------------------------------------------------------------------- #


class TestBuiltinSearchBackend:
    @pytest.mark.asyncio
    async def test_search_returns_parsed_results(self):
        backend = BuiltinSearchBackend()
        with patch("deepr.tools.web_search.WebSearchTool.execute", autospec=True) as exec_:

            async def fake_exec(self, *_args, **kwargs):
                assert kwargs["query"] == "hi"
                assert kwargs["num_results"] == 10
                return ToolResult(
                    success=True,
                    data=[
                        {"title": "T", "url": "https://x", "snippet": "snip"},
                    ],
                )

            exec_.side_effect = fake_exec
            out = await backend.search("hi")
        assert isinstance(out, list)
        assert len(out) == 1
        assert out[0].url == "https://x"
        assert out[0].source == "builtin"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_failure(self):
        backend = BuiltinSearchBackend()

        async def fake_exec(self, *_a, **_k):
            return ToolResult(success=False, data=None, error="no backend")

        with patch("deepr.tools.web_search.WebSearchTool.execute", side_effect=fake_exec, autospec=True):
            out = await backend.search("q")
        assert out == []

    @pytest.mark.asyncio
    async def test_search_swallows_exceptions(self):
        backend = BuiltinSearchBackend()

        async def boom(self, *_a, **_k):
            raise RuntimeError("net down")

        with patch("deepr.tools.web_search.WebSearchTool.execute", side_effect=boom, autospec=True):
            out = await backend.search("q")
        assert out == []

    @pytest.mark.asyncio
    async def test_health_check_constructs_tool(self):
        backend = BuiltinSearchBackend()
        assert (await backend.health_check()) is True

    def test_name_is_builtin(self):
        assert BuiltinSearchBackend().name == "builtin:auto"

    def test_name_includes_backend(self):
        assert BuiltinSearchBackend(web_backend="duckduckgo").name == "builtin:duckduckgo"


class TestBuiltinBrowserBackend:
    @pytest.mark.asyncio
    async def test_fetch_page_returns_extracted_text(self):
        from deepr.tools.browser_backend import BuiltinBrowserBackend

        class _FetchResult:
            success = True
            html = "<html><head><title>T</title></head><body><main>Body text</main></body></html>"
            content = html
            error = None

        class _Fetcher:
            def __init__(self, _config):
                self.config = _config

            def fetch(self, url):
                assert url == "https://example.com"
                return _FetchResult()

        with patch("deepr.utils.scrape.ContentFetcher", _Fetcher):
            page = await BuiltinBrowserBackend().fetch_page("https://example.com")

        assert page.title == "T"
        assert page.text == "Body text"
        assert page.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_pages_can_enter_scraper_concurrently(self):
        from deepr.tools.browser_backend import BuiltinBrowserBackend

        state_lock = threading.Lock()
        both_started = threading.Event()
        started = 0

        class _FetchResult:
            success = True
            html = "<html><body><main>Body text</main></body></html>"
            content = html
            error = None

        class _Fetcher:
            def __init__(self, _config):
                self.config = _config

            def fetch(self, _url):
                nonlocal started
                with state_lock:
                    started += 1
                    if started == 2:
                        both_started.set()
                assert both_started.wait(timeout=2)
                return _FetchResult()

        with patch("deepr.utils.scrape.ContentFetcher", _Fetcher):
            pages = await asyncio.wait_for(
                asyncio.gather(
                    BuiltinBrowserBackend().fetch_page("https://example.com/one"),
                    BuiltinBrowserBackend().fetch_page("https://example.com/two"),
                ),
                timeout=3,
            )

        assert [page.text for page in pages] == ["Body text", "Body text"]

    @pytest.mark.asyncio
    async def test_fetch_page_reports_fetch_failure(self):
        from deepr.tools.browser_backend import BuiltinBrowserBackend

        configs = []

        class _FetchResult:
            success = False
            html = None
            content = None
            error = "blocked"

        class _Fetcher:
            def __init__(self, _config):
                self.config = _config
                configs.append(_config)

            def fetch(self, _url):
                return _FetchResult()

        with patch("deepr.utils.scrape.ContentFetcher", _Fetcher):
            page = await BuiltinBrowserBackend().fetch_page("https://example.com")

        assert page.status_code == 0
        assert page.text == "blocked"
        assert configs[0].log_strategy_failures is True

    @pytest.mark.asyncio
    async def test_structured_failure_reporting_suppresses_generic_strategy_warning(self):
        from deepr.tools.browser_backend import BuiltinBrowserBackend

        configs = []

        class _FetchResult:
            success = False
            html = None
            content = None
            error = "blocked"

        class _Fetcher:
            def __init__(self, _config):
                self.config = _config
                configs.append(_config)

            def fetch(self, _url):
                return _FetchResult()

        with patch("deepr.utils.scrape.ContentFetcher", _Fetcher):
            page = await BuiltinBrowserBackend(structured_failure_reporting=True).fetch_page("https://example.com")

        assert page.status_code == 0
        assert page.text == "blocked"
        assert configs[0].log_strategy_failures is False


class TestMCPSearchBackend:
    @pytest.mark.asyncio
    async def test_search_raises_not_implemented(self):
        backend = MCPSearchBackend(server_name="brave-mcp")
        with pytest.raises(NotImplementedError):
            await backend.search("q")

    @pytest.mark.asyncio
    async def test_health_check_false(self):
        assert (await MCPSearchBackend().health_check()) is False

    def test_name_carries_server(self):
        assert MCPSearchBackend("tavily-mcp").name == "tavily-mcp"


class TestSearchResult:
    def test_dataclass_round_trip(self):
        r = SearchResult(title="t", url="u", snippet="s", score=0.5, source="x")
        assert r.title == "t" and r.score == 0.5

    def test_protocol_runtime_check_recognises_implementation(self):
        # Both backends satisfy the runtime_checkable Protocol.
        assert isinstance(BuiltinSearchBackend(), SearchBackend)
        assert isinstance(MCPSearchBackend(), SearchBackend)
