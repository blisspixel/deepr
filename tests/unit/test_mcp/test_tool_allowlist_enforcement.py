"""Cross-surface MCP allowlist enforcement contracts."""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
from types import SimpleNamespace
from typing import Any

import pytest

from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.security.scoped_keys import (
    ScopedMCPKeyContext,
    authorize_scoped_mcp_tool_call,
)
from deepr.mcp.security.tool_allowlist import (
    ResearchMode,
    ToolAllowlist,
    ToolConfig,
)
from deepr.mcp.server import _handle_tools_call, _register_new_tools


def _visible_tool_names() -> set[str]:
    registry = create_default_registry()
    _register_new_tools(registry)
    return {tool.name for tool in registry.all_tools()}


def _dispatch_tool_names() -> set[str]:
    source = textwrap.dedent(inspect.getsource(_handle_tools_call))
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "tool_dispatch":
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        return {key.value for key in node.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}

    raise AssertionError("could not find tool_dispatch mapping in _handle_tools_call")


def _all_mcp_tool_names() -> list[str]:
    return sorted(_visible_tool_names() | _dispatch_tool_names())


def _declared_decision(config: ToolConfig, mode: ResearchMode) -> tuple[bool, bool]:
    if mode in config.blocked_in:
        return False, False

    rule = ToolAllowlist.CATEGORY_RULES[mode][config.category]
    if rule == "block":
        return False, False

    if mode is ResearchMode.UNRESTRICTED:
        return True, False

    return True, mode in config.requires_confirmation_in or rule == "confirm"


def _tool_mode_cases() -> list[tuple[str, ResearchMode]]:
    return [(tool_name, mode) for tool_name in _all_mcp_tool_names() for mode in ResearchMode]


def _blocked_or_confirm_cases() -> list[tuple[str, ResearchMode]]:
    allowlist = ToolAllowlist()
    cases: list[tuple[str, ResearchMode]] = []
    for tool_name, mode in _tool_mode_cases():
        config = allowlist.get_tool_config(tool_name)
        assert config is not None
        allowed, requires_confirmation = _declared_decision(config, mode)
        if not allowed or requires_confirmation:
            cases.append((tool_name, mode))
    return cases


def _error_code(result: dict[str, Any]) -> str:
    payload = json.loads(result["content"][0]["text"])
    return str(payload["error_code"])


def test_visible_mcp_tools_are_dispatchable():
    assert sorted(_visible_tool_names() - _dispatch_tool_names()) == []


def test_every_mcp_tool_has_explicit_allowlist_config():
    allowlist = ToolAllowlist()

    missing = [tool_name for tool_name in _all_mcp_tool_names() if allowlist.get_tool_config(tool_name) is None]

    assert missing == []


@pytest.mark.parametrize(("tool_name", "mode"), _tool_mode_cases())
def test_tool_allowlist_decisions_match_declared_policy(tool_name: str, mode: ResearchMode):
    allowlist = ToolAllowlist(mode=mode)
    config = allowlist.get_tool_config(tool_name)
    assert config is not None

    expected_allowed, expected_confirmation = _declared_decision(config, mode)
    validation = allowlist.validate_tool_call(tool_name)

    assert validation["allowed"] is expected_allowed
    assert validation["requires_confirmation"] is expected_confirmation


@pytest.mark.parametrize(("tool_name", "mode"), _tool_mode_cases())
def test_scoped_key_authorizer_enforces_declared_allowlist(tool_name: str, mode: ResearchMode):
    allowlist = ToolAllowlist(mode=mode)
    config = allowlist.get_tool_config(tool_name)
    assert config is not None
    expected_allowed, expected_confirmation = _declared_decision(config, mode)

    context = ScopedMCPKeyContext("agent", mode)
    decision = authorize_scoped_mcp_tool_call(context, tool_name, {}, allowlist=allowlist)

    if not expected_allowed:
        assert not decision.allowed
        assert decision.error_code == "TOOL_BLOCKED_BY_KEY_MODE"
        return

    if expected_confirmation:
        assert not decision.allowed
        assert decision.error_code == "CONFIRMATION_REQUIRED"
        assert decision.requires_confirmation

        approved = authorize_scoped_mcp_tool_call(
            context,
            tool_name,
            {"_approved": True},
            allowlist=allowlist,
        )
        assert approved.allowed
        assert approved.requires_confirmation
        return

    assert decision.allowed
    assert not decision.requires_confirmation


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "mode"), _blocked_or_confirm_cases())
async def test_jsonrpc_handler_blocks_before_dispatch_for_declared_gates(
    tool_name: str,
    mode: ResearchMode,
):
    allowlist = ToolAllowlist(mode=mode)
    config = allowlist.get_tool_config(tool_name)
    assert config is not None
    expected_allowed, expected_confirmation = _declared_decision(config, mode)
    server = SimpleNamespace(tool_allowlist=allowlist)

    result = await _handle_tools_call(server, {"name": tool_name, "arguments": {}})

    assert result["isError"] is True
    if not expected_allowed:
        assert _error_code(result) == "TOOL_BLOCKED"
    else:
        assert expected_confirmation
        assert _error_code(result) == "CONFIRMATION_REQUIRED"
