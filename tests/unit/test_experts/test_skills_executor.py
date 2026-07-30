"""Fail-closed regressions for expert skill tool execution."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from deepr.experts.skills.definition import SkillDefinition, SkillTool
from deepr.experts.skills.executor import SKILL_TOOL_EXECUTION_DISABLED, SkillExecutor


def _tool(*, name: str = "run", tool_type: str = "python", cost_tier: str = "free") -> SkillTool:
    return SkillTool(
        name=name,
        description="test tool",
        type=tool_type,
        cost_tier=cost_tier,
        module="tools",
        function="run",
        server_command="python",
        server_args=["server.py"],
    )


def _skill(tmp_path: Path, tool: SkillTool) -> SkillDefinition:
    return SkillDefinition(
        name="test-skill",
        version="1.0.0",
        description="test",
        path=tmp_path,
        tier="built-in",
        tools=[tool],
    )


def _assert_quarantined(result: dict[str, Any], *, tool_type: str) -> None:
    assert result == {
        "error": SKILL_TOOL_EXECUTION_DISABLED,
        "status": "blocked",
        "detail": (
            "Skill tool execution is quarantined because arbitrary Python and MCP tools "
            "can incur external spend that manifest estimates and self-reported costs "
            "cannot enforce. Skill inventory and inspection remain available."
        ),
        "tool_type": tool_type,
        "cost": 0.0,
    }


@pytest.mark.parametrize("tool_type", ["python", "mcp", "shell", "future-provider"])
@pytest.mark.parametrize("cost_tier", ["free", "low", "medium", "high", "unknown"])
@pytest.mark.parametrize("allow_metered_tools", [False, True])
@pytest.mark.asyncio
async def test_every_inventoried_tool_is_quarantined(
    tmp_path: Path,
    tool_type: str,
    cost_tier: str,
    allow_metered_tools: bool,
) -> None:
    tool = _tool(tool_type=tool_type, cost_tier=cost_tier)
    executor = SkillExecutor(
        _skill(tmp_path, tool),
        budget_remaining=10.0,
        allow_metered_tools=allow_metered_tools,
    )

    result = await executor.execute_tool(tool.name, {"budget": 999_999.0})

    _assert_quarantined(result, tool_type=tool_type)
    assert executor._budget_remaining == 10.0


@pytest.mark.asyncio
async def test_python_tool_is_blocked_before_code_load(tmp_path: Path) -> None:
    tool = _tool(tool_type="python", cost_tier="high")
    executor = SkillExecutor(_skill(tmp_path, tool), 10.0, allow_metered_tools=True)

    with patch.object(
        importlib.util,
        "spec_from_file_location",
        side_effect=AssertionError("quarantined Python skill must not load code"),
    ) as load_code:
        result = await executor.execute_tool(tool.name, {})

    _assert_quarantined(result, tool_type="python")
    load_code.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_tool_is_blocked_before_subprocess_spawn(tmp_path: Path) -> None:
    tool = _tool(tool_type="mcp", cost_tier="high")
    executor = SkillExecutor(_skill(tmp_path, tool), 10.0, allow_metered_tools=True)
    spawn = AsyncMock(side_effect=AssertionError("quarantined MCP skill must not spawn"))

    with patch("asyncio.create_subprocess_exec", spawn):
        result = await executor.execute_tool(tool.name, {})

    _assert_quarantined(result, tool_type="mcp")
    spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tool_remains_an_inventory_error(tmp_path: Path) -> None:
    executor = SkillExecutor(_skill(tmp_path, _tool()), 10.0)

    result = await executor.execute_tool("missing", {})

    assert result == {"error": "Unknown tool: missing", "cost": 0.0}


@pytest.mark.asyncio
async def test_arguments_are_not_read_or_mutated(tmp_path: Path) -> None:
    executor = SkillExecutor(_skill(tmp_path, _tool()), 10.0)
    arguments = {"nested": {"secret": "unchanged"}}

    await executor.execute_tool("run", arguments)

    assert arguments == {"nested": {"secret": "unchanged"}}


@pytest.mark.asyncio
async def test_parallel_calls_cannot_dispatch_or_change_budget(tmp_path: Path) -> None:
    tool = _tool(tool_type="mcp", cost_tier="high")
    executor = SkillExecutor(_skill(tmp_path, tool), 0.01, allow_metered_tools=True)
    spawn = AsyncMock(side_effect=AssertionError("quarantined MCP skill must not spawn"))

    with patch("asyncio.create_subprocess_exec", spawn):
        results = await asyncio.gather(*(executor.execute_tool(tool.name, {}) for _ in range(20)))

    assert all(result["error"] == SKILL_TOOL_EXECUTION_DISABLED for result in results)
    assert executor._budget_remaining == 0.01
    spawn.assert_not_awaited()


@pytest.mark.parametrize("budget", [True, False, -1, float("nan"), float("inf"), "10", None])
def test_invalid_budget_is_rejected(tmp_path: Path, budget: Any) -> None:
    with pytest.raises(ValueError, match="finite non-negative"):
        SkillExecutor(_skill(tmp_path, _tool()), budget)


@pytest.mark.parametrize("budget", [0, 0.0, 10, 10.5])
def test_valid_budget_is_retained_for_contract_compatibility(tmp_path: Path, budget: float) -> None:
    executor = SkillExecutor(_skill(tmp_path, _tool()), budget)

    assert executor._budget_remaining == float(budget)


@pytest.mark.asyncio
async def test_cleanup_is_a_resource_free_noop(tmp_path: Path) -> None:
    executor = SkillExecutor(_skill(tmp_path, _tool()), 10.0)

    assert await executor.cleanup() is None


def test_skills_package_does_not_export_proxy_transport() -> None:
    import deepr.experts.skills as skills_package
    import deepr.experts.skills.executor as executor_module

    assert not hasattr(skills_package, "MCPClientProxy")
    assert "MCPClientProxy" not in skills_package.__all__
    assert not hasattr(executor_module, "MCPClientProxy")
    assert not hasattr(executor_module, "_MCPClientProxy")
