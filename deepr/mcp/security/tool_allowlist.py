"""Tool allowlist for MCP research modes.

Controls which tools are available in different research modes,
and which require user confirmation before execution.

Usage:
    from deepr.mcp.security.tool_allowlist import ToolAllowlist, ResearchMode

    allowlist = ToolAllowlist()

    # Check if a tool is allowed
    if allowlist.is_allowed("web_search", ResearchMode.STANDARD):
        # Tool can be used
        pass

    # Check if confirmation is required
    if allowlist.require_confirmation("file_write", ResearchMode.STANDARD):
        # Prompt user before executing
        pass
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ResearchMode(Enum):
    """Research mode determines tool availability."""

    READ_ONLY = "read_only"  # Only read operations
    STANDARD = "standard"  # Normal research operations
    EXTENDED = "extended"  # Includes write operations with confirmation
    UNRESTRICTED = "unrestricted"  # All tools, no confirmation (use with caution)


class ToolCategory(Enum):
    """Categories of tools by risk level."""

    READ = "read"  # Read-only operations (web search, file read)
    COMPUTE = "compute"  # Computation/analysis (no side effects)
    WRITE = "write"  # Write operations (file write, API calls)
    EXECUTE = "execute"  # Code/command execution
    SENSITIVE = "sensitive"  # Access to sensitive data


@dataclass
class ToolConfig:
    """Configuration for a tool."""

    name: str
    category: ToolCategory
    description: str = ""
    requires_confirmation_in: set[ResearchMode] = field(default_factory=set)
    blocked_in: set[ResearchMode] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolAllowlist:
    """Manages tool permissions per research mode.

    Provides centralized control over which tools can be used
    and which require user confirmation.

    Attributes:
        mode: Current research mode
    """

    # Default tool configurations
    DEFAULT_TOOLS: dict[str, ToolConfig] = {
        # Read tools
        "web_search": ToolConfig(
            name="web_search",
            category=ToolCategory.READ,
            description="Search the web for information",
        ),
        "web_fetch": ToolConfig(
            name="web_fetch",
            category=ToolCategory.READ,
            description="Fetch content from a URL",
        ),
        "file_read": ToolConfig(
            name="file_read",
            category=ToolCategory.READ,
            description="Read a file from the filesystem",
        ),
        "arxiv_search": ToolConfig(
            name="arxiv_search",
            category=ToolCategory.READ,
            description="Search arXiv for papers",
        ),
        "semantic_scholar": ToolConfig(
            name="semantic_scholar",
            category=ToolCategory.READ,
            description="Search Semantic Scholar",
        ),
        # Compute tools
        "summarize": ToolConfig(
            name="summarize",
            category=ToolCategory.COMPUTE,
            description="Summarize text content",
        ),
        "analyze": ToolConfig(
            name="analyze",
            category=ToolCategory.COMPUTE,
            description="Analyze data or text",
        ),
        "extract": ToolConfig(
            name="extract",
            category=ToolCategory.COMPUTE,
            description="Extract structured data",
        ),
        # Write tools
        "file_write": ToolConfig(
            name="file_write",
            category=ToolCategory.WRITE,
            description="Write content to a file",
            requires_confirmation_in={ResearchMode.STANDARD, ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY},
        ),
        "api_call": ToolConfig(
            name="api_call",
            category=ToolCategory.WRITE,
            description="Make an external API call",
            requires_confirmation_in={ResearchMode.STANDARD, ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY},
        ),
        # Execute tools
        "code_execute": ToolConfig(
            name="code_execute",
            category=ToolCategory.EXECUTE,
            description="Execute code in a sandbox",
            requires_confirmation_in={ResearchMode.STANDARD, ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY},
        ),
        "shell_command": ToolConfig(
            name="shell_command",
            category=ToolCategory.EXECUTE,
            description="Execute a shell command",
            requires_confirmation_in={ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY, ResearchMode.STANDARD},
        ),
        # Sensitive tools
        "credential_access": ToolConfig(
            name="credential_access",
            category=ToolCategory.SENSITIVE,
            description="Access stored credentials",
            requires_confirmation_in={ResearchMode.STANDARD, ResearchMode.EXTENDED},
            blocked_in={ResearchMode.READ_ONLY},
        ),
    }

    # Category-level rules per mode
    CATEGORY_RULES: dict[ResearchMode, dict[ToolCategory, str]] = {
        ResearchMode.READ_ONLY: {
            ToolCategory.READ: "allow",
            ToolCategory.COMPUTE: "allow",
            ToolCategory.WRITE: "block",
            ToolCategory.EXECUTE: "block",
            ToolCategory.SENSITIVE: "block",
        },
        ResearchMode.STANDARD: {
            ToolCategory.READ: "allow",
            ToolCategory.COMPUTE: "allow",
            ToolCategory.WRITE: "confirm",
            ToolCategory.EXECUTE: "confirm",
            ToolCategory.SENSITIVE: "confirm",
        },
        ResearchMode.EXTENDED: {
            ToolCategory.READ: "allow",
            ToolCategory.COMPUTE: "allow",
            ToolCategory.WRITE: "confirm",
            ToolCategory.EXECUTE: "confirm",
            ToolCategory.SENSITIVE: "confirm",
        },
        ResearchMode.UNRESTRICTED: {
            ToolCategory.READ: "allow",
            ToolCategory.COMPUTE: "allow",
            ToolCategory.WRITE: "allow",
            ToolCategory.EXECUTE: "allow",
            ToolCategory.SENSITIVE: "allow",
        },
    }

    def __init__(
        self,
        mode: ResearchMode = ResearchMode.STANDARD,
        custom_tools: Optional[dict[str, ToolConfig]] = None,
    ):
        """Initialize the allowlist.

        Args:
            mode: Research mode to use
            custom_tools: Additional tool configurations
        """
        self.mode = mode
        self._tools = dict(self.DEFAULT_TOOLS)

        if custom_tools:
            self._tools.update(custom_tools)

    def is_allowed(
        self,
        tool_name: str,
        mode: Optional[ResearchMode] = None,
    ) -> bool:
        """Check if a tool is allowed in the given mode.

        Args:
            tool_name: Name of the tool
            mode: Research mode (uses instance mode if not provided)

        Returns:
            True if tool is allowed
        """
        mode = mode or self.mode
        tool_config = self._tools.get(tool_name)

        if not tool_config:
            # Unknown tool - block in read_only, allow in others
            return mode != ResearchMode.READ_ONLY

        # Check explicit block list
        if mode in tool_config.blocked_in:
            return False

        # Check category rules
        category_rules = self.CATEGORY_RULES.get(mode, {})
        rule = category_rules.get(tool_config.category, "allow")

        return rule != "block"

    def require_confirmation(
        self,
        tool_name: str,
        mode: Optional[ResearchMode] = None,
    ) -> bool:
        """Check if a tool requires user confirmation.

        Args:
            tool_name: Name of the tool
            mode: Research mode (uses instance mode if not provided)

        Returns:
            True if confirmation is required
        """
        mode = mode or self.mode
        tool_config = self._tools.get(tool_name)

        # Unrestricted mode never requires confirmation
        if mode == ResearchMode.UNRESTRICTED:
            return False

        if not tool_config:
            # Unknown tool requires confirmation except in unrestricted
            return True

        # Check explicit confirmation list
        if mode in tool_config.requires_confirmation_in:
            return True

        # Check category rules
        category_rules = self.CATEGORY_RULES.get(mode, {})
        rule = category_rules.get(tool_config.category, "allow")

        return rule == "confirm"

    def get_tool_config(self, tool_name: str) -> Optional[ToolConfig]:
        """Get configuration for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolConfig or None if not found
        """
        return self._tools.get(tool_name)

    def register_tool(
        self,
        name: str,
        category: ToolCategory,
        description: str = "",
        requires_confirmation_in: Optional[set[ResearchMode]] = None,
        blocked_in: Optional[set[ResearchMode]] = None,
    ) -> ToolConfig:
        """Register a new tool.

        Args:
            name: Tool name
            category: Tool category
            description: Tool description
            requires_confirmation_in: Modes requiring confirmation
            blocked_in: Modes where tool is blocked

        Returns:
            Created ToolConfig
        """
        config = ToolConfig(
            name=name,
            category=category,
            description=description,
            requires_confirmation_in=requires_confirmation_in or set(),
            blocked_in=blocked_in or set(),
        )
        self._tools[name] = config
        return config

    def unregister_tool(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was unregistered
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_allowed_tools(
        self,
        mode: Optional[ResearchMode] = None,
    ) -> list[str]:
        """Get list of allowed tools for a mode.

        Args:
            mode: Research mode (uses instance mode if not provided)

        Returns:
            List of allowed tool names
        """
        mode = mode or self.mode
        return [name for name in self._tools.keys() if self.is_allowed(name, mode)]

    def get_blocked_tools(
        self,
        mode: Optional[ResearchMode] = None,
    ) -> list[str]:
        """Get list of blocked tools for a mode.

        Args:
            mode: Research mode (uses instance mode if not provided)

        Returns:
            List of blocked tool names
        """
        mode = mode or self.mode
        return [name for name in self._tools.keys() if not self.is_allowed(name, mode)]

    def get_tools_requiring_confirmation(
        self,
        mode: Optional[ResearchMode] = None,
    ) -> list[str]:
        """Get list of tools requiring confirmation.

        Args:
            mode: Research mode (uses instance mode if not provided)

        Returns:
            List of tool names requiring confirmation
        """
        mode = mode or self.mode
        return [
            name for name in self._tools.keys() if self.is_allowed(name, mode) and self.require_confirmation(name, mode)
        ]

    def validate_tool_call(
        self,
        tool_name: str,
        mode: Optional[ResearchMode] = None,
    ) -> dict:
        """Validate a tool call and return status.

        Args:
            tool_name: Name of the tool
            mode: Research mode (uses instance mode if not provided)

        Returns:
            Dict with 'allowed', 'requires_confirmation', 'reason' keys
        """
        mode = mode or self.mode
        allowed = self.is_allowed(tool_name, mode)
        requires_confirmation = self.require_confirmation(tool_name, mode) if allowed else False

        if not allowed:
            tool_config = self._tools.get(tool_name)
            if tool_config:
                reason = f"Tool '{tool_name}' (category: {tool_config.category.value}) is blocked in {mode.value} mode"
            else:
                reason = f"Unknown tool '{tool_name}' is blocked in {mode.value} mode"
        elif requires_confirmation:
            reason = f"Tool '{tool_name}' requires user confirmation in {mode.value} mode"
        else:
            reason = "Tool is allowed"

        return {
            "allowed": allowed,
            "requires_confirmation": requires_confirmation,
            "reason": reason,
            "mode": mode.value,
            "tool_name": tool_name,
        }

    def set_mode(self, mode: ResearchMode) -> None:
        """Change the research mode.

        Args:
            mode: New research mode
        """
        self.mode = mode

    def get_mode_info(self, mode: Optional[ResearchMode] = None) -> dict:
        """Get information about a research mode.

        Args:
            mode: Research mode (uses instance mode if not provided)

        Returns:
            Dict with mode information
        """
        mode = mode or self.mode
        rules = self.CATEGORY_RULES.get(mode, {})

        return {
            "mode": mode.value,
            "allowed_tools": len(self.get_allowed_tools(mode)),
            "blocked_tools": len(self.get_blocked_tools(mode)),
            "requiring_confirmation": len(self.get_tools_requiring_confirmation(mode)),
            "category_rules": {cat.value: rule for cat, rule in rules.items()},
        }


# Convenience functions


def is_tool_allowed(tool_name: str, mode: str = "standard") -> bool:
    """Check if a tool is allowed in the given mode.

    Args:
        tool_name: Name of the tool
        mode: Research mode string

    Returns:
        True if tool is allowed
    """
    try:
        research_mode = ResearchMode(mode)
    except ValueError:
        research_mode = ResearchMode.STANDARD

    allowlist = ToolAllowlist(mode=research_mode)
    return allowlist.is_allowed(tool_name)


def get_allowed_tools(mode: str = "standard") -> list[str]:
    """Get list of allowed tools for a mode.

    Args:
        mode: Research mode string

    Returns:
        List of allowed tool names
    """
    try:
        research_mode = ResearchMode(mode)
    except ValueError:
        research_mode = ResearchMode.STANDARD

    allowlist = ToolAllowlist(mode=research_mode)
    return allowlist.get_allowed_tools()
