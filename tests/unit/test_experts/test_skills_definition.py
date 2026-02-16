"""Tests for skill definition data classes.

Tests SkillTrigger, SkillTool, SkillBudget, and SkillDefinition including
YAML loading, pattern matching, OpenAI tool conversion, and prompt caching.
"""

import logging
from pathlib import Path

import pytest

from deepr.experts.skills.definition import (
    SkillBudget,
    SkillDefinition,
    SkillTool,
    SkillTrigger,
)


# ---------------------------------------------------------------------------
# SkillTrigger
# ---------------------------------------------------------------------------


class TestSkillTrigger:
    """Tests for SkillTrigger dataclass."""

    def test_empty_trigger(self):
        """Default trigger has no keywords or patterns."""
        trigger = SkillTrigger()
        assert trigger.keywords == []
        assert trigger.patterns == []
        assert trigger._compiled == []

    def test_keywords_stored(self):
        """Keywords are stored as provided."""
        trigger = SkillTrigger(keywords=["alpha", "Beta"])
        assert trigger.keywords == ["alpha", "Beta"]

    def test_patterns_compiled(self):
        """Valid patterns are compiled to regex objects."""
        trigger = SkillTrigger(patterns=[r"calculate .+ ratio", r"financial (analysis|metrics)"])
        assert len(trigger._compiled) == 2

    def test_keyword_match_case_insensitive(self):
        """Keyword matching is case-insensitive."""
        trigger = SkillTrigger(keywords=["P/E ratio"])
        assert trigger.matches("What is the P/E ratio?")
        assert trigger.matches("WHAT IS THE P/E RATIO?")
        assert trigger.matches("show p/e ratio for AAPL")

    def test_keyword_match_substring(self):
        """Keywords match as substrings."""
        trigger = SkillTrigger(keywords=["margin"])
        assert trigger.matches("profit margin analysis")
        assert trigger.matches("what is the margin?")

    def test_keyword_no_match(self):
        """Returns False when no keyword matches."""
        trigger = SkillTrigger(keywords=["debt-to-equity"])
        assert not trigger.matches("What is the weather today?")

    def test_pattern_match(self):
        """Regex pattern matching works."""
        trigger = SkillTrigger(patterns=[r"calculate .+ ratio"])
        assert trigger.matches("calculate P/E ratio")
        assert trigger.matches("please calculate debt-to-equity ratio now")

    def test_pattern_match_case_insensitive(self):
        """Pattern matching is case-insensitive (re.IGNORECASE)."""
        trigger = SkillTrigger(patterns=[r"financial analysis"])
        assert trigger.matches("Financial Analysis report")
        assert trigger.matches("FINANCIAL ANALYSIS")

    def test_pattern_no_match(self):
        """Returns False when no pattern matches."""
        trigger = SkillTrigger(patterns=[r"^calculate \d+ ratio$"])
        assert not trigger.matches("what is the weather")

    def test_invalid_pattern_gracefully_skipped(self, caplog):
        """Invalid regex patterns are logged and skipped, not raised."""
        with caplog.at_level(logging.WARNING):
            trigger = SkillTrigger(patterns=[r"[invalid", r"valid .+ pattern"])
        # Only the valid pattern should be compiled
        assert len(trigger._compiled) == 1
        assert "Invalid trigger pattern" in caplog.text

    def test_mixed_keywords_and_patterns(self):
        """Both keywords and patterns can trigger a match."""
        trigger = SkillTrigger(
            keywords=["ROE"],
            patterns=[r"compare .+ stocks"],
        )
        # Keyword match
        assert trigger.matches("What is the ROE?")
        # Pattern match
        assert trigger.matches("compare AAPL and GOOG stocks")
        # Neither
        assert not trigger.matches("What is the weather?")

    def test_empty_query(self):
        """Empty query string does not match keywords or patterns."""
        trigger = SkillTrigger(keywords=["hello"], patterns=[r"world"])
        assert not trigger.matches("")

    def test_no_keywords_or_patterns_returns_false(self):
        """Empty trigger never matches."""
        trigger = SkillTrigger()
        assert not trigger.matches("anything at all")


# ---------------------------------------------------------------------------
# SkillTool
# ---------------------------------------------------------------------------


class TestSkillTool:
    """Tests for SkillTool dataclass."""

    def test_creation_with_required_fields(self):
        """SkillTool can be created with only required fields."""
        tool = SkillTool(name="my_tool", type="python", description="A tool")
        assert tool.name == "my_tool"
        assert tool.type == "python"
        assert tool.description == "A tool"

    def test_default_values(self):
        """Verify default values for optional fields."""
        tool = SkillTool(name="t", type="python", description="d")
        assert tool.parameters == {}
        assert tool.cost_tier == "free"
        assert tool.timeout_seconds == 30
        assert tool.module is None
        assert tool.function is None
        assert tool.server_command is None
        assert tool.server_args == []
        assert tool.server_env == {}
        assert tool.remote_tool_name is None

    def test_from_dict_python_tool(self):
        """from_dict parses a Python tool entry correctly."""
        data = {
            "name": "calculate_ratios",
            "type": "python",
            "module": "tools.ratios",
            "function": "calculate_financial_ratios",
            "description": "Calculate financial ratios",
            "cost_tier": "free",
            "timeout_seconds": 60,
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "object"},
                },
                "required": ["data"],
            },
        }
        tool = SkillTool.from_dict(data)
        assert tool.name == "calculate_ratios"
        assert tool.type == "python"
        assert tool.module == "tools.ratios"
        assert tool.function == "calculate_financial_ratios"
        assert tool.description == "Calculate financial ratios"
        assert tool.cost_tier == "free"
        assert tool.timeout_seconds == 60
        assert "data" in tool.parameters["properties"]
        # MCP fields should be absent / default
        assert tool.server_command is None
        assert tool.server_args == []
        assert tool.server_env == {}
        assert tool.remote_tool_name is None

    def test_from_dict_mcp_tool(self):
        """from_dict parses an MCP tool entry with server block."""
        data = {
            "name": "web_search",
            "type": "mcp",
            "description": "Search the web",
            "remote_tool_name": "brave_search",
            "server": {
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server"],
                "env": {"API_KEY": "secret"},
            },
        }
        tool = SkillTool.from_dict(data)
        assert tool.name == "web_search"
        assert tool.type == "mcp"
        assert tool.server_command == "npx"
        assert tool.server_args == ["-y", "@anthropic/mcp-server"]
        assert tool.server_env == {"API_KEY": "secret"}
        assert tool.remote_tool_name == "brave_search"

    def test_from_dict_defaults(self):
        """from_dict uses defaults for missing optional fields."""
        data = {"name": "minimal"}
        tool = SkillTool.from_dict(data)
        assert tool.type == "python"
        assert tool.description == ""
        assert tool.parameters == {}
        assert tool.cost_tier == "free"
        assert tool.timeout_seconds == 30
        assert tool.module is None
        assert tool.function is None

    def test_to_openai_tool_def_basic(self):
        """to_openai_tool_def produces valid OpenAI function schema."""
        tool = SkillTool(
            name="get_price",
            type="python",
            description="Get stock price",
            parameters={
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        )
        result = tool.to_openai_tool_def("market-data")
        assert result["type"] == "function"
        assert result["function"]["name"] == "market_data__get_price"
        assert result["function"]["description"] == "Get stock price"
        assert result["function"]["parameters"]["required"] == ["ticker"]

    def test_to_openai_tool_def_hyphen_replacement(self):
        """Hyphens in skill name are replaced with underscores."""
        tool = SkillTool(name="my_tool", type="python", description="desc")
        result = tool.to_openai_tool_def("my-cool-skill")
        assert result["function"]["name"] == "my_cool_skill__my_tool"

    def test_to_openai_tool_def_no_hyphens(self):
        """Skill names without hyphens are left unchanged."""
        tool = SkillTool(name="run", type="python", description="desc")
        result = tool.to_openai_tool_def("simple")
        assert result["function"]["name"] == "simple__run"

    def test_to_openai_tool_def_empty_parameters(self):
        """Empty parameters dict is replaced with default schema."""
        tool = SkillTool(name="ping", type="python", description="ping", parameters={})
        result = tool.to_openai_tool_def("skill")
        assert result["function"]["parameters"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# SkillBudget
# ---------------------------------------------------------------------------


class TestSkillBudget:
    """Tests for SkillBudget dataclass."""

    def test_defaults(self):
        """Default budget values are 1.0 max_per_call and 5.0 default_budget."""
        budget = SkillBudget()
        assert budget.max_per_call == 1.0
        assert budget.default_budget == 5.0

    def test_custom_values(self):
        """Custom budget values are stored correctly."""
        budget = SkillBudget(max_per_call=0.5, default_budget=10.0)
        assert budget.max_per_call == 0.5
        assert budget.default_budget == 10.0

    def test_zero_budget(self):
        """Zero budget (free skills) is valid."""
        budget = SkillBudget(max_per_call=0.0, default_budget=0.0)
        assert budget.max_per_call == 0.0
        assert budget.default_budget == 0.0


# ---------------------------------------------------------------------------
# SkillDefinition
# ---------------------------------------------------------------------------


class TestSkillDefinitionLoad:
    """Tests for SkillDefinition.load()."""

    SAMPLE_YAML = """\
name: financial-data
version: "1.0.0"
description: "Financial ratio calculations and data analysis"
author: "Deepr"
license: "MIT"
domains: ["financial", "investment", "economics", "accounting"]
triggers:
  keywords: ["P/E ratio", "debt-to-equity", "financial ratio"]
  patterns: ["calculate .+ ratio", "financial (analysis|metrics)"]
prompt_file: "prompt.md"
tools:
  - name: calculate_ratios
    type: python
    module: tools.ratios
    function: calculate_financial_ratios
    description: "Calculate financial ratios"
    cost_tier: free
    parameters:
      type: object
      properties:
        data:
          type: object
          description: "Financial data dict"
      required: ["data"]
budget:
  max_per_call: 0.0
  default_budget: 0.0
"""

    def _create_skill_dir(self, tmp_path: Path, yaml_content: str, prompt_content: str = "You are a helper.") -> Path:
        """Helper: create a skill directory with skill.yaml and optional prompt.md."""
        skill_dir = tmp_path / "financial-data"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")
        if prompt_content is not None:
            (skill_dir / "prompt.md").write_text(prompt_content, encoding="utf-8")
        return skill_dir

    def test_load_full_manifest(self, tmp_path):
        """Load a complete skill.yaml and verify all fields."""
        skill_dir = self._create_skill_dir(tmp_path, self.SAMPLE_YAML)
        defn = SkillDefinition.load(skill_dir, tier="built-in")

        assert defn.name == "financial-data"
        assert defn.version == "1.0.0"
        assert defn.description == "Financial ratio calculations and data analysis"
        assert defn.path == skill_dir
        assert defn.tier == "built-in"
        assert defn.author == "Deepr"
        assert defn.license == "MIT"
        assert defn.domains == ["financial", "investment", "economics", "accounting"]
        assert defn.prompt_file == "prompt.md"

    def test_load_triggers(self, tmp_path):
        """Triggers are parsed and functional after load."""
        skill_dir = self._create_skill_dir(tmp_path, self.SAMPLE_YAML)
        defn = SkillDefinition.load(skill_dir, tier="built-in")

        assert defn.triggers.matches("What is the P/E ratio?")
        assert defn.triggers.matches("calculate debt-to-equity ratio")
        assert defn.triggers.matches("financial analysis of AAPL")
        assert not defn.triggers.matches("What is the weather?")

    def test_load_tools(self, tmp_path):
        """Tools list is parsed correctly."""
        skill_dir = self._create_skill_dir(tmp_path, self.SAMPLE_YAML)
        defn = SkillDefinition.load(skill_dir, tier="built-in")

        assert len(defn.tools) == 1
        tool = defn.tools[0]
        assert tool.name == "calculate_ratios"
        assert tool.type == "python"
        assert tool.module == "tools.ratios"
        assert tool.function == "calculate_financial_ratios"
        assert tool.cost_tier == "free"

    def test_load_budget(self, tmp_path):
        """Budget values are parsed correctly."""
        skill_dir = self._create_skill_dir(tmp_path, self.SAMPLE_YAML)
        defn = SkillDefinition.load(skill_dir, tier="built-in")

        assert defn.budget.max_per_call == 0.0
        assert defn.budget.default_budget == 0.0

    def test_load_missing_yaml_raises(self, tmp_path):
        """FileNotFoundError raised when skill.yaml is absent."""
        empty_dir = tmp_path / "empty-skill"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="No skill.yaml"):
            SkillDefinition.load(empty_dir, tier="built-in")

    def test_load_invalid_yaml_not_dict_raises(self, tmp_path):
        """ValueError raised when YAML content is not a mapping."""
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="expected mapping"):
            SkillDefinition.load(skill_dir, tier="built-in")

    def test_load_scalar_yaml_raises(self, tmp_path):
        """ValueError raised when YAML content is a scalar string."""
        skill_dir = tmp_path / "scalar-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("just a string\n", encoding="utf-8")
        with pytest.raises(ValueError, match="expected mapping"):
            SkillDefinition.load(skill_dir, tier="built-in")

    def test_load_minimal_yaml_defaults(self, tmp_path):
        """Missing optional fields get sensible defaults."""
        skill_dir = tmp_path / "minimal-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: minimal\n", encoding="utf-8")
        defn = SkillDefinition.load(skill_dir, tier="global")

        assert defn.name == "minimal"
        assert defn.version == "0.1.0"
        assert defn.description == ""
        assert defn.tier == "global"
        assert defn.domains == []
        assert defn.author == ""
        assert defn.license == ""
        assert defn.tools == []
        assert defn.prompt_file == "prompt.md"
        assert defn.output_templates == {}
        assert defn.budget.max_per_call == 1.0
        assert defn.budget.default_budget == 5.0

    def test_load_name_defaults_to_dir_name(self, tmp_path):
        """When name is missing from YAML, directory name is used."""
        skill_dir = tmp_path / "my-auto-named-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("version: '2.0.0'\n", encoding="utf-8")
        defn = SkillDefinition.load(skill_dir, tier="built-in")
        assert defn.name == "my-auto-named-skill"

    def test_load_multiple_tools(self, tmp_path):
        """Multiple tools are all parsed."""
        yaml_content = """\
name: multi
tools:
  - name: tool_a
    description: "First tool"
  - name: tool_b
    type: mcp
    description: "Second tool"
    server:
      command: node
      args: ["server.js"]
"""
        skill_dir = tmp_path / "multi"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")
        defn = SkillDefinition.load(skill_dir, tier="built-in")
        assert len(defn.tools) == 2
        assert defn.tools[0].name == "tool_a"
        assert defn.tools[1].name == "tool_b"
        assert defn.tools[1].type == "mcp"
        assert defn.tools[1].server_command == "node"

    def test_load_output_templates(self, tmp_path):
        """output_templates dict is preserved."""
        yaml_content = """\
name: templated
output_templates:
  summary: "templates/summary.md"
  detail: "templates/detail.md"
"""
        skill_dir = tmp_path / "templated"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")
        defn = SkillDefinition.load(skill_dir, tier="built-in")
        assert defn.output_templates == {
            "summary": "templates/summary.md",
            "detail": "templates/detail.md",
        }


class TestSkillDefinitionLoadPrompt:
    """Tests for SkillDefinition.load_prompt()."""

    def test_load_prompt_reads_file(self, tmp_path):
        """load_prompt reads the prompt.md file content."""
        skill_dir = tmp_path / "skill-with-prompt"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: test\n", encoding="utf-8")
        prompt_text = "You are a financial analyst.\nBe precise."
        (skill_dir / "prompt.md").write_text(prompt_text, encoding="utf-8")

        defn = SkillDefinition.load(skill_dir, tier="built-in")
        result = defn.load_prompt()
        assert result == prompt_text

    def test_load_prompt_missing_file_returns_empty(self, tmp_path):
        """load_prompt returns empty string when prompt file does not exist."""
        skill_dir = tmp_path / "no-prompt"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: test\n", encoding="utf-8")
        # No prompt.md created

        defn = SkillDefinition.load(skill_dir, tier="built-in")
        result = defn.load_prompt()
        assert result == ""

    def test_load_prompt_caches_result(self, tmp_path):
        """Second call returns cached content without re-reading file."""
        skill_dir = tmp_path / "cached-prompt"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: test\n", encoding="utf-8")
        (skill_dir / "prompt.md").write_text("Original prompt", encoding="utf-8")

        defn = SkillDefinition.load(skill_dir, tier="built-in")
        first = defn.load_prompt()
        assert first == "Original prompt"

        # Overwrite the file on disk
        (skill_dir / "prompt.md").write_text("Modified prompt", encoding="utf-8")

        # Should still return cached value
        second = defn.load_prompt()
        assert second == "Original prompt"

    def test_load_prompt_caches_empty_string(self, tmp_path):
        """Even an empty-string result is cached (no re-read)."""
        skill_dir = tmp_path / "cache-empty"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text("name: test\n", encoding="utf-8")
        # No prompt.md

        defn = SkillDefinition.load(skill_dir, tier="built-in")
        first = defn.load_prompt()
        assert first == ""

        # Now create the file -- should still return cached empty string
        (skill_dir / "prompt.md").write_text("Late prompt", encoding="utf-8")
        second = defn.load_prompt()
        assert second == ""

    def test_load_prompt_custom_filename(self, tmp_path):
        """load_prompt respects a custom prompt_file setting."""
        yaml_content = """\
name: custom-prompt
prompt_file: "system.md"
"""
        skill_dir = tmp_path / "custom-prompt"
        skill_dir.mkdir()
        (skill_dir / "skill.yaml").write_text(yaml_content, encoding="utf-8")
        (skill_dir / "system.md").write_text("Custom prompt content", encoding="utf-8")

        defn = SkillDefinition.load(skill_dir, tier="built-in")
        assert defn.load_prompt() == "Custom prompt content"


class TestSkillDefinitionGetSummary:
    """Tests for SkillDefinition.get_summary()."""

    def _make_definition(self, name: str, tools: list[SkillTool]) -> SkillDefinition:
        """Helper to create a SkillDefinition with given tools."""
        return SkillDefinition(
            name=name,
            version="1.0.0",
            description="test",
            path=Path("/fake"),
            tier="built-in",
            tools=tools,
        )

    def test_summary_zero_tools(self):
        """Summary with no tools shows '0 tools ()'."""
        defn = self._make_definition("empty-skill", [])
        assert defn.get_summary() == "empty-skill: 0 tools ()"

    def test_summary_one_tool(self):
        """Summary with one tool uses singular 'tool'."""
        tools = [SkillTool(name="get_data", type="python", description="Get data")]
        defn = self._make_definition("data-skill", tools)
        assert defn.get_summary() == "data-skill: 1 tool (get_data)"

    def test_summary_two_tools(self):
        """Summary with multiple tools uses plural 'tools'."""
        tools = [
            SkillTool(name="get_earnings", type="python", description="Get earnings"),
            SkillTool(name="calculate_ratios", type="python", description="Calculate ratios"),
        ]
        defn = self._make_definition("market-data", tools)
        assert defn.get_summary() == "market-data: 2 tools (get_earnings, calculate_ratios)"

    def test_summary_three_tools(self):
        """Summary correctly lists three tool names."""
        tools = [
            SkillTool(name="a", type="python", description=""),
            SkillTool(name="b", type="python", description=""),
            SkillTool(name="c", type="python", description=""),
        ]
        defn = self._make_definition("triple", tools)
        assert defn.get_summary() == "triple: 3 tools (a, b, c)"
