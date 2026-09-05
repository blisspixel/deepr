"""Shared command help must distinguish configuration from executable capacity."""

from types import SimpleNamespace

import pytest

from deepr.experts.command_handlers import dispatch_command
from deepr.experts.commands import MODE_CONFIGS, ChatMode


@pytest.mark.parametrize("prefix", ["/", "\\"])
@pytest.mark.parametrize("mode", list(ChatMode))
async def test_tool_inventory_preserves_mode_selection_without_advertising_dispatch(prefix, mode):
    session = SimpleNamespace(chat_mode=mode, active_skills=[], budget=0, cost_accumulated=0)
    before = vars(session).copy()
    result = await dispatch_command(session, f"{prefix}tools")

    assert result is not None and result.success
    assert "inventory" in result.output.lower()
    assert "Metered calls and skill execution are blocked" in result.output
    assert "free" not in result.output.lower() and "$0.10" not in result.output
    for tool in {name for config in MODE_CONFIGS.values() for name in config["tools"]}:
        assert (tool in result.output) == (tool in MODE_CONFIGS[mode]["tools"])
    assert vars(session) == before


async def test_stored_skills_remain_visible_as_blocked_inventory():
    session = SimpleNamespace(
        chat_mode=ChatMode.ASK,
        active_skills=[SimpleNamespace(name="stored-skill", tools=[SimpleNamespace(name="inspect")])],
    )
    result = await dispatch_command(session, "/tools")

    assert result is not None and result.success
    assert "stored-skill/inspect" in result.output
    assert "Skill inventory (execution blocked)" in result.output


@pytest.mark.parametrize("command", ["/mode", "/research", "/focus"])
async def test_mode_help_and_switches_do_not_grant_tool_access(command):
    session = SimpleNamespace(chat_mode=ChatMode.ASK)
    result = await dispatch_command(session, command)

    assert result is not None and result.success
    assert "full tool access" not in result.output.lower()
    assert "always on" not in result.output.lower()
    if command != "/mode":
        assert session.chat_mode == ChatMode(command[1:])
        assert result.mode_changed == session.chat_mode


@pytest.mark.parametrize("command", ["/help tools", "/help"])
async def test_command_help_describes_tools_as_inventory(command):
    result = await dispatch_command(None, command)

    assert result is not None and result.success
    assert "tool inventory" in result.output.lower()
    assert "list available tools" not in result.output.lower()


async def test_model_help_matches_read_only_model_handler():
    session = SimpleNamespace(expert=SimpleNamespace(model="current-model"))
    help_result = await dispatch_command(session, "/help model")
    response = await dispatch_command(session, "/model another-model")

    assert help_result is not None and response is not None
    assert "change model" not in help_result.output.lower()
    assert "[name]" not in help_result.output
    assert "current-model" in response.output
    assert session.expert.model == "current-model"
