"""Skill definition data classes.

Parsed representation of a skill.yaml manifest and its companion files
(prompt.md, tools/*.py, templates/*.md).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillTrigger:
    """Auto-activation triggers for a skill."""

    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    _compiled: list[re.Pattern] = field(default_factory=list, repr=False)

    # Trigger patterns come from skill.yaml which may originate from a
    # community share. Cap length and reject obvious catastrophic-
    # backtrack shapes so a poisoned manifest can't burn the loop.
    _MAX_PATTERN_LENGTH = 256
    _BACKTRACK_RE = re.compile(r"\((?:[^()]|\([^)]*\))*\)[+*]\??[+*]")

    def __post_init__(self):
        self._compiled = []
        for pattern in self.patterns:
            if not isinstance(pattern, str) or len(pattern) > self._MAX_PATTERN_LENGTH:
                logger.warning(
                    "Skipping over-long trigger pattern (%d chars)", len(pattern) if isinstance(pattern, str) else 0
                )
                continue
            if self._BACKTRACK_RE.search(pattern):
                logger.warning("Skipping trigger pattern with nested-quantifier backtrack risk: %r", pattern)
                continue
            try:
                self._compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning("Invalid trigger pattern %r: %s", pattern, e)

    def matches(self, query: str) -> bool:
        """Return True if any keyword or pattern matches the query.

        Pattern search is bounded by the per-pattern length cap and
        backtrack-shape filter applied at compile time (above), so this
        is safe to call on attacker-controlled query strings.
        """
        # Cap the query length too — extremely long inputs can still
        # exercise pathological matching against a benign pattern.
        query_lower = query.lower()[:8192]
        bounded_query = query[:8192]
        for keyword in self.keywords:
            if keyword.lower() in query_lower:
                return True
        for compiled in self._compiled:
            if compiled.search(bounded_query):
                return True
        return False


@dataclass
class SkillTool:
    """A single tool provided by a skill."""

    name: str
    type: str  # "python" or "mcp"
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    cost_tier: str = "free"
    timeout_seconds: int = 30
    # Python tool fields
    module: str | None = None
    function: str | None = None
    # MCP tool fields
    server_command: str | None = None
    server_args: list[str] = field(default_factory=list)
    server_env: dict[str, str] = field(default_factory=dict)
    remote_tool_name: str | None = None

    def to_openai_tool_def(self, skill_name: str) -> dict:
        """Convert to OpenAI function-calling format.

        Tool names are namespaced as ``skill_name__tool_name`` to prevent
        conflicts between skills.
        """
        qualified_name = f"{skill_name.replace('-', '_')}__{self.name}"
        return {
            "type": "function",
            "function": {
                "name": qualified_name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillTool:
        """Create from a tool entry in skill.yaml."""
        server = data.get("server", {})
        return cls(
            name=data["name"],
            type=data.get("type", "python"),
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            cost_tier=data.get("cost_tier", "free"),
            timeout_seconds=data.get("timeout_seconds", 30),
            module=data.get("module"),
            function=data.get("function"),
            server_command=server.get("command"),
            server_args=server.get("args", []),
            server_env=server.get("env", {}),
            remote_tool_name=data.get("remote_tool_name"),
        )


@dataclass
class SkillBudget:
    """Budget constraints for a skill."""

    max_per_call: float = 1.0
    default_budget: float = 5.0


@dataclass
class SkillDefinition:
    """Complete parsed skill definition."""

    name: str
    version: str
    description: str
    path: Path
    tier: str  # "built-in", "global", or "expert-local"
    domains: list[str] = field(default_factory=list)
    author: str = ""
    license: str = ""
    triggers: SkillTrigger = field(default_factory=SkillTrigger)
    tools: list[SkillTool] = field(default_factory=list)
    prompt_file: str = "prompt.md"
    output_templates: dict[str, Any] = field(default_factory=dict)
    budget: SkillBudget = field(default_factory=SkillBudget)
    _prompt_content: str | None = field(default=None, repr=False)

    @classmethod
    def load(cls, skill_dir: Path, tier: str) -> SkillDefinition:
        """Parse skill.yaml and companion files from a directory.

        Args:
            skill_dir: Directory containing skill.yaml
            tier: Storage tier ("built-in", "global", or "expert-local")

        Returns:
            SkillDefinition instance

        Raises:
            FileNotFoundError: If skill.yaml is missing
            yaml.YAMLError: If YAML is malformed
        """
        manifest_path = skill_dir / "skill.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No skill.yaml in {skill_dir}")

        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid skill.yaml in {skill_dir}: expected mapping")

        # Parse triggers
        trigger_data = data.get("triggers", {})
        triggers = SkillTrigger(
            keywords=trigger_data.get("keywords", []),
            patterns=trigger_data.get("patterns", []),
        )

        # Parse tools
        tools = [SkillTool.from_dict(t) for t in data.get("tools", [])]

        # Parse budget
        budget_data = data.get("budget", {})
        budget = SkillBudget(
            max_per_call=budget_data.get("max_per_call", 1.0),
            default_budget=budget_data.get("default_budget", 5.0),
        )

        return cls(
            name=data.get("name", skill_dir.name),
            version=data.get("version", "0.1.0"),
            description=data.get("description", ""),
            path=skill_dir,
            tier=tier,
            domains=data.get("domains", []),
            author=data.get("author", ""),
            license=data.get("license", ""),
            triggers=triggers,
            tools=tools,
            prompt_file=data.get("prompt_file", "prompt.md"),
            output_templates=data.get("output_templates", {}),
            budget=budget,
        )

    def load_prompt(self) -> str:
        """Load prompt.md content (lazy, cached).

        The ``prompt_file`` field is read verbatim from skill.yaml. A
        skill with ``prompt_file: ../../../etc/passwd`` (or any path
        that resolves outside the skill directory) is silently rejected
        here so a malicious / community-supplied manifest cannot pull
        arbitrary host files into the system prompt.
        """
        if self._prompt_content is not None:
            return self._prompt_content

        # Reject absolute paths and parent-traversal segments outright.
        from pathlib import Path as _Path

        if _Path(self.prompt_file).is_absolute() or ".." in _Path(self.prompt_file).parts:
            logger.warning(
                "Skill %s: prompt_file %r escapes skill dir; ignoring",
                self.name,
                self.prompt_file,
            )
            self._prompt_content = ""
            return ""

        skill_root = self.path.resolve()
        prompt_path = (self.path / self.prompt_file).resolve()
        try:
            prompt_path.relative_to(skill_root)
        except ValueError:
            logger.warning(
                "Skill %s: prompt_file %r resolves outside skill dir; ignoring",
                self.name,
                self.prompt_file,
            )
            self._prompt_content = ""
            return ""

        if prompt_path.is_file():
            self._prompt_content = prompt_path.read_text(encoding="utf-8")
        else:
            self._prompt_content = ""
        return self._prompt_content

    def get_summary(self) -> str:
        """One-line summary for progressive disclosure.

        Example: 'market-data: 2 tools (get_earnings, calculate_ratios)'
        """
        tool_names = ", ".join(t.name for t in self.tools)
        return f"{self.name}: {len(self.tools)} tool{'s' if len(self.tools) != 1 else ''} ({tool_names})"
