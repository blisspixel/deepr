"""Final coverage push: skill helpers + run_stdio_server entry registration.

The skill helpers (``_list_skills``, ``_install_skill``,
``_validate_expert_name_component``) accept expert-name input straight from MCP
clients, so the path-traversal validator and error branches really need
coverage. ``run_stdio_server`` registers every protocol method on the
``StdioServer``; a smoke test confirms the wiring without binding stdin.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.server import (
    _install_skill,
    _list_skills,
    _validate_expert_name_component,
    run_stdio_server,
)


class TestValidateExpertNameComponent:
    def test_empty_name_returns_none(self):
        # Empty is allowed (caller treats it as "no expert filter").
        assert _validate_expert_name_component("") is None

    def test_slash_rejected(self):
        assert "illegal path" in _validate_expert_name_component("foo/bar")

    def test_backslash_rejected(self):
        assert "illegal path" in _validate_expert_name_component("foo\\bar")

    def test_dotdot_rejected(self):
        assert "illegal path" in _validate_expert_name_component("../etc/passwd")

    def test_absolute_path_rejected(self):
        # /abs/path has a "/" so the illegal-character branch fires before
        # the absolute-path check (which would otherwise fire on POSIX hosts).
        out = _validate_expert_name_component("/abs/path")
        assert out is not None

    def test_absolute_windows_rejected(self):
        # On Windows, ``C:\foo`` has anchor; on POSIX it does not. Either way,
        # the ``\`` triggers the illegal-character branch.
        out = _validate_expert_name_component("C:\\foo")
        assert out is not None

    def test_safe_name_allowed(self):
        assert _validate_expert_name_component("my_expert_v1") is None


class TestListSkills:
    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self):
        out = await _list_skills("../etc/passwd")
        assert "illegal path" in out["error"]

    @pytest.mark.asyncio
    async def test_returns_skill_listing_for_known_expert(self):
        skill = MagicMock(
            name="x",
            description="d",
            version="1",
            tools=[MagicMock(name="t1")],
            tier="builtin",
            domains=["test"],
        )
        skill.name = "x"  # MagicMock(name=...) sets the mock name not the attr
        skill.tools[0].name = "t1"

        with (
            patch("deepr.experts.skills.SkillManager") as SM,
            patch("deepr.mcp.server.ExpertStore") as ES,
        ):
            SM.return_value.list_all.return_value = [skill]
            store = MagicMock()
            profile = MagicMock()
            profile.installed_skills = ["x"]
            store.load.return_value = profile
            ES.return_value = store
            out = await _list_skills("alice")
        assert out["expert_name"] == "alice"
        assert out["skills"][0]["name"] == "x"
        assert out["skills"][0]["installed"] is True

    @pytest.mark.asyncio
    async def test_no_expert_name_omits_install_status(self):
        skill = MagicMock(description="d", version="1", tools=[], tier="builtin", domains=[])
        skill.name = "global_skill"
        with patch("deepr.experts.skills.SkillManager") as SM:
            SM.return_value.list_all.return_value = [skill]
            out = await _list_skills("")
        assert out["expert_name"] is None
        assert out["skills"][0]["installed"] is False

    @pytest.mark.asyncio
    async def test_internal_error_wrapped(self):
        with patch("deepr.experts.skills.SkillManager", side_effect=RuntimeError("boom")):
            out = await _list_skills("alice")
        assert "boom" in out["error"]


class TestInstallSkill:
    @pytest.mark.asyncio
    async def test_missing_args(self):
        out = await _install_skill("", "x")
        assert "required" in out["error"]
        out2 = await _install_skill("alice", "")
        assert "required" in out2["error"]

    @pytest.mark.asyncio
    async def test_traversal_blocked(self):
        out = await _install_skill("../etc", "x")
        assert "illegal path" in out["error"]

    @pytest.mark.asyncio
    async def test_unknown_expert(self):
        with patch("deepr.mcp.server.ExpertStore") as ES:
            store = MagicMock()
            store.load.return_value = None
            ES.return_value = store
            out = await _install_skill("alice", "skill_x")
        assert "Expert not found" in out["error"]

    @pytest.mark.asyncio
    async def test_unknown_skill(self):
        with (
            patch("deepr.mcp.server.ExpertStore") as ES,
            patch("deepr.experts.skills.SkillManager") as SM,
        ):
            store = MagicMock()
            profile = MagicMock(installed_skills=[])
            store.load.return_value = profile
            ES.return_value = store
            manager = MagicMock()
            manager.get_skill.return_value = None
            SM.return_value = manager
            out = await _install_skill("alice", "ghost")
        assert "Skill not found" in out["error"]

    @pytest.mark.asyncio
    async def test_already_installed_is_idempotent(self):
        with (
            patch("deepr.mcp.server.ExpertStore") as ES,
            patch("deepr.experts.skills.SkillManager") as SM,
        ):
            store = MagicMock()
            profile = MagicMock(installed_skills=["skill_x"])
            store.load.return_value = profile
            ES.return_value = store
            manager = MagicMock()
            manager.get_skill.return_value = MagicMock()
            SM.return_value = manager
            out = await _install_skill("alice", "skill_x")
        assert out["status"] == "already_installed"

    @pytest.mark.asyncio
    async def test_happy_install(self):
        with (
            patch("deepr.mcp.server.ExpertStore") as ES,
            patch("deepr.experts.skills.SkillManager") as SM,
        ):
            store = MagicMock()
            profile = MagicMock(installed_skills=["other"])
            store.load.return_value = profile
            ES.return_value = store
            manager = MagicMock()
            manager.get_skill.return_value = MagicMock()
            SM.return_value = manager
            out = await _install_skill("alice", "skill_x")
        assert out["status"] == "installed"


class TestRunStdioServer:
    @pytest.mark.asyncio
    async def test_registers_all_methods(self):
        """run_stdio_server wires every JSON-RPC method on the StdioServer.

        We patch ``StdioServer`` so the call doesn't block on stdin, then
        assert the expected method names land on its register_method call list.
        """
        recorded = []

        fake_stdio = MagicMock()
        fake_stdio.register_method = lambda name, _h: recorded.append(name)
        fake_stdio.run = AsyncMock()

        with (
            patch("deepr.mcp.server.StdioServer", return_value=fake_stdio),
            patch("deepr.mcp.server.DeeprMCPServer"),
        ):
            await run_stdio_server()

        # Standard MCP protocol methods.
        for method in (
            "initialize",
            "tools/list",
            "tools/call",
            "resources/list",
            "resources/read",
            "resources/subscribe",
            "resources/unsubscribe",
            "prompts/list",
            "prompts/get",
        ):
            assert method in recorded
        # Legacy aliases registered too.
        for legacy in ("list_experts", "get_expert_info", "query_expert", "expert_manifest", "rank_gaps"):
            assert legacy in recorded
