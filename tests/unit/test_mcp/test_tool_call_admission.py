"""Confirmation follows lookup and argument checks (#349)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist
from deepr.mcp.server import _handle_tools_call
from deepr.mcp.tool_call_admission import known_tool_names
from tests.unit.test_mcp.test_tool_allowlist_enforcement import _dispatch_tool_names

_INVALID_RESEARCH = {
    "prompt": "",
    "budget": -1,
    "allow_metered_api": True,
    "confirm_metered_cost": True,
}


def _server() -> SimpleNamespace:
    research = AsyncMock()
    return SimpleNamespace(
        tool_allowlist=ToolAllowlist(mode=ResearchMode.STANDARD),
        deepr_research=research,
    )


def _error_code(result: dict) -> str:
    return str(json.loads(result["content"][0]["text"])["error_code"])


def test_known_tool_names_match_the_stdio_dispatcher() -> None:
    assert known_tool_names() == _dispatch_tool_names()


@pytest.mark.asyncio
async def test_playtest_unknown_tool_is_not_found_before_confirmation() -> None:
    server = _server()
    result = await _handle_tools_call(server, {"name": "deepr_nonexistent_tool", "arguments": {}})

    assert result["isError"] is True
    assert _error_code(result) == "TOOL_NOT_FOUND"
    assert "deepr_nonexistent_tool" in result["content"][0]["text"]
    server.deepr_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_playtest_invalid_budget_precedes_confirmation() -> None:
    server = _server()
    result = await _handle_tools_call(server, {"name": "deepr_research", "arguments": dict(_INVALID_RESEARCH)})

    assert result["isError"] is True
    data = json.loads(result["content"][0]["text"])
    assert data["error_code"] == "INVALID_BUDGET"
    assert "finite positive budget" in data["message"]
    server.deepr_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_invalid_budget_stays_a_validation_error() -> None:
    server = _server()
    arguments = dict(_INVALID_RESEARCH)
    arguments["_approved"] = True
    result = await _handle_tools_call(server, {"name": "deepr_research", "arguments": arguments})

    assert _error_code(result) == "INVALID_BUDGET"
    server.deepr_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_research_contract_still_requires_confirmation() -> None:
    server = _server()
    result = await _handle_tools_call(
        server,
        {
            "name": "deepr_research",
            "arguments": {
                "prompt": "a bounded question",
                "budget": 1.0,
                "allow_metered_api": True,
                "confirm_metered_cost": True,
            },
        },
    )

    assert _error_code(result) == "CONFIRMATION_REQUIRED"
    server.deepr_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_only_unknown_name_is_not_found_and_known_tool_stays_blocked() -> None:
    server = SimpleNamespace(tool_allowlist=ToolAllowlist(mode=ResearchMode.READ_ONLY))

    unknown = await _handle_tools_call(server, {"name": "deepr_nonexistent_tool", "arguments": {}})
    blocked = await _handle_tools_call(server, {"name": "deepr_research", "arguments": dict(_INVALID_RESEARCH)})

    assert _error_code(unknown) == "TOOL_NOT_FOUND"
    assert _error_code(blocked) == "TOOL_BLOCKED"
