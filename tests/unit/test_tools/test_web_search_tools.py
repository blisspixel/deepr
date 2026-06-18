"""Coverage for ``deepr/tools/{web_search.py, base.py, registry.py, search_backend.py}``.

These modules sit on the boundary that lets agents reach the public internet,
so the failover/error paths matter even though they had no unit coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    async def test_brave_backend_calls_brave_api(self):
        tool = WebSearchTool(backend="brave", brave_api_key="bk")
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "web": {
                "results": [
                    {"title": "T", "url": "https://x", "description": "snip"},
                    {"title": "T2", "url": "https://y", "description": "snip2"},
                ]
            }
        }
        fake_response.raise_for_status.return_value = None
        with patch("deepr.tools.web_search.requests.get", return_value=fake_response) as get:
            res = await tool.execute(query="hi", num_results=2)
        assert res.success is True
        assert res.metadata["backend"] == "brave"
        assert len(res.data) == 2
        get.assert_called_once()
        called_headers = get.call_args.kwargs["headers"]
        assert called_headers["X-Subscription-Token"] == "bk"

    @pytest.mark.asyncio
    async def test_tavily_backend_calls_tavily_api(self):
        tool = WebSearchTool(backend="tavily", tavily_api_key="tk")
        fake = MagicMock()
        fake.json.return_value = {
            "results": [{"title": "A", "url": "https://a", "content": "snip"}],
        }
        fake.raise_for_status.return_value = None
        with patch("deepr.tools.web_search.requests.post", return_value=fake) as post:
            res = await tool.execute(query="q", num_results=1)
        assert res.success is True
        assert res.metadata["backend"] == "tavily"
        assert res.data[0]["url"] == "https://a"
        assert post.call_args.kwargs["json"]["api_key"] == "tk"

    @pytest.mark.asyncio
    async def test_no_backend_returns_error(self):
        tool = WebSearchTool(backend="brave")
        tool.brave_api_key = None
        res = await tool.execute(query="hi")
        assert res.success is False
        assert "No working web search backend" in res.error

    @pytest.mark.asyncio
    async def test_brave_failure_falls_through_to_tavily_in_auto_mode(self):
        tool = WebSearchTool(backend="auto", brave_api_key="bk", tavily_api_key="tk")
        # Brave raises, Tavily succeeds.
        with (
            patch(
                "deepr.tools.web_search.requests.get",
                side_effect=RuntimeError("brave 500"),
            ),
            patch("deepr.tools.web_search.requests.post") as post,
        ):
            ok = MagicMock()
            ok.json.return_value = {"results": [{"title": "x", "url": "https://x", "content": "s"}]}
            ok.raise_for_status.return_value = None
            post.return_value = ok
            res = await tool.execute(query="q", num_results=1)
            assert res.success is True
            assert res.metadata["backend"] == "tavily"

    @pytest.mark.asyncio
    async def test_duckduckgo_missing_lib_reports_install_hint(self):
        tool = WebSearchTool(backend="duckduckgo")
        # Force the import inside _search_duckduckgo to fail.
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "duckduckgo_search":
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            res = await tool.execute(query="q")
        assert res.success is False
        assert "duckduckgo-search not installed" in res.error


# ---------------------------------------------------------------------- #
# MCPWebSearchTool (placeholder)
# ---------------------------------------------------------------------- #


class TestMCPWebSearchTool:
    @pytest.mark.asyncio
    async def test_returns_not_implemented_error(self):
        tool = MCPWebSearchTool()
        assert tool.name == "mcp_web_search"
        res = await tool.execute(query="x")
        assert res.success is False
        assert "not yet implemented" in res.error


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
                pass

            def fetch(self, url):
                assert url == "https://example.com"
                return _FetchResult()

        with patch("deepr.utils.scrape.ContentFetcher", _Fetcher):
            page = await BuiltinBrowserBackend().fetch_page("https://example.com")

        assert page.title == "T"
        assert page.text == "Body text"
        assert page.status_code == 200

    @pytest.mark.asyncio
    async def test_fetch_page_reports_fetch_failure(self):
        from deepr.tools.browser_backend import BuiltinBrowserBackend

        class _FetchResult:
            success = False
            html = None
            content = None
            error = "blocked"

        class _Fetcher:
            def __init__(self, _config):
                pass

            def fetch(self, _url):
                return _FetchResult()

        with patch("deepr.utils.scrape.ContentFetcher", _Fetcher):
            page = await BuiltinBrowserBackend().fetch_page("https://example.com")

        assert page.status_code == 0
        assert page.text == "blocked"


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
