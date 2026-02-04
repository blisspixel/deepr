"""Unit tests for tool allowlist."""

import pytest

from deepr.mcp.security.tool_allowlist import (
    ToolAllowlist,
    ResearchMode,
    ToolCategory,
    ToolConfig,
    is_tool_allowed,
    get_allowed_tools,
)


class TestResearchModes:
    """Tests for research mode behavior."""

    def test_read_only_mode_blocks_write_tools(self):
        """Test that read_only mode blocks write operations."""
        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)

        assert allowlist.is_allowed("web_search") is True
        assert allowlist.is_allowed("file_read") is True
        assert allowlist.is_allowed("file_write") is False
        assert allowlist.is_allowed("code_execute") is False

    def test_standard_mode_allows_with_confirmation(self):
        """Test that standard mode allows write tools with confirmation."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        assert allowlist.is_allowed("web_search") is True
        assert allowlist.is_allowed("file_write") is True
        assert allowlist.require_confirmation("file_write") is True

    def test_extended_mode_allows_more(self):
        """Test that extended mode allows more tools."""
        allowlist = ToolAllowlist(mode=ResearchMode.EXTENDED)

        assert allowlist.is_allowed("web_search") is True
        assert allowlist.is_allowed("file_write") is True
        assert allowlist.is_allowed("shell_command") is True
        assert allowlist.require_confirmation("shell_command") is True

    def test_unrestricted_mode_allows_all(self):
        """Test that unrestricted mode allows all tools."""
        allowlist = ToolAllowlist(mode=ResearchMode.UNRESTRICTED)

        assert allowlist.is_allowed("web_search") is True
        assert allowlist.is_allowed("file_write") is True
        assert allowlist.is_allowed("shell_command") is True
        assert allowlist.require_confirmation("file_write") is False
        assert allowlist.require_confirmation("shell_command") is False


class TestToolAllowlist:
    """Tests for ToolAllowlist class."""

    def test_is_allowed_default_tools(self):
        """Test is_allowed with default tools."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        # Read tools should be allowed
        assert allowlist.is_allowed("web_search") is True
        assert allowlist.is_allowed("web_fetch") is True
        assert allowlist.is_allowed("arxiv_search") is True

        # Compute tools should be allowed
        assert allowlist.is_allowed("summarize") is True
        assert allowlist.is_allowed("analyze") is True

    def test_is_allowed_unknown_tool(self):
        """Test is_allowed with unknown tool."""
        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)

        # Unknown tools blocked in read_only
        assert allowlist.is_allowed("unknown_tool") is False

        allowlist_standard = ToolAllowlist(mode=ResearchMode.STANDARD)
        # Unknown tools allowed in standard
        assert allowlist_standard.is_allowed("unknown_tool") is True

    def test_require_confirmation_default_tools(self):
        """Test require_confirmation with default tools."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        # Read tools don't need confirmation
        assert allowlist.require_confirmation("web_search") is False
        assert allowlist.require_confirmation("file_read") is False

        # Write tools need confirmation
        assert allowlist.require_confirmation("file_write") is True
        assert allowlist.require_confirmation("api_call") is True

    def test_require_confirmation_unknown_tool(self):
        """Test require_confirmation with unknown tool."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        # Unknown tools require confirmation (safety)
        assert allowlist.require_confirmation("unknown_tool") is True

    def test_validate_tool_call(self):
        """Test validate_tool_call method."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        # Allowed tool
        result = allowlist.validate_tool_call("web_search")
        assert result["allowed"] is True
        assert result["requires_confirmation"] is False
        assert result["mode"] == "standard"
        assert result["tool_name"] == "web_search"

        # Blocked tool
        allowlist_ro = ToolAllowlist(mode=ResearchMode.READ_ONLY)
        result = allowlist_ro.validate_tool_call("file_write")
        assert result["allowed"] is False
        assert "blocked" in result["reason"].lower()

    def test_get_tool_config(self):
        """Test get_tool_config method."""
        allowlist = ToolAllowlist()

        config = allowlist.get_tool_config("web_search")

        assert config is not None
        assert config.name == "web_search"
        assert config.category == ToolCategory.READ

    def test_get_tool_config_not_found(self):
        """Test get_tool_config with unknown tool."""
        allowlist = ToolAllowlist()

        config = allowlist.get_tool_config("nonexistent")

        assert config is None


class TestToolRegistration:
    """Tests for tool registration."""

    def test_register_tool(self):
        """Test registering a new tool."""
        allowlist = ToolAllowlist()

        config = allowlist.register_tool(
            name="custom_tool",
            category=ToolCategory.COMPUTE,
            description="A custom tool",
        )

        assert config.name == "custom_tool"
        assert allowlist.get_tool_config("custom_tool") is not None
        assert allowlist.is_allowed("custom_tool") is True

    def test_register_tool_with_restrictions(self):
        """Test registering a tool with restrictions."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        allowlist.register_tool(
            name="dangerous_tool",
            category=ToolCategory.EXECUTE,
            requires_confirmation_in={ResearchMode.STANDARD, ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY},
        )

        assert allowlist.is_allowed("dangerous_tool") is True
        assert allowlist.require_confirmation("dangerous_tool") is True

        allowlist_ro = ToolAllowlist(mode=ResearchMode.READ_ONLY)
        allowlist_ro.register_tool(
            name="dangerous_tool",
            category=ToolCategory.EXECUTE,
            blocked_in={ResearchMode.READ_ONLY},
        )
        assert allowlist_ro.is_allowed("dangerous_tool") is False

    def test_unregister_tool(self):
        """Test unregistering a tool."""
        allowlist = ToolAllowlist()

        # Register then unregister
        allowlist.register_tool("temp_tool", ToolCategory.COMPUTE)
        assert allowlist.get_tool_config("temp_tool") is not None

        result = allowlist.unregister_tool("temp_tool")
        assert result is True
        assert allowlist.get_tool_config("temp_tool") is None

    def test_unregister_nonexistent_tool(self):
        """Test unregistering a nonexistent tool."""
        allowlist = ToolAllowlist()

        result = allowlist.unregister_tool("nonexistent")

        assert result is False


class TestToolLists:
    """Tests for tool listing methods."""

    def test_get_allowed_tools(self):
        """Test get_allowed_tools method."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        allowed = allowlist.get_allowed_tools()

        assert "web_search" in allowed
        assert "file_read" in allowed
        assert "file_write" in allowed  # Allowed in standard (with confirmation)

    def test_get_blocked_tools(self):
        """Test get_blocked_tools method."""
        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)

        blocked = allowlist.get_blocked_tools()

        assert "file_write" in blocked
        assert "code_execute" in blocked

    def test_get_tools_requiring_confirmation(self):
        """Test get_tools_requiring_confirmation method."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        requiring_confirm = allowlist.get_tools_requiring_confirmation()

        assert "file_write" in requiring_confirm
        assert "api_call" in requiring_confirm
        assert "web_search" not in requiring_confirm


class TestModeManagement:
    """Tests for mode management."""

    def test_set_mode(self):
        """Test changing research mode."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        assert allowlist.is_allowed("file_write") is True

        allowlist.set_mode(ResearchMode.READ_ONLY)

        assert allowlist.is_allowed("file_write") is False

    def test_get_mode_info(self):
        """Test get_mode_info method."""
        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD)

        info = allowlist.get_mode_info()

        assert info["mode"] == "standard"
        assert "allowed_tools" in info
        assert "blocked_tools" in info
        assert "requiring_confirmation" in info
        assert "category_rules" in info


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_is_tool_allowed_function(self):
        """Test is_tool_allowed convenience function."""
        assert is_tool_allowed("web_search", "standard") is True
        assert is_tool_allowed("file_write", "read_only") is False

    def test_is_tool_allowed_invalid_mode(self):
        """Test is_tool_allowed with invalid mode."""
        # Should default to standard
        assert is_tool_allowed("web_search", "invalid_mode") is True

    def test_get_allowed_tools_function(self):
        """Test get_allowed_tools convenience function."""
        allowed = get_allowed_tools("standard")

        assert "web_search" in allowed


class TestToolCategories:
    """Tests for tool category behavior."""

    def test_read_category_always_allowed(self):
        """Test that READ category is always allowed."""
        for mode in ResearchMode:
            allowlist = ToolAllowlist(mode=mode)
            assert allowlist.is_allowed("web_search") is True
            assert allowlist.is_allowed("file_read") is True

    def test_compute_category_always_allowed(self):
        """Test that COMPUTE category is always allowed."""
        for mode in ResearchMode:
            allowlist = ToolAllowlist(mode=mode)
            assert allowlist.is_allowed("summarize") is True
            assert allowlist.is_allowed("analyze") is True

    def test_write_category_blocked_in_read_only(self):
        """Test that WRITE category is blocked in read_only."""
        allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)

        assert allowlist.is_allowed("file_write") is False
        assert allowlist.is_allowed("api_call") is False

    def test_execute_category_requires_extended(self):
        """Test that some EXECUTE tools require extended mode."""
        allowlist_standard = ToolAllowlist(mode=ResearchMode.STANDARD)
        allowlist_extended = ToolAllowlist(mode=ResearchMode.EXTENDED)

        # shell_command is blocked in standard
        assert allowlist_standard.is_allowed("shell_command") is False

        # shell_command is allowed in extended
        assert allowlist_extended.is_allowed("shell_command") is True


class TestCustomTools:
    """Tests for custom tool configurations."""

    def test_custom_tools_in_constructor(self):
        """Test passing custom tools in constructor."""
        custom = {
            "my_tool": ToolConfig(
                name="my_tool",
                category=ToolCategory.COMPUTE,
                description="My custom tool",
            )
        }

        allowlist = ToolAllowlist(custom_tools=custom)

        assert allowlist.get_tool_config("my_tool") is not None
        assert allowlist.is_allowed("my_tool") is True

    def test_custom_tool_overrides_default(self):
        """Test that custom tool can override default."""
        custom = {
            "web_search": ToolConfig(
                name="web_search",
                category=ToolCategory.SENSITIVE,  # Override category
                blocked_in={ResearchMode.STANDARD},
            )
        }

        allowlist = ToolAllowlist(mode=ResearchMode.STANDARD, custom_tools=custom)

        # web_search should now be blocked
        assert allowlist.is_allowed("web_search") is False
