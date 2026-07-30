"""Cost-safety regressions for the supported ``expert run-skill`` surface."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.skills.definition import SkillDefinition, SkillTool


def _skill(tmp_path: Path, tool_type: str) -> SkillDefinition:
    return SkillDefinition(
        name="community-skill",
        version="1.0.0",
        description="untrusted executable skill",
        path=tmp_path,
        tier="community",
        tools=[
            SkillTool(
                name="research",
                description="could call an external provider",
                type=tool_type,
                cost_tier="high",
                module="tools",
                function="research",
                server_command="python",
                server_args=["server.py"],
            )
        ],
    )


@pytest.mark.parametrize("tool_type", ["python", "mcp"])
def test_run_skill_never_dispatches_or_mutates_profile(tmp_path: Path, tool_type: str) -> None:
    profile = SimpleNamespace(installed_skills=[])
    store = MagicMock()
    store.load.return_value = profile
    manager = MagicMock()
    manager.get_skill.return_value = _skill(tmp_path, tool_type)
    executor = MagicMock(side_effect=AssertionError("run-skill must not construct an executor"))
    spawn = AsyncMock(side_effect=AssertionError("run-skill must not spawn a subprocess"))

    with (
        patch("deepr.experts.profile_store.ExpertStore", return_value=store),
        patch("deepr.experts.skills.SkillManager", return_value=manager),
        patch("deepr.experts.skills.SkillExecutor", executor),
        patch("asyncio.create_subprocess_exec", spawn),
        patch.object(
            importlib.util,
            "spec_from_file_location",
            side_effect=AssertionError("run-skill must not load Python skill code"),
        ) as load_code,
    ):
        result = CliRunner().invoke(
            cli,
            [
                "expert",
                "run-skill",
                "Cost-Safe Expert",
                "community-skill",
                "research",
                "--args",
                '{"query":"test","budget":999999}',
            ],
        )

    assert result.exit_code == 1, result.output
    assert "Skill tool execution is disabled" in result.output
    assert "cannot be enforced" in result.output
    executor.assert_not_called()
    spawn.assert_not_awaited()
    load_code.assert_not_called()
    store.save.assert_not_called()
    assert profile.installed_skills == []


def test_run_skill_keeps_read_only_validation_for_unknown_tool(tmp_path: Path) -> None:
    store = MagicMock()
    store.load.return_value = SimpleNamespace(installed_skills=[])
    manager = MagicMock()
    manager.get_skill.return_value = _skill(tmp_path, "python")

    with (
        patch("deepr.experts.profile_store.ExpertStore", return_value=store),
        patch("deepr.experts.skills.SkillManager", return_value=manager),
    ):
        result = CliRunner().invoke(
            cli,
            ["expert", "run-skill", "Cost-Safe Expert", "community-skill", "missing"],
        )

    assert result.exit_code == 0, result.output
    assert "Tool not found in community-skill: missing" in result.output
    store.save.assert_not_called()
