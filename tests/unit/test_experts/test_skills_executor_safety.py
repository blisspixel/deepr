"""Regression tests for the skill executor's RCE and spend quarantine.

Pins down the round-3 hardening:
- All Python code loading is refused before module/function inspection.
- ``prompt_file`` traversal is refused.
- Failed tools do not charge cost or mutate the budget.
- Concurrent calls remain side-effect free.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from deepr.experts.skills.definition import SkillDefinition, SkillTool
from deepr.experts.skills.executor import SKILL_TOOL_EXECUTION_DISABLED, SkillExecutor


def _make_skill(tmp_path: Path, tool: SkillTool, name: str = "test-skill") -> SkillDefinition:
    return SkillDefinition(
        name=name,
        version="1.0",
        description="test",
        path=tmp_path,
        tier="built-in",
        domains=[],
        author="",
        license="",
        triggers=None,
        tools=[tool],
        prompt_file="prompt.md",
        output_templates={},
        budget=None,
    )


class TestPythonModuleSandbox:
    @pytest.mark.asyncio
    async def test_stdlib_module_refused(self, tmp_path):
        """``module: os, function: system`` must NOT execute - the previous
        executor imported it via ``importlib.import_module`` from the
        global module space and would have spawned a shell."""
        tool = SkillTool(
            name="rce-attempt", description="", type="python", module="os", function="system", cost_tier="free"
        )
        skill = _make_skill(tmp_path, tool)
        executor = SkillExecutor(skill, budget_remaining=1.0)
        result = await executor.execute_tool("rce-attempt", {"command": "echo pwned"})
        assert "error" in result
        assert result["error"] == SKILL_TOOL_EXECUTION_DISABLED

    @pytest.mark.asyncio
    async def test_dunder_function_refused(self, tmp_path):
        """``function: __import__`` blocked even if the module is inside
        the skill - function name allowlist rejects dunders."""
        (tmp_path / "mymod.py").write_text("def __secret__():\n    return 1\n")
        tool = SkillTool(
            name="dunder", description="", type="python", module="mymod", function="__secret__", cost_tier="free"
        )
        skill = _make_skill(tmp_path, tool)
        executor = SkillExecutor(skill, budget_remaining=1.0)
        result = await executor.execute_tool("dunder", {})
        assert "error" in result
        assert result["error"] == SKILL_TOOL_EXECUTION_DISABLED

    @pytest.mark.asyncio
    async def test_legitimate_module_is_still_quarantined(self, tmp_path):
        """A local-looking module is not proof that its runtime behavior is free."""
        (tmp_path / "tools.py").write_text("def add(a, b):\n    return a + b\n")
        tool = SkillTool(name="add", description="", type="python", module="tools", function="add", cost_tier="free")
        skill = _make_skill(tmp_path, tool)
        executor = SkillExecutor(skill, budget_remaining=1.0)
        result = await executor.execute_tool("add", {"a": 2, "b": 3})
        assert result["error"] == SKILL_TOOL_EXECUTION_DISABLED

    @pytest.mark.asyncio
    async def test_module_path_traversal_refused(self, tmp_path):
        """``module: ../etc/passwd`` must be rejected as a path-escape."""
        tool = SkillTool(
            name="escape", description="", type="python", module="../foo", function="bar", cost_tier="free"
        )
        skill = _make_skill(tmp_path, tool)
        executor = SkillExecutor(skill, budget_remaining=1.0)
        result = await executor.execute_tool("escape", {})
        assert "error" in result


class TestPromptFileTraversal:
    def test_traversal_refused(self, tmp_path):
        """``prompt_file: ../../../etc/passwd`` returns empty prompt, not
        the host file."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        outside = tmp_path / "secret.md"
        outside.write_text("SECRET CONTENT")
        skill = SkillDefinition(
            name="t",
            version="1.0",
            description="",
            path=skill_dir,
            tier="built-in",
            domains=[],
            author="",
            license="",
            triggers=None,
            tools=[],
            prompt_file="../secret.md",
            output_templates={},
            budget=None,
        )
        assert skill.load_prompt() == ""

    def test_absolute_path_refused(self, tmp_path):
        skill = SkillDefinition(
            name="t",
            version="1.0",
            description="",
            path=tmp_path,
            tier="built-in",
            domains=[],
            author="",
            license="",
            triggers=None,
            tools=[],
            prompt_file=str(tmp_path / "anything.md"),  # absolute
            output_templates={},
            budget=None,
        )
        assert skill.load_prompt() == ""


class TestFailedToolNotCharged:
    @pytest.mark.asyncio
    async def test_failed_python_tool_zero_cost(self, tmp_path):
        # Module doesn't exist; tool returns error; budget must remain.
        tool = SkillTool(
            name="missing", description="", type="python", module="nope", function="run", cost_tier="medium"
        )
        skill = _make_skill(tmp_path, tool)
        executor = SkillExecutor(skill, budget_remaining=1.0)
        result = await executor.execute_tool("missing", {})
        assert "error" in result
        assert result.get("cost", 0.0) == 0.0
        # And the executor's budget hasn't been deducted.
        assert executor._budget_remaining == pytest.approx(1.0)


class TestConcurrentBudgetSerialisation:
    @pytest.mark.asyncio
    async def test_parallel_calls_do_not_overdraw(self, tmp_path):
        """Two parallel calls against a $0.06 budget for $0.05 tools each
        cannot both succeed - the second is rejected by the lock-serialised
        budget check."""
        (tmp_path / "tools.py").write_text("def slow():\n    return 'ok'\n")
        tool = SkillTool(
            name="slow", description="", type="python", module="tools", function="slow", cost_tier="medium"
        )
        skill = _make_skill(tmp_path, tool)
        executor = SkillExecutor(skill, budget_remaining=0.06)

        results = await asyncio.gather(executor.execute_tool("slow", {}), executor.execute_tool("slow", {}))
        assert all(r["error"] == SKILL_TOOL_EXECUTION_DISABLED for r in results)
        assert executor._budget_remaining == pytest.approx(0.06)
