"""Tests for the shared chat command registry (deepr.experts.commands)."""

from __future__ import annotations

from deepr.experts.commands import (
    MODE_CONFIGS,
    ChatCommand,
    ChatMode,
    CommandCategory,
    CommandRegistry,
    CommandResult,
    CommandScope,
)


class TestModeConfigs:
    def test_every_mode_has_a_config(self):
        for mode in ChatMode:
            assert mode in MODE_CONFIGS
            cfg = MODE_CONFIGS[mode]
            assert "tools" in cfg and "label" in cfg and "description" in cfg

    def test_focus_forces_tot(self):
        assert MODE_CONFIGS[ChatMode.FOCUS]["force_tot"] is True
        assert MODE_CONFIGS[ChatMode.ASK]["force_tot"] is False


class TestDataclasses:
    def test_chat_command_defaults(self):
        cmd = ChatCommand("foo")
        assert cmd.name == "foo"
        assert cmd.aliases == []
        assert cmd.category == CommandCategory.UTILITY
        assert cmd.scope == CommandScope.SESSION_REQUIRED
        assert cmd.hidden is False

    def test_command_result_defaults(self):
        res = CommandResult()
        assert res.success is True
        assert res.output == ""
        assert res.clear_chat is False
        assert res.mode_changed is None
        assert res.end_session is False


class TestRegistry:
    def test_get_instance_is_singleton_with_defaults(self):
        reg = CommandRegistry.get_instance()
        reg2 = CommandRegistry.get_instance()
        assert reg is reg2
        assert reg.get("ask") is not None
        assert reg.get("research") is not None

    def test_lookup_by_alias(self):
        reg = CommandRegistry.get_instance()
        # "?" is an alias of help; "exit"/"q" of quit; "pins" of memories
        assert reg.get("?") is reg.get("help")
        assert reg.get("q") is reg.get("quit")
        assert reg.get("pins") is reg.get("memories")

    def test_get_unknown_returns_none(self):
        assert CommandRegistry.get_instance().get("does-not-exist") is None

    def test_register_custom_command(self):
        reg = CommandRegistry()
        reg.register(ChatCommand("zonk", aliases=["zk"], description="test"))
        assert reg.get("zonk").name == "zonk"
        assert reg.get("zk").name == "zonk"


class TestParse:
    def test_parse_slash_prefix(self):
        reg = CommandRegistry.get_instance()
        cmd, args = reg.parse("/ask")
        assert cmd is not None and cmd.name == "ask"
        assert args == ""

    def test_parse_backslash_prefix_with_args(self):
        reg = CommandRegistry.get_instance()
        cmd, args = reg.parse("\\remember the sky is blue")
        assert cmd is not None and cmd.name == "remember"
        assert args == "the sky is blue"

    def test_parse_non_command_returns_none(self):
        reg = CommandRegistry.get_instance()
        assert reg.parse("just a normal message") == (None, "")

    def test_parse_empty_returns_none(self):
        reg = CommandRegistry.get_instance()
        assert reg.parse("   ") == (None, "")

    def test_parse_unknown_command_returns_none_cmd_but_args(self):
        reg = CommandRegistry.get_instance()
        cmd, args = reg.parse("/bogus some args")
        assert cmd is None
        assert args == "some args"

    def test_parse_is_case_insensitive(self):
        reg = CommandRegistry.get_instance()
        cmd, _ = reg.parse("/ASK")
        assert cmd is not None and cmd.name == "ask"


class TestListingAndCompletions:
    def test_list_commands_excludes_hidden_by_default(self):
        reg = CommandRegistry()
        reg.register(ChatCommand("visible"))
        reg.register(ChatCommand("secret", hidden=True))
        names = {c.name for c in reg.list_commands()}
        assert "visible" in names and "secret" not in names
        names_all = {c.name for c in reg.list_commands(include_hidden=True)}
        assert "secret" in names_all

    def test_completions_match_name_prefix(self):
        reg = CommandRegistry.get_instance()
        results = reg.get_completions("re")
        names = {c.name for c in results}
        assert "research" in names and "remember" in names

    def test_completions_strip_prefix_chars(self):
        reg = CommandRegistry.get_instance()
        assert {c.name for c in reg.get_completions("/re")} == {c.name for c in reg.get_completions("re")}

    def test_completions_match_alias(self):
        reg = CommandRegistry()
        reg.register(ChatCommand("memories", aliases=["pins"]))
        results = reg.get_completions("pin")
        assert any(c.name == "memories" for c in results)

    def test_commands_by_category_groups(self):
        reg = CommandRegistry.get_instance()
        groups = reg.commands_by_category()
        assert CommandCategory.MODE in groups
        assert any(c.name == "ask" for c in groups[CommandCategory.MODE])
