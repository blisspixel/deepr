"""Tests for skill tool execution and budget tracking.

Tests the MCPClientProxy, SkillExecutor, and budget management logic
in deepr.experts.skills.executor.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts.skills.definition import SkillBudget, SkillDefinition, SkillTool, SkillTrigger
from deepr.experts.skills.executor import MCPClientProxy, SkillExecutor, _COST_TIER_ESTIMATES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_python_tool(
    name: str = "add",
    module: str = "tools.math_tools",
    function: str = "add",
    cost_tier: str = "free",
) -> SkillTool:
    return SkillTool(
        name=name,
        type="python",
        description=f"Python tool {name}",
        module=module,
        function=function,
        cost_tier=cost_tier,
    )


def _make_mcp_tool(
    name: str = "search",
    cost_tier: str = "low",
    server_command: str = "node",
    server_args: list[str] | None = None,
    server_env: dict[str, str] | None = None,
    remote_tool_name: str | None = None,
) -> SkillTool:
    return SkillTool(
        name=name,
        type="mcp",
        description=f"MCP tool {name}",
        cost_tier=cost_tier,
        server_command=server_command,
        server_args=server_args or ["server.js"],
        server_env=server_env or {},
        remote_tool_name=remote_tool_name,
    )


def _make_skill(
    tmp_path: Path,
    tools: list[SkillTool] | None = None,
    name: str = "test-skill",
) -> SkillDefinition:
    skill_dir = tmp_path / name
    skill_dir.mkdir(exist_ok=True)
    return SkillDefinition(
        name=name,
        version="1.0.0",
        description="Test skill",
        path=skill_dir,
        tier="built-in",
        tools=tools or [],
    )


def _create_python_skill(tmp_path: Path) -> Path:
    """Create a real Python skill directory with a tools module."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir(exist_ok=True)
    tools_dir = skill_dir / "tools"
    tools_dir.mkdir(exist_ok=True)
    (tools_dir / "__init__.py").write_text("")
    (tools_dir / "math_tools.py").write_text(
        "def add(a, b):\n    return a + b\n\n"
        "async def async_add(a, b):\n    return a + b\n\n"
        "def broken():\n    raise ValueError('test error')\n"
    )
    return skill_dir


# ---------------------------------------------------------------------------
# MCPClientProxy._resolve_env
# ---------------------------------------------------------------------------


class TestMCPClientProxyResolveEnv:
    """Tests for MCPClientProxy._resolve_env static method."""

    def test_literal_values_pass_through(self):
        """Literal string values are returned unchanged."""
        env = {"KEY1": "value1", "KEY2": "value2"}
        result = MCPClientProxy._resolve_env(env)
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_resolve_existing_env_var(self, monkeypatch):
        """${VAR} references are resolved from os.environ."""
        monkeypatch.setenv("MY_SECRET", "s3cret")
        env = {"API_KEY": "${MY_SECRET}"}
        result = MCPClientProxy._resolve_env(env)
        assert result == {"API_KEY": "s3cret"}

    def test_resolve_missing_env_var_returns_empty(self, monkeypatch):
        """${VAR} for a missing env var resolves to empty string."""
        monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
        env = {"MISSING": "${NONEXISTENT_VAR_XYZ}"}
        result = MCPClientProxy._resolve_env(env)
        assert result == {"MISSING": ""}

    def test_mixed_literal_and_variable(self, monkeypatch):
        """Mix of literal values and ${VAR} references."""
        monkeypatch.setenv("DB_HOST", "localhost")
        env = {"HOST": "${DB_HOST}", "PORT": "5432"}
        result = MCPClientProxy._resolve_env(env)
        assert result == {"HOST": "localhost", "PORT": "5432"}

    def test_non_string_values_cast_to_string(self):
        """Non-string values are cast to str (defensive)."""
        # The env dict is typed as dict[str, str], but we test robustness
        env = {"NUM": 42, "BOOL": True}  # type: ignore[dict-item]
        result = MCPClientProxy._resolve_env(env)
        assert result == {"NUM": "42", "BOOL": "True"}

    def test_empty_env(self):
        """Empty dict returns empty dict."""
        assert MCPClientProxy._resolve_env({}) == {}

    def test_partial_dollar_braces_not_resolved(self):
        """Values like '$VAR' or '${VAR' are treated as literals."""
        env = {"A": "$VAR", "B": "${VAR", "C": "VAR}"}
        result = MCPClientProxy._resolve_env(env)
        assert result == {"A": "$VAR", "B": "${VAR", "C": "VAR}"}


# ---------------------------------------------------------------------------
# MCPClientProxy.close
# ---------------------------------------------------------------------------


class TestMCPClientProxyClose:
    """Tests for MCPClientProxy.close."""

    @pytest.mark.asyncio
    async def test_close_no_process(self):
        """close() is safe when no process has been started."""
        proxy = MCPClientProxy(command="echo", args=[], env={})
        await proxy.close()  # should not raise
        assert proxy._process is None

    @pytest.mark.asyncio
    async def test_close_terminates_running_process(self):
        """close() terminates a running process and sets _process to None."""
        proxy = MCPClientProxy(command="echo", args=[], env={})
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(return_value=0)
        proxy._process = mock_proc

        await proxy.close()

        mock_proc.terminate.assert_called_once()
        assert proxy._process is None

    @pytest.mark.asyncio
    async def test_close_kills_on_timeout(self):
        """close() kills the process if terminate does not finish in time."""
        proxy = MCPClientProxy(command="echo", args=[], env={})
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(side_effect=asyncio.TimeoutError)
        proxy._process = mock_proc

        await proxy.close()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert proxy._process is None

    @pytest.mark.asyncio
    async def test_close_already_exited_process(self):
        """close() is a no-op when process has already exited."""
        proxy = MCPClientProxy(command="echo", args=[], env={})
        mock_proc = MagicMock()
        mock_proc.returncode = 0  # already exited
        proxy._process = mock_proc

        await proxy.close()

        mock_proc.terminate.assert_not_called()


# ---------------------------------------------------------------------------
# SkillExecutor.execute_tool — routing and error cases
# ---------------------------------------------------------------------------


class TestSkillExecutorExecuteTool:
    """Tests for SkillExecutor.execute_tool dispatch and error handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, tmp_path):
        """Requesting a tool not in the skill returns an error dict."""
        skill = _make_skill(tmp_path, tools=[_make_python_tool()])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("nonexistent", {})

        assert result["error"] == "Unknown tool: nonexistent"
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_for_costly_tool(self, tmp_path):
        """A tool whose estimated cost exceeds remaining budget is rejected."""
        tool = _make_mcp_tool(name="expensive", cost_tier="high")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=0.10)

        result = await executor.execute_tool("expensive", {})

        assert result["error"] == "BUDGET_EXCEEDED"
        assert "0.20" in result["detail"]
        assert "0.10" in result["detail"]
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_free_tool_not_blocked_by_zero_budget(self, tmp_path):
        """Free tools are never blocked by budget checks."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool(cost_tier="free")
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=0.0)

        result = await executor.execute_tool("add", {"a": 1, "b": 2})

        assert result["result"] == 3
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_unknown_tool_type_returns_error(self, tmp_path):
        """A tool with an unrecognized type returns an error."""
        tool = SkillTool(
            name="weird",
            type="grpc",
            description="Unknown type tool",
        )
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("weird", {})

        assert result["error"] == "Unknown tool type: grpc"
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_routes_to_python_executor(self, tmp_path):
        """Python tool type routes to _execute_python."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool()
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("add", {"a": 5, "b": 3})

        assert result["result"] == 8

    @pytest.mark.asyncio
    async def test_routes_to_mcp_executor(self, tmp_path):
        """MCP tool type routes to _execute_mcp (mocked proxy)."""
        tool = _make_mcp_tool(name="search", cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "found it"}
            result = await executor.execute_tool("search", {"query": "test"})

        assert result["result"] == "found it"
        assert result["cost"] == _COST_TIER_ESTIMATES["low"]


# ---------------------------------------------------------------------------
# SkillExecutor._execute_python — real module execution
# ---------------------------------------------------------------------------


class TestSkillExecutorPython:
    """Tests for SkillExecutor._execute_python with real modules."""

    @pytest.mark.asyncio
    async def test_sync_function_execution(self, tmp_path):
        """A synchronous Python tool function executes and returns result."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool(function="add")
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("add", {"a": 10, "b": 20})

        assert result["result"] == 30
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_async_function_execution(self, tmp_path):
        """An async Python tool function is awaited and returns result."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool(name="async_add", function="async_add")
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("async_add", {"a": 7, "b": 3})

        assert result["result"] == 10
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_function_raises_returns_error(self, tmp_path):
        """A Python function that raises returns an error dict."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool(name="broken", function="broken")
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("broken", {})

        assert "test error" in result["error"]
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_missing_module_returns_error(self, tmp_path):
        """A tool with no module field returns an error."""
        tool = SkillTool(
            name="nomod",
            type="python",
            description="Missing module",
            module=None,
            function="add",
        )
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("nomod", {})

        assert result["error"] == "Python tool missing module/function"
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_missing_function_returns_error(self, tmp_path):
        """A tool with no function field returns an error."""
        tool = SkillTool(
            name="nofunc",
            type="python",
            description="Missing function",
            module="tools.math_tools",
            function=None,
        )
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("nofunc", {})

        assert result["error"] == "Python tool missing module/function"
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_nonexistent_module_returns_error(self, tmp_path):
        """Importing a module that does not exist returns an error."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool(module="tools.does_not_exist", function="nope")
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("add", {})

        assert "error" in result
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_skill_dir_added_to_sys_path(self, tmp_path):
        """The skill directory is added to sys.path during execution."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool()
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=10.0)

        await executor.execute_tool("add", {"a": 1, "b": 1})

        assert str(skill_dir) in sys.path


# ---------------------------------------------------------------------------
# SkillExecutor._execute_mcp
# ---------------------------------------------------------------------------


class TestSkillExecutorMCP:
    """Tests for SkillExecutor._execute_mcp with mocked proxy."""

    @pytest.mark.asyncio
    async def test_mcp_missing_server_command(self, tmp_path):
        """An MCP tool with no server_command returns error."""
        tool = SkillTool(
            name="noserver",
            type="mcp",
            description="No server",
            server_command=None,
        )
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        result = await executor.execute_tool("noserver", {})

        assert result["error"] == "MCP tool missing server command"
        assert result["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_mcp_creates_proxy_and_calls(self, tmp_path):
        """MCP execution creates a proxy and calls call_tool on it."""
        tool = _make_mcp_tool(name="search", cost_tier="medium")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "data"}
            result = await executor.execute_tool("search", {"q": "test"})

        assert result["result"] == "data"
        assert result["cost"] == _COST_TIER_ESTIMATES["medium"]
        # A proxy should have been stored
        assert len(executor._mcp_proxies) == 1

    @pytest.mark.asyncio
    async def test_mcp_reuses_proxy_for_same_server(self, tmp_path):
        """Multiple calls to the same MCP server reuse the proxy instance."""
        tool = _make_mcp_tool(name="search", cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "r1"}
            await executor.execute_tool("search", {"q": "a"})

            mock_call.return_value = {"result": "r2"}
            await executor.execute_tool("search", {"q": "b"})

        # Still only one proxy
        assert len(executor._mcp_proxies) == 1
        assert mock_call.call_count == 2

    @pytest.mark.asyncio
    async def test_mcp_uses_remote_tool_name(self, tmp_path):
        """When remote_tool_name is set, it is used instead of the local name."""
        tool = _make_mcp_tool(name="local_search", remote_tool_name="remote_search", cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            await executor.execute_tool("local_search", {"q": "test"})

        # call_tool should have been called with the remote name
        mock_call.assert_called_once_with("remote_search", {"q": "test"}, timeout=30)

    @pytest.mark.asyncio
    async def test_mcp_falls_back_to_tool_name(self, tmp_path):
        """When remote_tool_name is None, the local tool name is used."""
        tool = _make_mcp_tool(name="search", remote_tool_name=None, cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            await executor.execute_tool("search", {"q": "test"})

        mock_call.assert_called_once_with("search", {"q": "test"}, timeout=30)


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


class TestSkillExecutorBudget:
    """Tests for budget tracking across tool executions."""

    @pytest.mark.asyncio
    async def test_budget_decreases_after_execution(self, tmp_path):
        """Budget is reduced by the cost returned from tool execution."""
        tool = _make_mcp_tool(name="search", cost_tier="medium")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=1.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            await executor.execute_tool("search", {})

        expected_remaining = 1.0 - _COST_TIER_ESTIMATES["medium"]
        assert executor._budget_remaining == pytest.approx(expected_remaining)

    @pytest.mark.asyncio
    async def test_budget_tracks_across_multiple_calls(self, tmp_path):
        """Budget accumulates deductions across multiple tool calls."""
        tool = _make_mcp_tool(name="search", cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=0.05)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "r1"}
            r1 = await executor.execute_tool("search", {})

            # After first call: 0.05 - 0.01 = 0.04
            assert executor._budget_remaining == pytest.approx(0.04)

            mock_call.return_value = {"result": "r2"}
            r2 = await executor.execute_tool("search", {})

            # After second call: 0.04 - 0.01 = 0.03
            assert executor._budget_remaining == pytest.approx(0.03)

        assert "error" not in r1
        assert "error" not in r2

    @pytest.mark.asyncio
    async def test_budget_not_charged_on_error(self, tmp_path):
        """Budget exceeded errors do not deduct cost."""
        tool = _make_mcp_tool(name="costly", cost_tier="high")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=0.10)

        result = await executor.execute_tool("costly", {})

        assert result["error"] == "BUDGET_EXCEEDED"
        assert executor._budget_remaining == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_free_tool_does_not_reduce_budget(self, tmp_path):
        """Free Python tools don't deduct anything from budget."""
        skill_dir = _create_python_skill(tmp_path)
        tool = _make_python_tool(cost_tier="free")
        skill = SkillDefinition(
            name="test-skill",
            version="1.0.0",
            description="Test",
            path=skill_dir,
            tier="built-in",
            tools=[tool],
        )
        executor = SkillExecutor(skill, budget_remaining=5.0)

        await executor.execute_tool("add", {"a": 1, "b": 2})

        assert executor._budget_remaining == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_budget_eventually_blocks_repeated_calls(self, tmp_path):
        """Repeated tool calls eventually exhaust the budget."""
        tool = _make_mcp_tool(name="search", cost_tier="low")  # $0.01 each
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=0.025)

        results = []
        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            for _ in range(5):
                r = await executor.execute_tool("search", {})
                results.append(r)

        # First two should succeed ($0.01 each, 0.025 - 0.02 = 0.005)
        assert "error" not in results[0]
        assert "error" not in results[1]
        # Third call: budget is 0.005, cost is 0.01 -> BUDGET_EXCEEDED
        assert results[2]["error"] == "BUDGET_EXCEEDED"


# ---------------------------------------------------------------------------
# SkillExecutor.cleanup
# ---------------------------------------------------------------------------


class TestSkillExecutorCleanup:
    """Tests for SkillExecutor.cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_closes_all_proxies(self, tmp_path):
        """cleanup() calls close() on every MCP proxy and clears the dict."""
        tool = _make_mcp_tool(name="search", cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            await executor.execute_tool("search", {})

        assert len(executor._mcp_proxies) == 1

        with patch.object(MCPClientProxy, "close", new_callable=AsyncMock) as mock_close:
            await executor.cleanup()
            mock_close.assert_called_once()

        assert len(executor._mcp_proxies) == 0

    @pytest.mark.asyncio
    async def test_cleanup_with_no_proxies(self, tmp_path):
        """cleanup() is safe when no proxies exist."""
        skill = _make_skill(tmp_path, tools=[])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        await executor.cleanup()  # should not raise

        assert len(executor._mcp_proxies) == 0

    @pytest.mark.asyncio
    async def test_cleanup_multiple_proxies(self, tmp_path):
        """cleanup() closes multiple proxies from different servers."""
        tool_a = _make_mcp_tool(name="tool_a", server_command="node", server_args=["a.js"], cost_tier="low")
        tool_b = _make_mcp_tool(name="tool_b", server_command="python", server_args=["b.py"], cost_tier="low")
        skill = _make_skill(tmp_path, tools=[tool_a, tool_b])
        executor = SkillExecutor(skill, budget_remaining=10.0)

        with patch.object(MCPClientProxy, "call_tool", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            await executor.execute_tool("tool_a", {})
            await executor.execute_tool("tool_b", {})

        assert len(executor._mcp_proxies) == 2

        with patch.object(MCPClientProxy, "close", new_callable=AsyncMock) as mock_close:
            await executor.cleanup()
            assert mock_close.call_count == 2

        assert len(executor._mcp_proxies) == 0


# ---------------------------------------------------------------------------
# _COST_TIER_ESTIMATES sanity
# ---------------------------------------------------------------------------


class TestCostTierEstimates:
    """Sanity checks on the module-level cost tier mapping."""

    def test_expected_tiers_present(self):
        assert "free" in _COST_TIER_ESTIMATES
        assert "low" in _COST_TIER_ESTIMATES
        assert "medium" in _COST_TIER_ESTIMATES
        assert "high" in _COST_TIER_ESTIMATES

    def test_free_is_zero(self):
        assert _COST_TIER_ESTIMATES["free"] == 0.0

    def test_tiers_are_ordered(self):
        assert (
            _COST_TIER_ESTIMATES["free"]
            < _COST_TIER_ESTIMATES["low"]
            < _COST_TIER_ESTIMATES["medium"]
            < _COST_TIER_ESTIMATES["high"]
        )
