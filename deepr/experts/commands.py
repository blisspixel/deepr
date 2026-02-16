"""Command registry for expert chat — shared between CLI and web.

Provides a unified slash-command system with categories, modes, and
completions. CLI uses ``\\`` prefix; web uses ``/``. The registry
normalises both.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chat modes
# ---------------------------------------------------------------------------

class ChatMode(Enum):
    """Chat interaction modes that control tool availability and behaviour."""

    ASK = "ask"
    RESEARCH = "research"
    ADVISE = "advise"
    FOCUS = "focus"


MODE_CONFIGS: dict[ChatMode, dict[str, Any]] = {
    ChatMode.ASK: {
        "tools": ["search_knowledge_base"],
        "system_suffix": "Answer directly and concisely. Only search your knowledge base if needed.",
        "model_bias": "fast",
        "force_tot": False,
        "label": "Ask",
        "description": "Quick answers — KB search only",
    },
    ChatMode.RESEARCH: {
        "tools": ["search_knowledge_base", "standard_research", "deep_research"],
        "system_suffix": "",
        "model_bias": "balanced",
        "force_tot": False,
        "label": "Research",
        "description": "Default — full tool access",
    },
    ChatMode.ADVISE: {
        "tools": ["search_knowledge_base", "standard_research"],
        "system_suffix": (
            "Structure your response as a consulting recommendation. "
            "Include pros/cons, risks, and a recommended path forward."
        ),
        "model_bias": "quality",
        "force_tot": False,
        "label": "Advise",
        "description": "Consulting-style structured advice",
    },
    ChatMode.FOCUS: {
        "tools": ["search_knowledge_base", "standard_research", "deep_research"],
        "system_suffix": (
            "Use advanced reasoning. Generate hypotheses, verify claims, "
            "and self-correct. Think step by step."
        ),
        "model_bias": "quality",
        "force_tot": True,
        "label": "Focus",
        "description": "Deep reasoning — Tree of Thoughts always on",
    },
}


# ---------------------------------------------------------------------------
# Command categories
# ---------------------------------------------------------------------------

class CommandCategory(Enum):
    MODE = "Mode"
    SESSION = "Session"
    REASONING = "Reasoning"
    CONTROL = "Control"
    MANAGEMENT = "Management"
    UTILITY = "Utility"


# ---------------------------------------------------------------------------
# Command definition + result
# ---------------------------------------------------------------------------

class CommandScope(Enum):
    """Where a command can be executed."""

    CLIENT_ONLY = "client_only"  # handled entirely on the client (clear, help)
    SESSION_REQUIRED = "session_required"  # needs an active ExpertChatSession


@dataclass
class ChatCommand:
    """Definition of a slash command."""

    name: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    category: CommandCategory = CommandCategory.UTILITY
    scope: CommandScope = CommandScope.SESSION_REQUIRED
    args: str = ""  # human-readable arg description, e.g. "<text>"
    hidden: bool = False  # hide from help / autocomplete


@dataclass
class CommandResult:
    """Result returned by a command handler."""

    output: str = ""
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    # Flags that the caller should interpret
    clear_chat: bool = False
    mode_changed: ChatMode | None = None
    export_content: str | None = None
    end_session: bool = False


# ---------------------------------------------------------------------------
# Registry singleton
# ---------------------------------------------------------------------------

class CommandRegistry:
    """Central registry of chat commands."""

    _instance: CommandRegistry | None = None

    def __init__(self) -> None:
        self._commands: dict[str, ChatCommand] = {}
        self._alias_map: dict[str, str] = {}  # alias -> canonical name

    @classmethod
    def get_instance(cls) -> CommandRegistry:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_defaults()
        return cls._instance

    # -- registration -------------------------------------------------------

    def register(self, cmd: ChatCommand) -> None:
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._alias_map[alias] = cmd.name

    def _register_defaults(self) -> None:
        """Register all built-in commands."""
        defaults = [
            # Mode commands
            ChatCommand("ask", [], "Switch to Ask mode (KB only)", CommandCategory.MODE, CommandScope.SESSION_REQUIRED),
            ChatCommand("research", [], "Switch to Research mode (default)", CommandCategory.MODE, CommandScope.SESSION_REQUIRED),
            ChatCommand("advise", [], "Switch to Advise mode (structured advice)", CommandCategory.MODE, CommandScope.SESSION_REQUIRED),
            ChatCommand("focus", [], "Switch to Focus mode (deep reasoning)", CommandCategory.MODE, CommandScope.SESSION_REQUIRED),
            ChatCommand("mode", [], "Show or switch mode", CommandCategory.MODE, CommandScope.SESSION_REQUIRED, args="[name]"),
            # Session commands
            ChatCommand("clear", [], "Clear conversation history", CommandCategory.SESSION, CommandScope.CLIENT_ONLY),
            ChatCommand("compact", [], "Summarise and compress conversation", CommandCategory.SESSION, CommandScope.SESSION_REQUIRED, args="[topic]"),
            ChatCommand("remember", [], "Pin a fact to session memory", CommandCategory.SESSION, CommandScope.SESSION_REQUIRED, args="<text>"),
            ChatCommand("forget", ["unpin"], "Remove a pinned memory", CommandCategory.SESSION, CommandScope.SESSION_REQUIRED, args="<index>"),
            ChatCommand("memories", ["pins"], "List pinned memories", CommandCategory.SESSION, CommandScope.SESSION_REQUIRED),
            ChatCommand("new", [], "Start a new conversation", CommandCategory.SESSION, CommandScope.CLIENT_ONLY),
            # Reasoning commands
            ChatCommand("trace", [], "Show reasoning trace", CommandCategory.REASONING, CommandScope.SESSION_REQUIRED),
            ChatCommand("why", [], "Explain the last decision", CommandCategory.REASONING, CommandScope.SESSION_REQUIRED),
            ChatCommand("decisions", [], "List all decisions this session", CommandCategory.REASONING, CommandScope.SESSION_REQUIRED),
            ChatCommand("thinking", [], "Toggle verbose thinking display", CommandCategory.REASONING, CommandScope.SESSION_REQUIRED, args="[on|off]"),
            # Control commands
            ChatCommand("model", [], "Show or change model", CommandCategory.CONTROL, CommandScope.SESSION_REQUIRED, args="[name]"),
            ChatCommand("tools", [], "List available tools for current mode", CommandCategory.CONTROL, CommandScope.SESSION_REQUIRED),
            ChatCommand("effort", [], "Set reasoning effort level", CommandCategory.CONTROL, CommandScope.SESSION_REQUIRED, args="[low|med|high]"),
            ChatCommand("budget", [], "Show or set session budget", CommandCategory.CONTROL, CommandScope.SESSION_REQUIRED, args="[amount]"),
            # Management commands
            ChatCommand("save", [], "Save current conversation", CommandCategory.MANAGEMENT, CommandScope.SESSION_REQUIRED, args="[name]"),
            ChatCommand("load", [], "Load a saved conversation", CommandCategory.MANAGEMENT, CommandScope.SESSION_REQUIRED, args="<id>"),
            ChatCommand("export", [], "Export conversation as markdown or JSON", CommandCategory.MANAGEMENT, CommandScope.SESSION_REQUIRED, args="[md|json]"),
            ChatCommand("council", [], "Consult multiple experts", CommandCategory.MANAGEMENT, CommandScope.SESSION_REQUIRED, args="<query>"),
            ChatCommand("plan", [], "Decompose a complex query into steps", CommandCategory.MANAGEMENT, CommandScope.SESSION_REQUIRED, args="<query>"),
            # Utility commands
            ChatCommand("help", ["?"], "Show command help", CommandCategory.UTILITY, CommandScope.CLIENT_ONLY, args="[command]"),
            ChatCommand("status", [], "Show session statistics", CommandCategory.UTILITY, CommandScope.SESSION_REQUIRED),
            ChatCommand("quit", ["exit", "q"], "End the chat session", CommandCategory.UTILITY, CommandScope.CLIENT_ONLY),
        ]
        for cmd in defaults:
            self.register(cmd)

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> ChatCommand | None:
        """Look up a command by name or alias."""
        canonical = self._alias_map.get(name, name)
        return self._commands.get(canonical)

    def parse(self, raw_input: str) -> tuple[ChatCommand | None, str]:
        """Parse user input into a command and its arguments.

        Strips leading ``/`` or ``\\`` and splits into command + args.
        Returns ``(None, "")`` if the input is not a command.
        """
        text = raw_input.strip()
        if not text:
            return None, ""

        # Normalise prefix
        if text.startswith("/") or text.startswith("\\"):
            text = text[1:]
        else:
            return None, ""

        parts = text.split(None, 1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self.get(cmd_name)
        return cmd, args

    # -- listing / completions ----------------------------------------------

    def list_commands(self, include_hidden: bool = False) -> list[ChatCommand]:
        return [c for c in self._commands.values() if include_hidden or not c.hidden]

    def get_completions(self, prefix: str) -> list[ChatCommand]:
        """Return commands whose name or alias starts with *prefix*."""
        prefix = prefix.lower().lstrip("/").lstrip("\\")
        results: list[ChatCommand] = []
        seen: set[str] = set()
        for cmd in self._commands.values():
            if cmd.hidden:
                continue
            if cmd.name.startswith(prefix) and cmd.name not in seen:
                results.append(cmd)
                seen.add(cmd.name)
            for alias in cmd.aliases:
                if alias.startswith(prefix) and cmd.name not in seen:
                    results.append(cmd)
                    seen.add(cmd.name)
        return results

    def commands_by_category(self) -> dict[CommandCategory, list[ChatCommand]]:
        """Return commands grouped by category."""
        groups: dict[CommandCategory, list[ChatCommand]] = {}
        for cmd in self._commands.values():
            if cmd.hidden:
                continue
            groups.setdefault(cmd.category, []).append(cmd)
        return groups
